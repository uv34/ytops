import mimetypes
import os
import secrets
import socket
import ssl
import threading
from datetime import datetime, timedelta
from urllib.parse import urlparse, parse_qs

import mysql_helper
from MailManager import Mail

HOST = '0.0.0.0'  # Listen on all interfaces
PORT = 443  # Port to listen on
BASE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'webroot/')
print(BASE_DIR)
CERT_FILE = os.path.join(BASE_DIR, 'cert.pem')
KEY_FILE = os.path.join(BASE_DIR, 'key.pem')
"""db = mysql_helper.DBController(
    host="192.168.1.20", user="stopify", password="stop123", database="mydb"
)"""
print(CERT_FILE)
allowed_paths = [
    'index.html',
    'verify-email',
    'favicon.ico',
    'icon.png',
    'installer.py'
]


def parse_query(path: str) -> dict:
    """
    Given a request path like '/verify-email?token=XYZ&foo=bar',
    return a dict mapping each key to a list of values:
      { 'token': ['XYZ'], 'foo': ['bar'] }
    """
    # Split off any fragment, then parse out query
    parsed = urlparse(path)
    return parse_qs(parsed.query)


def send_400(client_conn, message: str):
    """
    Send a 400 Bad Request with a plain-text error message.
    """
    body = message.encode('utf-8')
    headers = [
        'HTTP/1.1 400 Bad Request',
        'Content-Type: text/plain; charset=utf-8',
        f'Content-Length: {len(body)}',
        'Connection: close',
        '\r\n'
    ]
    response = '\r\n'.join(headers).encode('utf-8') + body
    client_conn.sendall(response)


def send_html(client_conn, status_code: int, html: str):
    """
    Send an HTML response (e.g. success page).
    """
    body = html.encode('utf-8')
    reason = {
        200: 'OK',
        404: 'Not Found',
        400: 'Bad Request'
    }.get(status_code, 'OK')
    headers = [
        f'HTTP/1.1 {status_code} {reason}',
        'Content-Type: text/html; charset=utf-8',
        f'Content-Length: {len(body)}',
        'Connection: close',
        '\r\n'
    ]
    response = '\r\n'.join(headers).encode('utf-8') + body
    client_conn.sendall(response)


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
            path = 'index.html'
        print(f"Serving {path} to {client_addr}")
        if path.startswith('/verify-email'):
            token = parse_query(path)['token'][0]
            print('token', token)

            not_expired, user = db.get_user_by_token(token)
            if not user:
                send_400(client_conn, "Invalid verification link")
            elif not not_expired:

                send_400(client_conn, "Verification link expired, sending new one")
                # Send a new verification email
                token = secrets.token_urlsafe(32)
                expiry = datetime.utcnow() + timedelta(hours=24)
                db.update_user_token(user['id'], token, expiry)
                m = Mail('Stopify - Email Verification', """<!DOCTYPE html>
                                <html lang="en">
                                <head>
                                  <meta charset="UTF-8">
                                  <title>Stopify – Email Verification</title>
                                </head>
                                <body style="font-family: Arial, sans-serif; line-height: 1.5; color: #333; margin: 20px;">
                                <center>
                                  <h2 style="margin-top: 0;">Welcome to Stopify!</h2>
                                  <p>To activate your account, please click the link below:</p>
                                  <p><a href='https://localhost/verify-email?token=""" + token + """' style="color: #1a73e8; text-decoration: none;">Verify your email</a></p>
                                  <p style="font-size: 0.9em; color: #666;">
                                    This link expires in 24 hours. If you didn’t sign up, you can ignore this message.
                                  </p>
                                  <p>Thanks,<br>The Stopify Team</p>
                                </center>
                                </body>
                                </html>""", user["email"])
                m.send()
            else:
                db.verify_user(user['id'])
                html = """
                    <html lang="en">
                    <head>
                      <meta charset="UTF-8">
                      <title>Email Verified</title>
                      <style>
                        body {
                          font-family: Arial, sans-serif;
                          background-color: #f9f9f9;
                          color: #333;
                          display: flex;
                          flex-direction: column;
                          align-items: center;
                          justify-content: center;
                          height: 100vh;
                          margin: 0;
                        }
                        .container {
                          background: #fff;
                          padding: 40px 60px;
                          border-radius: 8px;
                          box-shadow: 0 4px 12px rgba(0,0,0,0.1);
                          text-align: center;
                        }
                        h1 {
                          margin: 0 0 20px;
                          font-size: 2em;
                          color: #4CAF50;
                        }
                        p {
                          margin: 0;
                          font-size: 1em;
                          color: #666;
                        }
                      </style>
                    </head>
                    <body>
                      <div class="container">
                        <h1>Email verified!</h1>
                        <p>Please refresh the app to start using your account.</p>
                      </div>
                    </body>
                    </html>
                    """
                send_html(client_conn, 200, html)
            return

        # Construct full file path
        file_path = os.path.join(BASE_DIR, path.lstrip('/'))
        print(f"File path: {file_path}")
        path = path.lstrip('/')
        print(os.path.isfile(file_path))
        print(path, allowed_paths, path in allowed_paths)
        if os.path.isfile(file_path) and path in allowed_paths:
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
                print("Waiting for a connection...")
                client_conn, client_addr = tls_sock.accept()
                thread = threading.Thread(
                    target=handle_client,
                    args=(client_conn, client_addr),
                    daemon=True
                )
                thread.start()


if __name__ == '__main__':
    main()
