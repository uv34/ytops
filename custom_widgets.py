import threading
import tkinter as tk
import customtkinter as ctk
from tkinter import filedialog
from PIL import Image, ImageTk
import base64
import io
from datetime import datetime
from song import *
import math


class HexagonRadar(tk.Canvas):
    def __init__(self, master, size=200, stats=None, labels=None, **kw):
        super().__init__(master, width=size, height=size,  **kw)
        self.size = size
        self.stats = stats or [0, 0, 0, 0, 0, 0]
        # labels: list of six strings
        self.labels = labels or ["ACS","DNC","ENR","INS","LIV","SPC"]
        self.draw_radar()

    def draw_radar(self):
        cx = cy = self.size/2
        radius = self.size*0.4
        angles = [math.radians(90 - i*60) for i in range(6)]
        # outer hexagon points
        outer = [(cx + radius*math.cos(a), cy - radius*math.sin(a)) for a in angles]
        # inner polygon points (scaled by stats)
        inner = [(cx + radius*self.stats[i]*math.cos(a),
                  cy - radius*self.stats[i]*math.sin(a))
                 for i,a in enumerate(angles)]
        # draw web
        for p in outer:
            self.create_line(cx, cy, p[0], p[1], fill="#444")
        self.create_polygon(outer, outline="#888", fill="", width=2)
        # draw stat area
        self.create_polygon(inner, outline="#fc0", fill="#fc0", stipple="gray25")
        # draw labels
        for i,(x,y) in enumerate(outer):
            lbl = self.labels[i]
            # push label slightly outward
            lx = cx + (radius+15)*math.cos(angles[i])
            ly = cy - (radius+15)*math.sin(angles[i])
            self.create_text(lx, ly, text=lbl, fill="white", font=("TkDefaultFont", 10))


class BaseFrame:
    def __init__(self, parent, width, height, bg="#1e1e1e", bd=2, relief="solid"):
        self.parent = parent
        self.frame_width = width
        self.frame_height = height
        self.frame = tk.Frame(parent, bg=bg, bd=bd, relief=relief)
        self.create_widgets()
        self.place_frame()

    def create_widgets(self):
        raise NotImplementedError("Subclasses must implement create_widgets")

    def place_frame(self):
        self.parent.update_idletasks()
        pw = self.parent.winfo_width()
        ph = self.parent.winfo_height()
        x = (pw - self.frame_width) // 2
        y = (ph - self.frame_height) // 2
        self.frame.place(x=x, y=y, width=self.frame_width, height=self.frame_height)

    def destroy(self):
        self.frame.destroy()


class SocialFrame(BaseFrame):
    def __init__(self, parent, social_profile):
        self.profile_data = social_profile
        super().__init__(parent, width=300, height=360)

    def create_widgets(self):
        uname = self.profile_data['profile'][0][0]
        last_time = self.profile_data['profile'][0][1]
        time_str = (
            last_time.strftime("%Y-%m-%d %H:%M:%S")
            if isinstance(last_time, datetime)
            else str(last_time)
        )

        # --- Header ---
        tk.Label(self.frame,
                 text=uname,
                 font=("Arial", 14, "bold"),
                 fg="white",
                 bg="#1e1e1e")\
          .place(relx=0.5, y=20, anchor="n")
        tk.Label(self.frame,
                 text=f"Created: {time_str}",
                 font=("Arial", 10),
                 fg="#cccccc",
                 bg="#1e1e1e")\
          .place(relx=0.5, y=45, anchor="n")

        # --- Single Scrollable Area (hexagon + lists) ---
        scroll = ctk.CTkScrollableFrame(
            master=self.frame,
            width=260, height=230,
            fg_color="#1e1e1e",
            scrollbar_button_color="#444444",
            scrollbar_button_hover_color="#555555"
        )
        scroll.place(relx=0.5, y=75, anchor="n")

        # --- Hexagon stats at top of scroll ---
        stats_vals = self.profile_data['profile'][0][2:]
        hexa = HexagonRadar(
            scroll,
            size=200,
            stats=stats_vals,
            labels=["ACS","DNC","ENR","INS","LIV","SPC"],
            bg="#1e1e1e",
            highlightthickness=0
        )
        hexa.pack(pady=(8, 16))

        # --- Songs Section ---
        ctk.CTkLabel(master=scroll,
                     text="Latest listens:",
                     text_color="white",
                     fg_color="#1e1e1e",
                     anchor="w",
                     font=("Arial", 11, "underline"))\
           .pack(fill="x", padx=4, pady=(0,4))
        for s in self.profile_data['songs']:
            ctk.CTkLabel(master=scroll,
                         text=f"{s.name} — {s.author}",
                         text_color="white",
                         fg_color="#2e2e2e",
                         anchor="w",
                         height=28,
                         corner_radius=0)\
               .pack(fill="x", padx=8, pady=2)

        # --- Playlists Section ---
        ctk.CTkLabel(master=scroll,
                     text="Playlists:",
                     text_color="white",
                     fg_color="#1e1e1e",
                     anchor="w",
                     font=("Arial", 11, "underline"))\
           .pack(fill="x", padx=4, pady=(12,4))
        for pl in self.profile_data['playlists']:
            lbl = ctk.CTkLabel(master=scroll,
                               text=pl.name,
                               text_color="white",
                               fg_color="#2e2e2e",
                               anchor="w",
                               height=28,
                               corner_radius=0)
            lbl.pack(fill="x", padx=8, pady=2)
            lbl.bind("<Button-1>",
                     lambda e, playlist=pl: PlaylistInfoFrame(self.parent, playlist))

        # --- Close Button below scroll ---
        ctk.CTkButton(master=self.frame,
                      text="Close",
                      fg_color="#3e3e3e",
                      text_color="white",
                      width=100,
                      command=self.destroy).place(relx=0.5, y=320, anchor="n")


