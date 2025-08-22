#!/usr/bin/env python3
"""
Encrypted File System (EFS) – GitHub-friendly layout (ALL metadata encrypted)

Changes in this version:
- Replaces JSON envelope `data.enc` with a **binary vault file** `vault.enc`.
- `vault.enc` contains ONLY opaque binary data. There is **no readable JSON header** anymore.
- Minimal fixed-size binary header stores KDF params + salt + AEAD nonce; the rest is ciphertext.
- Unlocking requires the master passphrase to derive Kmaster and decrypt the inner JSON metadata.
- Per-file random AES-256 keys are wrapped under Kmaster and blobs remain separate (nonce||ct), still opaque.

Binary header (big-endian):
    magic     : 4 bytes   -> b"EFS1"
    version   : 1 byte    -> 0x01
    t_cost    : u32
    m_cost    : u32  (KiB)
    parallel  : u32
    salt      : 16 bytes
    nonce     : 12 bytes
    ciphertext: remaining bytes (AES-256-GCM over inner JSON)

Repo layout:
  repo/
    vault.enc             # opaque binary (no readable JSON)
    blobs/
      <uuid>.bin         # binary: 12-byte nonce || AES-256-GCM(ciphertext)

Commands:
  init                 Initialize vault (create vault.enc)
  add <path>           Add a plaintext file (encrypt -> blobs/<uuid>.bin; update vault)
  ls                   List files (after unlock)
  extract <id> <out>   Decrypt by id to output path
  rm <id>              Remove a file (deletes blob and metadata entry)
  rename <id> <name>   Rename a file entry (metadata only)
  rotate-master        Rotate master key (new Argon2 params/salt, rewrap all per-file keys)
  gui                  Launch minimal GUI (PyQt6) for browse/extract

Security choices:
  - AEAD: AES-256-GCM via cryptography.hazmat
  - Argon2id via argon2-cffi low-level API
  - Kmaster = Argon2id(SHA3-512(passphrase)) -> 32 bytes

Note: This is a reference implementation for clarity, not a final audited product.
"""
from __future__ import annotations

import argparse
import json
import os
import struct
import sys
import uuid
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, Any, List, Tuple

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend

from argon2.low_level import hash_secret_raw, Type as Argon2Type

# ------------------------------ Utils ------------------------------

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


# --------------------------- Data Models ---------------------------

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


# -------------------------- Vault IO ------------------------------

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


# -------------------------- Crypto Helpers ------------------------

def aead_encrypt(key: bytes, plaintext: bytes, aad: bytes | None = None) -> Tuple[bytes, bytes]:
    nonce = os.urandom(12)
    aesgcm = AESGCM(key)
    ct = aesgcm.encrypt(nonce, plaintext, aad)
    return nonce, ct


def aead_decrypt(key: bytes, nonce: bytes, ct: bytes, aad: bytes | None = None) -> bytes:
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ct, aad)


# --------------------------- Helpers ------------------------------

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


# ----------------------------- Core -------------------------------

def cmd_init(args: argparse.Namespace) -> None:
    repo = Path(args.repo)
    repo.mkdir(parents=True, exist_ok=True)
    p = repo_paths(repo)
    p["blobs"].mkdir(parents=True, exist_ok=True)

    if p["vault"].exists() and not args.force:
        print(f"[!] {p['vault']} exists. Use --force to overwrite.")
        sys.exit(1)

    salt = os.urandom(16)
    kmaster = derive_kmaster(args.passphrase, salt, args.t, args.m, args.p)

    # Empty inner metadata
    inner = InnerMetadata(version=1, files=[])
    inner_bytes = inner.to_bytes()

    # Encrypt inner under Kmaster
    nonce, ct = aead_encrypt(kmaster, inner_bytes)

    save_vault(p["vault"], args.t, args.m, args.p, salt, nonce, ct)
    print(f"[+] Initialized vault at {repo}")


def unlock(repo: Path, passphrase: str) -> tuple[InnerMetadata, bytes, Dict[str, int | bytes]]:
    p = repo_paths(repo)
    t, m, paral, salt, nonce, ct = load_vault(p["vault"])
    kmaster = derive_kmaster(passphrase, salt, t, m, paral)
    inner_bytes = aead_decrypt(kmaster, nonce, ct)
    inner = InnerMetadata.from_bytes(inner_bytes)
    return inner, kmaster, {"t": t, "m": m, "p": paral, "salt": salt}


