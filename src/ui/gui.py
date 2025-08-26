import argparse
import sys
import mimetypes
import os

from pathlib import Path

from utils.core import unlock, cmd_extract, cmd_add, update_file_in_vault
from utils.maintain import cmd_rm
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
        def __init__(self, repo: Path):
            super().__init__()
            self.repo = repo
            self.setWindowTitle("EFS – Vault Explorer")
            self.resize(900, 600)

            central = QtWidgets.QWidget(self)
            self.setCentralWidget(central)
            layout = QtWidgets.QVBoxLayout(central)

            # Passphrase prompt
            self.pass_edit = QtWidgets.QLineEdit()
            self.pass_edit.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
            self.pass_edit.setPlaceholderText("Master passphrase…")
            open_btn = QtWidgets.QPushButton("Unlock Vault")
            open_btn.clicked.connect(self.unlock)

            hl = QtWidgets.QHBoxLayout()
            hl.addWidget(self.pass_edit)
            hl.addWidget(open_btn)
            layout.addLayout(hl)

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

            # Table
            self.table = QtWidgets.QTableWidget(0, 5) 
            self.table.setHorizontalHeaderLabels(["Select", "ID", "Name", "Size", "Blob Path"])
            self.table.horizontalHeader().setStretchLastSection(True)
            layout.addWidget(self.table)

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
            
            layout.addLayout(btn_row)

            self.inner = None
            self.kmaster = None
            self.current_editor = None
            self.current_file_id = None

        def unlock(self):
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
            self.select_all_btn.setEnabled(True)
            self.deselect_all_btn.setEnabled(True)

        def populate(self):
            self.table.setRowCount(0)
            for f in self.inner.files:
                r = self.table.rowCount()
                self.table.insertRow(r)
                
                # Checkbox for selection
                checkbox = QtWidgets.QCheckBox()
                checkbox.setStyleSheet("margin-left:50%; margin-right:50%;")
                self.table.setCellWidget(r, 0, checkbox)
                
                # File data
                self.table.setItem(r, 1, QtWidgets.QTableWidgetItem(f.get("id", "")))
                self.table.setItem(r, 2, QtWidgets.QTableWidgetItem(f.get("name", "")))
                self.table.setItem(r, 3, QtWidgets.QTableWidgetItem(str(f.get("size", 0))))
                self.table.setItem(r, 4, QtWidgets.QTableWidgetItem(f.get("blob", "")))

        def select_all(self):
            """Select all files in the table."""
            for row in range(self.table.rowCount()):
                checkbox = self.table.cellWidget(row, 0)
                if checkbox:
                    checkbox.setChecked(True)

        def deselect_all(self):
            """Deselect all files in the table."""
            for row in range(self.table.rowCount()):
                checkbox = self.table.cellWidget(row, 0)
                if checkbox:
                    checkbox.setChecked(False)

        def get_selected_files(self):
            """Get list of selected file IDs and names."""
            selected = []
            for row in range(self.table.rowCount()):
                checkbox = self.table.cellWidget(row, 0)
                if checkbox and checkbox.isChecked():
                    fid = self.table.item(row, 1).text()
                    name = self.table.item(row, 2).text()
                    selected.append((fid, name))
            return selected

        def add_file(self):
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
                            
                            add_args = argparse.Namespace(
                                repo=str(self.repo),
                                path=str(temp_file_path),
                                passphrase=self.pass_edit.text()
                            )
                            cmd_add(add_args)
                            success_count += 1
                            
                            # Clean up temporary file
                            temp_file_path.unlink()
                            if temp_file_path.parent.exists() and not any(temp_file_path.parent.iterdir()):
                                temp_file_path.parent.rmdir()
                            
                        except Exception as e:
                            failed_files.append((str(rel_path), str(e)))
                        finally:
                            # Clean up temporary directory
                            try:
                                if Path(temp_dir).exists():
                                    shutil.rmtree(temp_dir)
                            except:
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
            selected_files = self.get_selected_files()
            if not selected_files:
                QtWidgets.QMessageBox.warning(self, "No Selection", "Please select files to remove")
                return
            
            # Confirm deletion
            file_list = "\n".join([f"• {name}" for fid, name in selected_files])
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
                    for fid, name in selected_files:
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
            selected_files = self.get_selected_files()
            if not selected_files:
                QtWidgets.QMessageBox.warning(self, "No Selection", "Please select a file to open")
                return
            
            if len(selected_files) > 1:
                QtWidgets.QMessageBox.warning(self, "Multiple Selection", "Please select only one file to open")
                return
            
            fid, name = selected_files[0]
            
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
            selected_files = self.get_selected_files()
            if not selected_files:
                QtWidgets.QMessageBox.warning(self, "No Selection", "Please select files to extract")
                return
            
            if len(selected_files) == 1:
                # Single file - use save dialog
                fid, name = selected_files[0]
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
                    for fid, name in selected_files:
                        out_path = Path(out_dir) / name
                        args = argparse.Namespace(repo=str(self.repo), id=fid, out=str(out_path), passphrase=self.pass_edit.text())
                        cmd_extract(args)
                        success_count += 1
                    
                    QtWidgets.QMessageBox.information(self, "Done", f"Extracted {success_count} files to {out_dir}")
                except Exception as e:
                    QtWidgets.QMessageBox.critical(self, "Error", str(e))

    # Initialize QApplication with command line arguments for WebEngine compatibility
    app = QtWidgets.QApplication(sys.argv)
    v = VaultApp(Path(args.repo))
    v.show()
    app.exec()