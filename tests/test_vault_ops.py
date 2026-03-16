"""Tests for vault operations: init, add, ls, extract, rm, rename, rotate-master."""
import argparse
import os
import pytest

from pathlib import Path

from test_constants import FAST_T, FAST_M, FAST_P, TEST_PASSPHRASE
from utils.core import cmd_init, cmd_add, cmd_ls, cmd_extract, unlock
from utils.maintain import cmd_rm, cmd_rename, cmd_rotate_master
from utils.helper import repo_paths


def _init_args(repo: Path, passphrase: str = TEST_PASSPHRASE, force: bool = False) -> argparse.Namespace:
    return argparse.Namespace(
        repo=str(repo), passphrase=passphrase, t=FAST_T, m=FAST_M, p=FAST_P, force=force
    )


def _add_args(repo: Path, path: Path, passphrase: str = TEST_PASSPHRASE, relpath: str = None) -> argparse.Namespace:
    return argparse.Namespace(repo=str(repo), path=str(path), passphrase=passphrase, relpath=relpath)


def _ls_args(repo: Path, passphrase: str = TEST_PASSPHRASE) -> argparse.Namespace:
    return argparse.Namespace(repo=str(repo), passphrase=passphrase)


# ---------------------------------------------------------------------------
# cmd_init
# ---------------------------------------------------------------------------

class TestCmdInit:
    def test_creates_vault_enc(self, tmp_path: Path):
        cmd_init(_init_args(tmp_path))
        assert (tmp_path / "vault.enc").exists()

    def test_creates_blobs_directory(self, tmp_path: Path):
        cmd_init(_init_args(tmp_path))
        assert (tmp_path / "blobs").is_dir()

    def test_vault_is_unlockable(self, tmp_path: Path):
        cmd_init(_init_args(tmp_path))
        inner, kmaster, kdf = unlock(tmp_path, TEST_PASSPHRASE)
        assert inner.files == []
        assert len(kmaster) == 32

    def test_init_twice_without_force_exits(self, tmp_path: Path):
        cmd_init(_init_args(tmp_path))
        with pytest.raises(SystemExit):
            cmd_init(_init_args(tmp_path, force=False))

    def test_init_with_force_overwrites(self, tmp_path: Path):
        cmd_init(_init_args(tmp_path))
        cmd_init(_init_args(tmp_path, force=True))  # Should not raise
        assert (tmp_path / "vault.enc").exists()


# ---------------------------------------------------------------------------
# cmd_add
# ---------------------------------------------------------------------------

class TestCmdAdd:
    def test_add_creates_blob(self, tmp_vault: Path, sample_file: Path):
        cmd_add(_add_args(tmp_vault, sample_file))
        blobs = list((tmp_vault / "blobs").iterdir())
        assert len(blobs) == 1

    def test_add_updates_metadata(self, tmp_vault: Path, sample_file: Path):
        cmd_add(_add_args(tmp_vault, sample_file))
        inner, _, _ = unlock(tmp_vault, TEST_PASSPHRASE)
        assert len(inner.files) == 1
        assert inner.files[0]["name"] == sample_file.name

    def test_add_preserves_file_size(self, tmp_vault: Path, sample_file: Path):
        cmd_add(_add_args(tmp_vault, sample_file))
        inner, _, _ = unlock(tmp_vault, TEST_PASSPHRASE)
        assert inner.files[0]["size"] == len(sample_file.read_bytes())

    def test_add_multiple_files(self, tmp_vault: Path, tmp_path: Path):
        for i in range(3):
            f = tmp_path / f"file{i}.txt"
            f.write_bytes(f"content {i}".encode())
            cmd_add(_add_args(tmp_vault, f))
        inner, _, _ = unlock(tmp_vault, TEST_PASSPHRASE)
        assert len(inner.files) == 3

    def test_add_nonexistent_file_exits(self, tmp_vault: Path):
        args = _add_args(tmp_vault, Path("/nonexistent/path/file.txt"))
        with pytest.raises(SystemExit):
            cmd_add(args)

    def test_add_with_relpath(self, tmp_vault: Path, sample_file: Path):
        cmd_add(_add_args(tmp_vault, sample_file, relpath="docs/hello.txt"))
        inner, _, _ = unlock(tmp_vault, TEST_PASSPHRASE)
        assert inner.files[0]["relpath"] == "docs/hello.txt"

    def test_add_binary_file(self, tmp_vault: Path, binary_file: Path):
        cmd_add(_add_args(tmp_vault, binary_file))
        inner, _, _ = unlock(tmp_vault, TEST_PASSPHRASE)
        assert inner.files[0]["size"] == 256


