import socket
from encryption import CryptoManager

COMMANDS = ['PGNM', 'RQST', 'STOP', 'SCNF', 'PAGE', 'CRPL', 'ASTP', 'USTH']
LENGTH_O_LENGTH_HEADER = 4
CMD_HEADER = 4

def check_cmd(cmd):
    return cmd in COMMANDS

def create_msg(cmd: str, data: bytes, key=None):
    """
    Creates a message that includes:
      - LENGTH_HEADER (5 bytes, decimal string, zero-padded)
      - CMD_HEADER (4 bytes)
      - data (length bytes)
    """
    if key:
        part = CryptoManager.encrypt(key,cmd.encode() + data)
    else:
        part = cmd.encode() + data
    length_str = str(len(part))
    length_of_length = str(len(length_str)).zfill(LENGTH_O_LENGTH_HEADER)
    msg = length_of_length.encode() + length_str.encode() + part
    return msg

def recv_exact(sock, num_bytes):
    """
    Repeatedly calls recv() until exactly num_bytes have been read
    or the connection is lost.
    """
    chunks = []
    total_received = 0
    while total_received < num_bytes:
        chunk = sock.recv(num_bytes - total_received)
        if not chunk:
            # Connection closed or lost mid-read
            return b''
        chunks.append(chunk)
        total_received += len(chunk)
    return b''.join(chunks)

def get_msg(other_socket, key=None):
    """
    Reads a message from the socket:
      1) Read 5 bytes for length.
      2) Read 4 bytes for command.
      3) Read `length` bytes for data.
    Returns (cmd, data) or ("ERR1", b"<error>") if something goes wrong.
    """
    try:
        # 1) Read length (6 bytes)
        length_of_length_bytes = recv_exact(other_socket, LENGTH_O_LENGTH_HEADER)
        if len(length_of_length_bytes) < LENGTH_O_LENGTH_HEADER:
            return ("ERR1", b"Failed to read length header")

        length_of_length = int(length_of_length_bytes.decode())

        length = recv_exact(other_socket, length_of_length)
        if len(length) < length_of_length:
            return ("ERR1", b"Incomplete length read")
        length = int(length.decode())
        data = recv_exact(other_socket, length)
        if len(data) < length:
            return ("ERR1", b"Incomplete data read")

        if key:
            data = CryptoManager.decrypt(key, data)
        cmd = data[:CMD_HEADER].decode()
        data = data[CMD_HEADER:]
        return cmd, data

    except ValueError as e:
        return ("ERR1", f"ValueError: {e}".encode())
