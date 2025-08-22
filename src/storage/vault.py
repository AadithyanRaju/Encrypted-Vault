import os
import struct

from utils.dataModels import VAULT_HDR_FMT, VAULT_MAGIC, VAULT_VERSION, VAULT_HDR_SIZE

from pathlib import Path
from typing import Tuple

def save_vault(path: Path, t: int, m: int, p: int, salt: bytes, nonce: bytes, ct: bytes) -> None:
    header = struct.pack(VAULT_HDR_FMT, VAULT_MAGIC, VAULT_VERSION, t, m, p, salt, nonce)
    tmp = path.with_suffix(".tmp")
    with tmp.open("wb") as f:
        f.write(header)
        f.write(ct)
    os.replace(tmp, path)


def load_vault(path: Path) -> Tuple[int, int, int, bytes, bytes, bytes]:
    data = path.read_bytes()
    if len(data) < VAULT_HDR_SIZE:
        raise ValueError("vault.enc is too small or corrupt")
    magic, ver, t, m, p, salt, nonce = struct.unpack(VAULT_HDR_FMT, data[:VAULT_HDR_SIZE])
    if magic != VAULT_MAGIC:
        raise ValueError("Invalid vault magic")
    if ver != VAULT_VERSION:
        raise ValueError("Unsupported vault version")
    ct = data[VAULT_HDR_SIZE:]
    return t, m, p, salt, nonce, ct
