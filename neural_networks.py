import numpy as np
import librosa
import matplotlib
matplotlib.use('TkAgg')
import matplotlib.pyplot as plt
import librosa.display
import pandas as pd
import os
import sys

# --------------------------
# Path Variables
# --------------------------
AUDIO_DIR = r'C:\Users\uv\Downloads\fma_small\fma_small'  # Directory with audio files
ECHONEST_CSV = r'C:\Users\uv\Downloads\fma_metadata\fma_metadata\echonest.csv'  # Echonest CSV with 3-level header
NEW_SONG_PATH = r'songs/1.ogg'  # Test song path
FIXED_FRAMES = 130  # Fixed time frames for each spectrogram

# --------------------------
# Neural Network Base Classes
# --------------------------
class Layer:
    def forward(self, input):
        raise NotImplementedError
    def backward(self, output_gradient, learning_rate):
        raise NotImplementedError

class Dense(Layer):
    def __init__(self, input_size, output_size):
        self.weights = np.random.randn(input_size, output_size) * np.sqrt(2. / input_size)
        self.bias = np.zeros((1, output_size))
    def forward(self, input):
        self.input = input
        self.output = np.dot(input, self.weights) + self.bias
        return self.output
    def backward(self, output_gradient, learning_rate):
        weights_gradient = np.dot(self.input.T, output_gradient)
        self.weights -= learning_rate * weights_gradient
        self.bias -= learning_rate * np.sum(output_gradient, axis=0, keepdims=True)
        return np.dot(output_gradient, self.weights.T)

class Activation(Layer):
    def __init__(self, activation, activation_prime):
        self.activation = activation
        self.activation_prime = activation_prime
    def forward(self, input):
        self.input = input
        self.output = self.activation(input)
        return self.output
    def backward(self, output_gradient, learning_rate):
        return self.activation_prime(self.input) * output_gradient

def relu(x):
    return np.maximum(0, x)
def relu_prime(x):
    return (x > 0).astype(float)
def sigmoid(x):
    return 1 / (1 + np.exp(-x))
def sigmoid_prime(x):
    s = sigmoid(x)
    return s * (1 - s)

# --------------------------
# Convolutional and Pooling Layers
# --------------------------
class Conv2D(Layer):
    def __init__(self, num_filters, filter_size, input_channels, stride=1, padding=0):
        self.num_filters = num_filters
        self.filter_size = filter_size
        self.stride = stride
        self.padding = padding
        self.input_channels = input_channels
        scale = np.sqrt(2. / (input_channels * filter_size * filter_size))
        self.filters = np.random.randn(num_filters, input_channels, filter_size, filter_size) * scale

    def forward(self, input):
        # input shape: (batch, height, width, channels)
        self.input = input
        batch_size, in_h, in_w, in_c = input.shape
        pad = self.padding
        if pad > 0:
            input_padded = np.pad(input, ((0,0), (pad, pad), (pad, pad), (0,0)), mode='constant')
        else:
            input_padded = input
        out_h = int((in_h - self.filter_size + 2 * pad) / self.stride) + 1
        out_w = int((in_w - self.filter_size + 2 * pad) / self.stride) + 1
        output = np.zeros((batch_size, out_h, out_w, self.num_filters))
        for b in range(batch_size):
            for f in range(self.num_filters):
                for i in range(out_h):
                    for j in range(out_w):
                        h_start = i * self.stride
                        h_end = h_start + self.filter_size
                        w_start = j * self.stride
                        w_end = w_start + self.filter_size
                        region = input_padded[b, h_start:h_end, w_start:w_end, :]
                        output[b, i, j, f] = np.sum(region * self.filters[f])
        self.output = output
        return output

    def backward(self, output_gradient, learning_rate):
        batch_size, out_h, out_w, num_filters = output_gradient.shape
        pad = self.padding
        d_filters = np.zeros_like(self.filters)
        d_input = np.zeros_like(self.input)
        if pad > 0:
            input_padded = np.pad(self.input, ((0,0), (pad, pad), (pad, pad), (0,0)), mode='constant')
            d_input_padded = np.pad(d_input, ((0,0), (pad, pad), (pad, pad), (0,0)), mode='constant')
        else:
            input_padded = self.input
            d_input_padded = d_input
        for b in range(batch_size):
            for f in range(num_filters):
                for i in range(out_h):
                    for j in range(out_w):
                        h_start = i * self.stride
                        h_end = h_start + self.filter_size
                        w_start = j * self.stride
                        w_end = w_start + self.filter_size
                        region = input_padded[b, h_start:h_end, w_start:w_end, :]
                        # region originally shape: (filter_size, filter_size, channels)
                        # Transpose to (channels, filter_size, filter_size) to match filter shape.
                        region = np.transpose(region, (2, 0, 1))
                        d_filters[f] += output_gradient[b, i, j, f] * region
                        # For d_input update, we need to convert the filter to shape (filter_size, filter_size, channels)
                        d_input_padded[b, h_start:h_end, w_start:w_end, :] += output_gradient[b, i, j, f] * self.filters[f].transpose(1,2,0)
        if pad > 0:
            d_input = d_input_padded[:, pad:-pad, pad:-pad, :]
        else:
            d_input = d_input_padded
        self.filters -= learning_rate * d_filters
        return d_input

