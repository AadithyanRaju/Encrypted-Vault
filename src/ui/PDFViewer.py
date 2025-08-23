import sys
from pathlib import Path

try:
    from PyQt6 import QtWidgets, QtGui, QtCore
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
    from PyQt6.QtCore import QUrl
    WEBENGINE_AVAILABLE = True
except Exception as e:
    print("[!] PyQt6 WebEngine not available, using fallback method")
    WEBENGINE_AVAILABLE = False

class PDFViewer(QtWidgets.QDialog):
    def __init__(self, pdf_path: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"PDF Viewer - {Path(pdf_path).name}")
        self.resize(1200, 900)
        
        # Set minimum size to prevent too small windows
        self.setMinimumSize(800, 600)
        
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)
        
        if WEBENGINE_AVAILABLE:
            self.setup_webengine_view(pdf_path, layout)
        else:
            self.setup_fallback_view(pdf_path, layout)
        
        self.pdf_path = pdf_path
        self.zoom_factor = 1.0
    
    def setup_webengine_view(self, pdf_path: str, layout: QtWidgets.QVBoxLayout):
        """Setup WebEngine-based PDF viewer."""
        # Create web engine page with proper settings
        self.web_page = QWebEnginePage()
        self.web_page.settings().setAttribute(QWebEngineSettings.WebAttribute.PluginsEnabled, True)
        self.web_page.settings().setAttribute(QWebEngineSettings.WebAttribute.PdfViewerEnabled, True)
        
        # Web engine view for PDF display
        self.web_view = QWebEngineView()
        self.web_view.setPage(self.web_page)
        
        # Set minimum size for web view to ensure it's visible
        self.web_view.setMinimumSize(600, 400)
        
        # Convert file path to URL format
        pdf_url = QUrl.fromLocalFile(pdf_path)
        
        # Load PDF in the web view
        self.web_view.load(pdf_url)
        
        # Connect load finished signal to check if PDF loaded successfully
        self.web_view.loadFinished.connect(self.on_load_finished)
        
        # Add web view to layout with stretch to take up available space
        layout.addWidget(self.web_view, 1)  # Stretch factor of 1
        
        # Status label
        self.status_label = QtWidgets.QLabel("Loading PDF...")
        self.status_label.setMaximumHeight(30)
        layout.addWidget(self.status_label)
        
        # Button row
        btn_layout = QtWidgets.QHBoxLayout()
        btn_layout.setSpacing(10)
        
        # Zoom controls
        zoom_in_btn = QtWidgets.QPushButton("Zoom In")
        zoom_in_btn.setMinimumWidth(80)
        zoom_in_btn.clicked.connect(self.zoom_in)
        btn_layout.addWidget(zoom_in_btn)
        
        zoom_out_btn = QtWidgets.QPushButton("Zoom Out")
        zoom_out_btn.setMinimumWidth(80)
        zoom_out_btn.clicked.connect(self.zoom_out)
        btn_layout.addWidget(zoom_out_btn)
        
        # Reload button
        reload_btn = QtWidgets.QPushButton("Reload")
        reload_btn.setMinimumWidth(80)
        reload_btn.clicked.connect(self.reload_pdf)
        btn_layout.addWidget(reload_btn)
        
        btn_layout.addStretch()
        
        # Close button
        close_btn = QtWidgets.QPushButton("Close")
        close_btn.setMinimumWidth(80)
        close_btn.clicked.connect(self.close)
        btn_layout.addWidget(close_btn)
        
        layout.addLayout(btn_layout)
    
    def setup_fallback_view(self, pdf_path: str, layout: QtWidgets.QVBoxLayout):
        """Setup fallback PDF viewer using external application."""
        # Info label
        info_label = QtWidgets.QLabel(
            "PDF Viewer requires PyQt6-WebEngine.\n"
            "Please install it with: pip install PyQt6-WebEngine\n\n"
            f"PDF file: {Path(pdf_path).name}\n"
            f"Location: {pdf_path}"
        )
        info_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        info_label.setStyleSheet("font-size: 14px; padding: 20px;")
        layout.addWidget(info_label)
        
        # Button row
        btn_layout = QtWidgets.QHBoxLayout()
        
        # Open with default app button
        open_btn = QtWidgets.QPushButton("Open with Default App")
        open_btn.clicked.connect(lambda: self.open_with_default_app(pdf_path))
        btn_layout.addWidget(open_btn)
        
        btn_layout.addStretch()
        
        # Close button
        close_btn = QtWidgets.QPushButton("Close")
        close_btn.clicked.connect(self.close)
        btn_layout.addWidget(close_btn)
        
        layout.addLayout(btn_layout)
    
    def open_with_default_app(self, pdf_path: str):
        """Open PDF with system default application."""
        try:
            import subprocess
            import platform
            import os
            
            if platform.system() == "Windows":
                os.startfile(pdf_path)
            elif platform.system() == "Darwin":  # macOS
                subprocess.run(["open", pdf_path])
            else:  # Linux
                subprocess.run(["xdg-open", pdf_path])
                
            QtWidgets.QMessageBox.information(self, "Success", "PDF opened with default application")
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error", f"Failed to open PDF: {str(e)}")
    
    def on_load_finished(self, success):
        """Handle when PDF load is finished."""
        if success:
            self.status_label.setText("PDF loaded successfully")
            self.status_label.setStyleSheet("color: green;")
        else:
            self.status_label.setText("Failed to load PDF")
            self.status_label.setStyleSheet("color: red;")
    
    def zoom_in(self):
        """Increase zoom level."""
        if hasattr(self, 'web_view'):
            self.zoom_factor *= 1.2
            self.web_view.setZoomFactor(self.zoom_factor)
    
    def zoom_out(self):
        """Decrease zoom level."""
        if hasattr(self, 'web_view'):
            self.zoom_factor /= 1.2
            self.web_view.setZoomFactor(self.zoom_factor)
    
    def reload_pdf(self):
        """Reload the PDF file."""
        if hasattr(self, 'web_view'):
            self.status_label.setText("Reloading PDF...")
            self.status_label.setStyleSheet("")
            pdf_url = QUrl.fromLocalFile(self.pdf_path)
            self.web_view.load(pdf_url)
