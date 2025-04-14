from PIL import Image
from ogg_handler import *
import mysql_helper
import os
import network_with_tensor

def create_album(db, album_cover_path, name, author):
    """
    Creates an album cover image with the given name and author.
    """
    if not os.path.exists(album_cover_path):
        raise FileNotFoundError(f"Album cover path '{album_cover_path}' does not exist.")

    img = Image.open(album_cover_path)

    resized_img = img.resize((64, 64))

    album_id = db.create_album(name, author, f"{name}.jpg")

    with open(f"covers/{album_id}.jpg", "wb") as f:
        resized_img.save(f, format='JPEG')
    print(f"Album cover '{name}.jpg' created successfully.")

    return album_id


def create_song(db, song_file, song_name, song_author, album_id):
    """
    Creates a song entry in the database.
    """
    length = get_ogg_duration(song_file)
    sample_rate = get_sample_rate(song_file)
    pages = count_ogg_pages(song_file)

    song_id = db.create_song(album_id, song_name, song_author, length, sample_rate, pages)
    with open(f"{song_id}.ogg", "wb") as f:
        with open(song_file, "rb") as song_f:
            f.write(song_f.read())

    pred = network_with_tensor.load_model_and_calc(song_file)
    db.create_song_profile(song_id, pred)


if __name__ == '__main__':
    db = mysql_helper.DBController(
        host="192.168.1.20", user="stopify", password="stop123", database="mydb"
    )
    album_id = create_album(db, r"C:\Users\uv\Downloads\ab67616d0000b273afe473a4a47a4e69ab174069.jpeg", "Typical of Me", "Laufey")
    create_song(db, r"C:\Users\uv\Downloads\Laufey - Like The Movies (Official Audio).ogg", "Like The Movies", "Laufey", album_id)
    create_song(db, r"C:\Users\uv\Downloads\Laufey - I Wish You Love (Official Audio).ogg", "I Wish You Love", "Laufey", album_id)
    create_song(db, r"C:\Users\uv\Downloads\Laufey - Best Friend (Official Video).ogg", "Best Friend", "Laufey", album_id)
