import argparse
import os
import sys
import uuid

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from pathlib import Path
from typing import Dict

from crypto.aead import aead_encrypt, aead_decrypt
from crypto.hash import derive_kmaster
from storage.vault import save_vault, load_vault
from utils.helper import repo_paths, rel_time_iso
from utils.dataModels import InnerMetadata, KeyWrap, FileEntry

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


def update_file_in_vault(repo: Path, fid: str, new_content: bytes, passphrase: str) -> None:
    """Update an existing file in the vault with new content."""
    inner, kmaster, kdf = unlock(repo, passphrase)
    p = repo_paths(repo)

    # Find the file entry
    match = next((f for f in inner.files if f["id"] == fid), None)
    if not match:
        raise ValueError(f"No such id: {fid}")

    # Generate new per-file key
    file_key = os.urandom(32)  # AES-256

    # Encrypt new content with new file_key
    file_nonce = os.urandom(12)
    file_ct = AESGCM(file_key).encrypt(file_nonce, new_content, None)

    # Write new blob: nonce||ct
    blob_path = p["blobs"] / f"{fid}.bin"
    with blob_path.open("wb") as f:
        f.write(file_nonce + file_ct)

    # Wrap new file_key with Kmaster
    wrap_nonce, wrap_ct = aead_encrypt(kmaster, file_key)
    import base64
    keywrap = KeyWrap(nonce_b64=base64.b64encode(wrap_nonce).decode(), ct_b64=base64.b64encode(wrap_ct).decode())

    # Update the file entry
    match["size"] = len(new_content)
    match["file_key_wrap"] = keywrap.to_dict()

    # Re-encrypt inner and save vault
    inner_bytes = inner.to_bytes()
    new_nonce, new_ct = aead_encrypt(kmaster, inner_bytes)
    save_vault(p["vault"], kdf["t"], kdf["m"], kdf["p"], kdf["salt"], new_nonce, new_ct)


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
