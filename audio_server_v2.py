import socket
import threading
import os
import time
import struct
import pyogg
import protocol
import pickle
from mysql_helper import DBController
from ogg_handler import *

CHUNK_SIZE = 8192
DELAY = 0  # artificial delay


def closest_index(sorted_list, target):
    """
    Finds the index of the closest number to the target in a sorted list.

    Parameters:
    sorted_list (list[float]): A list of floats sorted in ascending order.
    target (float): The number to find the closest value to.

    Returns:
    int: The index of the closest number.
    """
    if not sorted_list:
        raise ValueError("The list is empty")

    closest_idx = 0
    min_diff = abs(sorted_list[0] - target)

    for i in range(1, len(sorted_list)):
        diff = abs(sorted_list[i] - target)
        if diff < min_diff:
            min_diff = diff
            closest_idx = i
        elif diff > min_diff:
            break

    return closest_idx



class OggServer:
    """
    A server that:
      - Receives "RQST <song_name>~<time>"
      - Builds the page index and time index
      - Finds all Vorbis headers & identifies last_header_page
      - If page_num <= last_header_page: stream from offset=0 with NO re-injection
      - Else re-inject header_data, then jump to that page offset
    """

    def __init__(self, host='0.0.0.0', port=5000):
        self.host = host
        self.port = port
        self.db = DBController(host="localhost", user="root", password="SqlUV123!", database="mydb")
        self.stop_events = {}

    def start_server(self):
        """
        initialize the server
        """
        serv_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        serv_sock.bind((self.host, self.port))
        serv_sock.listen()
        print(f"Server listening on {self.host}:{self.port}...")
        while True:
            conn, addr = serv_sock.accept()
            print(f"Connection from {addr}")
            self.stop_events[conn] = threading.Event()
            threading.Thread(target=self.handle_client, args=(conn,), daemon=True).start()

    def handle_client(self, conn):
        """
        Handles client requests for streaming an Ogg Vorbis file.
        - Reads & validates "RQST song.ogg~time" -> extracts metadata (pages, duration, sample rate).
        - Sends "PGNM" response with playback details or "ERR" if invalid request.
        - Determines stream start: from 0 (if within headers) or re-injects headers & seeks.
        - Streams Ogg pages -> listens for "STOP" in a separate thread.
        - Sends "SCNF" on completion, cleans up, and closes connection.
        """
        stop_event = self.stop_events[conn]
        # 1) Read request

        cmd, data = protocol.get_msg(conn)
        if cmd != "RQST":
            print("Expected RQST, got:", cmd)
            conn.close()
            return

        parts = data.decode().split('~')
        if len(parts) != 2:
            print("Bad request format: must be 'song.ogg~time'")
            conn.sendall(protocol.create_msg("ERR ", b"Bad request"))
            conn.close()
            return

        song_name, t_str = parts
        asked_time = float(t_str)

        song = self.db.get_song(song_name)
        filepath = f'songs/{song_name}.ogg'
        if song is None:
            print(f"File not found: {song_name}")
            conn.sendall(protocol.create_msg("ERR ", b"Song does not exist"))
            conn.close()
            return
        print(song)

        # 2) Build page index
        page_offsets = build_page_index(filepath)
        total_pages = len(page_offsets)
        print(f"'{song_name}' => total_pages={total_pages}")

        # 3) Extract headers + find last_header_page
        header_data, last_header_page_idx = extract_header_data_and_last_page(filepath)
        print(f"Extracted header pages up to page {last_header_page_idx}")
        times = build_time_index(filepath, total_pages)

        # 4) Compute total duration
        duration = song['length']
        sample_rate = song['sample_rate']
        page_num = closest_index(times, asked_time)
        current_time = get_time_until_page(filepath, page_num)

        if asked_time >= duration:
            err_msg = b"Requested time out of range"
            conn.sendall(protocol.create_msg("ERR ", err_msg))
            conn.close()
            return

        # 5) Send PGNM "<total_pages>~<duration>"
        real_page = 0 if page_num <= last_header_page_idx else page_num - 2
        # dumps contained ~ so i used |
        pgnm_data = f"{total_pages}~{duration}~{current_time}~{sample_rate}~{real_page}|".encode() + pickle.dumps(times)
        print('items:', pgnm_data.count(b'|'))
        conn.sendall(protocol.create_msg("PGNM", pgnm_data))
        print(f"Sent PGNM: {total_pages} pages, {duration:.2f} sec")

        # 6) Decide how to stream:
        # If page_num <= last_header_page_idx => no re-injection, just stream from offset=0

        stop_thread = threading.Thread(target=self.wait_for_stop, args=(conn, stop_event))
        stop_thread.start()

        if page_num <= last_header_page_idx:
            print(f"Page {page_num} <= last_header_page_idx={last_header_page_idx}, streaming from 0 (no injection).")
            self.stream_from_offset(conn, song_name, 0)
        elif page_num:
            # Re-inject header_data, then jump to page_num
            print(f"Page {page_num} > last_header_page_idx={last_header_page_idx}, re-injecting headers then offset.")
            # 7) Send the Vorbis headers
            conn.sendall(protocol.create_msg("PAGE", header_data))
            # 8) Then stream from page_offsets[page_num]
            offset = page_offsets[page_num]
            print(f"Streaming from offset={offset}, page={page_num}")
            self.stream_from_offset(conn, song_name, offset)

        conn.sendall(protocol.create_msg("SCNF", b"1"))
        stop_event.set()
        stop_thread.join()

        conn.close()

        del self.stop_events[conn]

    def stream_from_offset(self, conn, song_name, file_offset):
        """
        Streams Ogg pages from 'file_offset' to EOF in 8192 chunks,
        reassembling complete pages and sending them to the client.
        """
        path = f'songs/{song_name}.ogg'
        with open(path, "rb") as f:
            f.seek(file_offset)
            buffer = bytearray()
            while not self.stop_events[conn].is_set():
                chunk = f.read(CHUNK_SIZE)
                if not chunk:
                    break
                buffer.extend(chunk)

                while b"OggS" in buffer:
                    idx = buffer.index(b"OggS")
                    if idx > 0:
                        buffer = buffer[idx:]

                    if len(buffer) < 27:
                        break
                    segs = buffer[26]
                    header_size = 27 + segs
                    if len(buffer) < header_size:
                        break

                    seg_table = buffer[27:header_size]
                    page_size = 27 + len(seg_table) + sum(seg_table)
                    if len(buffer) < page_size:
                        break

                    page_data = buffer[:page_size]
                    if not self.stop_events[conn].is_set():
                        conn.sendall(protocol.create_msg("PAGE", page_data))
                    buffer = buffer[page_size:]

                    time.sleep(DELAY)

        print(f"Finished streaming from offset={file_offset}.")

    def wait_for_stop(self, conn, stop_event):
        """
        Listens for a STOP command from the client.
        If received, sets the stop event to terminate streaming.
        """
        while not stop_event.is_set():
            try:
                cmd, data = protocol.get_msg(conn)
                if cmd == "STOP":
                    print(f"Received STOP command from client.")
                    stop_event.set()

                    break
            except Exception as e:
                print(f"Error receiving STOP command: {e}")
                break


if __name__ == "__main__":
    server = OggServer(host="0.0.0.0", port=5000)
    server.start_server()
