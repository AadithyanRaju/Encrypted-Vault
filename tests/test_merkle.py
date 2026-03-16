"""Tests for Merkle tree tamper-evident vault feature."""
import argparse
import base64
import hashlib
import os
import pytest

from pathlib import Path

from crypto.merkle import compute_merkle_root
from test_constants import FAST_T, FAST_M, FAST_P, TEST_PASSPHRASE
from utils.core import cmd_init, cmd_add, cmd_verify, compute_vault_merkle_root, verify_vault_integrity, unlock
from utils.dataModels import InnerMetadata


# ---------------------------------------------------------------------------
# compute_merkle_root unit tests
# ---------------------------------------------------------------------------

class TestComputeMerkleRoot:
    def test_empty_list_returns_32_zero_bytes(self):
        root = compute_merkle_root([])
        assert root == b"\x00" * 32

    def test_single_leaf_is_sha256_of_leaf(self):
        leaf = b"hello"
        root = compute_merkle_root([leaf])
        assert root == hashlib.sha256(leaf).digest()

    def test_two_leaves(self):
        a, b = b"left", b"right"
        h_a = hashlib.sha256(a).digest()
        h_b = hashlib.sha256(b).digest()
        expected = hashlib.sha256(h_a + h_b).digest()
        assert compute_merkle_root([a, b]) == expected

    def test_three_leaves_odd_count_duplicates_last(self):
        a, b, c = b"a", b"b", b"c"
        h_a = hashlib.sha256(a).digest()
        h_b = hashlib.sha256(b).digest()
        h_c = hashlib.sha256(c).digest()
        parent_ab = hashlib.sha256(h_a + h_b).digest()
        parent_cc = hashlib.sha256(h_c + h_c).digest()
        expected = hashlib.sha256(parent_ab + parent_cc).digest()
        assert compute_merkle_root([a, b, c]) == expected

    def test_four_leaves_balanced_tree(self):
        leaves = [b"w", b"x", b"y", b"z"]
        hashes = [hashlib.sha256(l).digest() for l in leaves]
        left = hashlib.sha256(hashes[0] + hashes[1]).digest()
        right = hashlib.sha256(hashes[2] + hashes[3]).digest()
        expected = hashlib.sha256(left + right).digest()
        assert compute_merkle_root(leaves) == expected

    def test_output_is_32_bytes(self):
        for n in range(1, 6):
            leaves = [os.urandom(64) for _ in range(n)]
            assert len(compute_merkle_root(leaves)) == 32

    def test_deterministic(self):
        leaves = [b"alpha", b"beta", b"gamma"]
        assert compute_merkle_root(leaves) == compute_merkle_root(leaves)

    def test_different_leaves_different_root(self):
        leaves1 = [b"a", b"b"]
        leaves2 = [b"a", b"c"]
        assert compute_merkle_root(leaves1) != compute_merkle_root(leaves2)

    def test_order_matters(self):
        leaves = [b"first", b"second"]
        assert compute_merkle_root(leaves) != compute_merkle_root(list(reversed(leaves)))

    def test_modified_leaf_changes_root(self):
        leaves = [b"unchanged", b"original"]
        root1 = compute_merkle_root(leaves)
        tampered = [b"unchanged", b"tampered"]
        root2 = compute_merkle_root(tampered)
        assert root1 != root2


# ---------------------------------------------------------------------------
# Vault Merkle root integration tests
# ---------------------------------------------------------------------------

def _init_args(repo: Path, force: bool = False) -> argparse.Namespace:
    return argparse.Namespace(
        repo=str(repo), passphrase=TEST_PASSPHRASE,
        t=FAST_T, m=FAST_M, p=FAST_P, force=force,
    )


def _add_args(repo: Path, path: Path, relpath: str = None) -> argparse.Namespace:
    return argparse.Namespace(
        repo=str(repo), path=str(path),
        passphrase=TEST_PASSPHRASE, relpath=relpath,
    )


