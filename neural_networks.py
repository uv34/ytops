import numpy as np  # Used for numerical computations and array operations
import librosa  # Used for audio processing, e.g., loading and creating spectrograms
import librosa.display  # Used for visualizing spectrograms (optional)
import pandas as pd  # Used for handling CSV data with multi-level headers
import os  # Used for file system operations, e.g., checking paths
import sys  # Used for system operations, e.g., exiting on errors

# --------------------------
# Path Variables
# --------------------------
AUDIO_DIR = r'C:\Users\uv\Downloads\fma_small\fma_small'  # Directory containing audio files (e.g., MP3s)
ECHONEST_CSV = r'C:\Users\uv\Downloads\fma_metadata\fma_metadata\echonest.csv'  # CSV with audio features (3-level header)
NEW_SONG_PATH = r'songs/1.ogg'  # Path to a test song for prediction
FIXED_FRAMES = 130  # Fixed number of time frames for each spectrogram to ensure consistent input size


# --------------------------
# Neural Network Base Classes
# --------------------------
class Layer:
    """
    Abstract base class for neural network layers.

    Defines the interface for forward and backward passes.
    """

    def forward(self, input):
        raise NotImplementedError  # Must be implemented by subclasses

    def backward(self, output_gradient, learning_rate):
        raise NotImplementedError  # Must be implemented by subclasses


class Dense(Layer):
    """
    Fully connected (dense) layer.

    Applies a linear transformation followed by an optional activation.
    """

    def __init__(self, input_size, output_size):
        """
        Initialize weights and biases.

        :param input_size: Number of input features.
        :param output_size: Number of output features.
        """
        # Initialize weights using He initialization for better convergence
        self.weights = np.random.randn(input_size, output_size) * np.sqrt(2. / input_size)
        self.bias = np.zeros((1, output_size))  # Initialize biases to zero

    def forward(self, input):
        """
        Compute the forward pass: input @ weights + bias.

        :param input: Input data (batch_size, input_size).
        :return: Output of the layer (batch_size, output_size).
        """
        self.input = input
        self.output = np.dot(input, self.weights) + self.bias
        return self.output

    def backward(self, output_gradient, learning_rate):
        """
        Compute gradients and update weights and biases.

        :param output_gradient: Gradient of the loss w.r.t. the output (batch_size, output_size).
        :param learning_rate: Step size for weight updates.
        :return: Gradient of the loss w.r.t. the input (batch_size, input_size).
        """
        # Compute gradients for weights and biases
        weights_gradient = np.dot(self.input.T, output_gradient)
        self.weights -= learning_rate * weights_gradient
        self.bias -= learning_rate * np.sum(output_gradient, axis=0, keepdims=True)
        # Compute gradient w.r.t. input for backpropagation
        return np.dot(output_gradient, self.weights.T)


class Activation(Layer):
    """
    Activation layer applying a specified activation function.

    Supports forward and backward passes for the activation.
    """

    def __init__(self, activation, activation_prime):
        """
        Initialize with activation function and its derivative.

        :param activation: Activation function (e.g., ReLU, sigmoid).
        :param activation_prime: Derivative of the activation function.
        """
        self.activation = activation
        self.activation_prime = activation_prime

    def forward(self, input):
        """
        Apply the activation function to the input.

        :param input: Input data (any shape).
        :return: Activated output.
        """
        self.input = input
        self.output = self.activation(input)
        return self.output

    def backward(self, output_gradient, learning_rate):
        """
        Compute the gradient of the loss w.r.t. the input using the chain rule.

        :param output_gradient: Gradient of the loss w.r.t. the output.
        :param learning_rate: Not used in this layer.
        :return: Gradient of the loss w.r.t. the input.
        """
        return self.activation_prime(self.input) * output_gradient


# Define ReLU activation and its derivative
def relu(x):
    """ReLU activation: max(0, x)."""
    return np.maximum(0, x)


def relu_prime(x):
    """Derivative of ReLU: 1 if x > 0, else 0."""
    return (x > 0).astype(float)


# Define sigmoid activation and its derivative
def sigmoid(x):
    """Sigmoid activation: 1 / (1 + exp(-x))."""
    return 1 / (1 + np.exp(-x))


def sigmoid_prime(x):
    """Derivative of sigmoid: sigmoid(x) * (1 - sigmoid(x))."""
    s = sigmoid(x)
    return s * (1 - s)


