import argparse

from ui.gui import cmd_gui
from utils.core import cmd_add, cmd_ls, cmd_extract, cmd_init
from utils.dataModels import DEFAULT_T_COST, DEFAULT_M_COST_KiB, DEFAULT_PARALLELISM
from utils.maintain import cmd_rename, cmd_rm, cmd_rotate_master
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Encrypted File System (GitHub-ready, opaque vault)")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_init = sub.add_parser("init", help="Initialize vault")
    p_init.add_argument("repo", help="Path to repo directory")
    p_init.add_argument("--passphrase", required=True)
    p_init.add_argument("-t", type=int, default=DEFAULT_T_COST, help="Argon2 time cost (iterations)")
    p_init.add_argument("-m", type=int, default=DEFAULT_M_COST_KiB, help="Argon2 memory (KiB)")
    p_init.add_argument("-p", type=int, default=DEFAULT_PARALLELISM, help="Argon2 parallelism")
    p_init.add_argument("--force", action="store_true", help="Overwrite existing vault.enc if present")
    p_init.set_defaults(func=cmd_init)

    p_add = sub.add_parser("add", help="Add a file (encrypt)")
    p_add.add_argument("repo", help="Path to repo directory")
    p_add.add_argument("path", help="Plaintext file to add")
    p_add.add_argument("--passphrase", required=True)
    p_add.set_defaults(func=cmd_add)

    p_ls = sub.add_parser("ls", help="List files (after unlock)")
    p_ls.add_argument("repo", help="Path to repo directory")
    p_ls.add_argument("--passphrase", required=True)
    p_ls.set_defaults(func=cmd_ls)

    p_ext = sub.add_parser("extract", help="Decrypt a file by id")
    p_ext.add_argument("repo", help="Path to repo directory")
    p_ext.add_argument("id", help="File id (UUID)")
    p_ext.add_argument("out", help="Output plaintext path")
    p_ext.add_argument("--passphrase", required=True)
    p_ext.set_defaults(func=cmd_extract)

    p_rm = sub.add_parser("rm", help="Remove a file by id")
    p_rm.add_argument("repo", help="Path to repo directory")
    p_rm.add_argument("id", help="File id (UUID)")
    p_rm.add_argument("--passphrase", required=True)
    p_rm.set_defaults(func=cmd_rm)

    p_ren = sub.add_parser("rename", help="Rename a file entry")
    p_ren.add_argument("repo", help="Path to repo directory")
    p_ren.add_argument("id", help="File id (UUID)")
    p_ren.add_argument("name", help="New name")
    p_ren.add_argument("--passphrase", required=True)
    p_ren.set_defaults(func=cmd_rename)

    p_rot = sub.add_parser("rotate-master", help="Rotate/Change master key and/or Argon2 params")
    p_rot.add_argument("repo", help="Path to repo directory")
    p_rot.add_argument("--passphrase", required=True, help="Current passphrase")
    p_rot.add_argument("--new-passphrase", help="New passphrase (default: reuse current)")
    p_rot.add_argument("-t", type=int, help="New Argon2 time cost (iterations)")
    p_rot.add_argument("-m", type=int, help="New Argon2 memory (KiB)")
    p_rot.add_argument("-p", type=int, help="New Argon2 parallelism")
    p_rot.set_defaults(func=cmd_rotate_master)

    p_gui = sub.add_parser("gui", help="Launch minimal GUI")
    p_gui.add_argument("repo", help="Path to repo directory")
    p_gui.set_defaults(func=cmd_gui)

    return p