class FollowFrame(BaseFrame):
    def __init__(self, parent):
        super().__init__(parent, width=300, height=350)

    def create_widgets(self):
        self.title_entry = ctk.CTkEntry(self.frame, font=("Arial", 12), placeholder_text="Jon Doe",
                                        fg_color="#2e2e2e", text_color="white")
        self.title_entry.place(relx=0.5, y=100, anchor="n", relwidth=0.8)

        self.suggestion_frame = ctk.CTkScrollableFrame(self.frame, fg_color="#2e2e2e", height=100)
        self.suggestion_frame._scrollbar.configure(height=20)
        self.suggestion_frame.place(relx=0.5, y=130, anchor="n")

        btn_frame = tk.Frame(self.frame, bg="#1e1e1e")
        btn_frame.place(relx=0.5, y=250, anchor="n")
        tk.Button(btn_frame, text="Cancel", bg="#3e3e3e", fg="white", width=10, command=self.destroy).pack(side="left", padx=5)
        self.title_entry.bind("<KeyRelease>", self.update_suggestions)

    def update_suggestions(self, event):
        suggestions = self.parent.controller.user_search_suggestions(self.title_entry.get())
        for w in self.suggestion_frame.winfo_children(): w.destroy()
        if suggestions == [""]: return
        for suggestion in suggestions:
            row = tk.Frame(self.suggestion_frame, bg="#2e2e2e"); row.pack(fill="x", pady=2, padx=5)
            tk.Label(row, text=suggestion, bg="#2e2e2e", fg="white").pack(side="left")
            ctk.CTkButton(row, text="Follow", command=lambda s=suggestion: self.follow(s), width=10).pack(side="right")

    def follow(self, username):
        self.parent.controller.follow_user(username)
        self.destroy()


