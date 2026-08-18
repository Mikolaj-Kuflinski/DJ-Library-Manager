from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QTreeWidget,
    QVBoxLayout,
    QWidget,
)


class SpotifySyncDialog(QDialog):
    """Compact popup for managing Spotify playlist synchronization."""

    sync_requested = Signal(str)
    playlists_changed = Signal(list)

    def __init__(self, playlists=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🔄 Synchronizacja playlist Spotify")
        self.setMinimumSize(620, 460)
        self._playlists = list(playlists or [])
        self._build_ui()
        self._refresh_list()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        header = QLabel("Playlisty Spotify do synchronizacji")
        header.setStyleSheet("font-size:18px;font-weight:bold;")
        layout.addWidget(header)

        info = QLabel(
            "Dodaj playlistę przez wklejenie jej linku. "
            "DJLM zapamięta ją tutaj, a synchronizację uruchomisz "
            "bez zaśmiecania głównej zakładki Spotify."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        add_row = QHBoxLayout()

        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText(
            "https://open.spotify.com/playlist/..."
        )
        add_row.addWidget(self.url_edit, 2)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Nazwa playlisty")
        add_row.addWidget(self.name_edit, 1)

        self.add_btn = QPushButton("＋ Dodaj")
        self.add_btn.clicked.connect(self._add_playlist)
        add_row.addWidget(self.add_btn)
        layout.addLayout(add_row)

        self.list_widget = QListWidget()
        self.list_widget.setAlternatingRowColors(True)
        layout.addWidget(self.list_widget, 1)

        action_row = QHBoxLayout()
        self.sync_btn = QPushButton("🔄 Synchronizuj zaznaczoną")
        self.sync_btn.clicked.connect(self._sync_selected)
        action_row.addWidget(self.sync_btn)

        self.sync_all_btn = QPushButton("🔄 Synchronizuj wszystkie")
        self.sync_all_btn.clicked.connect(self._sync_all)
        action_row.addWidget(self.sync_all_btn)

        self.remove_btn = QPushButton("🗑 Usuń")
        self.remove_btn.clicked.connect(self._remove_selected)
        action_row.addWidget(self.remove_btn)
        action_row.addStretch()
        layout.addLayout(action_row)

        self.status = QLabel("Brak dodanych playlist.")
        layout.addWidget(self.status)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _refresh_list(self):
        self.list_widget.clear()
        for entry in self._playlists:
            title = entry.get("name") or entry.get("url", "Spotify playlist")
            item = QListWidgetItem(f"🎵 {title}")
            item.setToolTip(entry.get("url", ""))
            item.setData(32, entry.get("url", ""))
            self.list_widget.addItem(item)
        self.status.setText(
            f"Obserwowane playlisty: {len(self._playlists)}"
            if self._playlists else "Brak dodanych playlist."
        )
        self._emit_changed()

    def _add_playlist(self):
        url = self.url_edit.text().strip()
        if "/playlist/" not in url:
            QMessageBox.warning(
                self, "Nieprawidłowy link",
                "Wklej link do playlisty Spotify."
            )
            return
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(
                self,
                "Brak nazwy",
                "Podaj nazwę playlisty, która ma być wyświetlana w DJLM.",
            )
            self.name_edit.setFocus()
            return

        if any(x.get("url") == url for x in self._playlists):
            QMessageBox.information(
                self,
                "Playlista już istnieje",
                "Ta playlista jest już dodana do synchronizacji.",
            )
            return

        self._playlists.append({
            "url": url,
            "name": name,
            "has_updates": False,
        })
        self.url_edit.clear()
        self.name_edit.clear()
        self._refresh_list()

    def _selected_urls(self):
        items = self.list_widget.selectedItems()
        return [item.data(32) for item in items if item.data(32)]

    def _sync_selected(self):
        urls = self._selected_urls()
        if urls:
            self.sync_requested.emit(urls[0])
            self.status.setText("Synchronizacja uruchomiona…")

    def _sync_all(self):
        urls = [
            x.get("url") for x in self._playlists
            if x.get("url")
        ]
        for url in urls:
            self.sync_requested.emit(url)
        if urls:
            self.status.setText(
                f"Uruchomiono synchronizację {len(urls)} playlist."
            )

    def _remove_selected(self):
        urls = set(self._selected_urls())
        if not urls:
            return
        self._playlists = [
            x for x in self._playlists if x.get("url") not in urls
        ]
        self._refresh_list()

    def _emit_changed(self):
        self.playlists_changed.emit(list(self._playlists))


class SpotifyWidget(QWidget):
    """Presentation layer for Spotify/spotDL controls."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        header_row = QHBoxLayout()
        title = QLabel("🎵 Spotify")
        title.setStyleSheet("font-size:18px;font-weight:bold;")
        header_row.addWidget(title)
        header_row.addStretch()

        self.sync_playlists_btn = QPushButton("🔄 Synchronizacja playlist")
        self.sync_playlists_btn.setToolTip(
            "Otwórz zarządzanie playlistami Spotify do synchronizacji"
        )
        header_row.addWidget(self.sync_playlists_btn)
        layout.addLayout(header_row)

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
