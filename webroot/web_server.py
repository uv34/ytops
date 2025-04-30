import socket
import threading
import os
import mimetypes

HOST = '0.0.0.0'  # Listen on all interfaces
PORT = 80       # Port to listen on
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
print('BASE_DIR:', BASE_DIR)


def handle_client(client_conn, client_addr):
    with client_conn:
        request = client_conn.recv(1024).decode('utf-8', errors='ignore')
        if not request:
            return
        print(f"Received request from {client_addr}: {request}")

        # Parse HTTP request line
        request_line = request.splitlines()[0]
        parts = request_line.split()
        if len(parts) < 2:
            return
        method, path = parts[0], parts[1]

        # Only handle GET requests
        if method != 'GET':
            response = (
                'HTTP/1.1 405 Method Not Allowed\r\n'
                'Connection: close\r\n\r\n'
            )
            client_conn.sendall(response.encode('utf-8'))
            return

        # Default to index.html for root
        if path == '/':
            path = '/index.html'

        # Construct full file path
        file_path = os.path.join(BASE_DIR, path.lstrip('/'))

        if os.path.isfile(file_path):
            # Determine MIME type
            content_type, _ = mimetypes.guess_type(file_path)
            if content_type is None:
                content_type = 'application/octet-stream'

            # Read file content
            with open(file_path, 'rb') as f:
                body = f.read()

            # Build HTTP response headers
            headers = [
                'HTTP/1.1 200 OK',
                f'Content-Type: {content_type}',
                f'Content-Length: {len(body)}',
                'Connection: close',
                '\r\n'
            ]
            header_bytes = '\r\n'.join(headers).encode('utf-8')

            client_conn.sendall(header_bytes + body)
            print(f"Served {file_path} to {client_addr}: {header_bytes + body}")
        else:
            # File not found
            body = b'404 Not Found'
            headers = [
                'HTTP/1.1 404 Not Found',
                'Content-Type: text/plain',
                f'Content-Length: {len(body)}',
                'Connection: close',
                '\r\n'
            ]
            header_bytes = '\r\n'.join(headers).encode('utf-8')
            client_conn.sendall(header_bytes + body)


def main():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind((HOST, PORT))
        server_socket.listen()
        print(f"Serving HTTP on {HOST} port {PORT} ...")

        while True:
            client_conn, client_addr = server_socket.accept()
            thread = threading.Thread(
                target=handle_client,
                args=(client_conn, client_addr),
                daemon=True
            )
            thread.start()


if __name__ == '__main__':
    main()
