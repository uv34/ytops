# audio_client_seek.py

import socket
import subprocess
import threading
import queue
import time

import pygame
import numpy as np
from pygame import sndarray
import protocol


class AudioClient:
    """
    A client that requests "song_name~page_num" from server,
    then decodes Ogg data from that page onward using ffmpeg + pygame.
    """

    def __init__(self, host='127.0.0.1', port=5000, chunk_size=8192):
        self.host = host
        self.port = port
        self.chunk_size = chunk_size
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        self.audio_queue = None
        self.done_flag = None
        self.ffmpeg_process = None
        self.playing = False
        self.running = False

        self.total_pages = 0
        self.current_pages = 0
        self.played_time = 0.0
        self.total_duration = 0.0
        self.sample_rate = 44100

        # callbacks
        self._progress_callback = None  # (current_pages, total_pages)
        self._time_callback = None      # (played_time, total_duration)

    # -------------
    # Callback setup
    # -------------
    def set_progress_callback(self, cb):
        self._progress_callback = cb

    def set_time_callback(self, cb):
        self._time_callback = cb

    # -------------
    # Main request
    # -------------
    def ask_for_song(self, song_name, t=0.0):
        """
        Opens a socket, sends "RQST" with data = "song_name~page_num".
        Returns the connected socket if server is ready, or None if error.
        """
        self.sock.connect((self.host, self.port))
        req_str = f"{song_name}~{t}"
        t = t - 2 if t >= 3 else 0.0
        msg = protocol.create_msg("RQST", req_str.encode())
        self.sock.sendall(msg)

    # -------------
    # Decoding & Playback
    # -------------
    def receive_stream(self):
        """
        Reads either "ERR" or "PGNM" from server.
        If "PGNM", parse pages, duration, then start ffmpeg + streaming loop.
        """
        cmd, data = protocol.get_msg(self.sock)
        if not cmd:
            print("No command from server. Possibly disconnected.")
            return

        if cmd == "ERR ":
            # server says error
            print("Error from server:", data.decode())
            return

        if cmd != "PGNM":
            print(f"Unexpected cmd={cmd}, data={data}")
            return

        # parse e.g. "179~180.5~20~44100"
        pages_str, dur_str, cur_str, slr_str, pgn_str = data.decode().split('~')
        self.total_pages = int(pages_str)
        self.total_duration = float(dur_str)
        self.played_time = float(cur_str)
        self.sample_rate = int(slr_str)
        self.current_pages = int(pgn_str)
        print(f"Server responded with {data}")

        # initialize ffmpeg
        ffmpeg_cmd = [
            "ffmpeg",
            "-loglevel", "error",
            "-i", "pipe:0",
            "-f", "s16le",
            "-acodec", "pcm_s16le",
            "-ac", "2",
            "-ar", slr_str,
            "pipe:1"
        ]
        self.ffmpeg_process = subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE)

        self.audio_queue = queue.Queue()
        self.done_flag = threading.Event()

        # spawn threads
        reader_t = threading.Thread(target=self.reader_thread_func, daemon=True)
        reader_t.start()

        player_t = threading.Thread(target=self.playback_thread_func, daemon=True)
        player_t.start()

        # read Ogg data from server -> ffmpeg
        self.stream_loop(self.sock)

        # shutdown
        self.ffmpeg_process.stdin.close()
        self.ffmpeg_process.wait()
        reader_t.join()
        player_t.join()

    def stream_loop(self, client_socket):
        """
        Continuously recv Ogg data, count pages, feed ffmpeg.
        """
        self.playing = True
        self.running = True
        while self.running:
            chunk = client_socket.recv(self.chunk_size)
            if not chunk:
                break
            page_count = chunk.count(b"OggS")
            self.current_pages += page_count
            if self._progress_callback:
                self._progress_callback(self.current_pages, self.total_pages)

            try:
                self.ffmpeg_process.stdin.write(chunk)
                self.ffmpeg_process.stdin.flush()
            except BrokenPipeError:
                print('pipe error')
                break

    def reader_thread_func(self):  # TODO - fix - done_flag never sets
        """
        Reads raw PCM from ffmpeg stdout => audio_queue
        """
        self.running = True
        while self.running:
            pcm = self.ffmpeg_process.stdout.read(self.chunk_size)
            if not pcm:
                break
            self.audio_queue.put(pcm)
        print('reader thread done')
        self.done_flag.set()

    def playback_thread_func(self):
        """
        Converts PCM to PyGame Sounds and plays them, tracking time.
        """
        pygame.mixer.init(frequency=self.sample_rate, size=-16, channels=2)
        bytes_per_frame = 4.0  # 16-bit * 2 channels

        while True:
            if self.done_flag.is_set() and self.audio_queue.empty():
                break

            if not self.playing:
                pygame.time.Clock().tick(50)
                continue

            try:
                chunk = self.audio_queue.get(timeout=0.1)
            except queue.Empty:
                continue

            sound = self.pcm_chunk_to_sound(chunk)
            n_frames = len(chunk) / bytes_per_frame
            duration_s = n_frames / self.sample_rate

            sound.play()

            while pygame.mixer.get_busy() and self.playing:
                pygame.time.Clock().tick(200)

            self.played_time += duration_s
            if self._time_callback:
                self._time_callback(self.played_time, self.total_duration)

        self.stop()
        print('stopped playback')
        pygame.mixer.quit()

    def pcm_chunk_to_sound(self, pcm_chunk):
        samples = np.frombuffer(pcm_chunk, dtype=np.int16)
        samples = samples.reshape(-1, 2)
        return sndarray.make_sound(samples)

    # -------------
    # Controls
    # -------------
    def pause(self):
        self.playing = not self.playing

    def stop(self):
        """
        Stops playback, closes connections, and terminates the ffmpeg process.
        """
        if not self.running:
            return  # Already stopped

        print("Stopping audio stream...")

        self.running = False  # Stop streaming
        self.playing = False  # Stop playback

        # Signal the playback and reader threads to stop
        if self.done_flag:
            self.done_flag.set()

        # Close the network socket
        if self.sock:
            self.sock.sendall(protocol.create_msg("STOP", b"1"))
            try:
                time.sleep(0.1)  # wait for server to close connection
                self.sock.close()
            except Exception as e:
                print(f"Error closing socket: {e}")

        # Close the ffmpeg process safely
        if self.ffmpeg_process:
            try:
                self.ffmpeg_process.stdin.close()
                self.ffmpeg_process.terminate()
                self.ffmpeg_process.wait()
            except Exception as e:
                print(f"Error terminating ffmpeg: {e}")

        # Clear the audio queue to release resources
        if self.audio_queue:
            with self.audio_queue.mutex:
                self.audio_queue.queue.clear()

        print("Audio streaming stopped.")
