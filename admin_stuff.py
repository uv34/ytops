import os  # Used for interacting with the operating system, e.g., file operations
from PIL import Image  # Used for image processing, specifically for resizing album covers
from google import genai  # Used for interacting with the Google Gemini API to generate content

import mysql_helper  # Custom module for MySQL database operations
import network_with_tensor  # Custom module for machine learning operations, likely involving TensorFlow
from ogg_handler import *  # Custom module for handling OGG audio files, including duration, sample rate, and page counting


def create_album(db, album_cover_path, name, author):
    """
    Create an album in the database and save its cover image.

    This function resizes the provided album cover image to 64x64 pixels, saves it with a filename based on the album's name,
    and creates an entry in the database for the new album.

    :param db: An instance of the database controller (mysql_helper.DBController).
    :param album_cover_path: Path to the album cover image file.
    :param name: Name of the album.
    :param author: Author or artist of the album.
    :return: The ID of the newly created album.
    :raises FileNotFoundError: If the album cover image file does not exist.
    """
    if not os.path.exists(album_cover_path):
        raise FileNotFoundError(f"Album cover path '{album_cover_path}' does not exist.")

    # Open and resize the album cover image to 64x64 pixels
    img = Image.open(album_cover_path)
    resized_img = img.resize((64, 64))

    # Create the album in the database and get its ID
    album_id = db.create_album(name, author, f"{name}.jpg")

    # Save the resized image with the album ID as the filename
    with open(f"covers/{album_id}.jpg", "wb") as f:
        resized_img.save(f, format='JPEG')
    print(f"Album cover '{name}.jpg' created successfully.")

    return album_id


def create_song(db, song_file, song_name, song_author, album_id):
    """
    Create a song entry in the database and save the song file.

    This function extracts metadata from the OGG song file (duration, sample rate, and number of pages),
    creates a song entry in the database, saves the song file with the song ID, and generates a song profile
    using a machine learning model.

    :param db: An instance of the database controller (mysql_helper.DBController).
    :param song_file: Path to the OGG song file.
    :param song_name: Name of the song.
    :param song_author: Author or artist of the song.
    :param album_id: ID of the album to which the song belongs.
    """
    # Extract metadata from the OGG file
    length = get_ogg_duration(song_file)  # Duration in seconds
    sample_rate = get_sample_rate(song_file)  # Sample rate in Hz
    pages = count_ogg_pages(song_file)  # Number of OGG pages

    # Create the song in the database and get its ID
    song_id = db.create_song(album_id, song_name, song_author, length, sample_rate, pages)

    # Save the song file with the song ID as the filename
    with open(f"songs/{song_id}.ogg", "wb") as f:
        with open(song_file, "rb") as song_f:
            f.write(song_f.read())

    # Generate a song profile using a machine learning model and save it in the database
    pred = network_with_tensor.load_model_and_calc(song_file)
    db.create_song_profile(song_id, pred)


def extract_all(db, user_id, start_dt, end_dt, top_n=5):
    """
    Extract comprehensive listening statistics for a user within a specified date range.

    This function gathers various statistics such as total listening minutes, top songs, top artists,
    peak listening days, and the longest listening streak.

    :param db: An instance of the database controller (mysql_helper.DBController).
    :param user_id: ID of the user.
    :param start_dt: Start date for the statistics (string, e.g., '2024-01-01').
    :param end_dt: End date for the statistics (string, e.g., '2024-12-31').
    :param top_n: Number of top items to retrieve (default is 5).
    :return: A dictionary containing the extracted statistics.
    """
    return {
        'total_minutes': db.total_listening_minutes(user_id, start_dt, end_dt),
        'top_songs': db.top_songs(user_id, start_dt, end_dt, top_n),
        'top_artists': db.top_artists(user_id, start_dt, end_dt, top_n),
        'peak_days': db.peak_listening_days(user_id, start_dt, end_dt, top_n),
        'longest_streak': db.longest_listening_streak(user_id, start_dt, end_dt),
    }