# --------------------------
# Convolutional and Pooling Layers
# --------------------------
class Conv2D(Layer):
    """
    2D Convolutional layer for processing image-like data (e.g., spectrograms).

    Applies multiple filters to extract features from input images.
    """

    def __init__(self, num_filters, filter_size, input_channels, stride=1, padding=0):
        """
        Initialize convolutional filters.

        :param num_filters: Number of filters (output channels).
        :param filter_size: Size of each filter (e.g., 3 for 3x3).
        :param input_channels: Number of input channels (e.g., 1 for grayscale).
        :param stride: Step size for sliding the filters (default: 1).
        :param padding: Padding size around the input (default: 0).
        """
        self.num_filters = num_filters
        self.filter_size = filter_size
        self.stride = stride
        self.padding = padding
        self.input_channels = input_channels
        # Initialize filters with He initialization for better convergence
        scale = np.sqrt(2. / (input_channels * filter_size * filter_size))
        self.filters = np.random.randn(num_filters, input_channels, filter_size, filter_size) * scale

    def forward(self, input):
        """
        Apply convolutional filters to the input.

        :param input: Input data (batch_size, height, width, channels).
        :return: Convolved output (batch_size, out_height, out_width, num_filters).
        """
        self.input = input
        batch_size, in_h, in_w, in_c = input.shape
        pad = self.padding
        # Apply padding if specified
        if pad > 0:
            input_padded = np.pad(input, ((0, 0), (pad, pad), (pad, pad), (0, 0)), mode='constant')
        else:
            input_padded = input
        # Calculate output dimensions
        out_h = int((in_h - self.filter_size + 2 * pad) / self.stride) + 1
        out_w = int((in_w - self.filter_size + 2 * pad) / self.stride) + 1
        output = np.zeros((batch_size, out_h, out_w, self.num_filters))
        # Perform convolution for each filter and batch sample
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
        """
        Compute gradients for filters and input, and update filters.

        :param output_gradient: Gradient of the loss w.r.t. the output (batch_size, out_h, out_w, num_filters).
        :param learning_rate: Step size for weight updates.
        :return: Gradient of the loss w.r.t. the input (batch_size, in_h, in_w, in_c).
        """
        batch_size, out_h, out_w, num_filters = output_gradient.shape
        pad = self.padding
        d_filters = np.zeros_like(self.filters)
        d_input = np.zeros_like(self.input)
        # Handle padding for input gradient
        if pad > 0:
            input_padded = np.pad(self.input, ((0, 0), (pad, pad), (pad, pad), (0, 0)), mode='constant')
            d_input_padded = np.pad(d_input, ((0, 0), (pad, pad), (pad, pad), (0, 0)), mode='constant')
        else:
            input_padded = self.input
            d_input_padded = d_input
        # Compute gradients for filters and input
        for b in range(batch_size):
            for f in range(num_filters):
                for i in range(out_h):
                    for j in range(out_w):
                        h_start = i * self.stride
                        h_end = h_start + self.filter_size
                        w_start = j * self.stride
                        w_end = w_start + self.filter_size
                        region = input_padded[b, h_start:h_end, w_start:w_end, :]
                        # Update filter gradient (transpose region to match filter shape)
                        d_filters[f] += output_gradient[b, i, j, f] * region.transpose(2, 0, 1)
                        # Update input gradient (transpose filter to match input shape)
                        d_input_padded[b, h_start:h_end, w_start:w_end, :] += output_gradient[b, i, j, f] * \
                                                                              self.filters[f].transpose(1, 2, 0)
        # Remove padding from input gradient if applied
        if pad > 0:
            d_input = d_input_padded[:, pad:-pad, pad:-pad, :]
        else:
            d_input = d_input_padded
        # Update filters using gradient descent
        self.filters -= learning_rate * d_filters
        return d_input


