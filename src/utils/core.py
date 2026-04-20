import argparse
import base64
import os
import sys
import uuid

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from pathlib import Path
from typing import Dict, List

from crypto.aead import aead_encrypt, aead_decrypt
from crypto.hash import derive_kmaster
from crypto.merkle import compute_merkle_root
from crypto.secure_bytes import SecureBytes, wipe_key
from storage.vault import save_vault, load_vault
from utils.helper import repo_paths, rel_time_iso
from utils.dataModels import InnerMetadata, KeyWrap, FileEntry


def compute_vault_merkle_root(repo: Path, files: List[Dict]) -> bytes:
    """Return the Merkle root computed over the raw blob bytes of *files*.

    Leaves are ordered by their position in *files* (i.e. the canonical
    order stored in ``InnerMetadata.files``).  Missing blobs cause a
    ``FileNotFoundError``.
    """
    blobs = [((repo / f["blob"]).read_bytes()) for f in files]
    return compute_merkle_root(blobs)


def verify_vault_integrity(repo: Path, inner: InnerMetadata) -> None:
    """Verify the vault's Merkle root against the stored value.

    Raises:
        ValueError: if no Merkle root is stored (vault predates this
            feature) or if the computed root does not match the stored one.
    """
    if inner.merkle_root is None:
        raise ValueError("Vault has no Merkle root; run any vault-modifying command (add/rm/rename/rotate-master) to upgrade.")
    stored = base64.b64decode(inner.merkle_root)
    computed = compute_vault_merkle_root(repo, inner.files)
    if computed != stored:
        raise ValueError("Vault integrity check FAILED: Merkle root mismatch – possible tampering or corruption detected.")


def cmd_verify(args: argparse.Namespace) -> None:
    repo = Path(args.repo)
    inner, kmaster, _ = unlock(repo, args.passphrase)
    try:
        verify_vault_integrity(repo, inner)
    finally:
        kmaster.wipe()
    print("[+] Vault integrity verified: Merkle tree root matches.")


def prepare_file_add(repo: Path, src: Path, relpath: str | None, kmaster: "bytes | SecureBytes") -> FileEntry:
    """Encrypt *src* and store it as a new blob inside the vault.

    *kmaster* may be plain ``bytes`` or a ``SecureBytes`` instance; it is
    converted to ``bytes`` internally and the per-file key is wiped once
    the blob has been written.
    """
    p = repo_paths(repo)
    kmaster_bytes = bytes(kmaster)  # safe whether kmaster is bytes or SecureBytes
    file_key = SecureBytes(os.urandom(32))
    try:
        plaintext = src.read_bytes()
        file_nonce = os.urandom(12)
        file_ct = AESGCM(bytes(file_key)).encrypt(file_nonce, plaintext, None)

        fid = str(uuid.uuid4())
        blob_path = p["blobs"] / f"{fid}.bin"
        with blob_path.open("wb") as f:
            f.write(file_nonce + file_ct)

        wrap_nonce, wrap_ct = aead_encrypt(kmaster_bytes, bytes(file_key))
        keywrap = KeyWrap(
            nonce_b64=base64.b64encode(wrap_nonce).decode(),
            ct_b64=base64.b64encode(wrap_ct).decode(),
        )
    finally:
        file_key.wipe()

    # normalize relpath to POSIX style if provided
    relpath_value = str(Path(relpath).as_posix()) if relpath else None

    entry = FileEntry(
        id=fid,
        name=src.name,
        relpath=relpath_value,
        blob=f"blobs/{fid}.bin",
        size=len(plaintext),
        created_at=rel_time_iso(os.path.getctime(src)),
        modified_at=rel_time_iso(os.path.getmtime(src)),
        mimetype=None,
        file_key_wrap=keywrap,
    )
    return entry

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
    try:
        # Empty inner metadata
        merkle_root_b64 = base64.b64encode(compute_merkle_root([])).decode()
        inner = InnerMetadata(version=1, files=[], merkle_root=merkle_root_b64)
        inner_bytes = inner.to_bytes()

        # Encrypt inner under Kmaster
        nonce, ct = aead_encrypt(bytes(kmaster), inner_bytes)
    finally:
        kmaster.wipe()

    save_vault(p["vault"], args.t, args.m, args.p, salt, nonce, ct)
    print(f"[+] Initialized vault at {repo}")


def unlock(repo: Path, passphrase: str) -> "tuple[InnerMetadata, SecureBytes, Dict[str, int | bytes]]":
    """Decrypt and return the vault's inner metadata together with the master key.

    The caller is responsible for wiping the returned ``SecureBytes``
    (``kmaster``) when it is no longer needed.
    """
    p = repo_paths(repo)
    t, m, paral, salt, nonce, ct = load_vault(p["vault"])
    kmaster = derive_kmaster(passphrase, salt, t, m, paral)
    inner_bytes = aead_decrypt(bytes(kmaster), nonce, ct)
    inner = InnerMetadata.from_bytes(inner_bytes)
    return inner, kmaster, {"t": t, "m": m, "p": paral, "salt": salt}


