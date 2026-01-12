# Encrypted Vault

A secure, user-friendly file encryption tool with both command-line and graphical interfaces. Protect your sensitive files with military-grade encryption using AES-256-GCM and Argon2id key derivation.

## 🔒 Features

- **Strong Encryption**: AES-256-GCM authenticated encryption with per-file random keys
- **Secure Key Derivation**: Argon2id algorithm with SHA3-512 pre-hashing for master key derivation
- **Dual Interface**: Full-featured GUI (PyQt6) and powerful CLI for scripting
- **GitHub-Friendly Storage**: Binary vault format with opaque metadata - no readable headers
- **File Management**: Add, extract, rename, and remove encrypted files with ease
- **Folder Support**: Preserve directory structure when adding entire folders
- **Built-in Viewers**: View images, PDFs, videos, audio, and text files directly from the vault
- **Master Key Rotation**: Change passphrase and Argon2 parameters without re-encrypting files
- **Portable**: Package as standalone executable using PyInstaller

## 📋 Prerequisites

- **Python**: 3.8 or higher
- **pip**: Python package manager
- **virtualenv** (recommended): For isolated Python environment

## 🚀 Installation

### 1. Clone the Repository

```bash
git clone https://github.com/AadithyanRaju/Encrypted-Vault.git
cd Encrypted-Vault
```

### 2. Create Virtual Environment (Recommended)

**Linux/macOS:**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

**Windows (PowerShell):**
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

**Windows (CMD):**
```cmd
python -m venv .venv
.venv\Scripts\activate.bat
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

**Dependencies include:**
- `cryptography>=41.0.0` - Cryptographic primitives
- `PyQt6>=6.5.0` - GUI framework
- `PyQt6-WebEngine>=6.5.0` - PDF viewing support
- `pycryptodome>=3.18.0` - Additional crypto utilities
- `argon2-cffi>=25.1.0` - Argon2 key derivation
- `Pillow>=12.1.0` - Image processing
- `pyinstaller` - Executable packaging

## 💻 Usage

### GUI Mode (Graphical Interface)

**Launch GUI without specifying vault:**
```bash
python src/efs.py gui
```

**Launch GUI with vault path:**
```bash
python src/efs.py gui /path/to/vault
```

**GUI Features:**
- 🔓 Unlock/lock vault with master passphrase
- ➕ Add individual files or entire folders
- 📂 Browse files in tree view with search/filter
- 👁️ Preview images, PDFs, videos, audio, and text files
- 💾 Extract files individually or in bulk
- ✏️ Rename and delete files
- 🔑 Change master password

### CLI Mode (Command Line)

#### Initialize a New Vault
```bash
python src/efs.py init /path/to/vault --passphrase "your-secure-passphrase"
```

**With custom Argon2 parameters:**
```bash
python src/efs.py init /path/to/vault --passphrase "your-passphrase" -t 8 -m 524288 -p 4
```

- `-t`: Time cost (iterations), default: 4
- `-m`: Memory cost in KiB, default: 262144 (256 MiB)
- `-p`: Parallelism, default: 2

#### Add Files
```bash
# Add a single file
python src/efs.py add /path/to/vault /path/to/file.txt --passphrase "your-passphrase"

# Preserve folder structure
python src/efs.py add /path/to/vault /path/to/file.txt --relpath "documents/file.txt" --passphrase "your-passphrase"
```

#### List Files
```bash
python src/efs.py ls /path/to/vault --passphrase "your-passphrase"
```

#### Extract Files
```bash
python src/efs.py extract /path/to/vault <file-id> /output/path.txt --passphrase "your-passphrase"
```

#### Remove Files
```bash
python src/efs.py rm /path/to/vault <file-id> --passphrase "your-passphrase"
```

#### Rename Files
```bash
python src/efs.py rename /path/to/vault <file-id> "new-name.txt" --passphrase "your-passphrase"
```

#### Rotate Master Key
```bash
# Change passphrase only
python src/efs.py rotate-master /path/to/vault --passphrase "old-passphrase" --new-passphrase "new-passphrase"

