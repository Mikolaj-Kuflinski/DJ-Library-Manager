from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.widgets.tag_panel import TagPanel
from src.widgets.playlist_widgets import SongListWidget


class LibraryWidget(QWidget):
    """Presentation layer for the Library tab."""

    def __init__(self, available_tags, parent=None):
        super().__init__(parent)
        self.available_tags = available_tags
        self._build_ui()

    def _build_ui(self):
        layout = QHBoxLayout(self)

        left = QVBoxLayout()

        self.search = QLineEdit()
        self.search.setPlaceholderText("🔍 Szukaj artysty / tytułu...")
        left.addWidget(self.search)

        left.addWidget(QLabel("Filtr tagów"))

        self.category_filter = QComboBox()
        self.category_filter.addItem("Wszystkie kategorie", "")
        for category in self.available_tags.keys():
            self.category_filter.addItem(category, category)
        left.addWidget(self.category_filter)

        self.tag_filter = QComboBox()
        self.tag_filter.addItem("Wszystkie tagi", "")
        left.addWidget(self.tag_filter)

        self.clear_filters_button = QPushButton("✕ Wyczyść filtry")
        left.addWidget(self.clear_filters_button)

        self.counter = QLabel()
        left.addWidget(self.counter)

        self.selected_counter = QLabel("Wybrano: 0 utworów")
        left.addWidget(self.selected_counter)

        self.song_list = SongListWidget()
        self.song_list.setSelectionMode(
            QAbstractItemView.ExtendedSelection
        )
        left.addWidget(self.song_list)

        self.add_to_playlist_button = QPushButton(
            "＋ Dodaj zaznaczone do playlisty"
        )
        left.addWidget(self.add_to_playlist_button)

        layout.addLayout(left, 1)

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

        layout.addLayout(center, 1)

        self.tag_panel = TagPanel()
        layout.addWidget(self.tag_panel, 2)
