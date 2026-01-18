import sys
from pathlib import Path

try:
    from PyQt6 import QtWidgets, QtGui, QtCore
except Exception as e:
    print("[!] PyQt6 not installed. pip install PyQt6")
    sys.exit(1)

class TextEditor(QtWidgets.QDialog):
    # Signal to notify when file is saved
    file_saved = QtCore.pyqtSignal(str, str)  # file_path, content
    
    def __init__(self, file_path: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Text Editor - {Path(file_path).name}")
        self.resize(900, 700)
        
        layout = QtWidgets.QVBoxLayout(self)
        
        # Text editor
        self.text_edit = QtWidgets.QTextEdit()
        self.text_edit.setFont(QtGui.QFont("Consolas", 10))
        layout.addWidget(self.text_edit)
        
        # Status message area
        self.status_label = QtWidgets.QLabel("")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("padding: 8px; border: 1px solid #ccc; background-color: #f0f0f0; border-radius: 4px;")
        self.status_label.setMinimumHeight(30)
        self.status_label.setVisible(False)
        layout.addWidget(self.status_label)
        
        # Load file content
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            self.text_edit.setPlainText(content)
        except UnicodeDecodeError:
            # Try with different encoding
            try:
                with open(file_path, 'r', encoding='latin-1') as f:
                    content = f.read()
                self.text_edit.setPlainText(content)
            except Exception as e:
                self.text_edit.setPlainText(f"Error reading file: {str(e)}")
        except Exception as e:
            self.text_edit.setPlainText(f"Error reading file: {str(e)}")
        
        # Button row
        btn_layout = QtWidgets.QHBoxLayout()
        
        save_btn = QtWidgets.QPushButton("Save")
        save_btn.clicked.connect(self.save_file)
        btn_layout.addWidget(save_btn)
        
        close_btn = QtWidgets.QPushButton("Close")
        close_btn.clicked.connect(self.close)
        btn_layout.addWidget(close_btn)
        
        layout.addLayout(btn_layout)
        
        self.file_path = file_path
        self.original_content = self.text_edit.toPlainText()
    
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
    
    def save_file(self):
        try:
            content = self.text_edit.toPlainText()
            with open(self.file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            # Emit signal to notify parent about the save
            self.file_saved.emit(self.file_path, content)
            
            self.show_message("File saved successfully", "success")
        except Exception as e:
            self.show_message(f"Failed to save file: {str(e)}", "error")
    
    def closeEvent(self, event):
        # Check if content has changed
        current_content = self.text_edit.toPlainText()
        if current_content != self.original_content:
            reply = QtWidgets.QMessageBox.question(
                self, 
                "Save Changes?", 
                "The file has been modified. Do you want to save the changes?",
                QtWidgets.QMessageBox.StandardButton.Save | 
                QtWidgets.QMessageBox.StandardButton.Discard | 
                QtWidgets.QMessageBox.StandardButton.Cancel
            )
            
            if reply == QtWidgets.QMessageBox.StandardButton.Save:
                self.save_file()
                event.accept()
            elif reply == QtWidgets.QMessageBox.StandardButton.Discard:
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()
