from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.widgets.tag_panel import TagPanel
from src.widgets.track_list_view import TrackListViewMixin, TrackViewModeButton


class NewTracksListWidget(TrackListViewMixin, QListWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_track_view()
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)


class NewTracksWidget(QWidget):
    """Presentation layer for the New Tracks tab."""

    refresh_requested = Signal()
    finish_requested = Signal()
    selection_changed = Signal(int)
    tags_changed = Signal()

    def __init__(self, available_tags, parent=None):
        super().__init__(parent)
        self.available_tags = available_tags
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        header = QHBoxLayout()
        title = QLabel("🆕 Nowe utwory")
        title.setStyleSheet("font-size:18px;font-weight:bold;")
        header.addWidget(title)

        self.count_label = QLabel("0 w sesji")
        header.addStretch()
        header.addWidget(self.count_label)
        layout.addLayout(header)

        info = QLabel(
            "To jest Twoja kolejka pracy. Zmiany tagów zapisują się "
            "automatycznie. Utwory zostają w tej sesji, dopóki ręcznie "
            "nie zakończysz pracy nad nimi."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        filters = QHBoxLayout()

        self.status_filter = QComboBox()
        self.status_filter.addItem("Wszystkie", "all")
        self.status_filter.addItem("🆕 Nowe", "new")
        self.status_filter.addItem("⚠️ Do uzupełnienia", "todo")
        filters.addWidget(self.status_filter)

        self.search = QLineEdit()
        self.search.setPlaceholderText(
            "Szukaj po tytule, artyście lub albumie..."
        )
        filters.addWidget(self.search, 1)
        layout.addLayout(filters)

        content = QHBoxLayout()

        left = QVBoxLayout()
        self.song_list = NewTracksListWidget()
        self.song_list.setSelectionMode(
            QAbstractItemView.ExtendedSelection
        )

        list_header = QHBoxLayout()
        list_header.addStretch()
        self.view_mode_button = TrackViewModeButton(
            self.song_list,
            "medium",
        )
        list_header.addWidget(self.view_mode_button)
        left.addLayout(list_header)

        left.addWidget(self.song_list)
        content.addLayout(left, 2)

        self.tag_panel = TagPanel()
        self.tag_panel.tags_changed.connect(self.tags_changed.emit)
        content.addWidget(self.tag_panel, 2)

        layout.addLayout(content, 1)

        actions = QHBoxLayout()

        self.finish_btn = QPushButton(
            "✅ Zakończ pracę nad zaznaczonymi"
        )
        self.finish_btn.setEnabled(False)
        actions.addWidget(self.finish_btn)

        self.refresh_btn = QPushButton("↻ Odśwież")
        actions.addWidget(self.refresh_btn)

        actions.addStretch()
        layout.addLayout(actions)
