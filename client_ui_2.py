import tkinter as tk
from tkinter import ttk, messagebox
import threading


from audio_client_v2 import AudioClient

def time_str(time: float) -> str:
    return f"{int(time / 60)}:{str(int(time) % 60).zfill(2)}"

class AudioClientApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Ogg Vorbis Client (YouTube-like Slider)")
        self.geometry("400x150")
        self.resizable(False, False)

        style = ttk.Style(self)
        style.theme_use("clam")

        # Song
        tk.Label(self, text="Song:").grid(row=0, column=1, sticky='e', padx=5, pady=5)
        self.song_entry = tk.Entry(self)
        self.song_entry.insert(0, "1")
        self.song_entry.grid(row=0, column=2, padx=5, pady=5)

        self. song_info_label = tk.Label(self, text="song name\n author")
        self.song_info_label.grid(row=1, column=1, columnspan=2, sticky='', padx=5, pady=5)

        # Buttons
        self.start_button = tk.Button(self, text="Start/Stop", command=self.start_button)
        self.start_button.grid(row=2, column=1, sticky='e', padx=5, pady=5)

        self.pause_button = tk.Button(self, text="Pause/Resume", command=self.pause_stream, state=tk.DISABLED)
        self.pause_button.grid(row=2, column=2, sticky='w', padx=5, pady=5)

        # Canvas that will serve as our slider
        self.slider_canvas = tk.Canvas(self, width=300, height=10, bg=self.cget("bg"), highlightthickness=0)
        self.slider_canvas.grid(row=3, column=1, columnspan=2, padx=5, pady=(10,5))
        # Bind <Configure> so we know when the canvas size is finalized
        self.slider_canvas.bind("<Configure>", self.on_canvas_configure)

        # Bind mouse events for seeking
        self.slider_canvas.bind("<ButtonPress-1>", self.on_slider_press)
        self.slider_canvas.bind("<B1-Motion>", self.on_slider_move)
        self.slider_canvas.bind("<ButtonRelease-1>", self.on_slider_release)
        self.dragging = False

        # Playback time label
        self.current_playback_label = tk.Label(self, text="0:00")
        self.current_playback_label.grid(row=3, column=0, padx=10)

        self.total_playback_label = tk.Label(self, text="0:00")
        self.total_playback_label.grid(row=3, column=3, padx=10)


        # Internal state
        self.client = None
        self.stream_thread = None

        self.total_time = 1.0
        self.downloaded_time = 0.0
        self.played_time = 0.0


    def on_canvas_configure(self, event):
        print('event', event)
        self.draw_slider()

    def draw_slider(self):
        self.slider_canvas.delete("all")
        handle_radius = 7

        w = self.slider_canvas.winfo_width() - handle_radius * 2
        h = self.slider_canvas.winfo_height()

        # Basic geometry
        bar_height = 6
        center_y = h // 2

        ratio_downloaded = min(max(self.downloaded_time / self.total_time, 0.0), 1.0)
        ratio_played = min(max(self.played_time / self.total_time, 0.0), 1.0)

        downloaded_x = ratio_downloaded * w
        played_x = ratio_played * w

        # Draw total track (light gray)
        self.slider_canvas.create_line(
            handle_radius, center_y,
            w + handle_radius, center_y,
            width=bar_height,
            fill="#dddddd"
        )
        # Draw downloaded portion (medium gray)
        self.slider_canvas.create_line(
            handle_radius, center_y,
            downloaded_x + handle_radius, center_y,
            width=bar_height,
            fill="#cccccc"
        )
        # Draw played portion (red)
        self.slider_canvas.create_line(
            handle_radius, center_y,
            played_x + handle_radius, center_y,
            width=bar_height,
            fill="#888888"
        )
        # Draw the handle (circle)
        """self.slider_canvas.create_oval(
            played_x, center_y - handle_radius,
            played_x + 2 * handle_radius, center_y + handle_radius,
            fill="#888888", outline="white", width=2
        )"""

    # Mouse events
    def on_slider_press(self, event):
        self.dragging = True
        self._update_position_from_click(event.x)

    def on_slider_move(self, event):
        if self.dragging:
            self._update_position_from_click(event.x)

    def on_slider_release(self, event):
        self.dragging = False
        self._update_position_from_click(event.x, do_seek=True)

    def _update_position_from_click(self, x, do_seek=False):
        w = self.slider_canvas.winfo_width()
        x = max(0, min(w, x))  # clamp

        new_time = (x / w) * self.total_time
        self.played_time = new_time
        self.draw_slider()

        if do_seek and self.client:
            self.client.seek(self.played_time)

    # AudioClient callbacks
    def on_download_progress(self, cur_pages, duration):
        if cur_pages < len(self.client.times):
            downloaded_sec = self.client.times[cur_pages]
        else:
            downloaded_sec = 0.0
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
        self.current_playback_label.config(text=time_str(played_s))
        if self.total_time > 0:
            self.total_playback_label.config(text=time_str(total_s))
        if not self.dragging:
            self.draw_slider()

    # Helpers
    def update_status(self, text):
        print(f"Status: {text}")

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

        song_id = self.song_entry.get()
        time = 0

        self.client = AudioClient()
        self.client.set_progress_callback(self.on_download_progress)
        self.client.set_time_callback(self.on_playback_time)

        def run():
            try:
                self.update_status("Connecting to server...")
                self.client.ask_for_song(song_id, time)
                self.update_status(f"Requesting {song_id}, time={time}")
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
        self.current_playback_label.config(text="0:00")
        self.total_playback_label.config(text="0:00")
        self.draw_slider()
        while self.client.author == '':
            continue
        self.song_info_label.config(text=f'{self.client.song_name}\n{self.client.author}')

if __name__ == "__main__":
    app = AudioClientApp()
    app.mainloop()
