import socket
import threading
import os
import time
import struct
import pyogg
import protocol
import pickle

CHUNK_SIZE = 8192
DELAY = 0  # artificial delay


def closest_index(sorted_list: list[float], target: float) -> int:
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


def get_granule_positions(file_path):
    """
    Extracts the granule positions of all Ogg pages in the file.
    Returns a list of granule positions.
    """
    granule_positions = []
    with open(file_path, 'rb') as f:
        offset = 0
        while True:
            header = f.read(27)
            if len(header) < 27:
                break
            if not header.startswith(b"OggS"):
                break

            # Extract granule position (bytes 6–13)
            granule_pos_bytes = header[6:14]
            granule_pos = struct.unpack('<Q', granule_pos_bytes)[0]  # Little-endian unsigned 64-bit

            granule_positions.append(granule_pos)

            # Move to the next page
            page_segments = header[26]
            segment_table = f.read(page_segments)
            page_size = 27 + page_segments + sum(segment_table)
            offset += page_size
            f.seek(offset)

    return granule_positions


def get_sample_rate(file_path):
    """
    Uses PyOgg to extract the sample rate of the Ogg Vorbis file.
    """
    vorbis_file = pyogg.VorbisFile(file_path)
    return vorbis_file.frequency


def get_time_until_page(file_path, target_page_index):
    """
    Returns the total time (in seconds) from the start of the file
    up to the specified page (target_page_index).

    If target_page_index is 0, the output is 0 seconds.
    If target_page_index exceeds the total number of pages, returns total duration.
    """
    granule_positions = get_granule_positions(file_path)
    sample_rate = get_sample_rate(file_path)

    total_pages = len(granule_positions)

    if target_page_index <= 0:
        return 0.0  # No time passed before the first page

    if target_page_index >= total_pages:
        # If the target page exceeds the total pages, return the total duration
        total_samples = granule_positions[-1]
        total_time = total_samples / sample_rate
        return total_time

    # The granule position of the target page represents the total samples up to that page
    samples_up_to_page = granule_positions[target_page_index]
    time_up_to_page = samples_up_to_page / sample_rate

    return time_up_to_page


def build_page_index(file_path):
    """
    Returns a list of byte offsets for each OggS page in the file:
      page_offsets[i] = byte_offset_of_page_i
    """
    page_offsets = []
    with open(file_path, 'rb') as f:
        offset = 0
        while True:
            header = f.read(27)
            if len(header) < 27:
                break
            if not header.startswith(b"OggS"):
                break

            page_segments = header[26]
            segment_table = f.read(page_segments)
            if len(segment_table) < page_segments:
                break

            page_size = 27 + page_segments + sum(segment_table)

            page_offsets.append(offset)

            offset += page_size
            f.seek(offset, 0)

    return page_offsets


def build_time_index(file_path, total_pages):
    """
        TBA
    """
    granule_positions = get_granule_positions(file_path)
    sample_rate = get_sample_rate(file_path)

    total_pages = len(granule_positions)

    page_times = []
    for target_page_index in range(0, total_pages):
        if target_page_index <= 0:
            page_times.append(0.0)

        if target_page_index >= total_pages:
            total_samples = granule_positions[-1]
            total_time = total_samples / sample_rate
            page_times.append(total_time)

        samples_up_to_page = granule_positions[target_page_index]
        time_up_to_page = samples_up_to_page / sample_rate
        page_times.append(time_up_to_page)

    print(page_times)
    return page_times


def get_ogg_duration(file_path):
    """
    Returns the duration (in seconds) of an Ogg Vorbis file using PyOgg.
    """
    vorbis_file = pyogg.VorbisFile(file_path)
    data = vorbis_file.buffer
    sample_rate = vorbis_file.frequency
    channels = vorbis_file.channels

    total_bytes = len(data)
    bytes_per_sample = 2  # 16-bit
    samples_per_frame = channels
    num_frames = total_bytes // (bytes_per_sample * samples_per_frame)
    duration = num_frames / float(sample_rate)
    return duration


