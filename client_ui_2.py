import tkinter as tk
from tkinter import ttk, messagebox
import threading

from audio_client_v2 import AudioClient

class AudioClientApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Ogg Vorbis Client (YouTube-like Slider)")

        style = ttk.Style(self)
        style.theme_use("alt")

        # Song
        tk.Label(self, text="Song:").grid(row=0, column=0, sticky='e', padx=5, pady=5)
        self.song_entry = tk.Entry(self)
        self.song_entry.insert(0, "example.ogg")
        self.song_entry.grid(row=0, column=1, padx=5, pady=5)

        # Static Start Time
        tk.Label(self, text="Start Time:").grid(row=1, column=0, sticky='e', padx=5, pady=5)
        self.time_text = tk.Label(self, text="0")
        self.time_text.grid(row=1, column=1, sticky='w', padx=5, pady=5)

        # Buttons
        self.start_button = tk.Button(self, text="Start/Stop", command=self.start_button)
        self.start_button.grid(row=2, column=0, sticky='e', padx=5, pady=5)

        self.pause_button = tk.Button(self, text="Pause/Resume", command=self.pause_stream, state=tk.DISABLED)
        self.pause_button.grid(row=2, column=1, sticky='w', padx=5, pady=5)

        # Canvas that will serve as our "YouTube-like" progress bar + handle
        # You can tweak the width/height as you like.
        self.slider_canvas = tk.Canvas(self, width=400, height=30, bg="white", highlightthickness=0)
        self.slider_canvas.grid(row=3, column=0, columnspan=2, padx=5, pady=(10,5))
        # We’ll bind mouse events for seeking:
        self.slider_canvas.bind("<ButtonPress-1>", self.on_slider_press)
        self.slider_canvas.bind("<B1-Motion>", self.on_slider_move)
        self.slider_canvas.bind("<ButtonRelease-1>", self.on_slider_release)

        # Playback time label (like "12.3 / 88.0 sec")
        self.playback_label = tk.Label(self, text="0.0 / ? sec")
        self.playback_label.grid(row=4, column=0, columnspan=2)

        # Status
        self.status_label = tk.Label(self, text="Status: Idle")
        self.status_label.grid(row=5, column=0, columnspan=2)

        # Internal state
        self.client = None
        self.stream_thread = None

        self.total_time = 1.0       # total track duration (avoid 0)
        self.downloaded_time = 0.0  # how many seconds are buffered
        self.played_time = 0.0      # current playback position

        # For dragging:
        self.dragging = False

        # We’ll call a function to draw the slider:
        self.draw_slider()

    def start_button(self):
        if self.client:
            if self.stream_thread:
                self.stop_stream()
                return
        self.start_stream()

    def start_stream(self):
        if self.stream_thread and self.stream_thread.is_alive():
            messagebox.showinfo("Info", "Already streaming!")
            return

        song_name = self.song_entry.get()
        page_num = 0

        self.client = AudioClient()
        self.client.set_progress_callback(self.on_download_progress)
        self.client.set_time_callback(self.on_playback_time)

        def run():
            try:
                self.update_status("Connecting to server...")
                self.client.ask_for_song(song_name, page_num)
                self.update_status(f"Requesting {song_name}, page={page_num}")
                self.client.receive_stream()
                self.update_status("Stream ended.")
                self.client = None
            except Exception as e:
                messagebox.showerror("Error", str(e))
                self.update_status(f"Error: {e}")
            finally:
                self.pause_button.config(state=tk.DISABLED)

        self.stream_thread = threading.Thread(target=run, daemon=True)
        self.stream_thread.start()

        self.update_status("Attempting to stream...")
        self.pause_button.config(state=tk.NORMAL)

        # Reset times
        self.total_time = 1.0
        self.downloaded_time = 0.0
        self.played_time = 0.0
        self.playback_label.config(text="0.0 / ? sec")
        self.draw_slider()

    def pause_stream(self):
        if self.client:
            self.client.pause()
            new_state = "Paused" if not self.client.playing else "Resumed"
            self.update_status(new_state)

    def stop_stream(self):
        if self.client:
            self.client.stop()
        self.update_status("Stopped")
        self.pause_button.config(state=tk.DISABLED)

    # ---------- Canvas-based slider drawing ----------

    def draw_slider(self):
        """
        Draw a "YouTube-style" bar:
          - Gray line for total track
          - Lighter bar for downloaded portion
          - Darker bar for played portion
          - A handle to indicate the current play position
        """
        # Clear previous drawings
        self.slider_canvas.delete("all")

        w = self.slider_canvas.winfo_width()
        h = self.slider_canvas.winfo_height()

        # We’ll draw everything in the horizontal center:
        bar_height = 6
        center_y = h // 2

        # Compute ratios
        ratio_downloaded = min(max(self.downloaded_time / self.total_time, 0.0), 1.0)
        ratio_played = min(max(self.played_time / self.total_time, 0.0), 1.0)

        # x-coordinates for the downloaded portion and played portion
        downloaded_x = ratio_downloaded * w
        played_x = ratio_played * w

        # 1) Draw the "total track" as a light gray line from x=0 -> x=w
        self.slider_canvas.create_line(
            0, center_y,
            w, center_y,
            width=bar_height,
            fill="#cccccc"
        )

        # 2) Draw the "buffered" or "downloaded" portion as a medium-gray line
        self.slider_canvas.create_line(
            0, center_y,
            downloaded_x, center_y,
            width=bar_height,
            fill="#888888"
        )

        # 3) Draw the "played" portion as a more distinct color (e.g. red)
        self.slider_canvas.create_line(
            0, center_y,
            played_x, center_y,
            width=bar_height,
            fill="light gray"
        )

        # 4) Draw the handle at the "played" position
        #    We'll use a small circle whose center is at (played_x, center_y).
        handle_radius = 7
        self.slider_canvas.create_oval(
            played_x - handle_radius, center_y - handle_radius,
            played_x + handle_radius, center_y + handle_radius,
            fill="light gray", outline="white", width=2
        )

    def on_slider_press(self, event):
        # Mark that we’re dragging
        self.dragging = True
        # Move handle right away
        self._update_position_from_click(event.x)

    def on_slider_move(self, event):
        if self.dragging:
            self._update_position_from_click(event.x)

    def on_slider_release(self, event):
        self.dragging = False
        # Final position – send the seek command to server
        self._update_position_from_click(event.x, do_seek=True)

    def _update_position_from_click(self, x, do_seek=False):
        """
        Convert canvas x-coordinate to a time in seconds.
        Set self.played_time accordingly, then re-draw the slider.
        If do_seek=True, actually call self.client.seek().
        """
        w = self.slider_canvas.winfo_width()
        # clamp x between [0, w]
        x = max(0, min(w, x))

        # ratio is x / w, so new time is ratio * total_time
        new_time = (x / w) * self.total_time

        # Optional: clamp seeking to downloaded_time, if you want
        # new_time = min(new_time, self.downloaded_time)

        self.played_time = new_time
        self.draw_slider()

        if do_seek and self.client:
            self.client.seek(self.played_time)

    # ---------- AudioClient callbacks ----------

    def on_download_progress(self, cur_pages, duration):
        """
        Called by AudioClient to indicate how much is downloaded + total track length.
        """
        downloaded_sec = self.client.times[cur_pages] if cur_pages < len(self.client.times) else 0.0

        self.after(0, self._update_download, downloaded_sec, duration)

    def _update_download(self, downloaded_sec, total_sec):
        if total_sec < 1:
            total_sec = 1
        self.total_time = total_sec
        self.downloaded_time = downloaded_sec
        self.draw_slider()

    def on_playback_time(self, played_s, total_s):
        self.after(0, self._update_playback, played_s, total_s)

    def _update_playback(self, played_s, total_s):
        if total_s < 1:
            total_s = 1
        self.total_time = total_s
        self.played_time = played_s

        # Update time label
        self.playback_label.config(text=f"{played_s:.1f} / {total_s:.1f} sec")

        # Redraw
        # If user is dragging, we won't override their handle position
        if not self.dragging:
            self.draw_slider()

    # ---------- Helpers ----------

    def update_status(self, text):
        self.status_label.config(text=f"Status: {text}")


if __name__ == "__main__":
    app = AudioClientApp()
    app.mainloop()
