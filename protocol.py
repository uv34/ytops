import socket

COMMANDS = ['PGNM', 'RQST', 'STOP', 'SCNF', 'PAGE']
LENGTH_HEADER = 5
CMD_HEADER = 4


def check_cmd(cmd):
    return cmd in COMMANDS


def create_msg(cmd: str, data: bytes):
    print(data)
    length = str(len(data)).zfill(LENGTH_HEADER)
    msg = length.encode() + cmd.encode() + data
    if cmd != "PAGE":
        print(msg)
    return msg


def get_msg(other_socket):
    try:
        length = other_socket.recv(LENGTH_HEADER)
        length = int(length.decode())
        cmd = other_socket.recv(CMD_HEADER).decode()
        data = other_socket.recv(length)
        return cmd, data
    except ValueError as e:
        return "ERR1", f"error recieving the information: {e}".encode()
