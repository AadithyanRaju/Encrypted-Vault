"""Shared pytest fixtures for the Encrypted-Vault test suite."""
import os
import sys
import pytest

from pathlib import Path

# Add tests directory to sys.path so helper modules can be imported
sys.path.insert(0, str(Path(__file__).parent))

from test_constants import FAST_T, FAST_M, FAST_P, TEST_PASSPHRASE


@pytest.fixture()
def tmp_vault(tmp_path: Path) -> Path:
    """Return a Path pointing to a freshly initialised vault directory."""
    from utils.core import cmd_init
    import argparse

    args = argparse.Namespace(
        repo=str(tmp_path),
        passphrase=TEST_PASSPHRASE,
        t=FAST_T,
        m=FAST_M,
        p=FAST_P,
        force=False,
    )
    cmd_init(args)
    return tmp_path


@pytest.fixture()
def sample_file(tmp_path: Path) -> Path:
    """A small plaintext file to encrypt."""
    f = tmp_path / "hello.txt"
    f.write_bytes(b"Hello, Encrypted Vault!")
    return f


@pytest.fixture()
def binary_file(tmp_path: Path) -> Path:
    """A binary file with 256 bytes (0x00–0xFF)."""
    f = tmp_path / "binary.bin"
    f.write_bytes(bytes(range(256)))
    return f