class MaxPool2D(Layer):
    """
    2D Max Pooling layer for downsampling feature maps.

    Reduces spatial dimensions by taking the maximum value in each pooling region.
    """

    def __init__(self, pool_size, stride):
        """
        Initialize pooling parameters.

        :param pool_size: Size of the pooling window (e.g., 2 for 2x2).
        :param stride: Step size for sliding the pooling window.
        """
        self.pool_size = pool_size
        self.stride = stride

    def forward(self, input):
        """
        Apply max pooling to the input.

        :param input: Input data (batch_size, height, width, channels).
        :return: Pooled output (batch_size, out_height, out_width, channels).
        """
        self.input = input
        batch_size, h, w, c = input.shape
        pool_size = self.pool_size
        stride = self.stride
        # Calculate output dimensions
        out_h = int((h - pool_size) / stride) + 1
        out_w = int((w - pool_size) / stride) + 1
        output = np.zeros((batch_size, out_h, out_w, c))
        self.max_indices = np.zeros((batch_size, out_h, out_w, c, 2), dtype=int)
        # Perform max pooling for each channel and batch sample
        for b in range(batch_size):
            for ch in range(c):
                for i in range(out_h):
                    for j in range(out_w):
                        h_start = i * stride
                        w_start = j * stride
                        region = input[b, h_start:h_start + pool_size, w_start:w_start + pool_size, ch]
                        output[b, i, j, ch] = np.max(region)
                        # Store indices of max values for backpropagation
                        idx = np.unravel_index(np.argmax(region), region.shape)
                        self.max_indices[b, i, j, ch] = idx
        self.output = output
        return output

    def backward(self, output_gradient, learning_rate):
        """
        Compute the gradient of the loss w.r.t. the input for max pooling.

        :param output_gradient: Gradient of the loss w.r.t. the output (batch_size, out_h, out_w, c).
        :param learning_rate: Not used in this layer.
        :return: Gradient of the loss w.r.t. the input (batch_size, in_h, in_w, c).
        """
        batch_size, out_h, out_w, c = output_gradient.shape
        d_input = np.zeros_like(self.input)
        pool_size = self.pool_size
        stride = self.stride
        # Distribute gradients to the positions of max values
        for b in range(batch_size):
            for ch in range(c):
                for i in range(out_h):
                    for j in range(out_w):
                        h_start = i * stride
                        w_start = j * stride
                        idx = self.max_indices[b, i, j, ch]
                        d_input[b, h_start + idx[0], w_start + idx[1], ch] += output_gradient[b, i, j, ch]
        return d_input


class Flatten(Layer):
    """
    Flatten layer to convert 2D feature maps to 1D vectors.

    Used before fully connected layers.
    """

    def forward(self, input):
        """
        Flatten the input to (batch_size, flattened_size).

        :param input: Input data (batch_size, height, width, channels).
        :return: Flattened output (batch_size, height*width*channels).
        """
        self.input_shape = input.shape
        return input.reshape(input.shape[0], -1)

    def backward(self, output_gradient, learning_rate):
        """
        Reshape the gradient back to the original input shape.

        :param output_gradient: Gradient of the loss w.r.t. the flattened output.
        :param learning_rate: Not used in this layer.
        :return: Gradient of the loss w.r.t. the input.
        """
        return output_gradient.reshape(self.input_shape)


