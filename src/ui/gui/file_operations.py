"""File operations for the GUI application."""
import argparse
import mimetypes
import os
import sys
import tempfile
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    from PyQt6 import QtWidgets, QtCore
except ImportError:
    pass

from utils.core import unlock, cmd_extract, cmd_add, update_file_in_vault, prepare_file_add
from crypto.aead import aead_encrypt
from storage.vault import save_vault
from utils.helper import repo_paths
from ui.ImageViewer import ImageViewer
from ui.TextEditor import TextEditor
from ui.PDFViewer import PDFViewer
from ui.VideoPlayer import VideoPlayer
from ui.AudioPlayer import AudioPlayer


def add_single_file(parent_window, repo, passphrase, populate_callback):
    """Add a single file to the vault.
    
    Args:
        parent_window: Parent window for dialogs
        repo: Repository path
        passphrase: Master passphrase
        populate_callback: Function to call to refresh the file list
        
    Returns:
        tuple: (inner_metadata, kmaster) on success, (None, None) on failure
    """
    if not repo:
        QtWidgets.QMessageBox.warning(parent_window, "No Repository", "Please select a repository first")
        return None, None
        
    dlg = QtWidgets.QFileDialog(parent_window)
    file_path, _ = dlg.getOpenFileName(parent_window, "Select file to add to vault")
    if not file_path:
        return None, None
    
    try:
        add_args = argparse.Namespace(
            repo=str(repo),
            path=file_path,
            passphrase=passphrase
        )
        cmd_add(add_args)
        
        inner, kmaster, _ = unlock(repo, passphrase)
        populate_callback()
        
        QtWidgets.QMessageBox.information(parent_window, "Success", f"Added {Path(file_path).name} to vault")
        return inner, kmaster
    except Exception as e:
        QtWidgets.QMessageBox.critical(parent_window, "Error", f"Failed to add file: {str(e)}")
        return None, None


