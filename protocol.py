import socket  # Used for creating and managing network sockets
from encryption import CryptoManager  # Custom module for encryption operations

# List of valid commands that can be sent or received
COMMANDS = ['PGNM', 'RQST', 'STOP', 'SCNF', 'PAGE', 'CRPL', 'ASTP', 'USTH']

# Constants for message formatting
LENGTH_O_LENGTH_HEADER = 4  # Number of bytes for the length of the length header
CMD_HEADER = 4  # Number of bytes for the command header


def check_cmd(cmd):
    """
    Check if the given command is valid.

    :param cmd: The command to check (string).
    :return: True if the command is in the COMMANDS list, False otherwise.
    """
    return cmd in COMMANDS


def create_msg(cmd: str, data: bytes, key=None):
    """
    Create a formatted message for sending over the socket.

    The message format includes:
    - A fixed-length header (LENGTH_O_LENGTH_HEADER bytes) indicating the length of the length header.
    - The length of the data (cmd + actual data) as a string.
    - The command (cmd) and the actual data.

    If a key is provided, the command and data are encrypted before formatting.

    :param cmd: The command to include in the message (string).
    :param data: The data to include in the message (bytes).
    :param key: Optional encryption key (default is None).
    :return: The formatted message as bytes.
    """
    if key:
        # Encrypt the command and data if a key is provided
        part = CryptoManager.encrypt(key, cmd.encode() + data)
    else:
        # Use the command and data as is if no encryption is required
        part = cmd.encode() + data
    # Calculate the length of the part (cmd + data)
    length_str = str(len(part))
    # Pad the length of the length string to LENGTH_O_LENGTH_HEADER bytes
    length_of_length = str(len(length_str)).zfill(LENGTH_O_LENGTH_HEADER)
    # Construct the message: length_of_length + length_str + part
    msg = length_of_length.encode() + length_str.encode() + part
    return msg


def recv_exact(sock, num_bytes):
    """
    Receive exactly num_bytes from the socket.

    This function ensures that the specified number of bytes is received by repeatedly
    calling recv() until the total is reached or the connection is closed.

    :param sock: The socket object to receive data from.
    :param num_bytes: The exact number of bytes to receive (integer).
    :return: The received bytes, or b'' if the connection is closed prematurely.
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
    Read and parse a message from the socket.

    The function processes the message in the following steps:
    1. Reads the length of the length header (LENGTH_O_LENGTH_HEADER bytes).
    2. Reads the length of the data (variable bytes based on step 1).
    3. Reads the full data (cmd + actual data) based on the length from step 2.
    4. Decrypts the data if a key is provided.
    5. Extracts the command (first CMD_HEADER bytes) and the remaining data.

    :param other_socket: The socket object to read the message from.
    :param key: Optional decryption key (default is None).
    :return: A tuple (cmd, data) if successful, or ("ERR1", error_message) on failure.
    """
    try:
        # Step 1: Read the length of the length header
        length_of_length_bytes = recv_exact(other_socket, LENGTH_O_LENGTH_HEADER)
        if len(length_of_length_bytes) < LENGTH_O_LENGTH_HEADER:
            return "ERR1", b"Failed to read length header"

        # Convert the length of the length header to an integer
        length_of_length = int(length_of_length_bytes.decode())

        # Step 2: Read the length of the data
        length_bytes = recv_exact(other_socket, length_of_length)
        if len(length_bytes) < length_of_length:
            return "ERR1", b"Incomplete length read"
        length = int(length_bytes.decode())

        # Step 3: Read the data (cmd + actual data)
        data = recv_exact(other_socket, length)
        if len(data) < length:
            return "ERR1", b"Incomplete data read"

        # Step 4: Decrypt the data if a key is provided
        if key:
            data = CryptoManager.decrypt(key, data)

        # Step 5: Extract the command and the actual data
        cmd = data[:CMD_HEADER].decode()
        data = data[CMD_HEADER:]
        return cmd, data

    except ValueError as e:
        # Handle errors from invalid integer conversion (e.g., non-numeric length)
        return "ERR1", f"ValueError: {e}".encode()
    except Exception as e:
        # Handle any other unexpected errors during message parsing
        return "ERR1", f"Unexpected error: {e}".encode()
