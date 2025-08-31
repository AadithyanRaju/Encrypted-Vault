import argparse
import sys
import mimetypes
import os

from pathlib import Path

from ui.AudioPlayer import AudioPlayer
from ui.VideoPlayer import VideoPlayer
from utils.core import unlock, cmd_extract, cmd_add, update_file_in_vault
from utils.maintain import cmd_rm, cmd_rotate_master
from ui.ImageViewer import ImageViewer
from ui.TextEditor import TextEditor
from ui.PDFViewer import PDFViewer

def cmd_gui(args: argparse.Namespace) -> None:
    try:
        from PyQt6 import QtWidgets, QtGui, QtCore
    except Exception as e:
        print("[!] PyQt6 not installed. pip install PyQt6")
        sys.exit(1)

    class VaultApp(QtWidgets.QMainWindow):
        def __init__(self, repo: Path = None):
            super().__init__()
            self.repo = repo
            self.setWindowTitle("EFS - Vault Explorer")
            self.resize(900, 600)

            central = QtWidgets.QWidget(self)
            self.setCentralWidget(central)
            layout = QtWidgets.QVBoxLayout(central)

            # Passphrase prompt
            self.pass_edit = QtWidgets.QLineEdit()
            self.pass_edit.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
            self.pass_edit.setPlaceholderText("Master passphrase…")
            # Pressing Enter in the passphrase field should attempt to unlock
            self.pass_edit.returnPressed.connect(self.unlock)
            open_btn = QtWidgets.QPushButton("Unlock Vault")
            open_btn.clicked.connect(self.unlock)

            hl = QtWidgets.QHBoxLayout()
            hl.addWidget(self.pass_edit)
            hl.addWidget(open_btn)
            layout.addLayout(hl)

            # Give keyboard focus to the passphrase field by default
            self.pass_edit.setFocus()

            # Selection controls
            select_layout = QtWidgets.QHBoxLayout()
            self.select_all_btn = QtWidgets.QPushButton("Select All")
            self.select_all_btn.clicked.connect(self.select_all)
            self.select_all_btn.setEnabled(False)
            select_layout.addWidget(self.select_all_btn)
            
            self.deselect_all_btn = QtWidgets.QPushButton("Deselect All")
            self.deselect_all_btn.clicked.connect(self.deselect_all)
            self.deselect_all_btn.setEnabled(False)
            select_layout.addWidget(self.deselect_all_btn)
            
            select_layout.addStretch()
            layout.addLayout(select_layout)

            # Tree for folders/files
            self.tree = QtWidgets.QTreeWidget()
            self.tree.setColumnCount(5)
            self.tree.setHeaderLabels(["Select", "ID", "Name", "Size", "Relpath"])
            self.tree.header().setStretchLastSection(True)
            # Only allow single visual selection in the tree; checkbox column is used for multi-select
            self.tree.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
            # Clicking a row (not the checkbox) should select that single item via its checkbox
            self.tree.itemClicked.connect(self._on_tree_item_clicked)
            layout.addWidget(self.tree)

            # Actions
            btn_row = QtWidgets.QHBoxLayout()
            self.add_btn = QtWidgets.QPushButton("Add File…")
            self.add_btn.clicked.connect(self.add_file)
            self.add_btn.setEnabled(False)
            btn_row.addWidget(self.add_btn)
            
            self.add_folder_btn = QtWidgets.QPushButton("Add Folder…")
            self.add_folder_btn.clicked.connect(self.add_folder)
            self.add_folder_btn.setEnabled(False)
            btn_row.addWidget(self.add_folder_btn)
            
            self.open_btn = QtWidgets.QPushButton("Open File")
            self.open_btn.clicked.connect(self.open_file)
            self.open_btn.setEnabled(False)
            btn_row.addWidget(self.open_btn)
            
            self.save_btn = QtWidgets.QPushButton("Extract Selected…")
            self.save_btn.clicked.connect(self.extract_selected)
            self.save_btn.setEnabled(False)
            btn_row.addWidget(self.save_btn)
            
            self.remove_btn = QtWidgets.QPushButton("Remove Selected")
            self.remove_btn.clicked.connect(self.remove_files)
            self.remove_btn.setEnabled(False)
            btn_row.addWidget(self.remove_btn)

            self.rotate_btn = QtWidgets.QPushButton("Change Master Password…")
            self.rotate_btn.clicked.connect(self.change_master_password)
            self.rotate_btn.setEnabled(False)
            btn_row.addWidget(self.rotate_btn)
            
            self.close_btn = QtWidgets.QPushButton("Close Repository")
            self.close_btn.clicked.connect(self.close_repo)
            self.close_btn.setEnabled(True)
            btn_row.addWidget(self.close_btn)
            
            layout.addLayout(btn_row)

            self.inner = None
            self.kmaster = None
            self.current_editor = None
            self.current_file_id = None

        def show_startup_dialog(self):
            """Show dialog to create new repo or select existing one."""
            dlg = QtWidgets.QDialog(self)
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
            create_btn.clicked.connect(lambda: self.create_new_repo(dlg))
            layout.addWidget(create_btn)
            
            select_btn = QtWidgets.QPushButton("Select an existing vault")
            select_btn.setMinimumHeight(40)
            select_btn.clicked.connect(lambda: self.select_existing_repo(dlg))
            layout.addWidget(select_btn)
            
            # Show dialog
            dlg.exec()

        def create_new_repo(self, parent_dialog):
            """Create a new repository."""
            # Get directory for new repo
            dlg = QtWidgets.QFileDialog(self)
            repo_dir = dlg.getExistingDirectory(self, "Select directory for new repository")
            if not repo_dir:
                return
            
            repo_path = Path(repo_dir)
            
            # Get passphrase for new repo
            pass_dlg = QtWidgets.QDialog(self)
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
                QtWidgets.QMessageBox.warning(self, "Error", "Passwords do not match or are empty")
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
                self.repo = repo_path
                self.pass_edit.setText(password)
                parent_dialog.close()
                self.show()
                self.unlock()
                
                QtWidgets.QMessageBox.information(self, "Success", f"Created new repository at {repo_path}")
                
            except Exception as e:
                QtWidgets.QMessageBox.critical(self, "Error", f"Failed to create repository: {str(e)}")

        def select_existing_repo(self, parent_dialog):
            """Select an existing repository."""
            dlg = QtWidgets.QFileDialog(self)
            repo_dir = dlg.getExistingDirectory(self, "Select repository directory")
            if not repo_dir:
                return
            
            repo_path = Path(repo_dir)
            vault_file = repo_path / "vault.enc"
            
            if not vault_file.exists():
                QtWidgets.QMessageBox.warning(self, "Invalid Repository", "Selected directory does not contain a vault.enc file")
                return
            
            # Set repo and show main window
            self.repo = repo_path
            parent_dialog.close()
            self.show()

        def unlock(self):
            if not self.repo:
                QtWidgets.QMessageBox.warning(self, "No Repository", "Please select a repository first")
                return
                
            pw = self.pass_edit.text()
            try:
                self.inner, self.kmaster, _ = unlock(self.repo, pw)
            except Exception as e:
                QtWidgets.QMessageBox.critical(self, "Unlock failed", str(e))
                return
            self.populate()
            self.save_btn.setEnabled(True)
            self.add_btn.setEnabled(True)
            self.add_folder_btn.setEnabled(True)
            self.open_btn.setEnabled(True)
            self.remove_btn.setEnabled(True)
            self.rotate_btn.setEnabled(True)
            # close button remains enabled
            self.close_btn.setEnabled(True)
            self.select_all_btn.setEnabled(True)
            self.deselect_all_btn.setEnabled(True)

        def populate(self):
            self.tree.clear()
            # Build folder structure from relpaths
            folders = {}
            for f in self.inner.files:
                relpath = f.get("relpath") or f.get("name", "")
                parts = Path(relpath).parts
                parent = self.tree.invisibleRootItem()
                current_path = []
                # Create/find folder nodes
                for part in parts[:-1]:
                    current_path.append(part)
                    key = "/".join(current_path)
                    if key not in folders:
                        item = QtWidgets.QTreeWidgetItem(["", "", part, "", "/".join(current_path)])
                        item.setFirstColumnSpanned(False)
                        folders[key] = item
                        parent.addChild(item)
                        # Add checkbox to folder node and wire it to toggle descendants
                        folder_checkbox = QtWidgets.QCheckBox()
                        folder_checkbox.setStyleSheet("margin-left:50%; margin-right:50%;")
                        self.tree.setItemWidget(item, 0, folder_checkbox)
                        # Capture current item in a closure
                        def make_handler(folder_item):
                            def handler(state):
                                self.__set_descendants_checked(folder_item, state == QtCore.Qt.CheckState.Checked)
                            return handler
                        folder_checkbox.stateChanged.connect(make_handler(item))
                    parent = folders[key]
                # Add file leaf
                leaf = QtWidgets.QTreeWidgetItem(["", f.get("id", ""), f.get("name", ""), str(f.get("size", 0)), relpath])
                parent.addChild(leaf)
                # Add a checkbox widget on column 0
                checkbox = QtWidgets.QCheckBox()
                checkbox.setStyleSheet("margin-left:50%; margin-right:50%;")
                self.tree.setItemWidget(leaf, 0, checkbox)

        def __set_descendants_checked(self, item: 'QtWidgets.QTreeWidgetItem', checked: bool) -> None:
            # Recursively set all descendant file checkboxes
            for i in range(item.childCount()):
                child = item.child(i)
                cb = self.tree.itemWidget(child, 0)
                if cb is not None:
                    cb.setChecked(checked)
                # Recurse into folders
                if child.childCount() > 0:
                    self.__set_descendants_checked(child, checked)

        def _clear_all_checkboxes(self) -> None:
            """Uncheck every checkbox widget in the tree."""
            it = QtWidgets.QTreeWidgetItemIterator(self.tree)
            while it.value():
                item = it.value()
                cb = self.tree.itemWidget(item, 0)
                if cb is not None:
                    # Use setChecked to update UI; connected handlers will run as expected
                    cb.setChecked(False)
                it += 1

        def _on_tree_item_clicked(self, item: 'QtWidgets.QTreeWidgetItem', column: int) -> None:
            """Handle clicks on tree rows: if a leaf row (file) is clicked (any column except checkbox),
            treat it as a single selection by clearing all checkboxes and checking only that row's checkbox.
            Clicking the checkbox itself keeps normal multi-select behavior.
            """
            try:
                # Only convert a single selection for leaf items (files). Folders are left to checkbox logic.
                if item is None:
                    return
                if item.childCount() != 0:
                    # folder node: when user clicks the row (not the checkbox column),
                    # treat that as selecting the entire folder: clear other selections
                    # and check all descendants of this folder.
                    if column == 0:
                        # clicking the folder's checkbox - leave default multi-select behavior
                        return
                    # clear other selections and check this folder's descendants
                    self._clear_all_checkboxes()
                    folder_cb = self.tree.itemWidget(item, 0)
                    if folder_cb is not None:
                        folder_cb.setChecked(True)
                    # check all descendant file checkboxes
                    self.__set_descendants_checked(item, True)
                    return
                # If user clicked the checkbox column directly, don't override (allow multi-select)
                if column == 0:
                    return

                # Clear all other checkboxes and check the clicked item's checkbox
                self._clear_all_checkboxes()
                cb = self.tree.itemWidget(item, 0)
                if cb is not None:
                    cb.setChecked(True)
            except Exception:
                # Non-critical UI handler: ignore unexpected errors
                pass

        def select_all(self):
            """Select all files in the table."""
            it = QtWidgets.QTreeWidgetItemIterator(self.tree)
            while it.value():
                item = it.value()
                checkbox = self.tree.itemWidget(item, 0)
                if checkbox:
                    checkbox.setChecked(True)
                it += 1

        def deselect_all(self):
            """Deselect all files in the table."""
            it = QtWidgets.QTreeWidgetItemIterator(self.tree)
            while it.value():
                item = it.value()
                checkbox = self.tree.itemWidget(item, 0)
                if checkbox:
                    checkbox.setChecked(False)
                it += 1

        def get_selected_files(self):
            """Get list of selected file IDs and names."""
            selected = []
            it = QtWidgets.QTreeWidgetItemIterator(self.tree)
            while it.value():
                item = it.value()
                checkbox = self.tree.itemWidget(item, 0)
                # only leaves have IDs
                if checkbox and checkbox.isChecked() and item.text(1):
                    selected.append((item.text(1), item.text(2), item.text(4)))
                it += 1
            return selected

        def add_file(self):
            if not self.repo:
                QtWidgets.QMessageBox.warning(self, "No Repository", "Please select a repository first")
                return
                
            dlg = QtWidgets.QFileDialog(self)
            file_path, _ = dlg.getOpenFileName(self, "Select file to add to vault")
            if not file_path:
                return
            
            try:
                add_args = argparse.Namespace(
                    repo=str(self.repo),
                    path=file_path,
                    passphrase=self.pass_edit.text()
                )
                cmd_add(add_args)
                
                self.inner, self.kmaster, _ = unlock(self.repo, self.pass_edit.text())
                self.populate()
                
                QtWidgets.QMessageBox.information(self, "Success", f"Added {Path(file_path).name} to vault")
            except Exception as e:
                QtWidgets.QMessageBox.critical(self, "Error", f"Failed to add file: {str(e)}")

        def add_folder(self):
            if not self.repo:
                QtWidgets.QMessageBox.warning(self, "No Repository", "Please select a repository first")
                return
                
            dlg = QtWidgets.QFileDialog(self)
            folder_path = dlg.getExistingDirectory(self, "Select folder to add to vault")
            if not folder_path:
                return
            
            folder_path = Path(folder_path)
            if not folder_path.is_dir():
                QtWidgets.QMessageBox.warning(self, "Invalid Selection", "Please select a valid folder")
                return
            
            # Get all files in the folder recursively
            files_to_add = []
            for file_path in folder_path.rglob('*'):
                if file_path.is_file():
                    # Calculate relative path from the selected folder
                    rel_path = file_path.relative_to(folder_path)
                    files_to_add.append((file_path, rel_path))
            
            if not files_to_add:
                QtWidgets.QMessageBox.information(self, "Empty Folder", "The selected folder contains no files")
                return
            
            # Confirm with user
            file_list = "\n".join([f"• {rel_path}" for file_path, rel_path in files_to_add[:10]])  # Show first 10
            if len(files_to_add) > 10:
                file_list += f"\n... and {len(files_to_add) - 10} more files"
            
            reply = QtWidgets.QMessageBox.question(
                self,
                "Confirm Folder Addition",
                f"Add {len(files_to_add)} files from '{folder_path.name}' to vault?\n\n{file_list}",
                QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
                QtWidgets.QMessageBox.StandardButton.No
            )
            
            if reply == QtWidgets.QMessageBox.StandardButton.Yes:
                try:
                    success_count = 0
                    failed_files = []
                    
                    # Show progress dialog
                    progress = QtWidgets.QProgressDialog("Adding files to vault...", "Cancel", 0, len(files_to_add), self)
                    progress.setWindowModality(QtCore.Qt.WindowModality.WindowModal)
                    progress.setAutoClose(False)
                    
                    for i, (file_path, rel_path) in enumerate(files_to_add):
                        progress.setValue(i)
                        progress.setLabelText(f"Adding: {rel_path}")
                        
                        if progress.wasCanceled():
                            break
                        
                        try:
                            # Create a temporary file with the relative path as name to preserve structure
                            import tempfile
                            import shutil
                            
                            # Create a temporary directory structure
                            temp_dir = tempfile.mkdtemp()
                            temp_file_path = Path(temp_dir) / rel_path
                            
                            # Create parent directories if they don't exist
                            temp_file_path.parent.mkdir(parents=True, exist_ok=True)
                            
                            # Copy the file to the temporary location with relative path
                            shutil.copy2(file_path, temp_file_path)
                            
                            # Prefix relpath with selected folder name to keep top-level folder
                            prefixed_rel = Path(folder_path.name) / rel_path
                            add_args = argparse.Namespace(
                                repo=str(self.repo),
                                path=str(file_path),
                                relpath=str(prefixed_rel),
                                passphrase=self.pass_edit.text()
                            )
                            cmd_add(add_args)
                            success_count += 1
                            
                            # No temp cleanup needed now
                            
                        except Exception as e:
                            failed_files.append((str(rel_path), str(e)))
                        finally:
                            pass
                    
                    progress.setValue(len(files_to_add))
                    
                    # Refresh the table
                    self.inner, self.kmaster, _ = unlock(self.repo, self.pass_edit.text())
                    self.populate()
                    
                    # Show results
                    if failed_files:
                        error_msg = f"Successfully added {success_count} files.\n\nFailed to add {len(failed_files)} files:\n"
                        error_msg += "\n".join([f"• {name}: {error}" for name, error in failed_files[:5]])
                        if len(failed_files) > 5:
                            error_msg += f"\n... and {len(failed_files) - 5} more failures"
                        QtWidgets.QMessageBox.warning(self, "Partial Success", error_msg)
                    else:
                        QtWidgets.QMessageBox.information(self, "Success", f"Added {success_count} files from '{folder_path.name}' to vault")
                        
                except Exception as e:
                    QtWidgets.QMessageBox.critical(self, "Error", f"Failed to add folder: {str(e)}")

        def remove_files(self):
            if not self.repo:
                QtWidgets.QMessageBox.warning(self, "No Repository", "Please select a repository first")
                return
                
            selected_files = self.get_selected_files()
            if not selected_files:
                QtWidgets.QMessageBox.warning(self, "No Selection", "Please select files to remove")
                return
            
            # Confirm deletion
            file_list = "\n".join([f"• {name}" for fid, name, _ in selected_files])
            reply = QtWidgets.QMessageBox.question(
                self,
                "Confirm Deletion",
                f"Are you sure you want to remove {len(selected_files)} file(s) from the vault?\n\n{file_list}\n\nThis action cannot be undone.",
                QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
                QtWidgets.QMessageBox.StandardButton.No
            )
            
            if reply == QtWidgets.QMessageBox.StandardButton.Yes:
                try:
                    # Remove each selected file
                    for fid, name, _ in selected_files:
                        rm_args = argparse.Namespace(
                            repo=str(self.repo),
                            id=fid,
                            passphrase=self.pass_edit.text()
                        )
                        cmd_rm(rm_args)
                    
                    # Refresh the table
                    self.inner, self.kmaster, _ = unlock(self.repo, self.pass_edit.text())
                    self.populate()
                    
                    QtWidgets.QMessageBox.information(self, "Success", f"Removed {len(selected_files)} file(s) from vault")
                except Exception as e:
                    QtWidgets.QMessageBox.critical(self, "Error", f"Failed to remove files: {str(e)}")

        def close_repo(self):
            """Close the currently opened repository and clear UI state."""
            if not self.repo:
                return
            reply = QtWidgets.QMessageBox.question(
                self,
                "Close Repository",
                "Close the current repository and clear unlocked state?",
                QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
                QtWidgets.QMessageBox.StandardButton.No,
            )
            if reply != QtWidgets.QMessageBox.StandardButton.Yes:
                return

            # Clear internal state
            self.repo = None
            self.inner = None
            self.kmaster = None
            self.current_editor = None
            self.current_file_id = None
            self.tree.clear()
            self.pass_edit.clear()

            # Disable controls
            for btn in (
                self.save_btn, self.add_btn, self.add_folder_btn, self.open_btn,
                self.remove_btn, self.rotate_btn, self.select_all_btn, self.deselect_all_btn,
                self.close_btn,
            ):
                try:
                    btn.setEnabled(False)
                except Exception:
                    pass

            #QtWidgets.QMessageBox.information(self, "Closed", "Repository closed.")

            try:
                self.hide()
                self.show_startup_dialog()
                if self.repo:
                    self.show()
                else:
                    sys.exit(0)
            except Exception:
                pass

        def on_text_file_saved(self, file_path: str, content: str):
            """Handle when a text file is saved in the editor."""
            try:
                # Update the file in the vault
                update_file_in_vault(
                    self.repo, 
                    self.current_file_id, 
                    content.encode('utf-8'), 
                    self.pass_edit.text()
                )
                
                # Refresh the table to show updated file size
                self.inner, self.kmaster, _ = unlock(self.repo, self.pass_edit.text())
                self.populate()
                
                QtWidgets.QMessageBox.information(self, "Success", "File updated in vault successfully!")
            except Exception as e:
                QtWidgets.QMessageBox.critical(self, "Error", f"Failed to update file in vault: {str(e)}")

        def open_file(self):
            if not self.repo:
                QtWidgets.QMessageBox.warning(self, "No Repository", "Please select a repository first")
                return
                
            selected_files = self.get_selected_files()
            if not selected_files:
                QtWidgets.QMessageBox.warning(self, "No Selection", "Please select a file to open")
                return
            
            if len(selected_files) > 1:
                QtWidgets.QMessageBox.warning(self, "Multiple Selection", "Please select only one file to open")
                return
            
            fid, name, relpath = selected_files[0]
            
            # Store current file ID for saving
            self.current_file_id = fid
            
            # Create temporary file for viewing
            import tempfile
            import os
            
            temp_dir = tempfile.mkdtemp()
            temp_path = os.path.join(temp_dir, name)
            
            try:
                # Extract file to temp location
                extract_args = argparse.Namespace(
                    repo=str(self.repo), 
                    id=fid, 
                    out=temp_path, 
                    passphrase=self.pass_edit.text()
                )
                cmd_extract(extract_args)
                
                # Determine file type and open appropriate viewer
                mime_type, _ = mimetypes.guess_type(name)
                
                if mime_type and mime_type.startswith('image/'):
                    # Open image viewer
                    viewer = ImageViewer(temp_path, self)
                    viewer.exec()
                elif mime_type == 'application/pdf':
                    # Open PDF viewer
                    viewer = PDFViewer(temp_path, self)
                    viewer.exec()
                elif mime_type and mime_type.startswith('video/'):
                    player = VideoPlayer(temp_path, self)
                    player.exec()
                elif mime_type and mime_type.startswith('audio/'):
                    player = AudioPlayer(temp_path, self)
                    player.exec()
                else:
                    # Open text editor for text files and unknown types
                    editor = TextEditor(temp_path, self)
                    # Connect the save signal
                    editor.file_saved.connect(self.on_text_file_saved)
                    self.current_editor = editor
                    editor.exec()
                    
            except Exception as e:
                QtWidgets.QMessageBox.critical(self, "Error", f"Failed to open file: {str(e)}")
            finally:
                # Clean up temporary file
                try:
                    os.remove(temp_path)
                    os.rmdir(temp_dir)
                except:
                    pass

        def extract_selected(self):
            if not self.repo:
                QtWidgets.QMessageBox.warning(self, "No Repository", "Please select a repository first")
                return
                
            selected_files = self.get_selected_files()
            if not selected_files:
                QtWidgets.QMessageBox.warning(self, "No Selection", "Please select files to extract")
                return
            
            if len(selected_files) == 1:
                # Single file - use save dialog
                fid, name, relpath = selected_files[0]
                dlg = QtWidgets.QFileDialog(self)
                out, _ = dlg.getSaveFileName(self, "Save decrypted file", name)
                if not out:
                    return
                
                try:
                    args = argparse.Namespace(repo=str(self.repo), id=fid, out=out, passphrase=self.pass_edit.text())
                    cmd_extract(args)
                    QtWidgets.QMessageBox.information(self, "Done", f"Saved to {out}")
                except Exception as e:
                    QtWidgets.QMessageBox.critical(self, "Error", str(e))
            else:
                # Multiple files - use directory dialog
                dlg = QtWidgets.QFileDialog(self)
                out_dir = dlg.getExistingDirectory(self, "Select directory to save files")
                if not out_dir:
                    return
                
                try:
                    success_count = 0
                    for fid, name, relpath in selected_files:
                        # Recreate folder structure when extracting many
                        out_path = Path(out_dir) / (relpath or name)
                        out_path.parent.mkdir(parents=True, exist_ok=True)
                        args = argparse.Namespace(repo=str(self.repo), id=fid, out=str(out_path), passphrase=self.pass_edit.text())
                        cmd_extract(args)
                        success_count += 1
                    
                    QtWidgets.QMessageBox.information(self, "Done", f"Extracted {success_count} files to {out_dir}")
                except Exception as e:
                    QtWidgets.QMessageBox.critical(self, "Error", str(e))

        def change_master_password(self):
            if not self.repo:
                QtWidgets.QMessageBox.warning(self, "No Repository", "Please select a repository first")
                return
                
            dlg = QtWidgets.QDialog(self)
            dlg.setWindowTitle("Change Master Password")
            v = QtWidgets.QVBoxLayout(dlg)

            current_edit = QtWidgets.QLineEdit()
            current_edit.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
            current_edit.setPlaceholderText("Current password")
            # Pre-fill with current if present
            current_edit.setText(self.pass_edit.text())

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
                return

            curr = current_edit.text()
            newp = new_edit.text()
            conf = confirm_edit.text()

            if not curr or not newp:
                QtWidgets.QMessageBox.warning(self, "Missing", "Please fill all fields")
                return
            if newp != conf:
                QtWidgets.QMessageBox.warning(self, "Mismatch", "New passwords do not match")
                return

            try:
                args = argparse.Namespace(repo=str(self.repo), passphrase=curr, new_passphrase=newp, t=None, m=None, p=None)
                cmd_rotate_master(args)
                # Update UI to use new password and re-unlock
                self.pass_edit.setText(newp)
                self.unlock()
                QtWidgets.QMessageBox.information(self, "Success", "Master password changed.")
            except Exception as e:
                QtWidgets.QMessageBox.critical(self, "Error", f"Failed to change password: {str(e)}")
            

    app = QtWidgets.QApplication(sys.argv)
    
    if not args.repo:
        v = VaultApp()
        v.show_startup_dialog()
        if not v.repo:
            sys.exit(0)
    else:
        v = VaultApp(Path(args.repo))
        v.show()
    
    app.exec()

   