def add_folder(parent_window, repo, passphrase, populate_callback):
    """Add a folder to the vault.
    
    Args:
        parent_window: Parent window for dialogs
        repo: Repository path
        passphrase: Master passphrase
        populate_callback: Function to call to refresh the file list
        
    Returns:
        tuple: (inner_metadata, kmaster) on success, (None, None) on failure
    """
    if not repo:
        QtWidgets.QMessageBox.warning(parent_window, "No Repository", "Please select a repository first")
        return None, None
        
    dlg = QtWidgets.QFileDialog(parent_window)
    folder_path = dlg.getExistingDirectory(parent_window, "Select folder to add to vault")
    if not folder_path:
        return None, None
    
    folder_path = Path(folder_path)
    if not folder_path.is_dir():
        QtWidgets.QMessageBox.warning(parent_window, "Invalid Selection", "Please select a valid folder")
        return None, None
    
    # Get all files in the folder recursively
    files_to_add = []
    for file_path in folder_path.rglob('*'):
        if file_path.is_file():
            # Calculate relative path from the selected folder
            rel_path = file_path.relative_to(folder_path)
            files_to_add.append((file_path, rel_path))
    
    if not files_to_add:
        QtWidgets.QMessageBox.information(parent_window, "Empty Folder", "The selected folder contains no files")
        return None, None
    
    # Confirm with user
    file_list = "\n".join([f"• {rel_path}" for file_path, rel_path in files_to_add[:10]])  # Show first 10
    if len(files_to_add) > 10:
        file_list += f"\n... and {len(files_to_add) - 10} more files"
    
    reply = QtWidgets.QMessageBox.question(
        parent_window,
        "Confirm Folder Addition",
        f"Add {len(files_to_add)} files from '{folder_path.name}' to vault?\n\n{file_list}",
        QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
        QtWidgets.QMessageBox.StandardButton.No
    )
    
    if reply == QtWidgets.QMessageBox.StandardButton.Yes:
        progress = None
        try:
            # Unlock once to get inner, kmaster, and KDF params
            inner, kmaster, kdf = unlock(repo, passphrase)

            success_entries = []
            failed_files = []

            # Progress dialog
            progress = QtWidgets.QProgressDialog("Adding files to vault...", "Cancel", 0, len(files_to_add), parent_window)
            progress.setWindowModality(QtCore.Qt.WindowModality.WindowModal)
            progress.setAutoClose(False)

            # Prepare tasks: (file_path, prefixed_rel)
            tasks = [(file_path, str(Path(folder_path.name) / rel_path)) for file_path, rel_path in files_to_add]

            # Thread pool equal to CPU cores
            max_workers = max(1, (os.cpu_count() or 1))
            completed = 0

            with ThreadPoolExecutor(max_workers=max_workers) as ex:
                future_map = {}
                for file_path, relp in tasks:
                    future = ex.submit(prepare_file_add, repo, Path(file_path), relp, kmaster)
                    future_map[future] = (file_path, relp)

                for fut in as_completed(future_map):
                    file_path, relp = future_map[fut]
                    progress.setLabelText(f"Adding: {relp}")
                    try:
                        entry = fut.result()
                        success_entries.append(entry)
                    except Exception as e:
                        failed_files.append((str(relp), str(e)))
                    completed += 1
                    progress.setValue(completed)
                    if progress.wasCanceled():
                        break

            # If canceled, do not write partial metadata changes (blobs already written remain orphaned)
            if progress.wasCanceled():
                progress.close()
                progress = None
                QtWidgets.QMessageBox.information(parent_window, "Canceled", "Folder add canceled. Some blobs may have been written.")
                return None, None
            else:
                # Merge entries and save vault once
                for entry in success_entries:
                    inner.files.append(entry.to_dict())
                inner_bytes = inner.to_bytes()
                new_nonce, new_ct = aead_encrypt(kmaster, inner_bytes)
                p = repo_paths(repo)
                save_vault(p["vault"], kdf["t"], kdf["m"], kdf["p"], kdf["salt"], new_nonce, new_ct)

                # Refresh UI state
                inner, kmaster, _ = unlock(repo, passphrase)
                populate_callback()

                # Close progress dialog before showing result
                progress.close()
                progress = None

                # Show results
                success_count = len(success_entries)
                if failed_files:
                    error_msg = f"Successfully added {success_count} files.\n\nFailed to add {len(failed_files)} files:\n"
                    error_msg += "\n".join([f"• {name}: {error}" for name, error in failed_files[:5]])
                    if len(failed_files) > 5:
                        error_msg += f"\n... and {len(failed_files) - 5} more failures"
                    QtWidgets.QMessageBox.warning(parent_window, "Partial Success", error_msg)
                else:
                    QtWidgets.QMessageBox.information(parent_window, "Success", f"Added {success_count} files from '{folder_path.name}' to vault")
                
                return inner, kmaster

        except Exception as e:
            if progress:
                progress.close()
                progress = None
            QtWidgets.QMessageBox.critical(parent_window, "Error", f"Failed to add folder: {str(e)}")
            return None, None
    
    return None, None


