import base64  # Used for encoding/decoding data in base64 format
import multiprocessing  # Enables parallel execution for audio playback
import pickle  # Serializes/deserializes Python objects (e.g., timestamps)
import queue  # Manages queues, especially for multiprocessing
import socket  # Handles network communication with the server
import ssl  # Provides SSL/TLS encryption for secure connections
import subprocess  # Runs external processes like ffmpeg for audio decoding
import threading  # Manages concurrent threads for reading audio data

import numpy as np  # Processes numerical data, particularly audio samples
import pygame  # Handles audio playback
from pygame import sndarray  # Converts numpy arrays to playable sound objects

import protocol  # Custom module defining the communication protocol
from encryption import CryptoManager  # Custom module for encryption key management


def playback_process_func(audio_queue, done_flag, playing, volume, sample_rate, played_time, time_update_queue,
                          total_duration, seek_flag, pause_enqueuing):
    """
    Runs in a separate process to handle audio playback using pygame.

    Dequeues audio chunks from audio_queue, converts them to sound objects,
    and plays them while respecting pause, seek, and stop signals.

    :param audio_queue: Queue of audio chunks (index, duration, PCM data).
    :param done_flag: Event signaling when streaming is complete.
    :param playing: Shared boolean indicating playback state.
    :param volume: Shared float for volume level (0.0 to 1.0).
    :param sample_rate: Audio sample rate (e.g., 44100 Hz).
    :param played_time: Shared float tracking current playback position.
    :param time_update_queue: Queue to send time updates to the main process.
    :param total_duration: Total length of the song in seconds.
    :param seek_flag: Event signaling a seek operation.
    :param pause_enqueuing: Event to pause adding new audio chunks.
    """
    def pcm_chunk_to_sound(pcm):
        """
        Convert raw PCM audio data to a pygame sound object.

        :param pcm: Bytes of PCM audio data.
        :return: Pygame sound object ready for playback.
        """
        samples = np.frombuffer(pcm, dtype=np.int16).copy()
        samples = samples.reshape(-1, 2)  # Stereo: 2 channels
        return sndarray.make_sound(samples)

    # Initialize pygame mixer with specified audio parameters
    pygame.mixer.init(frequency=sample_rate, size=-16, channels=2)
    while True:
        # Exit if streaming is done and queue is empty
        if done_flag.is_set() and audio_queue.empty() and not pause_enqueuing.is_set():
            print('playback process done 1', done_flag.is_set(), audio_queue.empty(), pause_enqueuing.is_set())
            break
        if not playing.value:  # Pause playback if not playing
            pygame.time.Clock().tick(50)  # Brief wait to reduce CPU usage
            continue
        try:
            # Fetch next audio chunk with a timeout
            item = audio_queue.get(timeout=0.1)
            i, duration_s, pcm = item  # Unpack: index, duration, PCM data
        except queue.Empty:
            continue
        sound = pcm_chunk_to_sound(pcm)
        sound.set_volume(volume.value)  # Apply current volume
        sound.play()
        # Monitor playback and handle seek interruptions
        while pygame.mixer.get_busy():
            if seek_flag.is_set():  # Stop sound if seeking
                pygame.mixer.stop()
                break
            pygame.time.Clock().tick(200)  # Check 5 times per second
        # Update played time and notify main process
        with played_time.get_lock():
            played_time.value += duration_s
            time_update_queue.put(("update_time", played_time.value, total_duration))

    print('playback process done')
    pygame.mixer.quit()  # Clean up pygame resources

