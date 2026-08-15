from PySide6.QtCore import Qt, QSize, Signal
from PySide6.QtGui import QIcon, QPixmap, QPainter, QFont, QColor
from PySide6.QtWidgets import QListView, QListWidget, QListWidgetItem, QPushButton

VIEW_MODES = (
    ("large", "▦"),
    ("thin", "☰"),
    ("medium", "▤"),
    ("wide", "▥"),
)

VIEW_LABELS = {
    "large": "Duże kwadraty",
    "thin": "Cienka linijka",
    "medium": "Średnia linijka",
    "wide": "Szeroka linijka",
}

ICON_SIZES = {
    "large": 128,
    "thin": 28,
    "medium": 48,
    "wide": 72,
}

ROW_HEIGHTS = {"thin": 34, "medium": 58, "wide": 82}

ITEM_SIZES = {
    "thin": QSize(0, 36),
    "medium": QSize(0, 58),
    "wide": QSize(0, 84),
    "large": QSize(170, 170),
}


class TrackListViewMixin:
    def init_track_view(self, cover_art_service=None, mode="medium"):
        self.cover_art_service = cover_art_service
        self.view_mode = mode if mode in VIEW_LABELS else "medium"
        self._apply_view_mode()

    def set_cover_art_service(self, service):
        self.cover_art_service = service
        self.refresh_cover_art()

    def set_view_mode(self, mode):
        if mode not in VIEW_LABELS:
            mode = "medium"
        if mode == self.view_mode:
            return
        self.view_mode = mode
        self._apply_view_mode()
        self.viewport().update()

    def _apply_view_mode(self):
        mode = self.view_mode
        size = ICON_SIZES[mode]

        # Reset geometry left by the previous mode. This is important on
        # startup and when switching back from IconMode.
        self.setGridSize(QSize())
        self.setSpacing(0)
        self.setWrapping(False)

        if mode == "large":
            self.setViewMode(QListView.ViewMode.IconMode)
            self.setFlow(QListView.Flow.LeftToRight)
            self.setWrapping(True)
            self.setIconSize(QSize(size, size))
            self.setGridSize(QSize(150, 160))
            self.setSpacing(8)
            self.setStyleSheet("")
        else:
            self.setViewMode(QListView.ViewMode.ListMode)
            self.setFlow(QListView.Flow.TopToBottom)
            self.setWrapping(False)
            self.setIconSize(QSize(size, size))
            self.setGridSize(QSize())
            self.setSpacing(0)
            row_height = ROW_HEIGHTS[mode]
            self.setStyleSheet(
                f"QListWidget::item {{ "
                f"height: {row_height}px; "
                f"min-height: {row_height}px; "
                f"max-height: {row_height}px; }}"
            )

    def refresh_cover_art(self):
        for row in range(self.count()):
            item = self.item(row)
            path = item.data(Qt.ItemDataRole.UserRole)
            self._set_item_cover(item, path)

    def add_track_item(self, item, path):
        item.setData(Qt.ItemDataRole.UserRole, path)
        self.addItem(item)
        self._set_item_cover(item, path)

    def _set_item_cover(self, item, path):
        size = 128
        data = None
        if self.cover_art_service is not None:
            try:
                data = self.cover_art_service.get_cover_bytes(path)
            except Exception:
                data = None

        if data:
            pixmap = QPixmap()
            if pixmap.loadFromData(data):
                item.setIcon(QIcon(pixmap.scaled(
                    QSize(size, size),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )))
                return

        item.setIcon(self._placeholder_icon(128))

    @staticmethod
    def _placeholder_icon(size):
        pixmap = QPixmap(size, size)
        pixmap.fill(QColor(48, 48, 48))
        painter = QPainter(pixmap)
        painter.setPen(QColor(190, 190, 190))
        font = QFont()
        font.setPointSize(max(12, size // 3))
        painter.setFont(font)
        painter.drawText(
            pixmap.rect(),
            Qt.AlignmentFlag.AlignCenter,
            "♪",
        )
        painter.end()
        return QIcon(pixmap)


class TrackViewModeButton(QPushButton):
    mode_changed = Signal(str)

    def __init__(self, list_widget, initial_mode="medium", parent=None):
        super().__init__(parent)
        self.list_widget = list_widget
        self.modes = [mode for mode, _ in VIEW_MODES]
        self.mode = initial_mode if initial_mode in self.modes else "medium"
        self.setFixedWidth(34)
        self.setFixedHeight(28)
        self.clicked.connect(self.cycle_mode)
        self._update_text()

    def set_mode(self, mode):
        if mode in self.modes:
            self.mode = mode
        self._update_text()

    def _update_text(self):
        self.setText(dict(VIEW_MODES)[self.mode])
        self.setToolTip(f"Tryb widoku: {VIEW_LABELS[self.mode]}")

    def cycle_mode(self):
        next_index = (self.modes.index(self.mode) + 1) % len(self.modes)
        self.set_mode(self.modes[next_index])
        self.list_widget.set_view_mode(self.mode)
        self.mode_changed.emit(self.mode)
