from operator import length_hint
import bcrypt
import mysql.connector
from ogg_handler import get_ogg_duration, get_sample_rate, count_ogg_pages
from datetime import datetime, timedelta, date
import pandas as pd

class DBController:
    """
    A controller class to interact with the MySQL database 'mydb'.
    Provides methods for creating and retrieving albums, songs, and playlists,
    as well as adding songs to playlists.
    im inserting the params through execute to avoid injections
    """

    def __init__(self, host, user, password, database, port=3306, autocommit=False):
        self.conn = mysql.connector.connect(
            host=host,
            user=user,
            password=password,
            database=database,
            port=port,
            autocommit=autocommit
        )

    def get_all_users(self):
        cursor = self.conn.cursor()
        query = "SELECT id, username FROM `user`"
        cursor.execute(query)
        users = cursor.fetchall()
        cursor.close()
        return users

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

    def get_all_song_names(self):
        cursor = self.conn.cursor()
        query = "SELECT id, name FROM songs"
        cursor.execute(query)
        songs = cursor.fetchall()
        cursor.close()
        return songs

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
        # Attempt to delete the song
        delete_query = """
            DELETE FROM songs_has_playlists 
             WHERE songs_id = %s AND playlists_id = %s
        """
        cursor.execute(delete_query, (song_id, playlist_id))

        # If no rows were removed -> nothing deleted
        if cursor.rowcount == 0:
            cursor.close()
            return False

        # Otherwise re-index the remaining songs
        select_query = """
            SELECT songs_id 
              FROM songs_has_playlists
             WHERE playlists_id = %s
          ORDER BY `index` ASC
        """
        cursor.execute(select_query, (playlist_id,))
        songs = cursor.fetchall()

        for new_index, (s_id,) in enumerate(songs, start=1):
            update_query = """
                UPDATE songs_has_playlists
                   SET `index` = %s
                 WHERE playlists_id = %s
                   AND songs_id = %s
            """
            cursor.execute(update_query, (new_index, playlist_id, s_id))

        self.conn.commit()
        cursor.close()
        return True

    def get_user_profile(self, user_id):
        """
        Retrieves the user profile from the database.
        """
        cursor = self.conn.cursor(dictionary=True)
        query = """
            SELECT acoustic, dance, energy, instrument, live, speech, weight, last_updated
            FROM proflie
            WHERE user_id = %s
        """
        cursor.execute(query, (user_id,))
        profile = cursor.fetchone()
        cursor.close()
        return profile

    def get_song_profile(self, song_id):
        """
        Retrieves the song profile from the database.
        """
        cursor = self.conn.cursor(dictionary=True)
        query = """
            SELECT acoustic, dance, energy, instrument, live, speech
            FROM songs_profile
            WHERE songs_id = %s
        """
        cursor.execute(query, (song_id,))
        profile = cursor.fetchone()
        cursor.close()
        return profile

    def update_user_profile(self, user_id, new_profile, new_weight, new_timestamp):
        try:
            cursor = self.conn.cursor()

            # In case new_timestamp is a string, convert it to the proper format.
            # If it's already a datetime, this step can be skipped.
            if isinstance(new_timestamp, str):
                from datetime import datetime
                new_timestamp = datetime.fromisoformat(new_timestamp)

            update_query = """
                    UPDATE `proflie`
                    SET acoustic = %s,
                        dance = %s,
                        energy = %s,
                        instrument = %s,
                        live = %s,
                        speech = %s,
                        weight = %s,
                        last_updated = %s
                    WHERE user_id = %s
                """

            # Map our keys from the passed profile dictionary to the correct columns.
            parameters = (
                new_profile.get('acoustic', 0.0),
                new_profile.get('dance', 0.0),
                new_profile.get('energy', 0.0),
                new_profile.get('instrument', 0.0),
                new_profile.get('live', 0.0),
                new_profile.get('speech', 0.0),
                new_weight,
                new_timestamp,
                user_id
            )

            cursor.execute(update_query, parameters)
            self.conn.commit()
            return True
        except Exception as e:
            print("Error while updating user profile:", e)
            self.conn.rollback()
            return False
        finally:
            cursor.close()

    def get_all_song_profiles(self):
        """
        Retrieves all song profiles from the database.
        """
        cursor = self.conn.cursor(dictionary=True)
        query = "SELECT * FROM songs_profile"
        cursor.execute(query)
        profiles = cursor.fetchall()
        cursor.close()
        return profiles

    def create_song_profile(self, song_id, profile):
        """
        Creates a song profile in the database.
        """
        cursor = self.conn.cursor()
        query = """
            INSERT INTO songs_profile (songs_id, acoustic, dance, energy, instrument, live, speech)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """
        cursor.execute(query, (song_id, float(profile[0]), float(profile[1]), float(profile[2]), float(profile[3]), float(profile[4]), float(profile[5])))
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

    def add_user(self, username, plain_password, email, verify_token, expiry):
        cursor = self.conn.cursor()

        # 1) Check if user already exists
        cursor.execute("SELECT COUNT(*) FROM `user` WHERE username = %s OR email = %s", (username, email))
        if cursor.fetchone()[0] > 0:
            return -1, '0'
        # Generate the hash (bcrypt automatically creates a salt)
        hashed_password = bcrypt.hashpw(plain_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        user_status = 'r'
        # Insert the new user into the database
        insert_query = """
            INSERT INTO `user`
                (username, email, password, create_time, status,
                 verify_token, token_expiry, is_verified)
            VALUES
                (%s, %s, %s, NOW(), %s, %s, %s, FALSE)
        """
        cursor.execute(insert_query, (username, email, hashed_password, user_status, verify_token, expiry))
        self.conn.commit()

        new_user_id = cursor.lastrowid

        insert_profile_query = """
                INSERT INTO `proflie`
                    (user_id, acoustic, dance, energy, instrument, live, speech, weight, last_updated)
                VALUES
                    (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
            """
        default_profile = (new_user_id, 0.5, 0.5, 0.5, 0.0, 0.5, 0.05, 1.0)
        cursor.execute(insert_profile_query, default_profile)
        self.conn.commit()

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
            count_query = """
                        SELECT COUNT(*) FROM user_segments
                        WHERE user_id = %s AND used = 0
                    """
            cursor.execute(count_query, (user_id,))
            unused_count = cursor.fetchone()[0]
            cursor.close()
            return unused_count
        except Exception as e:
            print(f"Error while inserting segment: {e}")
            self.conn.rollback()
            cursor.close()
            return -1

    def get_unused_segments(self, user_id, n):
        cursor = self.conn.cursor(dictionary=True)
        query = """
            SELECT * 
            FROM user_segments
            WHERE used = 0 AND user_id = %s
            ORDER BY id ASC 
            LIMIT %s
        """
        cursor.execute(query, (user_id, n))
        segments = cursor.fetchall()
        cursor.close()
        return segments


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
        except Exception as e:
            print(f"Error while updating segments: {e}")
            self.conn.rollback()
        finally:
            cursor.close()

    def follow_user(self, follower_id, followed_id):
        if follower_id == followed_id:
            raise ValueError("You can’t follow yourself")
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                "INSERT INTO social (follower, folowee, time) VALUES (%s, %s, NOW())",
                (follower_id, followed_id),
            )
            self.conn.commit()
        except mysql.connector.errors.IntegrityError as e:
            if e.errno == 1062:
                # already following
                cursor.close()
                print("Already following this user.")
                print(f"Error occurred: {e}")
                return False
            else:
                cursor.close()
                print(f"Error occurred: {e}")
                return False
        finally:
            cursor.close()
        return True

    def unfollow_user(self, follower_id, followed_id):
        """
        Allows one user to unfollow another.
        """
        if follower_id == followed_id:
            raise ValueError("You can’t unfollow yourself")

        cursor = self.conn.cursor()
        query = "DELETE FROM social WHERE follower = %s AND folowee = %s"
        cursor.execute(query, (follower_id, followed_id))
        self.conn.commit()
        deleted = cursor.rowcount
        cursor.close()
        return bool(deleted)

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

    def get_id_by_username(self, username):
        """
        Retrieves the user ID based on the username.
        """
        cursor = self.conn.cursor()
        query = "SELECT id FROM `user` WHERE username = %s"
        cursor.execute(query, (username,))
        user_id = cursor.fetchone()
        cursor.close()
        return user_id[0] if user_id else None

    def get_followings_username(self, user_id):
        """
        Retrieves the usernames of users that the given user is following.
        """
        cursor = self.conn.cursor()
        query = """
            SELECT u2.username
            FROM `user` AS u1
            JOIN social     AS s  ON u1.id = s.follower
            JOIN `user`        AS u2 ON s.folowee = u2.id
            WHERE u1.id = %s
        """
        cursor.execute(query, (user_id,))
        followings = cursor.fetchall()
        print(f"Followings for user {user_id}:", followings)
        cursor.close()
        return [str(f[0]) for f in followings]

    def get_social_table(self):
        """
        Retrieves the usernames of users that the given user is following.
        """
        cursor = self.conn.cursor()
        query = """
            SELECT *
            FROM social
        """
        cursor.execute(query)
        followings = cursor.fetchall()
        cursor.close()
        return followings

    def get_social_profile(self, username):
        cursor = self.conn.cursor()
        query = """
                SELECT u.username, u.create_time, p.acoustic, p.dance, p.energy, 
                p.instrument, p.live, p.speech
                FROM user u
                JOIN proflie p ON u.id = p.user_id
                WHERE u.username = %s;
                """
        cursor.execute(query, (username,))
        profile = cursor.fetchall()
        cursor.close()
        return profile

    def get_last_10_songs(self, username):
        cursor = self.conn.cursor(dictionary=True)
        query="""
            SELECT
              s.*,
              latest.last_time
            FROM (
              -- find each song’s most‐recent play time for this user
              SELECT
                us.songs_id,
                MAX(us.time) AS last_time
              FROM user_segments us
              JOIN `user` u
                ON us.user_id = u.id
              WHERE u.username = %s
              GROUP BY us.songs_id
            ) AS latest
            JOIN songs s
              ON s.id = latest.songs_id
            ORDER BY latest.last_time DESC
            LIMIT 10;
            """
        cursor.execute(query, (username,))
        songs = cursor.fetchall()
        cursor.close()
        return songs

    def get_user_playlist_by_username(self, username):
        cursor = self.conn.cursor(dictionary=True)
        query = """
                SELECT p.id, p.name
                FROM playlists p
                JOIN user u ON p.user_id = u.id
                WHERE u.username = %s;
                """
        cursor.execute(query, (username,))
        playlists = cursor.fetchall()
        cursor.close()
        return playlists

    def is_playlist_by_user(self, user_id, playlist_id):
        cursor = self.conn.cursor()
        query = "SELECT COUNT(*) FROM playlists WHERE id = %s AND user_id = %s"
        cursor.execute(query, (playlist_id, user_id))
        exists = cursor.fetchone()[0]
        cursor.close()
        return exists > 0

    def get_user_by_token(self, token):
        cursor = self.conn.cursor(dictionary=True)
        query = "SELECT * FROM `user` WHERE verify_token = %s"
        cursor.execute(query, (token,))
        user = cursor.fetchone()
        cursor.close()
        if not user:
            # no such token
            return False, None

            # token_expiry should be a datetime object
        if user.get('token_expiry') and user['token_expiry'] < datetime.utcnow():
            # token found but expired
            return False, user

            # valid token
        return True, user

    def update_user_token(self, user_id, token, expiry):
        cursor = self.conn.cursor()
        query = "UPDATE `user` SET verify_token = %s, token_expiry = %s WHERE id = %s"
        cursor.execute(query, (token, expiry, user_id))
        self.conn.commit()
        cursor.close()

    def verify_user(self, user_id):
        cursor = self.conn.cursor()
        query = "UPDATE `user` SET is_verified = TRUE WHERE id = %s"
        cursor.execute(query, (user_id,))
        self.conn.commit()
        cursor.close()

    def is_verified(self, user_id):
        cursor = self.conn.cursor()
        query = "SELECT is_verified FROM `user` WHERE id = %s"
        cursor.execute(query, (user_id,))
        is_verified = cursor.fetchone()[0]
        cursor.close()
        return is_verified

    def is_admin(self, user_id):
        cursor = self.conn.cursor()
        query = "SELECT status FROM `user` WHERE id = %s"
        cursor.execute(query, (user_id,))
        status = cursor.fetchone()[0]
        cursor.close()
        print(status)
        return status == 'a'

    def get_albums_ids_names(self):
        cursor = self.conn.cursor()
        query = "SELECT id, name FROM album"
        cursor.execute(query)
        albums = cursor.fetchall()
        cursor.close()
        return albums

    def album_exists(self, album_id):
        cursor = self.conn.cursor()
        query = "SELECT COUNT(*) FROM album WHERE id = %s"
        cursor.execute(query, (album_id,))
        exists = cursor.fetchone()[0]
        cursor.close()
        return exists > 0

    def get_mail_by_id(self, user_id):
        cursor = self.conn.cursor()
        query = "SELECT email FROM `user` WHERE id = %s"
        cursor.execute(query, (user_id,))
        email = cursor.fetchone()[0]
        cursor.close()
        return email

    def total_listening_minutes(self, user_id, start_dt, end_dt):
        sql = """
            SELECT IFNULL(SUM(duration),0)/60
              FROM mydb.user_segments
             WHERE user_id=%s
               AND time BETWEEN %s AND %s
        """
        cursor = self.conn.cursor()
        cursor.execute(sql, (user_id, start_dt, end_dt))
        (mins,) = cursor.fetchone()
        cursor.close()
        return mins

    def top_songs(self, user_id, start_dt, end_dt, top_n=5):
        sql = """
            SELECT s.id, s.name, s.author,
                   SUM(us.duration)/60 AS total_duration
              FROM mydb.user_segments us
              JOIN mydb.songs s ON us.songs_id = s.id
             WHERE us.user_id=%s
               AND us.time BETWEEN %s AND %s
             GROUP BY s.id, s.name, s.author
             ORDER BY total_duration DESC
             LIMIT %s
        """
        cursor = self.conn.cursor(dictionary=True)
        cursor.execute(sql, (user_id, start_dt, end_dt, top_n))
        results = cursor.fetchall()
        cursor.close()
        return results  # list of dicts: { 'id', 'name', 'author', 'total_duration' }

    def top_artists(self, user_id, start_dt, end_dt, top_n=5):
        sql = """
            SELECT s.author AS artist_name,
                   SUM(us.duration)/60 AS total_duration
              FROM mydb.user_segments us
              JOIN mydb.songs s ON us.songs_id = s.id
             WHERE us.user_id=%s
               AND us.time BETWEEN %s AND %s
             GROUP BY s.author
             ORDER BY total_duration DESC
             LIMIT %s
        """
        cursor = self.conn.cursor(dictionary=True)
        cursor.execute(sql, (user_id, start_dt, end_dt, top_n))
        results = cursor.fetchall()
        cursor.close()
        return results  # list of dicts: { 'artist_name', 'total_duration' }

    def peak_listening_days(self, user_id, start_dt, end_dt, top_n=5):
        sql = """
            SELECT DATE(us.time) AS day,
                   SUM(us.duration)/60 AS total_duration
              FROM mydb.user_segments us
             WHERE us.user_id=%s
               AND us.time BETWEEN %s AND %s
             GROUP BY day
             ORDER BY total_duration DESC
             LIMIT %s
        """
        cursor = self.conn.cursor(dictionary=True)
        cursor.execute(sql, (user_id, start_dt, end_dt, top_n))
        results = cursor.fetchall()
        cursor.close()
        # convert day from date to ISO string
        for row in results:
            row['day'] = row['day'].isoformat()
        return results

    def longest_listening_streak(self, user_id, start_dt, end_dt):
        # 1. fetch all distinct listening dates
        sql = """
            SELECT DISTINCT DATE(time) AS d
              FROM mydb.user_segments
             WHERE user_id=%s
               AND time BETWEEN %s AND %s
             ORDER BY d
        """
        cursor = self.conn.cursor()
        cursor.execute(sql, (user_id, start_dt, end_dt))
        dates = [row[0] for row in cursor.fetchall()]  # list of datetime.date
        cursor.close()

        if not dates:
            return 0

        max_streak = curr_streak = 1
        for prev, curr in zip(dates, dates[1:]):
            if curr - prev == timedelta(days=1):
                curr_streak += 1
            else:
                max_streak = max(max_streak, curr_streak)
                curr_streak = 1
        return max(max_streak, curr_streak)

    def close(self):
        self.conn.close()


# Example usage:
if __name__ == '__main__':
    db = DBController(host="192.168.1.20", user="stopify", password="stop123", database="mydb")

    print("\nPrinting all tables:")
    db.print_tables()
    db.print_users()

    print(db.get_playlists_by_user(1))
    print(db.get_all_song_names())
    print(db.get_followings_username(5))
    print(db.get_social_table())
    print(db.get_user_playlist_by_username("1"))
    print(db.is_admin(1))
    print(db.get_albums_ids_names())

    print(db.get_all_users())
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
    album_id = db.create_album("Dire Straits (Remastered)", "Dire Straits", "1.jpg")
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

