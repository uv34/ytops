import tkinter as tk
from tkinter import ttk, messagebox
import threading
from PIL import Image, ImageTk
import io
import socket
import protocol
from audio_client_v2 import AudioClient
import base64, json

def time_str(time: float) -> str:
    return f"{int(time / 60)}:{str(int(time) % 60).zfill(2)}"

class ToolTip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tip_window = None
        # Bindings
        self.widget.bind("<Enter>", self.show_tip)
        self.widget.bind("<Leave>", self.hide_tip)

    def show_tip(self, event=None):
        # Avoid showing if the tip window already exists or if there is no text
        if self.tip_window or not self.text:
            return
        # Calculate the position of the tooltip
        x, y, cx, cy = self.widget.bbox("insert") if self.widget.bbox("insert") else (0, 0, 0, 0)
        x += self.widget.winfo_rootx() + 25
        y += self.widget.winfo_rooty() + 20

        # Create a top-level window to act as the tooltip
        self.tip_window = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)  # Remove window decorations
        tw.wm_geometry(f"+{x}+{y}")

        label = tk.Label(tw, text=self.text, justify=tk.LEFT,
                         background="#aaaaaa", relief=tk.SOLID, borderwidth=1,
                         font=("tahoma", "8", "normal"))
        label.pack(ipadx=1)

    def hide_tip(self, event=None):
        # Destroy the tooltip window if it exists
        if self.tip_window:
            self.tip_window.destroy()
            self.tip_window = None


