import os
import sys
import numpy as np
import pandas as pd
import librosa
import librosa.display
import tensorflow as tf
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import InputLayer, Conv2D, MaxPooling2D, Flatten, Dense

# --------------------------
# Path Variables
# --------------------------
AUDIO_DIR = r'C:\Users\uv\Downloads\fma_small\fma_small'  # Directory with audio files
ECHONEST_CSV = r'C:\Users\uv\Downloads\fma_metadata\fma_metadata\echonest.csv'  # Echonest CSV (3-level header)
NEW_SONG_PATH = r'songs/4.ogg'  # Test song path
FIXED_FRAMES = 130  # Fixed time frames for each spectrogram

# --------------------------
# Data Preparation Functions
# --------------------------
def get_audio_path(track_id, audio_dir=AUDIO_DIR):
    track_id_str = str(track_id).zfill(6)
    folder = track_id_str[:3]
    return os.path.join(audio_dir, folder, track_id_str + '.mp3')

def song_to_spectrograms(file_path, segment_duration=15, sr=22050,
                         n_fft=2048, hop_length=512, n_mels=128, fixed_frames=FIXED_FRAMES):
    if not os.path.isfile(file_path):
        print(f"[Warning] File does not exist: {file_path}")
        return np.array([])
    y, sr = librosa.load(file_path, sr=sr)
    segment_samples = int(segment_duration * sr)
    num_segments = len(y) // segment_samples
    spectrograms = []
    for i in range(num_segments):
        start = i * segment_samples
        end = start + segment_samples
        y_segment = y[start:end]
        S = librosa.feature.melspectrogram(y=y_segment, sr=sr, n_fft=n_fft,
                                           hop_length=hop_length, n_mels=n_mels)
        S_dB = librosa.power_to_db(S, ref=np.max)
        if S_dB.shape[1] < fixed_frames:
            pad_width = fixed_frames - S_dB.shape[1]
            S_dB = np.pad(S_dB, ((0,0), (0, pad_width)), mode='constant')
        else:
            S_dB = S_dB[:, :fixed_frames]
        S_norm = (S_dB - S_dB.min()) / (S_dB.max() - S_dB.min())
        S_norm = np.expand_dims(S_norm, axis=-1)[..., :1]  # ensure single channel
        spectrograms.append(S_norm)
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
            S_dB = np.pad(S_dB, ((0,0), (0, pad_width)), mode='constant')
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
    X = []
    Y = []
    counter = 0
    for track_id in features_df.index[:num_tracks]:
        audio_path = get_audio_path(track_id, audio_dir)
        if not os.path.exists(audio_path):
            print(f"Audio file not found: {audio_path}")
            continue
        spectrograms = song_to_spectrograms(audio_path, segment_duration, sr,
                                            n_fft, hop_length, n_mels, fixed_frames)
        if spectrograms.size == 0:
            print(f"[Warning] No spectrogram data for track {track_id}")
            continue
        features = features_df.loc[track_id].values  # 6 target values
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
    model = Sequential([
        InputLayer(input_shape=input_shape),
        Conv2D(16, (3, 3), padding='same', activation='relu'),
        MaxPooling2D(pool_size=(2, 2), strides=2),
        Flatten(),
        Dense(256, activation='relu'),
        Dense(num_outputs, activation='sigmoid')  # outputs in [0,1]
    ])
    model.compile(optimizer=tf.keras.optimizers.Adam(learning_rate=1e-4),
                  loss='mse',
                  metrics=[tf.keras.metrics.RootMeanSquaredError()])
    model.summary()
    return model

# --------------------------
# Main Execution
# --------------------------


if __name__ == "__main__":

    if os.path.exists("trained_model.h5"):
        print("Model already trained. Skipping training.")
        model = tf.keras.models.load_model(
            "trained_model.h5",
            custom_objects={'mse': tf.keras.losses.MeanSquaredError()}
        )
    else:
        if not os.path.isfile(ECHONEST_CSV):
            print(f"[Error] Could not find echonest.csv at {ECHONEST_CSV}.")
            sys.exit(1)
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
        features_df = echonest[required_cols].dropna()
        if len(features_df) == 0:
            print("[Error] features_df is empty after dropping NA. Nothing to train on.")
            sys.exit(1)

        # 3. Prepare training data from up to 100 tracks.
        print("Preparing training data...")
        X, y = prepare_training_data(features_df, AUDIO_DIR, num_tracks=1000, fixed_frames=FIXED_FRAMES)
        if X.size == 0 or y.size == 0:
            print("[Error] No training data generated. Check your AUDIO_DIR path and ensure audio files are present.")
            sys.exit(1)
        input_shape = X.shape[1:]  # (128, FIXED_FRAMES, 1)
        num_outputs = y.shape[1]  # Should be 6
        print(f"Input shape: {input_shape}, Number of output features: {num_outputs}")
        model = build_tf_model(input_shape, num_outputs)

        history = model.fit(X, y, epochs=10000, batch_size=16, verbose=2)

        # 6. Save the trained model.
        model.save("trained_model.h5")
        print("Model saved as 'trained_model.h5'.")

    # 7. Predict Echonest features for a new song.
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
