import sys
from pathlib import Path

try:
    from PyQt6 import QtWidgets, QtGui, QtCore
except Exception as e:
    print("[!] PyQt6 not installed. pip install PyQt6")
    sys.exit(1)

class TextEditor(QtWidgets.QDialog):
    def __init__(self, file_path: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Text Editor - {Path(file_path).name}")
        self.resize(900, 700)
        
        layout = QtWidgets.QVBoxLayout(self)
        
        # Text editor
        self.text_edit = QtWidgets.QTextEdit()
        self.text_edit.setFont(QtGui.QFont("Consolas", 10))
        layout.addWidget(self.text_edit)
        
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
    
    def save_file(self):
        try:
            content = self.text_edit.toPlainText()
            with open(self.file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            QtWidgets.QMessageBox.information(self, "Success", "File saved successfully!")
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error", f"Failed to save file: {str(e)}")
