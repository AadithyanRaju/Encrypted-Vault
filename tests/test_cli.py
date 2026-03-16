"""Integration tests for the CLI parser and command dispatch."""
import argparse
import sys
import types
import pytest

from pathlib import Path
from io import StringIO
from unittest.mock import patch, MagicMock

# ---------------------------------------------------------------------------
# Mock PyQt6 and the GUI module before any vault imports trigger them.
# This allows CLI tests to run in environments without a display or PyQt6.
# ---------------------------------------------------------------------------
_gui_mock = MagicMock()
sys.modules.setdefault("PyQt6", MagicMock())
sys.modules.setdefault("PyQt6.QtWidgets", MagicMock())
sys.modules.setdefault("PyQt6.QtCore", MagicMock())
sys.modules.setdefault("PyQt6.QtGui", MagicMock())
sys.modules.setdefault("ui.gui", _gui_mock)
sys.modules.setdefault("ui.gui_components", MagicMock())
sys.modules.setdefault("ui.gui_components.dialogs", MagicMock())
sys.modules.setdefault("ui.gui_components.tree_operations", MagicMock())
sys.modules.setdefault("ui.gui_components.file_operations", MagicMock())
sys.modules.setdefault("ui.gui_components.vault_operations", MagicMock())

from test_constants import FAST_T, FAST_M, FAST_P, TEST_PASSPHRASE
from ui.cli import build_parser
from utils.core import cmd_init, cmd_add, unlock


def _run_cli(argv: list[str], passphrase: str = TEST_PASSPHRASE) -> tuple[int, str]:
    """Run the CLI with the given argv and capture stdout, returning (exit_code, output)."""
    parser = build_parser()
    buf = StringIO()
    try:
        with patch("sys.stdout", buf), patch("getpass.getpass", return_value=passphrase):
            args = parser.parse_args(argv)
            args.func(args)
        return 0, buf.getvalue()
    except SystemExit as e:
        return int(e.code or 0), buf.getvalue()


class TestBuildParser:
    def test_parser_returns_argument_parser(self):
        parser = build_parser()
        assert isinstance(parser, argparse.ArgumentParser)

    def test_init_subcommand_parsed(self):
        parser = build_parser()
        args = parser.parse_args(["init", "/tmp/testvault"])
        assert args.cmd == "init"

    def test_add_subcommand_parsed(self):
        parser = build_parser()
        args = parser.parse_args(["add", "/tmp/v", "/tmp/f.txt"])
        assert args.cmd == "add"

    def test_ls_subcommand_parsed(self):
        parser = build_parser()
        args = parser.parse_args(["ls", "/tmp/v"])
        assert args.cmd == "ls"

    def test_extract_subcommand_parsed(self):
        parser = build_parser()
        args = parser.parse_args(["extract", "/tmp/v", "some-id", "/tmp/out"])
        assert args.cmd == "extract"
        assert args.id == "some-id"

    def test_rm_subcommand_parsed(self):
        parser = build_parser()
        args = parser.parse_args(["rm", "/tmp/v", "some-id"])
        assert args.cmd == "rm"

    def test_rename_subcommand_parsed(self):
        parser = build_parser()
        args = parser.parse_args(["rename", "/tmp/v", "some-id", "newname.txt"])
        assert args.cmd == "rename"
        assert args.name == "newname.txt"

    def test_rotate_master_subcommand_parsed(self):
        parser = build_parser()
        args = parser.parse_args(["rotate-master", "/tmp/v"])
        assert args.cmd == "rotate-master"

    def test_init_defaults(self):
        from utils.dataModels import DEFAULT_T_COST, DEFAULT_M_COST_KiB, DEFAULT_PARALLELISM
        parser = build_parser()
        args = parser.parse_args(["init", "/tmp/v"])
        assert args.t == DEFAULT_T_COST
        assert args.m == DEFAULT_M_COST_KiB
        assert args.p == DEFAULT_PARALLELISM

    def test_passphrase_argument_rejected(self):
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["init", "/tmp/v", "--passphrase", "pw"])

    def test_unknown_subcommand_exits(self):
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["nonexistent"])


class TestCliInitCommand:
    def test_cli_init_creates_vault(self, tmp_path: Path):
        code, out = _run_cli(["init", str(tmp_path),
                               "-t", str(FAST_T), "-m", str(FAST_M), "-p", str(FAST_P)])
        assert code == 0
        assert (tmp_path / "vault.enc").exists()

    def test_cli_init_prints_confirmation(self, tmp_path: Path):
        _, out = _run_cli(["init", str(tmp_path),
                            "-t", str(FAST_T), "-m", str(FAST_M), "-p", str(FAST_P)])
        assert "Initialized" in out or "[+]" in out

    def test_cli_init_twice_exits(self, tmp_path: Path):
        _run_cli(["init", str(tmp_path),
                  "-t", str(FAST_T), "-m", str(FAST_M), "-p", str(FAST_P)])
        code, _ = _run_cli(["init", str(tmp_path),
                             "-t", str(FAST_T), "-m", str(FAST_M), "-p", str(FAST_P)])
        assert code != 0


class TestCliAddAndLs:
    def test_cli_add_and_ls(self, tmp_vault: Path, sample_file: Path):
        code, out = _run_cli(["add", str(tmp_vault), str(sample_file)])
        assert code == 0
        assert sample_file.name in out or "[+]" in out

        code2, ls_out = _run_cli(["ls", str(tmp_vault)])
        assert code2 == 0
        assert sample_file.name in ls_out

    def test_cli_ls_empty_vault(self, tmp_vault: Path):
        code, out = _run_cli(["ls", str(tmp_vault)])
        assert code == 0
        assert "(empty)" in out


class TestCliExtract:
    def test_cli_extract(self, tmp_vault: Path, sample_file: Path, tmp_path: Path):
        _run_cli(["add", str(tmp_vault), str(sample_file)])
        inner, _, _ = unlock(tmp_vault, TEST_PASSPHRASE)
        fid = inner.files[0]["id"]
        out = tmp_path / "out.txt"
        code, _ = _run_cli(["extract", str(tmp_vault), fid, str(out)])
        assert code == 0
        assert out.read_bytes() == sample_file.read_bytes()


class TestCliRmAndRename:
    def test_cli_rm(self, tmp_vault: Path, sample_file: Path):
        _run_cli(["add", str(tmp_vault), str(sample_file)])
        inner, _, _ = unlock(tmp_vault, TEST_PASSPHRASE)
        fid = inner.files[0]["id"]
        code, out = _run_cli(["rm", str(tmp_vault), fid])
        assert code == 0
        inner2, _, _ = unlock(tmp_vault, TEST_PASSPHRASE)
        assert inner2.files == []

    def test_cli_rename(self, tmp_vault: Path, sample_file: Path):
        _run_cli(["add", str(tmp_vault), str(sample_file)])
        inner, _, _ = unlock(tmp_vault, TEST_PASSPHRASE)
        fid = inner.files[0]["id"]
        code, _ = _run_cli(["rename", str(tmp_vault), fid, "renamed.txt"])
        assert code == 0
        inner2, _, _ = unlock(tmp_vault, TEST_PASSPHRASE)
        assert inner2.files[0]["name"] == "renamed.txt"
