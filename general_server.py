import datetime
import socket
import threading
import time
import base64
import pickle
import jwt
import protocol
import random
from sys import exit
import mysql_helper
from song import Song

SECRET_KEY = 'very‑strong‑secret-key'


def generate_token(user_id):
    payload = {"user": user_id}
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")


def verify_token(token):
    try:
        print('checking token', token)
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        return payload
    except Exception as e:
        print('invalid token')
        return False

class User:
    def __init__(self, id, username, status):
        self.id = id
        self.username = username
        self.status = status


class StopifyServer:
    def __init__(self, host="0.0.0.0", port=5001):
        self.host = host
        self.port = port
        self.client_users = {}
        self.threads = []
        self.db = mysql_helper.DBController(
            host="192.168.1.20", user="stopify", password="stop123", database="mydb"
        )

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

    def send_msg(self, client_socket, cmd, data):
        msg = protocol.create_msg(cmd, data)
        client_socket.send(msg)
        self.log('Sent', client_socket, msg)

    def recv_msg(self, client_socket):
        cmd, data = protocol.get_msg(client_socket)
        self.log('Received', client_socket, f'{cmd} {data}')
        return cmd, data

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
        songs = []
        for i in range(1, 6):
            print(i)
            song = self.db.get_song(str(i))
            album = self.db.get_album(song['album_id'])
            with open(f'covers/{album["cover"]}', 'rb') as f:
                cover_data = f.read()
            cover_b64 = base64.b64encode(cover_data).decode('utf-8')
            songs.append(Song(i, song['name'], song['author'], album['name'], cover_b64))
        return pickle.dumps(songs)

    def handle_cmd(self, payload, cmd, data):
        actions = {"RECM": self.handle_recm}
        if cmd in actions:
            response = actions[cmd](data, payload)
        else:
            response = False, b'invalid command'
        print(pickle.loads(response))
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
            try:
                cmd, data = self.recv_msg(client_socket)
                token = data.split(b'~')[0]
                payload = verify_token(token)
                if payload:
                    data = data[1:]
                    response = self.handle_cmd(payload, cmd, data)
                    msg = protocol.create_msg(cmd, response)
                    client_socket.send(msg)
            except Exception as e:
                print(f'Error: {e}')
                break

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
