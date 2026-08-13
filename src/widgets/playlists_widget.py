from PySide6.QtGui import QCursor, QDrag
from PySide6.QtCore import QByteArray, QMimeData, Qt, Signal
from PySide6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QMenu,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTreeWidget,
    QVBoxLayout,
    QWidget,
)

from src.widgets.playlist_widgets import PlaylistTrackListWidget


class PlaylistTreeWidget(QTreeWidget):
    """Playlist/folder tree with explicit Windows-like drag semantics."""

    playlist_dropped = Signal(int, object, object, int, object)

    MIME_TYPE = "application/x-djlm-playlist"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHeaderHidden(True)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setDragEnabled(False)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.DropOnly)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self._press_pos = None
        self._drag_button = None
        self._drag_source_index = None
        self._drag_source_folder = ""
        self._expanded_before_drag = set()

    def _playlist_item(self, item):
        if item is None:
            return None
        if item.data(0, Qt.ItemDataRole.UserRole) != "playlist":
            return None
        return item

    def mousePressEvent(self, event):
        self._press_pos = event.position().toPoint()
        self._drag_button = event.button()
        super().mousePressEvent(event)

    def _capture_expanded_folders(self):
        expanded = set()
        for i in range(self.topLevelItemCount()):
            stack = [self.topLevelItem(i)]
            while stack:
                item = stack.pop()
                if item.data(0, Qt.ItemDataRole.UserRole) == "folder":
                    path = item.data(
                        0, Qt.ItemDataRole.UserRole + 2
                    ) or ""
                    if path and item.isExpanded():
                        expanded.add(path)
                for j in range(item.childCount()):
                    stack.append(item.child(j))
        return expanded

    def mouseMoveEvent(self, event):
        if self._press_pos is not None and self._drag_button in (
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.RightButton,
        ):
            distance = (
                event.position().toPoint() - self._press_pos
            ).manhattanLength()

            if distance >= QApplication.startDragDistance():
                item = self._playlist_item(self.currentItem())
                if item is not None:
                    self._drag_source_index = item.data(
                        0, Qt.ItemDataRole.UserRole + 1
                    )
                    self._drag_source_folder = item.data(
                        0, Qt.ItemDataRole.UserRole + 2
                    ) or ""
                    self._expanded_before_drag = (
                        self._capture_expanded_folders()
                    )

                    mime = QMimeData()
                    payload = QByteArray(
                        f"{self._drag_source_index}|"
                        f"{self._drag_source_folder}".encode("utf-8")
                    )
                    mime.setData(self.MIME_TYPE, payload)

                    drag = QDrag(self)
                    drag.setMimeData(mime)
                    drag.exec(
                        Qt.DropAction.CopyAction
                        | Qt.DropAction.MoveAction
                    )

                    self._press_pos = None
                    self._drag_button = None
                    return

        super().mouseMoveEvent(event)

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(self.MIME_TYPE):
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat(self.MIME_TYPE):
            item = self.itemAt(event.position().toPoint())
            if item is not None and item.data(
                0, Qt.ItemDataRole.UserRole
            ) in ("folder", "playlist"):
                event.setDropAction(Qt.DropAction.MoveAction)
                event.accept()
                return
            event.ignore()
            return
        super().dragMoveEvent(event)

    def _drop_action_for_right_drag(self):
        menu = QMenu(self)
        copy_action = menu.addAction("📋 Kopiuj do folderu")
        move_action = menu.addAction("↪ Przenieś do folderu")
        menu.addSeparator()
        menu.addAction("Anuluj")

        chosen = menu.exec(QCursor.pos())
        if chosen is copy_action:
            return "copy"
        if chosen is move_action:
            return "move"
        return "cancel"

    def dropEvent(self, event):
        if not event.mimeData().hasFormat(self.MIME_TYPE):
            super().dropEvent(event)
            return

        raw = bytes(
            event.mimeData().data(self.MIME_TYPE)
        ).decode("utf-8")
        try:
            source_index_text, source_folder = raw.split("|", 1)
            source_index = int(source_index_text)
        except (ValueError, UnicodeDecodeError):
            event.ignore()
            return

        target_item = self.itemAt(event.position().toPoint())
        if target_item is None:
            event.ignore()
            return

        target_kind = target_item.data(
            0, Qt.ItemDataRole.UserRole
        )
        if target_kind == "folder":
            target_folder = target_item.data(
                0, Qt.ItemDataRole.UserRole + 2
            ) or ""
            target_position = target_item.childCount()
        elif target_kind == "playlist":
            parent = target_item.parent()
            target_folder = (
                parent.data(
                    0, Qt.ItemDataRole.UserRole + 2
                ) or ""
                if parent is not None
                else ""
            )
            target_position = (
                parent.indexOfChild(target_item)
                if parent is not None
                else 0
            )
        else:
            event.ignore()
            return

        action = "move"
        if self._drag_button == Qt.MouseButton.RightButton:
            action = self._drop_action_for_right_drag()
            if action == "cancel":
                event.ignore()
                return

        # Keep the expanded state from BEFORE Qt's drag interaction.
        self._expanded_before_drag = (
            self._expanded_before_drag
            or self._capture_expanded_folders()
        )

        self.playlist_dropped.emit(
            source_index,
            source_folder,
            target_folder,
            target_position,
            action,
        )
        event.setDropAction(
            Qt.DropAction.CopyAction
            if action == "copy"
            else Qt.DropAction.MoveAction
        )
        event.accept()

