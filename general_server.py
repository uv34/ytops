import base64
import io
import os
import pickle
import socket
import threading
import time
import difflib
import secrets
from datetime import datetime, timedelta
import ssl

import jwt
from PIL import Image

import mysql_helper
import protocol
from song import Song, Playlist, PlaybackSegment
import recommendations
from encryption import CryptoManager
from MailManager import Mail

SECRET_KEY = 'very‑strong‑secret-key'
THRESHOLD = 5

def generate_token(user_id):
    payload = {"user": user_id}
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")


def verify_token(token):
    try:
        print('checking token', token)
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        print('checked token', payload)
        return payload
    except Exception as e:
        print('invalid token')
        return False


class User:
    def __init__(self, id, username, status, verified):
        self.id = id
        self.username = username
        self.status = status
        self.verified = verified
        self.connected = True


class StopifyServer:
    def __init__(self, host="0.0.0.0", port=5001):
        self.host = host
        self.port = port
        self.client_users = {}
        self.threads = []
        self.db = mysql_helper.DBController(
            host="192.168.1.20", user="stopify", password="stop123", database="mydb", autocommit=True
        )
        self.recommender = recommendations.Recommender(self.db)

    def log(self, direction, client_id, message):
        print(f'{direction} {client_id}: {message}')

    def check_creds_regi(self, data):
        return data.count(b'~') == 2 and len(data) > 0

    def check_creds_logi(self, data):
        return data.count(b'~') == 1 and len(data) > 0

    def login_user(self, username, hashed_password):
        id, status = self.db.login_user(username, hashed_password)
        return id, status

    def register_user(self, username, email, hashed_password, token, expiry):
        id, status = self.db.add_user(username, hashed_password, email, token, expiry)
        return id, status

    def _update_user_profile(self, user_id):
        segments_db = self.db.get_unused_segments(user_id, THRESHOLD)
        print('segments', segments_db)
        if not segments_db:
            print(f"No segments found for user {user_id}")
            return
        segments = [PlaybackSegment(seg['songs_id'], seg['start_time'], seg['end_time'],
                    seg['duration'], seg['time']) for seg in segments_db]
        print('updating', user_id)
        updated_profile, combined_weight, current_time = self.recommender.update_user_profile(user_id, segments)
        print('updated profile', updated_profile, combined_weight, current_time)
        self.db.update_user_profile(user_id, updated_profile, combined_weight, current_time)
        print('updated user profile', user_id)
        self.db.mark_segments_used(user_id, THRESHOLD)

    def hybrid_search(self, songs, query, n=10, cutoff=0.6, prev=[]):
        q = query.lower().strip()

        # first check for enough results no fuzzy
        results = [(sid, title) for (sid, title) in songs if title.lower().startswith(q) and (sid,title) not in prev]
        if len(results) >= n:
            return results[:n]

        prefix_fuzzy = []
        for sid, title in songs:
            if (sid, title) in results:
                continue
            low = title.lower()
            slice_ = low[:len(q)]
            score = difflib.SequenceMatcher(None, q, slice_).ratio()
            if score >= cutoff and (sid, title) not in prev:
                print((sid, title), 'not in', prev)
                prefix_fuzzy.append((sid, title))
        results.extend(prefix_fuzzy)
        return results[:n]

    def send_msg(self, client_socket, cmd, data, shared_key):
        msg = protocol.create_msg(cmd, data, shared_key)
        client_socket.send(msg)
        self.log('Sent', client_socket, msg)

    def recv_msg(self, client_socket, shared_key):
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
        if not self.check_creds_logi(data):
            return False, b'contains invalid characters'
        username, hashed_password = data.decode().split('~')
        id, status = self.login_user(username, hashed_password)
        if status != '0':
            self.client_users[client_socket] = User(id, username, status, self.db.is_verified(id))
            token = generate_token(id)
            print(f'token generated: {token}')
            return True, b'login successful~' + token.encode()
        return False, b'password or username incorrect~###'

    def handle_register(self, data, client_socket):
        if not self.check_creds_regi(data):
            return False, b'contains invalid characters~###'
        username, email, hashed_password = data.decode().split('~')
        token = secrets.token_urlsafe(32)
        expiry = datetime.utcnow() + timedelta(days=1)
        id, status = self.register_user(username, email, hashed_password, token, expiry)
        if status != '0':
            self.client_users[client_socket] = User(id, username, status, False)
            m = Mail('Stopify - Email Verification', """Welcome to Stopify! To activate your account, please click the link below:
            https://localhost/verify-email?token=""" + token + """
            
            This link expires in 24 hours. If you didn’t sign up, just ignore this message.
            
            Thanks,
            The Stopify Team""", email)
            m.send()
            token = generate_token(id)
            return True, b'login successful~' + token.encode()
        return False, b'username already exists~###'

    def handle_recm(self, data, payload):
        id = payload['user']
        songs = self.recommender.recommend(id, 5)
        """for i in range(1, 6):
            print(i)
            song = self.db.get_song(str(i))
            album = self.db.get_album(song['album_id'])
            with open(f'covers/{album["cover"]}', 'rb') as f:
                cover_data = f.read()
            cover_b64 = base64.b64encode(cover_data)
            songs.append(Song(i, song['name'], song['author'], album['name'], cover_b64))"""

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
                cover_file = f'{album["id"]}.jpg'
                with open(f'covers/{cover_file}', 'rb') as f:
                    song_cover = f.read()
                song_coverb64 = base64.b64encode(song_cover)
                s = Song(song['id'], song['name'], song['author'], album['name'],
                         song_coverb64)  # mabye change to the songs real cover
                songs_in_p.append(s)
            playlist = Playlist(pid, name, coverb64, songs_in_p)
            playlists_list.append(playlist)
        print('songs in playlist', playlists_list)

        return pickle.dumps((songs, playlists_list))

    def handle_crpl(self, data, payload):
        _, name, imageb64 = data.split(b'~')
        user_id = payload['user']
        image_bytes = base64.b64decode(imageb64)
        img_io_bytes = io.BytesIO(image_bytes)
        if not (image_bytes.startswith(b'\xff\xd8') and image_bytes.endswith(b'\xff\xd9')):
            return b'NOT Valid jpg'
        playlist_id = self.db.create_playlist(user_id, name.decode())
        img = Image.open(img_io_bytes)
        img_resized = img.resize((64, 64))

        output_stream = io.BytesIO()
        img_resized.save(output_stream, format='JPEG')
        resized_image_bytes = output_stream.getvalue()
        with open(f'playlists/{playlist_id}.jpg', 'wb') as f:
            f.write(resized_image_bytes)
        return b'OK' + pickle.dumps(Playlist(playlist_id, name.decode(), base64.b64encode(resized_image_bytes)))

    def handle_astp(self, data, payload):
        if not data.count(b'~') == 2:
            return b'NO'
        _, playlist_id, song_id = data.split(b'~')
        if self.db.add_song_to_playlist(song_id.decode(), playlist_id.decode()):
            return b'OK'
        return b'NO'

    def handle_dlpl(self, data, payload):
        if not data.count(b'~') == 1:
            return b'NO'
        if self.db.is_playlist_by_user(playlist_id.decode(), payload['user']):
            return b'NO'
        _, playlist_id = data.split(b'~')
        if self.db.delete_playlist(playlist_id.decode()) and os.path.exists(f'playlists/{playlist_id.decode()}.jpg'):
            os.remove(f'playlists/{playlist_id.decode()}.jpg')
            print('removed playlist', playlist_id.decode())
            return b'OK'
        return b'NO'

    def handle_usth(self, data, payload):
        pick_segments = b'~'.join(data.split(b'~')[1:])
        seg = pickle.loads(pick_segments)
        user_id = payload['user']
        # try:
        n = self.db.add_segment_to_user(user_id, seg.song_id, seg.duration, seg.timestamp
                                        , seg.start_time, seg.end_time)
        print(n)
        if n > THRESHOLD:
            self._update_user_profile(user_id)
        print('added segment to user', user_id, seg.song_id, seg.timestamp)
        """except Exception as e:
            print(f"Error adding segment to user: {e}")
            return b'NO'"""
        return None

    def handle_ssis(self, data, payload):
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
            cover_file = f'{album["id"]}.jpg'
            with open(f'covers/{cover_file}', 'rb') as f:
                song_cover = f.read()
            song_coverb64 = base64.b64encode(song_cover)
            s = Song(song['id'], song['name'], song['author'], album['name'],
                     song_coverb64)
            songs.append(s)

        print('songs', songs)
        return pickle.dumps(songs)

    def handle_usss(self, data, payload):
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
        if not data.count(b'~') == 1:
            return b'NO'
        if data.split(b'~')[1] != b'':
            return b'NO'
        print('user', payload['user'])
        following = self.db.get_followings_username(payload['user'])
        return ' '.join(following).encode()

    def handle_prfl(self, data, payload):
        if not data.count(b'~') == 1:
            return b'NO'
        username = data.split(b'~')[1]
        print("username of", username)
        profile = self.db.get_social_profile(username)
        if not profile:
            return b'NO'
        songs = []
        for song in self.db.get_last_10_songs(username):
            songs.append(self.get_song(song))
        playlists = []
        not_goof_playlists = self.db.get_user_playlist_by_username(username)
        print('playlists', not_goof_playlists)
        for playlist in not_goof_playlists:
            playlists.append(self.get_playlist(playlist))
        social_profile = {"profile": profile, "songs": songs, "playlists": playlists}
        return pickle.dumps(social_profile)

    def handle_rsfp(self, data, payload):
        if not data.count(b'~') == 2:
            return b'NO'
        _, pid, sid = data.split(b'~')
        removed = self.db.remove_song_from_playlist(sid.decode(), pid.decode())
        if removed:
            return b'OK'
        return b'NO'

    def get_playlist(self,dict):
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
            cover_file = f'{album["id"]}.jpg'
            with open(f'covers/{cover_file}', 'rb') as f:
                song_cover = f.read()
            song_coverb64 = base64.b64encode(song_cover)
            s = Song(song['id'], song['name'], song['author'], album['name'],
                     song_coverb64)  # mabye change to the songs real cover
            songs_in_p.append(s)
        playlist = Playlist(pid, name, coverb64, songs_in_p)
        return playlist

    def get_song(self, song):
        album = self.db.get_album(song['album_id'])
        cover_file = f'{album["id"]}.jpg'
        with open(f'covers/{cover_file}', 'rb') as f:
            song_cover = f.read()
        song_coverb64 = base64.b64encode(song_cover)
        s = Song(song['id'], song['name'], song['author'], album['name'],
                 song_coverb64)
        return s

    def handle_cmd(self, payload, cmd, data):
        actions = {"RECM": self.handle_recm, "CRPL": self.handle_crpl, "ASTP": self.handle_astp,
                   "DLPL": self.handle_dlpl, "USTH": self.handle_usth, "SSIS": self.handle_ssis,
                   "USSS": self.handle_usss, "FOLW": self.handle_folw, "UNFL": self.handle_unfl,
                   "FLWS": self.handle_flws, "PRFL": self.handle_prfl, "RSFP": self.handle_rsfp}
        if cmd in actions:
            response = actions[cmd](data, payload)
        else:
            response = b'invalid command'
        return response

    def handle_client(self, client_socket, client_id, addr):
        cryp = CryptoManager()
        msg = protocol.create_msg("SHKY", base64.b64encode(str(cryp.public_key).encode()))
        client_socket.send(msg)
        cmd, data = protocol.get_msg(client_socket)
        if cmd != 'SHKY':
            return
        pub_b = int(base64.b64decode(data).decode())
        shared_key = cryp.shared_secret(pub_b)
        shared_key = cryp.hash_secret(shared_key)
        print(shared_key, '_' * 100)

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
        while True:
            #  try:
            cmd, data = self.recv_msg(client_socket, shared_key)
            if not self.client_users[client_socket].connected:
                print('client disconnected')
                break
            if cmd == 'EXIT':
                print('client disconnected')
                break
            token = data.split(b'~')[0]
            payload = verify_token(token)

            if payload:
                data = data[1:]
                if self.client_users[client_socket].id != payload['user']:
                    print('user id mismatch')
                    break
                if not self.client_users[client_socket].verified:
                    if self.db.is_verified(payload['user']):
                        self.client_users[client_socket].verified = True
                if self.client_users[client_socket].verified:
                    response = self.handle_cmd(payload, cmd, data)
                    print('response:', response)
                    if response is not None:
                        msg = protocol.create_msg(cmd, response, shared_key)
                        client_socket.send(msg)
                else:
                    print('user not verified')
                    self.db.print_users()
                    self.send_msg(client_socket, 'ERR ', b'not verified', shared_key)
            else:
                print('invalid token')
                self.send_msg(client_socket, 'ERR ', b'invalid token', shared_key)
            """except Exception as e:
                print(f'Error: {e}')
                break"""
        del self.client_users[client_socket]
        self.threads.remove(threading.current_thread())

    def run(self):
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(certfile='webroot/cert.pem',
                                keyfile='webroot/key.pem')

        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.bind((self.host, self.port))
        server_socket.listen(0)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        print("Server is up and running")

        i = 1
        while True:
            print('Main thread: before accepting ...')
            plain_socket, addr = server_socket.accept()
            client_socket = context.wrap_socket(plain_socket, server_side=True, do_handshake_on_connect=True)

            t = threading.Thread(target=self.handle_client, args=(client_socket, str(i).zfill(4), addr))
            t.start()
            self.threads.append(t)
            i += 1

        print("Closing server")
        server_socket.close()


if __name__ == '__main__':
    server = StopifyServer()
    server.run()