class MaxPool2D(Layer):
    def __init__(self, pool_size, stride):
        self.pool_size = pool_size
        self.stride = stride
    def forward(self, input):
        self.input = input
        batch_size, h, w, c = input.shape
        pool_size = self.pool_size
        stride = self.stride
        out_h = int((h - pool_size) / stride) + 1
        out_w = int((w - pool_size) / stride) + 1
        output = np.zeros((batch_size, out_h, out_w, c))
        self.max_indices = np.zeros((batch_size, out_h, out_w, c, 2), dtype=int)
        for b in range(batch_size):
            for ch in range(c):
                for i in range(out_h):
                    for j in range(out_w):
                        h_start = i * stride
                        w_start = j * stride
                        region = input[b, h_start:h_start+pool_size, w_start:w_start+pool_size, ch]
                        output[b, i, j, ch] = np.max(region)
                        idx = np.unravel_index(np.argmax(region), region.shape)
                        self.max_indices[b, i, j, ch] = idx
        self.output = output
        return output
    def backward(self, output_gradient, learning_rate):
        batch_size, out_h, out_w, c = output_gradient.shape
        d_input = np.zeros_like(self.input)
        pool_size = self.pool_size
        stride = self.stride
        for b in range(batch_size):
            for ch in range(c):
                for i in range(out_h):
                    for j in range(out_w):
                        h_start = i * stride
                        w_start = j * stride
                        idx = self.max_indices[b, i, j, ch]
                        d_input[b, h_start+idx[0], w_start+idx[1], ch] += output_gradient[b, i, j, ch]
        return d_input

class Flatten(Layer):
    def forward(self, input):
        self.input_shape = input.shape
        return input.reshape(input.shape[0], -1)
    def backward(self, output_gradient, learning_rate):
        return output_gradient.reshape(self.input_shape)

# --------------------------
# Neural Network Class (for CNN)
# --------------------------
class NeuralNetwork:
    def __init__(self, loss_type="mse"):
        self.layers = []
        self.loss_type = loss_type
    def add(self, layer):
        self.layers.append(layer)
    def predict(self, X):
        output = X
        for layer in self.layers:
            output = layer.forward(output)
        return output
    def compute_loss(self, y_true, y_pred):
        if self.loss_type == "mse":
            return np.mean((y_true - y_pred) ** 2)
        else:
            return np.mean((y_true - y_pred) ** 2)
    def compute_loss_gradient(self, y_true, y_pred):
        if self.loss_type == "mse":
            return 2 * (y_pred - y_true) / y_true.size
        else:
            return 2 * (y_pred - y_true) / y_true.size
    def train(self, X, y, epochs, learning_rate, batch_size=32):
        n_samples = X.shape[0]
        for epoch in range(epochs):
            indices = np.arange(n_samples)
            np.random.shuffle(indices)
            X_shuffled = X[indices]
            y_shuffled = y[indices]
            for start in range(0, n_samples, batch_size):
                end = start + batch_size
                batch_X = X_shuffled[start:end]
                batch_y = y_shuffled[start:end]
                y_pred = self.predict(batch_X)
                loss = self.compute_loss(batch_y, y_pred)
                grad = self.compute_loss_gradient(batch_y, y_pred)
                for layer in reversed(self.layers):
                    grad = layer.backward(grad, learning_rate)
            if epoch % 10 == 0:
                rmse_percentage = np.sqrt(loss)*100
                print(f"Epoch {epoch}: RMSE = {rmse_percentage:.2f}%")

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
        # Force single channel:
        S_norm = np.expand_dims(S_norm, axis=-1)[..., :1]
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