def generate_wrapped(db, user_id, start_dt, end_dt):
    """
    Generate a "Wrapped" summary for a user's listening activity using the Google Gemini API.

    This function extracts the user's listening statistics and uses the Gemini API to generate a fun,
    engaging summary in HTML format.

    :param db: An instance of the database controller (mysql_helper.DBController).
    :param user_id: ID of the user.
    :param start_dt: Start date for the summary (string, e.g., '2024-01-01').
    :param end_dt: End date for the summary (string, e.g., '2024-12-31').
    :return: The generated HTML summary as a string.
    """
    print('context')
    context = extract_all(db, user_id, start_dt, end_dt)
    print(context)

    # Read the Google API key from a file
    with open("google_key_.txt", "r") as file:
        key = file.read()

    # Initialize the Google Gemini client with the API key
    client = genai.Client(api_key=key)

    # Define the prompt for the Gemini API to generate the wrapped summary
    prompt = """System: You are Stopify’s “Wrapped” assistant. Your job is to take a user’s listening stats and turn them into a fun, punchy year-end recap.

            User: Here are my start_dt-""" +str(start_dt) + """: end_dt-""" +str(end_dt) + """ listening stats: """ + str(context) + """
            Generate:
            1. A celebratory paragraph (~150–180 words) that highlights these stats in a lively, “year-in-review” tone.
            2. Three “Did you know?” bullet-point fun facts (e.g. “Did you know you listened more to jazz on Fridays?”).

            Generate a paragraph for each request, title the first paragraph “Your Year in Review” and the second “Fun Facts”.
            Make it upbeat, shareable, and branded as “Stopify Wrapped {start_dt}:{end_dt}”.

            Generate it in a styled HTML format
            
            EXAMPLE:
            <!DOCTYPE html>
            <html lang="en">
            <head>
              <meta charset="UTF-8" />
              <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
              <title>Stopify Wrapped 2024-01-01:2026-12-31</title>
              <link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@400;700&display=swap" rel="stylesheet">
              <style>
                /* Base styles */
                body {
                  margin: 0;
                  padding: 0;
                  background: #f0f4f8;
                  font-family: 'Montserrat', sans-serif;
                  color: #333;
                }
                .container {
                  max-width: 800px;
                  margin: 40px auto;
                  background: #ffffff;
                  border-radius: 10px;
                  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
                  overflow: hidden;
                }
            
                /* Header */
                .header {
                  background: linear-gradient(135deg, #6a11cb 0%, #2575fc 100%);
                  padding: 30px 20px;
                  text-align: center;
                  color: #fff;
                }
                .header h2 {
                  margin: 0;
                  font-size: 2.5rem;
                  letter-spacing: 1px;
                }
            
                /* Content area */
                .content {
                  padding: 30px 40px;
                  line-height: 1.6;
                }
                .section-title {
                  font-size: 1.8rem;
                  margin-bottom: 15px;
                  color: #2575fc;
                  border-bottom: 2px solid #2575fc;
                  padding-bottom: 8px;
                }
                p {
                  margin-bottom: 20px;
                  font-size: 1rem;
                  color: #555;
                }
                .highlight {
                  font-weight: 700;
                  color: #e44d26;
                }
            
                /* Fun Facts list */
                .fun-facts {
                  list-style: none;
                  padding: 0;
                  margin: 20px 0 0;
                }
                .fun-facts li {
                  background: #f7f9fb;
                  border-left: 4px solid #2575fc;
                  padding: 15px 20px;
                  margin-bottom: 15px;
                  border-radius: 5px;
                  font-size: 1rem;
                  color: #555;
                }
                .fun-facts b {
                  color: #333;
                }
            
                /* Responsive tweaks */
                @media (max-width: 600px) {
                  .content {
                    padding: 20px;
                  }
                  .header h2 {
                    font-size: 2rem;
                  }
                  .section-title {
                    font-size: 1.5rem;
                  }
                }
              </style>
            </head>
            <body>
              <div class="container">
                <div class="header">
                  <h2>Stopify Wrapped 2024-01-01:2026-12-31</h2>
                </div>
            
                <div class="content">
                  <h3 class="section-title">Your Year in Review</h3>
                  <p>
                    Get ready to relive your sonic journey! Your Stopify Wrapped 
                    <span class="highlight">2024-01-01:2026-12-31</span> is here, and it's packed with incredible listening moments. 
                    During this period, you clocked in a whopping <span class="highlight">272.49 minutes</span> of pure audio bliss! 
                    It's clear you have a soft spot for <span class="highlight">Laufey</span>, who dominated your ears with a staggering 
                    <span class="highlight">162.45 minutes</span> of playtime—making them your top artist by a landslide. Your anthem of the 
                    year? None other than <span class="highlight">'I Wish You Love' by Laufey</span>, which resonated with you for an amazing 
                    <span class="highlight">105.13 minutes</span>! You also showed some love for <span class="highlight">מוניקה סקס</span> and 
                    <span class="highlight">d4vd</span>. May 8th, 2025 turned out to be your ultimate listening day, where you enjoyed a massive 
                    <span class="highlight">80.48 minutes</span> of music—plus you maintained an impressive listening streak of 7 days!
                  </p>
            
                  <h3 class="section-title">Fun Facts</h3>
                  <ul class="fun-facts">
                    <li><b>Did you know?</b> You spent more time listening to Laufey than the entire runtime of some classic movies! Now that's dedication.</li>
                    <li><b>Did you know?</b> Your top 5 listening days were all within a single month (April–May 2025).</li>
                    <li><b>Did you know?</b> 'I Wish You Love' made up a whopping 38% of your total listening time. Sounds like it might be time for a new favorite!</li>
                  </ul>
                </div>
              </div>
            </body>
            </html>

            """

    # Send the prompt to the Gemini API and get the response
    response = client.models.generate_content(
        model="gemini-2.0-flash", contents=prompt
    )

    return response.text


if __name__ == '__main__':
    # Example usage: Connect to the database and generate a wrapped summary for a user
    db = mysql_helper.DBController(
        host="192.168.1.14", user="stopify", password="stop123", database="mydb"
    )
    print(generate_wrapped(db, user_id=1, start_dt='2024-01-01', end_dt='2026-12-31'))

    # The following code is commented out and demonstrates how to create albums and songs
    r"""
    album_id = create_album(db, r"C:\Users\uv\Downloads\GunsnRosesAppetiteforDestructionalbumcover.jpg", "Appetite for Destruction", "Guns N' Roses")
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