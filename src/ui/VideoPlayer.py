import sys
import os
from pathlib import Path

try:
    from PyQt6 import QtWidgets, QtGui, QtCore, QtMultimediaWidgets, QtMultimedia
except Exception as e:
    print("[!] PyQt6 not installed. pip install PyQt6")
    sys.exit(1)

class VideoPlayer(QtWidgets.QDialog):
    def __init__(self, video_path: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Video Player")
        self.resize(800, 600)
        self.init_ui()
        self.load_video(video_path)

    def init_ui(self):
        self.video_widget = QtMultimediaWidgets.QVideoWidget(self)
        # Create audio output and media player
        self.audio_output = QtMultimedia.QAudioOutput(self)
        try:
            # set a reasonable default volume (0.0 - 1.0)
            self.audio_output.setVolume(0.6)
        except Exception:
            pass
        self.media_player = QtMultimedia.QMediaPlayer(self)
        self.media_player.setVideoOutput(self.video_widget)
        self.media_player.setAudioOutput(self.audio_output)

        self._temp_copy_path = None

        self.play_button = QtWidgets.QPushButton("Play", self)
        self.pause_button = QtWidgets.QPushButton("Pause", self)
        self.stop_button = QtWidgets.QPushButton("Stop", self)

        # Position slider and time label
        self.position_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal, self)
        self.position_slider.setRange(0, 0)
        self.time_label = QtWidgets.QLabel("00:00 / 00:00", self)

        # Volume slider
        self.volume_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal, self)
        self.volume_slider.setRange(0, 100)
        try:
            self.volume_slider.setValue(int(self.audio_output.volume() * 100))
        except Exception:
            self.volume_slider.setValue(60)

        # Layout
        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(self.video_widget)

        controls_row = QtWidgets.QHBoxLayout()
        controls_row.addWidget(self.play_button)
        controls_row.addWidget(self.pause_button)
        controls_row.addWidget(self.stop_button)
        controls_row.addWidget(self.position_slider)
        controls_row.addWidget(self.time_label)
        controls_row.addWidget(QtWidgets.QLabel("Vol", self))
        controls_row.addWidget(self.volume_slider)

        layout.addLayout(controls_row)

        self.setLayout(layout)

        # Helpers
        def ms_to_time(ms: int) -> str:
            s = int(ms // 1000)
            m = s // 60
            s = s % 60
            return f"{m:02d}:{s:02d}"

        def update_time_label():
            pos = int(self.media_player.position())
            dur = int(self.media_player.duration())
            self.time_label.setText(f"{ms_to_time(pos)} / {ms_to_time(dur if dur > 0 else 0)}")

        def toggle_play():
            state = self.media_player.playbackState()
            playing = state == QtMultimedia.QMediaPlayer.PlaybackState.PlayingState
            if playing:
                self.media_player.pause()
                self.play_button.setText("Play")
            else:
                self.media_player.play()
                self.play_button.setText("Pause")

        # Connect buttons
        self.play_button.clicked.connect(toggle_play)
        self.pause_button.clicked.connect(lambda: (self.media_player.pause(), self.play_button.setText("Play")))
        self.stop_button.clicked.connect(lambda: (self.media_player.stop(), self.play_button.setText("Play")))

        # Slider interaction state
        self._slider_is_pressed = False
        self.position_slider.sliderPressed.connect(lambda: setattr(self, '_slider_is_pressed', True))
        self.position_slider.sliderMoved.connect(lambda p: self.time_label.setText(f"{ms_to_time(p)} / {ms_to_time(self.media_player.duration() if self.media_player.duration() > 0 else 0)}"))
        def _on_slider_released():
            pos = int(self.position_slider.value())
            try:
                self.media_player.setPosition(pos)
            except Exception:
                pass
            setattr(self, '_slider_is_pressed', False)
        self.position_slider.sliderReleased.connect(_on_slider_released)

        # Volume control
        self.volume_slider.valueChanged.connect(lambda v: self.audio_output.setVolume(v / 100.0))

        # Update UI from player signals
        def _on_position_changed(p):
            if not getattr(self, '_slider_is_pressed', False):
                try:
                    self.position_slider.setValue(int(p))
                except Exception:
                    pass
            update_time_label()

        def _on_duration_changed(d):
            try:
                self.position_slider.setRange(0, int(d))
            except Exception:
                pass
            update_time_label()

        self.media_player.positionChanged.connect(_on_position_changed)
        self.media_player.durationChanged.connect(_on_duration_changed)

    def load_video(self, video_path: str):
        try:
            import shutil
            import tempfile
            try:
                if self._temp_copy_path and os.path.exists(self._temp_copy_path):
                    os.remove(self._temp_copy_path)
            except Exception:pass

            suffix = Path(video_path).suffix
            fd, tmpname = tempfile.mkstemp(suffix=suffix)
            os.close(fd)
            shutil.copy2(video_path, tmpname)
            self._temp_copy_path = tmpname
            url = QtCore.QUrl.fromLocalFile(self._temp_copy_path)
            self.media_player.setSource(url)
            self.media_player.play()
        except Exception as e:
            url = QtCore.QUrl.fromLocalFile(video_path)
            self.media_player.setSource(url)
            self.media_player.play()

    def closeEvent(self, event):
        try:self.media_player.stop()
        except Exception:pass
        try:
            if self._temp_copy_path and os.path.exists(self._temp_copy_path):
                os.remove(self._temp_copy_path)
        except Exception:pass
        return super().closeEvent(event)

    def _on_media_error(self, err, err_str):
        QtWidgets.QMessageBox.warning(self, "Playback error", f"Player error: {err_str}\nFalling back to external player.")
        try:
            import os
            os.startfile(self._temp_copy_path)  # Windows: opens with default app (VLC if installed)
        except Exception:
            pass

    def __del__(self):
        try:
            self.media_player.errorOccurred.disconnect(self._on_media_error)
        except Exception:
            pass

