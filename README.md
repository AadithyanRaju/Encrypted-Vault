# Encrypted Vault

## Abstract
Encrypted Vault is a small tool to encrypt and decrypt files and folders using a simple, auditable interface (CLI + GUI). It is intended for protecting sensitive files at rest with user-controlled keys and does not replace full-disk encryption or enterprise key management.

## Requirements
- Python 3.8+
- pip
- (Recommended) virtualenv or venv
- See requirements.txt for Python package dependencies (cryptography, optionally a GUI toolkit)

## Setup
```bash
# clone the repository
git clone https://github.com/AadithyanRaju/Encrypted-Vault.git
cd encrypted-vault

# create and activate a virtual environment
python3 -m venv .venv
# macOS / Linux
source .venv/bin/activate
# Windows (PowerShell)
# .venv\Scripts\Activate.ps1

# install dependencies
pip install -r requirements.txt

# run the GUI
python3 ./src/efi.py gui
    
```

## File Structure
- README (this file)
- requirements.txt
- src/
    - efi.py        — entry point (CLI / GUI launcher)

## Usage
- Initialize a vault or key material before encrypting data.
- Use the CLI for scripting and the GUI for interactive workflows.

## Security
- This tool uses application-level symmetric encryption. Protect and back up your keys or passphrases; losing them means irreversible data loss.
- Do not commit keys, passphrases, or unencrypted secrets to version control.
- Ensure filesystem permissions restrict access to vault files and key material.
- Review and understand the threat model in docs/threat-model.md — this tool is not a substitute for disk encryption, secure OS configuration, or enterprise key management.
- Keep dependencies up to date and run tests to validate behavior after upgrades.
