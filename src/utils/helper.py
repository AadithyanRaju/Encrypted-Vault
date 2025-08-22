
from pathlib import Path
from typing import Dict

def repo_paths(repo: Path) -> Dict[str, Path]:
    return {
        "vault": repo / "vault.enc",
        "blobs": repo / "blobs",
    }


def rel_time_iso(ts: float | None) -> str:
    import datetime as _dt
    if ts is None:
        return _dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
    return _dt.datetime.utcfromtimestamp(ts).replace(microsecond=0).isoformat() + "Z"

