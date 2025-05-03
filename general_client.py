import socket
import threading
import tkinter as tk
import customtkinter as ctk
from tkinter import messagebox
import protocol  # assuming protocol has create_msg, get_msg, and PORT defined
import client_ui_3

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

        self.primary_ui = "#A8DADC"
        self.secondary_accent = "#F4C2C2"
        self.success = "#C4E1C1"
        self.background = "#E8E8FA"
        self.prime_text = "#36454F"
        self.second_text = "#A0A0A0"

        self.tabview = ctk.CTkTabview(self, width=380, height=300, fg_color=self.background)
        self.tabview.pack(padx=20, pady=20)
        self.login_tab = self.tabview.add("Login")
        self.register_tab = self.tabview.add("Register")

        self.build_login_tab()
        self.build_register_tab()

    def destroy1(self):
        for after_id in self.tk.call('after', 'info'):
            self.after_cancel(after_id)

        super().destroy()

    def build_login_tab(self):
        pad_y = 12
        # Username
        ctk.CTkLabel(self.login_tab, text="Username", text_color=self.prime_text).pack(anchor="w", pady=(10, 4),
                                                                                       padx=20)
        self.login_username_entry = ctk.CTkEntry(
            self.login_tab, placeholder_text="Enter username",
            fg_color="white", text_color=self.prime_text)
        self.login_username_entry.pack(fill="x", padx=20)

        # Password
        ctk.CTkLabel(self.login_tab, text="Password", text_color=self.prime_text).pack(anchor="w", pady=(pad_y, 4),
                                                                                       padx=20)
        self.login_password_entry = ctk.CTkEntry(
            self.login_tab, placeholder_text="Enter password", show="*",
            fg_color="white", text_color=self.prime_text)
        self.login_password_entry.pack(fill="x", padx=20)

        login_btn = ctk.CTkButton(
            self.login_tab, text="Login",
            fg_color=self.primary_ui, hover_color=self.success,
            text_color=self.prime_text, command=self.login)
        login_btn.pack(side="left", expand=True, padx=(0, 5))


    def build_register_tab(self):
        pad_y = 12
        # Username
        ctk.CTkLabel(self.register_tab, text="Username", text_color=self.prime_text).pack(anchor="w", pady=(10, 4),
                                                                                          padx=20)
        self.register_username_entry = ctk.CTkEntry(
            self.register_tab, placeholder_text="Choose username",
            fg_color="white", text_color=self.prime_text)
        self.register_username_entry.pack(fill="x", padx=20)

        # Email
        ctk.CTkLabel(self.register_tab, text="Email", text_color=self.prime_text).pack(anchor="w", pady=(pad_y, 4),
                                                                                       padx=20)
        self.register_email_entry = ctk.CTkEntry(
            self.register_tab, placeholder_text="Your email",
            fg_color="white", text_color=self.prime_text)
        self.register_email_entry.pack(fill="x", padx=20)

        # Password
        ctk.CTkLabel(self.register_tab, text="Password", text_color=self.prime_text).pack(anchor="w", pady=(pad_y, 4),
                                                                                          padx=20)
        self.register_password_entry = ctk.CTkEntry(
            self.register_tab, placeholder_text="Choose password", show="*",
            fg_color="white", text_color=self.prime_text)
        self.register_password_entry.pack(fill="x", padx=20)

        register_btn = ctk.CTkButton(
            self.register_tab, text="Register",
            fg_color=self.primary_ui, hover_color=self.success,
            text_color=self.prime_text, command=self.register)
        register_btn.pack(side="left", expand=True, padx=(0, 5))


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
        client_ui_3.AudioClientApp(token, sock, user).mainloop()
        if sock:
            print(sock)
            sock.send(protocol.create_msg('EXIT', b''))


if __name__ == "__main__":
    main()
