from PySide6.QtWidgets import (
    QApplication, QWidget, QListWidget, QLabel, QVBoxLayout, QHBoxLayout,
    QLineEdit, QAbstractItemView, QPushButton, QComboBox,
)
from PySide6.QtGui import QKeySequence, QShortcut

from src.database_service import load_songs, update_song
from src.tags import read_grouping, save_grouping, parse_grouping
from src.config import get_available_tags
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

        self.undo_stack = []
        self.redo_stack = []
        self._history_busy = False
        self.available_tags = get_available_tags()

        main_layout = QHBoxLayout()

        # LEWA STRONA
        left = QVBoxLayout()

        self.search = QLineEdit()
        self.search.setPlaceholderText("🔍 Szukaj artysty / tytułu...")
        self.search.textChanged.connect(self.apply_filters)
        left.addWidget(self.search)

        left.addWidget(QLabel("Filtr tagów"))

        self.category_filter = QComboBox()
        self.category_filter.addItem("Wszystkie kategorie", "")
        for category in self.available_tags.keys():
            self.category_filter.addItem(category, category)
        self.category_filter.currentIndexChanged.connect(
            self.category_filter_changed
        )
        left.addWidget(self.category_filter)

        self.tag_filter = QComboBox()
        self.tag_filter.addItem("Wszystkie tagi", "")
        self.tag_filter.currentIndexChanged.connect(self.apply_filters)
        left.addWidget(self.tag_filter)

        self.clear_filters_button = QPushButton("✕ Wyczyść filtry")
        self.clear_filters_button.clicked.connect(self.clear_filters)
        left.addWidget(self.clear_filters_button)

        self.counter = QLabel()
        left.addWidget(self.counter)

        self.selected_counter = QLabel("Wybrano: 0 utworów")
        left.addWidget(self.selected_counter)

        self.song_list = QListWidget()
        self.song_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.song_list.currentRowChanged.connect(self.song_selected)
        self.song_list.itemSelectionChanged.connect(self.selection_changed)
        left.addWidget(self.song_list)

        main_layout.addLayout(left, 1)

        # ŚRODEK
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

        # PRAWA STRONA
        self.tag_panel = TagPanel()
        self.tag_panel.tags_changed.connect(self.tags_changed)
        main_layout.addWidget(self.tag_panel, 2)

        self.setLayout(main_layout)

        # UNDO / REDO
        undo_row = QHBoxLayout()
        self.undo_button = QPushButton("↶ Cofnij")
        self.redo_button = QPushButton("↷ Ponów")
        self.undo_button.clicked.connect(self.undo)
        self.redo_button.clicked.connect(self.redo)
        undo_row.addWidget(self.undo_button)
        undo_row.addWidget(self.redo_button)
        main_layout.addLayout(undo_row)

        self.undo_shortcut = QShortcut(QKeySequence("Ctrl+Z"), self)
        self.undo_shortcut.activated.connect(self.undo)
        self.redo_shortcut = QShortcut(QKeySequence("Ctrl+Shift+Z"), self)
        self.redo_shortcut.activated.connect(self.redo)

        self.update_history_buttons()
        self.update_filter_tag_options()
        self.apply_filters()

    # FILTROWANIE
    def category_filter_changed(self):
        self.update_filter_tag_options()
        self.apply_filters()

    def update_filter_tag_options(self):
        current_tag = self.tag_filter.currentData()
        self.tag_filter.blockSignals(True)
        self.tag_filter.clear()
        self.tag_filter.addItem("Wszystkie tagi", "")

        category = self.category_filter.currentData()
        if category:
            for value in self.available_tags.get(category, []):
                self.tag_filter.addItem(value, value)

        self.tag_filter.blockSignals(False)

        index = self.tag_filter.findData(current_tag)
        self.tag_filter.setCurrentIndex(index if index >= 0 else 0)

    def apply_filters(self):
        search_text = self.search.text().strip().lower()
        category = self.category_filter.currentData()
        tag = self.tag_filter.currentData()

        self.filtered_songs = []
        self.song_list.blockSignals(True)
        self.song_list.clear()

        for song in self.songs:
            if search_text and (
                search_text not in song.title.lower()
                and search_text not in song.artist.lower()
            ):
                continue

            if category and tag:
                tags = parse_grouping(read_grouping(song.path))
                if tag not in tags.get(category, []):
                    continue

            self.filtered_songs.append(song)
            self.song_list.addItem(f"{song.artist}\n{song.title}")

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
            self.title.clear()
            self.artist.clear()
            self.album.clear()
            self.tag_panel.load_song("")

    def clear_filters(self):
        self.search.blockSignals(True)
        self.search.clear()
        self.search.blockSignals(False)

        self.category_filter.blockSignals(True)
        self.category_filter.setCurrentIndex(0)
        self.category_filter.blockSignals(False)

        self.update_filter_tag_options()
        self.apply_filters()

    # WYBÓR
    def update_selected_counter(self):
        count = len(self.song_list.selectedItems())
        text = "Wybrano: 1 utwór" if count == 1 else f"Wybrano: {count} utworów"
        self.selected_counter.setText(text)

    def get_selected_songs(self):
        songs = []
        for item in self.song_list.selectedItems():
            row = self.song_list.row(item)
            if 0 <= row < len(self.filtered_songs):
                songs.append(self.filtered_songs[row])
        return songs

    def selection_changed(self):
        self.update_selected_counter()
        selected_songs = self.get_selected_songs()
        if len(selected_songs) > 1:
            self.tag_panel.load_songs(
                [read_grouping(song.path) for song in selected_songs]
            )

    def song_selected(self, index):
        if index < 0 or index >= len(self.filtered_songs):
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
                [read_grouping(song.path) for song in selected_songs]
            )
        else:
            self.tag_panel.load_song(grouping)

    # TAGI
    def tags_changed(self):
        if self._history_busy:
            return

        selected_songs = self.get_selected_songs()
        changes = self.tag_panel.get_changes()
        if not selected_songs or not changes:
            return

        history_entry = []

        for song in selected_songs:
            before_grouping = read_grouping(song.path)
            song_tags = parse_grouping(before_grouping)

            for category, value, should_have in changes:
                values = song_tags.setdefault(category, [])
                if should_have and value not in values:
                    values.append(value)
                elif not should_have and value in values:
                    values.remove(value)

            after_grouping = save_grouping(song.path, song_tags)
            song.grouping = after_grouping
            update_song(song)
            history_entry.append((song, before_grouping, after_grouping))

        self.undo_stack.append(history_entry)
        self.redo_stack.clear()
        self.update_history_buttons()

        self.current_grouping = read_grouping(self.current_song.path)
        self.tag_panel.set_baseline(
            [read_grouping(song.path) for song in selected_songs]
        )

    # UNDO / REDO
    def apply_history_entry(self, entry, use_after):
        for song, before_grouping, after_grouping in entry:
            grouping = after_grouping if use_after else before_grouping
            tags = parse_grouping(grouping)
            saved_grouping = save_grouping(song.path, tags)
            song.grouping = saved_grouping
            update_song(song)

    def refresh_after_history(self):
        if self.current_song is None:
            return

        self.current_grouping = read_grouping(self.current_song.path)
        selected_songs = self.get_selected_songs()

        self._history_busy = True
        try:
            if len(selected_songs) > 1:
                self.tag_panel.load_songs(
                    [read_grouping(song.path) for song in selected_songs]
                )
            else:
                self.tag_panel.load_song(self.current_grouping)
        finally:
            self._history_busy = False

        self.update_history_buttons()

    def undo(self):
        if not self.undo_stack:
            return
        entry = self.undo_stack.pop()
        self._history_busy = True
        try:
            self.apply_history_entry(entry, False)
            self.redo_stack.append(entry)
        finally:
            self._history_busy = False
        self.refresh_after_history()

    def redo(self):
        if not self.redo_stack:
            return
        entry = self.redo_stack.pop()
        self._history_busy = True
        try:
            self.apply_history_entry(entry, True)
            self.undo_stack.append(entry)
        finally:
            self._history_busy = False
        self.refresh_after_history()

    def update_history_buttons(self):
        self.undo_button.setEnabled(bool(self.undo_stack))
        self.redo_button.setEnabled(bool(self.redo_stack))


def run_gui():
    app = QApplication([])
    window = MainWindow()
    window.show()
    app.exec()
