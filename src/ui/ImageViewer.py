import sys
from pathlib import Path

try:
    from PyQt6 import QtWidgets, QtGui, QtCore
except Exception as e:
    print("[!] PyQt6 not installed. pip install PyQt6")
    sys.exit(1)

class ImageViewer(QtWidgets.QDialog):
    def __init__(self, image_path: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Image Viewer - {Path(image_path).name}")
        self.resize(800, 600)
        
        layout = QtWidgets.QVBoxLayout(self)
        
        # Image label with scroll area
        scroll_area = QtWidgets.QScrollArea()
        self.image_label = QtWidgets.QLabel()
        self.image_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        
        # Load and display image
        pixmap = QtGui.QPixmap(image_path)
        if pixmap.isNull():
            self.image_label.setText("Failed to load image")
        else:
            # Scale image to fit window while maintaining aspect ratio
            scaled_pixmap = pixmap.scaled(
                scroll_area.size(), 
                QtCore.Qt.AspectRatioMode.KeepAspectRatio, 
                QtCore.Qt.TransformationMode.SmoothTransformation
            )
            self.image_label.setPixmap(scaled_pixmap)
        
        scroll_area.setWidget(self.image_label)
        layout.addWidget(scroll_area)
        
        # Close button
        close_btn = QtWidgets.QPushButton("Close")
        close_btn.clicked.connect(self.close)
        layout.addWidget(close_btn)
