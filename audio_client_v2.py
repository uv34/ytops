import socket
import subprocess
import threading
import queue
import multiprocessing
import pygame
import numpy as np
from pygame import sndarray
import protocol
import pickle
import base64
from encryption import CryptoManager

def closest_index(sorted_list, target):
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

def playback_process_func(audio_queue, done_flag, playing, volume, sample_rate, played_time, time_update_queue, total_duration, seek_flag):
    def pcm_chunk_to_sound(pcm):
        samples = np.frombuffer(pcm, dtype=np.int16)
        samples = samples.reshape(-1, 2)
        return sndarray.make_sound(samples)
    pygame.mixer.init(frequency=sample_rate, size=-16, channels=2)
    while True:
        if done_flag.is_set() and audio_queue.empty():
            break
        if not playing.value:
            pygame.time.Clock().tick(50)
            continue
        try:
            i, duration_s, pcm = audio_queue.get(timeout=0.1)
        except queue.Empty:
            continue
        sound = pcm_chunk_to_sound(pcm)
        sound.set_volume(volume.value)
        if seek_flag.is_set():
            pygame.mixer.stop()  # Stop any currently playing sound
            seek_flag.clear()  # Clear the seek flag
        print('playing')
        sound.play()
        while pygame.mixer.get_busy():
            if seek_flag.is_set():
                pygame.mixer.stop()
                seek_flag.clear()
                break
            pygame.time.Clock().tick(200)
        if not seek_flag.is_set():  # Only update time if no seek occurred
            with played_time.get_lock():
                print('updated time', playing.value)
                played_time.value += duration_s
                time_update_queue.put(("update_time", played_time.value, total_duration))
    pygame.mixer.quit()

