import os  # Used for file system operations, e.g., checking paths
import pickle  # Used for serializing/deserializing data (e.g., training data)
import sys  # Used for system operations, e.g., exiting on errors

import librosa  # Used for audio processing, e.g., loading and creating spectrograms
import librosa.display  # Used for visualizing spectrograms (not used in this code)
import numpy as np  # Used for numerical computations and array operations
import pandas as pd  # Used for handling CSV data with multi-level headers
import tensorflow as tf  # Used for building and training the CNN model
from tensorflow.keras.layers import InputLayer, Conv2D, MaxPooling2D, Flatten, Dense  # Neural network layers
from tensorflow.keras.models import Sequential  # Sequential model for CNN

# --------------------------
# Path Variables
# --------------------------
AUDIO_DIR = r'C:\Users\uv\Downloads\fma_small\fma_small'  # Directory containing audio files
ECHONEST_CSV = r'C:\Users\uv\Downloads\fma_metadata\fma_metadata\echonest.csv'  # CSV with audio features
NEW_SONG_PATH = r'songs/4.ogg'  # Path to a test song for prediction
FIXED_FRAMES = 130  # Fixed number of time frames for spectrograms


# --------------------------
# Data Preparation Functions
# --------------------------
def get_audio_path(track_id, audio_dir=AUDIO_DIR):
    """
    Construct the file path for an audio track based on its ID.

    Assumes a directory structure where tracks are organized by the first three digits of their ID.

    :param track_id: Integer ID of the track.
    :param audio_dir: Root directory containing audio files.
    :return: Full file path to the audio file.
    """
    track_id_str = str(track_id).zfill(6)  # Pad ID to 6 digits
    folder = track_id_str[:3]  # First 3 digits for folder
    return os.path.join(audio_dir, folder, track_id_str + '.mp3')


def song_to_spectrograms(file_path, segment_duration=15, sr=22050,
                         n_fft=2048, hop_length=512, n_mels=128, fixed_frames=FIXED_FRAMES):
    """
    Convert an audio file into a list of normalized mel spectrograms.

    Splits the audio into segments, computes mel spectrograms, and normalizes them to a fixed size.

    :param file_path: Path to the audio file.
    :param segment_duration: Duration of each segment in seconds (default: 15).
    :param sr: Sampling rate (default: 22050 Hz).
    :param n_fft: FFT window size (default: 2048).
    :param hop_length: Hop length for spectrogram (default: 512).
    :param n_mels: Number of mel bands (default: 128).
    :param fixed_frames: Fixed number of time frames for spectrograms.
    :return: Numpy array of normalized spectrograms, or empty array if file is invalid.
    """
    if not os.path.isfile(file_path):
        print(f"[Warning] File does not exist: {file_path}")
        return np.array([])

    # Load audio file
    y, sr = librosa.load(file_path, sr=sr)
    segment_samples = int(segment_duration * sr)  # Samples per segment
    num_segments = len(y) // segment_samples
    spectrograms = []

    # Process each full segment
    for i in range(num_segments):
        start = i * segment_samples
        end = start + segment_samples
        y_segment = y[start:end]
        # Compute mel spectrogram
        S = librosa.feature.melspectrogram(y=y_segment, sr=sr, n_fft=n_fft,
                                           hop_length=hop_length, n_mels=n_mels)
        S_dB = librosa.power_to_db(S, ref=np.max)  # Convert to dB scale
        # Pad or truncate to fixed number of frames
        if S_dB.shape[1] < fixed_frames:
            pad_width = fixed_frames - S_dB.shape[1]
            S_dB = np.pad(S_dB, ((0, 0), (0, pad_width)), mode='constant')
        else:
            S_dB = S_dB[:, :fixed_frames]
        # Normalize to [0, 1]
        S_norm = (S_dB - S_dB.min()) / (S_dB.max() - S_dB.min())
        S_norm = np.expand_dims(S_norm, axis=-1)[..., :1]  # Single channel
        spectrograms.append(S_norm)

    # Handle leftover segment
    leftover = len(y) % segment_samples
    if leftover != 0:
        start = num_segments * segment_samples
        y_segment = y[start:]
        pad_width = segment_samples - leftover
        y_segment = np.pad(y_segment, (0, pad_width), mode='constant')
        S = librosa.feature.melspectrogram(y=y_segment, sr=sr, n_fft=n_fft,
                                           hop_length=hop_length, n_mels=n_mels)
        S_dB = librosa.power_to_db(S, ref=np.max)
        if S_dB.shape[1] < fixed_frames:
            pad_width = fixed_frames - S_dB.shape[1]
            S_dB = np.pad(S_dB, ((0, 0), (0, pad_width)), mode='constant')
        else:
            S_dB = S_dB[:, :fixed_frames]
        S_norm = (S_dB - S_dB.min()) / (S_dB.max() - S_dB.min())
        S_norm = np.expand_dims(S_norm, axis=-1)[..., :1]
        spectrograms.append(S_norm)

    if len(spectrograms) == 0:
        return np.array([])
    return np.array(spectrograms)


