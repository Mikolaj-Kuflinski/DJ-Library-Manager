from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer


class AudioPlayerService(QObject):
    """Small playback engine kept outside the GUI layer."""

    position_changed = Signal(int)
    duration_changed = Signal(int)
    playing_changed = Signal(bool)
    error_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.audio_output = QAudioOutput(self)
        self.player = QMediaPlayer(self)
        self.player.setAudioOutput(self.audio_output)

        self.player.positionChanged.connect(self.position_changed.emit)
        self.player.durationChanged.connect(self.duration_changed.emit)
        self.player.playbackStateChanged.connect(self._state_changed)
        self.player.errorOccurred.connect(self._error)

    def _state_changed(self, state):
        self.playing_changed.emit(
            state == QMediaPlayer.PlaybackState.PlayingState
        )

    def _error(self, _error, error_string):
        if error_string:
            self.error_changed.emit(error_string)

    def load(self, path):
        if not path:
            self.stop()
            return False
        self.player.setSource(QUrl.fromLocalFile(str(path)))
        return True

    def play(self):
        self.player.play()

    def pause(self):
        self.player.pause()

    def toggle(self):
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.pause()
        else:
            self.play()

    def stop(self):
        self.player.stop()

    def seek(self, position):
        self.player.setPosition(max(0, int(position)))

    def seek_relative(self, milliseconds):
        current = self.player.position()
        duration = self.player.duration()
        target = current + int(milliseconds)
        if duration > 0:
            target = min(target, duration)
        self.player.setPosition(max(0, target))
        return target

    def set_volume(self, value):
        self.audio_output.setVolume(max(0.0, min(1.0, float(value) / 100.0)))

    def volume(self):
        return int(round(self.audio_output.volume() * 100))

    def position(self):
        return self.player.position()

    def duration(self):
        return self.player.duration()

    def is_playing(self):
        return (
            self.player.playbackState()
            == QMediaPlayer.PlaybackState.PlayingState
        )
