import argparse
import sys
import mimetypes

from pathlib import Path

from utils.core import unlock, cmd_extract, cmd_add, update_file_in_vault
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

            # Table
            self.table = QtWidgets.QTableWidget(0, 4)
            self.table.setHorizontalHeaderLabels(["ID", "Name", "Size", "Blob Path"])
            self.table.horizontalHeader().setStretchLastSection(True)
            layout.addWidget(self.table)

            # Actions
            btn_row = QtWidgets.QHBoxLayout()
            self.add_btn = QtWidgets.QPushButton("Add File…")
            self.add_btn.clicked.connect(self.add_file)
            self.add_btn.setEnabled(False)
            btn_row.addWidget(self.add_btn)
            
            self.open_btn = QtWidgets.QPushButton("Open File")
            self.open_btn.clicked.connect(self.open_file)
            self.open_btn.setEnabled(False)
            btn_row.addWidget(self.open_btn)
            
            self.save_btn = QtWidgets.QPushButton("Extract Selected…")
            self.save_btn.clicked.connect(self.extract_selected)
            self.save_btn.setEnabled(False)
            btn_row.addWidget(self.save_btn)
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
            self.open_btn.setEnabled(True)

        def populate(self):
            self.table.setRowCount(0)
            for f in self.inner.files:
                r = self.table.rowCount()
                self.table.insertRow(r)
                self.table.setItem(r, 0, QtWidgets.QTableWidgetItem(f.get("id", "")))
                self.table.setItem(r, 1, QtWidgets.QTableWidgetItem(f.get("name", "")))
                self.table.setItem(r, 2, QtWidgets.QTableWidgetItem(str(f.get("size", 0))))
                self.table.setItem(r, 3, QtWidgets.QTableWidgetItem(f.get("blob", "")))

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
            rows = sorted({ix.row() for ix in self.table.selectedIndexes()})
            if not rows:
                QtWidgets.QMessageBox.warning(self, "No Selection", "Please select a file to open")
                return
            
            r = rows[0]
            fid = self.table.item(r, 0).text()
            name = self.table.item(r, 1).text()
            
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
            rows = sorted({ix.row() for ix in self.table.selectedIndexes()})
            if not rows:
                return
            r = rows[0]
            fid = self.table.item(r, 0).text()
            name = self.table.item(r, 1).text()
            dlg = QtWidgets.QFileDialog(self)
            out, _ = dlg.getSaveFileName(self, "Save decrypted file", name)
            if not out:
                return
            # do extraction using kmaster
            args = argparse.Namespace(repo=str(self.repo), id=fid, out=out, passphrase=self.pass_edit.text())
            try:
                cmd_extract(args)
                QtWidgets.QMessageBox.information(self, "Done", f"Saved to {out}")
            except Exception as e:
                QtWidgets.QMessageBox.critical(self, "Error", str(e))

    # Initialize QApplication with command line arguments for WebEngine compatibility
    app = QtWidgets.QApplication(sys.argv)
    v = VaultApp(Path(args.repo))
    v.show()
    app.exec()