class PlaylistInfoFrame(BaseFrame):
    def __init__(self, parent, playlist):
        self.playlist = playlist
        self.song_images = []
        super().__init__(parent, width=300, height=350)

    def create_widgets(self):
        # Cover Image
        frame = tk.Frame(self.frame, bg="#1e1e1e", highlightthickness=2, highlightbackground="#666666",
                         width=100, height=100)
        frame.place(relx=0.5, y=20, anchor="n"); frame.pack_propagate(False)
        img_data = base64.b64decode(self.playlist.coverb64)
        img = Image.open(io.BytesIO(img_data)).resize((100, 100))
        tk_img = ImageTk.PhotoImage(img)
        tk.Label(frame, image=tk_img, bg="#1e1e1e").pack(expand=True, fill="both"); frame.image = tk_img

        # Title and Play
        tk.Label(self.frame, text=self.playlist.name, bg="#1e1e1e", fg="white",
                 font=("Arial", 12, "bold")).place(relx=0.5, y=130, anchor="n", width=260)
        tk.Button(self.frame, text="play", bg="#3e3e3e", fg="white", width=10,
                  command=lambda: self.parent.controller.play_playlist(self.playlist)).place(relx=0.5, y=160, anchor="n")

        # Songs list with scrollbar
        canvas = tk.Canvas(self.frame, bg="#2e2e2e", highlightthickness=0)
        canvas.place(relx=0.5, y=210, anchor="n", width=240, height=100)
        sb = tk.Scrollbar(self.frame, orient="vertical", command=canvas.yview)
        sb.place(relx=0.9, y=210, anchor="n", height=100)
        canvas.configure(yscrollcommand=sb.set)
        songs_frame = tk.Frame(canvas, bg="#2e2e2e")
        canvas.create_window((0, 0), window=songs_frame, anchor="nw")
        songs_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Enter>", lambda e: self._bind_mousewheel(canvas))
        canvas.bind("<Leave>", lambda e: self._unbind_mousewheel(canvas))
        for song in self.playlist.songs: self._add_song_row(songs_frame, song)

        tk.Button(self.frame, text="Cancel", bg="#3e3e3e", fg="white", width=10,
                  command=self.destroy).place(relx=0.5, y=320, anchor="n")

    def _add_song_row(self, parent, song):
        row = tk.Frame(parent, bg="#2e2e2e"); row.pack(fill="x", pady=2)
        try: img = Image.open(io.BytesIO(base64.b64decode(song.coverb64)))
        except: img = Image.new("RGB", (40, 40), color="gray")
        img.thumbnail((40, 40)); img_tk = ImageTk.PhotoImage(img); self.song_images.append(img_tk)
        tk.Label(row, image=img_tk, bg="#2e2e2e").pack(side="left", padx=5)
        tk.Label(row, text=f"{song.name} - {song.author}"[:12] + "...", bg="#2e2e2e", fg="white", anchor="w").pack(side="left", fill="x", expand=True)

    def _bind_mousewheel(self, canvas):
        canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(-1 if e.delta>0 else 1, "units"))
        canvas.bind_all("<Button-4>", lambda e: canvas.yview_scroll(-1, "units"))
        canvas.bind_all("<Button-5>", lambda e: canvas.yview_scroll(1, "units"))

    def _unbind_mousewheel(self, canvas):
        canvas.unbind_all("<MouseWheel>")
        canvas.unbind_all("<Button-4>")
        canvas.unbind_all("<Button-5>")


class PlaylistFrame(BaseFrame):
    def __init__(self, parent):
        self.filepath = None
        super().__init__(parent, width=300, height=350)

    def create_widgets(self):
        frame = tk.Frame(self.frame, bg="#1e1e1e", highlightthickness=2, highlightbackground="#666666",
                         width=100, height=100)
        frame.place(relx=0.5, y=20, anchor="n"); frame.pack_propagate(False)
        self.image_btn = tk.Button(frame, text="+", font=("Arial", 24), fg="#666666", bg="#1e1e1e",
                                   borderwidth=0, command=self.upload_image)
        self.image_btn.pack(expand=True, fill="both")

        self.title_entry = tk.Entry(self.frame, font=("Arial", 12), bg="#2e2e2e", fg="white",
                                    insertbackground="white")
        self.title_entry.insert(0, "Playlist Title")
        self.title_entry.place(relx=0.5, y=200, anchor="n", relwidth=0.8)

        btn_frame = tk.Frame(self.frame, bg="#1e1e1e")
        btn_frame.place(relx=0.5, y=250, anchor="n")
        tk.Button(btn_frame, text="Create", bg="#666666", fg="white", width=10,
                  command=self.create).pack(side="left", padx=5)
        tk.Button(btn_frame, text="Cancel", bg="#3e3e3e", fg="white", width=10,
                  command=self.destroy).pack(side="left", padx=5)

    def upload_image(self):
        def task():
            path = filedialog.askopenfilename(filetypes=[("Image files", "*.jpg;*.jpeg")])
            if path:
                img = Image.open(path).resize((100, 100))
                tk_img = ImageTk.PhotoImage(img)
                self.image_btn.config(image=tk_img); self.image_btn.image = tk_img
                self.filepath = path
        threading.Thread(target=task, daemon=True).start()

    def create(self):
        if self.filepath and len(self.title_entry.get())>1:
            self.parent.controller.create_playlist(self.title_entry.get(), self.filepath)
            self.destroy()

