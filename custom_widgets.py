import threading
import tkinter as tk
import customtkinter as ctk
from tkinter import ttk
from tkinter import filedialog
from PIL import Image, ImageTk
import base64
from song import *
import io


class PlaylistInfoFrame:
    def __init__(self, parent, playlist):
        self.parent = parent
        self.playlist = playlist
        self.frame_width = 300
        self.frame_height = 350
        self.frame = tk.Frame(parent, bg="#1e1e1e", bd=2, relief="solid")
        # List to hold references to song images to prevent garbage collection
        self.song_images = []
        self.create_widgets()
        self.place_frame()

    def create_widgets(self):
        # --- Playlist Cover Image Section ---
        self.image_frame = tk.Frame(self.frame, bg="#1e1e1e",
                                    highlightthickness=2, highlightbackground="#666666",
                                    width=100, height=100)
        self.image_frame.place(relx=0.5, y=20, anchor="n")
        self.image_frame.pack_propagate(False)

        # Decode and load the playlist cover image
        img_data = base64.b64decode(self.playlist.coverb64)
        img = Image.open(io.BytesIO(img_data))
        img_resized = img.resize((100, 100))
        img_tk = ImageTk.PhotoImage(img_resized)
        self.image_label = tk.Label(self.image_frame, image=img_tk, bg="#1e1e1e")
        self.image_label.image = img_tk  # Keep a reference!
        self.image_label.pack(expand=True, fill="both")

        # --- Playlist Title Section ---
        self.title_label = tk.Label(self.frame, text=self.playlist.name,
                                    bg="#1e1e1e", fg="white", font=("Arial", 12, "bold"))
        self.title_label.place(relx=0.5, y=130, anchor="n", width=260)

        self.play_button = tk.Button(self.frame, text="play", bg="#3e3e3e", fg="white", width=10,
                                       command=lambda: self.parent.controller.play_playlist(self.playlist))
        self.play_button.place(relx=0.5, y=160, anchor="n")

        # --- Scrollable Songs Section ---
        # Create a canvas to hold the songs frame and attach a scrollbar
        self.songs_canvas = tk.Canvas(self.frame, bg="#2e2e2e", highlightthickness=0)
        self.songs_canvas.place(relx=0.5, y=210, anchor="n", width=240, height=100)

        self.songs_scrollbar = tk.Scrollbar(self.frame, orient="vertical", command=self.songs_canvas.yview)
        # Place the scrollbar near the canvas
        self.songs_scrollbar.place(relx=0.9, y=210, anchor="n", height=100)
        self.songs_canvas.configure(yscrollcommand=self.songs_scrollbar.set)

        # Create a frame inside the canvas to hold the song rows
        self.songs_frame = tk.Frame(self.songs_canvas, bg="#2e2e2e")
        self.songs_canvas.create_window((0, 0), window=self.songs_frame, anchor="nw")

        # Bind the configure event to update the scrollregion
        self.songs_frame.bind("<Configure>",
                              lambda e: self.songs_canvas.configure(scrollregion=self.songs_canvas.bbox("all")))

        # Bind mousewheel events for scrolling
        self.songs_canvas.bind("<Enter>", lambda e: self.bind_mousewheel())
        self.songs_canvas.bind("<Leave>", lambda e: self.unbind_mousewheel())

        # Populate the songs frame with a row for each song
        for song in self.playlist.songs:
            self.add_song_row(song)

        # --- Cancel Button Section ---
        self.cancel_button = tk.Button(self.frame, text="Cancel", bg="#3e3e3e", fg="white", width=10,
                                       command=self.destroy)
        self.cancel_button.place(relx=0.5, y=320, anchor="n")

    def add_song_row(self, song):
        # Container frame for a single song
        row = tk.Frame(self.songs_frame, bg="#2e2e2e")
        row.pack(fill="x", pady=2)

        # Decode and load the song cover image
        try:
            img_data = base64.b64decode(song.coverb64)
            song_img = Image.open(io.BytesIO(img_data))
        except Exception:
            # Fallback: Create a blank image if there's an error
            song_img = Image.new("RGB", (40, 40), color="gray")
        song_img.thumbnail((40, 40))
        song_img_tk = ImageTk.PhotoImage(song_img)
        # Save image reference to avoid garbage collection
        self.song_images.append(song_img_tk)

        # Image label for song cover
        img_label = tk.Label(row, image=song_img_tk, bg="#2e2e2e")
        img_label.pack(side="left", padx=5)

        # Text label for song name and author
        song_text = f"{song.name} - {song.author}"
        text_label = tk.Label(row, text=song_text, bg="#2e2e2e", fg="white", anchor="w")
        text_label.pack(side="left", fill="x", expand=True)

    def bind_mousewheel(self):
        # Bind mousewheel events when the mouse enters the canvas
        self.songs_canvas.bind_all("<MouseWheel>", self._on_mousewheel)  # For Windows and MacOS
        self.songs_canvas.bind_all("<Button-4>", self._on_mousewheel)  # For Linux, scroll up
        self.songs_canvas.bind_all("<Button-5>", self._on_mousewheel)  # For Linux, scroll down

    def unbind_mousewheel(self):
        # Unbind mousewheel events when the mouse leaves the canvas
        self.songs_canvas.unbind_all("<MouseWheel>")
        self.songs_canvas.unbind_all("<Button-4>")
        self.songs_canvas.unbind_all("<Button-5>")

    def _on_mousewheel(self, event):
        # Mouse wheel event handler for scrolling the canvas.
        if event.num == 4 or event.delta > 0:
            self.songs_canvas.yview_scroll(-1, "units")
        elif event.num == 5 or event.delta < 0:
            self.songs_canvas.yview_scroll(1, "units")

    def place_frame(self):
        # Center the frame in the parent window
        self.parent.update_idletasks()
        parent_width = self.parent.winfo_width()
        parent_height = self.parent.winfo_height()
        x = (parent_width - self.frame_width) // 2
        y = (parent_height - self.frame_height) // 2
        self.frame.place(x=x, y=y, width=self.frame_width, height=self.frame_height)

    def destroy(self):
        self.frame.destroy()

