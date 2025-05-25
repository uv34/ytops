import base64  # Used for encoding album cover images
import random  # Used to add randomness to recommendation scores
from datetime import datetime  # Used for timestamp calculations
from math import exp, log  # Used for exponential decay calculations

import numpy as np  # Used for vector operations and numerical computations
from sklearn.metrics.pairwise import cosine_similarity  # Used to compute similarity between user and song profiles

from song import Song  # Custom class representing a song with attributes like ID, name, and cover

def vectorize_profile(profile):
    """
    Convert a user profile dictionary into a numpy vector for similarity calculations.

    Excludes the last two elements (assumed to be non-feature data like weight or timestamp).

    :param profile: Dictionary containing user profile features (e.g., acousticness, danceability).
    :return: Numpy array representing the profile as a 1D vector.
    """
    return np.array(list(profile.values())[:-2]).reshape(1, -1)

def vectorize_song(profile):
    """
    Convert a song profile dictionary into a numpy vector for similarity calculations.

    Excludes the first element (assumed to be the song ID).

    :param profile: Dictionary containing song profile features (e.g., acousticness, danceability).
    :return: Numpy array representing the song profile as a 1D vector.
    """
    return np.array(list(profile.values())[1:]).reshape(1, -1)

class Recommender:
    """
    A music recommendation system based on user listening history and song features.

    Uses a half-life decay model to weight playback segments and computes recommendations
    using cosine similarity between user and song profiles.

    Attributes:
        db: Database controller object for accessing user profiles, song profiles, and metadata.
    """

    def __init__(self, db):
        """
        Initialize the recommender with a database connection.

        :param db: Database controller object (e.g., mysql_helper.DBController).
        """
        self.db = db

    def create_profile(self, user_id, segments, T_HALF):
        """
        Create a weighted user profile from playback segments using exponential decay.

        Weights segments based on their age, with more recent listens contributing more
        to the profile. The decay rate is determined by the half-life (T_HALF).

        :param user_id: ID of the user.
        :param segments: List of PlaybackSegment objects, each with song_id, duration, and timestamp.
        :param T_HALF: Half-life in seconds for decay (e.g., 604800 for one week).
        :return: Tuple (user_profile, total_weight) or None if no valid segments.
        """
        # Calculate decay constant (lambda) based on half-life
        lambda_decay = log(2) / T_HALF
        current_time = datetime.now()

        # Initialize feature accumulators
        aggregated_features = {
            "acousticness": 0.0,
            "danceability": 0.0,
            "energy": 0.0,
            "instrumentalness": 0.0,
            "liveness": 0.0,
            "speechiness": 0.0
        }
        total_weight = 0.0

        # Process each playback segment
        for seg in segments:
            song_id = seg.song_id
            duration = seg.duration
            try:
                seg_time = datetime.fromisoformat(seg.timestamp)
            except Exception as e:
                print(f"Skipping segment with invalid timestamp: {seg.timestamp}")
                continue

            # Calculate weight using exponential decay based on time difference
            delta_seconds = (current_time - seg_time).total_seconds()
            weight = duration * exp(-lambda_decay * delta_seconds)
            total_weight += weight

            # Retrieve song features from the database
            features = self.db.get_song_profile(song_id)
            if not features:
                print(f"Song features for {song_id} not found. Skipping segment.")
                continue

            # Accumulate weighted feature contributions
            for key in aggregated_features:
                aggregated_features[key] += weight * features.get(key, 0.0)

        if total_weight == 0:
            return None

        # Compute weighted average for each feature
        user_profile = {key: aggregated_features[key] / total_weight for key in aggregated_features}
        # Save the profile to the database
        self.db.update_user_profile(user_id, user_profile, total_weight)
        return user_profile, total_weight

    def aggregate_segments(self, segments, T_HALF):
        """
        Aggregate playback segments into a weighted sum of features.

        Computes the sum of feature values weighted by duration and decayed by time,
        along with the total weight of all segments.

        :param segments: List of PlaybackSegment objects with song_id, duration, and timestamp.
        :param T_HALF: Half-life in seconds for decay (e.g., 604800 for one week).
        :return: Tuple (weighted_feature_sum, total_weight).
        """
        lambda_decay = log(2) / T_HALF
        current_time = datetime.now()

        # Initialize feature accumulators
        weighted_sum = {
            "acoustic": 0.0,
            "dance": 0.0,
            "energy": 0.0,
            "instrument": 0.0,
            "live": 0.0,
            "speech": 0.0
        }
        total_weight = 0.0

        # Process each segment
        for seg in segments:
            song_id = seg.song_id
            duration = seg.duration
            try:
                seg_time = datetime.fromisoformat(str(seg.timestamp).strip())
            except Exception as e:
                print(f"Skipping segment with invalid timestamp: {seg.timestamp}")
                continue

            # Calculate weight using exponential decay
            delta_seconds = (current_time - seg_time).total_seconds()
            weight = duration * exp(-lambda_decay * delta_seconds)
            total_weight += weight

            # Retrieve song features and add weighted contributions
            features = self.db.get_song_profile(song_id)
            if not features:
                print(f"Song features for {song_id} not found. Skipping segment.")
                continue

            for key in weighted_sum:
                weighted_sum[key] += weight * features[key]

        return weighted_sum, total_weight

    def update_user_profile(self, user_id, new_segments, T_HALF=604800):
        """
        Update an existing user profile with new playback segments.

        Applies decay to the existing profile based on time elapsed since the last update,
        then combines it with the new segments' contributions.

        :param user_id: ID of the user.
        :param new_segments: List of new PlaybackSegment objects.
        :param T_HALF: Half-life in seconds for decay (default: 604800, one week).
        :return: Tuple (updated_profile, combined_weight, current_time).
        """
        # Retrieve current user profile
        result = self.db.get_user_profile(user_id)
        existing_weight = result['weight']
        del result['weight']
        last_update = result['last_updated']
        del result['last_updated']
        existing_profile = result

        # Calculate decay factor for elapsed time
        lambda_decay = log(2) / T_HALF
        current_time = datetime.now()
        delta_time = (current_time - last_update).total_seconds()
        decay_factor = exp(-lambda_decay * delta_time)

        # Decay existing profile weight and feature sums
        decayed_weight = existing_weight * decay_factor
        decayed_profile_sum = {key: existing_profile.get(key, 0.0) * decayed_weight
                              for key in existing_profile}

        # Aggregate new segments
        new_profile_sum, new_total_weight = self.aggregate_segments(new_segments, T_HALF)

        # Combine decayed and new contributions
        combined_weight = decayed_weight + new_total_weight
        if combined_weight == 0:
            return existing_profile, existing_weight, last_update

        # Compute updated profile as weighted average
        combined_profile_sum = {}
        for key in decayed_profile_sum:
            combined_profile_sum[key] = decayed_profile_sum[key] + new_profile_sum.get(key, 0.0)

        updated_profile = {key: combined_profile_sum[key] / combined_weight for key in combined_profile_sum}
        return updated_profile, combined_weight, current_time

    def recommend(self, user_id, num_recommendations=10):
        """
        Generate song recommendations for a user based on their profile.

        Computes cosine similarity between the user profile and all song profiles,
        adds slight randomness to encourage exploration, and returns the top songs.

        :param user_id: ID of the user.
        :param num_recommendations: Number of songs to recommend (default: 10).
        :return: List of Song objects representing the recommended songs.
        """
        # Retrieve user profile
        result = self.db.get_user_profile(user_id)
        if not result:
            print("User profile not found. Please ensure the profile is created.")
            return []

        user_profile = result
        print(f"User profile: {user_profile}")
        user_vector = vectorize_profile(user_profile)
        print(f"User profile: {user_vector}")

        # Retrieve all song profiles
        all_song_profiles = self.db.get_all_song_profiles()
        all_song_profiles = {profile['songs_id']: vectorize_song(profile) for profile in all_song_profiles}
        if not all_song_profiles:
            print("No song profiles found in the database.")
            return []

        # Compute cosine similarity for each song
        recommendations = []
        for song_id, song_vector in all_song_profiles.items():
            similarity = cosine_similarity(user_vector, song_vector)[0, 0]
            recommendations.append((song_id, similarity))

        # Add randomness to similarity scores for exploration
        randomized_recommendations = [
            (song_id, sim * random.uniform(0.95, 1.05)) for song_id, sim in recommendations
        ]
        randomized_recommendations.sort(key=lambda tup: tup[1], reverse=True)

        # Retrieve song and album details for recommendations
        songs = []
        for song_id, _ in randomized_recommendations[:num_recommendations]:
            print(song_id)
            song = self.db.get_song(str(song_id))
            album = self.db.get_album(song['album_id'])
            with open(f'covers/{album["id"]}.jpg', 'rb') as f:
                cover_data = f.read()
            cover_b64 = base64.b64encode(cover_data)
            songs.append(Song(song_id, song['name'], song['author'], album['name'], cover_b64))
        return songs

if __name__ == '__main__':
    # Example usage: Initialize database connection
    db = None  # Replace with actual database connection