def cmd_add(args: argparse.Namespace) -> None:
    repo = Path(args.repo)
    src = Path(args.path)
    if not src.is_file():
        print(f"[!] Not a file: {src}")
        sys.exit(1)

    inner, kmaster, kdf = unlock(repo, args.passphrase)
    p = repo_paths(repo)

    # Generate per-file key
    file_key = os.urandom(32)  # AES-256

    # Read plaintext
    plaintext = src.read_bytes()

    # Encrypt file content with file_key
    file_nonce = os.urandom(12)
    file_ct = AESGCM(file_key).encrypt(file_nonce, plaintext, None)

    # Write blob: nonce||ct
    fid = str(uuid.uuid4())
    blob_path = p["blobs"] / f"{fid}.bin"
    with blob_path.open("wb") as f:
        f.write(file_nonce + file_ct)

    # Wrap file_key with Kmaster
    wrap_nonce, wrap_ct = aead_encrypt(kmaster, file_key)
    import base64
    keywrap = KeyWrap(nonce_b64=base64.b64encode(wrap_nonce).decode(), ct_b64=base64.b64encode(wrap_ct).decode())

    entry = FileEntry(
        id=fid,
        name=src.name,
        blob=f"blobs/{fid}.bin",
        size=len(plaintext),
        created_at=rel_time_iso(os.path.getctime(src)),
        modified_at=rel_time_iso(os.path.getmtime(src)),
        mimetype=None,
        file_key_wrap=keywrap,
    )
    inner.files.append(entry.to_dict())

    # Re-encrypt inner and save vault
    inner_bytes = inner.to_bytes()
    new_nonce, new_ct = aead_encrypt(kmaster, inner_bytes)
    save_vault(p["vault"], kdf["t"], kdf["m"], kdf["p"], kdf["salt"], new_nonce, new_ct)
    print(f"[+] Encrypted and added {src.name} as id={fid}")


def cmd_ls(args: argparse.Namespace) -> None:
    repo = Path(args.repo)
    inner, _, _ = unlock(repo, args.passphrase)
    if not inner.files:
        print("(empty)")
        return
    for fobj in inner.files:
        print(f"{fobj['id']}\t{fobj['name']}\t{fobj['size']} bytes\t{fobj['blob']}")


def cmd_extract(args: argparse.Namespace) -> None:
    repo = Path(args.repo)
    fid = args.id
    out = Path(args.out)

    inner, kmaster, _ = unlock(repo, args.passphrase)

    match = next((f for f in inner.files if f["id"] == fid), None)
    if not match:
        print(f"[!] No such id: {fid}")
        sys.exit(1)

    # Unwrap per-file key
    import base64
    wrap = match["file_key_wrap"]
    file_key = aead_decrypt(kmaster, base64.b64decode(wrap["nonce"]), base64.b64decode(wrap["ct"]))

    # Read blob and decrypt
    blob_path = Path(repo) / match["blob"]
    blob = blob_path.read_bytes()
    if len(blob) < 13:
        print("[!] Corrupt blob")
        sys.exit(1)
    file_nonce, file_ct = blob[:12], blob[12:]
    plaintext = AESGCM(file_key).decrypt(file_nonce, file_ct, None)

    out.write_bytes(plaintext)
    print(f"[+] Extracted {match['name']} -> {out}")


# ------------------------- Maintenance Ops ------------------------

def cmd_rm(args: argparse.Namespace) -> None:
    repo = Path(args.repo)
    fid = args.id
    inner, _, kdf = unlock(repo, args.passphrase)
    match = next((f for f in inner.files if f["id"] == fid), None)
    if not match:
        print(f"[!] No such id: {fid}")
        sys.exit(1)
    # Delete blob file
    blob_path = Path(repo) / match["blob"]
    try:
        blob_path.unlink()
    except FileNotFoundError:
        pass
    # Remove entry
    inner.files = [f for f in inner.files if f["id"] != fid]

    # Re-encrypt inner with existing kmaster (we need kmaster; unlock returns it)
    # Re-derive kmaster for encryption
    kmaster = derive_kmaster(args.passphrase, kdf["salt"], kdf["t"], kdf["m"], kdf["p"])
    inner_bytes = InnerMetadata(version=1, files=inner.files).to_bytes()
    new_nonce, new_ct = aead_encrypt(kmaster, inner_bytes)
    save_vault(repo_paths(repo)["vault"], kdf["t"], kdf["m"], kdf["p"], kdf["salt"], new_nonce, new_ct)
    print(f"[+] Removed id={fid}")


