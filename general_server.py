import base64  # Used for encoding and decoding data in base64 format
import io  # Used for handling in-memory binary streams
import os  # Used for interacting with the operating system, e.g., file operations
import pickle  # Used for serializing and deserializing Python objects
import socket  # Used for creating and managing network sockets
import threading  # Used for creating and managing threads
import time  # Used for time-related functions
import difflib  # Used for computing differences between sequences
import secrets  # Used for generating cryptographically secure random numbers
from datetime import datetime, timedelta  # Used for handling dates and times
import ssl  # Used for handling SSL/TLS encryption
import uuid  # Used for generating unique identifiers

import jwt  # Used for handling JSON Web Tokens (JWT)
from PIL import Image  # Used for image processing

import mysql_helper  # Custom module for MySQL database operations
import protocol  # Custom module for communication protocol
from song import Song, Playlist, PlaybackSegment  # Custom classes for song, playlist, and playback segment
import recommendations  # Custom module for recommendation system
from encryption import CryptoManager  # Custom module for encryption operations
from MailManager import Mail  # Custom module for sending emails
import admin_stuff  # Custom module for administrative functions
import checker  # Custom module for input validation

# Secret key for JWT token generation and verification
SECRET_KEY = 'very-strong-secret-key'
# Threshold value for triggering user profile updates based on unused segments
THRESHOLD = 5

