from argon2.low_level import hash_secret_raw, Type as Argon2Type
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes

def sha3_512_bytes(data: bytes) -> bytes:
    digest = hashes.Hash(hashes.SHA3_512(), backend=default_backend())
    digest.update(data)
    return digest.finalize()


def derive_kmaster(passphrase: str, salt: bytes, t_cost: int, m_cost_kib: int, parallelism: int) -> bytes:
    """Kmaster = Argon2id(SHA3-512(passphrase)) -> 32 bytes"""
    prehash = sha3_512_bytes(passphrase.encode("utf-8"))
    kmaster = hash_secret_raw(
        secret=prehash,
        salt=salt,
        time_cost=t_cost,
        memory_cost=m_cost_kib,
        parallelism=parallelism,
        hash_len=32,
        type=Argon2Type.ID,
    )
    return kmaster