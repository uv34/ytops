import socket
import threading
import tkinter as tk
from tkinter import messagebox
import hashlib
import protocol  # assuming protocol has create_msg, get_msg, and PORT defined

SERVER_IP = "127.0.0.1"  # adjust as needed
SERVER_PORT = 5001

class Client:
    def __init__(self, master):
        self.master = master
        self.master.title("Login/Register Client")
        self.client_socket = None
        self.build_ui()

    def build_ui(self):
        self.frame = tk.Frame(self.master)
        self.frame.pack(padx=10, pady=10)

        tk.Label(self.frame, text="Username:").grid(row=0, column=0, sticky=tk.E)
        self.username_entry = tk.Entry(self.frame)
        self.username_entry.grid(row=0, column=1)

        tk.Label(self.frame, text="Password:").grid(row=1, column=0, sticky=tk.E)
        self.password_entry = tk.Entry(self.frame, show="*")
        self.password_entry.grid(row=1, column=1)

        self.login_button = tk.Button(self.frame, text="Login", command=self.login)
        self.login_button.grid(row=2, column=0, pady=5)

        self.register_button = tk.Button(self.frame, text="Register", command=self.register)
        self.register_button.grid(row=2, column=1, pady=5)

    def connect(self):
        try:
            self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.client_socket.connect((SERVER_IP, SERVER_PORT))
        except Exception as e:
            messagebox.showerror("Connection Error", f"Could not connect to server: {e}")
            return False
        return True

    def hash_password(self, password):
        # Simple SHA256 hash; in production, use a proper salted hash
        return hashlib.sha256(password.encode()).hexdigest()

    def send_receive(self, cmd, data):
        # Create and send the message using the protocol functions
        msg = protocol.create_msg(cmd, data)
        self.client_socket.send(msg)
        # Wait for the response from the server
        response_cmd, response_data = protocol.get_msg(self.client_socket)
        return response_cmd, response_data

    def login(self):
        username = self.username_entry.get().strip()
        password = self.password_entry.get().strip()
        if not username or not password:
            messagebox.showwarning("Input Error", "Please enter both username and password.")
            return

        hashed_password = self.hash_password(password)
        data = f"{username}~{hashed_password}".encode()

        # Connect to the server if not already connected
        if self.client_socket is None:
            if not self.connect():
                return

        # Use a thread so the UI remains responsive
        threading.Thread(target=self.handle_login, args=(data,)).start()

    def handle_login(self, data):
        try:
            cmd, response = self.send_receive("LOGI", data)
            if "successful" in response.lower():
                messagebox.showinfo("Login", response)
            else:
                messagebox.showerror("Login Failed", response)
        except Exception as e:
            messagebox.showerror("Error", f"Error during login: {e}")

    def register(self):
        username = self.username_entry.get().strip()
        password = self.password_entry.get().strip()
        if not username or not password:
            messagebox.showwarning("Input Error", "Please enter both username and password.")
            return

        hashed_password = self.hash_password(password)
        data = f"{username}~{hashed_password}".encode()

        if self.client_socket is None:
            if not self.connect():
                return

        threading.Thread(target=self.handle_register, args=(data,)).start()

    def handle_register(self, data):
        try:
            cmd, response = self.send_receive("REGI", data)
            if "successful" in response.lower():
                messagebox.showinfo("Registration", response)
            else:
                messagebox.showerror("Registration Failed", response)
        except Exception as e:
            messagebox.showerror("Error", f"Error during registration: {e}")

if __name__ == '__main__':
    root = tk.Tk()
    client_app = Client(root)
    root.mainloop()