# ---------------------------------------------------------------------------
# cmd_extract
# ---------------------------------------------------------------------------

class TestCmdExtract:
    def _extract_args(self, repo: Path, fid: str, out: Path, passphrase: str = TEST_PASSPHRASE) -> argparse.Namespace:
        return argparse.Namespace(repo=str(repo), id=fid, out=str(out), passphrase=passphrase)

    def test_extract_recovers_plaintext(self, tmp_vault: Path, sample_file: Path, tmp_path: Path):
        cmd_add(_add_args(tmp_vault, sample_file))
        inner, _, _ = unlock(tmp_vault, TEST_PASSPHRASE)
        fid = inner.files[0]["id"]
        out = tmp_path / "recovered.txt"
        cmd_extract(self._extract_args(tmp_vault, fid, out))
        assert out.read_bytes() == sample_file.read_bytes()

    def test_extract_binary_file(self, tmp_vault: Path, binary_file: Path, tmp_path: Path):
        cmd_add(_add_args(tmp_vault, binary_file))
        inner, _, _ = unlock(tmp_vault, TEST_PASSPHRASE)
        fid = inner.files[0]["id"]
        out = tmp_path / "recovered.bin"
        cmd_extract(self._extract_args(tmp_vault, fid, out))
        assert out.read_bytes() == binary_file.read_bytes()

    def test_extract_wrong_passphrase_raises(self, tmp_vault: Path, sample_file: Path, tmp_path: Path):
        cmd_add(_add_args(tmp_vault, sample_file))
        inner, _, _ = unlock(tmp_vault, TEST_PASSPHRASE)
        fid = inner.files[0]["id"]
        out = tmp_path / "out.txt"
        with pytest.raises(Exception):
            cmd_extract(self._extract_args(tmp_vault, fid, out, passphrase="WRONG"))

    def test_extract_invalid_id_exits(self, tmp_vault: Path, tmp_path: Path):
        out = tmp_path / "out.txt"
        with pytest.raises(SystemExit):
            cmd_extract(self._extract_args(tmp_vault, "nonexistent-id", out))


# ---------------------------------------------------------------------------
# cmd_rm
# ---------------------------------------------------------------------------

class TestCmdRm:
    def _rm_args(self, repo: Path, fid: str, passphrase: str = TEST_PASSPHRASE) -> argparse.Namespace:
        return argparse.Namespace(repo=str(repo), id=fid, passphrase=passphrase)

    def test_rm_removes_metadata_entry(self, tmp_vault: Path, sample_file: Path):
        cmd_add(_add_args(tmp_vault, sample_file))
        inner, _, _ = unlock(tmp_vault, TEST_PASSPHRASE)
        fid = inner.files[0]["id"]
        cmd_rm(self._rm_args(tmp_vault, fid))
        inner2, _, _ = unlock(tmp_vault, TEST_PASSPHRASE)
        assert inner2.files == []

    def test_rm_deletes_blob_file(self, tmp_vault: Path, sample_file: Path):
        cmd_add(_add_args(tmp_vault, sample_file))
        inner, _, _ = unlock(tmp_vault, TEST_PASSPHRASE)
        fid = inner.files[0]["id"]
        blob_path = tmp_vault / "blobs" / f"{fid}.bin"
        assert blob_path.exists()
        cmd_rm(self._rm_args(tmp_vault, fid))
        assert not blob_path.exists()

    def test_rm_invalid_id_exits(self, tmp_vault: Path):
        with pytest.raises(SystemExit):
            cmd_rm(self._rm_args(tmp_vault, "no-such-id"))