class PlaylistFrame:
    def __init__(self, parent):
        self.parent = parent
        self.frame_width = 300
        self.frame_height = 350
        self.frame = tk.Frame(parent, bg="#1e1e1e", bd=2, relief="solid")
        self.filepath = None
        self.create_widgets()
        self.place_frame()

    def create_widgets(self):
        # Image placeholder: a frame with #666666 border containing a plus button
        self.image_frame = tk.Frame(self.frame, bg="#1e1e1e",
                                    highlightthickness=2, highlightbackground="#666666",
                                    width=100, height=100)
        self.image_frame.place(relx=0.5, y=20, anchor="n")
        self.image_frame.pack_propagate(False)  # Prevent frame from resizing to its content

        self.image_label = tk.Button(self.image_frame, text="+", font=("Arial", 24),
                                     fg="#666666", bg="#1e1e1e", borderwidth=0, command=self.upload_image)
        self.image_label.pack(expand=True, fill="both")

        # Playlist Title Entry
        self.title_entry = tk.Entry(self.frame, font=("Arial", 12),
                                    bg="#2e2e2e", fg="white", insertbackground="white")
        self.title_entry.insert(0, "Playlist Title")
        self.title_entry.place(relx=0.5, y=200, anchor="n", relwidth=0.8)

        # Button frame for Create and Cancel buttons
        self.button_frame = tk.Frame(self.frame, bg="#1e1e1e")
        self.button_frame.place(relx=0.5, y=250, anchor="n")

        self.create_button = tk.Button(self.button_frame, text="Create", bg="#666666", fg="white", width=10, command=self.create)
        self.create_button.pack(side="left", padx=5)

        self.cancel_button = tk.Button(self.button_frame, text="Cancel", bg="#3e3e3e", fg="white", width=10, command=self.destroy)
        self.cancel_button.pack(side="left", padx=5)

    def create(self):
        if self.filepath and len(self.title_entry.get()) > 1:
            self.parent.controller.create_playlist(self.title_entry.get(), self.filepath)
            self.destroy()

    def place_frame(self):
        # Update parent window info and center the frame
        self.parent.update_idletasks()
        parent_width = self.parent.winfo_width()
        parent_height = self.parent.winfo_height()
        x = (parent_width - self.frame_width) // 2
        y = (parent_height - self.frame_height) // 2
        self.frame.place(x=x, y=y, width=self.frame_width, height=self.frame_height)

    def upload_image(self):
        def _upload_image():
            self.filepath = filedialog.askopenfilename(filetypes=[("Image files", "*.jpg;*.jpeg")])
            if self.filepath:
                img = Image.open(self.filepath)
                img_resized = img.resize((100, 100))
                img_tk = ImageTk.PhotoImage(img_resized)
                self.image_label.config(image=img_tk)
                self.image_label.image = img_tk  # Keep a reference

        t = threading.Thread(target=_upload_image)
        t.start()


    def destroy(self):
        self.frame.destroy()


