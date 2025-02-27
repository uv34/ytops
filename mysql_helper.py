from operator import length_hint

import mysql.connector
from ogg_handler import get_ogg_duration, get_sample_rate, count_ogg_pages


class DBController:
    """
    A controller class to interact with the MySQL database 'mydb'.
    Provides methods for creating and retrieving albums, songs, and playlists,
    as well as adding songs to playlists.
    """

    def __init__(self, host, user, password, database, port=3306):
        self.conn = mysql.connector.connect(
            host=host,
            user=user,
            password=password,
            database=database,
            port=port
        )
        self.conn.autocommit = False

    def create_album(self, name, author, cover):
        cursor = self.conn.cursor()
        query = "INSERT INTO album (name, author, cover) VALUES (%s, %s, %s)"
        cursor.execute(query, (name, author, cover))
        self.conn.commit()
        album_id = cursor.lastrowid
        cursor.close()
        return album_id

    def get_album(self, album_id):
        cursor = self.conn.cursor(dictionary=True)
        query = "SELECT * FROM album WHERE id = %s"
        cursor.execute(query, (album_id,))
        album = cursor.fetchone()
        cursor.close()
        return album

    def create_song(self, album_id, name, author, length, sample_rate, pages):
        # Verify album exists first
        if not self.get_album(album_id):
            raise ValueError("Album not found")
        cursor = self.conn.cursor()
        query = ("INSERT INTO songs (name, author, length, sample_rate, pages, album_id) "
                 "VALUES (%s, %s, %s, %s, %s, %s)")
        cursor.execute(query, (name, author, length, sample_rate, pages, album_id))
        self.conn.commit()
        song_id = cursor.lastrowid
        cursor.close()
        return song_id

    def get_song(self, song_id):
        cursor = self.conn.cursor(dictionary=True)
        query = "SELECT * FROM songs WHERE id = %s"
        cursor.execute(query, (song_id,))
        song = cursor.fetchone()
        cursor.close()
        return song

    def create_playlist(self, name, cover):
        cursor = self.conn.cursor()
        query = "INSERT INTO playlists (name, cover) VALUES (%s, %s)"
        cursor.execute(query, (name, cover))
        self.conn.commit()
        playlist_id = cursor.lastrowid
        cursor.close()
        return playlist_id

    def get_playlist(self, playlist_id):
        cursor = self.conn.cursor(dictionary=True)
        query = "SELECT * FROM playlists WHERE id = %s"
        cursor.execute(query, (playlist_id,))
        playlist = cursor.fetchone()
        cursor.close()
        return playlist

    def add_song_to_playlist(self, song_id, playlist_id, index=None):
        cursor = self.conn.cursor()
        # Note: `index` is a reserved word in MySQL, so it is escaped with backticks.
        query = "INSERT INTO songs_has_playlists (songs_id, playlists_id, `index`) VALUES (%s, %s, %s)"
        cursor.execute(query, (song_id, playlist_id, index))
        self.conn.commit()
        cursor.close()


    def print_tables(self):
        """
        Prints the names of all tables in the current database and their contents.
        """
        cursor = self.conn.cursor()
        # Retrieve list of tables.
        cursor.execute("SHOW TABLES")
        tables = cursor.fetchall()
        for (table_name,) in tables:
            print(f"Table: {table_name}")
            # Retrieve all data from the table.
            cursor.execute(f"SELECT * FROM {table_name}")
            rows = cursor.fetchall()
            for row in rows:
                print(row)
            print("-" * 40)
        cursor.close()

    def close(self):
        self.conn.close()


# Example usage:
if __name__ == '__main__':
    # Replace with your actual credentials.
    db = DBController(host="localhost", user="root", password="SqlUV123!", database="mydb")

    print("\nPrinting all tables:")
    db.print_tables()
    """album_id = 1
    length = get_ogg_duration("2.ogg")
    sample_rate = get_sample_rate('2.ogg')
    pages = count_ogg_pages('2.ogg')
    song_id = db.create_song(album_id, "The Boy With The Thorn In His Side", "The Smiths", length, sample_rate, pages)"""
    """# Create an album.
    album_id = db.create_album("Album Title", "Album Author", "cover.jpg")
    print("Created Album ID:", album_id)

    # Create a song for the album.
    song_id = db.create_song(album_id, "Song Title", "Song Author", 3.5, 44100, 1)
    print("Created Song ID:", song_id)

    # Create a playlist.
    playlist_id = db.create_playlist("My Playlist", "playlist_cover.jpg")
    print("Created Playlist ID:", playlist_id)

    # Add the song to the playlist.
    db.add_song_to_playlist(song_id, playlist_id, index=1)
    print("Added song to playlist")

    # Print all tables and their contents."""

    db.close()