# ---------------------------------------------------------------------------
# cmd_rename
# ---------------------------------------------------------------------------

class TestCmdRename:
    def _rename_args(self, repo: Path, fid: str, name: str, passphrase: str = TEST_PASSPHRASE) -> argparse.Namespace:
        return argparse.Namespace(repo=str(repo), id=fid, name=name, passphrase=passphrase)

    def test_rename_updates_name(self, tmp_vault: Path, sample_file: Path):
        cmd_add(_add_args(tmp_vault, sample_file))
        inner, _, _ = unlock(tmp_vault, TEST_PASSPHRASE)
        fid = inner.files[0]["id"]
        cmd_rename(self._rename_args(tmp_vault, fid, "renamed.txt"))
        inner2, _, _ = unlock(tmp_vault, TEST_PASSPHRASE)
        assert inner2.files[0]["name"] == "renamed.txt"

    def test_rename_invalid_id_exits(self, tmp_vault: Path):
        with pytest.raises(SystemExit):
            cmd_rename(self._rename_args(tmp_vault, "no-such-id", "new.txt"))


# ---------------------------------------------------------------------------
# cmd_rotate_master
# ---------------------------------------------------------------------------

class TestCmdRotateMaster:
    def _rotate_args(self, repo: Path, passphrase: str = TEST_PASSPHRASE,
                     new_passphrase: str = None, t=None, m=None, p=None) -> argparse.Namespace:
        return argparse.Namespace(
            repo=str(repo), passphrase=passphrase,
            new_passphrase=new_passphrase, t=t, m=m, p=p
        )

    def test_rotate_same_passphrase_vault_still_accessible(self, tmp_vault: Path, sample_file: Path):
        cmd_add(_add_args(tmp_vault, sample_file))
        cmd_rotate_master(self._rotate_args(tmp_vault))
        inner, _, _ = unlock(tmp_vault, TEST_PASSPHRASE)
        assert len(inner.files) == 1

    def test_rotate_new_passphrase(self, tmp_vault: Path, sample_file: Path, tmp_path: Path):
        cmd_add(_add_args(tmp_vault, sample_file))
        new_pw = "new-secure-passphrase"
        cmd_rotate_master(self._rotate_args(tmp_vault, new_passphrase=new_pw))
        # Old passphrase should no longer work
        with pytest.raises(Exception):
            unlock(tmp_vault, TEST_PASSPHRASE)
        # New passphrase should work
        inner, _, _ = unlock(tmp_vault, new_pw)
        assert len(inner.files) == 1

    def test_rotate_file_content_survives(self, tmp_vault: Path, sample_file: Path, tmp_path: Path):
        cmd_add(_add_args(tmp_vault, sample_file))
        inner, _, _ = unlock(tmp_vault, TEST_PASSPHRASE)
        fid = inner.files[0]["id"]
        new_pw = "rotated-pw"
        cmd_rotate_master(self._rotate_args(tmp_vault, new_passphrase=new_pw))
        # Extract with new passphrase
        out = tmp_path / "out.txt"
        extract_args = argparse.Namespace(
            repo=str(tmp_vault), id=fid, out=str(out), passphrase=new_pw
        )
        cmd_extract(extract_args)
        assert out.read_bytes() == sample_file.read_bytes()


# ---------------------------------------------------------------------------
# Metadata protection: filename encryption & blob padding
# ---------------------------------------------------------------------------