# Change passphrase and Argon2 parameters
python src/efs.py rotate-master /path/to/vault --passphrase "old-passphrase" --new-passphrase "new-passphrase" -t 8 -m 524288 -p 4
```

## 📁 Project Structure

```
Encrypted-Vault/
├── src/
│   ├── efs.py                      # Main entry point
│   ├── crypto/
│   │   ├── aead.py                 # AES-256-GCM encryption/decryption
│   │   └── hash.py                 # SHA3-512 and Argon2id key derivation
│   ├── storage/
│   │   └── vault.py                # Binary vault file operations
│   ├── utils/
│   │   ├── core.py                 # Core commands (init, add, ls, extract)
│   │   ├── maintain.py             # Maintenance commands (rename, rm, rotate)
│   │   ├── dataModels.py           # Data structures and constants
│   │   └── helper.py               # Helper utilities
│   └── ui/
│       ├── cli.py                  # CLI argument parser
│       ├── gui.py                  # Main GUI application
│       ├── gui_components/         # Modular GUI components
│       │   ├── dialogs.py          # Dialog windows
│       │   ├── file_operations.py  # File add/extract/remove
│       │   ├── tree_operations.py  # Tree view operations
│       │   └── vault_operations.py # Vault unlock/lock/password change
│       ├── ImageViewer.py          # Image preview widget
│       ├── PDFViewer.py            # PDF preview widget
│       ├── VideoPlayer.py          # Video player widget
│       ├── AudioPlayer.py          # Audio player widget
│       └── TextEditor.py           # Text file viewer/editor
├── requirements.txt                # Python dependencies
├── LICENSE                         # MIT License
├── icon.ico                        # Application icon
└── vault.exe.spec                  # PyInstaller specification
```

## 🔐 Vault Structure

When you create a vault, the following structure is generated:

```
vault/
├── vault.enc                       # Binary encrypted metadata
└── blobs/
    ├── <uuid-1>.bin                # Encrypted file blob (nonce + ciphertext)
    ├── <uuid-2>.bin
    └── ...
```

**Binary Vault Header Format:**
```
Magic:       4 bytes  - "EFS1"
Version:     1 byte   - 0x01
T-Cost:      4 bytes  - Argon2 time cost
M-Cost:      4 bytes  - Argon2 memory cost (KiB)
Parallelism: 4 bytes  - Argon2 parallelism
Salt:        16 bytes - Random salt for key derivation
Nonce:       12 bytes - AEAD nonce
Ciphertext:  Remaining bytes - Encrypted metadata
```

## 🛡️ Security Considerations

### Encryption Details

- **Algorithm**: AES-256-GCM (Authenticated Encryption with Associated Data)
- **Key Derivation**: Argon2id with SHA3-512 pre-hashing
- **Per-file Encryption**: Each file uses a unique random 256-bit key
- **Key Wrapping**: File keys are encrypted with the master key
- **Nonce**: 96-bit random nonce per encryption operation

### Important Security Notes

⚠️ **Critical Warnings:**

1. **Passphrase Loss**: If you lose your passphrase, your data is **permanently unrecoverable**. There is no backdoor or recovery mechanism.

2. **Backup Your Passphrase**: Store your passphrase securely (e.g., password manager, encrypted backup).

3. **Not a Replacement**: This tool does **not** replace:
   - Full-disk encryption (BitLocker, FileVault, LUKS)
   - Operating system security
   - Enterprise key management systems
   - Network security measures

4. **Secure Storage**: 
   - Never commit passphrases or unencrypted secrets to version control
   - Set appropriate filesystem permissions on vault directories
   - Store vault.enc and blobs/ securely

5. **Threat Model**: This tool protects files **at rest**. It does not protect:
   - Files while unlocked in memory
   - Against malware running on your system
   - Against physical access to an unlocked vault
   - Network transmission (use HTTPS/SSH for transfers)

6. **Dependency Updates**: Keep dependencies up to date to patch security vulnerabilities.

### Best Practices

- Use a strong, unique passphrase (20+ characters, mixed case, numbers, symbols)
- Enable full-disk encryption on your system
- Keep your operating system and software updated
- Use higher Argon2 parameters on powerful machines for better security
- Regularly backup your encrypted vault to multiple locations

## 📦 Building Standalone Executable

Create a portable executable that doesn't require Python installation:

```bash
pyinstaller vault.exe.spec
```

The executable will be created in the `dist/` directory. You can distribute `vault.exe` as a standalone application.

## 🤝 Contributing

Contributions are welcome! Please follow these guidelines:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes with clear, minimal modifications
4. Test your changes thoroughly
5. Commit with descriptive messages
6. Push to your branch
7. Open a Pull Request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

**Copyright (c) 2025 Aadithyan Raju**

## 🙏 Acknowledgments

- Built with [cryptography](https://cryptography.io/) library
- GUI powered by [PyQt6](https://www.riverbankcomputing.com/software/pyqt/)
- Key derivation using [argon2-cffi](https://github.com/hynek/argon2-cffi)

## ⚠️ Disclaimer

This software is provided "as is" without warranty of any kind. Use at your own risk. The authors are not responsible for data loss, security breaches, or any other damages resulting from the use of this software. Always maintain backups of important data.
