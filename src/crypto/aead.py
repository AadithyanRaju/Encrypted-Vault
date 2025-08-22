import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from typing import Tuple

def aead_encrypt(key: bytes, plaintext: bytes, aad: bytes | None = None) -> Tuple[bytes, bytes]:
    nonce = os.urandom(12)
    aesgcm = AESGCM(key)
    ct = aesgcm.encrypt(nonce, plaintext, aad)
    return nonce, ct


def aead_decrypt(key: bytes, nonce: bytes, ct: bytes, aad: bytes | None = None) -> bytes:
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ct, aad)