# --------------------------
# Neural Network Class (for CNN)
# --------------------------
class NeuralNetwork:
    """
    A simple neural network class supporting sequential layers.

    Manages forward and backward passes through the network.
    """

    def __init__(self, loss_type="mse"):
        """
        Initialize the network with a specified loss type.

        :param loss_type: Type of loss function (default: "mse").
        """
        self.layers = []  # List to hold network layers
        self.loss_type = loss_type

    def add(self, layer):
        """
        Add a layer to the network.

        :param layer: An instance of a Layer subclass.
        """
        self.layers.append(layer)

    def predict(self, X):
        """
        Perform a forward pass through the network.

        :param X: Input data (batch_size, ...).
        :return: Output of the network.
        """
        output = X
        for layer in self.layers:
            output = layer.forward(output)
        return output

    def compute_loss(self, y_true, y_pred):
        """
        Compute the loss between true and predicted values.

        :param y_true: True labels (batch_size, num_outputs).
        :param y_pred: Predicted values (batch_size, num_outputs).
        :return: Mean squared error loss.
        """
        if self.loss_type == "mse":
            return np.mean((y_true - y_pred) ** 2)
        else:
            return np.mean((y_true - y_pred) ** 2)  # Default to MSE

    def compute_loss_gradient(self, y_true, y_pred):
        """
        Compute the gradient of the loss w.r.t. the predicted values.

        :param y_true: True labels.
        :param y_pred: Predicted values.
        :return: Gradient of the loss.
        """
        if self.loss_type == "mse":
            return 2 * (y_pred - y_true) / y_true.size
        else:
            return 2 * (y_pred - y_true) / y_true.size  # Default to MSE gradient

    def train(self, X, y, epochs, learning_rate, batch_size=32):
        """
        Train the network using mini-batch gradient descent.

        :param X: Training data (n_samples, ...).
        :param y: Training labels (n_samples, num_outputs).
        :param epochs: Number of training epochs.
        :param learning_rate: Step size for weight updates.
        :param batch_size: Size of each mini-batch (default: 32).
        """
        n_samples = X.shape[0]
        for epoch in range(epochs):
            # Shuffle data for each epoch
            indices = np.arange(n_samples)
            np.random.shuffle(indices)
            X_shuffled = X[indices]
            y_shuffled = y[indices]
            # Process mini-batches
            for start in range(0, n_samples, batch_size):
                end = start + batch_size
                batch_X = X_shuffled[start:end]
                batch_y = y_shuffled[start:end]
                # Forward pass
                y_pred = self.predict(batch_X)
                # Compute loss (for monitoring)
                loss = self.compute_loss(batch_y, y_pred)
                # Compute gradient of loss w.r.t. output
                grad = self.compute_loss_gradient(batch_y, y_pred)
                # Backward pass: propagate gradient through layers
                for layer in reversed(self.layers):
                    grad = layer.backward(grad, learning_rate)
            # Print RMSE every 10 epochs
            if epoch % 10 == 0:
                rmse_percentage = np.sqrt(loss) * 100
                print(f"Epoch {epoch}: RMSE = {rmse_percentage:.2f}%")


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
    # Process up to num_tracks
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


def train_network(nn, X, y, epochs=1000, learning_rate=0.001, batch_size=16):
    """
    Train the neural network using the provided data.

    :param nn: NeuralNetwork instance.
    :param X: Training data (spectrograms).
    :param y: Training labels (features).
    :param epochs: Number of training epochs (default: 1000).
    :param learning_rate: Learning rate for weight updates (default: 0.001).
    :param batch_size: Size of mini-batches (default: 16).
    """
    nn.train(X, y, epochs=epochs, learning_rate=learning_rate, batch_size=batch_size)


def predict_song(nn, file_path, segment_duration=15, sr=22050,
                 n_fft=2048, hop_length=512, n_mels=128, fixed_frames=FIXED_FRAMES):
    """
    Predict audio features for a new song using the trained network.

    Computes the average prediction over all segments of the song.

    :param nn: Trained NeuralNetwork instance.
    :param file_path: Path to the audio file.
    :param segment_duration: Duration of each segment (default: 15 seconds).
    :param sr: Sampling rate (default: 22050 Hz).
    :param n_fft: FFT window size (default: 2048).
    :param hop_length: Hop length for spectrogram (default: 512).
    :param n_mels: Number of mel bands (default: 128).
    :param fixed_frames: Fixed number of time frames for spectrograms.
    :return: Average predicted features, or None if no spectrograms.
    """
    spectrograms = song_to_spectrograms(file_path, segment_duration, sr,
                                        n_fft, hop_length, n_mels, fixed_frames)
    if spectrograms.size == 0:
        print("[Warning] Could not compute spectrograms for the song.")
        return None
    predictions = []
    for spec in spectrograms:
        spec = spec.reshape(1, spec.shape[0], spec.shape[1], spec.shape[2])  # Batch shape
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
    num_outputs = y.shape[1]  # Should be 6
    print(f"Input shape: {input_shape}, Number of output features: {num_outputs}")

    # 4. Build the convolutional neural network.
    nn = NeuralNetwork(loss_type="mse")
    nn.add(Conv2D(num_filters=16, filter_size=3, input_channels=1, stride=1, padding=1))
    nn.add(Activation(relu, relu_prime))
    nn.add(MaxPool2D(pool_size=2, stride=2))
    nn.add(Flatten())
    flattened_dim = 66560  # Precomputed flattened size: (64, 65, 16) -> 64*65*16=66560
    nn.add(Dense(input_size=flattened_dim, output_size=256))
    nn.add(Activation(relu, relu_prime))
    nn.add(Dense(input_size=256, output_size=num_outputs))
    nn.add(Activation(sigmoid, sigmoid_prime))  # Output in [0,1]

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
            import matplotlib.pyplot as plt  # Import here to avoid unnecessary dependency

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