class MyPlaylistInfoFrame(PlaylistInfoFrame):
    def __init__(self, parent, playlist):
        # Initialize using the base class constructor
        super().__init__(parent, playlist)

    def _add_song_row(self, parent, song):
        # Create row container
        row = tk.Frame(parent, bg="#2e2e2e")
        row.pack(fill="x", pady=2)

    def _add_song_row(self, parent, song):
        # Create row container
        row = tk.Frame(parent, bg="#2e2e2e")
        row.pack(fill="x", pady=2)

        # Load or fallback for cover image
        try:
            img = Image.open(io.BytesIO(base64.b64decode(song.coverb64)))
        except Exception:
            img = Image.new("RGB", (40, 40), color="gray")
        img.thumbnail((40, 40))
        img_tk = ImageTk.PhotoImage(img)
        self.song_images.append(img_tk)

        # Display cover
        tk.Label(row, image=img_tk, bg="#2e2e2e").pack(side="left", padx=5)

        # Song info
        tk.Label(
            row,
            text=f"{song.name} - {song.author}"[:12] + "...",
            bg="#2e2e2e",
            fg="white",
            anchor="w"
        ).pack(side="left", fill="x", expand=True)

        # Remove button
        remove_btn = tk.Button(
            row,
            text="❌",
            bg="#ff4d4d",
            fg="white",
            command=lambda s=song: self.remove_song(s, remove_btn)
        )
        remove_btn.pack(side="right", padx=20)

    def remove_song(self, song, widget):
        # Remove song from playlist
        if self.parent.controller.remove_song_from_playlist(self.playlist.playlist_id, song.song_id):
            self.playlist.remove_song(song)
            print(f"Removing song {song.name} from playlist {self.playlist.name}")
            # Remove row from UI
            widget.master.destroy()

class BasePopup:
    def __init__(self, widget, app=None):
        self.widget = widget
        self.app = app
        self.popup = None

    def show(self):
        if self.popup: return
        x = self.widget.winfo_rootx() + 25
        y = self.widget.winfo_rooty() + 20
        self.popup = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        tw.configure(bg="#aaaaaa")
        tw.bind("<FocusOut>", lambda e: self.hide())
        self.create_content()

    def hide(self):
        if self.popup:
            self.popup.destroy()
            self.popup = None

    def create_content(self):
        raise NotImplementedError("Subclasses must implement create_content")


class SongOptionsPopup(BasePopup):
    def create_content(self):
        tk.Button(self.popup, text="Volume", command=self._show_volume).pack(padx=10, pady=10)

    def _show_volume(self):
        self.hide()
        VolumePopup(self.widget, self.app).show()


class VolumePopup(BasePopup):
    def create_content(self):
        slider = tk.Scale(self.popup, from_=0, to=100, orient="horizontal", command=self._set_volume)
        slider.set(self.app.controller.volume * 100)
        slider.pack(padx=10, pady=10)
        self.popup.focus_set()

    def _set_volume(self, val):
        vol = float(val)/100
        self.app.controller.volume = vol
        if self.app.controller.client:
            self.app.controller.client.set_volume(vol)


class ToolTip(BasePopup):
    def __init__(self, widget, text):
        super().__init__(widget)
        self.text = text

        self.widget.bind("<Enter>", lambda e: self.show())
        self.widget.bind("<Leave>", lambda e: self.hide())

    def show(self, event=None):
        if self.popup or not self.text: return
        x, y, _, _ = self.widget.bbox("insert") if self.widget.bbox("insert") else (0,0,0,0)
        x += self.widget.winfo_rootx() + 25
        y += self.widget.winfo_rooty() + 20
        super().show()

    def create_content(self):
        tk.Label(self.popup, text=self.text, justify=tk.LEFT,
                 background="#aaaaaa", relief=tk.SOLID, borderwidth=1,
                 font=("tahoma", "8", "normal")).pack(ipadx=1)




# Example usage remains the same
if __name__ == '__main__':
    root = tk.Tk()
    root.title("Playlist Info")
    root.geometry("400x400")
    radar = HexagonRadar(root,
                         size=200,
                         stats=[0.8, 0.6, 0.5, 0.9, 0.7, 0.4],
                         highlightthickness=0)
    radar.pack(padx=20, pady=20)
    import base64
    with open('playlists/1.jpg', 'rb') as f:
        cover64b = base64.b64encode(f.read())
    song1 = Song(1, "Imagine", "John LeBron", "Imagine", cover64b)
    song2 = Song(2, "Let It Be", "The Beatles", "Let It Be", cover64b)
    song3 = Song(3, "Bohemian Rhapsody", "King", "A Night at the Opera", cover64b)
    playlist = Playlist(1, "My Playlist",  cover64b, [song1, song2, song3])
    PlaylistInfoFrame(root, playlist)
    root.mainloop()
