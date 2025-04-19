import socket
import threading
import tkinter
from tkinter import messagebox
import customtkinter as ctk


import protocol
from client import PlaybackController
from custom_widgets import *


def time_str(time: float) -> str:
    return f"{int(time / 60)}:{str(int(time) % 60).zfill(2)}"


class AudioClientApp(ctk.CTk):
    def __init__(self, token, gen_sock):
        super().__init__()
        self.title("Muniz Player sigmaboii123")
        self.geometry("400x160")
        self.iconbitmap("favicon.ico")
        self.primary_ui = "#A8DADC"
        self.secondary_accent = "#F4C2C2"
        self.success = "#C4E1C1"
        self.background = "#E8E8FA"
        self.prime_text = "#36454F"
        self.second_text = "#A0A0A0"
        self.configure(fg_color=self.background)

        self.resizable(False, False)
        self.controller = PlaybackController(gen_sock, token, self.disable_pause_button, self.enable_pause_button
                                             , self.on_playback_time, self.update_song_label, self.update_cover
                                             , self.draw_slider_callback, self.update_playlists)

        self.song_info_label = ctk.CTkLabel(self, text="song name\n author", text_color=self.prime_text, font=("Nunito", 12))
        self.song_info_label.grid(row=0, rowspan=2, column=1, columnspan=3, sticky='ew', padx=5, pady=5)

        pil_img = Image.open("default.jpg")
        self.cover_tk = ctk.CTkImage(pil_img, size=(64, 64))

        self.cover_label = ctk.CTkLabel(self, image=self.cover_tk, text='')
        self.cover_label.grid(row=0, column=0, columnspan=2, sticky='w', rowspan=2, padx=10, pady=10)

        self.make_middle_frame()

        # Canvas that will serve as our slider
        self.slider_canvas = ctk.CTkCanvas(self, width=300, height=10, bg=self.cget("bg"), highlightthickness=0)
        self.slider_canvas.grid(row=3, column=1, columnspan=3, padx=5)
        # Bind <Configure> so we know when the canvas size is finalized
        self.slider_canvas.bind("<Configure>", self.on_canvas_configure)

        # Bind mouse events for seeking
        self.slider_canvas.bind("<ButtonPress-1>", self.on_slider_press)
        self.slider_canvas.bind("<B1-Motion>", self.on_slider_move)
        self.slider_canvas.bind("<ButtonRelease-1>", self.on_slider_release)
        self.dragging = False

        # Playback time label
        self.current_playback_label = ctk.CTkLabel(self, text="0:00", text_color=self.prime_text, font=("Nunito", 12))
        self.current_playback_label.grid(row=3, column=0, padx=10)

        self.total_playback_label = ctk.CTkLabel(self, text="0:00", text_color=self.prime_text, font=("Nunito", 12))
        self.total_playback_label.grid(row=3, column=4, padx=10)

        # Buttons
        self.volume_button = ctk.CTkButton(self, text="🔊", width=10,
                                           fg_color=self.background, text_color=self.prime_text, font=("Nunito", 12)
                                           , hover_color=self.primary_ui)
        self.volume_button.grid(row=4, column=0, sticky='e', padx=5,)
        self.volume_popup = VolumePopup(self.volume_button, self)
        self.volume_button.configure(command=self.volume_popup.show)

        self.prev_button = ctk.CTkButton(self, text="⏮", command=self.controller.prev_button, width=15, height=40,
                                           fg_color=self.background, text_color=self.prime_text, font=("Nunito", 16)
                                           , hover_color=self.primary_ui)
        self.prev_button.grid(row=4, column=1, sticky='e', padx=5)

        self.pause_button = ctk.CTkButton(self, text="⏸︎", command=self.controller.pause_stream, state=ctk.DISABLED, width=15, height=40,
                                           fg_color=self.background, text_color=self.prime_text, font=("Nunito", 16)
                                           , hover_color=self.primary_ui, text_color_disabled=self.second_text)
        self.pause_button.grid(row=4, column=2, sticky='', padx=5)

        self.start_button = ctk.CTkButton(self, text="⏭", command=self.controller.start_button, width=15, height=40,
                                           fg_color=self.background, text_color=self.prime_text, font=("Nunito", 16)
                                           , hover_color=self.primary_ui)
        self.start_button.grid(row=4, column=3, sticky='w', padx=5)

        self.toggle_button = ctk.CTkButton(self, text="☰", command=self.toggle_middle_frame, width=10,
                                           fg_color=self.background, text_color=self.prime_text, font=("Nunito", 12)
                                           , hover_color=self.primary_ui)
        self.toggle_button.grid(row=4, column=4, sticky='w', padx=5)

    def make_middle_frame(self):
        self.tab_view = ctk.CTkTabview(self, width=380, height=240, fg_color=self.background, command=self.on_tab_change)
        self.tab_view.grid(row=2, column=0, sticky="ew", padx=5, pady=5, columnspan=6)
        self.tab_view.add('songs')
        self.tab_view.tab('songs').configure(fg_color=self.tab_view.cget("fg_color"))
        self.tab_view.add('queue')
        self.tab_view.tab('queue').configure(fg_color=self.tab_view.cget("fg_color"))
        self._build_songs_tab(self.tab_view.tab("songs"))
        self._build_queue_tab(self.tab_view.tab("queue"))

        self.tab_view.grid_remove()

    def on_tab_change(self):
        if self.tab_view.get() == "queue":
            self.load_queue()

    def _build_songs_tab(self, parent):
        self.search_frame = ctk.CTkFrame(parent,
                                    corner_radius=8,
                                    fg_color=("gray70", "gray30"),
                                    height=32)

        self.search_frame.grid(row=0, column=0, sticky="e", padx=10, pady=5)
        self.search_entry = ctk.CTkEntry(self.search_frame,
                                  border_width=0,
                                  fg_color="transparent",
                                  placeholder_text="Type and press Enter…")
        self.search_entry.pack(side="left", fill="both", expand=True, padx=(8, 0))
        self.search_entry.bind("<Return>", self.search_songs)

        # the icon-button on the right
        self.icon_btn = ctk.CTkButton(self.search_frame,
                                 text="🔍",
                                 width=32, height=32,
                                 fg_color="transparent",
                                 hover_color=("gray80", "gray40"),
                                 command=lambda: self.search_songs(None))
        self.icon_btn.pack(side="right", padx=4)

        self.canvas = ctk.CTkScrollableFrame(parent, height=100, width=360, orientation="horizontal"
                                             , fg_color=parent.cget("fg_color"))
        self.canvas.grid(row=1, column=0, sticky="nsew", pady=10, columnspan=2)

        # Second ca nvas and its scrollbar
        self.canvas2 = ctk.CTkScrollableFrame(parent, height=100, orientation="horizontal"
                                               , fg_color=parent.cget("fg_color"))
        self.canvas2.grid(row=2, column=0, sticky="nsew", pady=10, columnspan=2)

    def _add_song_row(self, song):
        # Container frame for a single song
        row = tk.Frame(self.queue_frame, bg=self.cget("fg_color"))
        row.pack(fill="x", pady=2)

        try:
            img_data = base64.b64decode(song.coverb64)
            song_img = Image.open(io.BytesIO(img_data))
        except Exception:
            print("Error loading image, using default")
            song_img = Image.new("RGB", (40, 40), color="gray")
        song_img.thumbnail((40, 40))
        song_img_tk = ImageTk.PhotoImage(song_img)
        self.queue_frame.covers.append(song_img_tk)

        # Image label for song cover
        img_label = tk.Label(row, image=song_img_tk, bg=self.cget("fg_color"))
        img_label.pack(side="left", padx=5)

        # Text label for song name and author
        song_text = f"{song.name} - {song.author}"
        text_label = tk.Label(row, text=song_text, bg=self.cget("fg_color"), fg=self.prime_text, anchor="w")
        text_label.pack(side="left", fill="x", expand=True)

    def _build_queue_tab(self, parent):
        self.queue_frame = ctk.CTkScrollableFrame(parent, height=294, width=354, orientation="vertical"
                                                   , fg_color=parent.cget("fg_color"))
        self.queue_frame.covers = []
        self.queue_frame.grid(row=0, column=0, sticky="e", pady=10, columnspan=2)

    def load_queue(self):
        for widget in self.queue_frame.winfo_children():
            widget.destroy()
        for song in self.controller.song_queue.queue:
            self._add_song_row(song)

    def search_songs(self, event):
        search_term = self.search_entry.get()
        if search_term:
            songs = self.controller.search(search_term)
            if songs:
                print('displaying songs', songs)
                self.display_songs_horizontaly(songs, self.canvas)

    def disable_pause_button(self):
        self.after(0, lambda: self.pause_button.configure(state=tk.DISABLED))

    def enable_pause_button(self):
        self.after(0, lambda: self.pause_button.configure(state=tk.NORMAL))

    def click_playlist_frame(self, event):
        PlaylistInfoFrame(self, event.widget.playlist)

    def click_add_playlist(self, event):

        PlaylistFrame(self)

    def show_playlist_action_menu(self, event):
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label='play', command=lambda: self.controller.play_playlist(event.widget.playlist))
        menu.add_command(label='delete', command=lambda: self.controller.delete_playlist(event))
        menu.post(event.x_root, event.y_root)

    def show_song_action_menu(self, event):
        menu = tk.Menu(self, tearoff=0)

        playlist_menu = tk.Menu(menu, tearoff=0)
        for playlist in self.controller.playlists:
            playlist_menu.add_command(
                label=playlist.name,
                command=lambda x=playlist: self.controller.add_to_playlist(event.widget.song, x)
            )
        menu.add_cascade(label="Add to Playlist", menu=playlist_menu)
        menu.post(event.x_root, event.y_root)

    def display_songs_horizontaly(self, songs, inner_frame):

        for w in inner_frame.winfo_children():  # clear old widgets
            w.destroy()

        for col, song in enumerate(songs):
            # Song block
            song_frame = tk.Frame(inner_frame, padx=5, pady=5, bg=inner_frame.cget("fg_color"))
            song_frame.song = song
            song_frame.grid(row=0, column=col, padx=5, pady=5)

            # Cover image
            cover_data = base64.b64decode(song.coverb64)
            image = Image.open(io.BytesIO(cover_data))
            image.thumbnail((100, 100))
            photo = ImageTk.PhotoImage(image)

            label_image = tk.Label(song_frame, image=photo, bg=inner_frame.cget("fg_color"))
            label_image.image = photo  # prevent
            label_image.song = song
            label_image.grid(row=0, column=0)

            # Title
            nn = song.name if len(song.name) < 12 else f"{song.name[:10]}..."
            label_title = tk.Label(song_frame, text=nn, bg=inner_frame.cget("fg_color"))
            label_title.song = song

            # ToolTip
            ToolTip(label_title, song.name)
            label_title.grid(row=1, column=0)

            for widget in (song_frame, label_title, label_image):
                widget.bind("<Button-1>", self.controller.click_song_frame)
                widget.bind("<Button-3>", self.show_song_action_menu)

    def display_playlists_horizontaly(self, playlists, inner_frame):
        self.controller.playlists = playlists

        for w in inner_frame.winfo_children():  # clear old widgets
            w.destroy()

        for col, playlist in enumerate(playlists):
            playlist_frame, label_title, label_image = self._display_playlist_item(inner_frame, playlist, col)

            for widget in (playlist_frame, label_title, label_image):
                widget.bind("<Button-1>", self.click_playlist_frame)
                widget.bind("<Button-3>", self.show_playlist_action_menu)

        add_playlist_frame = tk.Frame(inner_frame, padx=5, pady=5, bg=inner_frame.cget("fg_color"))
        add_playlist_frame.grid(row=0, column=len(playlists), padx=5, pady=5)
        # Cover image
        image = Image.open("default.jpg")
        image.thumbnail((100, 100))
        photo = ImageTk.PhotoImage(image)

        label_image = tk.Label(add_playlist_frame, image=photo, bg=inner_frame.cget("fg_color"))
        label_image.image = photo
        label_image.grid(row=0, column=0)

        # Title
        label_title = tk.Label(add_playlist_frame, text='new', bg=inner_frame.cget("fg_color"))
        label_title.grid(row=1, column=0)

        add_playlist_frame.bind("<Button-1>", self.click_add_playlist)
        label_title.bind("<Button-1>", self.click_add_playlist)
        label_image.bind("<Button-1>", self.click_add_playlist)

    def _display_playlist_item(self, inner_frame, playlist, col):
        # Song block
        playlist_frame = tk.Frame(inner_frame, padx=5, pady=5, bg=inner_frame.cget("fg_color"))
        playlist_frame.playlist = playlist
        playlist_frame.grid(row=0, column=col, padx=5, pady=5)

        # Cover image
        cover_data = base64.b64decode(playlist.coverb64)
        image = Image.open(io.BytesIO(cover_data))
        image.thumbnail((100, 100))
        photo = ImageTk.PhotoImage(image)

        label_image = tk.Label(playlist_frame, image=photo, bg=inner_frame.cget("fg_color"))
        label_image.image = photo  # prevent
        label_image.playlist = playlist
        label_image.grid(row=0, column=0)

        # Title
        nn = playlist.name if len(playlist.name) < 12 else f"{playlist.name[:10]}..."
        label_title = tk.Label(playlist_frame, text=nn, bg=inner_frame.cget("fg_color"))
        label_title.playlist = playlist
        ToolTip(label_title, playlist.name)
        label_title.grid(row=1, column=0)

        return playlist_frame, label_title, label_image

    def fetch_and_display(self):  # change to only display, fetch part will be in different file
        try:
            songs, playlists = self.controller.fetch_recommendations()
            # Schedule UI updates in main thread
            self.after(0, lambda: self.show_songs(songs, playlists))

        except Exception as e:
            print(f"Error fetching songs: {e}")
            print(e)

    def toggle_middle_frame(self):
        if self.tab_view.winfo_ismapped():
            self.tab_view.grid_remove()
            self.geometry("400x160")
        else:
            self.geometry("400x530")
            self.tab_view.grid()

            threading.Thread(target=self.fetch_and_display, daemon=True).start()

    def show_songs(self, songs, playlists):
        # Scrollable canvas

        self.display_songs_horizontaly(songs, self.canvas)
        if self.controller.playlists != playlists or self.controller.playlists == []:
            self.display_playlists_horizontaly(playlists, self.canvas2)

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

        ratio_downloaded = min(max(self.controller.downloaded_time / self.controller.total_time, 0.0), 1.0)
        ratio_played = min(max(self.controller.played_time / self.controller.total_time, 0.0), 1.0)

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

    # Mouse events
    def on_slider_press(self, event):
        self.dragging = True
        self._update_position_from_click(event.x)

    def on_slider_move(self, event):
        if self.dragging:
            playback_time = (event.x / self.slider_canvas.winfo_width()) * self.controller.total_time
            self.controller.played_time = playback_time
            self._update_position_from_click(event.x)

    def on_slider_release(self, event):
        self.dragging = False
        self._update_position_from_click(event.x, do_seek=True)

    def _update_position_from_click(self, x, do_seek=False):
        w = self.slider_canvas.winfo_width()
        x = max(0, min(w, x))  # clamp

        new_time = (x / w) * self.controller.total_time
        self.played_time = new_time
        self.draw_slider()

        if do_seek and self.client:
            self.controller.seek(self.played_time)

    def on_playback_time(self, played_s, total_s):
        self.after(0, self._update_playback, played_s, total_s)

    def _update_playback(self, played_s, total_s):
        if total_s < 1:
            total_s = 1
        self.controller.total_time = total_s
        self.controller.played_time = played_s
        self.current_playback_label.configure(text=time_str(played_s))
        if self.controller.total_time > 0:
            self.total_playback_label.configure(text=time_str(total_s))
        if not self.dragging:
            self.draw_slider()

    def draw_slider_callback(self):
        self.after(0, self.draw_slider)

    def update_song_label(self):
        self.song_info_label.configure(
            text=f"{self.controller.client.song_name}\n{self.controller.client.author} - {self.controller.client.album}"
        )

    def update_cover(self):
        img = io.BytesIO(self.controller.client.cover)
        pil_img = Image.open(img)
        cover = ctk.CTkImage(pil_img, size=(64, 64))
        self.after(0, lambda: self.cover_label.configure(image=cover))
        self.cover_tk = cover

    def update_playlists(self):
        self.display_playlists_horizontaly(self.controller.playlists, self.canvas2)


if __name__ == "__main__":
    gen_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    gen_sock.connect(("localhost", 5001))
    data = f"1~1".encode()
    gen_sock.send(protocol.create_msg('LOGI', data))
    cmd, resp = protocol.get_msg(gen_sock)
    response, token = resp.decode().split('~')
    app = AudioClientApp(token, gen_sock)
    app.mainloop()
    gen_sock.send(protocol.create_msg('EXIT', b''))
