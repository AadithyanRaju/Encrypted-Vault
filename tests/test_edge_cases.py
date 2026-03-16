"""Edge-case and security-boundary tests."""
import argparse
import os
import struct
import pytest

from pathlib import Path
from cryptography.exceptions import InvalidTag

from test_constants import FAST_T, FAST_M, FAST_P, TEST_PASSPHRASE
from crypto.aead import aead_encrypt, aead_decrypt
from crypto.hash import derive_kmaster
from storage.vault import save_vault, load_vault
from utils.core import cmd_init, cmd_add, cmd_extract, unlock
from utils.dataModels import VAULT_MAGIC, VAULT_VERSION, VAULT_HDR_FMT, VAULT_HDR_SIZE


def _init(repo: Path, passphrase: str = TEST_PASSPHRASE) -> None:
    cmd_init(argparse.Namespace(
        repo=str(repo), passphrase=passphrase,
        t=FAST_T, m=FAST_M, p=FAST_P, force=False
    ))


def _add(repo: Path, src: Path, passphrase: str = TEST_PASSPHRASE) -> None:
    cmd_add(argparse.Namespace(
        repo=str(repo), path=str(src), passphrase=passphrase, relpath=None
    ))


# ---------------------------------------------------------------------------
# Wrong-passphrase / authentication failures
# ---------------------------------------------------------------------------

class TestAuthenticationFailures:
    def test_wrong_passphrase_on_unlock_raises(self, tmp_path: Path):
        _init(tmp_path)
        with pytest.raises(Exception):
            unlock(tmp_path, "wrong-password")

    def test_wrong_passphrase_on_extract_exits(self, tmp_path: Path, sample_file: Path):
        _init(tmp_path)
        _add(tmp_path, sample_file)
        inner, _, _ = unlock(tmp_path, TEST_PASSPHRASE)
        fid = inner.files[0]["id"]
        out = tmp_path / "out.txt"
        with pytest.raises(Exception):
            cmd_extract(argparse.Namespace(
                repo=str(tmp_path), id=fid, out=str(out), passphrase="WRONG"
            ))


# ---------------------------------------------------------------------------
# Corrupted vault file
# ---------------------------------------------------------------------------

class TestCorruptedVault:
    def test_corrupted_ciphertext_raises_on_unlock(self, tmp_path: Path):
        _init(tmp_path)
        vp = tmp_path / "vault.enc"
        raw = bytearray(vp.read_bytes())
        # Flip a byte in the ciphertext portion
        raw[VAULT_HDR_SIZE] ^= 0xFF
        vp.write_bytes(bytes(raw))
        with pytest.raises(Exception):
            unlock(tmp_path, TEST_PASSPHRASE)

    def test_truncated_header_raises(self, tmp_path: Path):
        _init(tmp_path)
        vp = tmp_path / "vault.enc"
        vp.write_bytes(vp.read_bytes()[:5])
        with pytest.raises(ValueError):
            load_vault(vp)

    def test_corrupted_blob_raises_on_extract(self, tmp_path: Path, sample_file: Path):
        _init(tmp_path)
        _add(tmp_path, sample_file)
        inner, _, _ = unlock(tmp_path, TEST_PASSPHRASE)
        fid = inner.files[0]["id"]
        blob_path = tmp_path / "blobs" / f"{fid}.bin"
        raw = bytearray(blob_path.read_bytes())
        raw[-1] ^= 0xFF
        blob_path.write_bytes(bytes(raw))
        out = tmp_path / "out.txt"
        with pytest.raises(Exception):
            cmd_extract(argparse.Namespace(
                repo=str(tmp_path), id=fid, out=str(out), passphrase=TEST_PASSPHRASE
            ))


# ---------------------------------------------------------------------------
# Data model / inner metadata
# ---------------------------------------------------------------------------

class TestInnerMetadata:
    def test_empty_metadata_serialises(self):
        from utils.dataModels import InnerMetadata
        meta = InnerMetadata(version=1, files=[])
        b = meta.to_bytes()
        assert b"version" in b
        assert b"files" in b

    def test_roundtrip_serialisation(self):
        from utils.dataModels import InnerMetadata
        meta = InnerMetadata(version=1, files=[{"id": "abc", "name": "test.txt"}])
        restored = InnerMetadata.from_bytes(meta.to_bytes())
        assert restored.version == 1
        assert restored.files[0]["name"] == "test.txt"

    def test_from_bytes_missing_fields_defaults(self):
        import json
        from utils.dataModels import InnerMetadata
        b = json.dumps({}).encode()
        meta = InnerMetadata.from_bytes(b)
        assert meta.version == 1
        assert meta.files == []


# ---------------------------------------------------------------------------
# Large / zero-byte files
# ---------------------------------------------------------------------------

class TestFileSizeEdgeCases:
    def test_zero_byte_file(self, tmp_path: Path):
        _init(tmp_path)
        f = tmp_path / "empty.bin"
        f.write_bytes(b"")
        _add(tmp_path, f)
        inner, _, _ = unlock(tmp_path, TEST_PASSPHRASE)
        assert inner.files[0]["size"] == 0

    def test_zero_byte_file_extracts_correctly(self, tmp_path: Path):
        _init(tmp_path)
        f = tmp_path / "empty.bin"
        f.write_bytes(b"")
        _add(tmp_path, f)
        inner, _, _ = unlock(tmp_path, TEST_PASSPHRASE)
        fid = inner.files[0]["id"]
        out = tmp_path / "out.bin"
        cmd_extract(argparse.Namespace(
            repo=str(tmp_path), id=fid, out=str(out), passphrase=TEST_PASSPHRASE
        ))
        assert out.read_bytes() == b""

    def test_large_file(self, tmp_path: Path):
        _init(tmp_path)
        data = os.urandom(512 * 1024)  # 512 KiB
        f = tmp_path / "large.bin"
        f.write_bytes(data)
        _add(tmp_path, f)
        inner, _, _ = unlock(tmp_path, TEST_PASSPHRASE)
        fid = inner.files[0]["id"]
        out = tmp_path / "out.bin"
        cmd_extract(argparse.Namespace(
            repo=str(tmp_path), id=fid, out=str(out), passphrase=TEST_PASSPHRASE
        ))
        assert out.read_bytes() == data


# ---------------------------------------------------------------------------
# Nonce uniqueness / randomness properties
# ---------------------------------------------------------------------------

class TestNonceUniqueness:
    def test_file_blobs_have_unique_nonces(self, tmp_path: Path):
        _init(tmp_path)
        nonces = set()
        for i in range(5):
            f = tmp_path / f"file{i}.txt"
            f.write_bytes(f"content {i}".encode())
            _add(tmp_path, f)

        for blob in (tmp_path / "blobs").iterdir():
            raw = blob.read_bytes()
            nonces.add(raw[:12])

        assert len(nonces) == 5  # each blob has a unique nonce


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

class TestHelperUtils:
    def test_rel_time_iso_returns_string(self):
        from utils.helper import rel_time_iso
        ts = 1700000000.0
        s = rel_time_iso(ts)
        assert isinstance(s, str)
        assert s.endswith("Z")

    def test_rel_time_iso_none_returns_now(self):
        from utils.helper import rel_time_iso
        s = rel_time_iso(None)
        assert isinstance(s, str)
        assert s.endswith("Z")

    def test_repo_paths_keys(self, tmp_path: Path):
        from utils.helper import repo_paths
        paths = repo_paths(tmp_path)
        assert "vault" in paths
        assert "blobs" in paths
