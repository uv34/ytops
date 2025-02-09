import socket
import time
import threading
import os
import protocol
import pyogg


def get_ogg_duration(file_path: str) -> float:
    """
    Returns the duration (in seconds) of an Ogg Vorbis file
    using PyOgg, without relying on .length().
    """
    vorbis_file = pyogg.VorbisFile(file_path)
    data = vorbis_file.buffer
    sample_rate = vorbis_file.frequency
    num_channels = vorbis_file.channels

    # Total bytes of decoded PCM
    total_bytes = len(data)

    # Each sample is 2 bytes (16-bit)
    bytes_per_sample = 2

    # For stereo, each 'frame' has (channels) samples
    # e.g. stereo => 2 samples per frame.

    # Number of total frames in the audio
    num_frames = total_bytes // (bytes_per_sample * num_channels)

    # Duration = frames / sample_rate
    duration_seconds = num_frames / float(sample_rate)

    return duration_seconds
class OggServer:
    """
    A simple server that streams OGG pages from a local file to a connected client.
    It reads the file in chunks, processes complete OGG pages, and sends them out
    with an optional delay to simulate network latency.
    """

    def __init__(self, host='0.0.0.0', port=5000, chunk_size=8192, delay=0):
        """
        Initialize the OggServer with file, network, and streaming parameters.

        :param host: Host/IP address on which the server will bind.
        :param port: Port on which the server will listen for incoming connections.
        :param chunk_size: The number of bytes to read from the file at a time.
        :param delay: Delay (in seconds) to wait after sending each OGG page (simulates slow streaming).
        """
        self.host = host
        self.port = port
        self.chunk_size = chunk_size
        self.delay = delay
        self.sock = None
        self.threads = []

    def start_server(self):
        """
        Start listening for a single client connection and then stream the OGG file
        in complete pages to the client.
        """
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind((self.host, self.port))
        sock.listen()
        print(f"Server listening on {self.host}:{self.port}...")
        while True:
            conn, addr = sock.accept()
            print(f"Connection from {addr}")

            handle_client_thread = threading.Thread(target=self.handle_client, args=(conn,))
            handle_client_thread.start()
            self.threads.append(handle_client_thread)

    def handle_client(self, conn):
        song_name = conn.recv(1024).decode()
        print(f"Client requested song: {song_name}")
        if not os.path.exists(song_name):
            print("File not found. cant stream")
            conn.sendall(protocol.create_msg("PGNM", b"0"))
            conn.close()
            return

        print("File found. Streaming...")

        with open(song_name, 'rb') as f:
            buffer = bytearray()
            content = f.read()
            print('page num: ', )
            msg = protocol.create_msg("PGNM", f"{str(content.count(b'OggS'))}~{str(get_ogg_duration(song_name))}"
                                              f"".encode())
            conn.sendall(msg)
            print('...', msg)

            f.seek(0)

            while chunk := f.read(self.chunk_size):
                # Accumulate data in the buffer
                buffer.extend(chunk)

                # Look for complete OGG pages and send them
                while b"OggS" in buffer:
                    index = buffer.index(b"OggS")
                    if index > 0:
                        # Discard any junk before "OggS"
                        buffer = buffer[index:]

                    # OGG header is at least 27 bytes (for capture pattern and header fields)
                    if len(buffer) < 27:
                        break  # Wait for more data to get a full header

                    page_segments = buffer[26]  # Number of segments in this OGG page
                    expected_header_size = 27 + page_segments  # 27-byte header + segment table

                    if len(buffer) < expected_header_size:
                        break  # Not enough data for the full header + segment table

                    segment_table = buffer[27:expected_header_size]
                    page_size = 27 + len(segment_table) + sum(segment_table)
                    if len(buffer) < page_size:
                        break  # Wait for the complete page

                    # We have a full OGG page. Send it to the client.
                    page = buffer[:page_size]
                    conn.sendall(page)
                    # Remove the data that was just sent
                    buffer = buffer[page_size:]

                    # Simulate streaming delay (if desired)
                    time.sleep(self.delay)

        print("File transmission completed.")
        conn.close()


if __name__ == "__main__":
    # Example usage: create an OggServer and start it.
    server = OggServer(host='0.0.0.0', port=5000, chunk_size=8192, delay=0)
    server.start_server()