def generate_token(user_id: int) -> str:
    """
    Generate a JWT token for the user with a 1-hour expiration.

    :param user_id: The ID of the user for whom the token is generated
    :return: A JWT token as a string
    """
    payload = {
        "user": user_id,
        "expiration": int(time.time()) + 3600  # Token expires 1 hour from creation
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")

def verify_token(token: str) -> dict or bool:
    """
    Verify the JWT token and check if it is valid and not expired.

    :param token: The JWT token to verify
    :return: The payload if the token is valid and not expired, False otherwise
    """
    try:
        print('checking token', token)
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        if payload['expiration'] < int(time.time()):
            print('token expired')
            return False
        print('checked token', payload)
        return payload
    except Exception as e:
        print('invalid token')
        return False

class User:
    def __init__(self, id, username, status, verified):
        """
        Initialize a User object.

        :param id: The user's unique identifier
        :param username: The user's username
        :param status: The user's status (e.g., 'a' for admin, '0' for regular)
        :param verified: Boolean indicating if the user's email is verified
        """
        self.id = id
        self.username = username
        self.status = status
        self.verified = verified
        self.connected = True  # Tracks if the user is currently connected

class StopifyServer:
    def __init__(self, host="0.0.0.0", port=5001):
        """
        Initialize the StopifyServer.

        :param host: The host address to bind the server to (default: "0.0.0.0")
        :param port: The port to bind the server to (default: 5001)
        """
        self.host = host
        self.port = port
        self.client_users = {}  # Stores connected users mapped by their socket
        self.threads = []  # List of threads handling client connections
        self.db = mysql_helper.DBController(
            host="192.168.1.14", user="stopify", password="stop123", database="mydb", autocommit=True
        )  # Database controller for MySQL interactions
        self.recommender = recommendations.Recommender(self.db)  # Recommendation system instance

    def log(self, direction, client_id, message):
        """
        Log messages for debugging purposes.

        :param direction: Direction of the message ("Sent" or "Received")
        :param client_id: Identifier of the client
        :param message: The message content to log
        """
        print(f'{direction} {client_id}: {message}')

    def check_creds_regi(self, data):
        """
        Validate registration data format and content.

        :param data: Registration data in bytes (format: username~email~password)
        :return: True if data is valid, False otherwise
        """
        if data.count(b'~') != 2:  # Expect exactly 2 separators
            return False
        username, email, password = data.split(b'~')
        if not checker.check_username(username.decode()):
            return False
        if not checker.check_email(email.decode()):
            return False
        if not checker.check_password(password.decode()):
            return False
        return True

    def check_creds_logi(self, data):
        """
        Validate login data format and content.

        :param data: Login data in bytes (format: username~password)
        :return: True if data is valid, False otherwise
        """
        if data.count(b'~') != 1:  # Expect exactly 1 separator
            return False
        username, password = data.split(b'~')
        if not checker.check_username(username.decode()):
            return False
        if not checker.check_password(password.decode()):
            return False
        return True

    def login_user(self, username, hashed_password):
        """
        Attempt to log in a user with provided credentials.

        :param username: The user's username
        :param hashed_password: The user's hashed password
        :return: Tuple (user_id, status) where status indicates success or role
        """
        id, status = self.db.login_user(username, hashed_password)
        return id, status

    def register_user(self, username, email, hashed_password, token, expiry):
        """
        Register a new user and store their details.

        :param username: The user's username
        :param email: The user's email address
        :param hashed_password: The user's hashed password
        :param token: Verification token for email
        :param expiry: Expiration time for the verification token
        :return: Tuple (user_id, status) where status indicates success
        """
        id, status = self.db.add_user(username, hashed_password, email, token, expiry)
        return id, status

    def _update_user_profile(self, user_id):
        """
        Update a user's profile with unused playback segments.

        :param user_id: The ID of the user whose profile is to be updated
        """
        segments_db = self.db.get_unused_segments(user_id, THRESHOLD)
        if not segments_db:
            print(f"No segments found for user {user_id}")
            return
        # Convert database segments to PlaybackSegment objects
        segments = [PlaybackSegment(seg['songs_id'], seg['start_time'], seg['end_time'],
                                    seg['duration'], seg['time']) for seg in segments_db]
        updated_profile, combined_weight, current_time = self.recommender.update_user_profile(user_id, segments)
        self.db.update_user_profile(user_id, updated_profile, combined_weight, current_time)
        print('updated user profile', user_id)
        self.db.mark_segments_used(user_id, THRESHOLD)  # Mark segments as processed

    def hybrid_search(self, songs, query, n=10, cutoff=0.6, prev=[]):
        """
        Perform a hybrid search combining exact prefix and fuzzy matching.

        :param songs: List of tuples (song_id, title) to search through
        :param query: The search query string
        :param n: Maximum number of results to return (default: 10)
        :param cutoff: Similarity threshold for fuzzy matching (default: 0.6)
        :param prev: List of previous results to exclude
        :return: List of matching (song_id, title) tuples
        """
        q = query.lower().strip()
        # First, find exact prefix matches
        results = [(sid, title) for (sid, title) in songs if title.lower().startswith(q) and (sid, title) not in prev]
        if len(results) >= n:
            return results[:n]
        # If insufficient results, perform fuzzy matching on prefix
        prefix_fuzzy = []
        for sid, title in songs:
            if (sid, title) in results:
                continue
            low = title.lower()
            slice_ = low[:len(q)]
            score = difflib.SequenceMatcher(None, q, slice_).ratio()
            if score >= cutoff and (sid, title) not in prev:
                prefix_fuzzy.append((sid, title))
        results.extend(prefix_fuzzy)
        return results[:n]

    def send_msg(self, client_socket, cmd, data, shared_key):
        """
        Send an encrypted message to the client and log it.

        :param client_socket: The socket to send the message to
        :param cmd: The command identifier
        :param data: The data to send
        :param shared_key: The key used for encryption
        """
        msg = protocol.create_msg(cmd, data, shared_key)
        client_socket.send(msg)
        self.log('Sent', client_socket, msg)

    def recv_msg(self, client_socket, shared_key):
        """
        Receive and decrypt a message from the client, logging it.

        :param client_socket: The socket to receive the message from
        :param shared_key: The key used for decryption
        :return: Tuple (cmd, data) if successful, (None, None) on failure
        """
        try:
            cmd, data = protocol.get_msg(client_socket, shared_key)
            self.log('Received', client_socket, f'{cmd} {data}')
            return cmd, data
        except ConnectionError as e:
            print(f"Connection error: {e}")
            client_socket.close()
            self.client_users[client_socket].connected = False
            return None, None

    def handle_login(self, data, client_socket):
        """
        Process a login request from the client.

        :param data: Login data in bytes (format: username~password)
        :param client_socket: The client's socket
        :return: Tuple (status, response) where status is True on success
        """
        if not self.check_creds_logi(data):
            return False, b'contains invalid characters~' + b'###'
        username, hashed_password = data.decode().split('~')
        id, status = self.login_user(username, hashed_password)
        if status != '0':  # Successful login
            self.client_users[client_socket] = User(id, username, status, self.db.is_verified(id))
            print('client users', self.client_users)
            token = generate_token(id)
            print(f'token generated: {token}')
            print('user status', status)
            if status == 'a':
                return True, b'login successful admin~' + token.encode()
            return True, b'login successful ragil~' + token.encode()
        return False, b'password or username incorrect~###'

    def handle_register(self, data, client_socket):
        """
        Process a registration request and send a verification email.

        :param data: Registration data in bytes (format: username~email~password)
        :param client_socket: The client's socket
        :return: Tuple (status, response) where status is True on success
        """
        if not self.check_creds_regi(data):
            return False, b'contains invalid characters~###'
        username, email, hashed_password = data.decode().split('~')
        token = secrets.token_urlsafe(32)  # Generate a secure verification token
        expiry = datetime.utcnow() + timedelta(days=1)
        id, status = self.register_user(username, email, hashed_password, token, expiry)
        if status != '0':  # Successful registration
            self.client_users[client_socket] = User(id, username, status, False)
            print('client users', self.client_users)
            # Email verification HTML content
            html = f"""<!DOCTYPE html>
            <html lang="en">
            <head>
              <meta charset="UTF-8">
              <title>Stopify – Email Verification</title>
            </head>
            <body style="font-family: Arial, sans-serif; line-height: 1.5; color: #333; margin: 20px;">
            <center>
              <h2 style="margin-top: 0;">Welcome to Stopify!</h2>
              <p>To activate your account, please click the link below:</p>
              <p><a href='https://localhost/verify-email?token={token}' style="color: #1a73e8; text-decoration: none;">Verify your email</a></p>
              <p style="font-size: 0.9em; color: #666;">
                This link expires in 24 hours. If you didn’t sign up, you can ignore this message.
              </p>
              <p>Thanks,<br>The Stopify Team</p>
            </center>
            </body>
            </html>"""
            m = Mail('Stopify - Email Verification', html, email)
            m.send()
            token = generate_token(id)
            return True, b'login successful~' + token.encode()
        return False, b'username or mail already exists~###'

    def handle_recm(self, data, payload):
        """
        Handle recommendation request, returning songs and playlists.

        :param data: Request data (unused in this case)
        :param payload: JWT payload containing user ID
        :return: Pickled tuple of (songs, playlists)
        """
        id = payload['user']
        songs = self.recommender.recommend(id, 5)  # Get 5 song recommendations
        playlists = self.db.get_playlists_by_user(id)
        playlists_list = []
        for dict in playlists:
            pid = dict['id']
            name = dict['name']
            with open(f'playlists/{pid}.jpg', 'rb') as f:
                cover = f.read()
            coverb64 = base64.b64encode(cover)
            d = self.db.get_songs_in_playlist(pid)
            songs_in_p = []
            for song in d:
                album = self.db.get_album(song['album_id'])
                with open(f'covers/{album["id"]}.jpg', 'rb') as f:
                    song_cover = f.read()
                song_coverb64 = base64.b64encode(song_cover)
                s = Song(song['id'], song['name'], song['author'], album['name'], song_coverb64)
                songs_in_p.append(s)
            playlist = Playlist(pid, name, coverb64, songs_in_p)
            playlists_list.append(playlist)
        print('songs in playlist', playlists_list)
        return pickle.dumps((songs, playlists_list))

    def handle_crpl(self, data, payload):
        """
        Create a new playlist for the user.

        :param data: Playlist data in bytes (format: ~name~imageb64)
        :param payload: JWT payload containing user ID
        :return: Response indicating success or failure
        """
        _, name, imageb64 = data.split(b'~')
        user_id = payload['user']
        image_bytes = base64.b64decode(imageb64)
        img_io_bytes = io.BytesIO(image_bytes)
        # Validate image format (JPEG)
        if not (image_bytes.startswith(b'\xff\xd8') and image_bytes.endswith(b'\xff\xd9')):
            return b'NO'
        if len(image_bytes) > 2 * 1024 * 1024:  # 2MB size limit
            return b'NO'
        playlist_id = self.db.create_playlist(user_id, name.decode())
        img = Image.open(img_io_bytes)
        img = img.convert("RGB")
        img_resized = img.resize((64, 64))  # Resize for storage
        output_stream = io.BytesIO()
        img_resized.save(output_stream, format='JPEG')
        resized_image_bytes = output_stream.getvalue()
        with open(f'playlists/{playlist_id}.jpg', 'wb') as f:
            f.write(resized_image_bytes)
        return b'OK' + pickle.dumps(Playlist(playlist_id, name.decode(), base64.b64encode(resized_image_bytes)))

    def handle_astp(self, data, playlist):
        """
        Add a song to a playlist.

        :param data: Data in bytes (format: ~playlist_id~song_id)
        :param payload: JWT payload (unused here but required by handler)
        :return: Response indicating success or failure
        """
        if not data.count(b'~') == 2:
            return b'NO'
        _, playlist_id, song_id = data.split(b'~')
        if self.db.add_song_to_playlist(song_id.decode(), playlist_id.decode()):
            return b'OK'
        return b'NO'

    def handle_dlpl(self, data, payload):
        """
        Delete a playlist if owned by the user.

        :param data: Data in bytes (format: ~playlist_id)
        :param payload: JWT payload containing user ID
        :return: Response indicating success or failure
        """
        if not data.count(b'~') == 1:
            return b'NO'
        _, playlist_id = data.split(b'~')
        if not self.db.is_playlist_by_user(playlist_id.decode(), payload['user']):
            return b'NO'
        if self.db.delete_playlist(playlist_id.decode()) and os.path.exists(f'playlists/{playlist_id.decode()}.jpg'):
            os.remove(f'playlists/{playlist_id.decode()}.jpg')
            print('removed playlist', playlist_id.decode())
            return b'OK'
        return b'NO'

    def handle_usth(self, data, payload):
        """
        Add a playback segment to the user's history and update profile if needed.

        :param data: Data in bytes (format: ~pickled_segment)
        :param payload: JWT payload containing user ID
        :return: None on success, b'NO' on failure (currently commented out)
        """
        pick_segments = b'~'.join(data.split(b'~')[1:])
        seg = pickle.loads(pick_segments)
        user_id = payload['user']
        n = self.db.add_segment_to_user(user_id, seg.song_id, seg.duration, seg.timestamp,
                                        seg.start_time, seg.end_time)
        print(n)
        if n > THRESHOLD:
            self._update_user_profile(user_id)  # Update profile if threshold exceeded
        print('added segment to user', user_id, seg.song_id, seg.timestamp)
        return None

    def handle_ssis(self, data, payload):
        """
        Search for songs based on a query.

        :param data: Data in bytes (format: ~query)
        :param payload: JWT payload (unused here but required by handler)
        :return: Pickled list of matching Song objects
        """
        if not data.count(b'~') == 1:
            return b'NO'
        all_song_names = self.db.get_all_song_names()
        query = data.split(b'~')[1].decode().lower()
        n = 5
        close = difflib.get_close_matches(query, [song[1].lower() for song in all_song_names], n=n, cutoff=0.6)
        matches = [(sid, title) for (sid, title) in all_song_names if title in close]
        if len(matches) < n:
            additions = self.hybrid_search(all_song_names, query, n=n - len(matches), prev=matches)
            matches.extend(additions)
        print('matches', matches)
        songs = []
        for song_id, name in matches:
            song = self.db.get_song(song_id)
            album = self.db.get_album(song['album_id'])
            with open(f'covers/{album["id"]}.jpg', 'rb') as f:
                song_cover = f.read()
            song_coverb64 = base64.b64encode(song_cover)
            s = Song(song['id'], song['name'], song['author'], album['name'], song_coverb64)
            songs.append(s)
        print('songs', songs)
        return pickle.dumps(songs)

    def handle_usss(self, data, payload):
        """
        Search for users based on a query.

        :param data: Data in bytes (format: ~query)
        :param payload: JWT payload (unused here but required by handler)
        :return: Encoded string of matching usernames
        """
        if not data.count(b'~') == 1:
            return b'NO'
        all_users = self.db.get_all_users()
        query = data.split(b'~')[1].decode().lower()
        n = 5
        close = difflib.get_close_matches(query, [user[1].lower() for user in all_users], n=n, cutoff=0.6)
        matches = [(sid, user) for (sid, user) in all_users if user in close]
        if len(matches) < n:
            additions = self.hybrid_search(all_users, query, n=n - len(matches), prev=matches)
            matches.extend(additions)
        users_no_id = [user[1] for user in matches]
        s = ' '.join(users_no_id)
        return s.encode()

    def handle_folw(self, data, payload):
        """
        Follow another user.

        :param data: Data in bytes (format: ~username)
        :param payload: JWT payload containing user ID
        :return: Response indicating success or failure
        """
        if not data.count(b'~') == 1:
            return b'NO'
        _, username = data.split(b'~')
        user_id = self.db.get_id_by_username(username.decode())
        if not user_id or user_id == payload['user']:
            return b'NO'
        if self.db.follow_user(payload['user'], user_id):
            return b'OK'
        return b'NO'

    def handle_unfl(self, data, payload):
        """
        Unfollow another user.

        :param data: Data in bytes (format: ~username)
        :param payload: JWT payload containing user ID
        :return: Response indicating success or failure
        """
        if not data.count(b'~') == 1:
            return b'NO'
        _, username = data.split(b'~')
        user_id = self.db.get_id_by_username(username.decode())
        if not user_id or user_id == payload['user']:
            return b'NO'
        if self.db.unfollow_user(payload['user'], user_id):
            return b'OK'
        return b'NO'

    def handle_flws(self, data, payload):
        """
        Get list of users the current user is following.

        :param data: Data in bytes (format: ~)
        :param payload: JWT payload containing user ID
        :return: Encoded string of followed usernames
        """
        if not data.count(b'~') == 1:
            return b'NO'
        if data.split(b'~')[1] != b'':
            return b'NO'
        print('user', payload['user'])
        following = self.db.get_followings_username(payload['user'])
        return ' '.join(following).encode()

    def handle_prfl(self, data, payload):
        """
        Get social profile data for a user.

        :param data: Data in bytes (format: ~username)
        :param payload: JWT payload (unused here but required by handler)
        :return: Pickled social profile data or error response
        """
        if not data.count(b'~') == 1:
            return b'NO'
        username = data.split(b'~')[1].decode()
        print("username of", username)
        profile = self.db.get_social_profile(username)
        if not profile:
            return b'NO'
        songs = [self.get_song(song) for song in self.db.get_last_10_songs(username)]
        playlists = [self.get_playlist(playlist) for playlist in self.db.get_user_playlist_by_username(username)]
        print('playlists', playlists)
        social_profile = {"profile": profile, "songs": songs, "playlists": playlists}
        return pickle.dumps(social_profile)

    def handle_rsfp(self, data, payload):
        """
        Remove a song from a playlist.

        :param data: Data in bytes (format: ~playlist_id~song_id)
        :param payload: JWT payload (unused here but required by handler)
        :return: Response indicating success or failure
        """
        if not data.count(b'~') == 2:
            return b'NO'
        _, pid, sid = data.split(b'~')
        removed = self.db.remove_song_from_playlist(sid.decode(), pid.decode())
        if removed:
            return b'OK'
        return b'NO'

    def handle_upls(self, data: bytes, payload: dict):
        """
        Upload a new song (admin only).

        :param data: Data in bytes (format: ~name~author~album_id~song_file_b64)
        :param payload: JWT payload containing user ID
        :return: Response indicating success or failure
        """
        _, song_name, author, album_id, song_file_b64 = data.split(b'~')
        if not self.db.album_exists(album_id):
            return b'error, album does not exist'
        tmp_path = f"tmp/{uuid.uuid4()}.ogg"
        try:
            with open(tmp_path, "wb") as f:
                f.write(base64.b64decode(song_file_b64))
            admin_stuff.create_song(self.db, tmp_path, song_name, author, album_id)
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            return b'OK'
        except Exception as e:
            print(f"Error uploading song: {e}")
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            return b'NO'

    def handle_upla(self, data: bytes, payload: dict):
        """
        Upload a new album (admin only).

        :param data: Data in bytes (format: ~name~author~imageb64)
        :param payload: JWT payload containing user ID
        :return: Response indicating success or failure
        """
        _, name, author, imageb64 = data.split(b'~')
        image_bytes = base64.b64decode(imageb64)
        if not (image_bytes.startswith(b'\xff\xd8') and image_bytes.endswith(b'\xff\xd9')):
            return b'NO'
        ext = ".jpg"
        tmp_path = f"tmp/{uuid.uuid4()}{ext}"
        try:
            with open(tmp_path, "wb") as f:
                f.write(image_bytes)
            admin_stuff.create_album(self.db, tmp_path, name, author)
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            return b'OK'
        except Exception as e:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            return b'NO'

    def handle_wrpd(self, data, payload):
        """
        Generate and send a wrapped summary email (admin only).

        :param data: Data in bytes (format: ~user_id~start_date~end_date)
        :param payload: JWT payload (unused here but required by handler)
        :return: Response indicating success or failure
        """
        if not data.count(b'~') == 3:
            return b'NO'
        _, user_id, start_date, end_date = data.split(b'~')
        txt = admin_stuff.generate_wrapped(self.db, user_id.decode(), start_date.decode(), end_date.decode())
        try:
            email = self.db.get_mail_by_id(user_id.decode())
            print(txt)
            mail = Mail('Stopify - Wrapped', txt, email)
            mail.send()
            print('sent wrapped', user_id.decode())
            return b'OK'
        except Exception as e:
            print(f"Error generating wrapped: {e}")
            return b'NO'

    def handle_geta(self, data, payload):
        """
        Get all albums with their cover images (admin only).

        :param data: Data in bytes (format: ~)
        :param payload: JWT payload (unused here but required by handler)
        :return: Pickled list of albums or error response
        """
        if not data.count(b'~') == 1:
            return b'NO'
        try:
            all_albums = self.db.get_albums_ids_names()
            msg = []
            for album_id, name in all_albums:
                with open(f'covers/{album_id}.jpg', 'rb') as f:
                    cover = f.read()
                coverb64 = base64.b64encode(cover)
                msg.append((album_id, name, coverb64))
            return pickle.dumps(msg)
        except Exception as e:
            print(f"Error getting albums: {e}")
            return b'NO'

    def handle_usrs(self, data, payload):
        """
        Get list of all users (admin only).

        :param data: Data in bytes (format: ~)
        :param payload: JWT payload (unused here but required by handler)
        :return: Pickled list of users or error response
        """
        if not data.count(b'~') == 1:
            return b'NO'
        users = self.db.get_all_users()
        return b'OK' + pickle.dumps(users)

    def get_playlist(self, dict):
        """
        Construct a Playlist object from database data.

        :param dict: Dictionary containing playlist data (id, name)
        :return: Playlist object
        """
        print('getting playlist', dict)
        pid = dict['id']
        name = dict['name']
        with open(f'playlists/{pid}.jpg', 'rb') as f:
            cover = f.read()
        coverb64 = base64.b64encode(cover)
        d = self.db.get_songs_in_playlist(pid)
        songs_in_p = []
        for song in d:
            album = self.db.get_album(song['album_id'])
            with open(f'covers/{album["id"]}.jpg', 'rb') as f:
                song_cover = f.read()
            song_coverb64 = base64.b64encode(song_cover)
            s = Song(song['id'], song['name'], song['author'], album['name'], song_coverb64)
            songs_in_p.append(s)
        return Playlist(pid, name, coverb64, songs_in_p)

    def get_song(self, song):
        """
        Construct a Song object from database data.

        :param song: Dictionary containing song data
        :return: Song object
        """
        album = self.db.get_album(song['album_id'])
        with open(f'covers/{album["id"]}.jpg', 'rb') as f:
            song_cover = f.read()
        song_coverb64 = base64.b64encode(song_cover)
        return Song(song['id'], song['name'], song['author'], album['name'], song_coverb64)

    def handle_cmd(self, payload, cmd, data):
        """
        Dispatch client commands to appropriate handlers.

        :param payload: JWT payload containing user ID
        :param cmd: Command identifier
        :param data: Command data
        :return: Response from the handler
        """
        actions = {
            "RECM": self.handle_recm, "CRPL": self.handle_crpl, "ASTP": self.handle_astp,
            "DLPL": self.handle_dlpl, "USTH": self.handle_usth, "SSIS": self.handle_ssis,
            "USSS": self.handle_usss, "FOLW": self.handle_folw, "UNFL": self.handle_unfl,
            "FLWS": self.handle_flws, "PRFL": self.handle_prfl, "RSFP": self.handle_rsfp
        }
        admin_actions = {
            "UPLS": self.handle_upls, "UPLA": self.handle_upla, "GETA": self.handle_geta,
            "WRPD": self.handle_wrpd, "USRS": self.handle_usrs
        }
        if cmd in actions:
            response = actions[cmd](data, payload)
        elif cmd in admin_actions and self.db.is_admin(payload['user']):
            response = admin_actions[cmd](data, payload)
        else:
            response = b'invalid command'
        return response

    def update_token(self, client_socket, shared_key):
        """
        Update a user's token upon request.

        :param client_socket: The client's socket
        :param shared_key: The encryption key
        :return: New token or error response
        """
        cmd, data = self.recv_msg(client_socket, shared_key)
        if cmd != 'TOKN' or not data.count(b'~') == 1:
            return b'NO'
        username, password = data.decode().split('~')
        id, status = self.db.login_user(username, password)
        token = generate_token(id) if status != '0' else '###'
        return token.encode()

    def handle_client(self, client_socket, client_id, addr):
        """
        Handle communication with a connected client.

        :param client_socket: The client's socket
        :param client_id: Unique identifier for the client
        :param addr: Client's address
        """
        cryp = CryptoManager()
        # Send public key to establish shared secret
        msg = protocol.create_msg("SHKY", base64.b64encode(str(cryp.public_key).encode()))
        client_socket.send(msg)
        cmd, data = protocol.get_msg(client_socket)
        if cmd != 'SHKY':
            return
        pub_b = int(base64.b64decode(data).decode())
        shared_key = cryp.shared_secret(pub_b)
        shared_key = cryp.hash_secret(shared_key)
        print(shared_key, '_' * 100)

        # Initial login/registration phase
        while True:
            cmd, data = self.recv_msg(client_socket, shared_key)
            if cmd == 'REGI':
                status, response = self.handle_register(data, client_socket)
            elif cmd == 'LOGI':
                status, response = self.handle_login(data, client_socket)
            else:
                status, response = False, b'invalid command'
            self.send_msg(client_socket, cmd, response, shared_key)
            print("status", status)
            if status:
                break

        print('started main loop')
        # Main command handling loop
        while True:
            cmd, data = self.recv_msg(client_socket, shared_key)
            if not self.client_users[client_socket].connected or cmd == 'EXIT':
                print('client disconnected')
                break
            token = data.split(b'~')[0].decode()
            payload = verify_token(token)
            if payload:
                data = data[1:]
                if self.client_users[client_socket].id != payload['user']:
                    print('user id mismatch')
                    break
                if not self.client_users[client_socket].verified and self.db.is_verified(payload['user']):
                    self.client_users[client_socket].verified = True
                if self.client_users[client_socket].verified:
                    response = self.handle_cmd(payload, cmd, data)
                    print('response:', response)
                    if response is not None:
                        try:
                            msg = protocol.create_msg(cmd, response, shared_key)
                            client_socket.send(msg)
                        except ssl.SSLZeroReturnError:
                            print(f"Client {client_id} disconnected unexpectedly.")
                            break
                else:
                    print('user not verified')
                    self.send_msg(client_socket, 'VERF', b'not verified', shared_key)
            else:
                print('invalid token')
                self.send_msg(client_socket, 'TOKN', b'invalid token', shared_key)
                token = self.update_token(client_socket, shared_key)
                self.send_msg(client_socket, 'TOKN', token, shared_key)
                print('sent new token', token)

        # Clean up connection
        try:
            client_socket.unwrap()  # Respond to client's "close notify"
        except Exception as e:
            print(f"Error during unwrap: {e}")
        finally:
            client_socket.close()
            del self.client_users[client_socket]
            print('client users', self.client_users)
            self.threads.remove(threading.current_thread())

    def run(self):
        """
        Start the server and listen for incoming connections.
        """
        # Set up SSL context for secure connections
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(certfile='webroot/cert.pem', keyfile='webroot/key.pem')

        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.bind((self.host, self.port))
        server_socket.listen(0)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        print("Server is up and running")

        i = 1
        while True:
            print('Main thread: before accepting ...')
            try:
                plain_socket, addr = server_socket.accept()
                client_socket = context.wrap_socket(plain_socket, server_side=True, do_handshake_on_connect=True)
                t = threading.Thread(target=self.handle_client, args=(client_socket, str(i).zfill(4), addr))
                t.start()
                self.threads.append(t)
                i += 1
            except (ssl.SSLError, ConnectionResetError) as e:
                print('failed to connect with ssl: ', e)

        print("Closing server")
        server_socket.close()

if __name__ == '__main__':
    server = StopifyServer()
    server.run()