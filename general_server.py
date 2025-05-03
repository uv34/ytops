import base64
import io
import os
import pickle
import socket
import threading
import time
import difflib

import jwt
from PIL import Image

import mysql_helper
import protocol
from song import Song, Playlist, PlaybackSegment
import recommendations

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
    def __init__(self, id, username, status):
        self.id = id
        self.username = username
        self.status = status
        self.connected = True


class StopifyServer:
    def __init__(self, host="0.0.0.0", port=5001):
        self.host = host
        self.port = port
        self.client_users = {}
        self.threads = []
        self.db = mysql_helper.DBController(
            host="192.168.1.20", user="stopify", password="stop123", database="mydb"
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

    def register_user(self, username, email, hashed_password):
        id, status = self.db.add_user(username, hashed_password, email)
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

    def send_msg(self, client_socket, cmd, data):
        msg = protocol.create_msg(cmd, data)
        client_socket.send(msg)
        self.log('Sent', client_socket, msg)

    def recv_msg(self, client_socket):
        try:
            cmd, data = protocol.get_msg(client_socket)
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
            self.client_users[client_socket] = User(id, username, status)
            token = generate_token(id)
            print(f'token generated: {token}')
            return True, b'login successful~' + token.encode()
        return False, b'password or username incorrect~###'

    def handle_register(self, data, client_socket):
        if not self.check_creds_regi(data):
            return False, b'contains invalid characters~###'
        username, email, hashed_password = data.decode().split('~')
        id, status = self.register_user(username, email, hashed_password)
        if status != '0':
            self.client_users[client_socket] = User(id, username, status)
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
        if not user_id:
            return b'NO'
        if self.db.follow_user(payload['user'], user_id):
            return b'OK'
        return b'NO'

    def handle_unfl(self, data, payload):
        if not data.count(b'~') == 1:
            return b'NO'
        _, username = data.split(b'~')
        user_id = self.db.get_id_by_username(username.decode())
        if not user_id:
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

    def handle_cmd(self, payload, cmd, data):
        actions = {"RECM": self.handle_recm, "CRPL": self.handle_crpl, "ASTP": self.handle_astp,
                   "DLPL": self.handle_dlpl, "USTH": self.handle_usth, "SSIS": self.handle_ssis,
                   "USSS": self.handle_usss, "FOLW": self.handle_folw, "UNFL": self.handle_unfl,
                   "FLWS": self.handle_flws}
        if cmd in actions:
            response = actions[cmd](data, payload)
        else:
            response = b'invalid command'
        return response

    def handle_client(self, client_socket, client_id, addr):
        while True:
            cmd, data = self.recv_msg(client_socket)
            if cmd == 'REGI':
                status, response = self.handle_register(data, client_socket)
            elif cmd == 'LOGI':
                status, response = self.handle_login(data, client_socket)
            else:
                status, response = False, b'invalid command'

            self.send_msg(client_socket, cmd, response)
            print("status", status)
            if status:
                break

        print('started main loop')
        while True:
            #  try:
            cmd, data = self.recv_msg(client_socket)
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
                response = self.handle_cmd(payload, cmd, data)
                print('response:', response)
                if response is not None:
                    msg = protocol.create_msg(cmd, response)
                    client_socket.send(msg)
            """except Exception as e:
                print(f'Error: {e}')
                break"""
        del self.client_users[client_socket]
        self.threads.remove(threading.current_thread())

    def run(self):
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.bind((self.host, self.port))
        server_socket.listen(0)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        print("Server is up and running")

        i = 1
        while True:
            print('Main thread: before accepting ...')
            client_socket, addr = server_socket.accept()
            t = threading.Thread(target=self.handle_client, args=(client_socket, str(i).zfill(4), addr))
            t.start()
            self.threads.append(t)
            i += 1

        print("Closing server")
        server_socket.close()


if __name__ == '__main__':
    server = StopifyServer()
    server.run()
