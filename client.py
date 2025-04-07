import threading
import pickle
from song import SongQueue  # Assumes SongQueue class exists
from audio_client_v2 import AudioClient  # Assumes AudioClient class exists
import protocol  # Assumes this handles socket messaging

class PlaybackController:
    def __init__(self, view, audio_client, gen_sock, token):
        self.token = token
        self.gen_socket = gen_sock
        self.client = None
        self.stream_thread = None
        self.song_queue = SongQueue()
        self.volume = 1
        self.skipped = False

        self.total_time = 1.0
        self.downloaded_time = 0.0
        self.played_time = 0.0