class AudioClient:
    def __init__(self, host='127.0.0.1', port=5000, chunk_size=8192):
        self.host = host
        self.port = port
        self.chunk_size = chunk_size
        self.sock = None
        self.token = '###'
        self.volume = multiprocessing.Value('d', 1.0)
        self.song_id = None
        self.song_name = ''
        self.author = ''
        self.album = ''
        self.cover = b''
        self.audio_queue = multiprocessing.Queue()
        self.time_update_queue = multiprocessing.Queue()
        self.done_flag = multiprocessing.Event()
        self.seek_flag = multiprocessing.Event()  # Added seek flag
        self.ffmpeg_process = None
        self.playing = multiprocessing.Value('b', True)
        self.running = False
        self.in_song = False
        self.cache = {}
        self.total_pages = 0
        self.current_pages = 0
        self.played_time = multiprocessing.Value('d', 0.0)
        self.total_duration = 0.0
        self.sample_rate = 44100
        self.times = []
        self._progress_callback = None
        self._time_callback = None
        self._queue_checker_running = False
        self._queue_checker_timer = None
        self.queue_lock = threading.Lock()

    def set_progress_callback(self, cb):
        self._progress_callback = cb

    def set_time_callback(self, cb):
        self._time_callback = cb

    def set_volume(self, volume):
        with self.volume.get_lock():
            self.volume.value = volume

    def ask_for_song(self, song_id: str, t: float, token: str):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect((self.host, self.port))
        print('connected')
        req_str = f"{token}~{song_id}~{t}"
        self.song_id = song_id
        self.token = token
        cryp = CryptoManager()
        key_msg = protocol.create_msg("SHKY", base64.b64encode(str(cryp.public_key).encode()))
        cmd, data = protocol.get_msg(self.sock)
        if cmd != 'SHKY':
            print('unexpected response, trying again')
            self.ask_for_song(song_id, t, token)
        pub_a = int(base64.b64decode(data).decode())
        self.sock.send(key_msg)
        shared_key = cryp.shared_secret(pub_a)
        shared_key = cryp.hash_secret(shared_key)
        self.key = shared_key
        print(shared_key, '_'*100)
        print(f'{self.sock} is asking for {song_id} in {t}')
        msg = protocol.create_msg("RQST", req_str.encode())
        self.sock.sendall(msg)
        print('sent request')

    def receive_metadata(self, data):
        splited = data.split(b'|')
        metadata = splited[0]
        times_str = b'|'.join(splited[1:-1])
        cover_b64 = splited[-1]
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

    def receive_stream(self):
        cmd, data = protocol.get_msg(self.sock)
        if cmd == "ERR ":
            print("Error from server:", data.decode())
            return
        if cmd != "PGNM":
            print(f"Unexpected cmd={cmd}, data={data}")
            return
        self.receive_metadata(data)
        print(f"Server responded with {data}")
        ffmpeg_cmd = [
            "ffmpeg",
            "-loglevel", "error",
            "-i", "pipe:0",
            "-f", "s16le",
            "-acodec", "pcm_s16le",
            "-ac", "2",
            "-ar", str(self.sample_rate),
            "pipe:1"
        ]
        print('ffmpeg command:', ffmpeg_cmd)
        self.ffmpeg_process = subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        self.audio_queue = multiprocessing.Queue()
        self.time_update_queue = multiprocessing.Queue()
        self.done_flag.clear()
        self.seek_flag.clear()
        reader_t = threading.Thread(target=self.reader_thread_func, daemon=True)
        reader_t.start()
        playback_p = multiprocessing.Process(
            target=playback_process_func,
            args=(self.audio_queue, self.done_flag, self.playing, self.volume, self.sample_rate, self.played_time, self.time_update_queue, self.total_duration, self.seek_flag),
            daemon=True
        )
        playback_p.start()
        self._start_queue_checker()
        self.stream_loop(self.sock)
        self.ffmpeg_process.stdin.close()
        self.ffmpeg_process.wait()
        reader_t.join()
        playback_p.join()
        self._stop_queue_checker()
        with self.played_time.get_lock():
            if self.played_time.value >= self.total_duration - 0.5:
                self.in_song = False
        if not self.in_song or self.played_time.value >= self.total_duration - 0.5:
            self.real_stop()
        else:
            print('asking from', self.played_time.value)
            self.ask_for_song(self.song_id, self.played_time.value, self.token)
            self.receive_stream()
        print('back to normal', self.running, self.playing.value)

    def stream_loop(self, client_socket):
        with self.playing.get_lock():
            self.playing.value = True
        self.running = True
        self.in_song = True
        while True:
            cmd, chunk = protocol.get_msg(client_socket, self.key)
            if cmd == "SCNF":
                print("Server confirmed stop")
                if self.done_flag:
                    self.done_flag.set()
                    print('done flag set')
                break
            else:
                if not chunk:
                    break
                page_count = chunk.count(b"OggS")
                self.current_pages += page_count
                if self._progress_callback:
                    self._progress_callback(self.current_pages, self.total_duration)
                try:
                    self.ffmpeg_process.stdin.write(chunk)
                    self.ffmpeg_process.stdin.flush()
                except BrokenPipeError:
                    print('pipe error')
                    break

    def reader_thread_func(self):
        bytes_per_frame = 4.0
        virtual_time = self.played_time.value
        self.running = True
        c = 0
        while self.running:
            print('-----------------------')
            if self.done_flag.is_set():
                break
            print('1')
            pcm = self.ffmpeg_process.stdout.read(self.chunk_size)
            print('2')
            if not pcm:
                break
            if not self.done_flag.is_set():
                n_frames = len(pcm) / bytes_per_frame
                duration_s = n_frames / self.sample_rate
                self.cache[(c, virtual_time, duration_s)] = (duration_s, pcm)
                with self.queue_lock:
                    self.audio_queue.put((c, duration_s, pcm))
                c += 1
                virtual_time += duration_s
        print('reader thread done')
        self.running = False

    def pause(self):
        with self.playing.get_lock():
            self.playing.value = not self.playing.value

    def seek(self, seeked):
        times = [key[1] for key in self.cache.keys()]
        if times and max(times) >= seeked >= min(times):
            print('seeking from cache')
            with self.played_time.get_lock():
                self.played_time.value = seeked
            with self.playing.get_lock():
                self.playing.value = False
            self.seek_flag.set()  # Signal playback process to stop current sound
            with self.queue_lock:
                old_queue = []
                while True:
                    try:
                        item = self.audio_queue.get_nowait()
                        old_queue.append(item)
                    except queue.Empty:
                        break
                to_add = [t for t in self.cache if t[1] >= self.played_time.value]
                if to_add:
                    to_add.sort(key=lambda x: x[0])
                    max_c = to_add[-1][0]
                    for t in to_add:
                        self.audio_queue.put((t[0], t[2], self.cache[t][1]))
                    for item in old_queue:
                        if item[0] > max_c:
                            self.audio_queue.put(item)
            with self.playing.get_lock():
                self.playing.value = True
        else:
            print('seeking from server')
            with self.played_time.get_lock():
                self.played_time.value = seeked
            self.stop(True)
        print('finished seeking')

    def stop(self, for_seek=False):
        print("Stopping audio stream...")
        if not for_seek:
            self.in_song = False
            self.song_id = None
        print('for seek', for_seek)
        with self.playing.get_lock():
            self.playing.value = False
        self.seek_flag.set()  # Signal playback process to stop current sound
        with self.queue_lock:
            while True:
                try:
                    self.audio_queue.get_nowait()
                except queue.Empty:
                    break
        print('not playing and queue cleared')
        if not self.done_flag.is_set():
            if self.sock:
                self.sock.sendall(protocol.create_msg("STOP", b"1"))
                print('sent stop')
        else:
            print('already finished receiving')

    def real_stop(self):
        with self.playing.get_lock():
            self.playing.value = False
        self.cache = {}
        if self.sock:
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
        print("Audio streaming stopped.")

    def _check_queue(self):
        try:
            msg = self.time_update_queue.get_nowait()
            if msg[0] == "update_time" and self._time_callback:
                played_time, total_time = msg[1], msg[2]
                self._time_callback(played_time, total_time)
        except queue.Empty:
            pass
        if self._queue_checker_running:
            self._queue_checker_timer = threading.Timer(0.02, self._check_queue)
            self._queue_checker_timer.start()

    def _start_queue_checker(self):
        if not self._queue_checker_running:
            self._queue_checker_running = True
            self._check_queue()

    def _stop_queue_checker(self):
        self._queue_checker_running = False
        if self._queue_checker_timer:
            self._queue_checker_timer.cancel()
            self._queue_checker_timer = None