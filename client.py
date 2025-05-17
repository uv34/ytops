import pickle
import sys
import threading
import ssl

import protocol
from audio_client_v2 import AudioClient
from custom_widgets import *
from song import *


class PlaybackController:
    def __init__(self, gen_sock, token, pause_disable_callback, pause_enable_callback, on_playback_callback
                 , update_song_callback, update_cover_callback, update_slider_callback, update_playlist_callback
                 , add_user_callback, key, messagebox_callback):
        self.token = token
        self.gen_socket = gen_sock
        self.client = None
        self.stream_thread = None
        self.song_queue = SongQueue()
        self.volume = 1
        self.skipped = False
        self.playlists = []
        self.status = ""
        self.key = key
        self._send_lock = threading.Lock()
        self.active = True

        # -=+ Callbacks +=-
        self.pause_enable_callback = pause_enable_callback
        self.pause_disable_callback = pause_disable_callback
        self.on_playback_callback = on_playback_callback
        self.update_song_callback = update_song_callback
        self.update_cover_callback = update_cover_callback
        self.update_slider_callback = update_slider_callback
        self.update_playlist_callback = update_playlist_callback
        self.add_user_callback = add_user_callback
        self.messagebox_callback = messagebox_callback

        self.total_time = 1.0
        self.downloaded_time = 0.0
        self.played_time = 0.0
        self.started_playing_time = 0.0

        self.history_segments = []

    #  -=- click stuff -=-
    def click_song_frame(self, event):
        """self.stop_stream()
        self.start_after_stop(event.widget.song_id)"""
        self.play_song(event.widget.song)

    def add_song_to_queue(self, event):
        self.song_queue.add_song(event.widget.song)
        if not self.stream_thread:
            self.stop_stream()
            self.song_queue.next()
            self.start_after_stop(self.song_queue.current_song.song_id)

    def add_song_to_next(self, event):
        self.song_queue.add_song_to_next(event.widget.song)
        if not self.stream_thread:
            self.stop_stream()
            self.song_queue.next()
            self.start_after_stop(self.song_queue.current_song.song_id)

    #  -=- functionality -=-

    def send_recv(self, cmd: str, msg: str):
        with self._send_lock:
            msg = protocol.create_msg(cmd, f"{self.token}~{msg}".encode(), self.key)
            self.gen_socket.send(msg)
            cmd, data = protocol.get_msg(self.gen_socket, self.key)
            if cmd == 'VERF':
                self.update_status('verify', 'needs to verify - check your mail')
            return cmd, data

    def logout(self):
        self.active = False
        self.stop_stream()
        print('logout')
        self._wait_for_stop()
        print('logout')
        self.stream_thread = None
        self.client = None
        self.gen_socket.close()

    def play_playlist(self, p):
        def _real_play(p):
            self.stop_stream()
            self._wait_for_stop()
            self.song_queue.clear()
            for song in p.songs:
                self.song_queue.add_song(song)
            self.skipped = True
            self.song_queue.next()

            self.start_stream(self.song_queue.current_song.song_id)
        thread = threading.Thread(target=_real_play, args=(p,), daemon=True)
        thread.start()

    def play_song(self, s):
        def _real_play(s):
            self.stop_stream()
            self._wait_for_stop()
            self.song_queue.clear()
            self.song_queue.add_song(s)
            self.skipped = True
            self.song_queue.next()

            self.start_stream(self.song_queue.current_song.song_id)

        thread = threading.Thread(target=_real_play, args=(s,), daemon=True)
        thread.start()
    def _wait_for_stop(self):
        if self.stream_thread and self.stream_thread.is_alive():
            timer = threading.Timer(0.1, self._wait_for_stop)
            timer.daemon = True
            timer.start()
        else:
            print('stopped')
        print('1')

    def create_playlist(self, name, cover_file):
        with open(cover_file, "rb") as cover_file:
            coverb64 = base64.b64encode(cover_file.read())
        cmd, data = self.send_recv("CRPL", f"{name}~{coverb64.decode()}")
        if cmd == "CRPL":
            if data[:2].decode() == "OK":
                print('adding playlist')
                self._add_playlists_to_shown(pickle.loads(data[2:]))
                print("Success", "Playlist created successfully!")
            else:
                print("Error", "Failed to create playlist.")

    def _add_playlists_to_shown(self, p):
        self.playlists.append(p)
        print('playlists:', self.playlists)
        self.update_playlist_callback()
        print('added', p)

    def delete_playlist(self, event):
        p_to_delete = event.widget.playlist
        cmd, data = self.send_recv("DLPL", f"{p_to_delete.playlist_id}")
        if cmd == "DLPL":
            if data[:2].decode() == "OK":
                self.playlists.remove(p_to_delete)
                self.update_playlist_callback()
                return
        print("Error", "Failed to delete playlist.")

    def add_to_playlist(self, song, p_to_add):
        print('add top playlist')
        cmd, data = self.send_recv("ASTP", f"{p_to_add.playlist_id}~{song.song_id}")
        if cmd == "ASTP":
            if data[:2].decode() == "OK":
                p_to_add.add_song(song)
                self.update_playlist_callback()
                print("Success", "Song added to playlist successfully!")
                return
        print("Error", "Failed to add song to playlist.")

    def remove_song_from_playlist(self, pid, sid):
        cmd, data = self.send_recv("RSFP", f"{pid}~{sid}")
        print('data', data)
        if cmd == "RSFP":
            if data[:2].decode() == "OK":
                print("Success", "Song removed from playlist successfully!")
                return True
        print("Error", "Failed to remove song from playlist.")
        return False

    def search(self, query):
        cmd, data = self.send_recv("SSIS", query)
        if cmd == "SSIS":
            songs = pickle.loads(data)
            print("Success", "Search completed successfully!")
            return songs
        print("Error", "Failed to search for song.")

    def user_search_suggestions(self, query):
        cmd, data = self.send_recv("USSS", query)
        if cmd == "USSS":
            users = data.decode().split(' ')
            print("Success", "Search completed successfully!")
            return users
        print("Error", "Failed to search for song.")

    def get_user_following(self):
        cmd, data = self.send_recv("FLWS", "")
        if cmd == "FLWS":
            users = data.decode().split(' ')
            print("users:", users)
            print("Success", "Search completed successfully!")
            users = [] if users == [''] else users
            return users
        print("Error", "Failed to get followings")
        return []

    def follow_user(self, user):
        cmd, data = self.send_recv("FOLW", user)
        if cmd == "FOLW":
            if data.decode() == "OK":
                print("Success", "User followed successfully!")
                self.add_user_callback(user)
                return
        print("Error", "Failed to follow user.")

    def unfollow_user(self, user):
        cmd, data = self.send_recv("UNFL", user)
        if cmd == "UNFL":
            if data.decode() == "OK":
                print("Success", "User unfollowed successfully!")
                return True
        print("Error", "Failed to unfollow user.")
        return False

    def get_social_profile(self, username):
        cmd, data = self.send_recv("PRFL", username)
        if cmd == "PRFL":
            social_profile = pickle.loads(data)
            return social_profile
        return {}


    def fetch_recommendations(self):
        cmd, data = self.send_recv("RECM", "")
        if cmd == "RECM":
            songs, playlists = pickle.loads(data)
            print("Fetched songs")
            print(self.history_segments)
            return songs, playlists
        return [], []

    def upload_song(self, song_file, song_name, song_author, album_id):
        with open(song_file, "rb") as song_f:
            song_data = song_f.read()
        songb64 = base64.b64encode(song_data)
        cmd, data = self.send_recv("UPLS", f"{song_name}~{song_author}~{album_id}~{songb64.decode()}")
        if cmd == "UPLS":
            if data[:2].decode() == "OK":
                print("Success", "Song uploaded successfully!")
                return
        print("Error", "Failed to upload song.")

    def upload_album(self, album_name, album_author, cover_file):
        with open(cover_file, "rb") as cover_f:
            cover_data = cover_f.read()
        coverb64 = base64.b64encode(cover_data)
        cmd, data = self.send_recv("UPLA", f"{album_name}~{album_author}~{coverb64.decode()}")
        if cmd == "UPLA":
            if data[:2].decode() == "OK":
                print("Success", "Album uploaded successfully!")
                return
        print("Error", "Failed to upload album.")

    def get_albums(self):
        cmd, data = self.send_recv("GETA", "")
        if cmd == "GETA":
            albums = pickle.loads(data)
            print("Fetched albums")
            return albums
        return []

    #  -=- streaming -=-
    def start_after_stop(self, song_id):
        if self.stream_thread and self.stream_thread.is_alive():
            timer = threading.Timer(0.1, self.start_after_stop, args=(song_id,))
            timer.daemon = True
            timer.start()
        else:
            self.start_stream(song_id)

    def pause_stream(self):
        print(self.played_time, "-----------------------------")
        if self.client:
            self.client.pause()
            new_state = "Paused" if not self.client.playing else "Resumed"

    def stop_stream(self):
        if self.client:
            self.client.stop()
        self.pause_disable_callback()

    def exit(self):
        self.active = False
        if self.client:
            self.client.exit()
            print('logout')
            self._wait_for_stop()
            print('logout')
        self.pause_disable_callback()
        self.stream_thread = None
        self.client = None
        try:
            self.gen_socket.unwrap()  # Attempt to send SSL closure alert
            print("General socket unwrapped")
        except ssl.SSLError as e:
            if "APPLICATION_DATA_AFTER_CLOSE_NOTIFY" in str(e):
                print("Warning: Server sent application data after close notify. Ignoring.")
            else:
                print(f"Error unwrapping gen_socket: {e}")
        except Exception as e:
            print(f"Unexpected error during unwrap: {e}")
        finally:
            self.gen_socket.close()
            print("General socket closed")

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
        listened_segment = PlaybackSegment(self.song_queue.current_song.song_id, self.started_playing_time
                                           , self.played_time, self.total_time)
        msg = protocol.create_msg("USTH", (self.token.encode() + b'~' + pickle.dumps(listened_segment)), self.key)
        self.gen_socket.send(msg)
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

        if not self.active:
            print("Info", "Not streaming!")
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
                self.client.ask_for_song(song_id, time, self.token)
                self.client.receive_stream()
                self.client = None
            except Exception as e:
                print("Error", str(e))
                print(f"Error")
            finally:
                print(f'skipped: {self.skipped} ')
                if not self.skipped:
                    self.song_queue.next()
                self.skipped = False
                if self.song_queue.current_song and self.active:
                    listened_segment = PlaybackSegment(self.song_queue.current_song.song_id, self.started_playing_time
                                                       , self.played_time, self.total_time)
                    msg = protocol.create_msg("USTH", (self.token.encode() + b'~' + pickle.dumps(listened_segment)), self.key)
                    self.gen_socket.send(msg)
                    self.history_segments.append(listened_segment)
                    self.start_after_stop(self.song_queue.current_song.song_id)
                else:
                    print('no song')
                    self.pause_disable_callback()
                    self.stream_thread = None

        # Start background thread to avoid blocking UI
        self.stream_thread = threading.Thread(target=run, daemon=True)
        self.stream_thread.start()

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
                self.update_cover_callback()
            if self.client:
                timer = threading.Timer(0.1, check_metadata)
                timer.daemon = True
                timer.start()

        check_metadata()

    # --- util ---
    def update_status(self, title, status):
        self.status = status
        self.messagebox_callback(title, status)
