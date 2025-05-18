from PIL import Image
from ogg_handler import *
import mysql_helper
import os
import network_with_tensor
from google import genai

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
    with open(f"songs/{song_id}.ogg", "wb") as f:
        with open(song_file, "rb") as song_f:
            f.write(song_f.read())

    pred = network_with_tensor.load_model_and_calc(song_file)
    db.create_song_profile(song_id, pred)

def extract_all(db, user_id, start_dt, end_dt, top_n=5):
    return {
        'total_minutes': db.total_listening_minutes(user_id, start_dt, end_dt),
        'top_songs': db.top_songs(user_id, start_dt, end_dt, top_n),
        'top_artists': db.top_artists(user_id, start_dt, end_dt, top_n),
        'peak_days': db.peak_listening_days(user_id, start_dt, end_dt, top_n),
        'longest_streak': db.longest_listening_streak(user_id, start_dt, end_dt),
    }

def generate_wrapped(db, user_id, start_dt, end_dt):
    print('context')
    context = extract_all(db, user_id, start_dt, end_dt)
    print(context)
    with open("google_key_.txt", "r") as file:
        key = file.read()
    client = genai.Client(api_key=key)

    prompt = f"""System: You are Stopify’s “Wrapped” assistant. Your job is to take a user’s listening stats and turn them into a fun, punchy year-end recap.

            User: Here are my {start_dt}:{end_dt} listening stats: {context}
            Generate:
            1. A celebratory paragraph (~150–180 words) that highlights these stats in a lively, “year-in-review” tone.
            2. Three “Did you know?” bullet-point fun facts (e.g. “Did you know you listened more to jazz on Fridays?”).
            
            Generate a paragraph for each reqeust, title the first paragraph “Your Year in Review” and the second “Fun Facts”.
            Make it upbeat, shareable, and branded as “Stopify Wrapped {start_dt}:{end_dt}.
            
            Generate it in a styled html format
            """
    response = client.models.generate_content(
        model="gemini-2.0-flash", contents=prompt
    )
    return response.text


if __name__ == '__main__':
    db = mysql_helper.DBController(
        host="192.168.1.20", user="stopify", password="stop123", database="mydb"
    )
    generate_wrapped(db, user_id=1, start_dt='2024-01-01', end_dt='2026-12-31')
    r"""album_id = create_album(db, r"C:\Users\uv\Downloads\GunsnRosesAppetiteforDestructionalbumcover.jpg", "Appetite for Destruction", "Guns N' Roses")
    create_song(db, r"C:\Users\uv\Downloads\Guns N' Roses - Sweet Child O' Mine (Lyrics).ogg", "Sweet Child O Mine", "Guns N' Roses", album_id)
    create_song(db, r"C:\Users\uv\Downloads\Guns N' Roses - Welcome To The Jungle.ogg", "Welcome To The Jungle", "Guns N' Roses", album_id)

    album_id = create_album(db, r"C:\Users\uv\Downloads\ab67616d0000b273afe473a4a47a4e69ab174069.jpeg", "Typical of Me", "Laufey")
    create_song(db, r"C:\Users\uv\Downloads\Laufey - Like The Movies (Official Audio).ogg", "Like The Movies", "Laufey", album_id)
    create_song(db, r"C:\Users\uv\Downloads\Laufey - I Wish You Love (Official Audio).ogg", "I Wish You Love", "Laufey", album_id)
    create_song(db, r"C:\Users\uv\Downloads\Laufey - Best Friend (Official Video).ogg", "Best Friend", "Laufey", album_id)

    album_id = create_album(db, r"C:\Users\uv\Downloads\feel_it.jpg", "Single", "d4vd")
    create_song(db, r"C:\Users\uv\Downloads\d4vd - Feel It (Animated Lyric Video) [TubeRipper.cc].ogg", "Feel It", "d4vd", album_id)

    album_id = create_album(db, r"C:\Users\uv\Downloads\download (1).jpeg", "פצעים ונשיקות", "מוניקה סקס")
    create_song(db, r"C:\Users\uv\Downloads\guys.ogg", "כל החברה", "מוניקה סקס", album_id)
    create_song(db, r"C:\Users\uv\Downloads\floor.ogg", "על הרצפה", "מוניקה סקס", album_id)
    create_song(db, r"C:\Users\uv\Downloads\wound.ogg", "פצעים ונשיקות", "מוניקה סקס", album_id)
    create_song(db, r"C:\Users\uv\Downloads\gray.ogg", "מכה אפורה", "מוניקה סקס", album_id)

    album_id = create_album(db, r"C:\Users\uv\Downloads\download (2).jpeg", "Single", "Laufey")
    create_song(db, r"C:\Users\uv\Downloads\Laufey - From The Start (Official Music Video) (1).ogg", "From The Start", "Laufey", album_id)
    
    album_id = create_album(db, r"C:\Users\uv\Downloads\p_god.jpg", "Single", "Polyphia")
    create_song(db, r"C:\Users\uv\Downloads\Polyphia - Playing God (Official Music Video).ogg", "Playing God", "Polyphia", album_id)
    
    album_id = create_album(db, r"C:\Users\uv\Downloads\young.jpeg", "Writer's Block", "Peter Bjorn & John")
    create_song(db, r"C:\Users\uv\Downloads\Peter Bjorn And John - Young Folks.ogg", "Young Folks", "Peter Bjorn & John", album_id)
    """