def update_file_in_vault(repo: Path, fid: str, new_content: bytes, passphrase: str) -> None:
    """Update an existing file in the vault with new content."""
    inner, kmaster, kdf = unlock(repo, passphrase)
    p = repo_paths(repo)

    try:
        # Find the file entry
        match = next((f for f in inner.files if f["id"] == fid), None)
        if not match:
            raise ValueError(f"No such id: {fid}")

        # Generate new per-file key
        file_key = SecureBytes(os.urandom(32))
        try:
            # Encrypt new content with new file_key
            file_nonce = os.urandom(12)
            file_ct = AESGCM(bytes(file_key)).encrypt(file_nonce, new_content, None)

            # Write new blob: nonce||ct
            blob_path = p["blobs"] / f"{fid}.bin"
            with blob_path.open("wb") as f:
                f.write(file_nonce + file_ct)

            # Wrap new file_key with Kmaster
            wrap_nonce, wrap_ct = aead_encrypt(bytes(kmaster), bytes(file_key))
            keywrap = KeyWrap(
                nonce_b64=base64.b64encode(wrap_nonce).decode(),
                ct_b64=base64.b64encode(wrap_ct).decode(),
            )
        finally:
            file_key.wipe()

        # Update the file entry
        match["size"] = len(new_content)
        match["file_key_wrap"] = keywrap.to_dict()

        # Update Merkle root and re-encrypt inner and save vault
        inner.merkle_root = base64.b64encode(compute_vault_merkle_root(repo, inner.files)).decode()
        inner_bytes = inner.to_bytes()
        new_nonce, new_ct = aead_encrypt(bytes(kmaster), inner_bytes)
        save_vault(p["vault"], kdf["t"], kdf["m"], kdf["p"], kdf["salt"], new_nonce, new_ct)
    finally:
        kmaster.wipe()


def cmd_add(args: argparse.Namespace) -> None:
    repo = Path(args.repo)
    src = Path(args.path)
    if not src.is_file():
        print(f"[!] Not a file: {src}")
        sys.exit(1)

    inner, kmaster, kdf = unlock(repo, args.passphrase)
    p = repo_paths(repo)

    try:
        # Generate per-file key
        file_key = SecureBytes(os.urandom(32))

        # Read plaintext
        plaintext = src.read_bytes()

        try:
            # Encrypt file content with file_key
            file_nonce = os.urandom(12)
            file_ct = AESGCM(bytes(file_key)).encrypt(file_nonce, plaintext, None)

            # Write blob: nonce||ct
            fid = str(uuid.uuid4())
            blob_path = p["blobs"] / f"{fid}.bin"
            with blob_path.open("wb") as f:
                f.write(file_nonce + file_ct)

            # Wrap file_key with Kmaster
            wrap_nonce, wrap_ct = aead_encrypt(bytes(kmaster), bytes(file_key))
            keywrap = KeyWrap(
                nonce_b64=base64.b64encode(wrap_nonce).decode(),
                ct_b64=base64.b64encode(wrap_ct).decode(),
            )
        finally:
            file_key.wipe()

        # Optional relative path metadata to preserve folder structure
        relpath_value = getattr(args, "relpath", None)
        if relpath_value:
            # normalize separators to POSIX-style for portability
            relpath_value = str(Path(relpath_value).as_posix())

        entry = FileEntry(
            id=fid,
            name=src.name,
            relpath=relpath_value,
            blob=f"blobs/{fid}.bin",
            size=len(plaintext),
            created_at=rel_time_iso(os.path.getctime(src)),
            modified_at=rel_time_iso(os.path.getmtime(src)),
            mimetype=None,
            file_key_wrap=keywrap,
        )
        inner.files.append(entry.to_dict())

        # Update Merkle root and re-encrypt inner and save vault
        inner.merkle_root = base64.b64encode(compute_vault_merkle_root(repo, inner.files)).decode()
        inner_bytes = inner.to_bytes()
        new_nonce, new_ct = aead_encrypt(bytes(kmaster), inner_bytes)
        save_vault(p["vault"], kdf["t"], kdf["m"], kdf["p"], kdf["salt"], new_nonce, new_ct)
    finally:
        kmaster.wipe()

    print(f"[+] Encrypted and added {src.name} as id={fid}")


def cmd_ls(args: argparse.Namespace) -> None:
    repo = Path(args.repo)
    inner, kmaster, _ = unlock(repo, args.passphrase)
    try:
        if not inner.files:
            print("(empty)")
            return
        for fobj in inner.files:
            print(f"{fobj['id']}\t{fobj['name']}\t{fobj['size']} bytes\t{fobj['blob']}")
    finally:
        kmaster.wipe()


def cmd_extract(args: argparse.Namespace) -> None:
    repo = Path(args.repo)
    fid = args.id
    out = Path(args.out)

    inner, kmaster, _ = unlock(repo, args.passphrase)

    try:
        match = next((f for f in inner.files if f["id"] == fid), None)
        if not match:
            print(f"[!] No such id: {fid}")
            sys.exit(1)

        # Unwrap per-file key
        wrap = match["file_key_wrap"]
        file_key = SecureBytes(
            aead_decrypt(bytes(kmaster), base64.b64decode(wrap["nonce"]), base64.b64decode(wrap["ct"]))
        )
        try:
            # Read blob and decrypt
            blob_path = Path(repo) / match["blob"]
            blob = blob_path.read_bytes()
            if len(blob) < 13:
                print("[!] Corrupt blob")
                sys.exit(1)
            file_nonce, file_ct = blob[:12], blob[12:]
            plaintext = AESGCM(bytes(file_key)).decrypt(file_nonce, file_ct, None)
        finally:
            file_key.wipe()
    finally:
        kmaster.wipe()

    out.write_bytes(plaintext)
    print(f"[+] Extracted {match['name']} -> {out}")
