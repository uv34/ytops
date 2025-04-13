import pickle
import threading

import protocol
from audio_client_v2 import AudioClient
from custom_widgets import *


class PlaybackController:
    def __init__(self, gen_sock, token, pause_disable_callback, pause_enable_callback, on_playback_callback
                 , update_song_callback, update_cover_callback, update_slider_callback, update_playlist_callback):
        self.token = token
        self.gen_socket = gen_sock
        self.client = None
        self.stream_thread = None
        self.song_queue = SongQueue()
        self.volume = 1
        self.skipped = False
        self.playlists = []
        self.status = ""

        # -=+ Callbacks +=-
        self.pause_enable_callback = pause_enable_callback
        self.pause_disable_callback = pause_disable_callback
        self.on_playback_callback = on_playback_callback
        self.update_song_callback = update_song_callback
        self.update_cover_callback = update_cover_callback
        self.update_slider_callback = update_slider_callback
        self.update_playlist_callback = update_playlist_callback

        self.total_time = 1.0
        self.downloaded_time = 0.0
        self.played_time = 0.0
        self.started_playing_time = 0.0

        self.history_segments = []

    #  -=- click stuff -=-
    def click_song_frame(self, event):
        """self.stop_stream()
        self.start_after_stop(event.widget.song_id)"""
        self.song_queue.add_song(event.widget.song.song_id)
        if not self.stream_thread:
            self.stop_stream()
            self.song_queue.next()
            self.start_after_stop(self.song_queue.current_song)

    #  -=- functionality -=-
    def play_playlist(self, p):
        self.stop_stream()
        self.skipped = True
        self.song_queue.clear()
        for song in p.songs:
            self.song_queue.add_song(song.song_id)
        if not self.stream_thread:
            self.song_queue.next()
        print(self.song_queue)
        self.start_after_stop(self.song_queue.current_song)

        print("queue", list(self.song_queue.queue))
        print("history", list(self.song_queue.history))

    def create_playlist(self, name, cover_file):
        with open(cover_file, "rb") as cover_file:
            coverb64 = base64.b64encode(cover_file.read())
        msg = protocol.create_msg("CRPL", f"{self.token}~{name}~{coverb64.decode()}".encode())
        self.gen_socket.send(msg)
        cmd, data = protocol.get_msg(self.gen_socket)
        if cmd == "CRPL":
            if data[:2].decode() == "OK":
                self._add_playlists_to_shown(pickle.loads(data[2:]))
                print("Success", "Playlist created successfully!")
            else:
                print("Error", "Failed to create playlist.")

    def _add_playlists_to_shown(self, p):
        self.playlists.append(p)
        self.update_playlist_callback()
        print('added', p)

    def delete_playlist(self, event):
        p_to_delete = event.widget.playlist
        msg = protocol.create_msg("DLPL", f"{self.token}~{p_to_delete.playlist_id}".encode())
        self.gen_socket.send(msg)
        cmd, data = protocol.get_msg(self.gen_socket)
        if cmd == "DLPL":
            if data[:2].decode() == "OK":
                self.playlists.remove(p_to_delete)
                self.update_playlist_callback()
                return
        print("Error", "Failed to delete playlist.")

    def add_to_playlist(self, song, p_to_add):
        print('add top playlist')
        msg = protocol.create_msg("ASTP", f"{self.token}~{p_to_add.playlist_id}~{song.song_id}".encode())
        self.gen_socket.send(msg)
        cmd, data = protocol.get_msg(self.gen_socket)
        if cmd == "ASTP":
            if data[:2].decode() == "OK":
                p_to_add.add_song(song)
                print("Success", "Song added to playlist successfully!")
                return
        print("Error", "Failed to add song to playlist.")

    def fetch_recommendations(self):
        self.gen_socket.send(protocol.create_msg("RECM", self.token.encode() + b'~'))
        msg, data = protocol.get_msg(self.gen_socket)
        songs, playlists = pickle.loads(data)
        print("Fetched songs")
        print(self.history_segments)
        return songs, playlists

    #  -=- streaming -=-
    def start_after_stop(self, song_id):
        if self.stream_thread and self.stream_thread.is_alive():
            timer = threading.Timer(0.1, self.start_after_stop, args=(song_id,))
            timer.start()
        else:
            self.start_stream(song_id)

    def pause_stream(self):
        if self.client:
            self.client.pause()
            new_state = "Paused" if not self.client.playing else "Resumed"
            self.update_status(new_state)

    def stop_stream(self):
        if self.client:
            self.client.stop()
        self.update_status("Stopped")
        self.pause_disable_callback()

    def start_button(self):
        self.skipped = True
        self.song_queue.next()
        if self.client:
            if self.stream_thread:
                self.stop_stream()

    def prev_button(self):
        self.skipped = True
        self.song_queue.prev()
        if self.client:
            if self.stream_thread:
                self.stop_stream()

    def seek(self, time):
        self.client.seek(time)
        listened_segment = PlaybackSegment(self.song_queue.current_song, self.started_playing_time
                                           , self.played_time, self.total_time)
        self.history_segments.append(listened_segment)
        self.started_playing_time = time

    # --- Audio client Callbacks ---
    def on_download_progress(self, cur_pages, duration):
        if cur_pages < len(self.client.times):
            downloaded_sec = self.client.times[cur_pages]
        else:
            downloaded_sec = 0.0
        self._update_download(downloaded_sec, duration)

    def _update_download(self, downloaded_sec, total_sec):
        if total_sec < 1:
            total_sec = 1
        self.total_time = total_sec
        self.downloaded_time = downloaded_sec
        self.update_slider_callback()

    def start_stream(self, sid):
        if self.stream_thread and self.stream_thread.is_alive():
            print("Info", "Already streaming!")
            return

        song_id = sid
        time = 0
        self.started_playing_time = 0.0

        self.client = AudioClient()
        self.client.set_progress_callback(self.on_download_progress)
        self.client.set_time_callback(self.on_playback_callback)
        print('audio client created')

        def run():
            try:
                self.update_status("Connecting to server...")
                self.client.ask_for_song(song_id, time, self.token)
                self.update_status(f"Requesting {song_id}, time={time}")
                self.client.receive_stream()
                self.update_status("Stream ended.")
                self.client = None
            except Exception as e:
                print("Error", str(e))
                self.update_status(f"Error: {e}")
                print(f"Error")
            finally:
                listened_segment = PlaybackSegment(self.song_queue.current_song, self.started_playing_time
                                                   , self.played_time, self.total_time)
                msg = protocol.create_msg("USTH", (self.token.encode() + b'~' + pickle.dumps(listened_segment)))
                self.gen_socket.send(msg)
                self.history_segments.append(listened_segment)
                if not self.skipped:
                    self.song_queue.next()
                self.skipped = False
                if self.song_queue.current_song:
                    self.start_after_stop(self.song_queue.current_song)
                else:
                    print('no song')
                    self.pause_disable_callback()
                    self.stream_thread = None

        # Start background thread to avoid blocking UI
        self.stream_thread = threading.Thread(target=run, daemon=True)
        self.stream_thread.start()

        self.update_status("Attempting to stream...")
        self.client.set_volume(self.volume)
        self.pause_enable_callback()
        # Reset times
        self.total_time = 1.0
        self.downloaded_time = 0.0
        self.played_time = 0.0

        def check_metadata():
            if self.client and self.client.cover != b'':
                # Update the text label with metadata
                self.update_song_callback()
                try:
                    self.update_cover_callback()
                except Exception as e:
                    print(f"Error loading cover image: {e}")
            if self.client:
                timer = threading.Timer(0.1, check_metadata)
                timer.start()

        check_metadata()

    # --- util ---
    def update_status(self, status):
        self.status = status
        print('current status:', status)
