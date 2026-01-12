"""Vault operations for the GUI application."""
import argparse
import sys

try:
    from PyQt6 import QtWidgets
except ImportError:
    pass

from cryptography.exceptions import InvalidTag
from utils.core import unlock, update_file_in_vault
from utils.maintain import cmd_rotate_master


def unlock_vault(parent_window, repo, passphrase, populate_callback):
    """Unlock the vault with the given passphrase.
    
    Args:
        parent_window: Parent window for dialogs and UI updates
        repo: Repository path
        passphrase: Master passphrase
        populate_callback: Function to call to populate the tree
        
    Returns:
        tuple: (inner_metadata, kmaster) on success, (None, None) on failure
    """
    if not passphrase:
        QtWidgets.QMessageBox.warning(parent_window, "Empty Passphrase", "Please enter a passphrase")
        return None, None
    
    try:
        inner, kmaster, _ = unlock(repo, passphrase)
        
        # Update UI to show vault is unlocked
        parent_window.inner = inner
        parent_window.kmaster = kmaster
        
        # Hide passphrase input, show lock button
        parent_window.pass_edit.setVisible(False)
        parent_window.open_vault_btn.setVisible(False)
        parent_window.lock_btn.setVisible(True)
        
        # Enable controls
        parent_window.add_btn.setEnabled(True)
        parent_window.add_folder_btn.setEnabled(True)
        parent_window.save_btn.setEnabled(True)
        parent_window.open_btn.setEnabled(True)
        parent_window.remove_btn.setEnabled(True)
        parent_window.rotate_btn.setEnabled(True)
        parent_window.select_all_btn.setEnabled(True)
        parent_window.deselect_all_btn.setEnabled(True)
        parent_window.search_edit.setEnabled(True)
        
        populate_callback()
        return inner, kmaster
        
    except InvalidTag:
        QtWidgets.QMessageBox.critical(parent_window, "Authentication Failed", "Invalid passphrase or corrupted vault")
        return None, None
    except Exception as e:
        QtWidgets.QMessageBox.critical(parent_window, "Error", f"Failed to unlock vault: {str(e)}")
        return None, None


def lock_vault(parent_window):
    """Lock the currently opened repository but keep the repo selected (allow re-unlock).
    
    Args:
        parent_window: Parent window with UI elements to update
    """
    # Clear unlocked state but keep repo path
    parent_window.inner = None
    parent_window.kmaster = None
    parent_window.current_editor = None
    parent_window.current_file_id = None
    parent_window.tree.clear()

    # Disable controls that require unlock
    for btn in (
        parent_window.save_btn, parent_window.add_btn, parent_window.add_folder_btn, parent_window.open_btn,
        parent_window.remove_btn, parent_window.rotate_btn, parent_window.select_all_btn, parent_window.deselect_all_btn,
    ):
        try:
            btn.setEnabled(False)
        except Exception:
            pass
    
    # Disable and clear search field
    try:
        parent_window.search_edit.setEnabled(False)
        parent_window.search_edit.clear()
    except Exception:
        pass

    # Show passphrase UI again and hide lock button
    try:
        parent_window.pass_edit.clear()
        parent_window.pass_edit.setVisible(True)
        parent_window.open_vault_btn.setVisible(True)
    except Exception:
        pass
    parent_window.lock_btn.setVisible(False)
    parent_window.pass_edit.setFocus()


def close_repository(parent_window):
    """Close the currently opened repository and clear UI state.
    
    Args:
        parent_window: Parent window with UI elements and repo state
        
    Returns:
        bool: True if repo was closed, False if cancelled
    """
    if not parent_window.repo:
        return False
        
    reply = QtWidgets.QMessageBox.question(
        parent_window,
        "Close Repository",
        "Close the current repository and clear unlocked state?",
        QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
        QtWidgets.QMessageBox.StandardButton.No,
    )
    if reply != QtWidgets.QMessageBox.StandardButton.Yes:
        return False

    # Clear internal state
    parent_window.repo = None
    parent_window.inner = None
    parent_window.kmaster = None
    parent_window.current_editor = None
    parent_window.current_file_id = None
    parent_window.tree.clear()
    parent_window.pass_edit.clear()

    # Disable controls
    for btn in (
        parent_window.save_btn, parent_window.add_btn, parent_window.add_folder_btn, parent_window.open_btn,
        parent_window.remove_btn, parent_window.rotate_btn, parent_window.select_all_btn, parent_window.deselect_all_btn,
        parent_window.close_btn,
    ):
        try:
            btn.setEnabled(False)
        except Exception:
            pass
    
    # Disable and clear search field
    try:
        parent_window.search_edit.setEnabled(False)
        parent_window.search_edit.clear()
    except Exception:
        pass

    try:
        parent_window.hide()
        # Import here to avoid circular import
        from ui.gui.dialogs import show_startup_dialog
        show_startup_dialog(parent_window)
        if parent_window.repo:
            parent_window.show()
        else:
            sys.exit(0)
    except Exception:
        pass
    
    return True


def change_master_password(parent_window, repo, current_password, new_password, unlock_callback):
    """Change the master password for the repository.
    
    Args:
        parent_window: Parent window for dialogs
        repo: Repository path
        current_password: Current master password
        new_password: New master password
        unlock_callback: Function to call to unlock with new password
        
    Returns:
        bool: True on success, False on failure
    """
    try:
        args = argparse.Namespace(repo=str(repo), passphrase=current_password, new_passphrase=new_password, t=None, m=None, p=None)
        cmd_rotate_master(args)
        # Update UI to use new password and re-unlock
        parent_window.pass_edit.setText(new_password)
        unlock_callback()
        QtWidgets.QMessageBox.information(parent_window, "Success", "Master password changed.")
        return True
    except Exception as e:
        QtWidgets.QMessageBox.critical(parent_window, "Error", f"Failed to change password: {str(e)}")
        return False


def save_text_file_to_vault(parent_window, repo, file_id, content, passphrase, populate_callback):
    """Save updated text file content to the vault.
    
    Args:
        parent_window: Parent window for dialogs
        repo: Repository path
        file_id: ID of the file in the vault
        content: New content for the file
        passphrase: Master passphrase
        populate_callback: Function to refresh the file list
        
    Returns:
        tuple: (inner_metadata, kmaster) on success, (None, None) on failure
    """
    try:
        # Update the file in the vault
        update_file_in_vault(repo, file_id, content.encode('utf-8'), passphrase)
        
        # Refresh the table to show updated file size
        inner, kmaster, _ = unlock(repo, passphrase)
        populate_callback()
        
        QtWidgets.QMessageBox.information(parent_window, "Success", "File updated in vault successfully!")
        return inner, kmaster
    except Exception as e:
        QtWidgets.QMessageBox.critical(parent_window, "Error", f"Failed to update file in vault: {str(e)}")
        return None, None
