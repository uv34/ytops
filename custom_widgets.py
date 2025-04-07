import tkinter as tk
from tkinter import ttk
from tkinter import filedialog
from PIL import Image, ImageTk


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
                                    width=150, height=150)
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
            self.parent.create_playlist(self.title_entry.get(), self.filepath)

    def place_frame(self):
        # Update parent window info and center the frame
        self.parent.update_idletasks()
        parent_width = self.parent.winfo_width()
        parent_height = self.parent.winfo_height()
        x = (parent_width - self.frame_width) // 2
        y = (parent_height - self.frame_height) // 2
        self.frame.place(x=x, y=y, width=self.frame_width, height=self.frame_height)

    def upload_image(self):
        self.filepath = filedialog.askopenfilename(filetypes=[("Image files", "*.png;*.jpg;*.jpeg;*.gif")])
        if self.filepath:
            img = Image.open(self.filepath)
            img.thumbnail((64, 64))
            img_tk = ImageTk.PhotoImage(img)
            self.image_label.config(image=img_tk)
            self.image_label.image = img_tk  # Keep a reference

    def destroy(self):
        self.frame.destroy()


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
        slider.set(self.app.volume * 100)  # Set initial value
        slider.pack(padx=10, pady=10)

        tw.focus_set()  # Grab focus to auto-close when clicking outside

    def set_volume(self, val):
        volume = float(val)/100
        self.app.volume = volume
        if self.app.client:
            print('volume', volume)
            self.app.client.set_volume(volume)

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