class AudioClient:
    """
    A client for streaming and playing audio from a server.

    Connects to a server, requests songs, receives encrypted audio streams,
    decodes them with ffmpeg, and plays them with pygame. Supports playback
    controls like pause, seek, and stop.

    Attributes:
        host (str): Server hostname or IP.
        port (int): Server port number.
        chunk_size (int): Size of audio data chunks.
        sock (socket): Network socket for server communication.
        token (str): Authentication token (JWT).
        volume (multiprocessing.Value): Shared volume level.
        song_id (str): Current song identifier.
        song_name (str): Song title.
        author (str): Song artist.
        album (str): Song album.
        cover (bytes): Album cover image data.
        audio_queue (multiprocessing.Queue): Queue for playback audio chunks.
        time_update_queue (multiprocessing.Queue): Queue for time updates.
        done_flag (multiprocessing.Event): Signals end of streaming.
        seek_flag (multiprocessing.Event): Signals a seek operation.
        ffmpeg_process (subprocess.Popen): ffmpeg process for decoding.
        playing (multiprocessing.Value): Playback state (True = playing).
        running (bool): Client operational state.
        in_song (bool): Indicates if a song is being played.
        cache (dict): Stores audio chunks for seeking.
        total_pages (int): Total OGG pages in the song.
        current_pages (int): Number of pages received.
        played_time (multiprocessing.Value): Current playback position.
        total_duration (float): Song length in seconds.
        sample_rate (int): Audio sample rate.
        times (list): Timestamps of audio chunks.
        _progress_callback (callable): Callback for progress updates.
        _time_callback (callable): Callback for time updates.
        _queue_checker_running (bool): State of time update checker.
        _queue_checker_timer (threading.Timer): Timer for checking updates.
        queue_lock (threading.Lock): Synchronizes queue access.
        pause_enqueuing (multiprocessing.Event): Pauses audio enqueuing.
    """

    def __init__(self, host='127.0.0.1', port=5000, chunk_size=8192):
        """
        Initialize the audio client with connection and streaming settings.

        :param host: Server address (default: '127.0.0.1').
        :param port: Server port (default: 5000).
        :param chunk_size: Bytes per audio chunk (default: 8192).
        """
        self.host = host
        self.port = port
        self.chunk_size = chunk_size
        self.sock = None
        self.token = '###'  # Placeholder token
        self.volume = multiprocessing.Value('d', 1.0)  # Default volume: 100%
        self.song_id = None
        self.song_name = ''
        self.author = ''
        self.album = ''
        self.cover = b''
        self.audio_queue = multiprocessing.Queue()
        self.time_update_queue = multiprocessing.Queue()
        self.done_flag = multiprocessing.Event()
        self.seek_flag = multiprocessing.Event()
        self.ffmpeg_process = None
        self.playing = multiprocessing.Value('b', True)
        self.running = False
        self.in_song = False
        self.cache = {}
        self.total_pages = 0
        self.current_pages = 0
        self.played_time = multiprocessing.Value('d', 0.0)
        self.total_duration = 0.0
        self.sample_rate = 44100  # Default sample rate
        self.times = []
        self._progress_callback = None
        self._time_callback = None
        self._queue_checker_running = False
        self._queue_checker_timer = None
        self.queue_lock = threading.Lock()
        self.pause_enqueuing = multiprocessing.Event()

    def set_progress_callback(self, cb):
        """Set callback for progress updates (e.g., pages received)."""
        self._progress_callback = cb

    def set_time_callback(self, cb):
        """Set callback for time updates (e.g., current position)."""
        self._time_callback = cb

    def set_volume(self, volume):
        """Adjust playback volume (0.0 to 1.0)."""
        with self.volume.get_lock():
            self.volume.value = volume

    def ask_for_song(self, song_id: str, t: float, token: str):
        """
        Request a song from the server starting at a specific time.

        Establishes an encrypted connection, exchanges keys, and sends the request.

        :param song_id: Unique identifier of the song.
        :param t: Start time in seconds.
        :param token: JWT token for authentication.
        """
        client_ctx = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect((self.host, self.port))
        self.sock = client_ctx.wrap_socket(self.sock, server_hostname=self.host)
        print('connected')
        req_str = f"{token}~{song_id}~{t}"
        self.song_id = song_id
        self.token = token
        cryp = CryptoManager()
        # Send public key to server
        key_msg = protocol.create_msg("SHKY", base64.b64encode(str(cryp.public_key).encode()))
        cmd, data = protocol.get_msg(self.sock)
        print('cmd', cmd)
        if cmd != 'SHKY':  # Expecting server's public key
            print('unexpected response, trying again')
            self.ask_for_song(song_id, t, token)
            return
        pub_a = int(base64.b64decode(data).decode())
        self.sock.send(key_msg)
        # Generate shared encryption key
        shared_key = cryp.shared_secret(pub_a)
        self.key = cryp.hash_secret(shared_key)
        print(shared_key, '_' * 100)
        print(f'{self.sock} is asking for {song_id} in {t}')
        msg = protocol.create_msg("RQST", req_str.encode())
        self.sock.sendall(msg)
        print('sent request')

    def receive_metadata(self, data):
        """
        Parse song metadata from the server.

        Extracts song details, duration, sample rate, and cover image.

        :param data: Raw metadata bytes from the server.
        """
        splited = data.split(b'|')
        metadata = splited[0]
        times_str = b'|'.join(splited[1:-1])  # Timestamps
        cover_b64 = splited[-1]  # Base64-encoded cover image
        name_str, auth_str, album_str, pages_str, dur_str, cur_str, slr_str, pgn_str = metadata.split(b'~')
        self.total_pages = int(pages_str.decode())
        self.total_duration = float(dur_str.decode())
        with self.played_time.get_lock():
            self.played_time.value = float(cur_str.decode())
        self.sample_rate = int(slr_str.decode())
        self.current_pages = int(pgn_str.decode())
        self.song_name = name_str.decode()
        self.album = album_str.decode()
        self.author = auth_str.decode()
        self.cover = base64.b64decode(cover_b64)
        self.times = pickle.loads(times_str)

    def _start_ffmpeg(self):
        ffmpeg_cmd = [
            "ffmpeg", "-loglevel", "error", "-i", "pipe:0",
            "-f", "s16le", "-acodec", "pcm_s16le", "-ac", "2",
            "-ar", str(self.sample_rate), "pipe:1"
        ]
        print('ffmpeg command:', ffmpeg_cmd)
        self.ffmpeg_process = subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE)

    def _start_everything(self):
        self.reader_t = threading.Thread(target=self.reader_thread_func, daemon=True)
        self.reader_t.start()
        # Start process to play audio
        self.playback_p = multiprocessing.Process(
            target=playback_process_func,
            args=(self.audio_queue, self.done_flag, self.playing, self.volume, self.sample_rate,
                  self.played_time, self.time_update_queue, self.total_duration, self.seek_flag,
                  self.pause_enqueuing),
            daemon=True
        )
        self.playback_p.start()
        self._start_queue_checker()  # Monitor time updates
        self.stream_loop(self.sock)  # Receive audio data

    def _wait_to_finish(self):
        self.ffmpeg_process.stdin.close()
        print('stdin closed')
        self.ffmpeg_process.terminate()
        self.ffmpeg_process.wait()
        print('ffmpeg process done')
        self.reader_t.join()
        print('out from loops')
        if self.in_song:
            self.playback_p.join()

    def _on_stop(self):
        self._stop_queue_checker()
        # Check if song is complete
        with self.played_time.get_lock():
            if self.played_time.value >= self.total_duration - 0.5:
                self.in_song = False
        if not self.in_song:
            self.real_stop()
        else:  # Resume from current position
            print('asking from', self.played_time.value)
            self.ask_for_song(self.song_id, self.played_time.value, self.token)
            self.receive_stream()
        print('back to normal', self.running, self.playing.value)

    def receive_stream(self):
        """
        Receive and process the audio stream from the server.

        Sets up ffmpeg, starts playback process and reader thread,
        and manages the streaming loop until complete or interrupted.
        """
        cmd, data = protocol.get_msg(self.sock, self.key)
        print('cmd', cmd)
        if cmd == "ERR ":
            print("Error from server:", data.decode())
            return
        if cmd != "PGNM":  # Expecting metadata
            print(f"Unexpected cmd={cmd}, data={data}")
            return
        self.receive_metadata(data)
        print(f"Server responded with {data}")
        # Configure ffmpeg to decode OGG stream to PCM
        self._start_ffmpeg()

        self.audio_queue = multiprocessing.Queue()
        self.time_update_queue = multiprocessing.Queue()
        self.done_flag.clear()
        self.seek_flag.clear()
        self.pause_enqueuing.clear()
        # Start thread to read decoded audio from ffmpeg
        self._start_everything()
        print('stream loop done')
        # Clean up resources
        self._wait_to_finish()
        print('playback process done')
        self._on_stop()


    def stream_loop(self, client_socket):
        """
        Receive audio chunks from the server and feed them to ffmpeg.

        Updates progress and handles stream termination signals.

        :param client_socket: Socket connected to the server.
        """
        with self.playing.get_lock():
            self.playing.value = True
        self.running = True
        self.in_song = True
        while True:
            cmd, chunk = protocol.get_msg(client_socket, self.key)
            if cmd == "SCNF":  # Server confirms stop
                print("Server confirmed stop")
                self.done_flag.set()
                print('done flag set')
                break
            if not chunk:  # End of stream
                break
            page_count = chunk.count(b"OggS")  # Count OGG pages
            self.current_pages += page_count
            if self._progress_callback:
                self._progress_callback(self.current_pages, self.total_duration)
            try:
                if self.ffmpeg_process and self.ffmpeg_process.stdin and self.running:
                    self.ffmpeg_process.stdin.write(chunk)
                    self.ffmpeg_process.stdin.flush()
            except BrokenPipeError:
                print('pipe error')
                break
        print('exited stream loop')

    def reader_thread_func(self):
        """
        Read decoded PCM audio from ffmpeg and enqueue it for playback.

        Caches audio chunks and calculates their durations.
        """
        bytes_per_frame = 4  # 2 channels * 2 bytes/sample
        virtual_time = self.played_time.value
        self.running = True
        c = 0
        to_add = queue.Queue()  # Buffer for PCM data
        while self.running:
            if self.done_flag.is_set():
                break
            pcm = self.ffmpeg_process.stdout.read(self.chunk_size)
            if not pcm:
                break
            to_add.put(pcm)
            if self.pause_enqueuing.is_set():  # Wait if paused
                pygame.time.Clock().tick(50)
                continue
            while not to_add.empty():
                pcm = to_add.get()
                n_frames = len(pcm) / bytes_per_frame
                duration_s = n_frames / self.sample_rate
                self.cache[(c, virtual_time, duration_s)] = (duration_s, pcm)
                with self.queue_lock:  # Thread-safe queue access
                    if not self.pause_enqueuing.is_set():
                        self.audio_queue.put((c, duration_s, pcm))
            c += 1
            virtual_time += duration_s
        print('reader thread done')
        self.running = False

    def pause(self):
        """Toggle playback between paused and playing states."""
        with self.playing.get_lock():
            self.playing.value = not self.playing.value

    def seek(self, seeked):
        """
        Seek to a specific time in the song.

        Uses cached audio if possible; otherwise, requests from the server.

        :param seeked: Target time in seconds.
        """
        if self._is_seek_in_progress():
            return

        self._initiate_seek(seeked)

        if self._can_seek_from_cache(seeked):
            self._seek_from_cache(seeked)
        else:
            self._seek_from_server(seeked)

        self._complete_seek()

    def _is_seek_in_progress(self):
        """Check if a seek operation is already in progress."""
        if self.seek_flag.is_set():
            print("Seek already in progress, ignoring new seek request.")
            return True
        return False

    def _initiate_seek(self, seeked):
        """Initialize the seek operation."""
        self.seek_flag.set()
        print(f"\n=== SEEK called: target={seeked} ===")

    def _can_seek_from_cache(self, seeked):
        """Check if the seeked time is within cached audio range."""
        cache_times = [key[1] for key in self.cache.keys()]
        return cache_times and min(cache_times) <= seeked <= max(cache_times)

    def _seek_from_cache(self, seeked):
        """Handle seeking using cached audio."""
        print("-> Seeking from cache")
        self._update_played_time(seeked)
        self._pause_playback()
        self._refill_queue_from_cache()
        self._resume_playback()

    def _update_played_time(self, seeked):
        """Update the played time with the seeked value."""
        with self.played_time.get_lock():
            self.played_time.value = seeked
            print("   played_time set to:", self.played_time.value)

    def _pause_playback(self):
        """Pause playback and enqueuing."""
        with self.playing.get_lock():
            self.playing.value = False
            print("   playing paused")
        self.pause_enqueuing.set()

    def _refill_queue_from_cache(self):
        """Drain and refill the audio queue with cached data."""
        with self.queue_lock:
            old_queue = self._drain_audio_queue()
            self._add_cached_items_to_queue()
            self._requeue_old_items(old_queue)
        self.pause_enqueuing.clear()

    def _drain_audio_queue(self):
        """Drain the audio queue and return the drained items."""
        old_queue = []
        print("   Draining audio_queue…")
        while self.audio_queue.qsize() > 0:
            try:
                item = self.audio_queue.get_nowait()
                old_queue.append(item)
            except queue.Empty:
                continue
        print(f"   Queue size after draining: {self.audio_queue.qsize()}")
        return old_queue

    def _add_cached_items_to_queue(self):
        """Add relevant cached items to the audio queue."""
        to_add = [key for key in self.cache.keys() if key[1] >= self.played_time.value]
        if to_add:
            to_add.sort(key=lambda x: x[0])
            max_idx = to_add[-1][0]
            print("   Max cache idx:", max_idx)
            for key in to_add:
                self.audio_queue.put((key[0], key[2], self.cache[key][1]))
            return max_idx
        return None

    def _requeue_old_items(self, old_queue, max_idx=None):
        """Requeue items from the old queue that are still relevant."""
        if max_idx is not None:
            for item in old_queue:
                if item[0] > max_idx:
                    self.audio_queue.put(item)
        print("   Refill complete")

    def _resume_playback(self):
        """Resume playback after seeking."""
        with self.playing.get_lock():
            self.playing.value = True
            print("   playing resumed")

    def _seek_from_server(self, seeked):
        """Handle seeking by requesting data from the server."""
        print("-> Seeking from server (outside cache range)")
        self._stop_playback_process()
        self._update_played_time(seeked)
        self.cache.clear()
        print("   cache cleared")
        self.stop(True)

    def _stop_playback_process(self):
        """Stop the playback process if it exists."""
        if hasattr(self, 'playback_p'):
            print("Stopping playback process...")
            self.playback_p.join(timeout=0.1)
            if self.playback_p.is_alive():
                self.playback_p.terminate()
                self.playback_p.join()
                print("   playback process terminated")
            else:
                print("   playback process finished")

    def _complete_seek(self):
        """Finalize the seek operation."""
        self.seek_flag.clear()
        print("=== SEEK finished ===\n")

    def stop(self, for_seek=False):
        """
        Stop playback and optionally signal the server.

        :param for_seek: If True, stop is part of a seek operation.
        """
        print("Stopping audio stream...")
        if not for_seek:
            self.in_song = False
            self.song_id = None
        else:
            print("  [stop] pausing reader enqueues")
            self.pause_enqueuing.set()
        print('for seek', for_seek)
        with self.playing.get_lock():
            self.playing.value = False
        with self.queue_lock:
            while self.audio_queue.qsize() > 0:
                try:
                    self.audio_queue.get_nowait()
                except queue.Empty:
                    continue
        print('not playing and queue cleared', self.audio_queue.qsize())
        if not self.done_flag.is_set() and self.sock:
            try:
                self.sock.sendall(protocol.create_msg("STOP", b"1"))
                print('sent stop')
            except Exception as e:
                print(f"Error sending STOP command: {e}")
        else:
            print('already finished receiving')

    def exit(self):
        """Fully terminate the client by stopping playback and cleaning up."""
        self.stop()
        self.real_stop()
        self.done_flag.set()
        self.in_song = False
        self.running = False
        print('out of exit')

    def real_stop(self):
        """Perform a complete shutdown of streaming resources."""
        print("real Stopping audio streaming...")
        with self.playing.get_lock():
            self.playing.value = False
        self.cache.clear()
        if self.sock:
            self.sock.shutdown(socket.SHUT_RDWR)
            try:
                self.sock.unwrap()
            except Exception as e:
                print(f"Error unwrapping socket: {e}")
            try:
                self.sock.close()
            except Exception as e:
                print(f"Error closing socket: {e}")
        if self.ffmpeg_process:
            try:
                self.ffmpeg_process.stdin.close()
                self.ffmpeg_process.terminate()
                self.ffmpeg_process.wait()
            except Exception as e:
                print(f"Error terminating ffmpeg: {e}")
        if hasattr(self, 'playback_p'):
            print("Stopping playback process...")
            self.playback_p.join(timeout=0.1)
            if self.playback_p.is_alive():
                self.playback_p.terminate()
                self.playback_p.join()
                print("   playback process terminated")
            else:
                print("   playback process finished")
        else:
            print("   playback process not found")
        print("Audio streaming stopped.")

    def _check_queue(self):
        """
        Periodically check time_update_queue and invoke time callback.
        Runs every 0.02 seconds when active.
        """
        try:
            msg = self.time_update_queue.get_nowait()
            if msg[0] == "update_time" and self._time_callback:
                played_time, total_time = msg[1], msg[2]
                self._time_callback(played_time, total_time)
        except queue.Empty:
            pass
        if self._queue_checker_running:
            self._queue_checker_timer = threading.Timer(0.02, self._check_queue)
            self._queue_checker_timer.daemon = True
            self._queue_checker_timer.start()

    def _start_queue_checker(self):
        """Start the time update checker if not already running."""
        if not self._queue_checker_running:
            self._queue_checker_running = True
            self._check_queue()

    def _stop_queue_checker(self):
        """Stop the time update checker and cancel its timer."""
        self._queue_checker_running = False
        if self._queue_checker_timer:
            self._queue_checker_timer.cancel()
            self._queue_checker_timer = None