class TestMerkleRootStoredInVault:
    def test_init_stores_merkle_root(self, tmp_path: Path):
        cmd_init(_init_args(tmp_path))
        inner, kmaster, _ = unlock(tmp_path, TEST_PASSPHRASE)
        kmaster.wipe()
        assert inner.merkle_root is not None

    def test_init_empty_vault_root_is_zero_hash(self, tmp_path: Path):
        cmd_init(_init_args(tmp_path))
        inner, kmaster, _ = unlock(tmp_path, TEST_PASSPHRASE)
        kmaster.wipe()
        stored = base64.b64decode(inner.merkle_root)
        assert stored == b"\x00" * 32

    def test_add_updates_merkle_root(self, tmp_vault: Path, sample_file: Path):
        inner_before, km, _ = unlock(tmp_vault, TEST_PASSPHRASE)
        km.wipe()
        root_before = inner_before.merkle_root

        cmd_add(_add_args(tmp_vault, sample_file))

        inner_after, km2, _ = unlock(tmp_vault, TEST_PASSPHRASE)
        km2.wipe()
        assert inner_after.merkle_root != root_before

    def test_add_multiple_files_updates_merkle_root(self, tmp_vault: Path, tmp_path: Path):
        roots = []
        for i in range(3):
            f = tmp_path / f"file{i}.txt"
            f.write_bytes(f"content {i}".encode())
            cmd_add(_add_args(tmp_vault, f))
            inner, km, _ = unlock(tmp_vault, TEST_PASSPHRASE)
            km.wipe()
            roots.append(inner.merkle_root)
        # Each addition should produce a different root
        assert len(set(roots)) == 3

    def test_merkle_root_matches_computed(self, tmp_vault: Path, sample_file: Path):
        cmd_add(_add_args(tmp_vault, sample_file))
        inner, km, _ = unlock(tmp_vault, TEST_PASSPHRASE)
        km.wipe()
        computed = compute_vault_merkle_root(tmp_vault, inner.files)
        stored = base64.b64decode(inner.merkle_root)
        assert computed == stored


class TestVerifyVaultIntegrity:
    def test_verify_passes_clean_vault(self, tmp_vault: Path, sample_file: Path):
        cmd_add(_add_args(tmp_vault, sample_file))
        inner, km, _ = unlock(tmp_vault, TEST_PASSPHRASE)
        km.wipe()
        verify_vault_integrity(tmp_vault, inner)  # should not raise

    def test_verify_empty_vault_passes(self, tmp_vault: Path):
        inner, km, _ = unlock(tmp_vault, TEST_PASSPHRASE)
        km.wipe()
        verify_vault_integrity(tmp_vault, inner)  # empty vault has zero root stored

    def test_verify_fails_no_merkle_root(self, tmp_vault: Path, sample_file: Path):
        cmd_add(_add_args(tmp_vault, sample_file))
        inner, km, _ = unlock(tmp_vault, TEST_PASSPHRASE)
        km.wipe()
        inner.merkle_root = None
        with pytest.raises(ValueError, match="no Merkle root"):
            verify_vault_integrity(tmp_vault, inner)

    def test_verify_fails_tampered_blob(self, tmp_vault: Path, sample_file: Path):
        cmd_add(_add_args(tmp_vault, sample_file))
        inner, km, _ = unlock(tmp_vault, TEST_PASSPHRASE)
        km.wipe()

        # Tamper with the blob file directly
        blob_path = tmp_vault / inner.files[0]["blob"]
        data = bytearray(blob_path.read_bytes())
        data[0] ^= 0xFF
        blob_path.write_bytes(bytes(data))

        with pytest.raises(ValueError, match="Merkle root mismatch"):
            verify_vault_integrity(tmp_vault, inner)

    def test_verify_fails_wrong_stored_root(self, tmp_vault: Path, sample_file: Path):
        cmd_add(_add_args(tmp_vault, sample_file))
        inner, km, _ = unlock(tmp_vault, TEST_PASSPHRASE)
        km.wipe()
        # Replace stored root with garbage
        inner.merkle_root = base64.b64encode(b"\xff" * 32).decode()
        with pytest.raises(ValueError, match="Merkle root mismatch"):
            verify_vault_integrity(tmp_vault, inner)


class TestCmdVerify:
    def _verify_args(self, repo: Path) -> argparse.Namespace:
        return argparse.Namespace(repo=str(repo), passphrase=TEST_PASSPHRASE)

    def test_cmd_verify_clean_vault(self, tmp_vault: Path, sample_file: Path, capsys):
        cmd_add(_add_args(tmp_vault, sample_file))
        cmd_verify(self._verify_args(tmp_vault))
        captured = capsys.readouterr()
        assert "verified" in captured.out.lower()

    def test_cmd_verify_empty_vault(self, tmp_vault: Path, capsys):
        cmd_verify(self._verify_args(tmp_vault))
        captured = capsys.readouterr()
        assert "verified" in captured.out.lower()

    def test_cmd_verify_wrong_passphrase_raises(self, tmp_vault: Path):
        args = argparse.Namespace(repo=str(tmp_vault), passphrase="WRONG")
        with pytest.raises(Exception):
            cmd_verify(args)
