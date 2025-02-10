# ui_client_seek.py

import tkinter as tk
from tkinter import ttk, messagebox
import threading
from audio_client_v2 import AudioClient

class AudioClientApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Ogg Vorbis Client (Page-based)")

        # Song
        tk.Label(self, text="Song:").grid(row=0, column=0, sticky='e', padx=5, pady=5)
        self.song_entry = tk.Entry(self)
        self.song_entry.insert(0, "example.ogg")
        self.song_entry.grid(row=0, column=1, padx=5, pady=5)

        # Page
        tk.Label(self, text="Start Page:").grid(row=1, column=0, sticky='e', padx=5, pady=5)
        self.page_entry = tk.Entry(self)
        self.page_entry.insert(0, "50")  # default = 50
        self.page_entry.grid(row=1, column=1, padx=5, pady=5)

        # Buttons
        self.start_button = tk.Button(self, text="Start", command=self.start_stream)
        self.start_button.grid(row=2, column=0, sticky='e', padx=5, pady=5)

        self.pause_button = tk.Button(self, text="Pause/Resume", command=self.pause_stream, state=tk.DISABLED)
        self.pause_button.grid(row=2, column=1, sticky='w', padx=5, pady=5)

        # Download progress
        tk.Label(self, text="Download progress:").grid(row=3, column=0, sticky='e', padx=5, pady=5)
        self.download_bar = ttk.Progressbar(self, orient="horizontal", length=200, mode="determinate")
        self.download_bar.grid(row=3, column=1, sticky='w', padx=5, pady=5)
        self.download_label = tk.Label(self, text="0 / 0 pages")
        self.download_label.grid(row=4, column=0, columnspan=2)

        # Playback progress
        tk.Label(self, text="Playback (seconds):").grid(row=5, column=0, sticky='e', padx=5, pady=5)
        self.playback_bar = ttk.Progressbar(self, orient="horizontal", length=200, mode="determinate")
        self.playback_bar.grid(row=5, column=1, sticky='w', padx=5, pady=5)
        self.playback_label = tk.Label(self, text="0.0 / 0.0 sec")
        self.playback_label.grid(row=6, column=0, columnspan=2)

        # Status
        self.status_label = tk.Label(self, text="Status: Idle")
        self.status_label.grid(row=7, column=0, columnspan=2)

        self.client = None
        self.stream_thread = None

    def start_stream(self):
        if self.stream_thread and self.stream_thread.is_alive():
            messagebox.showinfo("Info", "Already streaming!")
            return

        song_name = self.song_entry.get()
        page_num = int(self.page_entry.get() or 0)

        self.client = AudioClient()
        self.client.set_progress_callback(self.on_download_progress)
        self.client.set_time_callback(self.on_playback_time)

        def run():
            try:
                self.update_status("Connecting to server...")
                sock = self.client.ask_for_song(song_name, page_num=page_num)
                self.update_status(f"Requesting {song_name}, page={page_num}")
                self.client.receive_stream(sock)
                self.update_status("Stream ended.")
            except Exception as e:
                messagebox.showerror("Error", str(e))
                self.update_status(f"Error: {e}")
            finally:
                self.start_button.config(state=tk.NORMAL)
                self.pause_button.config(state=tk.DISABLED)

        self.stream_thread = threading.Thread(target=run, daemon=True)
        self.stream_thread.start()

        # UI updates
        self.update_status("Attempting to stream...")
        self.start_button.config(state=tk.DISABLED)
        self.pause_button.config(state=tk.NORMAL)

        self.download_bar["value"] = 0
        self.download_bar["maximum"] = 1
        self.download_label.config(text="0 / ? pages")

        self.playback_bar["value"] = 0
        self.playback_bar["maximum"] = 1
        self.playback_label.config(text="0.0 / ? sec")

    def pause_stream(self):
        if self.client:
            self.client.pause()
            new_state = "Paused" if not self.client.playing else "Resumed"
            self.update_status(new_state)

    # Callbacks
    def on_download_progress(self, cur_pages, total_pages):
        self.after(0, self._update_download, cur_pages, total_pages)

    def _update_download(self, c, t):
        if t < 1: t = 1
        self.download_bar["maximum"] = t
        self.download_bar["value"] = c
        self.download_label.config(text=f"{c} / {t} pages")

    def on_playback_time(self, played_s, total_s):
        self.after(0, self._update_playback, played_s, total_s)

    def _update_playback(self, played_s, total_s):
        if total_s < 1: total_s = 1
        self.playback_bar["maximum"] = total_s
        self.playback_bar["value"] = played_s
        self.playback_label.config(text=f"{played_s:.1f} / {total_s:.1f} sec")

    def update_status(self, text):
        self.status_label.config(text=f"Status: {text}")


if __name__ == "__main__":
    app = AudioClientApp()
    app.mainloop()