def remove_selected_files(parent_window, repo, passphrase, selected_files, populate_callback):
    """Remove selected files from the vault.
    
    Args:
        parent_window: Parent window for dialogs
        repo: Repository path
        passphrase: Master passphrase
        selected_files: List of (file_id, name, relpath) tuples
        populate_callback: Function to call to refresh the file list
        
    Returns:
        tuple: (inner_metadata, kmaster) on success, (None, None) on failure
    """
    if not repo:
        QtWidgets.QMessageBox.warning(parent_window, "No Repository", "Please select a repository first")
        return None, None
        
    if not selected_files:
        QtWidgets.QMessageBox.warning(parent_window, "No Selection", "Please select files to remove")
        return None, None
    
    # Confirm deletion
    file_list = "\n".join([f"• {name}" for fid, name, _ in selected_files])
    reply = QtWidgets.QMessageBox.question(
        parent_window,
        "Confirm Deletion",
        f"Are you sure you want to remove {len(selected_files)} file(s) from the vault?\n\n{file_list}\n\nThis action cannot be undone.",
        QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
        QtWidgets.QMessageBox.StandardButton.No
    )
    
    if reply == QtWidgets.QMessageBox.StandardButton.Yes:
        try:
            # Unlock once and build id->entry map
            inner, kmaster, kdf = unlock(repo, passphrase)
            id_to_entry = {f["id"]: f for f in inner.files}

            # Prepare tasks for parallel blob deletion
            targets = []  # (fid, blob_path)
            for fid, name, _ in selected_files:
                entry = id_to_entry.get(fid)
                if entry:
                    blob_path = Path(repo) / entry.get("blob", "")
                    targets.append((fid, blob_path))

            if not targets:
                QtWidgets.QMessageBox.warning(parent_window, "No Matches", "Selected items not found in vault metadata")
                return None, None

            # Progress dialog
            progress = QtWidgets.QProgressDialog("Removing files from vault...", None, 0, len(targets), parent_window)
            progress.setWindowModality(QtCore.Qt.WindowModality.WindowModal)
            progress.setAutoClose(True)

            # Thread pool sized to CPU cores
            max_workers = max(1, (os.cpu_count() or 1))
            completed = 0
            success_ids = []
            failed = []  # (fid, error)

            def _unlink_blob(path: Path):
                try:
                    path.unlink()
                except FileNotFoundError:
                    # Treat missing blob as success for metadata cleanup
                    return
                except Exception as e:
                    raise e

            with ThreadPoolExecutor(max_workers=max_workers) as ex:
                future_map = {}
                for fid, blob_path in targets:
                    future = ex.submit(_unlink_blob, blob_path)
                    future_map[future] = (fid, blob_path)

                for fut in as_completed(future_map):
                    fid, blob_path = future_map[fut]
                    progress.setLabelText(f"Removing: {id_to_entry.get(fid, {}).get('name', fid)}")
                    try:
                        fut.result()
                        success_ids.append(fid)
                    except Exception as e:
                        failed.append((fid, str(e)))
                    completed += 1
                    progress.setValue(completed)

            # Update metadata once for all successful deletions
            if success_ids:
                remaining = [f for f in inner.files if f["id"] not in success_ids]
                inner.files = remaining
                inner_bytes = inner.to_bytes()
                new_nonce, new_ct = aead_encrypt(kmaster, inner_bytes)
                p = repo_paths(repo)
                save_vault(p["vault"], kdf["t"], kdf["m"], kdf["p"], kdf["salt"], new_nonce, new_ct)

            # Refresh UI
            inner, kmaster, _ = unlock(repo, passphrase)
            populate_callback()

            # Report outcome
            if failed:
                msg = f"Removed {len(success_ids)} file(s).\n\nFailed to remove {len(failed)}:"
                # show up to 5 failures
                for fid, err in failed[:5]:
                    name = id_to_entry.get(fid, {}).get("name", fid)
                    msg += f"\n• {name}: {err}"
                if len(failed) > 5:
                    msg += f"\n... and {len(failed) - 5} more"
                QtWidgets.QMessageBox.warning(parent_window, "Partial Success", msg)
            else:
                QtWidgets.QMessageBox.information(parent_window, "Success", f"Removed {len(success_ids)} file(s) from vault")
            
            return inner, kmaster
        except Exception as e:
            QtWidgets.QMessageBox.critical(parent_window, "Error", f"Failed to remove files: {str(e)}")
            return None, None
    
    return None, None


