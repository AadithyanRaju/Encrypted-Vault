"""Tests for storage/vault.py (binary vault header serialisation)."""
import os
import struct
import pytest

from pathlib import Path

from storage.vault import save_vault, load_vault
from utils.dataModels import VAULT_MAGIC, VAULT_VERSION, VAULT_HDR_FMT, VAULT_HDR_SIZE


SALT = os.urandom(16)
NONCE = os.urandom(12)
CT = os.urandom(64)


class TestSaveAndLoadVault:
    def test_roundtrip(self, tmp_path: Path):
        vp = tmp_path / "vault.enc"
        save_vault(vp, 1, 8, 1, SALT, NONCE, CT)
        t, m, p, salt, nonce, ct = load_vault(vp)
        assert t == 1
        assert m == 8
        assert p == 1
        assert salt == SALT
        assert nonce == NONCE
        assert ct == CT

    def test_file_created(self, tmp_path: Path):
        vp = tmp_path / "vault.enc"
        save_vault(vp, 1, 8, 1, SALT, NONCE, CT)
        assert vp.exists()

    def test_no_tmp_file_left_after_save(self, tmp_path: Path):
        vp = tmp_path / "vault.enc"
        save_vault(vp, 1, 8, 1, SALT, NONCE, CT)
        assert not (tmp_path / "vault.tmp").exists()

    def test_magic_bytes_present(self, tmp_path: Path):
        vp = tmp_path / "vault.enc"
        save_vault(vp, 1, 8, 1, SALT, NONCE, CT)
        raw = vp.read_bytes()
        assert raw[:4] == VAULT_MAGIC

    def test_ciphertext_appended_after_header(self, tmp_path: Path):
        vp = tmp_path / "vault.enc"
        save_vault(vp, 1, 8, 1, SALT, NONCE, CT)
        raw = vp.read_bytes()
        assert raw[VAULT_HDR_SIZE:] == CT

    def test_kdf_params_roundtrip(self, tmp_path: Path):
        vp = tmp_path / "vault.enc"
        save_vault(vp, t=3, m=65536, p=4, salt=SALT, nonce=NONCE, ct=CT)
        t, m, p, _, _, _ = load_vault(vp)
        assert (t, m, p) == (3, 65536, 4)


class TestLoadVaultErrors:
    def test_too_small_raises(self, tmp_path: Path):
        vp = tmp_path / "vault.enc"
        vp.write_bytes(b"\x00" * 10)
        with pytest.raises(ValueError, match="too small or corrupt"):
            load_vault(vp)

    def test_wrong_magic_raises(self, tmp_path: Path):
        vp = tmp_path / "vault.enc"
        header = struct.pack(VAULT_HDR_FMT, b"BAAD", VAULT_VERSION, 1, 8, 1, SALT, NONCE)
        vp.write_bytes(header + CT)
        with pytest.raises(ValueError, match="Invalid vault magic"):
            load_vault(vp)

    def test_wrong_version_raises(self, tmp_path: Path):
        vp = tmp_path / "vault.enc"
        header = struct.pack(VAULT_HDR_FMT, VAULT_MAGIC, 99, 1, 8, 1, SALT, NONCE)
        vp.write_bytes(header + CT)
        with pytest.raises(ValueError, match="Unsupported vault version"):
            load_vault(vp)

    def test_empty_file_raises(self, tmp_path: Path):
        vp = tmp_path / "vault.enc"
        vp.write_bytes(b"")
        with pytest.raises(ValueError):
            load_vault(vp)
