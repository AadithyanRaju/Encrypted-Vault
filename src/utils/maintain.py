import argparse
import os
import sys

from pathlib import Path

from crypto.hash import derive_kmaster
from crypto.aead import aead_encrypt, aead_decrypt
from storage.vault import save_vault
from utils.core import unlock
from utils.dataModels import InnerMetadata
from utils.helper import repo_paths


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