def cmd_rename(args: argparse.Namespace) -> None:
    repo = Path(args.repo)
    fid = args.id
    new_name = args.name
    inner, _, kdf = unlock(repo, args.passphrase)
    match = next((f for f in inner.files if f["id"] == fid), None)
    if not match:
        print(f"[!] No such id: {fid}")
        sys.exit(1)
    match["name"] = new_name

    kmaster = derive_kmaster(args.passphrase, kdf["salt"], kdf["t"], kdf["m"], kdf["p"])
    inner_bytes = InnerMetadata(version=1, files=inner.files).to_bytes()
    new_nonce, new_ct = aead_encrypt(kmaster, inner_bytes)
    save_vault(repo_paths(repo)["vault"], kdf["t"], kdf["m"], kdf["p"], kdf["salt"], new_nonce, new_ct)
    print(f"[+] Renamed id={fid} -> {new_name}")


def cmd_rotate_master(args: argparse.Namespace) -> None:
    """Rotate master key by changing salt and Argon2 params; rewrap all file keys.
    Steps:
      1) Unlock with old master; obtain inner metadata and unwrap nothing yet.
      2) Generate new salt (or use provided) and params; derive new_kmaster.
      3) For each file: unwrap file_key using old_kmaster, then rewrap with new_kmaster.
      4) Re-encrypt inner JSON under new_kmaster and write new header.
    """
    repo = Path(args.repo)
    inner, old_kmaster, old_kdf = unlock(repo, args.passphrase)

    # New KDF params
    new_t = args.t if args.t is not None else old_kdf["t"]
    new_m = args.m if args.m is not None else old_kdf["m"]
    new_p = args.p if args.p is not None else old_kdf["p"]
    new_salt = os.urandom(16)

    new_kmaster = derive_kmaster(args.new_passphrase or args.passphrase, new_salt, new_t, new_m, new_p)

    # Rewrap file keys
    import base64
    for f in inner.files:
        wrap = f["file_key_wrap"]
        file_key = aead_decrypt(old_kmaster, base64.b64decode(wrap["nonce"]), base64.b64decode(wrap["ct"]))
        n, c = aead_encrypt(new_kmaster, file_key)
        f["file_key_wrap"] = {"nonce": base64.b64encode(n).decode(), "ct": base64.b64encode(c).decode()}

    # Re-encrypt inner under new master
    inner_bytes = InnerMetadata(version=1, files=inner.files).to_bytes()
    nonce, ct = aead_encrypt(new_kmaster, inner_bytes)

    save_vault(repo_paths(repo)["vault"], new_t, new_m, new_p, new_salt, nonce, ct)
    print("[+] Master key rotated.")


# ------------------------------- GUI ------------------------------

def cmd_gui(args: argparse.Namespace) -> None:
    try:
        from PyQt6 import QtWidgets, QtGui, QtCore
    except Exception as e:
        print("[!] PyQt6 not installed. pip install PyQt6")
        sys.exit(1)

    class VaultApp(QtWidgets.QMainWindow):
        def __init__(self, repo: Path):
            super().__init__()
            self.repo = repo
            self.setWindowTitle("EFS – Vault Explorer")
            self.resize(900, 600)

            central = QtWidgets.QWidget(self)
            self.setCentralWidget(central)
            layout = QtWidgets.QVBoxLayout(central)

            # Passphrase prompt
            self.pass_edit = QtWidgets.QLineEdit()
            self.pass_edit.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
            self.pass_edit.setPlaceholderText("Master passphrase…")
            open_btn = QtWidgets.QPushButton("Unlock Vault")
            open_btn.clicked.connect(self.unlock)

            hl = QtWidgets.QHBoxLayout()
            hl.addWidget(self.pass_edit)
            hl.addWidget(open_btn)
            layout.addLayout(hl)

            # Table
            self.table = QtWidgets.QTableWidget(0, 4)
            self.table.setHorizontalHeaderLabels(["ID", "Name", "Size", "Blob Path"])
            self.table.horizontalHeader().setStretchLastSection(True)
            layout.addWidget(self.table)

            # Actions
            btn_row = QtWidgets.QHBoxLayout()
            self.save_btn = QtWidgets.QPushButton("Extract Selected…")
            self.save_btn.clicked.connect(self.extract_selected)
            self.save_btn.setEnabled(False)
            btn_row.addWidget(self.save_btn)
            layout.addLayout(btn_row)

            self.inner = None
            self.kmaster = None

        def unlock(self):
            pw = self.pass_edit.text()
            try:
                self.inner, self.kmaster, _ = unlock(self.repo, pw)
            except Exception as e:
                QtWidgets.QMessageBox.critical(self, "Unlock failed", str(e))
                return
            self.populate()
            self.save_btn.setEnabled(True)

        def populate(self):
            self.table.setRowCount(0)
            for f in self.inner.files:
                r = self.table.rowCount()
                self.table.insertRow(r)
                self.table.setItem(r, 0, QtWidgets.QTableWidgetItem(f.get("id", "")))
                self.table.setItem(r, 1, QtWidgets.QTableWidgetItem(f.get("name", "")))
                self.table.setItem(r, 2, QtWidgets.QTableWidgetItem(str(f.get("size", 0))))
                self.table.setItem(r, 3, QtWidgets.QTableWidgetItem(f.get("blob", "")))

        def extract_selected(self):
            rows = sorted({ix.row() for ix in self.table.selectedIndexes()})
            if not rows:
                return
            r = rows[0]
            fid = self.table.item(r, 0).text()
            name = self.table.item(r, 1).text()
            dlg = QtWidgets.QFileDialog(self)
            out, _ = dlg.getSaveFileName(self, "Save decrypted file", name)
            if not out:
                return
            # do extraction using kmaster
            args = argparse.Namespace(repo=str(self.repo), id=fid, out=out, passphrase=self.pass_edit.text())
            try:
                cmd_extract(args)
                QtWidgets.QMessageBox.information(self, "Done", f"Saved to {out}")
            except Exception as e:
                QtWidgets.QMessageBox.critical(self, "Error", str(e))

    app = QtWidgets.QApplication([])
    v = VaultApp(Path(args.repo))
    v.show()
    app.exec()


