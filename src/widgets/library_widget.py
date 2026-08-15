from PySide6.QtCore import Qt

from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QFormLayout,
    QLabel,
    QLineEdit,
    QSizePolicy,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.widgets.tag_panel import TagPanel
from src.widgets.playlist_widgets import SongListWidget
from src.widgets.track_list_view import TrackViewModeButton


class LibraryWidget(QWidget):
    """Presentation layer for the Library tab."""

    def __init__(self, available_tags, cover_art_service=None, parent=None):
        super().__init__(parent)
        self.available_tags = available_tags
        self.cover_art_service = cover_art_service
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

        self.selected_counter = QLabel("Wybrano: 0 utworów")
        left.addWidget(self.selected_counter)

        self.song_list = SongListWidget()
        self.song_list.set_cover_art_service(self.cover_art_service)
        self.song_list.setSelectionMode(
            QAbstractItemView.ExtendedSelection
        )
        list_header = QHBoxLayout()
        list_header.addWidget(self.counter)
        list_header.addStretch()
        self.view_mode_button = TrackViewModeButton(self.song_list, "medium")
        list_header.addWidget(self.view_mode_button)
        left.addLayout(list_header)
        left.addWidget(self.song_list)

        self.add_to_playlist_button = QPushButton(
            "＋ Dodaj zaznaczone do playlisty"
        )
        left.addWidget(self.add_to_playlist_button)

        layout.addLayout(left, 1)

        center = QVBoxLayout()
        center.setContentsMargins(8, 8, 8, 8)
        center.setSpacing(10)

        details = QVBoxLayout()
        details.setContentsMargins(0, 0, 0, 0)
        details.setSpacing(10)

        self.cover_label = QLabel()
        self.cover_label.setMinimumHeight(300)
        self.cover_label.setMaximumHeight(380)
        self.cover_label.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        self.cover_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cover_label.setObjectName("libraryCover")
        self.cover_label.setText("♪")
        self.cover_label.setStyleSheet(
            "#libraryCover {"
            " background: #252525;"
            " border: 1px solid #444;"
            " border-radius: 6px;"
            " color: #999;"
            " font-size: 48px;"
            "}"
        )
        details.addWidget(self.cover_label)

        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(6)

        self.title = QLineEdit()
        self.title.setReadOnly(True)
        self.title.setFixedHeight(34)

        self.artist = QLineEdit()
        self.artist.setReadOnly(True)
        self.artist.setFixedHeight(34)

        self.album = QLineEdit()
        self.album.setReadOnly(True)
        self.album.setFixedHeight(34)

        form.addRow("Tytuł", self.title)
        form.addRow("Artysta", self.artist)
        form.addRow("Album", self.album)

        details.addLayout(form)
        center.addLayout(details)
        center.addStretch(1)

        layout.addLayout(center, 1)

        self.tag_panel = TagPanel()
        layout.addWidget(self.tag_panel, 2)

    def set_cover_for_song(self, path):
        self.cover_label.clear()
        self.cover_label.setText("♪")

        if not path or self.cover_art_service is None:
            return

        try:
            data = self.cover_art_service.get_cover_bytes(path)
        except Exception:
            data = None

        if not data:
            return

        from PySide6.QtGui import QPixmap

        pixmap = QPixmap()
        if not pixmap.loadFromData(data):
            return

        pixmap = pixmap.scaled(
            self.cover_label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.cover_label.setPixmap(pixmap)