class TestMetadataProtection:
    """Verify filename encryption and size-obfuscation padding."""

    def test_name_enc_present_after_add(self, tmp_vault: Path, sample_file: Path):
        """name_enc must exist in the metadata dict after adding a file."""
        cmd_add(_add_args(tmp_vault, sample_file))
        inner, kmaster, _ = unlock(tmp_vault, TEST_PASSPHRASE)
        kmaster.wipe()
        assert "name_enc" in inner.files[0]

    def test_plaintext_name_absent_from_serialised_json(self, tmp_vault: Path, sample_file: Path):
        """After serialisation, the plaintext 'name' field must not appear when
        name_enc is present (so it is never written to disk)."""
        import json
        cmd_add(_add_args(tmp_vault, sample_file))
        inner, kmaster, _ = unlock(tmp_vault, TEST_PASSPHRASE)
        kmaster.wipe()
        data = json.loads(inner.to_bytes())
        assert "name" not in data["files"][0]
        assert "name_enc" in data["files"][0]

    def test_unlock_decrypts_name(self, tmp_vault: Path, sample_file: Path):
        """unlock() must populate the in-memory 'name' field from name_enc."""
        cmd_add(_add_args(tmp_vault, sample_file))
        inner, kmaster, _ = unlock(tmp_vault, TEST_PASSPHRASE)
        kmaster.wipe()
        assert inner.files[0]["name"] == sample_file.name

    def test_relpath_enc_present_when_relpath_given(self, tmp_vault: Path, sample_file: Path):
        """relpath_enc must exist when a relpath is provided during add."""
        cmd_add(_add_args(tmp_vault, sample_file, relpath="docs/hello.txt"))
        inner, kmaster, _ = unlock(tmp_vault, TEST_PASSPHRASE)
        kmaster.wipe()
        assert "relpath_enc" in inner.files[0]

    def test_unlock_decrypts_relpath(self, tmp_vault: Path, sample_file: Path):
        """unlock() must populate the in-memory 'relpath' field from relpath_enc."""
        cmd_add(_add_args(tmp_vault, sample_file, relpath="docs/hello.txt"))
        inner, kmaster, _ = unlock(tmp_vault, TEST_PASSPHRASE)
        kmaster.wipe()
        assert inner.files[0]["relpath"] == "docs/hello.txt"

    def test_blob_size_within_padding_bounds(self, tmp_vault: Path, sample_file: Path):
        """Blob must be at least real_size + nonce(12) + GCM-tag(16) bytes and
        at most real_size + PAD_MAX + nonce(12) + GCM-tag(16) bytes."""
        from utils.dataModels import PAD_MAX
        cmd_add(_add_args(tmp_vault, sample_file))
        inner, kmaster, _ = unlock(tmp_vault, TEST_PASSPHRASE)
        kmaster.wipe()
        fid = inner.files[0]["id"]
        real_size = inner.files[0]["size"]
        blob = (tmp_vault / "blobs" / f"{fid}.bin").read_bytes()
        # blob = nonce(12) + AEAD(padded_plaintext) where AEAD overhead = 16
        blob_data_len = len(blob) - 12
        assert blob_data_len >= real_size + 16
        assert blob_data_len <= real_size + PAD_MAX + 16

    def test_rename_updates_name_enc(self, tmp_vault: Path, sample_file: Path):
        """After rename, unlock() must return the new name via name_enc."""
        cmd_add(_add_args(tmp_vault, sample_file))
        inner, kmaster, _ = unlock(tmp_vault, TEST_PASSPHRASE)
        kmaster.wipe()
        fid = inner.files[0]["id"]
        rename_args = argparse.Namespace(
            repo=str(tmp_vault), id=fid, name="new_name.txt", passphrase=TEST_PASSPHRASE
        )
        cmd_rename(rename_args)
        inner2, kmaster2, _ = unlock(tmp_vault, TEST_PASSPHRASE)
        kmaster2.wipe()
        assert inner2.files[0]["name"] == "new_name.txt"

    def test_extract_strips_padding(self, tmp_vault: Path, sample_file: Path, tmp_path: Path):
        """Extracted content must exactly match the original file despite padding."""
        cmd_add(_add_args(tmp_vault, sample_file))
        inner, kmaster, _ = unlock(tmp_vault, TEST_PASSPHRASE)
        kmaster.wipe()
        fid = inner.files[0]["id"]
        out = tmp_path / "recovered.txt"
        cmd_extract(argparse.Namespace(
            repo=str(tmp_vault), id=fid, out=str(out), passphrase=TEST_PASSPHRASE
        ))
        assert out.read_bytes() == sample_file.read_bytes()
