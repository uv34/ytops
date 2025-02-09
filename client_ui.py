import tkinter as tk
from tkinter import messagebox
import threading

from audio_client_v2 import AudioClient  # Import our AudioClient from audioclient.py


class AudioClientApp(tk.Tk):
    """
    A simple Tkinter-based UI to interact with the AudioClient.
    """
    def __init__(self):
        super().__init__()
        self.title("Audio Client")

        # UI Elements
        self.host_label = tk.Label(self, text="Host:")
        self.host_label.grid(row=0, column=0, padx=5, pady=5, sticky='e')
        self.host_entry = tk.Entry(self)
        self.host_entry.insert(0, "127.0.0.1")  # default
        self.host_entry.grid(row=0, column=1, padx=5, pady=5)

        self.port_label = tk.Label(self, text="Port:")
        self.port_label.grid(row=1, column=0, padx=5, pady=5, sticky='e')
        self.port_entry = tk.Entry(self)
        self.port_entry.insert(0, "5000")  # default
        self.port_entry.grid(row=1, column=1, padx=5, pady=5)

        self.song_label = tk.Label(self, text="Song name:")
        self.song_label.grid(row=2, column=0, padx=5, pady=5, sticky='e')
        self.song_entry = tk.Entry(self)
        self.song_entry.insert(0, "example.ogg")  # default
        self.song_entry.grid(row=2, column=1, padx=5, pady=5)

        self.start_button = tk.Button(self, text="Start Streaming", command=self.start_stream)
        self.start_button.grid(row=3, column=0, padx=5, pady=5, sticky='e')

        self.pause_button = tk.Button(self, text="Pause Streaming", command=self.pause_stream, state=tk.DISABLED)
        self.pause_button.grid(row=3, column=1, padx=5, pady=5, sticky='w')

        self.status_label = tk.Label(self, text="Status: Idle")
        self.status_label.grid(row=4, column=0, columnspan=2, padx=5, pady=5)

        # References to the streaming client and thread
        self.client = None
        self.stream_thread = None

    def start_stream(self):
        """
        Start streaming in a background thread, so the UI remains responsive.
        """
        # If there's already a streaming thread, ignore if it's alive
        if self.stream_thread and self.stream_thread.is_alive():
            messagebox.showinfo("Streaming", "Already streaming!")
            return

        host = self.host_entry.get()
        port = int(self.port_entry.get())
        song_name = self.song_entry.get()

        self.client = AudioClient(host=host, port=port, chunk_size=8192)

        print(f"Starting stream for {song_name} from {host}:{port}...")

        def run_stream():
            try:
                self.update_status("Connecting to server...")
                sock = self.client.ask_for_song(song_name)
                self.update_status("Streaming started...")
                self.client.receive_stream(sock)
                self.update_status("Stream ended.")
            except Exception as e:
                self.update_status(f"Error: {e}")
                messagebox.showerror("Error", str(e))
            finally:
                # Re-enable the start button, disable the stop button
                self.start_button.config(state=tk.NORMAL)
                self.pause_button.config(state=tk.DISABLED)

        # Create a background thread to run the streaming logic
        self.stream_thread = threading.Thread(target=run_stream, daemon=True)
        self.stream_thread.start()

        self.update_status("Attempting to stream...")
        self.start_button.config(state=tk.DISABLED)
        self.pause_button.config(state=tk.NORMAL)

    def pause_stream(self):
        """
        Signal the client to stop streaming and wait for the thread to join.
        """
        if self.client:
            self.client.pause()
            self.update_status("paused")


    def update_status(self, text):
        self.status_label.config(text=f"Status: {text}")


if __name__ == "__main__":
    app = AudioClientApp()
    app.mainloop()