def prepare_training_data(features_df, audio_dir, num_tracks=100,
                          segment_duration=15, sr=22050,
                          n_fft=2048, hop_length=512, n_mels=128, fixed_frames=FIXED_FRAMES):
    """
    Prepare training data by generating spectrograms and corresponding features.

    Processes audio files to create spectrograms and pairs them with Echonest features.

    :param features_df: DataFrame with track IDs as index and feature columns.
    :param audio_dir: Directory containing audio files.
    :param num_tracks: Maximum number of tracks to process (default: 100).
    :param segment_duration: Duration of each audio segment (default: 15 seconds).
    :param sr: Sampling rate (default: 22050 Hz).
    :param n_fft: FFT window size (default: 2048).
    :param hop_length: Hop length for spectrogram (default: 512).
    :param n_mels: Number of mel bands (default: 128).
    :param fixed_frames: Fixed number of time frames for spectrograms.
    :return: Tuple (X, Y) where X is spectrograms and Y is feature arrays, or empty arrays if no data.
    """
    X = []  # Spectrograms
    Y = []  # Features
    counter = 0
    print(features_df)

    # Process each track in the DataFrame
    for track_id in features_df.index:
        audio_path = get_audio_path(track_id, audio_dir)
        if not os.path.exists(audio_path):
            print(f"Audio file not found: {audio_path}")
            continue
        spectrograms = song_to_spectrograms(audio_path, segment_duration, sr,
                                            n_fft, hop_length, n_mels, fixed_frames)
        if spectrograms.size == 0:
            print(f"[Warning] No spectrogram data for track {track_id}")
            continue
        features = features_df.loc[track_id].values  # 6 audio features
        # Pair each spectrogram with the track's features
        for spec in spectrograms:
            X.append(spec)
            Y.append(features)
        counter += 1

    print(f"Prepared data for {counter} tracks (some might be missing audio).")
    if len(X) == 0:
        return np.array([]), np.array([])
    return np.array(X), np.array(Y)


# --------------------------
# Build TensorFlow Model
# --------------------------
def build_tf_model(input_shape, num_outputs):
    """
    Build a convolutional neural network (CNN) for predicting audio features.

    The model processes mel spectrograms and outputs feature predictions in [0, 1].

    :param input_shape: Shape of input spectrograms (e.g., (128, 130, 1)).
    :param num_outputs: Number of output features (e.g., 6 for Echonest features).
    :return: Compiled Keras Sequential model.
    """
    model = Sequential([
        InputLayer(input_shape=input_shape),
        Conv2D(16, (3, 3), padding='same', activation='relu'),  # Convolutional layer
        MaxPooling2D(pool_size=(2, 2), strides=2),  # Downsample feature maps
        Flatten(),  # Convert to 1D vector
        Dense(256, activation='relu'),  # Fully connected layer
        Dense(num_outputs, activation='sigmoid')  # Output layer (0 to 1)
    ])
    # Compile with Adam optimizer and mean squared error loss
    model.compile(optimizer=tf.keras.optimizers.Adam(learning_rate=1e-4),
                  loss='mse',
                  metrics=[tf.keras.metrics.RootMeanSquaredError()])
    model.summary()
    return model


