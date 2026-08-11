from PySide6.QtCore import QMimeData, Qt, Signal
from PySide6.QtGui import QDrag
from PySide6.QtWidgets import QListWidget, QAbstractItemView, QTabBar


MIME_SONG_PATHS = "application/x-dj-song-paths"


def build_song_mime(items):
    mime = QMimeData()
    paths = []

    for item in items:
        path = item.data(Qt.ItemDataRole.UserRole)
        if path:
            paths.append(str(path))

    mime.setData(
        MIME_SONG_PATHS,
        "\n".join(paths).encode("utf-8")
    )
    return mime


def mime_paths(mime):
    if not mime.hasFormat(MIME_SONG_PATHS):
        return []

    raw = bytes(
        mime.data(MIME_SONG_PATHS)
    ).decode("utf-8")

    return [p for p in raw.split("\n") if p]


class DragTabBar(QTabBar):
    """Przełącza zakładkę Playlisty, gdy przeciągany utwór najedzie na jej kartę."""

    tab_dragged = Signal(int)

    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(MIME_SONG_PATHS):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if not event.mimeData().hasFormat(MIME_SONG_PATHS):
            event.ignore()
            return

        index = self.tabAt(
            event.position().toPoint()
        )

        if index >= 0:
            self.tab_dragged.emit(index)
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        # Drop jest wykonywany dopiero na konkretnej playliście.
        # Tutaj tylko akceptujemy ruch, aby drag mógł przejść dalej.
        if event.mimeData().hasFormat(MIME_SONG_PATHS):
            event.acceptProposedAction()
        else:
            event.ignore()


class SongListWidget(QListWidget):
    def __init__(self):
        super().__init__()
        self.setSelectionMode(
            QAbstractItemView.ExtendedSelection
        )
        self.setDragEnabled(True)
        self.setAcceptDrops(False)

    def startDrag(self, supported_actions):
        items = self.selectedItems()
        if not items:
            return

        drag = QDrag(self)
        drag.setMimeData(build_song_mime(items))
        drag.exec(Qt.DropAction.CopyAction)


class PlaylistListWidget(QListWidget):
    """Lista playlist — przyjmuje utwory upuszczone na konkretną playlistę."""

    songs_dropped = Signal(int, list)

    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(MIME_SONG_PATHS):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if not event.mimeData().hasFormat(MIME_SONG_PATHS):
            event.ignore()
            return

        item = self.itemAt(
            event.position().toPoint()
        )

        if item is not None:
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        if not event.mimeData().hasFormat(MIME_SONG_PATHS):
            event.ignore()
            return

        item = self.itemAt(
            event.position().toPoint()
        )

        if item is None:
            event.ignore()
            return

        paths = mime_paths(event.mimeData())

        if paths:
            self.songs_dropped.emit(
                self.row(item),
                paths
            )
            event.acceptProposedAction()
        else:
            event.ignore()


class PlaylistTrackListWidget(QListWidget):
    """Utwory w playliście: reorder + przyjmowanie utworów z innych źródeł."""

    songs_dropped = Signal(list)
    order_changed = Signal(list, list)

    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragEnabled(True)
        self.setSelectionMode(
            QAbstractItemView.ExtendedSelection
        )
        self.setDragDropMode(
            QAbstractItemView.InternalMove
        )
        self.setDefaultDropAction(
            Qt.DropAction.MoveAction
        )

    def startDrag(self, supported_actions):
        items = self.selectedItems()
        if not items:
            return

        drag = QDrag(self)
        drag.setMimeData(build_song_mime(items))
        drag.exec(
            Qt.DropAction.MoveAction
            | Qt.DropAction.CopyAction
        )

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(MIME_SONG_PATHS):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat(MIME_SONG_PATHS):
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        # Reorder wewnątrz tej samej listy.
        if event.source() is self:
            before = [
                self.item(i).data(
                    Qt.ItemDataRole.UserRole
                )
                for i in range(self.count())
            ]

            super().dropEvent(event)

            after = [
                self.item(i).data(
                    Qt.ItemDataRole.UserRole
                )
                for i in range(self.count())
            ]

            if before != after:
                self.order_changed.emit(
                    before,
                    after
                )

            event.acceptProposedAction()
            return

        # Drop z Biblioteki albo innej playlisty.
        if event.mimeData().hasFormat(MIME_SONG_PATHS):
            paths = mime_paths(
                event.mimeData()
            )

            if paths:
                self.songs_dropped.emit(paths)
                event.acceptProposedAction()
                return

        super().dropEvent(event)
