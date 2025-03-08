from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
import os


# Generate a random AES key (256-bit)
def generate_key():
    return os.urandom(32)


# Generate a random nonce (16 bytes for AES CTR mode)
def generate_nonce():
    return os.urandom(16)


# sender encrypts the file with her key
def sender_encrypt(input_file, output_file, key, nonce):
    cipher = Cipher(algorithms.AES(key), modes.CTR(nonce))
    encryptor = cipher.encryptor()

    with open(input_file, 'rb') as f:
        plaintext = f.read()

    ciphertext = encryptor.update(plaintext) + encryptor.finalize()

    with open(output_file, 'wb') as f:
        f.write(nonce + ciphertext)


# receiver encrypts the already encrypted file with his key
def receiver_encrypt(input_file, output_file, key, nonce):
    cipher = Cipher(algorithms.AES(key), modes.CTR(nonce))
    encryptor = cipher.encryptor()

    with open(input_file, 'rb') as f:
        data = f.read()

    nonce_orig = data[:16]  # Extract sender's nonce
    ciphertext = data[16:]  # Extract sender's ciphertext

    new_ciphertext = encryptor.update(ciphertext) + encryptor.finalize()

    with open(output_file, 'wb') as f:
        f.write(nonce_orig + nonce + new_ciphertext)  # Store both nonces


# sender decrypts her encryption
def sender_decrypt(input_file, output_file, key):
    with open(input_file, 'rb') as f:
        nonce1 = f.read(16)
        nonce2 = f.read(16)
        ciphertext = f.read()

    cipher = Cipher(algorithms.AES(key), modes.CTR(nonce1))
    decryptor = cipher.decryptor()
    decrypted = decryptor.update(ciphertext) + decryptor.finalize()

    with open(output_file, 'wb') as f:
        f.write(nonce2 + decrypted)


# receiver decrypts his encryption to get the original message
def receiver_decrypt(input_file, output_file, key):
    with open(input_file, 'rb') as f:
        nonce = f.read(16)
        ciphertext = f.read()

    cipher = Cipher(algorithms.AES(key), modes.CTR(nonce))
    decryptor = cipher.decryptor()
    plaintext = decryptor.update(ciphertext) + decryptor.finalize()

    with open(output_file, 'wb') as f:
        f.write(plaintext)


# Example usage
if __name__ == "__main__":
    sender_key = generate_key()
    receiver_key = generate_key()
    sender_nonce = generate_nonce()
    receiver_nonce = generate_nonce()

    sender_encrypt("input.txt", "sender_encrypted.bin", sender_key, sender_nonce)
    receiver_encrypt("sender_encrypted.bin", "receiver_encrypted.bin", receiver_key, receiver_nonce)
    sender_decrypt("receiver_encrypted.bin", "sender_decrypted.bin", sender_key)
    receiver_decrypt("sender_decrypted.bin", "decrypted.txt", receiver_key)

    print("Three-pass encryption and decryption completed successfully.")