def train_network(nn, X, y, epochs=1000, learning_rate=0.001, batch_size=16):
    nn.train(X, y, epochs=epochs, learning_rate=learning_rate, batch_size=batch_size)

def predict_song(nn, file_path, segment_duration=15, sr=22050,
                 n_fft=2048, hop_length=512, n_mels=128, fixed_frames=FIXED_FRAMES):
    spectrograms = song_to_spectrograms(file_path, segment_duration, sr,
                                        n_fft, hop_length, n_mels, fixed_frames)
    if spectrograms.size == 0:
        print("[Warning] Could not compute spectrograms for the song.")
        return None
    predictions = []
    for spec in spectrograms:
        spec = spec.reshape(1, spec.shape[0], spec.shape[1], spec.shape[2])
        pred = nn.predict(spec)
        predictions.append(pred[0])
    predictions = np.array(predictions)
    avg_prediction = np.mean(predictions, axis=0)
    return avg_prediction

# --------------------------
# Main Execution
# --------------------------
if __name__ == "__main__":
    # 1. Read the multi-level Echonest CSV
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

    # 2. Define required multi-index columns (6 features, excluding tempo and valence)
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
    X, y = prepare_training_data(features_df, AUDIO_DIR, num_tracks=100, fixed_frames=FIXED_FRAMES)
    if X.size == 0 or y.size == 0:
        print("[Error] No training data generated. Check your AUDIO_DIR path and ensure audio files are present.")
        sys.exit(1)
    input_shape = X.shape[1:]  # (128, FIXED_FRAMES, 1)
    num_outputs = y.shape[1]   # Should be 6
    print(f"Input shape: {input_shape}, Number of output features: {num_outputs}")

    # 4. Build the convolutional neural network.
    nn = NeuralNetwork(loss_type="mse")
    nn.add(Conv2D(num_filters=16, filter_size=3, input_channels=1, stride=1, padding=1))
    nn.add(Activation(relu, relu_prime))
    nn.add(MaxPool2D(pool_size=2, stride=2))
    nn.add(Flatten())
    flattened_dim = 66560  # As calculated: (64, 65, 16) flattened
    nn.add(Dense(input_size=flattened_dim, output_size=256))
    nn.add(Activation(relu, relu_prime))
    nn.add(Dense(input_size=256, output_size=num_outputs))
    nn.add(Activation(sigmoid, sigmoid_prime))  # outputs in [0,1]

    # 5. Train the network.
    print("Training the neural network...")
    train_network(nn, X, y, epochs=1000, learning_rate=0.0001, batch_size=16)

    # 6. Predict Echonest features for a new song.
    print(f"\nPredicting Echonest features for {NEW_SONG_PATH}...")
    prediction = predict_song(nn, NEW_SONG_PATH, fixed_frames=FIXED_FRAMES)
    if prediction is not None:
        feature_names = [
            "acousticness", "danceability", "energy",
            "instrumentalness", "liveness", "speechiness"
        ]
        print("Predicted Echonest features:")
        for name, value in zip(feature_names, prediction):
            print(f"  {name}: {value:.4f}")
    else:
        print("[Warning] Could not compute a prediction for the new song.")

    # 7. Optional: Visualize a spectrogram from a sample track.
    sample_track = features_df.index[0]
    sample_file = get_audio_path(sample_track, AUDIO_DIR)
    if os.path.isfile(sample_file):
        specs = song_to_spectrograms(sample_file, fixed_frames=FIXED_FRAMES)
        if specs.size > 0:
            plt.figure(figsize=(10, 4))
            S_first = specs[0].reshape(128, FIXED_FRAMES)
            librosa.display.specshow(S_first, sr=22050, hop_length=512,
                                     x_axis='time', y_axis='mel')
            plt.title('Mel-Spectrogram of First 15-Second Segment')
            plt.colorbar(format='%+2.0f dB')
            plt.tight_layout()
            plt.show()
        else:
            print(f"[Warning] No spectrogram segments for {sample_file}")
    else:
        print(f"[Warning] Sample file not found: {sample_file}")
