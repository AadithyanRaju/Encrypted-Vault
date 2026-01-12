import sys
from pathlib import Path

try:
    from PyQt6 import QtWidgets, QtGui, QtCore
except Exception as e:
    print("[!] PyQt6 not installed. pip install PyQt6")
    sys.exit(1)

class ImageViewer(QtWidgets.QDialog):
    ZOOM_FACTOR = 1.15  # Zoom step factor for buttons and wheel
    
    def __init__(self, image_path: str, parent=None):
        super().__init__(parent)
        self._filename = Path(image_path).name
        self.setWindowTitle(f"Image Viewer - {self._filename}")
        self.resize(800, 600)
        self._pixmap_orig = None
        self._scale = 1.0
        self._min_scale = 0.1
        self._max_scale = 4.0
        
        layout = QtWidgets.QVBoxLayout(self)
        
        # Image label with scroll area
        scroll_area = QtWidgets.QScrollArea()
        self.scroll_area = scroll_area
        self.image_label = QtWidgets.QLabel()
        self.image_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.image_label.setBackgroundRole(QtGui.QPalette.ColorRole.Base)
        self.image_label.setSizePolicy(QtWidgets.QSizePolicy.Policy.Ignored, QtWidgets.QSizePolicy.Policy.Ignored)
        self.image_label.setScaledContents(False)
        
        # Load and display image
        pixmap = QtGui.QPixmap(image_path)
        if pixmap.isNull():
            self.image_label.setText("Failed to load image")
        else:
            self._pixmap_orig = pixmap
            self.image_label.setPixmap(self._pixmap_orig)
            self._scale = 1.0
        
        scroll_area.setWidget(self.image_label)
        scroll_area.setWidgetResizable(False)
        scroll_area.viewport().installEventFilter(self)
        layout.addWidget(scroll_area)

        # Zoom controls
        controls = QtWidgets.QHBoxLayout()
        self.zoom_out_btn = QtWidgets.QPushButton("-")
        self.zoom_out_btn.setToolTip("Zoom Out")
        self.zoom_in_btn = QtWidgets.QPushButton("+")
        self.zoom_in_btn.setToolTip("Zoom In")
        self.fit_btn = QtWidgets.QPushButton("Fit")
        self.fit_btn.setToolTip("Fit to window")
        self.actual_btn = QtWidgets.QPushButton("100%")
        self.actual_btn.setToolTip("Actual size")
        self.zoom_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.zoom_slider.setMinimum(10)
        self.zoom_slider.setMaximum(400)
        self.zoom_slider.setValue(100)
        self.zoom_slider.setTickPosition(QtWidgets.QSlider.TickPosition.NoTicks)
        self.zoom_slider.setSingleStep(5)
        controls.addWidget(self.zoom_out_btn)
        controls.addWidget(self.zoom_in_btn)
        controls.addWidget(QtWidgets.QLabel("Zoom"))
        controls.addWidget(self.zoom_slider, 1)
        controls.addWidget(self.fit_btn)
        controls.addWidget(self.actual_btn)
        layout.addLayout(controls)
        
        # Close button
        close_btn = QtWidgets.QPushButton("Close")
        close_btn.clicked.connect(self.close)
        layout.addWidget(close_btn)

        # Wire controls
        self.zoom_in_btn.clicked.connect(lambda: self._zoom_by(self.ZOOM_FACTOR))
        self.zoom_out_btn.clicked.connect(lambda: self._zoom_by(1.0/self.ZOOM_FACTOR))
        self.fit_btn.clicked.connect(self._fit_to_window)
        self.actual_btn.clicked.connect(self._actual_size)
        self.zoom_slider.valueChanged.connect(self._slider_changed)

        # Initial fit
        if self._pixmap_orig is not None:
            self._fit_to_window()

    def eventFilter(self, obj, event):
        # Only zoom when Ctrl is held; otherwise let wheel scroll normally
        if obj is self.scroll_area.viewport() and isinstance(event, QtGui.QWheelEvent):
            if self._pixmap_orig is None:
                return False
            if event.modifiers() & QtCore.Qt.KeyboardModifier.ControlModifier:
                delta = event.angleDelta().y()
                if delta == 0:
                    return False
                factor = self.ZOOM_FACTOR if delta > 0 else (1.0/self.ZOOM_FACTOR)
                self._zoom_by(factor)
                event.accept()
                return True
            # No Ctrl: allow default scroll behavior
            return False
        return super().eventFilter(obj, event)

    def _update_pixmap_scaled(self):
        if self._pixmap_orig is None:
            return
        scaled_width = max(1, int(self._pixmap_orig.width() * self._scale))
        scaled_height = max(1, int(self._pixmap_orig.height() * self._scale))
        scaled = self._pixmap_orig.scaled(scaled_width, scaled_height, QtCore.Qt.AspectRatioMode.KeepAspectRatio, QtCore.Qt.TransformationMode.SmoothTransformation)
        self.image_label.setPixmap(scaled)
        self.image_label.setFixedSize(scaled.size())
        val = int(round(self._scale * 100))
        if val != self.zoom_slider.value():
            old_block_state = self.zoom_slider.blockSignals(True)
            try:
                self.zoom_slider.setValue(max(self.zoom_slider.minimum(), min(self.zoom_slider.maximum(), val)))
            finally:
                self.zoom_slider.blockSignals(old_block_state)
        self.setWindowTitle(f"Image Viewer - {self.windowTitle().split(' - ')[-1].split(' (')[0]} ({int(self._scale*100)}%)")

    def _set_scale(self, scale: float):
        clamped_scale = max(self._min_scale, min(self._max_scale, scale))
        if abs(clamped_scale - self._scale) < 1e-6:
            return
        self._scale = clamped_scale
        self._update_pixmap_scaled()

    def _zoom_by(self, factor: float):
        if self._pixmap_orig is None:
            return
        self._set_scale(self._scale * factor)

    def _slider_changed(self, val: int):
        self._set_scale(val / 100.0)

    def _fit_to_window(self):
        if self._pixmap_orig is None:
            return
        vp = self.scroll_area.viewport().size()
        if self._pixmap_orig.width() == 0 or self._pixmap_orig.height() == 0:
            return
        scale_x = vp.width() / self._pixmap_orig.width()
        scale_y = vp.height() / self._pixmap_orig.height()
        self._set_scale(max(self._min_scale, min(self._max_scale, min(scale_x, scale_y))))

    def _actual_size(self):
        if self._pixmap_orig is None:
            return
        self._set_scale(1.0)
