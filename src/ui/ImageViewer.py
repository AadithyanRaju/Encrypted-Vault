import sys
from pathlib import Path

try:
    from PyQt6 import QtWidgets, QtGui, QtCore
except Exception as e:
    print("[!] PyQt6 not installed. pip install PyQt6")
    sys.exit(1)

class ImageViewer(QtWidgets.QDialog):
    # Epsilon for floating-point scale comparison
    SCALE_EPSILON = 1e-6
    ZOOM_FACTOR = 1.15  # Zoom step factor for buttons and wheel
    
    # Slider constants (in percentage)
    SLIDER_MIN_PERCENT = 10
    SLIDER_MAX_PERCENT = 400
    SLIDER_STEP = 5
    SLIDER_DEFAULT_PERCENT = 100
    
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
        self._image_loaded = False
        pixmap = QtGui.QPixmap(image_path)
        if pixmap.isNull():
            self.image_label.setText("Failed to load image")
        else:
            self._pixmap_orig = pixmap
            self.image_label.setPixmap(self._pixmap_orig)
            self._scale = 1.0
            self._image_loaded = True
        
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
        self.zoom_slider.setMinimum(self.SLIDER_MIN_PERCENT)
        self.zoom_slider.setMaximum(self.SLIDER_MAX_PERCENT)
        self.zoom_slider.setValue(self.SLIDER_DEFAULT_PERCENT)
        self.zoom_slider.setTickPosition(QtWidgets.QSlider.TickPosition.NoTicks)
        self.zoom_slider.setSingleStep(self.SLIDER_STEP)
        controls.addWidget(self.zoom_out_btn)
        controls.addWidget(self.zoom_in_btn)
        controls.addWidget(QtWidgets.QLabel("Zoom"))
        controls.addWidget(self.zoom_slider, 1)
        controls.addWidget(self.fit_btn)
        controls.addWidget(self.actual_btn)
        layout.addLayout(controls)
        
        # Disable zoom controls if image loading failed
        if not self._image_loaded:
            self.zoom_out_btn.setEnabled(False)
            self.zoom_in_btn.setEnabled(False)
            self.fit_btn.setEnabled(False)
            self.actual_btn.setEnabled(False)
            self.zoom_slider.setEnabled(False)
        
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

        # Initial fit - deferred to ensure viewport has correct size
        if self._pixmap_orig is not None:
            QtCore.QTimer.singleShot(0, self._fit_to_window)

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

    def _update_pixmap_scaled(self, smooth: bool = True):
        if self._pixmap_orig is None:
            return
        scaled_width = max(1, int(self._pixmap_orig.width() * self._scale))
        scaled_height = max(1, int(self._pixmap_orig.height() * self._scale))
        transformation_mode = (
            QtCore.Qt.TransformationMode.SmoothTransformation
            if smooth
            else QtCore.Qt.TransformationMode.FastTransformation
        )
        scaled = self._pixmap_orig.scaled(
            scaled_width,
            scaled_height,
            QtCore.Qt.AspectRatioMode.KeepAspectRatio,
            transformation_mode,
        )
        self.image_label.setPixmap(scaled)
        self.image_label.setFixedSize(scaled.size())
        val = int(round(self._scale * 100))
        if val != self.zoom_slider.value():
            old_block_state = self.zoom_slider.blockSignals(True)
            try:
                self.zoom_slider.setValue(max(self.zoom_slider.minimum(), min(self.zoom_slider.maximum(), val)))
            finally:
                self.zoom_slider.blockSignals(old_block_state)
        self.setWindowTitle(f"Image Viewer - {self._filename} ({int(self._scale*100)}%)")

    def _set_scale(self, scale: float, smooth: bool = True):
        clamped_scale = max(self._min_scale, min(self._max_scale, scale))
        if abs(clamped_scale - self._scale) < self.SCALE_EPSILON:
            return
        self._scale = clamped_scale
        self._update_pixmap_scaled(smooth=smooth)

    def _zoom_by(self, factor: float):
        if self._pixmap_orig is None:
            return
        # Use fast transformation during interactive zooming for better performance
        self._set_scale(self._scale * factor, smooth=False)

    def _slider_changed(self, val: int):
        # Slider changes are typically interactive; use fast scaling for responsiveness
        self._set_scale(val / 100.0, smooth=False)

    def _fit_to_window(self):
        if self._pixmap_orig is None:
            return
        viewport_size = self.scroll_area.viewport().size()
        if self._pixmap_orig.width() == 0 or self._pixmap_orig.height() == 0:
            # Avoid division by zero and keep the viewer in a consistent state.
            # Set a reasonable default scale and notify the user that the image is invalid.
            try:
                QtWidgets.QMessageBox.warning(
                    self,
                    "Invalid image size",
                    "Cannot fit image to window because it has zero width or height.\n"
                    "Showing the image at 100% zoom instead."
                )
            except RuntimeError:
                # If the message box cannot be shown (e.g., in headless environments),
                # still ensure a valid scale is set.
                pass
            self._set_scale(1.0)
            return
        scale_x = viewport_size.width() / self._pixmap_orig.width()
        scale_y = viewport_size.height() / self._pixmap_orig.height()
        self._set_scale(max(self._min_scale, min(self._max_scale, min(scale_x, scale_y))))

    def _actual_size(self):
        if self._pixmap_orig is None:
            return
        self._set_scale(1.0)