def open_file_viewer(parent_window, repo, passphrase, selected_files, current_file_id_setter, on_text_file_saved_callback):
    """Open a file viewer for the selected file.
    
    Args:
        parent_window: Parent window for dialogs
        repo: Repository path
        passphrase: Master passphrase
        selected_files: List of (file_id, name, relpath) tuples
        current_file_id_setter: Function to set the current file ID
        on_text_file_saved_callback: Callback for when text file is saved
    """
    if not repo:
        QtWidgets.QMessageBox.warning(parent_window, "No Repository", "Please select a repository first")
        return
        
    if not selected_files:
        QtWidgets.QMessageBox.warning(parent_window, "No Selection", "Please select a file to open")
        return
    
    if len(selected_files) > 1:
        QtWidgets.QMessageBox.warning(parent_window, "Multiple Selection", "Please select only one file to open")
        return
    
    fid, name, relpath = selected_files[0]
    
    # Store current file ID for saving
    current_file_id_setter(fid)
    
    # Create temporary file for viewing
    temp_dir = tempfile.mkdtemp()
    temp_path = os.path.join(temp_dir, name)
    
    try:
        # Extract file to temp location
        extract_args = argparse.Namespace(
            repo=str(repo), 
            id=fid, 
            out=temp_path, 
            passphrase=passphrase
        )
        cmd_extract(extract_args)
        
        # Determine file type and open appropriate viewer
        mime_type, _ = mimetypes.guess_type(name)
        
        if mime_type and mime_type.startswith('image/'):
            # Open image viewer
            viewer = ImageViewer(temp_path, parent_window)
            viewer.exec()
        elif mime_type == 'application/pdf':
            # Open PDF viewer
            viewer = PDFViewer(temp_path, parent_window)
            viewer.exec()
        elif mime_type and mime_type.startswith('video/'):
            player = VideoPlayer(temp_path, parent_window)
            player.exec()
        elif mime_type and mime_type.startswith('audio/'):
            player = AudioPlayer(temp_path, parent_window)
            player.exec()
        else:
            # Open text editor for text files and unknown types
            editor = TextEditor(temp_path, parent_window)
            # Connect the save signal
            editor.file_saved.connect(on_text_file_saved_callback)
            editor.exec()
            
    except Exception as e:
        QtWidgets.QMessageBox.critical(parent_window, "Error", f"Failed to open file: {str(e)}")
    finally:
        # Clean up temporary file
        try:
            os.remove(temp_path)
            os.rmdir(temp_dir)
        except:
            pass


def extract_selected_files(parent_window, repo, passphrase, selected_files):
    """Extract selected files from the vault.
    
    Args:
        parent_window: Parent window for dialogs
        repo: Repository path
        passphrase: Master passphrase
        selected_files: List of (file_id, name, relpath) tuples
    """
    if not repo:
        QtWidgets.QMessageBox.warning(parent_window, "No Repository", "Please select a repository first")
        return
        
    if not selected_files:
        QtWidgets.QMessageBox.warning(parent_window, "No Selection", "Please select files to extract")
        return
    
    if len(selected_files) == 1:
        # Single file - use save dialog
        fid, name, relpath = selected_files[0]
        dlg = QtWidgets.QFileDialog(parent_window)
        out, _ = dlg.getSaveFileName(parent_window, "Save decrypted file", name)
        if not out:
            return
        
        try:
            args = argparse.Namespace(repo=str(repo), id=fid, out=out, passphrase=passphrase)
            cmd_extract(args)
            QtWidgets.QMessageBox.information(parent_window, "Done", f"Saved to {out}")
        except Exception as e:
            QtWidgets.QMessageBox.critical(parent_window, "Error", str(e))
    else:
        # Multiple files - use directory dialog
        dlg = QtWidgets.QFileDialog(parent_window)
        out_dir = dlg.getExistingDirectory(parent_window, "Select directory to save files")
        if not out_dir:
            return
        
        try:
            success_count = 0
            for fid, name, relpath in selected_files:
                # Recreate folder structure when extracting many
                out_path = Path(out_dir) / (relpath or name)
                out_path.parent.mkdir(parents=True, exist_ok=True)
                args = argparse.Namespace(repo=str(repo), id=fid, out=str(out_path), passphrase=passphrase)
                cmd_extract(args)
                success_count += 1
            
            QtWidgets.QMessageBox.information(parent_window, "Done", f"Extracted {success_count} files to {out_dir}")
        except Exception as e:
            QtWidgets.QMessageBox.critical(parent_window, "Error", str(e))