class SongOptionsPopup:
    def __init__(self, parent_widget, audio_app):
        self.widget = parent_widget
        self.popup = None
        self.app = audio_app

    def show(self):
        if self.popup:
            return  # Already showing

        x = self.widget.winfo_rootx() + 25
        y = self.widget.winfo_rooty() + 20

        self.popup = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        tw.configure(bg="#aaaaaa")

        # Close popup when focus is lost
        tw.bind("<FocusOut>", lambda e: self.hide())
        # Create volume button inside popup
        volume_button = tk.Button(tw, text="Volume", command=self.show_volume_popup)
        volume_button.pack(padx=10, pady=10)

    def show_volume_popup(self):
        if self.popup:
            self.popup.hide()
            VolumePopup(self.widget, self.app).show()

    def hide(self):
        if self.popup:
            self.popup.destroy()
            self.popup = None

class VolumePopup:
    def __init__(self, parent_widget, audio_app):
        self.widget = parent_widget
        self.popup = None
        self.app = audio_app

    def show(self):
        if self.popup:
            return  # Already showing

        x = self.widget.winfo_rootx() + 25
        y = self.widget.winfo_rooty() + 20

        self.popup = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        tw.configure(bg="#aaaaaa")

        # Close popup when focus is lost
        tw.bind("<FocusOut>", lambda e: self.hide())
        # Create volume slider inside popup
        slider = ttk.Scale(
            tw,
            from_=0,
            to=100,
            orient="horizontal",
            command=self.set_volume
        )
        slider.set(self.app.controller.volume * 100)  # Set initial value
        slider.pack(padx=10, pady=10)

        tw.focus_set()  # Grab focus to auto-close when clicking outside

    def set_volume(self, val):
        volume = float(val)/100
        self.app.controller.volume = volume
        if self.app.controller.client:
            print('volume', volume)
            self.app.controller.client.set_volume(volume)

    def hide(self):
        if self.popup:
            self.popup.destroy()
            self.popup = None


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

if __name__ == '__main__':
    root = tk.Tk()
    root.title("Playlist Info")
    root.geometry("400x400")
    with open('playlists/1.jpg', 'rb') as f:
        cover64b = base64.b64encode(f.read())

    song1 = Song(1, "Imagine", "John LeBron", "Imagine", cover64b)
    song2 = Song(2, "Let It Be", "The Beatles", "Let It Be", cover64b)
    song3 = Song(3, "Bohemian Rhapsody", "King", "A Night at the Opera", cover64b)

    playlist = Playlist(1, "My Playlist",  cover64b, [song1, song2, song3])
    playlist_frame = PlaylistInfoFrame(root, playlist)
    root.mainloop()