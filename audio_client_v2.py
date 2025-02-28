import socket
import subprocess
import threading
import queue
import pygame
import numpy as np
from pygame import sndarray
import protocol
import pickle
import base64


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


class AudioClient:
    """
    A client that requests "song_name~time" from server,
    then decodes Ogg data from that time onward using ffmpeg + pygame.
    """

    def __init__(self, host='127.0.0.1', port=5000, chunk_size=8192):
        self.host = host
        self.port = port
        self.chunk_size = chunk_size
        self.sock = None

        self.song_id = None
        self.song_name = ''
        self.author = ''
        self.album = ''
        self.cover = b''
        self.audio_queue = None
        self.done_flag = None  # stopped receiving from server
        self.ffmpeg_process = None
        self.playing = False
        self.running = False
        self.in_song = False
        self.cache = {}  # (PCM_number, time): processed data

        self.total_pages = 0
        self.current_pages = 0
        self.played_time = 0.0
        self.total_duration = 0.0
        self.sample_rate = 44100
        self.times = []

        # callbacks
        self._progress_callback = None  # (current_pages, duration)
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
    def ask_for_song(self, song_id: str, t: float):
        """
        connects to the server, sends "RQST" with data = "song_id~t".
        """
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect((self.host, self.port))
        req_str = f"{song_id}~{t}"
        self.song_id = song_id
        print(f'{self.sock} is asking for {song_id} in {t}')

        msg = protocol.create_msg("RQST", req_str.encode())
        self.sock.sendall(msg)

    # -------------
    # Decoding & Playback
    # -------------
    def receive_stream(self):
        """
        Reads either "ERR" or "PGNM" from server.
        If "PGNM", parse data, then start ffmpeg + streaming loop.
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

        # parse e.g. "179~180.5~20~44100~170~(byte data for a pickled list)"
        splited = data.split(b'|')
        metadata = splited[0]
        times_str = b'|'.join(splited[1:-1])
        cover_b64 = splited[-1]
        name_str, auth_str, album_str, pages_str, dur_str, cur_str, slr_str, pgn_str = metadata.split(b'~')
        self.total_pages = int(pages_str.decode())
        self.total_duration = float(dur_str.decode())
        self.played_time = float(cur_str.decode())
        self.sample_rate = int(slr_str.decode())
        self.current_pages = int(pgn_str.decode())
        self.song_name = name_str.decode()
        self.album = album_str.decode()
        self.author = auth_str.decode()
        self.cover = base64.b64decode(cover_b64)
        self.times = pickle.loads(times_str)

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
        print('ffmpeg command:', ffmpeg_cmd)
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
        print('back to noraml', self.running, self.playing)

    def stream_loop(self, client_socket):
        """
        Continuously recv Ogg data from the server, count pages and feed to ffmpeg stdin.
        checks for when the server finishes sending data
        """
        self.playing = True
        self.running = True
        self.in_song = True
        while True:
            cmd, chunk = protocol.get_msg(client_socket)
            if cmd == "SCNF":
                print("Server confirmed stop")
                # Signal the playback and reader threads to stop
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
        """
        Reads raw PCM from ffmpeg stdout and puts it in the audio_queue
        ffmpeg stdout -> audio_queue
        """
        bytes_per_frame = 4.0  # 16-bit * 2 channels
        virtual_time = self.played_time  # represents the received processed time
        self.running = True
        c = 0
        while self.running:
            if self.done_flag.is_set():
                break
            pcm = self.ffmpeg_process.stdout.read(self.chunk_size)
            if not pcm:
                break
            if not self.done_flag.is_set():  # in case done flag is set after receiving
                sound = self.pcm_chunk_to_sound(pcm)
                n_frames = len(pcm) / bytes_per_frame
                duration_s = n_frames / self.sample_rate

                self.cache[(c, virtual_time, duration_s)] = sound

                self.audio_queue.put((c, duration_s, sound))
                # self.audio_queue.put((c, pcm))
                c += 1
                virtual_time += duration_s
        print('reader thread done')

        self.running = False

    def playback_thread_func(self):
        """
        Converts PCM to PyGame Sounds and plays them, tracking time and buffering.
        """
        pygame.mixer.init(frequency=self.sample_rate, size=-16, channels=2)
        bytes_per_frame = 4.0  # 16-bit * 2 channels

        while True:
            if not self.running and self.audio_queue.empty():
                print('done flag set and audio queue empty')
                break

            if not self.playing:
                pygame.time.Clock().tick(50)
                continue

            try:
                # i, duration_s, sound = self.audio_queue.get(timeout=0.1)
                i, duration_s, sound = self.audio_queue.get(timeout=0.1)
            except queue.Empty:
                continue

            sound.play()

            while pygame.mixer.get_busy() and self.playing:
                pygame.time.Clock().tick(200)

            self.played_time += duration_s
            if self._time_callback:
                self._time_callback(self.played_time, self.total_duration)

        self.real_stop()
        if self.in_song:
            print('asking from', self.played_time)
            self.ask_for_song(self.song_id, self.played_time)
            self.receive_stream()

        print('stopped playback')
        pygame.mixer.quit()


    def pcm_chunk_to_sound(self, pcm_chunk):
        """
        converts pcm to pygame sounds
        """
        samples = np.frombuffer(pcm_chunk, dtype=np.int16)
        samples = samples.reshape(-1, 2)
        return sndarray.make_sound(samples)

    # -------------
    # Controls
    # -------------
    def pause(self):
        """
        pause the playback
        :return:
        """
        self.playing = not self.playing

    def seek(self, seeked):  # can be optimized
        times = [key[1] for key in self.cache.keys()]

        if max(times) >= seeked >= min(times):
            print('seeking from cache')
            self.played_time = seeked
            save_state = self.running
            self.running = True

            old_queue = list(self.audio_queue.queue)
            self.audio_queue.queue.clear()

            to_add = [t for t in self.cache if t[1] >= self.played_time]
            added = []
            first = to_add[0]
            for t in to_add:
                if t[0] not in added:
                    self.audio_queue.put((t[0], t[2], self.cache[t]))
                    added.append(t[0])

            for item in old_queue:

                if item[0] not in added and item[0] > first[0]:
                    self.audio_queue.put(item)
                    added.append(item[0])
            self.running = save_state
        else:
            print('seeking from server')
            self.played_time = seeked
            self.stop(True)
        print('finished seeking')

    def stop(self, for_seek=False):
        """
        asks the server to stop
        """

        print("Stopping audio stream...")
        if not for_seek:
            self.in_song = False
            self.song_id = None
        print('for seek', for_seek)
        self.playing = False  # Stop playback
        self.audio_queue.queue.clear()
        print('not playing and queue cleared')

        if not self.done_flag.is_set():
            if self.sock:
                self.sock.sendall(protocol.create_msg("STOP", b"1"))
                print('sent stop')
        else:
            print('already finished receiving')

    def real_stop(self):
        """
        Stops playback, closes connections, and terminates the ffmpeg process.
        """
        self.playing = False
        self.cache = {}
        if self.sock:
            try:
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

        print("Audio streaming stopped.")
