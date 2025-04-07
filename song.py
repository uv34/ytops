

class Song:
    def __init__(self, song_id, name, author, album, cover):
        self.song_id = song_id
        self.name = name
        self.album = album
        self.author = author
        self.coverb64 = cover

    def __repr__(self):
        return f"Song(id={self.song_id}, name='{self.name}', author='{self.author}', album='{self.album}', cover='{self.coverb64}')"


class Playlist:
    def __init__(self, playlist_id, name, cover, songs=[]):
        self.playlist_id = playlist_id
        self.name = name
        self.songs = songs
        self.coverb64 = cover

    def add_song(self, song):
        self.songs.append(song)

    def remove_song(self, song):
        if song in self.songs:
            self.songs.remove(song)

    def __repr__(self):
        return f"Playlist(id={self.playlist_id}, name='{self.name}', cover='{self.coverb64}', songs='{self.songs}')"


class SongQueue:
    def __init__(self):
        self.queue = []           # Songs to play next
        self.history = []         # Songs already played
        self.current_song = None  # Now playing

    def add_song(self, song):
        print('------------add song------------')
        self.queue.append(song)

    def remove_song(self, song):
        if song in self.queue:
            self.queue.remove(song)

    def next(self):
        print('------------next song------------')
        if self.queue:
            if self.current_song:
                self.history.append(self.current_song)
            self.current_song = self.queue.pop(0)
            return self.current_song
        return None  # No more songs

    def prev(self):
        print('------------prev song------------')
        if self.history:
            if self.current_song:
                self.queue.insert(0, self.current_song)
            self.current_song = self.history.pop()
            return self.current_song
        return None  # No history

    def empty(self):
        return len(self.queue) == 0


if __name__ == "__main__":
    song1 = Song(1, "Imagine", "John LeBron", "Imagine", "cover1b64")
    song2 = Song(2, "Let It Be", "The Beatles", "Let It Be", "cover2b64")
    song3 = Song(3, "Bohemian Rhapsody", "King", "A Night at the Opera", "cover3b64")

    q = SongQueue()

    q.add_song(song1)
    q.add_song(song2)

    current = q.next()
    print('Now playing:', current)
    current = q.next()
    print('Now playing:', current)

    print("--- Full history and queue ---")
    print("History:", q.history)
    print("Current:", q.current_song)
    print("Queue:", q.queue)
