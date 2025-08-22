import json
import struct

from dataclasses import dataclass, asdict
from typing import Dict, Any, List

DEFAULT_T_COST = 4
DEFAULT_M_COST_KiB = 262144  # 256 MiB (tune per device)
DEFAULT_PARALLELISM = 2

VAULT_MAGIC = b"EFS1"
VAULT_VERSION = 1
VAULT_HDR_FMT = ">4sBIII16s12s"  # magic, ver, t, m, p, salt(16), nonce(12)
VAULT_HDR_SIZE = struct.calcsize(VAULT_HDR_FMT)


@dataclass
class KeyWrap:
    nonce_b64: str
    ct_b64: str

    def to_dict(self) -> Dict[str, str]:
        return {"nonce": self.nonce_b64, "ct": self.ct_b64}


@dataclass
class FileEntry:
    id: str
    name: str
    blob: str
    size: int
    created_at: str
    modified_at: str
    mimetype: str | None
    file_key_wrap: KeyWrap

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["file_key_wrap"] = self.file_key_wrap.to_dict()
        return d


@dataclass
class InnerMetadata:
    version: int
    files: List[Dict[str, Any]]

    def to_bytes(self) -> bytes:
        return json.dumps({"version": self.version, "files": self.files}, ensure_ascii=False, separators=(",", ":")).encode("utf-8")

    @staticmethod
    def from_bytes(b: bytes) -> "InnerMetadata":
        obj = json.loads(b.decode("utf-8"))
        return InnerMetadata(version=obj.get("version", 1), files=obj.get("files", []))
