import numpy as np
import librosa
import matplotlib
matplotlib.use('TkAgg')
import matplotlib.pyplot as plt
import librosa.display

# Base class for layers.
class Layer:
    def forward(self, input):
        raise NotImplementedError

    def backward(self, output_gradient, learning_rate):
        raise NotImplementedError

# Dense (fully-connected) layer.
class Dense(Layer):
    def __init__(self, input_size, output_size):
        # Xavier initialization for weights.
        self.weights = np.random.randn(input_size, output_size) * np.sqrt(2. / input_size)
        self.bias = np.zeros((1, output_size))

    def forward(self, input):
        self.input = input
        self.output = np.dot(input, self.weights) + self.bias
        return self.output

    def backward(self, output_gradient, learning_rate):
        # Gradient with respect to input, weights, and bias.
        weights_gradient = np.dot(self.input.T, output_gradient)
        self.weights -= learning_rate * weights_gradient
        self.bias -= learning_rate * np.sum(output_gradient, axis=0, keepdims=True)
        return np.dot(output_gradient, self.weights.T)

# Activation layer that applies a given activation function and its derivative.
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

# Activation functions and their derivatives.
def sigmoid(x):
    return 1 / (1 + np.exp(-x))

def sigmoid_prime(x):
    s = sigmoid(x)
    return s * (1 - s)

def relu(x):
    return np.maximum(0, x)

def relu_prime(x):
    return (x > 0).astype(float)

# Generic neural network class.
class NeuralNetwork:
    def __init__(self):
        self.layers = []

    def add(self, layer):
        self.layers.append(layer)

    def predict(self, input):
        # Forward propagation.
        output = input
        for layer in self.layers:
            output = layer.forward(output)
        return output

    def train(self, X, y, epochs, learning_rate):
        # Training using mean squared error loss.
        for epoch in range(epochs):
            # Forward pass.
            output = self.predict(X)
            # Compute mean squared error loss.
            loss = np.mean((y - output) ** 2)
            # Compute gradient of loss with respect to output.
            grad = 2 * (output - y) / y.size

            # Backward pass.
            for layer in reversed(self.layers):
                grad = layer.backward(grad, learning_rate)

            if epoch % 100 == 0:
                print(f"Epoch {epoch}: Loss = {loss:.6f}")


def audio_to_spectrogram(file_path, n_fft=2048, hop_length=512, duration=30, sr=22050, fixed_frames=1300):
    """
    Load an audio file (supports OGG among others), compute its spectrogram,
    and normalize/pad/truncate it to fixed dimensions.

    Args:
        file_path (str): Path to the audio file (e.g., .ogg file).
        n_fft (int): Number of FFT components.
        hop_length (int): Number of samples between successive frames.
        duration (int): Duration (in seconds) to load from the file.
        sr (int): Sampling rate.
        fixed_frames (int): Desired fixed number of time frames.

    Returns:
        S_norm (np.ndarray): Normalized spectrogram with shape (frequency_bins, fixed_frames).
    """
    # Load a segment of the audio file (OGG files included)
    y, sr = librosa.load(file_path, sr=sr, duration=duration)
    print("Loaded duration:", len(y) / sr, "seconds")

    # Compute the spectrogram using Short-Time Fourier Transform (STFT)
    S = np.abs(librosa.stft(y, n_fft=n_fft, hop_length=hop_length))

    # Convert amplitude spectrogram to decibel (dB) scale
    S_dB = librosa.amplitude_to_db(S, ref=np.max)

    # Pad or truncate the spectrogram along the time dimension
    if S_dB.shape[1] < fixed_frames:
        pad_width = fixed_frames - S_dB.shape[1]
        S_dB = np.pad(S_dB, ((0, 0), (0, pad_width)), mode='constant')
    else:
        S_dB = S_dB[:, :fixed_frames]

    # Normalize the spectrogram to the range [0, 1]
    S_norm = (S_dB - S_dB.min()) / (S_dB.max() - S_dB.min())
    return S_norm

# Example usage:
if __name__ == '__main__':
    np.random.seed(42)
    X = np.random.rand(100, 1)
    y = 2 * X + 1

    # Build the network.
    nn = NeuralNetwork()
    nn.add(Dense(input_size=1, output_size=10))
    nn.add(Activation(relu, relu_prime))
    nn.add(Dense(input_size=10, output_size=1))

    # Train the network.
    nn.train(X, y, epochs=1000, learning_rate=0.1)

    # Make a prediction.
    predictions = nn.predict(3)
    print("First 5 predictions:")
    print(predictions[:5])

    file_path = 'songs/1.ogg'
    spectrogram = audio_to_spectrogram(file_path)
    print('has specto')

    plt.figure(figsize=(10, 4))
    librosa.display.specshow(spectrogram, sr=22050, hop_length=512, x_axis='time', y_axis='log')
    plt.title('Normalized Spectrogram for OGG File')
    plt.colorbar(format='%+2.0f dB')
    plt.tight_layout()
    plt.show()
