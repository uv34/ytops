import socket
import subprocess
import threading
import queue
import pygame
import numpy as np
from pygame import sndarray
import protocol

class AudioClient:
    """
    A client that connects to a remote OGG streaming server, decodes the incoming
    audio using ffmpeg (into raw 16-bit PCM), and plays it in near real-time via pygame.
    """

    def __init__(self, host='127.0.0.1', port=5000, chunk_size=8192):
        """
        Initialize the audio client with server host/port and chunk size.
        """
        self.host = host
        self.port = port
        self.chunk_size = chunk_size

        # These will be initialized when streaming begins
        self.audio_queue = None
        self.done_flag = None
        self.ffmpeg_process = None
        self.playing = False

    def pcm_chunk_to_sound(self, pcm_chunk):
        """
        Convert raw PCM (16-bit, stereo, 44100Hz) bytes into a pygame Sound object with stereo.
        """
        print("pcm_chunk_to_sound: Converting PCM chunk to pygame Sound...")
        samples = np.frombuffer(pcm_chunk, dtype=np.int16)
        print(f"pcm_chunk_to_sound: Chunk size = {len(pcm_chunk)} bytes, sample count = {len(samples)}")
        # Reshape for 2-channel (stereo) audio
        samples = samples.reshape(-1, 2)
        return sndarray.make_sound(samples)

    def playback_thread_func(self):
        """
        Continuously pulls PCM chunks from self.audio_queue, converts them to pygame Sound,
        and plays them. Stops once 'self.done_flag' is set and the queue is empty.
        """
        print("playback_thread_func: Initializing pygame mixer...")
        pygame.mixer.init(frequency=44100, size=-16, channels=2)
        print("playback_thread_func: Mixer initialized.")
        self.playing = True

        while True:
            if self.done_flag.is_set() and self.audio_queue.empty():
                print("playback_thread_func: No more data and done_flag set, exiting.")
                break
            if not self.playing:
                pygame.time.Clock().tick(100)
                continue
            try:
                chunk = self.audio_queue.get(timeout=0.1)
                print(f"playback_thread_func: Retrieved chunk of size {len(chunk)} from queue.")
            except queue.Empty:
                continue

            sound = self.pcm_chunk_to_sound(chunk)
            print("playback_thread_func: Playing sound...")
            sound.play()

            # Wait until playback of this chunk finishes before playing the next
            while pygame.mixer.get_busy():
                pygame.time.Clock().tick(200)
            print("playback_thread_func: Finished playing sound chunk.")

    def reader_thread_func(self):
        """
        Reads raw PCM data from ffmpeg's stdout and puts chunks into self.audio_queue.
        Sets the done_flag when ffmpeg signals no more data.
        """
        print("reader_thread_func: Starting to read from ffmpeg stdout...")
        while True:
            chunk = self.ffmpeg_process.stdout.read(self.chunk_size)
            if not chunk:
                print("reader_thread_func: No more data from ffmpeg, stopping.")
                break
            self.audio_queue.put(chunk)
            print(f"reader_thread_func: Put chunk of size {len(chunk)} in queue.")

        # Signal playback thread to finish once the queue is empty
        self.done_flag.set()
        print("reader_thread_func: Done flag set.")

    def receive_stream(self, client_socket):
        """
        Connects to the OGG streaming server, uses ffmpeg to decode to raw PCM,
        and streams it through pygame in near-real-time.
        """
        cmd, data = protocol.get_msg(client_socket)
        if cmd != "PGNM":
            print(cmd)
            print("receive_stream: Unexpected response from server.")
            return
        if data == b"0":
            print("receive_stream: Server does not have the requested song.")
            return
        print(f"receive_stream: Server is ready to stream song {data.decode()}")

        ffmpeg_command = [
            'ffmpeg',
            '-loglevel', 'error',
            '-i', 'pipe:0',
            '-f', 's16le',       # Raw 16-bit PCM
            '-acodec', 'pcm_s16le',
            '-ac', '2',          # 2 channels
            '-ar', '44100',      # 44.1 kHz
            'pipe:1'
        ]
        print(f"receive_stream: FFMPEG command is {ffmpeg_command}")

        # Start ffmpeg process
        self.ffmpeg_process = subprocess.Popen(
            ffmpeg_command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE
        )
        print("receive_stream: ffmpeg process started.")

        # Create a queue and a flag to handle streaming
        self.audio_queue = queue.Queue()
        self.done_flag = threading.Event()

        # Start reader and playback threads
        reader_thread = threading.Thread(target=self.reader_thread_func, daemon=True)
        reader_thread.start()
        print("receive_stream: Reader thread started.")

        player_thread = threading.Thread(target=self.playback_thread_func, daemon=True)
        player_thread.start()
        print("receive_stream: Playback thread started.")

        # begin receiving data
        while True:
            data = client_socket.recv(self.chunk_size)
            if not data:
                print("receive_stream: No more data from server, ending stream.")
                break

            # Feed data into ffmpeg's stdin
            try:
                self.ffmpeg_process.stdin.write(data)
                self.ffmpeg_process.stdin.flush()
                print(f"receive_stream: Wrote {len(data)} bytes to ffmpeg stdin.")
            except BrokenPipeError:
                print("receive_stream: BrokenPipeError writing to ffmpeg, stopping.")
                break

        # Close ffmpeg stdin to signal end of stream
        print("receive_stream: Closing ffmpeg stdin...")
        self.ffmpeg_process.stdin.close()

        # Wait for ffmpeg process to exit
        print("receive_stream: Waiting for ffmpeg process to exit...")
        self.ffmpeg_process.wait()
        print("receive_stream: ffmpeg process exited.")

        # Wait for reading thread to end
        print("receive_stream: Waiting for reader_thread to join...")
        reader_thread.join()
        print("receive_stream: reader_thread joined.")

        # Wait for playback thread to finish playing all data
        print("receive_stream: Waiting for player_thread to join...")
        player_thread.join()
        print("receive_stream: player_thread joined.")

        print("Audio stream ended.")

    def ask_for_song(self, song_name):
        """
        Creates a socket, connects to the server, and sends the song name.
        """
        client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client_socket.connect((self.host, self.port))
        client_socket.sendall(song_name.encode())
        return client_socket

    def pause(self):
        """
        Signal that the client should stop streaming.
        """
        if self.playing:
            self.playing = False
        else:
            self.playing = True


if __name__ == '__main__':
    client_ = AudioClient(host='127.0.0.1', port=5000, chunk_size=8192)
    sock = client_.ask_for_song('example.ogg')
    client_.receive_stream(sock)
