from PySide6.QtWidgets import (
    QApplication,
    QWidget,
    QListWidget,
    QLabel,
    QVBoxLayout,
    QHBoxLayout,
    QLineEdit,
    QAbstractItemView,
)

from src.database_service import load_songs, update_song
from src.tags import read_grouping, save_grouping, parse_grouping
from src.widgets.tag_panel import TagPanel


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

        self.selected_counter = QLabel("Wybrano: 0 utworów")
        left.addWidget(self.selected_counter)

        self.song_list = QListWidget()
        self.song_list.setSelectionMode(
            QAbstractItemView.ExtendedSelection
        )

        for song in self.filtered_songs:
            self.song_list.addItem(
                f"{song.artist}\n{song.title}"
            )

        self.song_list.currentRowChanged.connect(
            self.song_selected
        )
        self.song_list.itemSelectionChanged.connect(
            self.selection_changed
        )

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
        self.tag_panel.tags_changed.connect(self.tags_changed)

        main_layout.addWidget(self.tag_panel, 2)

        self.setLayout(main_layout)

        self.counter.setText(
            f"Znaleziono: {len(self.filtered_songs)} utworów"
        )

        self.update_selected_counter()

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

        self.update_selected_counter()

        if self.filtered_songs:
            self.song_list.setCurrentRow(0)
        else:
            self.current_song = None
            self.current_grouping = ""
            self.tag_panel.load_song("")

    # =====================================================

    def update_selected_counter(self):

        count = len(self.song_list.selectedItems())

        if count == 1:
            text = "Wybrano: 1 utwór"
        else:
            text = f"Wybrano: {count} utworów"

        self.selected_counter.setText(text)

    # =====================================================

    def get_selected_songs(self):

        songs = []

        for item in self.song_list.selectedItems():
            row = self.song_list.row(item)

            if 0 <= row < len(self.filtered_songs):
                songs.append(self.filtered_songs[row])

        return songs

    # =====================================================

    def selection_changed(self):

        self.update_selected_counter()

        selected_songs = self.get_selected_songs()

        if not selected_songs:
            return

        if len(selected_songs) > 1:
            self.tag_panel.load_songs(
                [
                    read_grouping(song.path)
                    for song in selected_songs
                ]
            )

    # =====================================================

    def song_selected(self, index):

        if index < 0:
            return

        if index >= len(self.filtered_songs):
            return

        self.current_song = self.filtered_songs[index]

        self.title.setText(self.current_song.title)
        self.artist.setText(self.current_song.artist)
        self.album.setText(self.current_song.album)

        grouping = read_grouping(self.current_song.path)
        self.current_grouping = grouping

        selected_songs = self.get_selected_songs()

        if len(selected_songs) > 1:
            self.tag_panel.load_songs(
                [
                    read_grouping(song.path)
                    for song in selected_songs
                ]
            )
        else:
            self.tag_panel.load_song(grouping)

    # =====================================================

    def tags_changed(self):

        selected_songs = self.get_selected_songs()

        if not selected_songs:
            return

        changes = self.tag_panel.get_changes()

        if not changes:
            return

        for song in selected_songs:

            song_tags = parse_grouping(
                read_grouping(song.path)
            )

            for category, value, should_have in changes:

                values = song_tags.setdefault(category, [])

                if should_have:
                    if value not in values:
                        values.append(value)
                else:
                    if value in values:
                        values.remove(value)

            new_grouping = save_grouping(
                song.path,
                song_tags
            )

            song.grouping = new_grouping
            update_song(song)

        self.current_grouping = read_grouping(
            self.current_song.path
        )

        self.tag_panel.set_baseline(
            [
                read_grouping(song.path)
                for song in selected_songs
            ]
        )


def run_gui():

    app = QApplication([])

    window = MainWindow()
    window.show()

    app.exec()
