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

        # Create frames for login and registration
        self.login_frame = tk.Frame(self)
        self.register_frame = tk.Frame(self)

        self.build_login_ui()
        self.build_register_ui()

        self.show_login_frame()

    def build_login_ui(self):
        """Build the login UI with username and password entries and buttons."""
        frame = self.login_frame
        # Pack is called in the show function, so we don't pack here immediately.
        tk.Label(frame, text="Username:").grid(row=0, column=0, sticky=tk.E)
        self.login_username_entry = tk.Entry(frame)
        self.login_username_entry.grid(row=0, column=1)

        tk.Label(frame, text="Password:").grid(row=1, column=0, sticky=tk.E)
        self.login_password_entry = tk.Entry(frame, show="*")
        self.login_password_entry.grid(row=1, column=1)

        login_button = tk.Button(frame, text="Login", command=self.login)
        login_button.grid(row=2, column=0, columnspan=2, pady=5)

        switch_to_register = tk.Button(frame, text="Go to Register", command=self.show_register_frame)
        switch_to_register.grid(row=3, column=0, columnspan=2, pady=5)

    def build_register_ui(self):
        """Build the registration UI with username, email, and password entries."""
        frame = self.register_frame
        tk.Label(frame, text="Username:").grid(row=0, column=0, sticky=tk.E)
        self.register_username_entry = tk.Entry(frame)
        self.register_username_entry.grid(row=0, column=1)

        tk.Label(frame, text="Email:").grid(row=1, column=0, sticky=tk.E)
        self.register_email_entry = tk.Entry(frame)
        self.register_email_entry.grid(row=1, column=1)

        tk.Label(frame, text="Password:").grid(row=2, column=0, sticky=tk.E)
        self.register_password_entry = tk.Entry(frame, show="*")
        self.register_password_entry.grid(row=2, column=1)

        register_button = tk.Button(frame, text="Register", command=self.register)
        register_button.grid(row=3, column=0, columnspan=2, pady=5)

        back_to_login = tk.Button(frame, text="Back to Login", command=self.show_login_frame)
        back_to_login.grid(row=4, column=0, columnspan=2, pady=5)

    def show_login_frame(self):
        """Show the login frame and hide the registration frame."""
        self.register_frame.pack_forget()
        self.login_frame.pack(padx=10, pady=10)

    def show_register_frame(self):
        """Show the registration frame and hide the login frame."""
        self.login_frame.pack_forget()
        self.register_frame.pack(padx=10, pady=10)

    def connect(self):
        """Establish a connection to the server if not already connected."""
        if self.client_socket is None:
            try:
                self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.client_socket.connect((SERVER_IP, SERVER_PORT))
            except Exception as e:
                messagebox.showerror("Connection Error", f"Could not connect to server: {e}")
                return False
        return True

    def send_receive(self, cmd, data):
        """Send a message using the protocol and wait for a response."""
        msg = protocol.create_msg(cmd, data)
        self.client_socket.send(msg)
        response_cmd, response_data = protocol.get_msg(self.client_socket)
        return response_cmd, response_data.decode()

    def login(self):
        """Gather login credentials and send a login request."""
        username = self.login_username_entry.get().strip()
        password = self.login_password_entry.get().strip()

        if not username or not password:
            messagebox.showwarning("Input Error", "Please enter both username and password.")
            return

        if not self.connect():
            return

        data = f"{username}~{password}".encode()
        threading.Thread(target=self.handle_login, args=(data, username)).start()

    def handle_login(self, data, username):
        try:
            cmd, response = self.send_receive("LOGI", data)
            if "successful" in response.lower():
                self.login_success = True
                self.logged_in_username = username
                messagebox.showinfo("Login", response)
                self.destroy()  # Ends the mainloop for login
            else:
                messagebox.showerror("Login Failed", response)
        except Exception as e:
            messagebox.showerror("Error", f"Error during login: {e}")

    def register(self):
        """Gather registration credentials and send a registration request."""
        username = self.register_username_entry.get().strip()
        email = self.register_email_entry.get().strip()
        password = self.register_password_entry.get().strip()

        if not username or not email or not password:
            messagebox.showwarning("Input Error", "Please fill in username, email, and password.")
            return

        if not self.connect():
            return

        data = f"{username}~{email}~{password}".encode()
        threading.Thread(target=self.handle_register, args=(data,username)).start()

    def handle_register(self, data, username):
        try:
            cmd, response = self.send_receive("REGI", data)
            if "successful" in response.lower():
                messagebox.showinfo("Registration", response)
                self.login_success = True
                self.logged_in_username = username
                self.destroy()  # Ends the mainloop for login
            else:
                messagebox.showerror("Registration Failed", response)
        except Exception as e:
            messagebox.showerror("Error", f"Error during registration: {e}")


class MainWindow(tk.Tk):
    """
    The main window that appears after a successful login.
    """
    def __init__(self, username):
        super().__init__()
        self.title("Main Window")
        self.username = username
        self.build_ui()

    def build_ui(self):
        tk.Label(self, text=f"Hello, {self.username}!").pack(padx=20, pady=20)
        logout_button = tk.Button(self, text="Exit", command=self.quit)
        logout_button.pack(pady=5)


def run_login_register_window():
    app = LoginRegisterWindow()
    app.mainloop()
    return app.login_success, app.logged_in_username



def main():
    success, user = run_login_register_window()
    if success and user:
        tk._default_root = None  # reset the default root
        main_app = client_ui_2.AudioClientApp()
        main_app.mainloop()


if __name__ == "__main__":
    main()
