import socket

COMMANDS = ['PGNM', 'RQST', 'STOP', 'SCNF', 'PAGE', 'CRPL', 'ASTP']
LENGTH_HEADER = 6
CMD_HEADER = 4

def check_cmd(cmd):
    return cmd in COMMANDS

def create_msg(cmd: str, data: bytes):
    """
    Creates a message that includes:
      - LENGTH_HEADER (5 bytes, decimal string, zero-padded)
      - CMD_HEADER (4 bytes)
      - data (length bytes)
    """
    length_str = str(len(data)).zfill(LENGTH_HEADER)
    msg = length_str.encode() + cmd.encode() + data
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

def get_msg(other_socket):
    """
    Reads a message from the socket:
      1) Read 5 bytes for length.
      2) Read 4 bytes for command.
      3) Read `length` bytes for data.
    Returns (cmd, data) or ("ERR1", b"<error>") if something goes wrong.
    """
    try:
        # 1) Read length (5 bytes)
        length_bytes = recv_exact(other_socket, LENGTH_HEADER)
        if len(length_bytes) < LENGTH_HEADER:
            return ("ERR1", b"Failed to read length header")

        length = int(length_bytes.decode())

        # 2) Read command (4 bytes)
        cmd_bytes = recv_exact(other_socket, CMD_HEADER)
        if len(cmd_bytes) < CMD_HEADER:
            return ("ERR1", b"Failed to read command header")
        cmd = cmd_bytes.decode()

        # 3) Read data (length bytes)
        data = recv_exact(other_socket, length)
        if len(data) < length:
            return ("ERR1", b"Incomplete data read")

        return cmd, data

    except ValueError as e:
        return ("ERR1", f"ValueError: {e}".encode())
    except Exception as e:
        return ("ERR1", f"Exception: {e}".encode())
