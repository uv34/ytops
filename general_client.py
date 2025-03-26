import socket
import threading
import tkinter as tk
from tkinter import messagebox
import protocol  # assuming protocol has create_msg, get_msg, and PORT defined
import client_ui_2

SERVER_IP = "127.0.0.1"
SERVER_PORT = 5001

class LoginRegisterWindow(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Login/Register")
        self.client_socket = None
        self.login_success = False
        self.logged_in_username = None
        self.token = '###'

        self.login_frame = tk.Frame(self)
        self.register_frame = tk.Frame(self)
        self.build_login_ui()
        self.build_register_ui()
        self.show_login_frame()

    def destroy1(self):
        for after_id in self.tk.call('after', 'info'):
            self.after_cancel(after_id)

        super().destroy()

    def build_login_ui(self):
        frame = self.login_frame
        tk.Label(frame, text="Username:").grid(row=0, column=0, sticky=tk.E)
        self.login_username_entry = tk.Entry(frame)
        self.login_username_entry.grid(row=0, column=1)
        tk.Label(frame, text="Password:").grid(row=1, column=0, sticky=tk.E)
        self.login_password_entry = tk.Entry(frame, show="*")
        self.login_password_entry.grid(row=1, column=1)
        tk.Button(frame, text="Login", command=self.login).grid(row=2, column=0, columnspan=2, pady=5)
        tk.Button(frame, text="Go to Register", command=self.show_register_frame).grid(row=3, column=0, columnspan=2, pady=5)

    def build_register_ui(self):
        frame = self.register_frame
        tk.Label(frame, text="Username:").grid(row=0, column=0, sticky=tk.E)
        self.register_username_entry = tk.Entry(frame); self.register_username_entry.grid(row=0, column=1)
        tk.Label(frame, text="Email:").grid(row=1, column=0, sticky=tk.E)
        self.register_email_entry = tk.Entry(frame); self.register_email_entry.grid(row=1, column=1)
        tk.Label(frame, text="Password:").grid(row=2, column=0, sticky=tk.E)
        self.register_password_entry = tk.Entry(frame, show="*"); self.register_password_entry.grid(row=2, column=1)
        tk.Button(frame, text="Register", command=self.register).grid(row=3, column=0, columnspan=2, pady=5)
        tk.Button(frame, text="Back to Login", command=self.show_login_frame).grid(row=4, column=0, columnspan=2, pady=5)

    def show_login_frame(self):
        self.register_frame.pack_forget()
        self.login_frame.pack(padx=10, pady=10)

    def show_register_frame(self):
        self.login_frame.pack_forget()
        self.register_frame.pack(padx=10, pady=10)

    def connect(self):
        if self.client_socket is None:
            try:
                self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.client_socket.connect((SERVER_IP, SERVER_PORT))
            except Exception as e:
                messagebox.showerror("Connection Error", f"Could not connect to server: {e}")
                return False
        return True

    def send_receive(self, cmd, data):
        msg = protocol.create_msg(cmd, data)
        self.client_socket.send(msg)
        response_cmd, response_data = protocol.get_msg(self.client_socket)
        return response_cmd, response_data.decode()

    def login(self):
        username = self.login_username_entry.get().strip()
        password = self.login_password_entry.get().strip()
        if not username or not password:
            messagebox.showwarning("Input Error", "Please enter both username and password.")
            return
        if not self.connect():
            return
        threading.Thread(target=self.handle_login, args=(f"{username}~{password}".encode(), username), daemon=True).start()

    def handle_login(self, data, username):
        try:
            cmd, resp = self.send_receive("LOGI", data)
            response, token = resp.split('~')
            if "successful" in response.lower():
                self.login_success, self.logged_in_username, self.token = True, username, token
                self.after(0, lambda: messagebox.showinfo("Login", response))
                self.after(0, self.destroy1)
            else:
                self.after(0, lambda: messagebox.showerror("Login Failed", response))
        except Exception as e:
            self.after(0, lambda: messagebox.showerror("Error", f"Error during login: {e}"))

    def register(self):
        username = self.register_username_entry.get().strip()
        email = self.register_email_entry.get().strip()
        password = self.register_password_entry.get().strip()
        if not username or not email or not password:
            messagebox.showwarning("Input Error", "Please fill all fields.")
            return
        if not self.connect():
            return
        threading.Thread(target=self.handle_register, args=(f"{username}~{email}~{password}".encode(), username), daemon=True).start()

    def handle_register(self, data, username):
        try:
            cmd, resp = self.send_receive("REGI", data)
            response, token = resp.split('~')
            if "successful" in response.lower():
                self.login_success, self.logged_in_username, self.token = True, username, token
                self.after(0, lambda: messagebox.showinfo("Registration", response))
                self.after(0, self.destroy1)
            else:
                self.after(0, lambda: messagebox.showerror("Registration Failed", response))
        except Exception as e:
            self.after(0, lambda: messagebox.showerror("Error", f"Error during registration: {e}"))

class MainWindow(tk.Tk):
    def __init__(self, username):
        super().__init__()
        self.title("Main Window")
        tk.Label(self, text=f"Hello, {username}!").pack(padx=20, pady=20)
        tk.Button(self, text="Exit", command=self.quit).pack(pady=5)

def run_login_register_window():
    app = LoginRegisterWindow()
    app.mainloop()
    return app.login_success, app.logged_in_username, app.token, app.client_socket

def main():
    success, user, token, sock = run_login_register_window()
    if success and user:
        tk._default_root = None
        print(token)
        client_ui_2.AudioClientApp(token).mainloop()


if __name__ == "__main__":
    main()
