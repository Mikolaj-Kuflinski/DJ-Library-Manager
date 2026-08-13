from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (
    QStyle,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)


class SeekSlider(QSlider):
    """Progress slider that seeks directly when clicked or dragged."""

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            value = QStyle.sliderValueFromPosition(
                self.minimum(),
                self.maximum(),
                int(event.position().x()),
                self.width(),
            )
            self.setValue(value)
            self.sliderMoved.emit(value)
            self.player_seek(value)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton:
            value = QStyle.sliderValueFromPosition(
                self.minimum(),
                self.maximum(),
                int(event.position().x()),
                self.width(),
            )
            self.setValue(value)
            self.sliderMoved.emit(value)
            self.player_seek(value)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def player_seek(self, value):
        # Assigned by PlayerWidget after construction.
        if hasattr(self, "_seek_callback"):
            self._seek_callback(value)


class PlayerWidget(QWidget):
    """Compact transport UI. Playback logic lives in AudioPlayerService."""

    # Arrow buttons are local seek controls; they no longer navigate tracks.

    def __init__(self, player_service, parent=None):
        super().__init__(parent)
        self.player_service = player_service
        self.skip_seconds = 5

        self.track_label = QLabel("Brak odtwarzanego utworu")
        self.track_label.setMinimumWidth(180)
        self.track_label.setMaximumWidth(260)

        self.time_label = QLabel("00:00 / 00:00")
        self.time_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.time_label.setMinimumWidth(82)

        self.position_slider = SeekSlider(Qt.Orientation.Horizontal)
        self.position_slider.setMinimumWidth(360)
        self.position_slider.setRange(0, 0)
        self.position_slider.setEnabled(False)
        self.position_slider._seek_callback = self._seek
        self.position_slider.sliderMoved.connect(self._seek)

        self.previous_button = QPushButton("↶")
        self.play_button = QPushButton("▶")
        self.next_button = QPushButton("↷")
        self.previous_button.setToolTip("Cofnij o ustawioną liczbę sekund")
        self.next_button.setToolTip("Przejdź do przodu o ustawioną liczbę sekund")
        for button in (
            self.previous_button,
            self.play_button,
            self.next_button,
        ):
            button.setFixedWidth(32)
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self.volume_label = QLabel("Głośność")
        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(self.player_service.volume())
        self.volume_slider.setMaximumWidth(100)

        self.previous_button.clicked.connect(self.skip_backward)
        self.play_button.clicked.connect(self.player_service.toggle)
        self.next_button.clicked.connect(self.skip_forward)
        self.volume_slider.valueChanged.connect(
            self.player_service.set_volume
        )

        transport = QHBoxLayout()
        transport.addWidget(self.previous_button)
        transport.addWidget(self.play_button)
        transport.addWidget(self.next_button)
        transport.addWidget(self.position_slider, 1)
        transport.addWidget(self.time_label)
        transport.addWidget(self.volume_label)
        transport.addWidget(self.volume_slider)

        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        top.addWidget(self.track_label, 1)
        top.addLayout(transport)
        layout.addLayout(top)

        self.player_service.position_changed.connect(self._position_changed)
        self.player_service.duration_changed.connect(self._duration_changed)
        self.player_service.playing_changed.connect(self._playing_changed)
        self.player_service.error_changed.connect(self._error_changed)

    def set_skip_seconds(self, seconds):
        try:
            self.skip_seconds = max(1, int(seconds))
        except (TypeError, ValueError):
            self.skip_seconds = 5

    def skip_backward(self):
        self.player_service.seek_relative(
            -self.skip_seconds * 1000
        )

    def skip_forward(self):
        self.player_service.seek_relative(
            self.skip_seconds * 1000
        )

    def set_track(self, artist, title):
        text = " — ".join(
            part for part in (artist or "", title or "") if part
        )
        self.track_label.setText(text or "Brak odtwarzanego utworu")

    def clear_track(self):
        self.track_label.setText("Brak odtwarzanego utworu")
        self.position_slider.setRange(0, 0)
        self.position_slider.setEnabled(False)
        self.time_label.setText("00:00 / 00:00")

    def _seek(self, position):
        self.player_service.seek(position)

    def _position_changed(self, position):
        if not self.position_slider.isSliderDown():
            self.position_slider.setValue(position)
        self._update_time(position, self.player_service.duration())

    def _duration_changed(self, duration):
        duration = max(0, duration)
        self.position_slider.setRange(0, duration)
        self.position_slider.setEnabled(duration > 0)
        self._update_time(self.player_service.position(), duration)

    def _playing_changed(self, playing):
        self.play_button.setText("⏸" if playing else "▶")

    def _error_changed(self, message):
        if message:
            self.track_label.setToolTip(message)

    @staticmethod
    def _format_time(milliseconds):
        total_seconds = max(0, int(milliseconds // 1000))
        minutes, seconds = divmod(total_seconds, 60)
        hours, minutes = divmod(minutes, 60)
        if hours:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        return f"{minutes:02d}:{seconds:02d}"

    def _update_time(self, position, duration):
        self.time_label.setText(
            f"{self._format_time(position)} / "
            f"{self._format_time(duration)}"
        )