def extract_header_data_and_last_page(file_path):
    """
    Extract all Ogg pages at the start that contain the 3 Vorbis headers
    (packets 0x01, 0x03, 0x05).

    Returns (header_data, last_header_page_index)

    'header_data' is the raw concatenation of the Ogg pages for those headers.
    'last_header_page_index' is the highest page index that contains
    any part of the 3rd header packet, so we know where the real audio begins.

    We parse packets within each page:
      - If we see packet type 0x01 (ID), 0x03 (comment), or 0x05 (setup),
        we mark them found.
      - Once all 3 are found, the next packet is likely audio.
      - We note which Ogg page index we ended on.
    """
    needed = {0x01, 0x03, 0x05}
    found = set()

    header_data = bytearray()
    last_header_page_idx = 0

    page_index = 0
    with open(file_path, "rb") as f:
        buffer = bytearray()
        done = False
        while not done:
            chunk = f.read(CHUNK_SIZE)
            if not chunk:
                break
            buffer.extend(chunk)

            while True:
                if b"OggS" not in buffer:
                    break
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

                page = buffer[:page_size]
                buffer = buffer[page_size:]

                # Parse the packets in this page
                # to detect if they contain ID(0x01), Comment(0x03), or Setup(0x05).
                data_start = header_size
                data_end = page_size
                packet_data = bytearray()

                for seg_len in seg_table:
                    if data_start + seg_len > data_end:
                        break
                    packet_data.extend(page[data_start:(data_start + seg_len)])
                    data_start += seg_len

                    if seg_len < 255:
                        # packet boundary
                        if packet_data:
                            # check first byte
                            first_byte = packet_data[0]
                            if first_byte in needed:
                                found.add(first_byte)
                        packet_data = bytearray()

                # Append this entire page to header_data
                header_data.extend(page)
                # If we found at least one header packet here,
                # update last_header_page_idx
                if len(found) > 0:
                    last_header_page_idx = page_index

                # If we've found all 3, we can stop
                if found == needed:
                    done = True

                page_index += 1

    return bytes(header_data), last_header_page_idx


class OggServer:
    """
    A server that:
      - Receives "RQST <song_name>~<page_num>"
      - Builds the page index
      - Finds all Vorbis headers & identifies last_header_page
      - If page_num <= last_header_page: stream from offset=0 with NO re-injection
      - Else re-inject header_data, then jump to that page offset
    """

    def __init__(self, host='0.0.0.0', port=5000):
        self.host = host
        self.port = port
        self.stop_events = {}

    def start_server(self):
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
        stop_event = self.stop_events[conn]
        # 1) Read request

        cmd, data = protocol.get_msg(conn)
        if cmd != "RQST":
            print("Expected RQST, got:", cmd)
            conn.close()
            return

        parts = data.decode().split('~')
        if len(parts) != 2:
            print("Bad request format: must be 'song.ogg~page_num'")
            conn.sendall(protocol.create_msg("ERR ", b"Bad request"))
            conn.close()
            return

        song_name, t_str = parts
        asked_time = float(t_str)

        if not os.path.exists(song_name):
            print(f"File not found: {song_name}")
            conn.sendall(protocol.create_msg("PGNM", b"0"))
            conn.close()
            return

        # 2) Build page index
        page_offsets = build_page_index(song_name)
        total_pages = len(page_offsets)
        print(f"'{song_name}' => total_pages={total_pages}")

        # 3) Extract headers + find last_header_page
        header_data, last_header_page_idx = extract_header_data_and_last_page(song_name)
        print(f"Extracted header pages up to page {last_header_page_idx}")
        times = build_time_index(song_name, total_pages)

        # 4) Compute total duration
        duration = get_ogg_duration(song_name)
        sample_rate = get_sample_rate(song_name)
        page_num = closest_index(times, asked_time)
        current_time = get_time_until_page(song_name, page_num-1)

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
        else:
            # Re-inject header_data, then jump to page_num
            print(f"Page {page_num} > last_header_page_idx={last_header_page_idx}, re-injecting headers then offset.")
            # 7) Send the Vorbis headers
            conn.sendall(protocol.create_msg("PAGE", header_data))
            # 8) Then stream from page_offsets[page_num]
            offset = page_offsets[page_num]
            print(f"Streaming from offset={offset}, page={page_num}")
            self.stream_from_offset(conn, song_name, offset)

        stop_event.set()
        stop_thread.join()
        del self.stop_events[conn]
        conn.close()

    def stream_from_offset(self, conn, song_name, file_offset):
        """
        Streams Ogg pages from 'file_offset' to EOF in 8192 chunks,
        reassembling complete pages and sending them to the client.
        """

        with open(song_name, "rb") as f:
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
        conn.sendall(protocol.create_msg("SCNF", b""))
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
                    conn.close()
                    break
            except Exception as e:
                print(f"Error receiving STOP command: {e}")
                break


if __name__ == "__main__":
    server = OggServer(host="0.0.0.0", port=5000)
    server.start_server()
