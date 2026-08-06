from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLineEdit,
    QLabel,
    QListWidget,
)


class SongListWidget(QWidget):
    def __init__(self):
        super().__init__()

        layout = QVBoxLayout(self)

        self.search = QLineEdit()
        self.search.setPlaceholderText("🔍 Szukaj...")

        self.counter = QLabel()

        self.list = QListWidget()

        layout.addWidget(self.search)
        layout.addWidget(self.counter)
        layout.addWidget(self.list)

    def clear(self):
        self.list.clear()

    def add_song(self, song):

        self.list.addItem(
            f"{song.artist}\n{song.title}"
        )

    def set_counter(self, count):

        self.counter.setText(
            f"Znaleziono: {count} utworów"
        )