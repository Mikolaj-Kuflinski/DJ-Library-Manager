from PySide6.QtWidgets import (
    QApplication,
    QWidget,
    QListWidget,
    QLabel,
    QVBoxLayout,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
)

from src.database_service import load_songs, update_song
from src.tags import read_grouping, save_grouping
from src.tag_panel import TagPanel


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("DJ Library Manager")
        self.resize(1400, 750)

        self.songs = load_songs()
        self.filtered_songs = self.songs.copy()

        self.current_song = None
        self.current_grouping = ""

        main_layout = QHBoxLayout()

        # ==================================
        # LEWA STRONA
        # ==================================

        left = QVBoxLayout()

        self.search = QLineEdit()
        self.search.setPlaceholderText("🔍 Szukaj...")
        self.search.textChanged.connect(self.filter_songs)

        left.addWidget(self.search)

        self.counter = QLabel()
        left.addWidget(self.counter)

        self.song_list = QListWidget()

        for song in self.filtered_songs:
            self.song_list.addItem(f"{song.artist}\n{song.title}")

        self.song_list.currentRowChanged.connect(self.song_selected)

        left.addWidget(self.song_list)

        main_layout.addLayout(left, 1)

        # ==================================
        # ŚRODEK
        # ==================================

        center = QVBoxLayout()

        center.addWidget(QLabel("Tytuł"))
        self.title = QLineEdit()
        self.title.setReadOnly(True)
        center.addWidget(self.title)

        center.addWidget(QLabel("Artysta"))
        self.artist = QLineEdit()
        self.artist.setReadOnly(True)
        center.addWidget(self.artist)

        center.addWidget(QLabel("Album"))
        self.album = QLineEdit()
        self.album.setReadOnly(True)
        center.addWidget(self.album)

        main_layout.addLayout(center, 1)

        # ==================================
        # PRAWA STRONA
        # ==================================

        self.tag_panel = TagPanel()

        # przycisk zostaje jako ręczny zapis
        self.tag_panel.save_button.clicked.connect(self.save_current_song)

        main_layout.addWidget(self.tag_panel, 2)

        self.setLayout(main_layout)

        self.counter.setText(
            f"Znaleziono: {len(self.filtered_songs)} utworów"
        )

        if self.filtered_songs:
            self.song_list.setCurrentRow(0)

    # =====================================================

    def filter_songs(self, text):

        text = text.lower()

        self.filtered_songs = []

        self.song_list.blockSignals(True)
        self.song_list.clear()

        for song in self.songs:

            if (
                text in song.title.lower()
                or text in song.artist.lower()
            ):

                self.filtered_songs.append(song)

                self.song_list.addItem(
                    f"{song.artist}\n{song.title}"
                )

        self.song_list.blockSignals(False)

        self.counter.setText(
            f"Znaleziono: {len(self.filtered_songs)} utworów"
        )

        if self.filtered_songs:
            self.song_list.setCurrentRow(0)

    # =====================================================

    def song_selected(self, index):

        # AUTOZAPIS POPRZEDNIEGO
        self.save_if_changed()

        if index < 0:
            return

        self.current_song = self.filtered_songs[index]

        self.title.setText(self.current_song.title)
        self.artist.setText(self.current_song.artist)
        self.album.setText(self.current_song.album)

        grouping = read_grouping(self.current_song.path)

        self.current_grouping = grouping

        self.tag_panel.load_song(grouping)

    # =====================================================

    def save_if_changed(self):

        if self.current_song is None:
            return

        new_grouping = self.tag_panel.get_grouping()

        if new_grouping == self.current_grouping:
            return

        save_grouping(
            self.current_song.path,
            self.tag_panel.get_tags()
        )

        self.current_song.grouping = new_grouping

        update_song(self.current_song)

        self.current_grouping = new_grouping

    # =====================================================

    def save_current_song(self):

        self.save_if_changed()

        QMessageBox.information(
            self,
            "DJ Library Manager",
            "Tagi zapisane."
        )


def run_gui():
    app = QApplication([])

    window = MainWindow()
    window.show()

    app.exec()