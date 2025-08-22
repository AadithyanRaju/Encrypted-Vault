import argparse
import sys

from pathlib import Path

from utils.core import unlock, cmd_extract

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
            self.save_btn = QtWidgets.QPushButton("Extract Selected…")
            self.save_btn.clicked.connect(self.extract_selected)
            self.save_btn.setEnabled(False)
            btn_row.addWidget(self.save_btn)
            layout.addLayout(btn_row)

            self.inner = None
            self.kmaster = None

        def unlock(self):
            pw = self.pass_edit.text()
            try:
                self.inner, self.kmaster, _ = unlock(self.repo, pw)
            except Exception as e:
                QtWidgets.QMessageBox.critical(self, "Unlock failed", str(e))
                return
            self.populate()
            self.save_btn.setEnabled(True)

        def populate(self):
            self.table.setRowCount(0)
            for f in self.inner.files:
                r = self.table.rowCount()
                self.table.insertRow(r)
                self.table.setItem(r, 0, QtWidgets.QTableWidgetItem(f.get("id", "")))
                self.table.setItem(r, 1, QtWidgets.QTableWidgetItem(f.get("name", "")))
                self.table.setItem(r, 2, QtWidgets.QTableWidgetItem(str(f.get("size", 0))))
                self.table.setItem(r, 3, QtWidgets.QTableWidgetItem(f.get("blob", "")))

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

    app = QtWidgets.QApplication([])
    v = VaultApp(Path(args.repo))
    v.show()
    app.exec()