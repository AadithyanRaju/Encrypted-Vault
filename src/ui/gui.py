import argparse
import sys
from pathlib import Path

# Import modular GUI components
from ui.gui_components.dialogs import show_startup_dialog, show_change_master_password_dialog
from ui.gui_components.tree_operations import (
    populate_tree, filter_tree_items, set_descendants_checked,
    select_all_items, deselect_all_items, get_selected_files,
    handle_tree_item_clicked
)
from ui.gui_components.file_operations import (
    add_single_file, add_folder, remove_selected_files,
    open_file_viewer, extract_selected_files
)
from ui.gui_components.vault_operations import (
    unlock_vault, lock_vault, close_repository,
    change_master_password, save_text_file_to_vault
)

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
            self.open_vault_btn = QtWidgets.QPushButton("Unlock Vault")
            self.open_vault_btn.clicked.connect(self.unlock)
            # Lock button (replaces passphrase UI when vault is unlocked)
            self.lock_btn = QtWidgets.QPushButton("Lock Vault")
            self.lock_btn.clicked.connect(self.lock_vault)
            self.lock_btn.setVisible(False)

            hl = QtWidgets.QHBoxLayout()
            hl.addWidget(self.pass_edit)
            hl.addWidget(self.open_vault_btn)
            hl.addWidget(self.lock_btn)
            layout.addLayout(hl)

            # Give keyboard focus to the passphrase field by default
            self.pass_edit.setFocus()

            # Selection controls and search bar
            select_layout = QtWidgets.QHBoxLayout()
            
            # Search bar
            self.search_edit = QtWidgets.QLineEdit()
            self.search_edit.setPlaceholderText("Search files...")
            self.search_edit.textChanged.connect(self.filter_files)
            self.search_edit.setEnabled(False)
            select_layout.addWidget(self.search_edit)
            
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
            # Ensure checkbox column is wide enough for nested items
            try:
                self.tree.setColumnWidth(0, 100)
            except Exception:
                pass
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
            
            self.close_btn = QtWidgets.QPushButton("Close Vault")
            self.close_btn.clicked.connect(self.close_repo)
            self.close_btn.setEnabled(True)
            btn_row.addWidget(self.close_btn)
            
            layout.addLayout(btn_row)

            # Status message area at the bottom
            self.status_label = QtWidgets.QLabel("")
            self.status_label.setWordWrap(True)
            self.status_label.setStyleSheet("padding: 8px; border: 1px solid #ccc; background-color: #f0f0f0; border-radius: 4px;")
            self.status_label.setMinimumHeight(40)
            self.status_label.setVisible(False)
            layout.addWidget(self.status_label)

            self.inner = None
            self.kmaster = None
            self.current_editor = None
            self.current_file_id = None
            self._last_clicked_item = None      # track last clicked item to support Shift+click range selection

        def show_message(self, message: str, message_type: str = "info"):
            """Display a message in the status area.
            
            Args:
                message: The message to display
                message_type: Type of message - "info", "warning", "error", "success"
            """
            colors = {
                "info": "#e3f2fd",      # Light blue
                "warning": "#fff3e0",   # Light orange
                "error": "#ffebee",     # Light red
                "success": "#e8f5e9"    # Light green
            }
            border_colors = {
                "info": "#2196F3",      # Blue
                "warning": "#FF9800",   # Orange
                "error": "#F44336",     # Red
                "success": "#4CAF50"    # Green
            }
            
            bg_color = colors.get(message_type, colors["info"])
            border_color = border_colors.get(message_type, border_colors["info"])
            
            self.status_label.setText(message)
            self.status_label.setStyleSheet(
                f"padding: 8px; border: 2px solid {border_color}; "
                f"background-color: {bg_color}; border-radius: 4px;"
            )
            self.status_label.setVisible(True)
            
            # Auto-hide success and info messages after 5 seconds
            if message_type in ["info", "success"]:
                QtCore.QTimer.singleShot(5000, lambda: self.status_label.setVisible(False))

        def show_startup_dialog(self):
            """Show dialog to create new repo or select existing one."""
            show_startup_dialog(self)

        def unlock(self):
            if not self.repo:
                self.show_message("Please select a repository first", "warning")
                return
            
            pw = self.pass_edit.text()
            result = unlock_vault(self, self.repo, pw, self.populate)
            if result[0] is not None:
                self.inner, self.kmaster = result

        def populate(self):
            populate_tree(self.tree, self.inner, self.__set_descendants_checked)

        def filter_files(self):
            """Filter tree items based on search text."""
            filter_tree_items(self.tree, self.search_edit.text())

        def __set_descendants_checked(self, item: 'QtWidgets.QTreeWidgetItem', checked: bool) -> None:
            set_descendants_checked(self.tree, item, checked)

        def _clear_all_checkboxes(self) -> None:
            from ui.gui_components.tree_operations import clear_all_checkboxes
            clear_all_checkboxes(self.tree)

        def _on_tree_item_clicked(self, item: 'QtWidgets.QTreeWidgetItem', column: int) -> None:
            """Handle clicks on tree rows for selection."""
            self._last_clicked_item = handle_tree_item_clicked(
                self.tree, item, column, self._last_clicked_item, self.__set_descendants_checked
            )

        def select_all(self):
            """Select all files in the table."""
            select_all_items(self.tree)

        def deselect_all(self):
            """Deselect all files in the table."""
            deselect_all_items(self.tree)

        def get_selected_files(self):
            """Get list of selected file IDs and names."""
            return get_selected_files(self.tree)

        def add_file(self):
            result = add_single_file(self, self.repo, self.pass_edit.text(), self.populate)
            if result[0] is not None:
                self.inner, self.kmaster = result

        def add_folder(self):
            result = add_folder(self, self.repo, self.pass_edit.text(), self.populate)
            if result[0] is not None:
                self.inner, self.kmaster = result

        def remove_files(self):
            result = remove_selected_files(self, self.repo, self.pass_edit.text(), self.get_selected_files(), self.populate)
            if result[0] is not None:
                self.inner, self.kmaster = result

        def close_repo(self):
            """Close the currently opened repository and clear UI state."""
            close_repository(self)

        def lock_vault(self):
            """Lock the currently opened repository but keep the repo selected (allow re-unlock)."""
            lock_vault(self)

        def on_text_file_saved(self, file_path: str, content: str):
            """Handle when a text file is saved in the editor."""
            result = save_text_file_to_vault(self, self.repo, self.current_file_id, content, self.pass_edit.text(), self.populate)
            if result[0] is not None:
                self.inner, self.kmaster = result

        def open_file(self):
            open_file_viewer(self, self.repo, self.pass_edit.text(), self.get_selected_files(), 
                           lambda fid: setattr(self, 'current_file_id', fid), self.on_text_file_saved)

        def extract_selected(self):
            extract_selected_files(self, self.repo, self.pass_edit.text(), self.get_selected_files())

        def change_master_password(self):
            curr, newp, confirmed = show_change_master_password_dialog(self)
            if confirmed:
                change_master_password(self, self.repo, curr, newp, self.unlock)

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

   