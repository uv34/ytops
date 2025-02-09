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

        # For tracking page-based progress
        self.total_pages = 0
        self.current_pages = 0

        # For tracking playback time (in seconds)
        self.played_time = 0.0
        # If you get a real duration from the server, store it here:
        self.total_duration = 0.0  # placeholder (could be updated once known)

        # Callbacks for updating UI
        self._progress_callback = None   # (current_pages, total_pages)
        self._time_callback = None       # (played_time, total_duration)

    # ------------------------------
    # Callbacks so the UI can attach its own methods
    # ------------------------------
    def set_progress_callback(self, callback):
        """
        Let the UI set a function that receives (current_pages, total_pages).
        We'll call it whenever new pages arrive from the server.
        """
        self._progress_callback = callback

    def set_time_callback(self, callback):
        """
        Let the UI set a function that receives (played_time_in_s, total_duration_in_s).
        We'll call it whenever PCM data is actually played.
        """
        self._time_callback = callback

    # ------------------------------
    # Playback & Reading
    # ------------------------------
    def pcm_chunk_to_sound(self, pcm_chunk):
        """
        Convert raw PCM (16-bit, stereo, 44100Hz) bytes into a pygame Sound object.
        """
        samples = np.frombuffer(pcm_chunk, dtype=np.int16)
        # For stereo, reshape: 2 samples per frame
        samples = samples.reshape(-1, 2)
        return sndarray.make_sound(samples)

    def playback_thread_func(self):
        """
        Continuously pulls PCM from self.audio_queue, converts to Sound, and plays it.
        Updates played_time after each chunk. Exits once done_flag is set + queue is empty.
        """
        pygame.mixer.init(frequency=44100, size=-16, channels=2)
        self.playing = True
        self.played_time = 0.0

        bytes_per_frame = 4.0  # (16-bit stereo = 2 bytes * 2 channels)

        while True:
            # If we've reached the end of the PCM stream (and queue is empty), we're done
            if self.done_flag.is_set() and self.audio_queue.empty():
                break

            if not self.playing:
                # "Paused": just idle briefly
                pygame.time.Clock().tick(100)
                continue

            try:
                chunk = self.audio_queue.get(timeout=0.1)
            except queue.Empty:
                continue

            # Convert chunk to a Sound
            sound = self.pcm_chunk_to_sound(chunk)
            sound_length_frames = len(chunk) / bytes_per_frame  # total frames in this chunk
            sound_length_seconds = sound_length_frames / 44100.0

            # Play the Sound
            sound.play()

            # Wait for playback of this chunk
            while pygame.mixer.get_busy() and self.playing:
                pygame.time.Clock().tick(200)

            # The chunk has finished playing, so add to total "played_time"
            self.played_time += sound_length_seconds

            # Notify UI of updated playback time
            if self._time_callback:
                self._time_callback(self.played_time, self.total_duration)

        pygame.mixer.quit()

    def reader_thread_func(self):
        """
        Read raw PCM from ffmpeg's stdout and fill self.audio_queue.
        """
        while True:
            chunk = self.ffmpeg_process.stdout.read(self.chunk_size)
            if not chunk:
                break
            self.audio_queue.put(chunk)

        self.done_flag.set()

    # ------------------------------
    # Main streaming method
    # ------------------------------
    def receive_stream(self, client_socket):
        """
        Connect to the server, read total pages from PGNM message,
        start ffmpeg, spin up threads, and read OGG data from server.
        """
        # Expecting (cmd="PGNM", data=b"<page_count>")
        cmd, data = protocol.get_msg(client_socket)
        pages, length = data.decode().split('~')
        if cmd != "PGNM":
            print("receive_stream: Unexpected response from server.")
            return
        if pages == "0":
            print("receive_stream: Server does not have the requested song.")
            return

        # Parse total number of OGG pages
        self.total_pages = int(pages)
        self.total_duration = float(length)
        self.current_pages = 0
        print(f"receive_stream: The server says total OGG pages = {self.total_pages}")

        # If you had a total duration from server, you'd parse it here:
        # e.g., if data was "<page_count>|<duration>", you'd split:
        # pages_str, duration_str = data.decode().split('|')
        # self.total_pages = int(pages_str)
        # self.total_duration = float(duration_str)

        # Update UI about initial "download" progress
        if self._progress_callback:
            self._progress_callback(self.current_pages, self.total_pages)

        # Prepare ffmpeg
        ffmpeg_command = [
            'ffmpeg',
            '-loglevel', 'error',
            '-i', 'pipe:0',
            '-f', 's16le',
            '-acodec', 'pcm_s16le',
            '-ac', '2',
            '-ar', '44100',
            'pipe:1'
        ]

        self.ffmpeg_process = subprocess.Popen(
            ffmpeg_command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE
        )

        self.audio_queue = queue.Queue()
        self.done_flag = threading.Event()

        # Threads for reading PCM from ffmpeg, and playing it
        reader_thread = threading.Thread(target=self.reader_thread_func, daemon=True)
        reader_thread.start()

        player_thread = threading.Thread(target=self.playback_thread_func, daemon=True)
        player_thread.start()

        # Receive raw OGG data from the server, count pages, pass to ffmpeg
        while True:
            data = client_socket.recv(self.chunk_size)
            if not data:
                # End of stream
                break

            # Count how many "OggS" markers are in this chunk
            page_count = data.count(b'OggS')
            self.current_pages += page_count

            if self._progress_callback:
                self._progress_callback(self.current_pages, self.total_pages)

            # Send OGG data to ffmpeg
            try:
                self.ffmpeg_process.stdin.write(data)
                self.ffmpeg_process.stdin.flush()
            except BrokenPipeError:
                break

        # Tell ffmpeg we're done sending
        self.ffmpeg_process.stdin.close()
        self.ffmpeg_process.wait()

        # Wait for threads to finish
        reader_thread.join()
        player_thread.join()

    # ------------------------------
    # Socket connection
    # ------------------------------
    def ask_for_song(self, song_name):
        """
        Creates a socket, connects to the server, and sends the requested song name.
        """
        client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client_socket.connect((self.host, self.port))
        client_socket.sendall(song_name.encode())
        return client_socket

    # ------------------------------
    # Controls
    # ------------------------------
    def pause(self):
        """Toggle pause/resume."""
        self.playing = not self.playing
