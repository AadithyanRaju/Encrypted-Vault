"""Dialog components for the GUI application."""
import argparse
from pathlib import Path

try:
    from PyQt6 import QtWidgets
except ImportError:
    pass


def show_startup_dialog(parent_window):
    """Show dialog to create new repo or select existing one.
    
    Args:
        parent_window: The parent VaultApp window
        
    Returns:
        None (modifies parent_window.repo if successful)
    """
    dlg = QtWidgets.QDialog(parent_window)
    dlg.setWindowTitle("EFS - Welcome")
    dlg.setModal(True)
    dlg.resize(400, 200)
    
    layout = QtWidgets.QVBoxLayout(dlg)
    
    # Welcome message
    welcome_label = QtWidgets.QLabel("Welcome to EFS - Encrypted File System")
    welcome_label.setStyleSheet("font-size: 16px; font-weight: bold; margin: 10px;")
    layout.addWidget(welcome_label)
    
    instruction_label = QtWidgets.QLabel("Choose an option:")
    instruction_label.setStyleSheet("margin: 10px;")
    layout.addWidget(instruction_label)
    
    # Buttons
    create_btn = QtWidgets.QPushButton("Create a new vault")
    create_btn.setMinimumHeight(40)
    create_btn.clicked.connect(lambda: create_new_repo(parent_window, dlg))
    layout.addWidget(create_btn)
    
    select_btn = QtWidgets.QPushButton("Select an existing vault")
    select_btn.setMinimumHeight(40)
    select_btn.clicked.connect(lambda: select_existing_repo(parent_window, dlg))
    layout.addWidget(select_btn)
    
    # Show dialog
    dlg.exec()


def create_new_repo(parent_window, parent_dialog):
    """Create a new repository.
    
    Args:
        parent_window: The parent VaultApp window
        parent_dialog: The startup dialog to close on success
    """
    # Get directory for new repo
    dlg = QtWidgets.QFileDialog(parent_window)
    repo_dir = dlg.getExistingDirectory(parent_window, "Select directory for new repository")
    if not repo_dir:
        return
    
    repo_path = Path(repo_dir)
    
    # Get passphrase for new repo
    pass_dlg = QtWidgets.QDialog(parent_window)
    pass_dlg.setWindowTitle("Set Master Password")
    pass_dlg.setModal(True)
    pass_layout = QtWidgets.QVBoxLayout(pass_dlg)
    
    pass_layout.addWidget(QtWidgets.QLabel("Set master password for new repository:"))
    
    pass_edit = QtWidgets.QLineEdit()
    pass_edit.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
    pass_edit.setPlaceholderText("Master password")
    pass_layout.addWidget(pass_edit)
    
    confirm_edit = QtWidgets.QLineEdit()
    confirm_edit.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
    confirm_edit.setPlaceholderText("Confirm password")
    pass_layout.addWidget(confirm_edit)
    
    btns = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Ok | QtWidgets.QDialogButtonBox.StandardButton.Cancel)
    pass_layout.addWidget(btns)
    btns.accepted.connect(pass_dlg.accept)
    btns.rejected.connect(pass_dlg.reject)
    
    if pass_dlg.exec() != QtWidgets.QDialog.DialogCode.Accepted:
        return
    
    password = pass_edit.text()
    confirm = confirm_edit.text()
    
    if not password or password != confirm:
        parent_window.show_message("Passwords do not match or are empty", "warning")
        return
    
    try:
        # Initialize new repo
        from utils.core import cmd_init
        init_args = argparse.Namespace(
            repo=str(repo_path),
            passphrase=password,
            t=4, m=262144, p=2, force=False
        )
        cmd_init(init_args)
        
        # Set repo and show main window
        parent_window.repo = repo_path
        parent_window.pass_edit.setText(password)
        parent_dialog.close()
        parent_window.show()
        parent_window.unlock()
        
        parent_window.show_message(f"Created new repository at {repo_path}", "success")
        
    except Exception as e:
        parent_window.show_message(f"Failed to create repository: {str(e)}", "error")


def select_existing_repo(parent_window, parent_dialog):
    """Select an existing repository.
    
    Args:
        parent_window: The parent VaultApp window
        parent_dialog: The startup dialog to close on success
    """
    dlg = QtWidgets.QFileDialog(parent_window)
    repo_dir = dlg.getExistingDirectory(parent_window, "Select repository directory")
    if not repo_dir:
        return
    
    repo_path = Path(repo_dir)
    vault_file = repo_path / "vault.enc"
    
    if not vault_file.exists():
        parent_window.show_message("Selected directory does not contain a vault.enc file", "warning")
        return
    
    # Set repo and show main window
    parent_window.repo = repo_path
    parent_dialog.close()
    parent_window.show()


def show_change_master_password_dialog(parent_window):
    """Show dialog to change master password.
    
    Args:
        parent_window: The parent VaultApp window with repo, pass_edit attributes
        
    Returns:
        tuple: (current_password, new_password, confirmed) or (None, None, False) if cancelled
    """
    if not parent_window.repo:
        parent_window.show_message("Please select a repository first", "warning")
        return None, None, False
        
    dlg = QtWidgets.QDialog(parent_window)
    dlg.setWindowTitle("Change Master Password")
    v = QtWidgets.QVBoxLayout(dlg)

    current_edit = QtWidgets.QLineEdit()
    current_edit.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
    current_edit.setPlaceholderText("Current password")
    # Pre-fill with current if present
    current_edit.setText(parent_window.pass_edit.text())

    new_edit = QtWidgets.QLineEdit()
    new_edit.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
    new_edit.setPlaceholderText("New password")

    confirm_edit = QtWidgets.QLineEdit()
    confirm_edit.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
    confirm_edit.setPlaceholderText("Confirm new password")

    v.addWidget(QtWidgets.QLabel("Enter your passwords:"))
    v.addWidget(current_edit)
    v.addWidget(new_edit)
    v.addWidget(confirm_edit)

    btns = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Ok | QtWidgets.QDialogButtonBox.StandardButton.Cancel)
    v.addWidget(btns)
    btns.accepted.connect(dlg.accept)
    btns.rejected.connect(dlg.reject)

    if dlg.exec() != QtWidgets.QDialog.DialogCode.Accepted:
        return None, None, False

    curr = current_edit.text()
    newp = new_edit.text()
    conf = confirm_edit.text()

    if not curr or not newp:
        parent_window.show_message("Please fill all fields", "warning")
        return None, None, False
    if newp != conf:
        parent_window.show_message("New passwords do not match", "warning")
        return None, None, False

    return curr, newp, True
