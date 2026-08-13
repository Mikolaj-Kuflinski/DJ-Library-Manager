from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QProgressBar,
    QTreeWidget,
    QVBoxLayout,
    QWidget,
)


class SpotifyWidget(QWidget):
    """Presentation layer for Spotify/spotDL controls."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        title = QLabel("🎵 Spotify")
        title.setStyleSheet("font-size:18px;font-weight:bold;")
        layout.addWidget(title)

        info = QLabel(
            "Wklej link do utworu albo playlisty Spotify. "
            "DJLM uruchomi lokalny spotDL i pobierze tylko brakujące pliki "
            "do folderu wejściowego."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        form = QFormLayout()

        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText(
            "https://open.spotify.com/track/... lub /playlist/..."
        )
        form.addRow("🔗 Link Spotify:", self.url_edit)

        self.download_folder = QLineEdit()
        self.download_folder.setReadOnly(True)
        form.addRow("📥 Folder pobierania:", self.download_folder)

        cookie_row = QHBoxLayout()
        self.cookie_file = QLineEdit()
        self.cookie_file.setPlaceholderText(
            "Opcjonalnie: ścieżka do cookies.txt z YouTube"
        )
        cookie_row.addWidget(self.cookie_file, 1)

        self.cookie_browse_btn = QPushButton("📂 Wybierz")
        cookie_row.addWidget(self.cookie_browse_btn)
        form.addRow("🍪 Cookies YouTube:", cookie_row)

        layout.addLayout(form)

        buttons = QHBoxLayout()

        self.download_btn = QPushButton("⬇️ Pobierz brakujące")
        buttons.addWidget(self.download_btn)

        self.add_queue_btn = QPushButton("➕ Dodaj do kolejki")
        buttons.addWidget(self.add_queue_btn)

        self.clear_btn = QPushButton("Wyczyść")
        buttons.addWidget(self.clear_btn)

        self.pause_btn = QPushButton("⏸ Wstrzymaj")
        self.pause_btn.setEnabled(False)
        buttons.addWidget(self.pause_btn)

        self.resume_btn = QPushButton("▶ Wznów")
        self.resume_btn.setEnabled(False)
        buttons.addWidget(self.resume_btn)

        self.cancel_btn = QPushButton("⛔ Anuluj")
        self.cancel_btn.setEnabled(False)
        buttons.addWidget(self.cancel_btn)

        buttons.addStretch()
        layout.addLayout(buttons)

        progress_row = QHBoxLayout()
        self.progress = QLabel("Gotowy.")
        progress_row.addWidget(self.progress, 1)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("Pobrano 0/0")
        progress_row.addWidget(self.progress_bar, 2)

        self.progress_count = QLabel("Pobrano 0/0")
        progress_row.addWidget(self.progress_count)
        layout.addLayout(progress_row)

        stats_row = QHBoxLayout()
        self.speed_label = QLabel("🚀 Prędkość: —")
        self.eta_label = QLabel("⏱️ ETA: —")
        self.queue_btn = QPushButton("📋 Kolejka: 0(0)")
        self.queue_btn.setFlat(True)
        stats_row.addWidget(self.speed_label)
        stats_row.addWidget(self.eta_label)
        stats_row.addWidget(self.queue_btn)
        stats_row.addStretch()
        layout.addLayout(stats_row)

        self.queue_tree = QTreeWidget()
        self.queue_tree.setHeaderHidden(True)
        self.queue_tree.setMaximumHeight(260)
        self.queue_tree.setVisible(False)
        self.queue_tree.setSelectionMode(
            QAbstractItemView.SingleSelection
        )
        layout.addWidget(self.queue_tree)

        queue_actions = QHBoxLayout()
        self.remove_queue_btn = QPushButton("🗑 Usuń z kolejki")
        self.remove_queue_btn.setVisible(False)
        self.remove_queue_btn.setEnabled(False)
        queue_actions.addWidget(self.remove_queue_btn)
        queue_actions.addStretch()
        layout.addLayout(queue_actions)

        self.log = QListWidget()
        self.log.setSelectionMode(QAbstractItemView.NoSelection)
        layout.addWidget(self.log, 1)

        error_row = QHBoxLayout()
        self.errors_btn = QPushButton("📕 Książka błędów (0)")
        error_row.addWidget(self.errors_btn)
        error_row.addStretch()
        layout.addLayout(error_row)