def load_model_and_calc(path):
    """
    Load a pre-trained model and predict audio features for a song.

    Generates spectrograms for the input song and computes average feature predictions.

    :param path: Path to the audio file.
    :return: Numpy array of predicted features (e.g., acousticness, danceability).
    """
    print("Model already trained. Skipping training.")
    # Load pre-trained model
    model = tf.keras.models.load_model(
        "trained_model.h5",
        custom_objects={'mse': tf.keras.losses.MeanSquaredError()}
    )
    # Generate spectrograms for the song
    spectrograms = song_to_spectrograms(path, fixed_frames=FIXED_FRAMES)
    if spectrograms.size == 0:
        print("[Warning] Could not compute spectrograms for the song.")
        return np.array([])  # Return empty array on failure

    # Predict features for each spectrogram
    predictions = []
    for spec in spectrograms:
        spec = spec.reshape(1, spec.shape[0], spec.shape[1], spec.shape[2])  # Batch shape
        pred = model.predict(spec)
        predictions.append(pred[0])

    # Compute average prediction
    predictions = np.array(predictions)
    avg_prediction = np.mean(predictions, axis=0)
    feature_names = [
        "acousticness", "danceability", "energy",
        "instrumentalness", "liveness", "speechiness"
    ]
    print("Predicted Echonest features:")
    for name, value in zip(feature_names, avg_prediction):
        print(f"  {name}: {value:.4f}")
    return avg_prediction


# --------------------------
# Main Execution
# --------------------------
if __name__ == "__main__":
    if os.path.exists("../trained_model.h5"):
        print("Model already trained. Skipping training.")
        model = tf.keras.models.load_model(
            "trained_model.h5",
            custom_objects={'mse': tf.keras.losses.MeanSquaredError()}
        )
    else:
        # Validate Echonest CSV exists
        if not os.path.isfile(ECHONEST_CSV):
            print(f"[Error] Could not find echonest.csv at {ECHONEST_CSV}.")
            sys.exit(1)

        # Load CSV with multi-level headers
        try:
            echonest = pd.read_csv(
                ECHONEST_CSV,
                index_col=0,
                header=[0, 1, 2],
                low_memory=False
            )
        except ValueError as e:
            print("[Error] Could not parse CSV with 3-level header. Check your CSV format.")
            print(e)
            sys.exit(1)

        print("Multi-level columns found. echonest.columns:")
        print(echonest.columns)

        # Validate required columns
        required_cols = [
            ('echonest', 'audio_features', 'acousticness'),
            ('echonest', 'audio_features', 'danceability'),
            ('echonest', 'audio_features', 'energy'),
            ('echonest', 'audio_features', 'instrumentalness'),
            ('echonest', 'audio_features', 'liveness'),
            ('echonest', 'audio_features', 'speechiness')
        ]
        for col in required_cols:
            if col not in echonest.columns:
                print(f"[Error] Column {col} not found in CSV. Exiting.")
                sys.exit(1)

        # Extract features and remove missing data
        features_df = echonest[required_cols].dropna()
        if len(features_df) == 0:
            print("[Error] features_df is empty after dropping NA. Nothing to train on.")
            sys.exit(1)

        # Prepare training data
        print("Preparing training data...")
        X, y = prepare_training_data(features_df, AUDIO_DIR, num_tracks=1000, fixed_frames=FIXED_FRAMES)
        with open("X.pkl", "wb") as f:
            pickle.dump(X, f)
        with open("y.pkl", "wb") as f:
            pickle.dump(y, f)

        # Validate training data
        if X.size == 0 or y.size == 0:
            print("[Error] No training data generated. Check your AUDIO_DIR path and ensure audio files are present.")
            sys.exit(1)

        # Build and train model
        input_shape = X.shape[1:]  # e.g., (128, 130, 1)
        num_outputs = y.shape[1]  # 6 features
        print(f"Input shape: {input_shape}, Number of output features: {num_outputs}")
        model = build_tf_model(input_shape, num_outputs)
        history = model.fit(X, y, epochs=1000, batch_size=16, verbose=2)

        # Save trained model
        model.save("trained_model.h5")
        print("Model saved as 'trained_model.h5'.")

    # Predict features for a new song
    print(f"\nPredicting Echonest features for {NEW_SONG_PATH}...")
    spectrograms = song_to_spectrograms(NEW_SONG_PATH, fixed_frames=FIXED_FRAMES)
    if spectrograms.size == 0:
        print("[Warning] Could not compute spectrograms for the song.")
    else:
        predictions = []
        for spec in spectrograms:
            spec = spec.reshape(1, spec.shape[0], spec.shape[1], spec.shape[2])
            pred = model.predict(spec)
            predictions.append(pred[0])
        predictions = np.array(predictions)
        avg_prediction = np.mean(predictions, axis=0)
        feature_names = [
            "acousticness", "danceability", "energy",
            "instrumentalness", "liveness", "speechiness"
        ]
        print("Predicted Echonest features:")
        for name, value in zip(feature_names, avg_prediction):
            print(f"  {name}: {value:.4f}")