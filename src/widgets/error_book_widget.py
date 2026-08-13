from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QListWidget,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QVBoxLayout,
    QWidget,
)


class ErrorBookWidget(QWidget):
    """UI for the persistent Spotify download error book."""

    open_requested = Signal()
    copy_requested = Signal()
    remove_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.errors = []
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        title = QLabel("📕 Książka błędów pobierania")
        title.setStyleSheet("font-size:18px;font-weight:bold;")
        layout.addWidget(title)

        info = QLabel(
            "Błędy są zapisywane między uruchomieniami DJLM. "
            "Możesz wrócić do nich później i otworzyć link ręcznie."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        self.list_widget = QListWidget()
        layout.addWidget(self.list_widget, 1)

        buttons = QHBoxLayout()

        open_btn = QPushButton("🌐 Otwórz link")
        open_btn.clicked.connect(self.open_requested.emit)
        buttons.addWidget(open_btn)

        copy_btn = QPushButton("📋 Kopiuj link")
        copy_btn.clicked.connect(self.copy_requested.emit)
        buttons.addWidget(copy_btn)

        remove_btn = QPushButton("🗑 Usuń wpis")
        remove_btn.clicked.connect(self.remove_requested.emit)
        buttons.addWidget(remove_btn)

        buttons.addStretch()
        layout.addLayout(buttons)

    def set_errors(self, errors):
        self.errors = list(errors or [])
        self.list_widget.clear()
        for entry in self.errors:
            self.list_widget.addItem(
                f"❌ {entry.get('status', 'error (nie pobrano)')} | "
                f"{entry.get('artist', 'Nieznany artysta')} — "
                f"{entry.get('title', 'Nieznany tytuł')}\n"
                f"🔗 {entry.get('url', 'brak linku')}\n"
                f"💬 {entry.get('error', '')}"
            )

    def selected_error(self):
        row = self.list_widget.currentRow()
        if 0 <= row < len(self.errors):
            return self.errors[row]
        return None
