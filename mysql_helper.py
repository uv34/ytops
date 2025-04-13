from operator import length_hint
import bcrypt
import mysql.connector
from ogg_handler import get_ogg_duration, get_sample_rate, count_ogg_pages


class DBController:
    """
    A controller class to interact with the MySQL database 'mydb'.
    Provides methods for creating and retrieving albums, songs, and playlists,
    as well as adding songs to playlists.
    im inserting the params through execute to avoid injections
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

    def create_playlist(self, user_id, name):
        """
        Creates a playlist associated with a user.
        Assumes the playlists table has a 'user_id' column.
        """
        cursor = self.conn.cursor()
        query = "INSERT INTO playlists (user_id, name) VALUES (%s, %s)"
        cursor.execute(query, (user_id, name))
        self.conn.commit()
        playlist_id = cursor.lastrowid
        cursor.close()
        return playlist_id

    def get_songs_in_playlist(self, playlist_id):
        """
        Retrieves all songs in a given playlist, ordered by their position (index).
        Returns a list of song dictionaries with details from the songs table.
        """
        cursor = self.conn.cursor(dictionary=True)
        query = """
            SELECT s.*, shp.`index`
            FROM songs s
            JOIN songs_has_playlists shp ON s.id = shp.songs_id
            WHERE shp.playlists_id = %s
            ORDER BY shp.`index` ASC
        """
        cursor.execute(query, (playlist_id,))
        songs = cursor.fetchall()
        cursor.close()
        return songs

    def get_playlist(self, playlist_id):
        cursor = self.conn.cursor(dictionary=True)
        query = "SELECT * FROM playlists WHERE id = %s"
        cursor.execute(query, (playlist_id,))
        playlist = cursor.fetchone()
        cursor.close()
        return playlist

    def delete_playlist(self, playlist_id):
        """
        Deletes the specified playlist and cleans up related song associations.
        """
        cursor = self.conn.cursor()
        try:
            # First, remove all song associations for this playlist.
            delete_associations_query = "DELETE FROM songs_has_playlists WHERE playlists_id = %s"
            cursor.execute(delete_associations_query, (playlist_id,))

            # Next, delete the playlist itself.
            delete_playlist_query = "DELETE FROM playlists WHERE id = %s"
            cursor.execute(delete_playlist_query, (playlist_id,))

            # Commit changes
            self.conn.commit()
        except Exception as e:
            self.conn.rollback()
            return False
        finally:
            cursor.close()
            return True

    def add_song_to_playlist(self, song_id, playlist_id):
        cursor = self.conn.cursor()

        # Check if the song is already in the playlist
        check_query = "SELECT COUNT(*) FROM songs_has_playlists WHERE songs_id = %s AND playlists_id = %s"
        cursor.execute(check_query, (song_id, playlist_id))
        exists = cursor.fetchone()[0]

        if exists > 0:
            print(f"Song {song_id} is already in playlist {playlist_id}.")
            cursor.close()
            return False

        # Determine the current count of songs in the playlist.
        count_query = "SELECT COUNT(*) FROM songs_has_playlists WHERE playlists_id = %s"
        cursor.execute(count_query, (playlist_id,))
        current_count = cursor.fetchone()[0]
        index = current_count + 1

        # Insert the new song at the adjusted index.
        insert_query = ("INSERT INTO songs_has_playlists (songs_id, playlists_id, `index`) "
                        "VALUES (%s, %s, %s)")
        cursor.execute(insert_query, (song_id, playlist_id, index))
        self.conn.commit()
        cursor.close()
        return True

    def get_playlists_by_user(self, user_id):
        """
        Retrieves all playlists for a given user.
        """
        cursor = self.conn.cursor(dictionary=True)
        query = "SELECT * FROM playlists WHERE user_id = %s ORDER BY id"
        cursor.execute(query, (user_id,))
        playlists = cursor.fetchall()
        cursor.close()
        return playlists

    def remove_song_from_playlist(self, song_id, playlist_id):
        cursor = self.conn.cursor()
        # Remove the song from the playlist
        delete_query = "DELETE FROM songs_has_playlists WHERE songs_id = %s AND playlists_id = %s"
        cursor.execute(delete_query, (song_id, playlist_id))

        # Optionally, re-index the remaining songs to fill the gap
        # Retrieve all songs for the playlist ordered by current index
        select_query = ("SELECT songs_id FROM songs_has_playlists "
                        "WHERE playlists_id = %s ORDER BY `index` ASC")
        cursor.execute(select_query, (playlist_id,))
        songs = cursor.fetchall()

        # Reassign indices starting from 1
        for new_index, (s_id,) in enumerate(songs, start=1):
            update_query = ("UPDATE songs_has_playlists SET `index` = %s "
                            "WHERE playlists_id = %s AND songs_id = %s")
            cursor.execute(update_query, (new_index, playlist_id, s_id))

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

    def login_user(self, username, plain_password):
        cursor = self.conn.cursor()
        cursor.execute("SELECT id, password, status FROM `user` WHERE username = %s LIMIT 1", (username,))
        result = cursor.fetchone()
        cursor.close()
        if not result:
            return -1, '0'  # User not found

        user_id, stored_hash, user_status = result

        # Verify the password using bcrypt
        if user_id and bcrypt.checkpw(plain_password.encode('utf-8'), stored_hash.encode('utf-8')):
            return user_id, user_status
        else:
            return -1, '0'  # Invalid credentials

    def add_user(self, username, plain_password, email):
        cursor = self.conn.cursor()

        # 1) Check if user already exists
        cursor.execute("SELECT COUNT(*) FROM `user` WHERE username = %s OR email = %s", (username, email))
        if cursor.fetchone()[0] > 0:
            return "ERROR: Username or email already exists."
        # Generate the hash (bcrypt automatically creates a salt)
        hashed_password = bcrypt.hashpw(plain_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        user_status = 'r'
        # Insert the new user into the database
        insert_query = "INSERT INTO `user` (username, email, password, create_time, status) VALUES (%s, %s, %s, NOW(), %s)"
        cursor.execute(insert_query, (username, email, hashed_password, user_status))
        self.conn.commit()

        new_user_id = cursor.lastrowid
        cursor.close()
        return new_user_id, user_status  # Return tuple: (id, status)

    def add_segment_to_user(self, user_id, songs_id, duration, segment_time, start_time, end_time, used=False):
        """
        Add a new segment for a user.
        """
        try:
            cursor = self.conn.cursor()
            insert_query = """
                INSERT INTO user_segments (user_id, songs_id, duration, time, start_time, end_time, used)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """
            # MySQL typically uses 0 or 1 for boolean fields.
            used_flag = 1 if used else 0
            cursor.execute(insert_query, (user_id, songs_id, duration, segment_time, start_time, end_time, used_flag))
            self.conn.commit()
            print("Segment added successfully.")
        except Error as e:
            print(f"Error while inserting segment: {e}")
            self.conn.rollback()
        finally:
            cursor.close()

    def mark_segments_used(self, user_id, n):
        """
        Set the first n unused segments (used = False) for the given user to used.
        """
        try:
            cursor = self.conn.cursor()
            update_query = """
                UPDATE user_segments
                SET used = 1
                WHERE user_id = %s AND used = 0
                ORDER BY time ASC
                LIMIT %s
            """
            cursor.execute(update_query, (user_id, n))
            self.conn.commit()
            print(f"{cursor.rowcount} segments marked as used.")
        except Error as e:
            print(f"Error while updating segments: {e}")
            self.conn.rollback()
        finally:
            cursor.close()

    def print_users(self):
        """
        Prints all users from the 'user' table in the database.
        """
        cursor = self.conn.cursor(dictionary=True)
        query = "SELECT * FROM `user`"
        cursor.execute(query)
        users = cursor.fetchall()
        if users:
            print("Users:")
            for user in users:
                print(user)
        else:
            print("No users found.")
        cursor.close()

    def close(self):
        self.conn.close()


# Example usage:
if __name__ == '__main__':
    db = DBController(host="192.168.1.20", user="stopify", password="stop123", database="mydb")

    print("\nPrinting all tables:")
    db.print_tables()
    db.print_users()

    print(db.get_playlists_by_user(10))
    db.mark_segments_used(10, 5)
    """user_id = 10

    # Create a new playlist for the user.
    playlist_id = db.create_playlist(user_id, "Test Playlist2")
    print("Created Playlist ID:", playlist_id)

    # Dummy song IDs for testing.
    # In practice, these would be created by db.create_song() or already exist in your songs table.
    song_ids = [1, 2, 3, 4]

    # Function to display the current order of songs in the playlist.
    def print_playlist_order(playlist_id):
        cursor = db.conn.cursor()
        query = "SELECT songs_id, `index` FROM songs_has_playlists WHERE playlists_id = %s ORDER BY `index` ASC"
        cursor.execute(query, (playlist_id,))
        rows = cursor.fetchall()
        print("Current Playlist Order:")
        for song_id, idx in rows:
            print(f"Index {idx}: Song {song_id}")
        cursor.close()

    # Test 1: Add song with id 101 at index 1.
    print("\nAdding song 101 at index 1:")
    db.add_song_to_playlist(song_ids[0], playlist_id, index=1)
    print_playlist_order(playlist_id)

    # Test 2: Add song with id 102 at index 2.
    print("\nAdding song 102 at index 2:")
    db.add_song_to_playlist(song_ids[1], playlist_id, index=2)
    print_playlist_order(playlist_id)

    # Test 3: Add song with id 103 at index 100 (should append at the end).
    print("\nAdding song 103 at index 100 (out-of-range):")
    db.add_song_to_playlist(song_ids[2], playlist_id, index=100)
    print_playlist_order(playlist_id)

    # Test 4: Insert song with id 104 at index 2 (should shift subsequent songs).
    print("\nAdding song 104 at index 2 (shifting others):")
    db.add_song_to_playlist(song_ids[3], playlist_id, index=2)
    print_playlist_order(playlist_id)

    # Test 5: Remove song 102 from the playlist.
    print("\nRemoving song 102:")
    db.remove_song_from_playlist(song_ids[1], playlist_id)
    print_playlist_order(playlist_id)"""

    """
    album_id = db.create_album("Dire Straits (Remastered)", "Dire Straits", "dire_straits_remastered.jpg")
    length = get_ogg_duration("5.ogg")
    sample_rate = get_sample_rate('5.ogg')
    pages = count_ogg_pages('5.ogg')
    song_id = db.create_song(album_id, "Sultans of Swing", "Dire Straits", length, sample_rate, pages)
    """

    """
    # Create an album.
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
    print("Added song to playlist")"""

    # Print all tables and their contents.

    db.close()

