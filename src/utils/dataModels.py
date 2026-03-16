import json
import struct

from dataclasses import dataclass
from typing import Dict, Any, List

DEFAULT_T_COST = 4
DEFAULT_M_COST_KiB = 262144  # 256 MiB (tune per device)
DEFAULT_PARALLELISM = 2

VAULT_MAGIC = b"EFS1"
VAULT_VERSION = 1
VAULT_HDR_FMT = ">4sBIII16s12s"  # magic, ver, t, m, p, salt(16), nonce(12)
VAULT_HDR_SIZE = struct.calcsize(VAULT_HDR_FMT)

# Maximum random padding (in bytes) appended to plaintext before blob encryption.
# This obfuscates the real file size on disk.
PAD_MAX = 4096


@dataclass
class KeyWrap:
    nonce_b64: str
    ct_b64: str

    def to_dict(self) -> Dict[str, str]:
        return {"nonce": self.nonce_b64, "ct": self.ct_b64}


@dataclass
class FileEntry:
    id: str
    name: str           # plaintext filename – in-memory only, never stored
    relpath: str | None # plaintext relpath – in-memory only, never stored
    blob: str
    size: int           # real (unpadded) plaintext size
    created_at: str
    modified_at: str
    mimetype: str | None
    file_key_wrap: KeyWrap
    name_enc: str       # base64(nonce || AES-GCM ct of name), encrypted with per-file key
    relpath_enc: str | None  # base64(nonce || AES-GCM ct of relpath), or None

    def to_dict(self) -> Dict[str, Any]:
        # name / relpath are in-memory convenience fields; they are not
        # persisted – the encrypted counterparts (name_enc / relpath_enc) are.
        return {
            "id": self.id,
            "blob": self.blob,
            "size": self.size,
            "created_at": self.created_at,
            "modified_at": self.modified_at,
            "mimetype": self.mimetype,
            "file_key_wrap": self.file_key_wrap.to_dict(),
            "name_enc": self.name_enc,
            "relpath_enc": self.relpath_enc,
        }


@dataclass
class InnerMetadata:
    version: int
    files: List[Dict[str, Any]]

    def to_bytes(self) -> bytes:
        # Strip in-memory plaintext name/relpath from entries that carry the
        # encrypted equivalents so they are never written to disk.
        # Always work with a shallow copy so the original in-memory dicts are
        # not modified and no plaintext fields can leak through aliasing.
        clean_files = []
        for f in self.files:
            if "name_enc" in f:
                f_clean = {k: v for k, v in f.items() if k not in ("name", "relpath")}
            else:
                f_clean = dict(f)
            clean_files.append(f_clean)
        return json.dumps({"version": self.version, "files": clean_files}, ensure_ascii=False, separators=(",", ":")).encode("utf-8")

    @staticmethod
    def from_bytes(b: bytes) -> "InnerMetadata":
        obj = json.loads(b.decode("utf-8"))
        return InnerMetadata(version=obj.get("version", 1), files=obj.get("files", []))
