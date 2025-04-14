from datetime import datetime
from math import exp, log
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np
import random
import base64
from song import Song

def vectorize_profile(profile):
    """
    Convert a profile dictionary into a numpy vector using a fixed feature order.
    """
    return np.array(list(profile.values())[:-2]).reshape(1, -1)

def vectorize_song(profile):
    """
    Convert a profile dictionary into a numpy vector using a fixed feature order.
    """
    return np.array(list(profile.values())[1:]).reshape(1, -1)


class Recommender:
    def __init__(self, db):
        self.db = db

    def create_profile(self, user_id, segments, T_HALF):
        """
        Calculate the weighted user profile from playback segments using a half-life-based decay.

        Args:
            segments (list of PlaybackSegment)
            T_HALF (float): Desired half-life in seconds (e.g., one week ≈ 604800 seconds).

        Returns:
            dict or None: Weighted average profile of the user.
        """
        # Calculate lambda for the decay based on desired half-life.
        lambda_decay = log(2) / T_HALF

        current_time = datetime.now()

        # Initialize aggregated feature sums.
        aggregated_features = {
            "acousticness": 0.0,
            "danceability": 0.0,
            "energy": 0.0,
            "instrumentalness": 0.0,
            "liveness": 0.0,
            "speechiness": 0.0
        }
        total_weight = 0.0

        for seg in segments:
            song_id = seg.song_id
            duration = seg.duration
            try:
                seg_time = datetime.fromisoformat(seg.timestamp)
            except Exception as e:
                print(f"Skipping segment with invalid timestamp: {seg.timestamp}")
                continue

            delta_seconds = (current_time - seg_time).total_seconds()
            weight = duration * exp(-lambda_decay * delta_seconds)
            total_weight += weight

            features = db.get_song_profile(song_id)
            if not features:
                print(f"Song features for {song_id} not found. Skipping segment.")
                continue

            for key in aggregated_features:
                aggregated_features[key] += weight * features.get(key, 0.0)

        if total_weight == 0:
            return None

        user_profile = {key: aggregated_features[key] / total_weight for key in aggregated_features}
        db.update_user_profile(user_id, user_profile, total_weight)
        return user_profile, total_weight

    def aggregate_segments(self, segments, T_HALF):
        """
        Aggregate new segments into a weighted sum of feature values and a total weight.

        Args:
            segments (list of dict): Each segment has:
                - "song_id": str, identifier of the song.
                - "duration": float, seconds listened.
                - "timestamp": str, ISO formatted timestamp.
            T_HALF (float): Desired half-life in seconds.

        Returns:
            tuple: (weighted_feature_sum, total_weight)
                weighted_feature_sum is a dict with summed (weight * feature)
                total_weight is the sum of all segment weights.
        """
        lambda_decay = log(2) / T_HALF
        current_time = datetime.now()

        # Initialize the accumulator for each feature.
        weighted_sum = {
            "acoustic": 0.0,
            "dance": 0.0,
            "energy": 0.0,
            "instrument": 0.0,
            "live": 0.0,
            "speech": 0.0
        }
        total_weight = 0.0

        for seg in segments:
            song_id = seg.song_id
            duration = seg.duration
            try:
                seg_time = datetime.fromisoformat(str(seg.timestamp).strip())
            except Exception as e:
                print(f"Skipping segment with invalid timestamp: {seg.timestamp}")
                continue

            # Calculate the time difference in seconds and the weight for this segment.
            delta_seconds = (current_time - seg_time).total_seconds()
            weight = duration * exp(-lambda_decay * delta_seconds)
            total_weight += weight

            features = self.db.get_song_profile(song_id)
            if not features:
                print(f"Song features for {song_id} not found. Skipping segment.")
                continue

            # For each feature, add weight * feature value.
            for key in weighted_sum:
                weighted_sum[key] += weight * features[key]

        return weighted_sum, total_weight

    def update_user_profile(self, user_id, new_segments, T_HALF=604800):
        """
        Update an existing user profile with new playback segments.
        """
        result = self.db.get_user_profile(user_id)
        existing_weight = result['weight']
        del result['weight']
        last_update = result['last_updated']
        del result['last_updated']
        existing_profile = result
        lambda_decay = log(2) / T_HALF
        current_time = datetime.now()
        # Compute decay factor for the time elapsed since last update.
        delta_time = (current_time - last_update).total_seconds()
        decay_factor = exp(-lambda_decay * delta_time)

        # Decay the existing total weight and calculate the decayed weighted sum.
        decayed_weight = existing_weight * decay_factor
        # The decayed weighted sum is simply the profile multiplied by the decayed weight.
        decayed_profile_sum = {key: existing_profile.get(key, 0.0) * decayed_weight
                               for key in existing_profile}

        # Aggregate the new segments.
        new_profile_sum, new_total_weight = self.aggregate_segments(new_segments, T_HALF)

        # Combine the two weighted sums and weights.
        combined_weight = decayed_weight + new_total_weight
        if combined_weight == 0:
            return existing_profile, existing_weight, last_update

        # Sum the feature contributions.
        combined_profile_sum = {}
        for key in decayed_profile_sum:
            combined_profile_sum[key] = decayed_profile_sum[key] + new_profile_sum.get(key, 0.0)

        # Compute the updated profile as the weighted average.
        updated_profile = {key: combined_profile_sum[key] / combined_weight for key in combined_profile_sum}

        return updated_profile, combined_weight, current_time

    def recommend(self, user_id, num_recommendations=10):
        # Retrieve the user's current profile.
        # Assume this returns a tuple like (profile_dict, cumulative_weight, last_update)
        result = self.db.get_user_profile(user_id)
        if not result:
            print("User profile not found. Please ensure the profile is created.")
            return []

        user_profile = result
        print(f"User profile: {user_profile}")
        user_vector = vectorize_profile(user_profile)
        print(f"User profile: {user_vector}")

        # Retrieve all song profiles from the database.
        # Assume this returns a dictionary mapping song IDs to a dictionary of feature values.
        all_song_profiles = self.db.get_all_song_profiles()
        all_song_profiles = {profile['songs_id']: vectorize_song(profile) for profile in all_song_profiles}
        if not all_song_profiles:
            print("No song profiles found in the database.")
            return []

        recommendations = []
        for song_id, song_vector in all_song_profiles.items():
            # sklearn's cosine_similarity returns a 2D array.
            similarity = cosine_similarity(user_vector, song_vector)[0, 0]
            recommendations.append((song_id, similarity))

        # Add a bit of randomness to the similarity scores for exploration.
        randomized_recommendations = [
            (song_id, sim * random.uniform(0.9, 1.1)) for song_id, sim in recommendations
        ]
        randomized_recommendations.sort(key=lambda tup: tup[1], reverse=True)
        print(recommendations)
        songs = []
        for i, _ in randomized_recommendations:
            print(i)
            song = self.db.get_song(str(i))
            album = self.db.get_album(song['album_id'])
            with open(f'covers/{album["id"]}.jpg', 'rb') as f:
                cover_data = f.read()
            cover_b64 = base64.b64encode(cover_data)
            songs.append(Song(i, song['name'], song['author'], album['name'], cover_b64))
        return songs[:num_recommendations]

if __name__ == '__main__':
    # Example usage:
    db = None  # Replace with actual database connection
