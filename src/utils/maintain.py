import argparse
import base64
import os
import sys

from pathlib import Path

from crypto.hash import derive_kmaster
from crypto.aead import aead_encrypt, aead_decrypt
from crypto.secure_bytes import SecureBytes, wipe_key
from storage.vault import save_vault
from utils.core import unlock
from utils.dataModels import InnerMetadata
from utils.helper import repo_paths


def cmd_rm(args: argparse.Namespace) -> None:
    repo = Path(args.repo)
    fid = args.id
    inner, kmaster, kdf = unlock(repo, args.passphrase)
    try:
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

        inner_bytes = InnerMetadata(version=1, files=inner.files).to_bytes()
        new_nonce, new_ct = aead_encrypt(bytes(kmaster), inner_bytes)
        save_vault(repo_paths(repo)["vault"], kdf["t"], kdf["m"], kdf["p"], kdf["salt"], new_nonce, new_ct)
    finally:
        kmaster.wipe()
    print(f"[+] Removed id={fid}")


def cmd_rename(args: argparse.Namespace) -> None:
    repo = Path(args.repo)
    fid = args.id
    new_name = args.name
    inner, kmaster, kdf = unlock(repo, args.passphrase)
    try:
        match = next((f for f in inner.files if f["id"] == fid), None)
        if not match:
            print(f"[!] No such id: {fid}")
            sys.exit(1)

        # Re-encrypt the new filename with the per-file key.
        wrap = match["file_key_wrap"]
        file_key = bytearray(
            aead_decrypt(bytes(kmaster), base64.b64decode(wrap["nonce"]), base64.b64decode(wrap["ct"]))
        )
        try:
            nonce, ct = aead_encrypt(bytes(file_key), new_name.encode("utf-8"))
            match["name_enc"] = base64.b64encode(nonce + ct).decode()
        finally:
            wipe_key(file_key)

        match["name"] = new_name  # update the in-memory convenience field

        inner_bytes = InnerMetadata(version=1, files=inner.files).to_bytes()
        new_nonce, new_ct = aead_encrypt(bytes(kmaster), inner_bytes)
        save_vault(repo_paths(repo)["vault"], kdf["t"], kdf["m"], kdf["p"], kdf["salt"], new_nonce, new_ct)
    finally:
        kmaster.wipe()
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

    try:
        # Rewrap file keys
        for f in inner.files:
            wrap = f["file_key_wrap"]
            file_key = SecureBytes(
                aead_decrypt(bytes(old_kmaster), base64.b64decode(wrap["nonce"]), base64.b64decode(wrap["ct"]))
            )
            try:
                n, c = aead_encrypt(bytes(new_kmaster), bytes(file_key))
            finally:
                file_key.wipe()
            f["file_key_wrap"] = {"nonce": base64.b64encode(n).decode(), "ct": base64.b64encode(c).decode()}

        # Re-encrypt inner under new master
        inner_bytes = InnerMetadata(version=1, files=inner.files).to_bytes()
        nonce, ct = aead_encrypt(bytes(new_kmaster), inner_bytes)

        save_vault(repo_paths(repo)["vault"], new_t, new_m, new_p, new_salt, nonce, ct)
    finally:
        old_kmaster.wipe()
        new_kmaster.wipe()

    print("[+] Master key rotated.")

