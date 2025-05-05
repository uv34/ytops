import socket
import threading
import os
import ssl
import mimetypes

HOST = '0.0.0.0'  # Listen on all interfaces
PORT = 443       # Port to listen on
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

CERT_FILE = os.path.join(BASE_DIR, 'cert.pem')
KEY_FILE = os.path.join(BASE_DIR, 'key.pem')


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
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certfile=CERT_FILE, keyfile=KEY_FILE)

    # Create and bind socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM, 0) as server_sock:
        server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_sock.bind((HOST, PORT))
        server_sock.listen(5)
        print(f"Serving HTTPS on {HOST} port {PORT} ...")

        # Wrap the socket with SSL
        with context.wrap_socket(server_sock, server_side=True) as tls_sock:
            while True:
                client_conn, client_addr = tls_sock.accept()
                thread = threading.Thread(
                    target=handle_client,
                    args=(client_conn, client_addr),
                    daemon=True
                )
                thread.start()


if __name__ == '__main__':
    main()
