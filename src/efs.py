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
  - Kmaster = Argon2id(SHA3-512(passphrase)) -> 32 bytes or 256 bits

Note: This is a reference implementation for clarity, not a final audited product.
"""
from __future__ import annotations
from ui.cli import build_parser

def main():
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
