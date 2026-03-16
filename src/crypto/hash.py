from argon2.low_level import hash_secret_raw, Type as Argon2Type
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes

from crypto.secure_bytes import SecureBytes, wipe_key


def sha3_512_bytes(data: bytes) -> bytes:
    digest = hashes.Hash(hashes.SHA3_512(), backend=default_backend())
    digest.update(data)
    return digest.finalize()


def derive_kmaster(passphrase: str, salt: bytes, t_cost: int, m_cost_kib: int, parallelism: int) -> SecureBytes:
    """Kmaster = Argon2id(SHA3-512(passphrase)) -> 32 bytes, returned as SecureBytes.

    The intermediate SHA-3 pre-hash is held in a mutable bytearray and
    wiped immediately after Argon2id has consumed it.
    """
    prehash = bytearray(sha3_512_bytes(passphrase.encode("utf-8")))
    try:
        raw = hash_secret_raw(
            secret=bytes(prehash),
            salt=salt,
            time_cost=t_cost,
            memory_cost=m_cost_kib,
            parallelism=parallelism,
            hash_len=32,
            type=Argon2Type.ID,
        )
        return SecureBytes(raw)
    finally:
        wipe_key(prehash)