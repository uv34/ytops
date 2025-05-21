import base64
import hashlib
import os
import secrets

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


class CryptoManager:
    # —————————————————————————————
    # 1) Generate or load one DH parameter set (2048-bit)
    # —————————————————————————————
    _P_HEX = """
            FFFFFFFF FFFFFFFF C90FDAA2 2168C234 C4C6628B 80DC1CD1
            29024E08 8A67CC74 020BBEA6 3B139B22 514A0879 8E3404DD
            EF9519B3 CD3A431B 302B0A6D F25F1437 4FE1356D 6D51C245
            E485B576 625E7EC6 F44C42E9 A637ED6B 0BFF5CB6 F406B7ED
            EE386BFB 5A899FA5 AE9F2411 7C4B1FE6 49286651 ECE65381
            FFFFFFFF FFFFFFFF
        """.replace("\n", "").replace(" ", "")
    P = int(_P_HEX, 16)
    G = 2

    def __init__(self, needs_diffie=True):
        # private key: random integer in [2, P−2]
        self._priv = secrets.randbelow(self.P - 3) + 2
        # public key: g^priv mod p
        self.public_key = pow(self.G, self._priv, self.P)

    def shared_secret(self, peer_pub: int) -> int:
        """
        Compute g^(priv * peer_priv) mod p.
        """
        if not 1 < peer_pub < self.P - 1:
            raise ValueError("Invalid peer public key")
        return pow(peer_pub, self._priv, self.P)

    @staticmethod
    def hash_secret(secret: int) -> bytes:
        """
        Hash the integer shared secret with SHA-256 to get a 32-byte key.
        """
        # Convert to big-endian bytes
        length = (secret.bit_length() + 7) // 8
        secret_bytes = secret.to_bytes(length, 'big')
        # SHA-256 digest
        return hashlib.sha256(secret_bytes).digest()

    @staticmethod
    def encrypt(key: bytes, plaintext: bytes) -> bytes:
        """
        AES-CTR encrypt. Returns base64(iv ∥ ciphertext).
        """
        iv = os.urandom(16)  # 128-bit nonce
        cipher = Cipher(algorithms.AES(key), modes.CTR(iv))
        encryptor = cipher.encryptor()
        ct = encryptor.update(plaintext) + encryptor.finalize()
        return base64.b64encode(iv + ct)

    @staticmethod
    def decrypt(key: bytes, token: bytes) -> bytes:
        """
        AES-CTR decrypt. Accepts base64(iv ∥ ciphertext).
        """
        data = base64.b64decode(token)
        iv, ct = data[:16], data[16:]
        cipher = Cipher(algorithms.AES(key), modes.CTR(iv))
        decryptor = cipher.decryptor()
        return decryptor.update(ct) + decryptor.finalize()
