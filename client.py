import pickle  # Used for serializing and deserializing Python objects
import socket  # Used for creating and managing network sockets
import ssl  # Used for handling SSL/TLS encryption
import threading  # Used for creating and managing threads
import base64  # Used for encoding and decoding data in base64 format
import time  # Used for time-related functions

import protocol  # Custom module for communication protocol
from audio_client_v2 import AudioClient  # Custom module for audio streaming
from custom_widgets import *  # Custom widgets for the UI
from song import *  # Custom classes for song, playlist, etc.

class PlaybackController:
    """
    Manages playback, communication with the server, and user interactions for the Stopify client.

    Attributes:
        token (str): JWT token for authenticating requests to the server.
        gen_socket (socket): General socket for communication with the server.
        client (AudioClient): Instance of AudioClient for handling audio streaming.
        stream_thread (threading.Thread): Thread for running the audio streaming process.
        song_queue (SongQueue): Queue of songs to be played.
        volume (float): Current volume level (0.0 to 1.0).
        skipped (bool): Flag indicating if the current song was skipped.
        playlists (list): List of user's playlists.
        status (str): Current status message.
        key (bytes): Shared key for encrypting/decrypting messages.
        _send_lock (threading.Lock): Lock for synchronizing send operations.
        stream_lock (threading.Lock): Lock for synchronizing stream operations.
        active (bool): Flag indicating if the controller is active.
        username (str): Username of the logged-in user.
        password (str): Password of the logged-in user.
        total_time (float): Total duration of the current song in seconds.
        downloaded_time (float): Downloaded duration of the current song in seconds.
        played_time (float): Played duration of the current song in seconds.
        started_playing_time (float): Time when playback started.
        history_segments (list): List of playback segments for history.

    Callbacks:
        pause_enable_callback: Callback to enable the pause button.
        pause_disable_callback: Callback to disable the pause button.
        on_playback_callback: Callback for playback time updates.
        update_song_callback: Callback to update song information in the UI.
        update_cover_callback: Callback to update the song cover in the UI.
        update_slider_callback: Callback to update the playback slider.
        update_playlist_callback: Callback to update the playlist display.
        add_user_callback: Callback to add a user to the following list.
        messagebox_callback: Callback to display messages to the user.
    """

    def __init__(self, gen_sock, token, pause_disable_callback, pause_enable_callback, on_playback_callback,
                 update_song_callback, update_cover_callback, update_slider_callback, update_playlist_callback,
                 add_user_callback, key, messagebox_callback, username, password):
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
        self.stream_lock = threading.Lock()
        self.active = True

        self.username = username
        self.password = password

        # Callbacks for UI updates and interactions
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

    # --- User Interaction Handlers ---
    def add_song_to_queue(self, event):
        """
        Add a song to the playback queue and start playing if not already streaming.

        :param event: Event object containing the song widget.
        """
        self.song_queue.add_song(event.widget.song)
        if not self.stream_thread:
            self.stop_stream()
            self.song_queue.next()
            self.start_after_stop(self.song_queue.current_song.song_id)

    def add_song_to_next(self, event):
        """
        Add a song to play next in the queue and start playing if not already streaming.

        :param event: Event object containing the song widget.
        """
        self.song_queue.add_song_to_next(event.widget.song)
        if not self.stream_thread:
            self.stop_stream()
            self.song_queue.next()
            self.start_after_stop(self.song_queue.current_song.song_id)

    # --- Server Communication ---
    def update_token(self):
        """
        Update the JWT token by sending a token request to the server.
        """
        self.gen_socket.send(protocol.create_msg("TOKN", f'{self.username}~{self.password}'.encode(), self.key))
        cmd, data = protocol.get_msg(self.gen_socket, self.key)
        print('update token2', cmd, data)
        if cmd == 'TOKN':
            self.token = data.decode()
        else:
            self.token = '###'

    def send_recv(self, og_cmd: str, msg_data: str):
        """
        Send a request to the server and receive the response, handling token validation and renewal.

        :param og_cmd: Original command to send.
        :param msg_data: Data to send with the command.
        :return: Tuple (cmd, data) received from the server.
        """
        with self._send_lock:
            msg = protocol.create_msg(og_cmd, f"{self.token}~{msg_data}".encode(), self.key)
            self.gen_socket.send(msg)
            cmd, data = protocol.get_msg(self.gen_socket, self.key)
            if cmd == 'VERF':
                self.update_status('verify', 'needs to verify - check your mail')
            if cmd == 'TOKN':
                print('update token', cmd, data)
                self.update_token()
                new_msg = protocol.create_msg(og_cmd, f"{self.token}~{msg_data}".encode(), self.key)
                print('updated token, sending msg ', f"{og_cmd}{self.token}~{msg_data}".encode())
                self.gen_socket.send(new_msg)
                cmd, data = protocol.get_msg(self.gen_socket, self.key)
                print('final data', data)
            return cmd, data

    def logout(self):
        """
        Log out the user by stopping the stream and closing the connection.
        """
        self.active = False
        self.stop_stream()
        print('logout')
        self.stream_thread = None
        self.client = None
        self.gen_socket.send(protocol.create_msg("EXIT", self.token.encode(), self.key))
        try:
            self.gen_socket.unwrap()  # Send close notify and shut down SSL
        except Exception as e:
            print(f"Error during unwrap: {e}")
        finally:
            self.gen_socket.close()

    # --- Playback Control ---
    def play_playlist(self, p):
        """
        Play a playlist by adding its songs to the queue and starting streaming.

        :param p: Playlist object to play.
        """
        with self.stream_lock:
            self.stop_stream()
            self.song_queue.clear()
            for song in p.songs:
                self.song_queue.add_song(song)
            if self.stream_thread and self.stream_thread.is_alive():
                self.skipped = True
            self.song_queue.next()
            self.start_stream(self.song_queue.current_song.song_id)

    def play_song(self, s):
        """
        Play a single song by adding it to the queue and starting streaming.

        :param s: Song object to play.
        """
        with self.stream_lock:
            self.stop_stream()
            self._wait_for_stop()
            self.song_queue.clear()
            self.song_queue.add_song(s)
            self.song_queue.next()
            self.start_stream(self.song_queue.current_song.song_id)

    def _wait_for_stop(self):
        """
        Wait for the current stream to stop before proceeding.
        """
        if self.stream_thread and self.stream_thread.is_alive():
            timer = threading.Timer(0.1, self._wait_for_stop)
            timer.daemon = True
            timer.start()
        else:
            print('stopped')
        print('1')

    # --- Playlist Management ---
    def create_playlist(self, name, cover_file):
        """
        Create a new playlist on the server.

        :param name: Name of the playlist.
        :param cover_file: Path to the cover image file.
        """
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
        """
        Add a playlist to the local list and update the UI.

        :param p: Playlist object to add.
        """
        self.playlists.append(p)
        print('playlists:', self.playlists)
        self.update_playlist_callback()
        print('added', p)

    def delete_playlist(self, event):
        """
        Delete a playlist from the server and update the local list.

        :param event: Event object containing the playlist widget.
        """
        p_to_delete = event.widget.playlist
        cmd, data = self.send_recv("DLPL", f"{p_to_delete.playlist_id}")
        if cmd == "DLPL":
            if data[:2].decode() == "OK":
                self.playlists.remove(p_to_delete)
                self.update_playlist_callback()
                return
        print("Error", "Failed to delete playlist.")

    def add_to_playlist(self, song, p_to_add):
        """
        Add a song to a playlist on the server.

        :param song: Song object to add.
        :param p_to_add: Playlist object to add the song to.
        """
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
        """
        Remove a song from a playlist on the server.

        :param pid: Playlist ID.
        :param sid: Song ID.
        :return: True if successful, False otherwise.
        """
        cmd, data = self.send_recv("RSFP", f"{pid}~{sid}")
        print('data', data)
        if cmd == "RSFP":
            if data[:2].decode() == "OK":
                print("Success", "Song removed from playlist successfully!")
                return True
        print("Error", "Failed to remove song from playlist.")
        return False

    # --- Search and Social Features ---
    def search(self, query):
        """
        Search for songs based on a query.

        :param query: Search query string.
        :return: List of matching Song objects.
        """
        cmd, data = self.send_recv("SSIS", query)
        if cmd == "SSIS":
            songs = pickle.loads(data)
            print("Success", "Search completed successfully!")
            return songs
        print("Error", "Failed to search for song.")

    def user_search_suggestions(self, query):
        """
        Get user suggestions based on a query.

        :param query: Search query string.
        :return: List of matching usernames.
        """
        cmd, data = self.send_recv("USSS", query)
        if cmd == "USSS":
            users = data.decode().split(' ')
            print("Success", "Search completed successfully!")
            return users
        print("Error", "Failed to search for song.")

    def get_user_following(self):
        """
        Get the list of users the current user is following.

        :return: List of usernames.
        """
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
        """
        Follow another user.

        :param user: Username of the user to follow.
        """
        cmd, data = self.send_recv("FOLW", user)
        if cmd == "FOLW":
            if data.decode() == "OK":
                print("Success", "User followed successfully!")
                self.add_user_callback(user)
                return
        print("Error", "Failed to follow user.")

    def unfollow_user(self, user):
        """
        Unfollow another user.

        :param user: Username of the user to unfollow.
        :return: True if successful, False otherwise.
        """
        cmd, data = self.send_recv("UNFL", user)
        if cmd == "UNFL":
            if data.decode() == "OK":
                print("Success", "User unfollowed successfully!")
                return True
        print("Error", "Failed to unfollow user.")
        return False

    def get_social_profile(self, username):
        """
        Get the social profile of a user.

        :param username: Username of the user.
        :return: Dictionary containing profile data.
        """
        cmd, data = self.send_recv("PRFL", username)
        if cmd == "PRFL":
            social_profile = pickle.loads(data)
            return social_profile
        return {}

    # --- Recommendations and Admin Features ---
    def fetch_recommendations(self):
        """
        Fetch song and playlist recommendations from the server.

        :return: Tuple (songs, playlists).
        """
        cmd, data = self.send_recv("RECM", "")
        if cmd == "RECM":
            songs, playlists = pickle.loads(data)
            print("Fetched songs")
            print(self.history_segments)
            return songs, playlists
        return [], []

    def send_wrapped(self, id, start_dt, end_dt):
        """
        Send a wrapped summary email to a user.

        :param id: User ID.
        :param start_dt: Start date for the summary.
        :param end_dt: End date for the summary.
        """
        cmd, data = self.send_recv("WRPD", f"{id}~{start_dt}~{end_dt}")
        if cmd == "WRPD":
            print("Fetched wrapped")
            self.messagebox_callback("Wrapped", f'sent wrpped for user {id} - {data}')

    def get_users(self):
        """
        Get a list of all users.

        :return: List of users.
        """
        cmd, data = self.send_recv("USRS", "")
        if cmd == "USRS":
            if data[:2].decode() == "OK":
                users = pickle.loads(data[2:])
                print("Fetched users")
                return users
        return []

    def upload_song(self, song_file, song_name, song_author, album_id):
        """
        Upload a new song to the server.

        :param song_file: Path to the song file.
        :param song_name: Name of the song.
        :param song_author: Author of the song.
        :param album_id: ID of the album.
        """
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
        """
        Upload a new album to the server.

        :param album_name: Name of the album.
        :param album_author: Author of the album.
        :param cover_file: Path to the cover image file.
        """
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
        """
        Get a list of all albums from the server.

        :return: List of albums.
        """
        cmd, data = self.send_recv("GETA", "")
        if cmd == "GETA":
            albums = pickle.loads(data)
            print("Fetched albums")
            return albums
        return []

    # --- Streaming Control ---
    def start_after_stop(self, song_id):
        """
        Start streaming a song after ensuring the current stream is stopped.

        :param song_id: ID of the song to stream.
        """
        if self.stream_thread and self.stream_thread.is_alive():
            timer = threading.Timer(0.1, self.start_after_stop, args=(song_id,))
            timer.daemon = True
            timer.start()
        else:
            self.start_stream(song_id)

    def pause_stream(self):
        """
        Pause or resume the current stream.
        """
        print(self.played_time, "-----------------------------")
        if self.client:
            self.client.pause()
            new_state = "Paused" if not self.client.playing else "Resumed"

    def stop_stream(self):
        """
        Stop the current stream.
        """
        if self.client:
            self.client.stop()
        self.pause_disable_callback()

    def exit(self):
        """
        Exit the application by stopping the stream and closing the connection.
        """
        self.active = False
        if self.client:
            self.client.exit()
            print('logout')
        self.pause_disable_callback()
        self.stream_thread = None
        self.client = None
        try:
            self.gen_socket.send(protocol.create_msg("EXIT", self.token.encode(), self.key))
            self.gen_socket.shutdown(socket.SHUT_RDWR)
        except OSError as e:
            print(f"Socket error during shutdown: {e}")
        try:
            self.gen_socket.unwrap()  # Attempt to send SSL closure alert
            print("General socket unwrapped")
        except ssl.SSLError as e:
            if "APPLICATION_DATA_AFTER_CLOSE_NOTIFY" in str(e):
                print("Warning", "Server sent application data after close notify. Ignoring.")
            else:
                print(f"Error unwrapping gen_socket: {e}")
        except Exception as e:
            print(f"Unexpected error during unwrap: {e}")
        finally:
            self.gen_socket.close()
            print("General socket closed")

    def start_button(self):
        """
        Skip to the next song in the queue.
        """
        self.skipped = True
        self.song_queue.next()
        if self.client:
            if self.stream_thread:
                self.stop_stream()

    def prev_button(self):
        """
        Go to the previous song in the queue.
        """
        self.skipped = True
        self.song_queue.prev()
        if self.client:
            if self.stream_thread:
                self.stop_stream()

    def seek(self, time):
        """
        Seek to a specific time in the current song.

        :param time: Time to seek to in seconds.
        """
        self.client.seek(time)
        listened_segment = PlaybackSegment(self.song_queue.current_song.song_id, self.started_playing_time,
                                           self.played_time, self.total_time)
        msg = protocol.create_msg("USTH", (self.token.encode() + b'~' + pickle.dumps(listened_segment)), self.key)
        self.gen_socket.send(msg)
        self.history_segments.append(listened_segment)
        self.started_playing_time = time

    # --- Audio Client Callbacks ---
    def on_download_progress(self, cur_pages, duration):
        """
        Callback for download progress updates.

        :param cur_pages: Current number of pages downloaded.
        :param duration: Total duration of the song.
        """
        if cur_pages < len(self.client.times):
            downloaded_sec = self.client.times[cur_pages]
        else:
            downloaded_sec = 0.0
        self._update_download(downloaded_sec, duration)

    def _update_download(self, downloaded_sec, total_sec):
        """
        Update the download progress and notify the UI.

        :param downloaded_sec: Downloaded duration in seconds.
        :param total_sec: Total duration in seconds.
        """
        if total_sec < 1:
            total_sec = 1
        self.total_time = total_sec
        self.downloaded_time = downloaded_sec
        self.update_slider_callback()

    def start_stream(self, sid):
        """
        Start streaming a song in a background thread.

        :param sid: Song ID to stream.
        """
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
            """
            Background thread function to handle streaming.
            """
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
                    listened_segment = PlaybackSegment(self.song_queue.current_song.song_id, self.started_playing_time,
                                                       self.played_time, self.total_time)
                    msg = protocol.create_msg("USTH", (self.token.encode() + b'~' + pickle.dumps(listened_segment)),
                                              self.key)
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
            """
            Periodically check for metadata updates and notify the UI.
            """
            if self.client and self.client.cover != b'':
                # Update the text label with metadata
                self.update_song_callback()
                self.update_cover_callback()
            if self.client:
                timer = threading.Timer(0.1, check_metadata)
                timer.daemon = True
                timer.start()

        check_metadata()

    # --- Utility ---
    def update_status(self, title, status):
        """
        Update the status message and display it to the user.

        :param title: Title of the message.
        :param status: Status message content.
        """
        self.status = status
        self.messagebox_callback(title, status)