class AudioClientApp(tk.Tk):
    def __init__(self, token, gen_sock):
        super().__init__()
        self.title("Ogg Vorbis Client (YouTube-like Slider)")
        self.geometry("400x150")
        self.token = token
        self.resizable(False, False)
        self.gen_socket = gen_sock

        style = ttk.Style(self)
        style.theme_use("clam")
        #cover
        pil_img = Image.open("default.jpg")
        self.cover_tk = ImageTk.PhotoImage(pil_img)

        self.cover_label = tk.Label(self, image=self.cover_tk, )
        self.cover_label.grid(row=0, column=0, columnspan=2, sticky='w', rowspan=2, padx=10, pady=10)

        # Song
        tk.Label(self, text="Song:").grid(row=0, column=1, sticky='e', padx=5, pady=5)
        self.song_entry = tk.Entry(self)
        self.song_entry.insert(0, "1")
        self.song_entry.grid(row=0, column=2, padx=5, pady=5)

        self.song_info_label = tk.Label(self, text="song name\n author")
        self.song_info_label.grid(row=1, column=1, columnspan=2, sticky='', padx=5, pady=5)

        self.middle_frame = tk.Frame(self, height=240, width=380)
        self.middle_frame.grid(row=2, column=0, sticky="ew", padx=10, pady=5, columnspan=4)
        self.middle_frame.grid_remove()

        # Buttons
        self.start_button = tk.Button(self, text="Start/Stop", command=self.start_button)
        self.start_button.grid(row=3, column=1, sticky='e', padx=5, pady=5)

        self.pause_button = tk.Button(self, text="Pause/Resume", command=self.pause_stream, state=tk.DISABLED)
        self.pause_button.grid(row=3, column=2, sticky='w', padx=5, pady=5)

        self.toggle_button = tk.Button(self, text="Ham", command=self.toggle_middle_frame)
        self.toggle_button.grid(row=3, column=3, sticky='w', padx=5, pady=5)

        # Canvas that will serve as our slider
        self.slider_canvas = tk.Canvas(self, width=300, height=10, bg=self.cget("bg"), highlightthickness=0)
        self.slider_canvas.grid(row=4, column=1, columnspan=2, padx=5, pady=(10,5))
        # Bind <Configure> so we know when the canvas size is finalized
        self.slider_canvas.bind("<Configure>", self.on_canvas_configure)

        # Bind mouse events for seeking
        self.slider_canvas.bind("<ButtonPress-1>", self.on_slider_press)
        self.slider_canvas.bind("<B1-Motion>", self.on_slider_move)
        self.slider_canvas.bind("<ButtonRelease-1>", self.on_slider_release)
        self.dragging = False


        # Playback time label
        self.current_playback_label = tk.Label(self, text="0:00")
        self.current_playback_label.grid(row=4, column=0, padx=10)

        self.total_playback_label = tk.Label(self, text="0:00")
        self.total_playback_label.grid(row=4, column=3, padx=10)


        # Internal state
        self.client = None
        self.stream_thread = None

        self.total_time = 1.0
        self.downloaded_time = 0.0
        self.played_time = 0.0

    def click_song_frame(self, event):
        self.stop_stream()
        self.start_after_stop(event.widget.song_id)

    def start_after_stop(self, song_id):
        if self.stream_thread and self.stream_thread.is_alive():
            self.after(100, self.start_after_stop, song_id)
        else:
            self.start_stream(song_id)

    def display_songs_horizontaly(self, songs, inner_frame):
        for col, (song_id, song_data) in enumerate(songs.items()):
            name, author, album, coverdatab64 = song_data

            # Song block
            song_frame = tk.Frame(inner_frame, padx=5, pady=5, bg="#CCCCCC")
            song_frame.song_id = song_id
            song_frame.grid(row=0, column=col, padx=5, pady=5)

            # Cover image
            cover_data = base64.b64decode(coverdatab64)
            image = Image.open(io.BytesIO(cover_data))
            image.thumbnail((100, 100))
            photo = ImageTk.PhotoImage(image)

            label_image = tk.Label(song_frame, image=photo, bg="#CCCCCC")
            label_image.image = photo  # prevent GC
            label_image.song_id = song_id
            label_image.grid(row=0, column=0)

            # Title
            nn = name if len(name) < 12 else f"{name[:10]}..."
            label_title = tk.Label(song_frame, text=nn, bg="#CCCCCC")
            label_title.song_id = song_id
            ToolTip(label_title, name)
            label_title.grid(row=1, column=0)

            song_frame.bind("<Button-1>", self.click_song_frame)
            label_title.bind("<Button-1>", self.click_song_frame)
            label_image.bind("<Button-1>", self.click_song_frame)

    def fetch_and_display(self):
        try:
            self.gen_socket.send(protocol.create_msg("RECM", self.token.encode() + b'~'))
            msg, data = protocol.get_msg(self.gen_socket)
            songs = json.loads(data)
            print("Fetched songs")

            # Schedule UI updates in main thread
            self.after(0, lambda: self.show_songs(songs))

        except Exception as e:
            print(f"Error fetching songs: {e}")
            self.after(0, lambda: messagebox.showerror("Error", str(e)))

    def toggle_middle_frame(self):
        if self.middle_frame.winfo_ismapped():
            self.middle_frame.grid_remove()
            self.geometry("400x150")
        else:
            self.geometry("400x400")
            self.middle_frame.grid()

            threading.Thread(target=self.fetch_and_display, daemon=True).start()

    def show_songs(self, songs):
        # Clear previous content
        for widget in self.middle_frame.winfo_children():
            widget.destroy()

        # Scrollable canvas
        canvas = tk.Canvas(self.middle_frame, height=120, bg="#CCCCCC")
        canvas.grid(row=0, column=0, sticky="nsew")

        h_scrollbar = tk.Scrollbar(self.middle_frame, orient="horizontal", command=canvas.xview)
        h_scrollbar.grid(row=1, column=0, sticky="ew")
        canvas.configure(xscrollcommand=h_scrollbar.set)

        inner_frame = tk.Frame(canvas, bg="#CCCCCC")
        canvas.create_window((0, 0), window=inner_frame, anchor="nw")

        def on_configure(event):  # update the canvas when its being scrolled
            canvas.configure(scrollregion=canvas.bbox("all"))

        inner_frame.bind("<Configure>", on_configure)

        self.display_songs_horizontaly(songs, inner_frame)

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
        # Draw played portion
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
        print('start stream')
        self.start_stream(self.song_entry.get())

    def start_stream(self, id):
        if self.stream_thread and self.stream_thread.is_alive():
            messagebox.showinfo("Info", "Already streaming!")
            return

        song_id = id
        time = 0

        self.client = AudioClient()
        self.client.set_progress_callback(self.on_download_progress)
        self.client.set_time_callback(self.on_playback_time)
        print('audio client created')

        def run():
            try:
                self.update_status("Connecting to server...")
                self.client.ask_for_song(song_id, time, self.token)
                self.update_status(f"Requesting {song_id}, time={time}")
                self.client.receive_stream()
                self.update_status("Stream ended.")
                self.client = None
            except Exception as e:
                messagebox.showerror("Error", str(e))
                self.update_status(f"Error: {e}")
                print(f"ErroRRRR")
            finally:
                self.pause_button.config(state=tk.DISABLED)
                self.stream_thread = None

        # Start background thread to avoid blocking UI
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

        def check_metadata():
            if self.client and self.client.cover != b'':
                self.song_info_label.config(
                    text=f"{self.client.song_name}\n{self.client.author} - {self.client.album}"
                )
                if self.client.cover:
                    try:
                        img = io.BytesIO(self.client.cover)
                        pil_img = Image.open(img)
                        self.cover_tk = ImageTk.PhotoImage(pil_img)
                        self.cover_label.config(image=self.cover_tk)
                    except Exception as e:
                        print(f"Error loading cover image: {e}")
                return
            # If metadata not there yet, keep checking
            if self.client:
                self.after(100, check_metadata)

        self.after(100, check_metadata)


if __name__ == "__main__":
    gen_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    gen_sock.connect(("localhost", 5001))
    data = f"uv3~3".encode()
    gen_sock.send(protocol.create_msg('LOGI', data))
    cmd, resp = protocol.get_msg(gen_sock)
    response, token = resp.decode().split('~')
    app = AudioClientApp(token, gen_sock)
    app.mainloop()
