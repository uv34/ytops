import tkinter as tk
from tkinter import ttk
from tkinter import messagebox
import threading

from audio_client_v2 import AudioClient


class AudioClientApp(tk.Tk):
    """
    A Tkinter-based UI with two progress bars:
     1) Download progress (pages)
     2) Playback progress (time)
    """
    def __init__(self):
        super().__init__()
        self.title("Audio Client")

        """# Host
        tk.Label(self, text="Host:").grid(row=0, column=0, padx=5, pady=5, sticky='e')
        self.host_entry = tk.Entry(self)
        self.host_entry.insert(0, "127.0.0.1")  # default
        self.host_entry.grid(row=0, column=1, padx=5, pady=5)

        # Port
        tk.Label(self, text="Port:").grid(row=1, column=0, padx=5, pady=5, sticky='e')
        self.port_entry = tk.Entry(self)
        self.port_entry.insert(0, "5000")  # default
        self.port_entry.grid(row=1, column=1, padx=5, pady=5)"""

        # Song
        tk.Label(self, text="Song:").grid(row=2, column=0, padx=5, pady=5, sticky='e')
        self.song_entry = tk.Entry(self)
        self.song_entry.insert(0, "example.ogg")  # default
        self.song_entry.grid(row=2, column=1, padx=5, pady=5)

        # Buttons
        self.start_button = tk.Button(self, text="Start", command=self.start_stream)
        self.start_button.grid(row=3, column=0, padx=5, pady=5, sticky='e')

        self.pause_button = tk.Button(self, text="Pause/Resume", command=self.pause_stream, state=tk.DISABLED)
        self.pause_button.grid(row=3, column=1, padx=5, pady=5, sticky='w')

        # 1) Download Progress (Pages)
        tk.Label(self, text="Download Progress:").grid(row=4, column=0, padx=5, pady=5, sticky='e')
        self.download_bar = ttk.Progressbar(self, orient="horizontal", length=200, mode="determinate")
        self.download_bar.grid(row=4, column=1, padx=5, pady=5, sticky='w')

        # 2) Playback Progress (Time)
        tk.Label(self, text="Playback Progress:").grid(row=5, column=0, padx=5, pady=5, sticky='e')
        self.playback_bar = ttk.Progressbar(self, orient="horizontal", length=200, mode="determinate")
        self.playback_bar.grid(row=5, column=1, padx=5, pady=5, sticky='w')

        # Labels to show numbers
        self.download_label = tk.Label(self, text="0 / 0 pages")
        self.download_label.grid(row=6, column=0, columnspan=2, pady=(0, 5))

        self.playback_label = tk.Label(self, text="0.0 / 0.0 sec")
        self.playback_label.grid(row=7, column=0, columnspan=2, pady=(0, 10))

        # Status
        self.status_label = tk.Label(self, text="Status: Idle")
        self.status_label.grid(row=8, column=0, columnspan=2, padx=5, pady=5)

        # Internals
        self.client = None
        self.stream_thread = None

    def start_stream(self):
        """Start streaming in a background thread."""
        if self.stream_thread and self.stream_thread.is_alive():
            messagebox.showinfo("Streaming", "Already streaming!")
            return

        host = 'localhost'
        port = 5000
        song_name = self.song_entry.get()

        self.client = AudioClient(host=host, port=port, chunk_size=8192)

        # Attach our callbacks
        self.client.set_progress_callback(self.on_download_progress)  # pages
        self.client.set_time_callback(self.on_playback_time)          # time

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
                self.start_button.config(state=tk.NORMAL)
                self.pause_button.config(state=tk.DISABLED)

        self.stream_thread = threading.Thread(target=run_stream, daemon=True)
        self.stream_thread.start()

        self.update_status("Attempting to stream...")
        self.start_button.config(state=tk.DISABLED)
        self.pause_button.config(state=tk.NORMAL)

        # Reset bars and labels
        self.download_bar["value"] = 0
        self.download_bar["maximum"] = 1
        self.download_label.config(text="0 / ? pages")

        self.playback_bar["value"] = 0
        self.playback_bar["maximum"] = 1
        self.playback_label.config(text="0.0 / ? sec")

    def pause_stream(self):
        """Toggle pause/resume playback."""
        if self.client:
            self.client.pause()
            status = "Resumed" if self.client.playing else "Paused"
            self.update_status(status)

    # ------------------------------
    # PROGRESS callbacks from client
    # ------------------------------
    def on_download_progress(self, current_pages, total_pages):
        """Called by AudioClient each time new OGG pages arrive."""
        # Must schedule UI updates to happen in the main thread:
        self.after(0, self._update_download_progress, current_pages, total_pages)

    def _update_download_progress(self, current_pages, total_pages):
        if total_pages <= 0:
            total_pages = 1  # avoid division by zero
        self.download_bar["maximum"] = total_pages
        self.download_bar["value"] = current_pages
        self.download_label.config(text=f"{current_pages} / {total_pages} pages")

    def on_playback_time(self, played_time, total_time):
        """Called by AudioClient after each PCM chunk is played."""
        self.after(0, self._update_playback_progress, played_time, total_time)

    def _update_playback_progress(self, played_time, total_time):
        # If you have an actual total_time from the server, set it once so this bar is scaled properly
        if total_time <= 0:
            total_time = 1.0  # pretend there's at least 1 second total

        self.playback_bar["maximum"] = total_time
        self.playback_bar["value"] = played_time
        self.playback_label.config(text=f"{played_time:.1f} / {total_time:.1f} sec")

    def update_status(self, text):
        """Update the status label."""
        self.status_label.config(text=f"Status: {text}")


if __name__ == "__main__":
    app = AudioClientApp()
    app.mainloop()
