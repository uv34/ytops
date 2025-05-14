import base64
import pickle
import socket
import threading
import time
import ssl

import encryption
import protocol
from general_server import verify_token
from mysql_helper import DBController
from ogg_handler import *
from encryption import CryptoManager

CHUNK_SIZE = 8192
DELAY = 0.1  # artificial delay


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
        self.db = DBController(host="127.0.0.1", user="stopify", password="stop123", database="mydb")
        self.stop_events = {}

    def start_server(self):
        """
        initialize the server
        """
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(certfile='webroot/cert.pem',
                                keyfile='webroot/key.pem')

        serv_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        serv_sock.bind((self.host, self.port))
        serv_sock.listen()
        print(f"Server listening on {self.host}:{self.port}...")
        while True:
            conn, addr = serv_sock.accept()
            ssl_conn = context.wrap_socket(conn, server_side=True, do_handshake_on_connect=True)
            print(f"Connection from {addr}")
            self.stop_events[ssl_conn] = threading.Event()
            threading.Thread(target=self.handle_client, args=(ssl_conn,), daemon=True).start()

    def handle_client(self, conn):
        """
        Handles client requests for streaming an Ogg Vorbis file.
        - Reads & validates "RQST song.ogg~time" -> extracts metadata (pages, duration, sample rate).
        - Sends "PGNM" 2response with playback details or "ERR" if invalid request.
        - Determines stream start: from 0 (if within headers) or re-injects headers & seeks.
        - Streams Ogg pages -> listens for "STOP" in a separate thread.
        - Sends "SCNF" on completion, cleans up, and closes connection.
        """
        cryp = CryptoManager()
        msg = protocol.create_msg("SHKY", base64.b64encode(str(cryp.public_key).encode()))
        conn.send(msg)
        cmd, data = protocol.get_msg(conn)
        if cmd != 'SHKY':
            return
        pub_b = int(base64.b64decode(data).decode())
        shared_key = cryp.shared_secret(pub_b)
        shared_key = cryp.hash_secret(shared_key)
        print(shared_key, '_'*100)

        stop_event = self.stop_events[conn]
        # 1) Read request

        cmd, data = protocol.get_msg(conn)
        if cmd != "RQST":
            print("Expected RQST, got:", cmd)
            conn.close()
            return

        parts = data.decode().split('~')
        if len(parts) != 3:
            print("Bad request format: must be 'token~song.ogg~time'")
            conn.sendall(protocol.create_msg("ERR ", b"Bad request"))
            conn.close()
            return

        tok, song_id, t_str = parts
        payload = verify_token(tok)
        if not payload:
            conn.sendall(protocol.create_msg("ERR ", b"invalid token b"))
            print('invalid token')
            return
        print(f"playing for user {str(payload['user'])}")
        asked_time = float(t_str)

        song = self.db.get_song(song_id)
        filepath = f'songs/{song_id}.ogg'
        if song is None:
            print(f"File not found: {song_id}.ogg")
            conn.sendall(protocol.create_msg("ERR ", b"Song does not exist"))
            conn.close()
            return
        print(song)

        # 2) Build page index
        page_offsets = build_page_index(filepath)
        total_pages = len(page_offsets)
        print(f"'{song_id}' => total_pages={total_pages}")

        # 3) Extract headers + find last_header_page
        header_data, last_header_page_idx = extract_header_data_and_last_page(filepath)
        print(f"Extracted header pages up to page {last_header_page_idx}")
        times = build_time_index(filepath, total_pages)

        # 4) Compute total duration
        duration = song['length']
        sample_rate = song['sample_rate']
        album = self.db.get_album(song['album_id'])
        page_num = closest_index(times, asked_time)
        current_time = get_time_until_page(filepath, page_num)
        print(f"-"*50)
        print(f"asked_time={asked_time}, duration={duration}")
        print(f"-"*50)
        if asked_time >= duration or times[page_num] >= duration:
            print("Requested time out of range")
            err_msg = b"Requested time out of range"
            conn.sendall(protocol.create_msg("ERR ", err_msg))
            conn.close()
            return

        # 5) Send PGNM "<total_pages>~<duration>"
        real_page = 0 if page_num <= last_header_page_idx else page_num - 2
        with open(f'covers/{album["id"]}.jpg', 'rb') as f:
            cover_data = f.read()
        # dumps contained ~ so i used |
        pgnm_data = (f"{song['name']}~{song['author']}~{album['name']}~{total_pages}~{duration}~{current_time}~"
                     f"{sample_rate}~{real_page}|").encode() + pickle.dumps(times) + b"|" + base64.b64encode(cover_data)

        conn.sendall(protocol.create_msg("PGNM", pgnm_data))
        print(f"Sent PGNM: {total_pages} pages, {duration} sec")

        # 6) Decide how to stream:
        # If page_num <= last_header_page_idx => no re-injection, just stream from offset=0

        stop_thread = threading.Thread(target=self.wait_for_stop, args=(conn, stop_event))
        stop_thread.start()

        if page_num <= last_header_page_idx:
            print(f"Page {page_num} <= last_header_page_idx={last_header_page_idx}, streaming from 0 (no injection).")
            self.stream_from_offset(conn, song_id, 0, shared_key)
        elif page_num < total_pages:
            # Re-inject header_data, then jump to page_num
            print(f"Page {page_num} > last_header_page_idx={last_header_page_idx}, re-injecting headers then offset.")
            # 7) Send the Vorbis headers
            conn.sendall(protocol.create_msg("PAGE", header_data, shared_key))
            # 8) Then stream from page_offsets[page_num]
            offset = page_offsets[page_num]
            print(f"Streaming from offset={offset}, page={page_num}")
            self.stream_from_offset(conn, song_id, offset, shared_key)

        conn.sendall(protocol.create_msg("SCNF", b"1", shared_key))
        stop_event.set()
        stop_thread.join()

        conn.close()

        del self.stop_events[conn]

    def stream_from_offset(self, conn, song_name, file_offset, key):
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
                        conn.sendall(protocol.create_msg("PAGE", page_data,key))
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
