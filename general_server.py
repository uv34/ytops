import datetime
import socket
import threading
import jwt
import protocol
import random
from sys import exit
import mysql_helper

client_users = {}  # socket: user
db = mysql_helper.DBController(host="127.0.0.1", user="stopify", password="stop123", database="mydb")

SECRET_KEY = 'very‑strong‑secret-key'

class User:  # the way the server is saving the users
    def __init__(self, id, username, status):
        self.id = id
        self.username = username
        self.status = status


def log(direction, client_id, message):  # log the recv and send messages
    print(f'{direction} {client_id}: {message}')


def check_creds_regi(data):  # check if the data is valid
    return data.count(b'~') == 2 and len(data) > 0


def check_creds_logi(data):  # check if the data is valid
    return data.count(b'~') == 1 and len(data) > 0


def login_user(username, hashed_password):  # login the user
    id, status = db.login_user(username, hashed_password)
    return id, status


def register_user(username, email, hashed_password):  # register the user
    id, status = db.add_user(username, hashed_password, email)
    return id, status


def handle_login(data, client_socket):
    username, hashed_password = data.decode().split('~')

    if not check_creds_logi(data):
        return False, b'contains invalid characters'
    id, status = login_user(username, hashed_password)
    if status != '0':
        client_users[client_socket] = User(id, username, status)
        token = generate_token(id)
        print(f'token generated: {token}')
        return True, b'login successful~' + token.encode()

    return False, b'password or username incorrect~###'


def handle_register(data, client_socket):
    username, email, hashed_password = data.decode().split('~')

    if not check_creds_regi(data):
        return False, b'contains invalid characters~###'
    id, status = register_user(username, email, hashed_password)
    if status != '0':
        client_users[client_socket] = User(id, username, status)
        token = generate_token(id)
        return True, b'login successful~' + token.encode()
    return False, b'username already exists~###'


def handle_cmd(client_socket, cmd, data):  # handle cmd
    actions = {}  # cmd : action
    credential_actions = {}  # cmd : action, only for register and login
    if cmd in actions:
        response = actions[cmd](data)
    else:
        response = False, b'invalid command'
    return response


def send_msg(client_socket, cmd, data):  # send the message to the client
    msg = protocol.create_msg(cmd, data)
    client_socket.send(msg)
    log('Sent', client_socket, msg)


def generate_token(user_id):
    payload = {
        "sub": user_id,
        "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=2)
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")

def verify_token(token):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        return payload["sub"]
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None


def recv_msg(client_socket):  # send the message to the client
    cmd, data = protocol.get_msg(client_socket)
    log('Received', client_socket, f'{cmd} {data}')
    return cmd, data


def handle_client(client_socket, client_id, addr):
    global threads
    while True:
        cmd, data = recv_msg(client_socket)
        if cmd == 'REGI':
            status, response = handle_register(data, client_socket)
        elif cmd == 'LOGI':
            status, response = handle_login(data, client_socket)
        else:
            status, response = False, b'invalid command'

        send_msg(client_socket, cmd, response)

        if status:
            break

    while True:
        try:
            cmd, data = recv_msg(client_socket)
            handle_cmd(client_socket, cmd, data)
        except Exception as e:
            print(f'Error: {e}')
            break

    threads.remove(threading.current_thread())


def main():
    communication()  # with fortnite


def communication():
    global threads
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.bind(("0.0.0.0", 5001))
    server_socket.listen(0)
    print("Server is up and running")
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    i = 1
    while True:
        print('Main thread: before accepting ...')
        client_socket, addr = server_socket.accept()
        t = threading.Thread(target=handle_client, args=(client_socket, str(i).zfill(4), addr))
        t.start()
        i += 1
        threads.append(t)
        """if i > 4:
            print('Main thread: going down for maintenance')
            break"""

    print("Closing server")

    server_socket.close()


if __name__ == '__main__':
    threads = []
    main()
