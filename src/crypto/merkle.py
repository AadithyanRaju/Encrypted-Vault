import hashlib
from typing import List


def _sha256(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()


def compute_merkle_root(leaves: List[bytes]) -> bytes:
    """Compute a SHA-256 Merkle root from a list of leaf data blobs.

    Each leaf is first hashed individually; pairs are then combined up the
    tree.  If the number of nodes at any level is odd, the last node is
    duplicated (standard binary Merkle tree behaviour).  Returns a 32-byte
    root digest, or 32 zero bytes for an empty list.
    """
    if not leaves:
        return b"\x00" * 32

    layer = [_sha256(leaf) for leaf in leaves]

    while len(layer) > 1:
        next_layer: List[bytes] = []
        for i in range(0, len(layer), 2):
            left = layer[i]
            right = layer[i + 1] if i + 1 < len(layer) else left
            next_layer.append(_sha256(left + right))
        layer = next_layer

    return layer[0]