class PlaylistsWidget(QWidget):
    """Presentation layer for the Playlists tab.

    Playlist data and actions remain in MainWindow for this refactor step.
    """

    new_requested = Signal()
    rename_requested = Signal()
    delete_requested = Signal()
    folder_create_requested = Signal()
    folder_delete_requested = Signal()
    remove_tracks_requested = Signal()
    export_m3u8_requested = Signal()
    export_djay_requested = Signal()
    sync_tags_requested = Signal()
    playlist_dropped = Signal(int, object, object, int, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _request_folder_create(self):
        self.folder_create_requested.emit()

    def _build_ui(self):
        layout = QHBoxLayout(self)

        left = QVBoxLayout()
        left.addWidget(QLabel("Moje playlisty"))

        folder_row = QHBoxLayout()
        folder_row.addWidget(QLabel("📁 Folder:"))

        self.playlist_folder_filter = QComboBox()
        folder_row.addWidget(self.playlist_folder_filter, 1)

        add_folder_btn = QPushButton("＋ Folder")
        add_folder_btn.clicked.connect(self._request_folder_create)
        folder_row.addWidget(add_folder_btn)

        remove_folder_btn = QPushButton("🗑")
        remove_folder_btn.setToolTip("Usuń folder (playlisty zostają)")
        remove_folder_btn.clicked.connect(self.folder_delete_requested.emit)
        folder_row.addWidget(remove_folder_btn)

        left.addLayout(folder_row)

        self.playlist_list = PlaylistTreeWidget()
        self.playlist_list.setAnimated(True)
        self.playlist_list.playlist_dropped.connect(
            self.playlist_dropped.emit
        )
        left.addWidget(self.playlist_list)

        playlist_buttons = QHBoxLayout()

        new_btn = QPushButton("＋ Nowa")
        new_btn.clicked.connect(self.new_requested.emit)
        playlist_buttons.addWidget(new_btn)

        rename_btn = QPushButton("✏ Zmień nazwę")
        rename_btn.clicked.connect(self.rename_requested.emit)
        playlist_buttons.addWidget(rename_btn)

        delete_btn = QPushButton("🗑 Usuń")
        delete_btn.clicked.connect(self.delete_requested.emit)
        playlist_buttons.addWidget(delete_btn)

        sync_tags_btn = QPushButton("🏷️ Playlisty z tagów")
        sync_tags_btn.setToolTip(
            "Utwórz/odśwież playlisty na podstawie kategorii i tagów"
        )
        sync_tags_btn.clicked.connect(self.sync_tags_requested.emit)
        playlist_buttons.addWidget(sync_tags_btn)

        left.addLayout(playlist_buttons)
        layout.addLayout(left, 1)

        middle = QVBoxLayout()

        self.playlist_title = QLabel("Wybierz playlistę")
        self.playlist_title.setStyleSheet(
            "font-size:18px;font-weight:bold;"
        )
        middle.addWidget(self.playlist_title)

        self.playlist_tracks = PlaylistTrackListWidget()
        middle.addWidget(self.playlist_tracks)

        remove_track_btn = QPushButton(
            "➖ Usuń zaznaczone z playlisty"
        )
        remove_track_btn.clicked.connect(
            self.remove_tracks_requested.emit
        )
        middle.addWidget(remove_track_btn)

        layout.addLayout(middle, 2)

        right = QVBoxLayout()
        right.addWidget(QLabel("Informacje"))

        self.playlist_info = QLabel("Wybierz playlistę")
        self.playlist_info.setWordWrap(True)
        right.addWidget(self.playlist_info)
        right.addStretch()

        export_btn = QPushButton("📤 Eksportuj playlistę M3U8")
        export_btn.clicked.connect(self.export_m3u8_requested.emit)
        right.addWidget(export_btn)

        djay_btn = QPushButton("🚀 Eksportuj do djay Pro")
        djay_btn.clicked.connect(self.export_djay_requested.emit)
        right.addWidget(djay_btn)

        layout.addLayout(right, 1)
