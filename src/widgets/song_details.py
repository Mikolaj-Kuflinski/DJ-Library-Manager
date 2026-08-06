from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QLineEdit,
)


class SongDetailsWidget(QWidget):
    def __init__(self):
        super().__init__()

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("Tytuł"))
        self.title = QLineEdit()
        self.title.setReadOnly(True)
        layout.addWidget(self.title)

        layout.addWidget(QLabel("Artysta"))
        self.artist = QLineEdit()
        self.artist.setReadOnly(True)
        layout.addWidget(self.artist)

        layout.addWidget(QLabel("Album"))
        self.album = QLineEdit()
        self.album.setReadOnly(True)
        layout.addWidget(self.album)

    def set_song(self, song):
        self.title.setText(song.title)
        self.artist.setText(song.artist)
        self.album.setText(song.album)

    def clear(self):
        self.title.clear()
        self.artist.clear()
        self.album.clear()