# ----------------------------- CLI -------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Encrypted File System (GitHub-ready, opaque vault)")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_init = sub.add_parser("init", help="Initialize vault")
    p_init.add_argument("repo", help="Path to repo directory")
    p_init.add_argument("--passphrase", required=True)
    p_init.add_argument("-t", type=int, default=DEFAULT_T_COST, help="Argon2 time cost (iterations)")
    p_init.add_argument("-m", type=int, default=DEFAULT_M_COST_KiB, help="Argon2 memory (KiB)")
    p_init.add_argument("-p", type=int, default=DEFAULT_PARALLELISM, help="Argon2 parallelism")
    p_init.add_argument("--force", action="store_true", help="Overwrite existing vault.enc if present")
    p_init.set_defaults(func=cmd_init)

    p_add = sub.add_parser("add", help="Add a file (encrypt)")
    p_add.add_argument("repo", help="Path to repo directory")
    p_add.add_argument("path", help="Plaintext file to add")
    p_add.add_argument("--passphrase", required=True)
    p_add.set_defaults(func=cmd_add)

    p_ls = sub.add_parser("ls", help="List files (after unlock)")
    p_ls.add_argument("repo", help="Path to repo directory")
    p_ls.add_argument("--passphrase", required=True)
    p_ls.set_defaults(func=cmd_ls)

    p_ext = sub.add_parser("extract", help="Decrypt a file by id")
    p_ext.add_argument("repo", help="Path to repo directory")
    p_ext.add_argument("id", help="File id (UUID)")
    p_ext.add_argument("out", help="Output plaintext path")
    p_ext.add_argument("--passphrase", required=True)
    p_ext.set_defaults(func=cmd_extract)

    p_rm = sub.add_parser("rm", help="Remove a file by id")
    p_rm.add_argument("repo", help="Path to repo directory")
    p_rm.add_argument("id", help="File id (UUID)")
    p_rm.add_argument("--passphrase", required=True)
    p_rm.set_defaults(func=cmd_rm)

    p_ren = sub.add_parser("rename", help="Rename a file entry")
    p_ren.add_argument("repo", help="Path to repo directory")
    p_ren.add_argument("id", help="File id (UUID)")
    p_ren.add_argument("name", help="New name")
    p_ren.add_argument("--passphrase", required=True)
    p_ren.set_defaults(func=cmd_rename)

    p_rot = sub.add_parser("rotate-master", help="Rotate/Change master key and/or Argon2 params")
    p_rot.add_argument("repo", help="Path to repo directory")
    p_rot.add_argument("--passphrase", required=True, help="Current passphrase")
    p_rot.add_argument("--new-passphrase", help="New passphrase (default: reuse current)")
    p_rot.add_argument("-t", type=int, help="New Argon2 time cost (iterations)")
    p_rot.add_argument("-m", type=int, help="New Argon2 memory (KiB)")
    p_rot.add_argument("-p", type=int, help="New Argon2 parallelism")
    p_rot.set_defaults(func=cmd_rotate_master)

    p_gui = sub.add_parser("gui", help="Launch minimal GUI")
    p_gui.add_argument("repo", help="Path to repo directory")
    p_gui.set_defaults(func=cmd_gui)

    return p


def main():
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
