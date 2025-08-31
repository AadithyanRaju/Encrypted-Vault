import sys
import os
from pathlib import Path

try:
    from PyQt6 import QtWidgets, QtGui, QtCore, QtMultimediaWidgets, QtMultimedia
except Exception as e:
    print("[!] PyQt6 not installed. pip install PyQt6")
    sys.exit(1)

class AudioPlayer(QtWidgets.QDialog):
    def __init__(self, audio_path: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Audio Player" + " - " + Path(audio_path).name)
        self.resize(800, 100)
        self.audio_path = audio_path
        if not Path(self.audio_path).exists():
            QtWidgets.QMessageBox.critical(self, "Error", f"File not found:\n{self.audio_path}")
            return

        # Player and audio output
        self.player = QtMultimedia.QMediaPlayer(self)
        self.audio_output = QtMultimedia.QAudioOutput(self)
        self.player.setAudioOutput(self.audio_output)
        self.audio_output.setVolume(0.5)

        # Load source
        url = QtCore.QUrl.fromLocalFile(str(Path(self.audio_path).absolute()))
        self.player.setSource(url)

        # UI widgets
        self.play_btn = QtWidgets.QPushButton("Play")
        self.stop_btn = QtWidgets.QPushButton("Stop")
        self.position_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.position_slider.setRange(0, 0)
        self.time_label = QtWidgets.QLabel("00:00 / 00:00")
        self.volume_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(int(self.audio_output.volume() * 100))

        # Layout
        controls = QtWidgets.QHBoxLayout()
        controls.addWidget(self.play_btn)
        controls.addWidget(self.stop_btn)
        controls.addWidget(self.position_slider)
        controls.addWidget(self.time_label)
        controls.addWidget(QtWidgets.QLabel("Vol"))
        controls.addWidget(self.volume_slider)

        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.addLayout(controls)

        # Helpers
        def ms_to_time(ms: int) -> str:
            s = int(ms // 1000)
            m = s // 60
            s = s % 60
            return f"{m:02d}:{s:02d}"

        def update_time_label():
            pos = int(self.player.position())
            dur = int(self.player.duration())
            self.time_label.setText(f"{ms_to_time(pos)} / {ms_to_time(dur if dur > 0 else 0)}")

        def toggle_play():
            state = self.player.playbackState()
            playing = state == QtMultimedia.QMediaPlayer.PlaybackState.PlayingState
            if playing:
                self.player.pause()
                self.play_btn.setText("Play")
            else:
                self.player.play()
                self.play_btn.setText("Pause")

        # Connections
        self.play_btn.clicked.connect(toggle_play)
        self.stop_btn.clicked.connect(self.player.stop)
        # Track when user is dragging the slider to avoid conflict with positionChanged updates
        self._slider_is_pressed = False
        self.position_slider.sliderPressed.connect(lambda: setattr(self, '_slider_is_pressed', True))
        # While dragging, show preview time
        self.position_slider.sliderMoved.connect(lambda p: self.time_label.setText(f"{ms_to_time(p)} / {ms_to_time(self.player.duration() if self.player.duration() > 0 else 0)}"))
        # On release, set player position and resume updates
        def _on_slider_released():
            pos = int(self.position_slider.value())
            try:
                self.player.setPosition(pos)
            except Exception:
                pass
            setattr(self, '_slider_is_pressed', False)

        self.position_slider.sliderReleased.connect(_on_slider_released)

        self.volume_slider.valueChanged.connect(lambda v: self.audio_output.setVolume(v / 100.0))

        def _on_position_changed(p):
            # Only update slider while user is not interacting with it
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

        self.player.positionChanged.connect(_on_position_changed)
        self.player.durationChanged.connect(_on_duration_changed)

        # initialize label
        update_time_label()