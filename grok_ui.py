import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image, ImageTk
import io
import threading
import pygame
import numpy as np
from audio_client_v2 import AudioClient

def time_str(time: float) -> str:
    """Convert time in seconds to a MM:SS string."""
    return f"{int(time / 60)}:{str(int(time) % 60).zfill(2)}"

class AppleMusicUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Apple Music-like Player")
        self.geometry("400x600")
        self.configure(bg='black')

        # Initialize AudioClient
        self.client = AudioClient()
        self.client.set_progress_callback(self.on_download_progress)
        self.client.set_time_callback(self.on_playback_time)
        self.stream_thread = None

        # Playback state variables
        self.current_tab = None
        self.previous_tab = None
        self.current_song = None
        self.playing = False
        self.total_time = 1.0
        self.downloaded_time = 0.0
        self.played_time = 0.0
        self.dragging = False

        # Create main layout frames
        self.content_frame = tk.Frame(self, bg='black')
        self.content_frame.grid(row=0, column=0, sticky='nsew')
        self.mini_player_frame = tk.Frame(self, bg='gray20', height=50)
        self.mini_player_frame.grid(row=1, column=0, sticky='ew')
        self.nav_bar_frame = tk.Frame(self, bg='gray10')
        self.nav_bar_frame.grid(row=2, column=0, sticky='ew')

        # Configure grid weights for resizing
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # Initialize tab frames
        self.library_frame = tk.Frame(self.content_frame, bg='black')
        self.search_frame = tk.Frame(self.content_frame, bg='black')
        self.now_playing_frame = tk.Frame(self.content_frame, bg='black')

        # Start with Library view
        self.current_tab = self.library_frame
        self.library_frame.pack(fill='both', expand=True)

        # Setup navigation bar
        self._setup_navigation_bar()

        # Setup mini-player
        self._setup_mini_player()

        # Setup views
        self._setup_library_frame()
        self._setup_search_frame()
        self._setup_now_playing_frame()

    def _setup_navigation_bar(self):
        """Configure the navigation bar with Library and Search buttons."""
        self.library_button = tk.Button(
            self.nav_bar_frame, text="Library",
            command=lambda: self.switch_tab(self.library_frame),
            bg='gray10', fg='white', relief='flat'
        )
        self.library_button.pack(side='left', fill='x', expand=True)
        self.search_button = tk.Button(
            self.nav_bar_frame, text="Search",
            command=lambda: self.switch_tab(self.search_frame),
            bg='gray10', fg='white', relief='flat'
        )
        self.search_button.pack(side='left', fill='x', expand=True)

    def _setup_mini_player(self):
        """Initialize the mini-player."""
        self.mini_player_label = tk.Label(
            self.mini_player_frame, text="No song playing",
            bg='gray20', fg='white'
        )
        self.mini_player_label.pack(fill='both', expand=True)
        self.mini_player_label.bind("<Button-1>", lambda e: self.switch_to_now_playing())

    def _setup_library_frame(self):
        """Configure the Library view with a song list."""
        self.song_list = tk.Listbox(
            self.library_frame, bg='black', fg='white',
            selectbackground='gray', font=('Helvetica', 12)
        )
        self.song_list.pack(fill='both', expand=True)
        self.song_list.bind("<Double-1>", self.play_selected_song)
        # Placeholder: Replace with actual songs from server
        for i in range(10):
            self.song_list.insert(tk.END, f"Song {i+1} - Artist {i+1} - Album {i+1}")

    def _setup_search_frame(self):
        """Configure the Search view with an entry and results list."""
        self.search_entry = tk.Entry(self.search_frame, bg='gray20', fg='white')
        self.search_entry.pack(fill='x', padx=5, pady=5)
        self.search_button = tk.Button(
            self.search_frame, text="Search", command=self.do_search,
            bg='gray10', fg='white'
        )
        self.search_button.pack(pady=5)
        self.search_results = tk.Listbox(
            self.search_frame, bg='black', fg='white',
            selectbackground='gray', font=('Helvetica', 12)
        )
        self.search_results.pack(fill='both', expand=True)
        self.search_results.bind("<Double-1>", self.play_selected_song)

    def _setup_now_playing_frame(self):
        """Configure the Now Playing view with controls and slider."""
        self.back_button = tk.Button(
            self.now_playing_frame, text="< Back", command=self.go_back,
            bg='gray10', fg='white'
        )
        self.back_button.pack(anchor='nw', padx=5, pady=5)
        self.album_art_label = tk.Label(self.now_playing_frame, bg='black')
        self.album_art_label.pack(pady=10)
        self.song_title_label = tk.Label(
            self.now_playing_frame, text="", bg='black', fg='white',
            font=('Helvetica', 16, 'bold')
        )
        self.song_title_label.pack()
        self.artist_album_label = tk.Label(
            self.now_playing_frame, text="", bg='black', fg='white',
            font=('Helvetica', 12)
        )
        self.artist_album_label.pack(pady=5)
        self.slider_canvas = tk.Canvas(
            self.now_playing_frame, height=10, bg='gray20', highlightthickness=0
        )
        self.slider_canvas.pack(fill='x', padx=10)
        self.slider_canvas.bind("<ButtonPress-1>", self.on_slider_press)
        self.slider_canvas.bind("<B1-Motion>", self.on_slider_move)
        self.slider_canvas.bind("<ButtonRelease-1>", self.on_slider_release)
        self.time_label = tk.Label(
            self.now_playing_frame, text="0:00 / 0:00", bg='black', fg='white'
        )
        self.time_label.pack(pady=5)
        self.control_frame = tk.Frame(self.now_playing_frame, bg='black')
        self.control_frame.pack(pady=10)
        self.prev_button = tk.Button(
            self.control_frame, text="<<", bg='gray10', fg='white',
            command=self.previous_song
        )
        self.prev_button.pack(side='left', padx=5)
        self.play_pause_button = tk.Button(
            self.control_frame, text="Play", bg='gray10', fg='white',
            command=self.toggle_play_pause
        )
        self.play_pause_button.pack(side='left', padx=5)
        self.next_button = tk.Button(
            self.control_frame, text=">>", bg='gray10', fg='white',
            command=self.next_song
        )
        self.next_button.pack(side='left', padx=5)

    def switch_tab(self, new_tab):
        """Switch the displayed tab."""
        if self.current_tab:
            self.current_tab.pack_forget()
        self.previous_tab = self.current_tab
        self.current_tab = new_tab
        new_tab.pack(fill='both', expand=True)

    def switch_to_now_playing(self):
        """Switch to Now Playing view when mini-player is clicked."""
        if self.current_song:
            self.switch_tab(self.now_playing_frame)

    def go_back(self):
        """Return to the previous tab from Now Playing."""
        if self.previous_tab:
            self.switch_tab(self.previous_tab)

    def play_selected_song(self, event):
        """Play the song selected from Library or Search."""
        widget = event.widget
        selection = widget.curselection()
        if selection:
            song_info = widget.get(selection[0])
            song_id = song_info.split(" - ")[0].replace("Song ", "")
            self.start_playing_song(song_id, song_info)

    def start_playing_song(self, song_id, song_info):
        """Start streaming the selected song with AudioClient."""
        if self.stream_thread and self.stream_thread.is_alive():
            if not self.client.stop():
                self.client.playing = False
            print('wainting for stream thread to finish')
            self.stream_thread.join()
            print('stream thread finished')

        self.current_song = {
            "id": song_id,
            "title": song_info.split(" - ")[0],
            "artist": song_info.split(" - ")[1],
            "album": song_info.split(" - ")[2],
            "cover": None
        }

        def run():
            try:
                self.client.ask_for_song(song_id, 0)
                self.client.receive_stream()
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("Error", str(e)))

        self.stream_thread = threading.Thread(target=run, daemon=True)
        self.stream_thread.start()

        # Check for metadata after starting the stream
        self.after(100, self.check_metadata)

    def check_metadata(self):
        """Update UI with song metadata when available."""
        if self.client.song_name:
            self.current_song["title"] = self.client.song_name
            self.current_song["artist"] = self.client.author
            self.current_song["album"] = self.client.album
            if self.client.cover:
                self.current_song["cover"] = self.client.cover
                self.update_album_art()
            self.update_mini_player()
            self.update_now_playing()
        else:
            self.after(100, self.check_metadata)

    def update_album_art(self):
        """Display album art in Now Playing view."""
        if self.current_song["cover"]:
            img = io.BytesIO(self.current_song["cover"])
            pil_img = Image.open(img)
            self.album_art_tk = ImageTk.PhotoImage(pil_img)
            self.album_art_label.config(image=self.album_art_tk)

    def update_mini_player(self):
        """Update mini-player with current song info."""
        for widget in self.mini_player_frame.winfo_children():
            widget.destroy()
        if self.current_song:
            title_label = tk.Label(
                self.mini_player_frame, text=self.current_song["title"],
                bg='gray20', fg='white'
            )
            title_label.pack(side='left', padx=5)
            play_pause = tk.Button(
                self.mini_player_frame, text="Pause" if self.playing else "Play",
                bg='gray20', fg='white', command=self.toggle_play_pause
            )
            play_pause.pack(side='right', padx=5)
            self.mini_player_frame.bind("<Button-1>", lambda e: self.switch_to_now_playing())
        else:
            tk.Label(self.mini_player_frame, text="No song playing", bg='gray20', fg='white').pack(fill='both', expand=True)

    def update_now_playing(self):
        """Update Now Playing view with current song details."""
        if self.current_song:
            self.song_title_label.config(text=self.current_song["title"])
            self.artist_album_label.config(text=f"{self.current_song['artist']} - {self.current_song['album']}")
            self.time_label.config(text=f"{time_str(self.played_time)} / {time_str(self.total_time)}")
            self.draw_slider()

    def toggle_play_pause(self):
        """Toggle playback state."""
        if self.client:
            self.client.pause()
            self.playing = not self.playing
            self.play_pause_button.config(text="Pause" if self.playing else "Play")
            # Sync mini-player button
            for widget in self.mini_player_frame.winfo_children():
                if isinstance(widget, tk.Button):
                    widget.config(text="Pause" if self.playing else "Play")

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
        """Update playback position based on slider interaction."""
        w = self.slider_canvas.winfo_width()
        x = max(0, min(w, x))  # Clamp to canvas width
        new_time = (x / w) * self.total_time
        self.played_time = new_time
        self.draw_slider()
        if do_seek and self.client:
            self.client.seek(self.played_time)

    def draw_slider(self):
        """Draw the custom playback slider."""
        self.slider_canvas.delete("all")
        w = self.slider_canvas.winfo_width()
        h = self.slider_canvas.winfo_height()
        ratio_downloaded = min(max(self.downloaded_time / self.total_time, 0.0), 1.0)
        ratio_played = min(max(self.played_time / self.total_time, 0.0), 1.0)
        downloaded_x = ratio_downloaded * w
        played_x = ratio_played * w
        self.slider_canvas.create_rectangle(0, 0, w, h, fill="#dddddd")  # Total
        self.slider_canvas.create_rectangle(0, 0, downloaded_x, h, fill="#cccccc")  # Downloaded
        self.slider_canvas.create_rectangle(0, 0, played_x, h, fill="#888888")  # Played

    def on_download_progress(self, cur_pages, duration):
        """Callback for download progress updates."""
        if cur_pages < len(self.client.times):
            downloaded_sec = self.client.times[cur_pages]
        else:
            downloaded_sec = 0.0
        self.after(0, self._update_download, downloaded_sec, duration)

    def _update_download(self, downloaded_sec, total_sec):
        """Update download progress UI."""
        if total_sec < 1:
            total_sec = 1
        self.total_time = total_sec
        self.downloaded_time = downloaded_sec
        self.draw_slider()

    def on_playback_time(self, played_s, total_s):
        """Callback for playback time updates."""
        self.after(0, self._update_playback, played_s, total_s)

    def _update_playback(self, played_s, total_s):
        """Update playback time UI."""
        if total_s < 1:
            total_s = 1
        self.total_time = total_s
        self.played_time = played_s
        self.time_label.config(text=f"{time_str(played_s)} / {time_str(total_s)}")
        if not self.dragging:
            self.draw_slider()

    def do_search(self):
        """Perform a search and display results."""
        query = self.search_entry.get()
        self.search_results.delete(0, tk.END)
        # Placeholder: Replace with server query using protocol
        for i in range(5):
            self.search_results.insert(tk.END, f"Result {i+1} - Artist {i+1} - Album {i+1}")

    def previous_song(self):
        """Placeholder for previous song functionality."""
        pass

    def next_song(self):
        """Placeholder for next song functionality."""
        pass

if __name__ == "__main__":
    app = AppleMusicUI()
    app.mainloop()