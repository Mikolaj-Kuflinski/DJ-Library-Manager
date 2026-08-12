from pathlib import Path
import json
import os
import re
import ctypes
from datetime import datetime, timedelta

from PySide6.QtWidgets import (
    QApplication, QWidget, QListWidget, QLabel, QVBoxLayout, QHBoxLayout,
    QLineEdit, QAbstractItemView, QPushButton, QComboBox, QTabWidget,
    QInputDialog, QMessageBox, QFileDialog, QToolButton, QDialog, QDialogButtonBox, QListWidgetItem,
    QFormLayout, QGroupBox, QProgressBar, QTreeWidget, QTreeWidgetItem,
)
from PySide6.QtGui import QKeySequence, QShortcut, QDesktopServices
from PySide6.QtCore import Qt, QProcess, QProcessEnvironment, QTimer, QUrl

from src.database_service import load_songs, update_song
from src.tags import read_grouping, save_grouping, parse_grouping
from src.config import get_available_tags
from src.playlist_service import load_playlists, save_playlists
from src.widgets.tag_panel import TagPanel
from src.widgets.playlist_widgets import SongListWidget, PlaylistTrackListWidget, PlaylistListWidget, DragTabBar


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DJ Library Manager")
        self.resize(1400, 800)

        # Ustawienia muszą być wczytane przed biblioteką — folder źródłowy
        # decyduje o tym, jakie utwory trafiają do zakładki „Biblioteka”.
        self.load_app_settings()
        self.spotify_errors = self.load_spotify_errors()
        self.songs = self.load_songs_from_source_folder()

        # Playlisty przechowują ścieżki, a Windows potrafi zwrócić tę samą
        # ścieżkę w różnych postaciach (względna/absolutna, \ i /,
        # różna wielkość liter). Trzymamy więc indeks po znormalizowanej
        # ścieżce, żeby playlisty z tagów nie wyświetlały "Brak".
        self.song_by_path = {}
        for song in self.songs:
            self.song_by_path[self._normalize_playlist_path(song.path)] = song

        self.filtered_songs = self.songs.copy()
        self.current_song = None
        self.current_grouping = ""

        self.undo_stack = []
        self.redo_stack = []
        self._history_busy = False

        self.available_tags = get_available_tags()
        self.playlists = load_playlists()
        self.playlist_folder_map = self.load_playlist_folder_map()
        self.playlist_generated_map = self.load_playlist_generated_map()
        self.current_playlist_index = 0 if self.playlists else -1

        main_layout = QVBoxLayout(self)

        self.tabs = QTabWidget()
        self.tabs.setTabBar(DragTabBar())
        self.tabs.tabBar().tab_dragged.connect(
            self.dragged_over_tab
        )

        self.library_tab = QWidget()
        self.playlist_tab = QWidget()
        self.spotify_tab = QWidget()
        self.error_book_tab = QWidget()
        self.settings_tab = QWidget()
        self.tabs.addTab(self.library_tab, "🎵 Biblioteka")
        self.tabs.addTab(self.playlist_tab, "📋 Playlisty")
        self.tabs.addTab(self.spotify_tab, "🎵 Spotify")
        self.new_tracks_tab = QWidget()
        self.tabs.addTab(self.new_tracks_tab, "🆕 Nowe utwory")
        self.tabs.addTab(self.error_book_tab, "📕 Błędy")
        self.tabs.addTab(self.settings_tab, "⚙ Ustawienia")
        main_layout.addWidget(self.tabs)

        self.build_library_tab()
        self.build_playlist_tab()
        self.build_spotify_tab()
        self.build_new_tracks_tab()
        self.build_error_book_tab()
        self.build_settings_tab()

        undo_row = QHBoxLayout()
        self.undo_button = QPushButton("↶ Cofnij")
        self.redo_button = QPushButton("↷ Ponów")
        self.undo_button.clicked.connect(self.undo)
        self.redo_button.clicked.connect(self.redo)
        undo_row.addWidget(self.undo_button)
        undo_row.addWidget(self.redo_button)
        undo_row.addStretch()
        main_layout.addLayout(undo_row)

        self.undo_shortcut = QShortcut(QKeySequence("Ctrl+Z"), self)
        self.undo_shortcut.activated.connect(self.undo)
        self.redo_shortcut = QShortcut(QKeySequence("Ctrl+Y"), self)
        self.redo_shortcut.activated.connect(self.redo)

        self.m3u8_shortcut = QShortcut(QKeySequence("Ctrl+E"), self)
        self.m3u8_shortcut.activated.connect(self.export_current_playlist)

        self.djay_shortcut = QShortcut(QKeySequence("Ctrl+Shift+E"), self)
        self.djay_shortcut.activated.connect(self.export_to_djay_pro)

        self.update_history_buttons()
        self.update_filter_tag_options()
        self.apply_filters()
        self.refresh_playlist_list()

    @staticmethod
    def _normalize_playlist_path(path):
        if not path:
            return ""
        try:
            return os.path.normcase(os.path.normpath(str(Path(path).resolve())))
        except Exception:
            return os.path.normcase(os.path.normpath(str(path)))

    def _find_song_for_playlist_path(self, path):
        key = self._normalize_playlist_path(path)
        song = self.song_by_path.get(key)
        if song is not None:
            return song

        # Legacy playlists may contain the old, non-normalized path.
        raw = str(path or "")
        for candidate in self.songs:
            if self._normalize_playlist_path(candidate.path) == key:
                return candidate
            if os.path.normcase(os.path.normpath(str(candidate.path))) == os.path.normcase(os.path.normpath(raw)):
                return candidate
        return None

    def dragged_over_tab(self, index):
        # Zakładka Playlisty ma indeks 1.
        # Przełączamy ją podczas trzymania przeciąganego utworu.
        if index == 1 and self.tabs.currentIndex() != 1:
            self.tabs.setCurrentIndex(1)

    # ==================== BIBLIOTEKA ====================
    def build_library_tab(self):
        layout = QHBoxLayout(self.library_tab)
        left = QVBoxLayout()

        self.search = QLineEdit()
        self.search.setPlaceholderText("🔍 Szukaj artysty / tytułu...")
        self.search.textChanged.connect(self.apply_filters)
        left.addWidget(self.search)

        left.addWidget(QLabel("Filtr tagów"))
        self.category_filter = QComboBox()
        self.category_filter.addItem("Wszystkie kategorie", "")
        self.category_filter.addItems(self.available_tags.keys())
        self.category_filter.currentIndexChanged.connect(self.category_filter_changed)
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

        self.song_list = SongListWidget()
        self.song_list.currentRowChanged.connect(self.song_selected)
        self.song_list.itemSelectionChanged.connect(self.selection_changed)
        left.addWidget(self.song_list)

        self.add_to_playlist_button = QPushButton("＋ Dodaj zaznaczone do playlisty")
        self.add_to_playlist_button.clicked.connect(self.choose_playlists_for_selected)
        left.addWidget(self.add_to_playlist_button)

        layout.addLayout(left, 1)

        center = QVBoxLayout()
        center.addWidget(QLabel("Tytuł"))
        self.title = QLineEdit(); self.title.setReadOnly(True); center.addWidget(self.title)
        center.addWidget(QLabel("Artysta"))
        self.artist = QLineEdit(); self.artist.setReadOnly(True); center.addWidget(self.artist)
        center.addWidget(QLabel("Album"))
        self.album = QLineEdit(); self.album.setReadOnly(True); center.addWidget(self.album)
        layout.addLayout(center, 1)

        self.tag_panel = TagPanel()
        self.tag_panel.tags_changed.connect(self.tags_changed)
        layout.addWidget(self.tag_panel, 2)

    # ==================== SPOTIFY ====================
    def build_spotify_tab(self):
        layout = QVBoxLayout(self.spotify_tab)

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

        self.spotify_url_edit = QLineEdit()
        self.spotify_url_edit.setPlaceholderText(
            "https://open.spotify.com/track/... lub /playlist/..."
        )
        form.addRow("🔗 Link Spotify:", self.spotify_url_edit)

        self.spotify_download_folder = QLineEdit(
            self.app_settings["source_folder"]
        )
        self.spotify_download_folder.setReadOnly(True)
        form.addRow("📥 Folder pobierania:", self.spotify_download_folder)

        cookie_row = QHBoxLayout()
        self.spotify_cookie_file = QLineEdit(
            self.app_settings.get("spotify_cookie_file", "")
        )
        self.spotify_cookie_file.setPlaceholderText(
            "Opcjonalnie: ścieżka do cookies.txt z YouTube"
        )
        self.spotify_cookie_file.editingFinished.connect(
            self.save_spotify_cookie_path
        )
        cookie_row.addWidget(self.spotify_cookie_file, 1)

        self.spotify_cookie_browse_btn = QPushButton("📂 Wybierz")
        self.spotify_cookie_browse_btn.clicked.connect(
            self.choose_spotify_cookie_file
        )
        cookie_row.addWidget(self.spotify_cookie_browse_btn)

        form.addRow("🍪 Cookies YouTube:", cookie_row)

        layout.addLayout(form)

        buttons = QHBoxLayout()
        self.spotify_download_btn = QPushButton("⬇️ Pobierz brakujące")
        self.spotify_download_btn.clicked.connect(self.start_spotify_download)
        buttons.addWidget(self.spotify_download_btn)

        self.spotify_add_queue_btn = QPushButton("➕ Dodaj do kolejki")
        self.spotify_add_queue_btn.clicked.connect(self.add_spotify_to_queue)
        buttons.addWidget(self.spotify_add_queue_btn)

        self.spotify_clear_btn = QPushButton("Wyczyść")
        self.spotify_clear_btn.clicked.connect(self.spotify_url_edit.clear)
        buttons.addWidget(self.spotify_clear_btn)

        self.spotify_pause_btn = QPushButton("⏸ Wstrzymaj")
        self.spotify_pause_btn.setEnabled(False)
        self.spotify_pause_btn.clicked.connect(self.pause_spotify_download)
        buttons.addWidget(self.spotify_pause_btn)

        self.spotify_resume_btn = QPushButton("▶ Wznów")
        self.spotify_resume_btn.setEnabled(False)
        self.spotify_resume_btn.clicked.connect(self.resume_spotify_download)
        buttons.addWidget(self.spotify_resume_btn)

        self.spotify_cancel_btn = QPushButton("⛔ Anuluj")
        self.spotify_cancel_btn.setEnabled(False)
        self.spotify_cancel_btn.clicked.connect(self.confirm_cancel_spotify_download)
        buttons.addWidget(self.spotify_cancel_btn)

        buttons.addStretch()
        layout.addLayout(buttons)

        progress_row = QHBoxLayout()
        self.spotify_progress = QLabel("Gotowy.")
        progress_row.addWidget(self.spotify_progress, 1)

        self.spotify_progress_bar = QProgressBar()
        self.spotify_progress_bar.setRange(0, 100)
        self.spotify_progress_bar.setValue(0)
        self.spotify_progress_bar.setTextVisible(True)
        self.spotify_progress_bar.setFormat("Pobrano 0/0")
        progress_row.addWidget(self.spotify_progress_bar, 2)

        self.spotify_progress_count = QLabel("Pobrano 0/0")
        progress_row.addWidget(self.spotify_progress_count)
        layout.addLayout(progress_row)

        stats_row = QHBoxLayout()
        self.spotify_speed_label = QLabel("🚀 Prędkość: —")
        self.spotify_eta_label = QLabel("⏱️ ETA: —")
        self.spotify_queue_btn = QPushButton("📋 Kolejka: 0(0)")
        self.spotify_queue_btn.setFlat(True)
        self.spotify_queue_btn.clicked.connect(self.toggle_spotify_queue)
        stats_row.addWidget(self.spotify_speed_label)
        stats_row.addWidget(self.spotify_eta_label)
        stats_row.addWidget(self.spotify_queue_btn)
        stats_row.addStretch()
        layout.addLayout(stats_row)

        self.spotify_queue_tree = QTreeWidget()
        self.spotify_queue_tree.setHeaderHidden(True)
        self.spotify_queue_tree.setMaximumHeight(260)
        self.spotify_queue_tree.setVisible(False)
        self.spotify_queue_tree.setSelectionMode(QAbstractItemView.SingleSelection)
        layout.addWidget(self.spotify_queue_tree)

        queue_actions = QHBoxLayout()
        self.spotify_remove_queue_btn = QPushButton("🗑 Usuń z kolejki")
        self.spotify_remove_queue_btn.setVisible(False)
        self.spotify_remove_queue_btn.setEnabled(False)
        self.spotify_remove_queue_btn.clicked.connect(
            self.remove_selected_spotify_queue_item
        )
        queue_actions.addWidget(self.spotify_remove_queue_btn)
        queue_actions.addStretch()
        layout.addLayout(queue_actions)

        self.spotify_queue_tree.itemSelectionChanged.connect(
            self.update_spotify_queue_actions
        )
        self.spotify_queue_tree.itemClicked.connect(
            self.spotify_queue_item_clicked
        )

        self.spotify_log = QListWidget()
        self.spotify_log.setSelectionMode(QAbstractItemView.NoSelection)
        layout.addWidget(self.spotify_log, 1)

        error_row = QHBoxLayout()
        self.spotify_errors_btn = QPushButton("📕 Książka błędów (0)")
        self.spotify_errors_btn.clicked.connect(
            lambda: self.tabs.setCurrentWidget(self.error_book_tab)
        )
        error_row.addWidget(self.spotify_errors_btn)
        error_row.addStretch()
        layout.addLayout(error_row)

        self.spotify_download_total = 0
        self.spotify_download_done = 0
        self.spotify_download_started_at = None
        self.spotify_current_track = ""
        self.spotify_current_source_url = ""
        self.spotify_queue = []
        self.spotify_active_queue_index = -1
        self.spotify_cancelled = False
        self.spotify_start_after_metadata = False
        self.spotify_active_error_count = 0
        self.spotify_metadata_pending = []
        self.spotify_metadata_current_url = None
        self.spotify_metadata_output = bytearray()
        self.spotify_last_download_bytes = 0
        self.spotify_last_speed_time = None
        self.spotify_last_speed_bytes = 0
        self.spotify_current_track = ""

        self.spotify_process = QProcess(self)
        self.spotify_process.setProcessChannelMode(
            QProcess.MergedChannels
        )
        self.spotify_process.readyReadStandardOutput.connect(
            self.spotify_process_output
        )
        self.spotify_process.finished.connect(
            self.spotify_download_finished
        )

        self.spotify_speed_timer = QTimer(self)
        self.spotify_speed_timer.setInterval(1000)
        self.spotify_speed_timer.timeout.connect(
            self.update_spotify_speed
        )
        self.spotify_speed_last_bytes = 0
        self.spotify_speed_last_time = None

        self.spotify_metadata_process = QProcess(self)
        self.spotify_metadata_process.setProcessChannelMode(
            QProcess.MergedChannels
        )
        self.spotify_metadata_process.readyReadStandardOutput.connect(
            self.spotify_metadata_output_ready
        )
        self.spotify_metadata_process.finished.connect(
            self.spotify_metadata_finished
        )

    def save_spotify_cookie_path(self):
        path = self.spotify_cookie_file.text().strip()
        self.app_settings["spotify_cookie_file"] = path
        self.save_app_settings()

    def choose_spotify_cookie_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Wybierz plik cookies.txt",
            str(Path.home()),
            "Pliki cookies (*.txt);;Wszystkie pliki (*.*)",
        )
        if path:
            path = str(Path(path).resolve())
            self.spotify_cookie_file.setText(path)
            self.app_settings["spotify_cookie_file"] = path
            self.save_app_settings()

    def _validate_spotify_url(self, url):
        if not url:
            QMessageBox.warning(
                self, "Spotify",
                "Wklej najpierw link do utworu albo playlisty Spotify."
            )
            return False
        if "open.spotify.com/" not in url:
            QMessageBox.warning(
                self, "Spotify",
                "To nie wygląda na link Spotify."
            )
            return False
        return True

    def _queue_label_from_url(self, url):
        match = re.search(r"open\.spotify\.com/(playlist|album|track|artist)/([^?]+)", url)
        if not match:
            return "Spotify"
        kind, ident = match.groups()
        names = {
            "playlist": "Playlist",
            "album": "Album",
            "track": "Utwór",
            "artist": "Artysta",
        }
        return f"{names[kind]} {ident[:8]}"

    def add_spotify_to_queue(self):
        url = self.spotify_url_edit.text().strip()
        if not self._validate_spotify_url(url):
            return

        if any(item["url"] == url for item in self.spotify_queue):
            self.spotify_progress.setText("ℹ️ Ta pozycja jest już w kolejce.")
            return

        item = {
            "url": url,
            "name": self._queue_label_from_url(url),
            "count": None,
            "tracks": [],
            "done": 0,
            "status": "queued",
        }
        self.spotify_queue.append(item)
        self.refresh_spotify_queue()
        self.spotify_progress.setText(
            f"➕ Dodano do kolejki: {item['name']}"
        )
        self.enqueue_spotify_metadata_resolution(url)

    def enqueue_spotify_metadata_resolution(self, url):
        if url not in self.spotify_metadata_pending:
            self.spotify_metadata_pending.append(url)
        self.start_next_spotify_metadata_resolution()

    def start_next_spotify_metadata_resolution(self):
        if self.spotify_metadata_process.state() != QProcess.NotRunning:
            return
        if not self.spotify_metadata_pending:
            return

        url = self.spotify_metadata_pending.pop(0)
        self.spotify_metadata_current_url = url
        self.spotify_metadata_output = bytearray()
        self.spotify_metadata_process.start(
            "spotdl",
            ["save", url, "--save-file", "-"]
        )

    def spotify_metadata_output_ready(self):
        self.spotify_metadata_output.extend(
            bytes(self.spotify_metadata_process.readAllStandardOutput())
        )

    def _extract_spotify_tracks_from_metadata(self, payload):
        tracks = []
        seen = set()

        def add_song(value):
            if not isinstance(value, dict):
                return

            url = value.get("url")
            if not (
                isinstance(url, str)
                and url.startswith("https://open.spotify.com/track/")
            ):
                return
            if url in seen:
                return

            artists = value.get("artists") or value.get("artist") or []
            if isinstance(artists, list):
                names = []
                for artist in artists:
                    if isinstance(artist, dict):
                        names.append(str(artist.get("name", "")))
                    else:
                        names.append(str(artist))
                artist_text = ", ".join(x for x in names if x)
            else:
                artist_text = str(artists)

            tracks.append({
                "url": url,
                "title": str(
                    value.get("name")
                    or value.get("title")
                    or "Nieznany tytuł"
                ),
                "artist": artist_text or "Nieznany artysta",
                "list_name": value.get("list_name"),
                "list_url": value.get("list_url"),
                "list_position": value.get("list_position"),
                "list_length": value.get("list_length"),
                "album_name": value.get("album_name"),
            })
            seen.add(url)

        def walk(value):
            if isinstance(value, dict):
                add_song(value)
                for child in value.values():
                    walk(child)
            elif isinstance(value, list):
                for child in value:
                    walk(child)

        walk(payload)
        return tracks

    def _extract_collection_name(self, payload):
        # `spotdl save ... --save-file -` returns a list of Song dictionaries.
        # For playlist/album entries, list_name/list_url identify the actual
        # Spotify collection name. This is more reliable than guessing from
        # an album ID.
        def walk(value):
            if isinstance(value, dict):
                name = value.get("list_name")
                url = value.get("list_url")
                if isinstance(name, str) and name.strip():
                    return name.strip(), url
                for child in value.values():
                    found = walk(child)
                    if found:
                        return found
            elif isinstance(value, list):
                for child in value:
                    found = walk(child)
                    if found:
                        return found
            return None

        return walk(payload)

    def _spotify_match_key(self, value):
        value = str(value or "").casefold()
        value = re.sub(r"[^\w]+", " ", value, flags=re.UNICODE)
        return " ".join(value.split())

    def apply_spotify_playlist_tags(self, playlist_name, tracks):
        """Assign downloaded/local songs to Spotify/<playlist> and persist the tag."""
        playlist_name = str(playlist_name or "").strip()
        if not playlist_name or not tracks:
            return

        # The metadata is normally available before the download starts, but
        # the files are not in the library yet. Therefore this method is also
        # called after spotDL finishes and the source folder has been rescanned.
        try:
            self.refresh_library_from_source_folder()
        except Exception:
            pass

        by_artist_title = {}
        by_title = {}
        for song in self.songs:
            artist_key = self._spotify_match_key(getattr(song, "artist", ""))
            title_key = self._spotify_match_key(getattr(song, "title", ""))
            if title_key:
                by_title.setdefault(title_key, []).append(song)
            if artist_key and title_key:
                by_artist_title.setdefault(
                    (artist_key, title_key), []
                ).append(song)

        matched = []
        for track in tracks:
            artist_key = self._spotify_match_key(track.get("artist", ""))
            title_key = self._spotify_match_key(track.get("title", ""))
            candidates = by_artist_title.get((artist_key, title_key), [])

            # spotDL/Spotify can format featured artists differently. If an
            # exact artist+title match fails, fall back to title-only when it
            # identifies exactly one local song.
            if not candidates and title_key:
                candidates = by_title.get(title_key, [])
                if len(candidates) > 1 and artist_key:
                    narrowed = [
                        s for s in candidates
                        if artist_key in self._spotify_match_key(
                            getattr(s, "artist", "")
                        )
                        or self._spotify_match_key(getattr(s, "artist", "")) in artist_key
                    ]
                    candidates = narrowed

            for song in candidates:
                if song not in matched:
                    matched.append(song)

        # Ensure Spotify is a real tag category and the playlist is generated
        # in the dedicated Spotify folder.
        self.playlist_folder_map.setdefault("__folders__", [])
        if "Spotify" not in self.playlist_folder_map["__folders__"]:
            self.playlist_folder_map["__folders__"].append("Spotify")

        existing = {
            p["name"].casefold(): p
            for p in self.playlists
        }
        playlist = existing.get(playlist_name.casefold())
        if playlist is None:
            playlist = {"name": playlist_name, "paths": []}
            self.playlists.append(playlist)

        playlist["paths"] = [
            self._normalize_playlist_path(song.path)
            for song in matched
        ]
        self.playlist_folder_map[playlist["name"]] = "Spotify"
        self.playlist_generated_map[playlist["name"]] = True

        # Persist Spotify/<playlist> as an ordinary grouping category.
        for song in matched:
            try:
                grouping = parse_grouping(read_grouping(song.path))
            except Exception:
                grouping = {}

            values = grouping.get("Spotify", [])
            if not isinstance(values, list):
                values = [values] if values else []

            if playlist_name not in values:
                values.append(playlist_name)
                grouping["Spotify"] = values
                song.grouping = save_grouping(song.path, grouping)
                update_song(song)

        save_playlists(self.playlists)
        self.save_playlist_folder_map()
        self.save_playlist_generated_map()
        if hasattr(self, "playlist_list"):
            self.refresh_playlist_list()

        self.spotify_progress.setText(
            f"🏷️ Spotify → {playlist_name}: przypisano {len(matched)} utworów."
        )

    def spotify_metadata_finished(self, exit_code, exit_status):
        url = self.spotify_metadata_current_url
        output = bytes(self.spotify_metadata_output).decode(
            "utf-8", errors="replace"
        )
        payload = None

        # spotDL may print log lines before the JSON. Find the first valid
        # JSON array/object.
        for match in re.finditer(r"[\[{]", output):
            try:
                payload, _ = json.JSONDecoder().raw_decode(
                    output[match.start():]
                )
                break
            except json.JSONDecodeError:
                continue

        tracks = (
            self._extract_spotify_tracks_from_metadata(payload)
            if payload is not None else []
        )
        collection = (
            self._extract_collection_name(payload)
            if payload is not None else None
        )

        # Fallback: spotDL always logs "Found N songs in NAME (Playlist/Album)".
        found_match = re.search(
            r"Found\s+(\d+)\s+songs?\s+in\s+(.+?)\s+\((Playlist|Album)\)",
            output,
            re.IGNORECASE,
        )
        found_count = int(found_match.group(1)) if found_match else None
        found_name = found_match.group(2).strip() if found_match else None
        found_kind = found_match.group(3).lower() if found_match else ""

        for item in self.spotify_queue:
            if item["url"] != url:
                continue

            if tracks:
                item["tracks"] = tracks
                item["count"] = len(tracks)

                # The exact Spotify collection name lives on each Song.
                first = tracks[0]
                exact_name = first.get("list_name")
                exact_url = first.get("list_url")
                if exact_name:
                    item["name"] = exact_name
                elif collection:
                    item["name"] = collection[0]
                if exact_url:
                    item["resolved_url"] = exact_url

                self.backfill_spotify_error_links(
                    item.get("url", ""), tracks
                )
                # Tagowanie Spotify wykonujemy po zakończeniu pobierania,
                # gdy nowe pliki są już obecne w Bibliotece.

            if found_count is not None:
                item["count"] = found_count
            elif item.get("count") is None:
                item["count"] = 1 if "/track/" in url else 0

            if found_name:
                item["name"] = found_name
            break

        self.refresh_spotify_queue()
        self.start_next_spotify_metadata_resolution()

    def toggle_spotify_queue(self):
        visible = not self.spotify_queue_tree.isVisible()
        self.spotify_queue_tree.setVisible(visible)
        self.spotify_remove_queue_btn.setVisible(visible)
        if visible:
            self.refresh_spotify_queue()

    def spotify_queue_item_clicked(self, item, column=0):
        if item is None:
            return
        if item.data(0, Qt.UserRole) != "playlist":
            return

        index = item.data(0, Qt.UserRole + 1)
        if not isinstance(index, int) or not (0 <= index < len(self.spotify_queue)):
            return

        queue_item = self.spotify_queue[index]
        if not queue_item.get("tracks"):
            # Metadata is only a UI enhancement; fetching it here never
            # interrupts the active spotDL download.
            self.enqueue_spotify_metadata_resolution(queue_item["url"])
        else:
            item.setExpanded(not item.isExpanded())

    def backfill_spotify_error_links(self, queue_url, tracks):
        if not queue_url or not tracks:
            return

        changed = False
        for entry in self.spotify_errors:
            if entry.get("queue_url") != queue_url:
                continue
            if entry.get("url", "").startswith("https://open.spotify.com/track/"):
                continue

            idx = entry.get("track_index")
            if not isinstance(idx, int) or idx < 0 or idx >= len(tracks):
                continue

            track = tracks[idx]
            entry["url"] = track.get("url", "")
            entry["artist"] = track.get("artist", entry.get("artist", "Nieznany artysta"))
            entry["title"] = track.get("title", entry.get("title", "Nieznany tytuł"))
            changed = True

        if changed:
            self.save_spotify_errors()
            self.refresh_error_book()

    def update_spotify_queue_actions(self):
        item = self.spotify_queue_tree.currentItem()
        can_remove = item is not None
        if can_remove and item.data(0, Qt.UserRole) == "track":
            can_remove = False
        if can_remove and item.data(0, Qt.UserRole) == "playlist":
            index = item.data(0, Qt.UserRole + 1)
            can_remove = index != self.spotify_active_queue_index
        self.spotify_remove_queue_btn.setEnabled(can_remove)

    def remove_selected_spotify_queue_item(self):
        item = self.spotify_queue_tree.currentItem()
        if item is None:
            return
        if item.data(0, Qt.UserRole) != "playlist":
            return

        index = item.data(0, Qt.UserRole + 1)
        if index == self.spotify_active_queue_index:
            QMessageBox.information(
                self,
                "Kolejka",
                "Nie można usunąć aktualnie pobieranej playlisty. "
                "Najpierw anuluj jej pobieranie."
            )
            return

        if not (0 <= index < len(self.spotify_queue)):
            return

        removed = self.spotify_queue.pop(index)
        self.spotify_metadata_pending = [
            u for u in self.spotify_metadata_pending
            if u != removed.get("url")
        ]

        if self.spotify_active_queue_index > index:
            self.spotify_active_queue_index -= 1

        self.refresh_spotify_queue()
        self.spotify_progress.setText(
            f"🗑 Usunięto z kolejki: {removed.get('name', 'playlistę')}"
        )

    def refresh_spotify_queue(self):
        if not hasattr(self, "spotify_queue_tree"):
            return

        self.spotify_queue_tree.clear()
        current_remaining = 0
        future_total = 0
        future_unknown = 0

        for index, item in enumerate(self.spotify_queue):
            count = item.get("count")
            remaining = max(0, (count or 0) - item.get("done", 0))

            if index == self.spotify_active_queue_index:
                current_remaining = remaining
            elif index > self.spotify_active_queue_index:
                if count is None:
                    future_unknown += 1
                else:
                    future_total += remaining

            if item.get("status") == "active":
                prefix = "📥"
            elif item.get("status") == "done":
                prefix = "✅"
            else:
                prefix = "⏳"

            count_text = "…" if count is None else str(remaining)
            playlist_item = QTreeWidgetItem(
                [f"{prefix} {item.get('name', 'Spotify')} ({count_text})"]
            )
            playlist_item.setToolTip(0, item.get("url", ""))
            playlist_item.setChildIndicatorPolicy(
                QTreeWidgetItem.ShowIndicator
            )
            playlist_item.setData(0, Qt.UserRole, "playlist")
            playlist_item.setData(0, Qt.UserRole + 1, index)
            self.spotify_queue_tree.addTopLevelItem(playlist_item)

            for track in item.get("tracks", []):
                pos = track.get("list_position")
                pos_text = f"{pos}. " if pos else ""
                track_item = QTreeWidgetItem([
                    f"{pos_text}🎵 {track.get('artist', 'Nieznany artysta')} — "
                    f"{track.get('title', 'Nieznany tytuł')}"
                ])
                track_item.setData(0, Qt.UserRole, "track")
                track_item.setData(0, Qt.UserRole + 1, index)
                track_item.setToolTip(0, track.get("url", ""))
                playlist_item.addChild(track_item)

        # Pokazujemy tylko liczbę utworów pozostałych w aktualnej
        # playliście. Lista kolejek nadal jest dostępna po kliknięciu.
        self.spotify_queue_btn.setText(
            f"📋 Kolejka: {current_remaining}"
        )
        self.update_spotify_queue_actions()

    def _start_next_spotify_queue_item(self):
        if self.spotify_process.state() != QProcess.NotRunning:
            return

        next_index = None
        for index, item in enumerate(self.spotify_queue):
            if item.get("status") == "queued":
                next_index = index
                break

        if next_index is None:
            self.spotify_active_queue_index = -1
            self.refresh_spotify_queue()
            self.spotify_download_btn.setEnabled(True)
            self.spotify_add_queue_btn.setEnabled(True)
            return

        item = self.spotify_queue[next_index]

        # Metadata jest pomocnicze (nazwy, liczby i dokładne linki błędów).
        # Nie może blokować właściwego pobierania.
        if "/track/" not in item["url"] and not item.get("tracks"):
            if item["url"] not in self.spotify_metadata_pending:
                self.enqueue_spotify_metadata_resolution(item["url"])

        self.spotify_active_queue_index = next_index
        self.spotify_cancelled = False
        self.spotify_active_error_count = 0
        item["status"] = "active"
        item["done"] = 0
        self.spotify_current_source_url = item["url"]
        self.spotify_current_track = ""
        self.spotify_download_total = item.get("count") or 0
        self.spotify_download_done = 0
        self.spotify_download_started_at = datetime.now()
        self.spotify_speed_last_bytes = self.source_folder_bytes()
        self.spotify_speed_last_time = datetime.now()

        self.spotify_log.clear()
        self.spotify_progress.setText(
            f"📥 Pobieranie: {item['name']}"
        )
        self.spotify_progress_bar.setRange(
            0, self.spotify_download_total or 0
        )
        self.spotify_progress_bar.setValue(0)
        self.spotify_progress_bar.setFormat(
            f"Pobrano 0/{self.spotify_download_total or '—'}"
        )
        self.spotify_progress_count.setText(
            f"Pobrano 0/{self.spotify_download_total or '—'}"
        )
        self.spotify_pause_btn.setEnabled(True)
        self.spotify_resume_btn.setEnabled(False)
        self.spotify_cancel_btn.setEnabled(True)
        self.spotify_download_btn.setEnabled(False)
        self.spotify_add_queue_btn.setEnabled(True)

        folder = Path(self.app_settings["source_folder"])
        output = str(folder / "{artists} - {title}.{output-ext}")

        args = [
            "download",
            item["url"],
            "--output", output,
            "--format", "m4a",
            "--bitrate", "disable",
            "--overwrite", "skip",
            "--scan-for-songs",
        ]

        cookie_file = self.spotify_cookie_file.text().strip()
        if cookie_file:
            self.app_settings["spotify_cookie_file"] = cookie_file
            self.save_app_settings()
            if not Path(cookie_file).is_file():
                QMessageBox.warning(
                    self, "Spotify",
                    "Podany plik cookies nie istnieje."
                )
                item["status"] = "queued"
                self.spotify_download_btn.setEnabled(True)
                self.spotify_add_queue_btn.setEnabled(True)
                self.refresh_spotify_queue()
                return
            args.extend(["--cookie-file", cookie_file])

        self.spotify_speed_timer.start()

        # spotDL runs as a Python console app. On Windows it can inherit the
        # legacy cp1250 console encoding and crash on emoji/non-ASCII output.
        env = QProcessEnvironment.systemEnvironment()
        env.insert("PYTHONUTF8", "1")
        env.insert("PYTHONIOENCODING", "utf-8")
        env.insert("LC_ALL", "C.UTF-8")
        env.insert("LANG", "C.UTF-8")
        self.spotify_process.setProcessEnvironment(env)
        self.spotify_process.start("spotdl", args)

    def start_spotify_download(self):
        url = self.spotify_url_edit.text().strip()
        if not self._validate_spotify_url(url):
            return

        existing = next(
            (i for i in self.spotify_queue if i["url"] == url),
            None
        )
        if existing is None:
            self.add_spotify_to_queue()

        self._start_next_spotify_queue_item()

    @staticmethod
    def _format_bytes(value):
        value = float(value)
        for unit in ("B", "KiB", "MiB", "GiB"):
            if abs(value) < 1024 or unit == "GiB":
                return f"{value:.1f} {unit}"
            value /= 1024
        return f"{value:.1f} GiB"

    @staticmethod
    def _format_duration(seconds):
        seconds = max(0, int(seconds))
        hours, remainder = divmod(seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        if hours:
            return f"{hours}h {minutes:02d}min {seconds:02d}s"
        return f"{minutes}min {seconds:02d}s"

    def source_folder_bytes(self):
        try:
            root = Path(self.app_settings["source_folder"])
            total = 0
            for f in root.rglob("*"):
                if f.is_file() and f.suffix.lower() in {
                    ".mp3", ".m4a", ".mp4", ".flac", ".wav",
                    ".aac", ".ogg", ".opus", ".wma", ".aiff",
                }:
                    try:
                        total += f.stat().st_size
                    except OSError:
                        pass
            return total
        except OSError:
            return 0

    def update_spotify_speed(self):
        if self.spotify_process.state() == QProcess.NotRunning:
            return
        now = datetime.now()
        current_bytes = self.source_folder_bytes()
        if self.spotify_speed_last_time:
            elapsed = (now - self.spotify_speed_last_time).total_seconds()
            if elapsed >= 0.8:
                speed = max(0, current_bytes - self.spotify_speed_last_bytes) / elapsed
                if speed > 0:
                    self.spotify_speed_label.setText(
                        f"🚀 Prędkość: {self._format_bytes(speed)}/s"
                    )
                    self.refresh_spotify_queue()
                self.spotify_speed_last_bytes = current_bytes
                self.spotify_speed_last_time = now

    def spotify_process_output(self):
        data = bytes(self.spotify_process.readAllStandardOutput())
        if not data:
            return

        text = data.decode("utf-8", errors="replace")
        for raw_line in text.splitlines():
            line = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", raw_line).strip()
            if not line:
                continue

            # Nie pokazujemy linków YouTube/Spotify w logu. Zostawiamy
            # komunikat o utworze, bo to jest dla użytkownika istotne.
            urls = re.findall(r"https?://\S+", line)
            if urls:
                if "Processing query:" in line:
                    self.spotify_current_source_url = urls[0].rstrip(")]>,")
            cleaned = re.sub(r"https?://\S+", "", line).strip()
            cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
            if not cleaned:
                continue

            # Czytelne oznaczenia statusu w logu:
            # 📥 pobrano, ⏭️ pominięto istniejący, ❌ błąd.
            if cleaned.startswith("Downloaded "):
                display_line = "📥 " + cleaned
            elif cleaned.startswith("Skipping "):
                display_line = "⏭️ " + cleaned
            elif (
                "ERROR" in cleaned.upper()
                or cleaned.startswith("Failed ")
                or cleaned.startswith("Exception")
                or cleaned.startswith("Unable to ")
                or "could not" in cleaned.lower()
            ):
                display_line = "❌ " + cleaned
                self.record_spotify_error(cleaned, line)
            else:
                display_line = cleaned

            self.spotify_log.addItem(display_line)
            self.spotify_log.scrollToBottom()

            # Zachowujemy nazwę bieżącego utworu do podglądu kolejki.
            if cleaned.startswith("Downloaded "):
                self.spotify_current_track = cleaned[len("Downloaded "):].strip()
            elif cleaned.startswith("Skipping "):
                self.spotify_current_track = cleaned[len("Skipping "):].strip()
            else:
                quoted_track = re.search(r'"([^"]+\s-\s[^"]+)"', cleaned)
                if quoted_track:
                    self.spotify_current_track = quoted_track.group(1).strip()

            # Próba odczytu postępu yt-dlp, np. "[download] 42.3% of 8.00MiB at 1.20MiB/s ETA 00:03".
            progress_match = re.search(
                r"(\d+(?:\.\d+)?)%.*?(?:(\d+(?:\.\d+)?)\s*(KiB|MiB|GiB)/s).*?(?:ETA\s+([0-9:]+))?",
                cleaned,
                re.IGNORECASE
            )
            if progress_match:
                speed_value = float(progress_match.group(2))
                speed_unit = progress_match.group(3).lower()
                multiplier = {
                    "kib": 1024,
                    "mib": 1024 ** 2,
                    "gib": 1024 ** 3,
                }[speed_unit]
                speed_bps = speed_value * multiplier
                self.spotify_speed_label.setText(
                    f"🚀 Prędkość: {self._format_bytes(speed_bps)}/s"
                )
                eta = progress_match.group(4)
                if eta:
                    self.spotify_eta_label.setText(f"⏱️ ETA: {eta}")

            # spotDL wypisuje liczbę utworów podczas skanowania playlisty.
            match = re.search(
                r"(?:Found|found)\s+(\d+)\s+(?:songs|tracks)\s+in\s+(.+?)\s+\((Playlist|Album)\)",
                cleaned
            )
            if match:
                self.spotify_download_total = int(match.group(1))
                if 0 <= self.spotify_active_queue_index < len(self.spotify_queue):
                    active_item = self.spotify_queue[self.spotify_active_queue_index]
                    active_item["count"] = self.spotify_download_total
                    active_item["name"] = match.group(2).strip()
                self.refresh_spotify_queue()
            else:
                count_only_match = re.search(
                    r"(?:Found|found|Processing)\s+(\d+)\s+(?:songs|tracks)",
                    cleaned
                )
                if count_only_match:
                    self.spotify_download_total = int(count_only_match.group(1))
                if self.spotify_download_total > 0:
                    self.spotify_progress_bar.setRange(
                        0, self.spotify_download_total
                    )
                    self.spotify_progress_bar.setValue(
                        min(
                            self.spotify_download_done,
                            self.spotify_download_total
                        )
                    )
                    self.spotify_progress_bar.setFormat(
                        f"Pobrano {self.spotify_download_done}/"
                        f"{self.spotify_download_total}"
                    )
                    self.spotify_progress_count.setText(
                        f"Pobrano {self.spotify_download_done}/"
                        f"{self.spotify_download_total}"
                    )

            completed = (
                cleaned.startswith("Downloaded ")
                or cleaned.startswith("Skipping ")
            )
            if completed:
                self.spotify_download_done += 1

                if self.spotify_download_total > 0:
                    done = min(
                        self.spotify_download_done,
                        self.spotify_download_total
                    )
                    self.spotify_progress_bar.setRange(
                        0, self.spotify_download_total
                    )
                    self.spotify_progress_bar.setValue(done)
                    self.spotify_progress_bar.setFormat(
                        f"Pobrano {done}/{self.spotify_download_total}"
                    )
                    self.spotify_progress_count.setText(
                        f"Pobrano {done}/{self.spotify_download_total}"
                    )
                    remaining = max(
                        0, self.spotify_download_total - done
                    )
                    if 0 <= self.spotify_active_queue_index < len(self.spotify_queue):
                        active_item = self.spotify_queue[self.spotify_active_queue_index]
                        active_item["done"] = done
                    self.refresh_spotify_queue()
                    if self.spotify_download_started_at and done:
                        elapsed = (
                            datetime.now() - self.spotify_download_started_at
                        ).total_seconds()
                        if elapsed > 0:
                            per_item = elapsed / done
                            remaining_seconds = int(
                                per_item * remaining
                            )
                            self.spotify_eta_label.setText(
                                f"⏱️ ETA: {self._format_duration(remaining_seconds)}"
                            )
                else:
                    self.spotify_progress_bar.setFormat(
                        f"Pobrano {self.spotify_download_done}/—"
                    )
                    self.spotify_progress_count.setText(
                        f"Pobrano {self.spotify_download_done}/—"
                    )

    def _set_spotify_process_suspended(self, suspended):
        if os.name != "nt":
            return False

        pid = int(self.spotify_process.processId())
        if not pid:
            return False

        try:
            ntdll = ctypes.WinDLL("ntdll")
            handle = ctypes.windll.kernel32.OpenProcess(
                0x0800 | 0x0400,  # PROCESS_SUSPEND_RESUME | PROCESS_QUERY_INFORMATION
                False,
                pid,
            )
            if not handle:
                return False

            try:
                if suspended:
                    status = ntdll.NtSuspendProcess(handle)
                else:
                    status = ntdll.NtResumeProcess(handle)
                return status == 0
            finally:
                ctypes.windll.kernel32.CloseHandle(handle)
        except (AttributeError, OSError):
            return False

    def pause_spotify_download(self):
        if self.spotify_process.state() == QProcess.NotRunning:
            return

        if self._set_spotify_process_suspended(True):
            self.spotify_progress.setText("⏸ Pobieranie wstrzymane.")
            self.spotify_pause_btn.setEnabled(False)
            self.spotify_resume_btn.setEnabled(True)
        else:
            QMessageBox.warning(
                self,
                "Spotify",
                "Nie udało się wstrzymać procesu spotDL."
            )

    def resume_spotify_download(self):
        if self.spotify_process.state() == QProcess.NotRunning:
            return

        if self._set_spotify_process_suspended(False):
            self.spotify_progress.setText("▶ Pobieranie wznowione…")
            self.spotify_pause_btn.setEnabled(True)
            self.spotify_resume_btn.setEnabled(False)
        else:
            QMessageBox.warning(
                self,
                "Spotify",
                "Nie udało się wznowić procesu spotDL."
            )

    def confirm_cancel_spotify_download(self):
        if self.spotify_process.state() == QProcess.NotRunning:
            return

        answer = QMessageBox.question(
            self,
            "Anuluj pobieranie",
            "Czy na pewno chcesz przerwać pobieranie?\n\n"
            "Utwory już zapisane na dysku pozostaną na miejscu.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return

        self.cancel_spotify_download()

    def cancel_spotify_download(self):
        if self.spotify_process.state() == QProcess.NotRunning:
            return

        pid = int(self.spotify_process.processId())

        # taskkill /T zatrzymuje także procesy potomne, np. yt-dlp uruchomione
        # przez spotDL. Jest używane tylko po wyraźnym potwierdzeniu użytkownika.
        if os.name == "nt" and pid:
            try:
                QProcess.execute(
                    "taskkill",
                    ["/PID", str(pid), "/T", "/F"]
                )
            except Exception:
                self.spotify_process.kill()
        else:
            self.spotify_process.kill()

        self.spotify_cancelled = True
        self.spotify_progress.setText("⛔ Pobieranie anulowane.")
        if 0 <= self.spotify_active_queue_index < len(self.spotify_queue):
            self.spotify_queue[self.spotify_active_queue_index]["status"] = "queued"
            self.refresh_spotify_queue()

    def spotify_errors_file(self):
        return self.settings_file_path().parent / "spotify_error_book.json"

    def load_spotify_errors(self):
        path = self.spotify_errors_file()
        try:
            if path.exists():
                data = json.loads(path.read_text(encoding="utf-8"))
                return data if isinstance(data, list) else []
        except (OSError, ValueError, TypeError):
            pass
        return []

    def save_spotify_errors(self):
        try:
            self.spotify_errors_file().write_text(
                json.dumps(self.spotify_errors, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
        except OSError:
            pass

    def build_error_book_tab(self):
        layout = QVBoxLayout(self.error_book_tab)

        title = QLabel("📕 Książka błędów pobierania")
        title.setStyleSheet("font-size:18px;font-weight:bold;")
        layout.addWidget(title)

        info = QLabel(
            "Błędy są zapisywane między uruchomieniami DJLM. "
            "Możesz wrócić do nich później i otworzyć link ręcznie."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        self.error_book_list = QListWidget()
        layout.addWidget(self.error_book_list, 1)

        buttons = QHBoxLayout()
        self.error_open_btn = QPushButton("🌐 Otwórz link")
        self.error_open_btn.clicked.connect(self.open_selected_error_link)
        buttons.addWidget(self.error_open_btn)

        self.error_copy_btn = QPushButton("📋 Kopiuj link")
        self.error_copy_btn.clicked.connect(self.copy_selected_error_link)
        buttons.addWidget(self.error_copy_btn)

        self.error_remove_btn = QPushButton("🗑 Usuń wpis")
        self.error_remove_btn.clicked.connect(self.remove_selected_error)
        buttons.addWidget(self.error_remove_btn)

        buttons.addStretch()
        layout.addLayout(buttons)
        self.refresh_error_book()

    def refresh_error_book(self):
        if not hasattr(self, "error_book_list"):
            return
        self.error_book_list.clear()
        for e in self.spotify_errors:
            self.error_book_list.addItem(
                f"❌ {e.get('status','error (nie pobrano)')} | "
                f"{e.get('artist','Nieznany artysta')} — "
                f"{e.get('title','Nieznany tytuł')}\n"
                f"🔗 {e.get('url','brak linku')}\n"
                f"💬 {e.get('error','')}"
            )
        if hasattr(self, "spotify_errors_btn"):
            self.spotify_errors_btn.setText(
                f"📕 Książka błędów ({len(self.spotify_errors)})"
            )

    def selected_error(self):
        if not hasattr(self, "error_book_list"):
            return None
        row = self.error_book_list.currentRow()
        if 0 <= row < len(self.spotify_errors):
            return self.spotify_errors[row]
        return None

    def open_selected_error_link(self):
        entry = self.selected_error()
        if entry and entry.get("url"):
            QDesktopServices.openUrl(QUrl(entry["url"]))

    def copy_selected_error_link(self):
        entry = self.selected_error()
        if entry and entry.get("url"):
            QApplication.clipboard().setText(entry["url"])

    def remove_selected_error(self):
        row = self.error_book_list.currentRow()
        if 0 <= row < len(self.spotify_errors):
            self.spotify_errors.pop(row)
            self.save_spotify_errors()
            self.refresh_error_book()

    def record_spotify_error(self, error_text, raw_line=""):
        urls = re.findall(r"https?://\S+", raw_line)
        url = urls[0].rstrip(")]>,") if urls else ""
        if not url.startswith("https://open.spotify.com/track/"):
            url = ""

        title = "Nieznany tytuł"
        artist = "Nieznany artysta"

        quoted = re.search(r'"([^"]+)"', error_text)
        label = quoted.group(1).strip() if quoted else ""
        if " - " in label:
            artist, title = label.split(" - ", 1)
        elif label:
            title = label
        elif " - " in self.spotify_current_track:
            artist, title = self.spotify_current_track.rsplit(" - ", 1)

        active_item = (
            self.spotify_queue[self.spotify_active_queue_index]
            if 0 <= self.spotify_active_queue_index < len(self.spotify_queue)
            else None
        )
        queue_url = active_item.get("url", "") if active_item else ""
        track_index = None
        if active_item:
            tracks = active_item.get("tracks", [])
            track_index = (
                active_item.get("done", 0)
                + self.spotify_active_error_count
            )
            title_norm = title.strip().casefold()
            artist_norm = artist.strip().casefold()

            for track in tracks:
                if (
                    track.get("title", "").strip().casefold() == title_norm
                    and track.get("artist", "").strip().casefold() == artist_norm
                ):
                    url = track.get("url", "")
                    break

            if not url and self.spotify_current_track:
                current_norm = self.spotify_current_track.casefold()
                for track in tracks:
                    label = (
                        f"{track.get('artist','')} - "
                        f"{track.get('title','')}"
                    ).casefold()
                    if label == current_norm:
                        artist = track.get("artist", artist)
                        title = track.get("title", title)
                        url = track.get("url", "")
                        break

            # Jeśli spotDL nie poda nazwy utworu w komunikacie błędu,
            # metadata playlisty pozwala wskazać konkretny track URL.
            if not url and tracks and track_index is not None:
                if track_index < len(tracks):
                    track = tracks[track_index]
                    artist = track.get("artist", artist)
                    title = track.get("title", title)
                    url = track.get("url", "")

            self.spotify_active_error_count += 1

        if not url and active_item and "/track/" in active_item.get("url", ""):
            url = active_item["url"]

        entry = {
            "time": datetime.now().isoformat(timespec="seconds"),
            "status": "error (nie pobrano)",
            "title": title.strip(),
            "artist": artist.strip(),
            "url": url,
            "queue_url": queue_url,
            "track_index": track_index,
            "error": error_text,
        }
        self.spotify_errors.append(entry)
        self.save_spotify_errors()
        self.refresh_error_book()

    def update_spotify_error_button(self):
        self.refresh_error_book()

    def spotify_download_finished(self, exit_code, exit_status):
        self.spotify_speed_timer.stop()
        self.spotify_pause_btn.setEnabled(False)
        self.spotify_resume_btn.setEnabled(False)
        self.spotify_cancel_btn.setEnabled(False)

        active = (
            self.spotify_queue[self.spotify_active_queue_index]
            if 0 <= self.spotify_active_queue_index < len(self.spotify_queue)
            else None
        )

        if exit_code == 0 and exit_status == QProcess.NormalExit:
            self.spotify_eta_label.setText("⏱️ ETA: gotowe")
            if self.spotify_download_total > 0:
                self.spotify_progress_bar.setRange(
                    0, self.spotify_download_total
                )
                self.spotify_progress_bar.setValue(
                    self.spotify_download_total
                )
                self.spotify_progress_bar.setFormat(
                    f"Pobrano {self.spotify_download_total}/"
                    f"{self.spotify_download_total}"
                )
                self.spotify_progress_count.setText(
                    f"Pobrano {self.spotify_download_total}/"
                    f"{self.spotify_download_total}"
                )

            self.spotify_progress.setText(
                "✅ Pobieranie zakończone. Skanuję bibliotekę…"
            )
            # Ponownie skanujemy folder wejściowy. Ta metoda aktualizuje
            # Bibliotekę oraz sesję „Nowe utwory”, więc świeżo pobrane pliki
            # dostają od razu status 🆕.
            self.refresh_library_from_source_folder()

            # Dopiero teraz lokalne pliki istnieją w bibliotece, więc możemy
            # pewnie przypisać pobrane utwory do Spotify/<playlist>.
            if active and active.get("tracks"):
                self.apply_spotify_playlist_tags(
                    active.get("name"),
                    active.get("tracks", []),
                )

            self.refresh_new_tracks_tab()
            self.spotify_progress.setText(
                "✅ Gotowe — nowe pliki są dostępne w „Nowe utwory”."
            )
        else:
            self.spotify_progress.setText(
                f"❌ spotDL zakończył pracę z kodem {exit_code}."
            )

        if active:
            if self.spotify_cancelled:
                active["status"] = "queued"
                self.refresh_spotify_queue()
                self.spotify_download_btn.setEnabled(True)
                self.spotify_add_queue_btn.setEnabled(True)
                return

            active["done"] = active.get("count") or self.spotify_download_done
            active["status"] = "done"
            self.refresh_spotify_queue()

            # Kolejna playlista startuje automatycznie dopiero po pełnym
            # zakończeniu procesu spotDL poprzedniej.
            self._start_next_spotify_queue_item()

    def new_track_status_path(self):
        return self.settings_file_path().parent / "new_tracks_status.json"

    def new_track_session_path(self):
        return self.settings_file_path().parent / "new_tracks_session.json"

    def load_new_track_statuses(self):
        self.new_track_statuses = {}
        try:
            path = self.new_track_status_path()
            if path.exists():
                import json
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    self.new_track_statuses = {
                        str(k): str(v) for k, v in data.items()
                    }
        except (OSError, ValueError, TypeError):
            self.new_track_statuses = {}

    def save_new_track_statuses(self):
        try:
            import json
            path = self.new_track_status_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(self.new_track_statuses, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
        except OSError:
            pass

    def load_new_track_session(self):
        self.new_track_session = set()
        try:
            path = self.new_track_session_path()
            if path.exists():
                import json
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    self.new_track_session = {str(Path(p).resolve()) for p in data}
        except (OSError, ValueError, TypeError):
            self.new_track_session = set()

    def save_new_track_session(self):
        try:
            import json
            path = self.new_track_session_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(sorted(self.new_track_session), ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
        except OSError:
            pass

    def ensure_new_track_session(self):
        if not hasattr(self, "new_track_statuses"):
            self.load_new_track_statuses()
        if not hasattr(self, "new_track_session"):
            self.load_new_track_session()

        current_paths = {
            str(Path(song.path).resolve()) for song in self.songs
        }

        # Pierwsze uruchomienie po v0.8: każdy istniejący utwór bez statusu
        # staje się nowym kandydatem. Później trafiają tu tylko nowe pliki.
        for path in current_paths:
            if path not in self.new_track_statuses:
                self.new_track_statuses[path] = "new"
                self.new_track_session.add(path)

        # Utwory nadal niezatwierdzone pozostają w sesji.
        for path, status in self.new_track_statuses.items():
            if status in ("new", "todo") and path in current_paths:
                self.new_track_session.add(path)

        # Pliki usunięte z biblioteki znikają z bieżącej sesji i statusów.
        self.new_track_session.intersection_update(current_paths)
        self.new_track_statuses = {
            path: status
            for path, status in self.new_track_statuses.items()
            if path in current_paths
        }

        self.save_new_track_statuses()
        self.save_new_track_session()

    def new_track_status_label(self, status):
        return {
            "new": "🆕 Nowe",
            "tagged": "🏷️ Otagowane",
            "todo": "⚠️ Do uzupełnienia",
            "ready": "✅ Gotowe",
        }.get(status, "🆕 Nowe")

    def build_new_tracks_tab(self):
        layout = QVBoxLayout(self.new_tracks_tab)

        header = QHBoxLayout()
        title = QLabel("🆕 Nowe utwory")
        title.setStyleSheet("font-size:18px;font-weight:bold;")
        header.addWidget(title)
        header.addStretch()
        self.new_tracks_count = QLabel("0 w sesji")
        header.addWidget(self.new_tracks_count)
        layout.addLayout(header)

        info = QLabel(
            "To jest Twoja kolejka pracy. Zmiany tagów zapisują się automatycznie. "
            "Utwory zostają w tej sesji, dopóki ręcznie nie zakończysz pracy nad nimi."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        filters = QHBoxLayout()
        self.new_tracks_status = QComboBox()
        self.new_tracks_status.addItem("Wszystkie", "all")
        self.new_tracks_status.addItem("🆕 Nowe", "new")
        self.new_tracks_status.addItem("⚠️ Do uzupełnienia", "todo")
        filters.addWidget(QLabel("Status:"))
        filters.addWidget(self.new_tracks_status)

        self.new_tracks_search = QLineEdit()
        self.new_tracks_search.setPlaceholderText(
            "Szukaj po tytule, artyście lub albumie…"
        )
        filters.addWidget(self.new_tracks_search, 1)
        layout.addLayout(filters)

        content = QHBoxLayout()

        left = QVBoxLayout()
        self.new_tracks_list = QListWidget()
        self.new_tracks_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        left.addWidget(self.new_tracks_list)
        content.addLayout(left, 2)

        center = QVBoxLayout()
        center.addWidget(QLabel("Tytuł"))
        self.new_track_title = QLineEdit()
        self.new_track_title.setReadOnly(True)
        center.addWidget(self.new_track_title)

        center.addWidget(QLabel("Artysta"))
        self.new_track_artist = QLineEdit()
        self.new_track_artist.setReadOnly(True)
        center.addWidget(self.new_track_artist)

        center.addWidget(QLabel("Album"))
        self.new_track_album = QLineEdit()
        self.new_track_album.setReadOnly(True)
        center.addWidget(self.new_track_album)
        center.addStretch()
        content.addLayout(center, 1)

        self.new_tracks_tag_panel = TagPanel()
        self.new_tracks_tag_panel.tags_changed.connect(
            self.new_tracks_tags_changed
        )
        content.addWidget(self.new_tracks_tag_panel, 2)

        layout.addLayout(content, 1)

        actions = QHBoxLayout()
        self.new_tracks_finish_btn = QPushButton(
            "✅ Zakończ pracę nad zaznaczonymi"
        )
        self.new_tracks_finish_btn.setEnabled(False)
        actions.addWidget(self.new_tracks_finish_btn)

        actions.addStretch()
        self.new_tracks_refresh_btn = QPushButton("↻ Odśwież")
        actions.addWidget(self.new_tracks_refresh_btn)
        layout.addLayout(actions)

        self.new_tracks_status.currentIndexChanged.connect(
            self.refresh_new_tracks_tab
        )
        self.new_tracks_search.textChanged.connect(
            self.refresh_new_tracks_tab
        )
        self.new_tracks_refresh_btn.clicked.connect(
            self.refresh_new_tracks_tab
        )
        self.new_tracks_list.currentRowChanged.connect(
            self.new_track_selected
        )
        self.new_tracks_list.itemSelectionChanged.connect(
            self.update_new_tracks_actions
        )
        self.new_tracks_finish_btn.clicked.connect(
            self.finish_selected_new_tracks
        )

        self.load_new_track_statuses()
        self.load_new_track_session()
        self.refresh_new_tracks_tab()

    def update_new_tracks_badge(self):
        if not hasattr(self, "new_tracks_tab"):
            return
        count = len(getattr(self, "new_track_session", set()))
        tab_index = self.tabs.indexOf(self.new_tracks_tab)
        if tab_index < 0:
            return
        if count > 0:
            self.tabs.setTabText(tab_index, f"🆕 Nowe utwory  🟠 {count}")
        else:
            self.tabs.setTabText(tab_index, "🆕 Nowe utwory")

    def refresh_new_tracks_tab(self):
        if not hasattr(self, "new_tracks_list"):
            return

        self.ensure_new_track_session()
        self.new_tracks_list.clear()

        query = self.new_tracks_search.text().strip().lower()
        selected_status = self.new_tracks_status.currentData()

        session_songs = []
        for song in self.songs:
            path = str(Path(song.path).resolve())
            if path in self.new_track_session:
                session_songs.append(song)

        for song in session_songs:
            path = str(Path(song.path).resolve())
            status = self.new_track_statuses.get(path, "new")

            if selected_status != "all" and status != selected_status:
                continue

            title = getattr(song, "title", None) or Path(song.path).stem
            artist = getattr(song, "artist", None) or ""
            album = getattr(song, "album", None) or ""

            if query and query not in f"{title} {artist} {album}".lower():
                continue

            item = QListWidgetItem(
                f"{self.new_track_status_label(status)}  {title}"
                + (f" — {artist}" if artist else "")
            )
            item.setData(Qt.UserRole, path)
            self.new_tracks_list.addItem(item)

        active_count = len(self.new_track_session)
        self.new_tracks_count.setText(f"{active_count} w sesji")
        self.update_new_tracks_badge()
        self.update_new_tracks_actions()

    def new_track_selected(self, index):
        if index < 0 or index >= self.new_tracks_list.count():
            self.new_track_title.clear()
            self.new_track_artist.clear()
            self.new_track_album.clear()
            self.new_tracks_tag_panel.load_song("")
            return

        item = self.new_tracks_list.item(index)
        path = item.data(Qt.UserRole)
        song = self.song_by_path.get(path)

        if song is None:
            return

        self.new_track_title.setText(
            getattr(song, "title", None) or Path(song.path).stem
        )
        self.new_track_artist.setText(getattr(song, "artist", None) or "")
        self.new_track_album.setText(getattr(song, "album", None) or "")

        selected = self.get_selected_new_tracks()
        if len(selected) > 1:
            self.new_tracks_tag_panel.load_songs(
                [read_grouping(s.path) for s in selected]
            )
        else:
            self.new_tracks_tag_panel.load_song(
                read_grouping(song.path)
            )

    def get_selected_new_tracks(self):
        result = []
        for item in self.new_tracks_list.selectedItems():
            path = item.data(Qt.UserRole)
            song = self._find_song_for_playlist_path(path)
            if song is not None:
                result.append(song)
        return result

    def new_tracks_tags_changed(self):
        if self._history_busy:
            return

        selected = self.get_selected_new_tracks()
        changes = self.new_tracks_tag_panel.get_changes()
        if not selected or not changes:
            return

        entry = []
        for song in selected:
            before = read_grouping(song.path)
            tags = parse_grouping(before)

            for category, value, should_have in changes:
                values = tags.setdefault(category, [])
                if should_have and value not in values:
                    values.append(value)
                elif not should_have and value in values:
                    values.remove(value)

            after = save_grouping(song.path, tags)
            song.grouping = after
            update_song(song)
            entry.append((song, before, after))

        # Pierwsza jakakolwiek zmiana taga oznacza, że utwór został rozpoczęty.
        # Status przechodzi automatycznie z 🆕 Nowe na ⚠️ Do dokończenia.
        for song in selected:
            path = str(Path(song.path).resolve())
            if self.new_track_statuses.get(path) == "new":
                self.new_track_statuses[path] = "todo"

        self.save_new_track_statuses()
        self.save_new_track_session()

        # Aktualizujemy tylko tekst zaznaczonych pozycji w miejscu.
        # Nie odświeżamy całej QListWidget, bo powodowałoby to utratę
        # bieżącego wyboru i przeskok do kolejnego utworu podczas tagowania.
        if hasattr(self, "new_tracks_list"):
            for item in self.new_tracks_list.selectedItems():
                path = item.data(Qt.UserRole)
                if path:
                    song = self._find_song_for_playlist_path(path)
                    if song is not None:
                        title = getattr(song, "title", None) or Path(song.path).stem
                        artist = getattr(song, "artist", None) or ""
                        item.setText(
                            f"⚠️ Do dokończenia  {title}"
                            + (f" — {artist}" if artist else "")
                        )

        # Autosave: tagi są zapisywane natychmiast. Do 🏷️ Otagowane przechodzimy
        # dopiero po ręcznym zakończeniu pracy nad utworem.
        self.undo_stack.append(("new_tags", entry))
        self.redo_stack.clear()
        self.update_history_buttons()
        self.save_new_track_session()

        if selected:
            self.new_tracks_tag_panel.set_baseline(
                [read_grouping(song.path) for song in selected]
            )

    def finish_selected_new_tracks(self):
        selected = self.get_selected_new_tracks()
        if not selected:
            return

        for song in selected:
            path = str(Path(song.path).resolve())
            self.new_track_statuses[path] = "tagged"
            self.new_track_session.discard(path)

        self.save_new_track_statuses()
        self.save_new_track_session()
        self.refresh_new_tracks_tab()

    def update_new_tracks_actions(self):
        enabled = bool(self.new_tracks_list.selectedItems())
        self.new_tracks_finish_btn.setEnabled(enabled)

    def playlist_metadata_file(self, name):
        return self.settings_file_path().parent / name

    def load_playlist_folder_map(self):
        path = self.playlist_metadata_file("playlist_folders.json")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {"__folders__": []}
        except (OSError, ValueError, TypeError):
            return {"__folders__": []}

    def save_playlist_folder_map(self):
        try:
            self.playlist_metadata_file("playlist_folders.json").write_text(
                json.dumps(self.playlist_folder_map, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
        except OSError:
            pass

    def load_playlist_generated_map(self):
        path = self.playlist_metadata_file("playlist_generated.json")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError, TypeError):
            return {}

    def save_playlist_generated_map(self):
        try:
            self.playlist_metadata_file("playlist_generated.json").write_text(
                json.dumps(self.playlist_generated_map, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
        except OSError:
            pass

    # ==================== USTAWIENIA ====================
    def load_songs_from_source_folder(self):
        """Skanuje aktualnie wybrany folder źródłowy i zwraca jego utwory."""
        source = Path(self.app_settings["source_folder"])
        if not source.exists() or not source.is_dir():
            return []

        try:
            from src.scanner import scan_library
            from src.database_service import save_songs

            songs = scan_library(source)
            if songs:
                save_songs(songs)
            return songs
        except Exception as exc:
            # Jeśli skanowanie nie jest dostępne, zachowujemy możliwość
            # uruchomienia aplikacji na istniejącej bazie.
            print(f"⚠️ Nie udało się zeskanować folderu źródłowego: {exc}")
            try:
                return [
                    song for song in load_songs()
                    if self.path_is_inside(song.path, source)
                ]
            except Exception:
                return []

    @staticmethod
    def path_is_inside(path, folder):
        try:
            Path(path).resolve().relative_to(Path(folder).resolve())
            return True
        except ValueError:
            return False
        except OSError:
            return False

    def refresh_library_from_source_folder(self):
        """Przeładowuje Bibliotekę po zmianie folderu źródłowego."""
        old_path = self.current_song.path if self.current_song else None

        self.songs = self.load_songs_from_source_folder()
        self.song_by_path = {song.path: song for song in self.songs}
        self.filtered_songs = self.songs.copy()

        self.current_song = None
        self.current_grouping = ""

        if hasattr(self, "song_list"):
            self.update_filter_tag_options()
            self.apply_filters()

        if hasattr(self, "new_tracks_list"):
            self.refresh_new_tracks_tab()

        # Jeśli aktualnie wybrany utwór nadal istnieje w nowym źródle,
        # zachowaj go; w przeciwnym razie wyczyść panel szczegółów.
        if old_path and old_path in self.song_by_path:
            self.current_song = self.song_by_path[old_path]
        elif hasattr(self, "title"):
            self.title.clear()
            self.artist.clear()
            self.album.clear()

    def settings_file_path(self):
        base = os.environ.get("LOCALAPPDATA")
        if base:
            folder = Path(base) / "DJ Library Manager"
        else:
            folder = Path.home() / ".dj-library-manager"
        folder.mkdir(parents=True, exist_ok=True)
        return folder / "settings.json"

    def load_app_settings(self):
        music_folder = Path.home() / "Music"
        documents_folder = Path.home() / "Documents"
        default_output = documents_folder / "DJ Library Manager" / "Exports"
        default_output.mkdir(parents=True, exist_ok=True)

        self.app_settings = {
            "source_folder": str(music_folder),
            "output_folder": str(default_output),
            "spotify_cookie_file": "",
        }

        try:
            settings_path = self.settings_file_path()
            if settings_path.exists():
                with settings_path.open("r", encoding="utf-8") as f:
                    loaded = json.load(f)
                if isinstance(loaded, dict):
                    self.app_settings.update({
                        k: str(v)
                        for k, v in loaded.items()
                        if k in self.app_settings and v
                    })
        except (OSError, ValueError, TypeError):
            pass

        Path(self.app_settings["output_folder"]).mkdir(
            parents=True,
            exist_ok=True
        )
        self.save_app_settings()

    def save_app_settings(self):
        try:
            with self.settings_file_path().open("w", encoding="utf-8") as f:
                json.dump(
                    self.app_settings,
                    f,
                    ensure_ascii=False,
                    indent=2
                )
        except OSError:
            pass

    def build_settings_tab(self):
        layout = QVBoxLayout(self.settings_tab)

        title = QLabel("⚙ Ustawienia")
        title.setStyleSheet("font-size:18px;font-weight:bold;")
        layout.addWidget(title)

        group = QGroupBox("Foldery")
        form = QFormLayout(group)

        source_row = QHBoxLayout()
        self.source_folder_edit = QLineEdit(
            self.app_settings["source_folder"]
        )
        self.source_folder_edit.setReadOnly(True)
        source_btn = QPushButton("Wybierz…")
        source_btn.clicked.connect(
            lambda: self.choose_app_folder("source_folder")
        )
        source_row.addWidget(self.source_folder_edit, 1)
        source_row.addWidget(source_btn)
        form.addRow("📁 Folder źródłowy:", source_row)

        output_row = QHBoxLayout()
        self.output_folder_edit = QLineEdit(
            self.app_settings["output_folder"]
        )
        self.output_folder_edit.setReadOnly(True)
        output_btn = QPushButton("Wybierz…")
        output_btn.clicked.connect(
            lambda: self.choose_app_folder("output_folder")
        )
        output_row.addWidget(self.output_folder_edit, 1)
        output_row.addWidget(output_btn)
        form.addRow("📤 Folder eksportu:", output_row)

        layout.addWidget(group)

        info = QLabel(
            "Folder źródłowy to domyślne miejsce, z którego DJ Library Manager "
            "będzie docelowo pobierał/indeksował muzykę.\n\n"
            "Folder eksportu jest używany przez M3U8 oraz eksport do djay Pro. "
            "Plik djay będzie miał stałą nazwę „DJLM Library.xml”, więc kolejne "
            "eksporty aktualizują ten sam plik."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        reset_btn = QPushButton("↺ Przywróć foldery domyślne")
        reset_btn.clicked.connect(self.reset_app_folders)
        layout.addWidget(reset_btn)
        layout.addStretch()

    def choose_app_folder(self, setting_name):
        current = self.app_settings.get(setting_name, str(Path.home()))
        folder = QFileDialog.getExistingDirectory(
            self,
            "Wybierz folder",
            current
        )
        if not folder:
            return

        folder = str(Path(folder).resolve())
        self.app_settings[setting_name] = folder

        if setting_name == "source_folder":
            self.source_folder_edit.setText(folder)
            self.save_app_settings()

            # Zmiana ustawienia ma natychmiast zmienić zawartość Biblioteki.
            self.refresh_library_from_source_folder()
            self.tabs.setCurrentIndex(0)
        else:
            Path(folder).mkdir(parents=True, exist_ok=True)
            self.output_folder_edit.setText(folder)
            self.save_app_settings()

    def reset_app_folders(self):
        music_folder = Path.home() / "Music"
        output_folder = Path.home() / "Documents" / "DJ Library Manager" / "Exports"
        output_folder.mkdir(parents=True, exist_ok=True)

        self.app_settings["source_folder"] = str(music_folder)
        self.app_settings["output_folder"] = str(output_folder)
        self.source_folder_edit.setText(str(music_folder))
        self.output_folder_edit.setText(str(output_folder))
        self.save_app_settings()
        self.refresh_library_from_source_folder()
        self.tabs.setCurrentIndex(0)

    # ==================== PLAYLISTY ====================
    def build_playlist_tab(self):
        layout = QHBoxLayout(self.playlist_tab)

        left = QVBoxLayout()
        left.addWidget(QLabel("Moje playlisty"))

        folder_row = QHBoxLayout()
        folder_row.addWidget(QLabel("📁 Folder:"))
        self.playlist_folder_filter = QComboBox()
        self.playlist_folder_filter.currentIndexChanged.connect(
            self.refresh_playlist_list
        )
        folder_row.addWidget(self.playlist_folder_filter, 1)
        add_folder_btn = QPushButton("＋ Folder")
        add_folder_btn.clicked.connect(self.create_playlist_folder)
        folder_row.addWidget(add_folder_btn)
        remove_folder_btn = QPushButton("🗑")
        remove_folder_btn.setToolTip("Usuń folder (playlisty zostają)")
        remove_folder_btn.clicked.connect(self.delete_playlist_folder)
        folder_row.addWidget(remove_folder_btn)
        left.addLayout(folder_row)

        self.playlist_list = QTreeWidget()
        self.playlist_list.setHeaderHidden(True)
        self.playlist_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.playlist_list.setDragEnabled(False)
        self.playlist_list.setAnimated(True)
        self.playlist_list.itemClicked.connect(self.playlist_tree_item_clicked)
        left.addWidget(self.playlist_list)

        playlist_buttons = QHBoxLayout()
        new_btn = QPushButton("＋ Nowa")
        rename_btn = QPushButton("✏ Zmień nazwę")
        delete_btn = QPushButton("🗑 Usuń")
        new_btn.clicked.connect(self.create_playlist)
        rename_btn.clicked.connect(self.rename_playlist)
        delete_btn.clicked.connect(self.delete_playlist)
        playlist_buttons.addWidget(new_btn); playlist_buttons.addWidget(rename_btn); playlist_buttons.addWidget(delete_btn)
        sync_tags_btn = QPushButton("🏷️ Playlisty z tagów")
        sync_tags_btn.setToolTip(
            "Utwórz/odśwież playlisty na podstawie kategorii i tagów"
        )
        sync_tags_btn.clicked.connect(self.sync_tag_playlists)
        playlist_buttons.addWidget(sync_tags_btn)
        left.addLayout(playlist_buttons)
        layout.addLayout(left, 1)

        middle = QVBoxLayout()
        self.playlist_title = QLabel("Wybierz playlistę")
        self.playlist_title.setStyleSheet("font-size:18px;font-weight:bold;")
        middle.addWidget(self.playlist_title)
        self.playlist_tracks = PlaylistTrackListWidget()
        self.playlist_tracks.songs_dropped.connect(self.add_paths_to_current_playlist)
        self.playlist_tracks.order_changed.connect(self.playlist_order_changed)
        middle.addWidget(self.playlist_tracks)
        remove_track_btn = QPushButton("➖ Usuń zaznaczone z playlisty")
        remove_track_btn.clicked.connect(self.remove_selected_playlist_tracks)
        middle.addWidget(remove_track_btn)
        layout.addLayout(middle, 2)

        right = QVBoxLayout()
        right.addWidget(QLabel("Informacje"))
        self.playlist_info = QLabel("Wybierz playlistę")
        self.playlist_info.setWordWrap(True)
        right.addWidget(self.playlist_info)
        right.addStretch()
        export_btn = QPushButton("📤 Eksportuj playlistę M3U8")
        export_btn.clicked.connect(self.export_current_playlist)
        right.addWidget(export_btn)

        djay_btn = QPushButton("🚀 Eksportuj do djay Pro")
        djay_btn.clicked.connect(self.export_to_djay_pro)
        right.addWidget(djay_btn)

        layout.addLayout(right, 1)

    def refresh_playlist_list(self):
        if not hasattr(self, "playlist_list"):
            return

        current_folder = (
            self.playlist_folder_filter.currentData()
            if hasattr(self, "playlist_folder_filter")
            else ""
        )

        # Folder list includes manually-created folders and folders inferred
        # from tag categories.
        folders = set(self.playlist_folder_map.get("__folders__", []))
        for playlist in self.playlists:
            folder = self.playlist_folder_map.get(playlist["name"], "")
            if folder:
                folders.add(folder)

        self.playlist_folder_filter.blockSignals(True)
        self.playlist_folder_filter.clear()
        self.playlist_folder_filter.addItem("📁 Wszystkie foldery", "")
        for folder in sorted(folders, key=str.casefold):
            self.playlist_folder_filter.addItem(f"📁 {folder}", folder)
        idx = self.playlist_folder_filter.findData(current_folder)
        self.playlist_folder_filter.setCurrentIndex(idx if idx >= 0 else 0)
        self.playlist_folder_filter.blockSignals(False)

        self.playlist_list.blockSignals(True)
        self.playlist_list.clear()

        folder_items = {}

        for index, playlist in enumerate(self.playlists):
            folder = self.playlist_folder_map.get(playlist["name"], "")
            if current_folder and folder != current_folder:
                continue

            generated = self.playlist_generated_map.get(playlist["name"], False)
            if folder:
                parent = folder_items.get(folder)
                if parent is None:
                    parent = QTreeWidgetItem([f"📁 {folder}"])
                    parent.setData(0, Qt.ItemDataRole.UserRole, "folder")
                    self.playlist_list.addTopLevelItem(parent)
                    folder_items[folder] = parent
            else:
                parent = folder_items.get("__mine__")
                if parent is None:
                    parent = QTreeWidgetItem(["📁 Moje playlisty"])
                    parent.setData(0, Qt.ItemDataRole.UserRole, "folder")
                    self.playlist_list.addTopLevelItem(parent)
                    folder_items["__mine__"] = parent

            icon = "🏷️" if generated else "🎵"
            child = QTreeWidgetItem([f"{icon} {playlist['name']}"])
            child.setData(0, Qt.ItemDataRole.UserRole, "playlist")
            child.setData(0, Qt.ItemDataRole.UserRole + 1, index)
            parent.addChild(child)

            if index == self.current_playlist_index:
                self.playlist_list.setCurrentItem(child)
                parent.setExpanded(True)

        self.playlist_list.blockSignals(False)

        # Folder nodes are collapsed by default, except the selected one.
        for i in range(self.playlist_list.topLevelItemCount()):
            item = self.playlist_list.topLevelItem(i)
            if item.data(0, Qt.ItemDataRole.UserRole) == "folder":
                if item is not self.playlist_list.currentItem():
                    item.setExpanded(
                        any(
                            item.child(j) is self.playlist_list.currentItem()
                            for j in range(item.childCount())
                        )
                    )

        if not (0 <= self.current_playlist_index < len(self.playlists)):
            self.current_playlist_index = -1
            self.refresh_playlist_contents()

    def playlist_tree_item_clicked(self, item, column=0):
        if item is None:
            return
        if item.data(0, Qt.ItemDataRole.UserRole) != "playlist":
            item.setExpanded(not item.isExpanded())
            return

        index = item.data(0, Qt.ItemDataRole.UserRole + 1)
        if isinstance(index, int) and 0 <= index < len(self.playlists):
            self.current_playlist_index = index
            self.refresh_playlist_contents()

    def create_playlist_folder(self):
        name, ok = QInputDialog.getText(
            self, "Nowy folder playlist", "Nazwa folderu:"
        )
        name = name.strip()
        if not ok or not name:
            return
        if name in self.playlist_folder_map.values():
            QMessageBox.warning(self, "Foldery", "Taki folder już istnieje.")
            return
        # Folder is represented by a standalone entry in the metadata map.
        self.playlist_folder_map.setdefault("__folders__", [])
        if name not in self.playlist_folder_map["__folders__"]:
            self.playlist_folder_map["__folders__"].append(name)
        self.save_playlist_folder_map()
        self.refresh_playlist_list()

    def delete_playlist_folder(self):
        folder = (
            self.playlist_folder_filter.currentData()
            if hasattr(self, "playlist_folder_filter")
            else ""
        )
        if not folder:
            return
        answer = QMessageBox.question(
            self, "Usuń folder",
            f"Usunąć folder „{folder}”? Playlisty w nim pozostaną."
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        for name, value in list(self.playlist_folder_map.items()):
            if value == folder:
                self.playlist_folder_map[name] = ""
        if folder in self.playlist_folder_map.get("__folders__", []):
            self.playlist_folder_map["__folders__"].remove(folder)
        self.save_playlist_folder_map()
        self.refresh_playlist_list()

    def normalize_tag_folder(self, category):
        key = str(category).strip()
        low = key.casefold()
        if low in {"language", "languages", "lang", "język", "języki"}:
            return "lang"
        return re.sub(r"[^\w -]+", "", key, flags=re.UNICODE).strip().lower().replace(" ", "_")

    def sync_tag_playlists_silent(self):
        existing = {p["name"].casefold(): p for p in self.playlists}
        changed = False
        for song in self.songs:
            tags = parse_grouping(read_grouping(song.path))
            for category, values in tags.items():
                folder = self.normalize_tag_folder(category)
                for value in values:
                    name = str(value).strip()
                    if not name:
                        continue
                    playlist = existing.get(name.casefold())
                    if playlist is None:
                        playlist = {"name": name, "paths": []}
                        self.playlists.append(playlist)
                        existing[name.casefold()] = playlist
                        changed = True
                    if song.path not in playlist["paths"]:
                        playlist["paths"].append(song.path)
                        changed = True
                    self.playlist_folder_map[name] = folder
                    self.playlist_generated_map[name] = True
        if changed:
            save_playlists(self.playlists)
        self.save_playlist_folder_map()
        self.save_playlist_generated_map()
        if hasattr(self, "playlist_list"):
            self.refresh_playlist_list()

    def sync_tag_playlists(self):
        """Synchronize generated playlists from the library's tag grouping."""
        # Build the desired membership from the actual tag data on disk.
        desired = {}
        desired_folders = {}

        for song in self.songs:
            raw = read_grouping(song.path)
            try:
                tags = parse_grouping(raw)
            except Exception:
                tags = {}

            # Fallback to the cached grouping if parsing the file fails.
            if not tags:
                try:
                    tags = parse_grouping(getattr(song, "grouping", "") or "")
                except Exception:
                    tags = {}

            for category, values in tags.items():
                if not isinstance(values, (list, tuple, set)):
                    values = [values]

                folder = self.normalize_tag_folder(category)
                for value in values:
                    name = str(value).strip()
                    if not name:
                        continue

                    key = name.casefold()
                    desired.setdefault(key, {
                        "name": name,
                        "paths": [],
                        "folder": folder,
                        "category": str(category),
                    })
                    normalized_path = self._normalize_playlist_path(song.path)
                    if normalized_path not in desired[key]["paths"]:
                        desired[key]["paths"].append(normalized_path)

        for playlist in self.playlists:
            if self.playlist_generated_map.get(playlist.get("name", ""), False):
                playlist["paths"] = [
                    self._normalize_playlist_path(path)
                    for path in playlist.get("paths", [])
                    if path
                ]

        # Generated playlists are identified by playlist_generated_map.
        # User-created playlists are never deleted or overwritten.
        generated_names = {
            name.casefold()
            for name, generated in self.playlist_generated_map.items()
            if generated
        }

        by_name = {p["name"].casefold(): p for p in self.playlists}
        changed = False

        # Update/create generated playlists.
        for key, wanted in desired.items():
            playlist = by_name.get(key)
            if playlist is None:
                playlist = {
                    "name": wanted["name"],
                    "paths": list(wanted["paths"]),
                }
                self.playlists.append(playlist)
                by_name[key] = playlist
                changed = True
            else:
                if playlist.get("paths", []) != wanted["paths"] and (
                    key in generated_names
                ):
                    playlist["paths"] = list(wanted["paths"])
                    changed = True

            self.playlist_folder_map[wanted["name"]] = wanted["folder"]
            self.playlist_generated_map[wanted["name"]] = True

        # Remove old memberships from generated playlists when tags were removed.
        for playlist in self.playlists:
            key = playlist["name"].casefold()
            if key in generated_names and key not in desired:
                if playlist.get("paths"):
                    playlist["paths"] = []
                    changed = True

        # Ensure category folders exist in the folder list.
        self.playlist_folder_map.setdefault("__folders__", [])
        for wanted in desired.values():
            folder = wanted["folder"]
            if folder and folder not in self.playlist_folder_map["__folders__"]:
                self.playlist_folder_map["__folders__"].append(folder)

        if changed:
            save_playlists(self.playlists)

        self.save_playlist_folder_map()
        self.save_playlist_generated_map()
        self.refresh_playlist_list()

        QMessageBox.information(
            self,
            "Playlisty z tagów",
            f"Utworzono/zaktualizowano {len(desired)} playlist z tagów.\n\n"
            "Language → folder „lang”; pozostałe kategorie → własne foldery."
        )

    def refresh_playlist_contents(self):
        self.playlist_tracks.clear()
        if not (0 <= self.current_playlist_index < len(self.playlists)):
            self.playlist_title.setText("Wybierz playlistę")
            self.playlist_info.setText("Brak wybranej playlisty")
            return
        playlist = self.playlists[self.current_playlist_index]
        self.playlist_title.setText(playlist["name"])
        valid_paths = []
        for path in playlist.get("paths", []):
            song = self._find_song_for_playlist_path(path)
            if not song:
                continue
            item = self.playlist_tracks.item(self.playlist_tracks.count())
            item = __import__("PySide6.QtWidgets", fromlist=["QListWidgetItem"]).QListWidgetItem(
                f"{song.artist}\n{song.title}"
            )
            item.setData(Qt.ItemDataRole.UserRole, path)
            self.playlist_tracks.addItem(item)
            valid_paths.append(path)
        self.playlist_info.setText(f"Nazwa: {playlist['name']}\nUtworów: {len(valid_paths)}")

    def playlist_selected(self, index):
        # Kept for compatibility with older UI code.
        if isinstance(index, int) and index >= 0:
            visible = [
                i for i, p in enumerate(self.playlists)
                if not self.playlist_folder_filter.currentData()
                or self.playlist_folder_map.get(p["name"], "") == self.playlist_folder_filter.currentData()
            ]
            if index < len(visible):
                self.current_playlist_index = visible[index]
                self.refresh_playlist_contents()

    def snapshot_playlists(self):
        return [{"name": p["name"], "paths": list(p.get("paths", []))} for p in self.playlists]

    def record_playlist_change(self, before):
        after = self.snapshot_playlists()
        if before == after: return
        self.undo_stack.append(("playlists", before, after, self.current_playlist_index))
        self.redo_stack.clear()
        save_playlists(self.playlists)
        self.update_history_buttons()

    def create_playlist(self):
        name, ok = QInputDialog.getText(self, "Nowa playlista", "Nazwa playlisty:")
        name = name.strip()
        if not ok or not name: return
        if any(p["name"].lower() == name.lower() for p in self.playlists):
            QMessageBox.warning(self, "Playlisty", "Taka playlista już istnieje.")
            return
        before = self.snapshot_playlists()
        self.playlists.append({"name": name, "paths": []})
        selected_folder = (
            self.playlist_folder_filter.currentData()
            if hasattr(self, "playlist_folder_filter")
            else ""
        )
        if selected_folder:
            self.playlist_folder_map[name] = selected_folder
        self.current_playlist_index = len(self.playlists) - 1
        self.record_playlist_change(before)
        self.save_playlist_folder_map()
        self.refresh_playlist_list()

    def rename_playlist(self):
        if not (0 <= self.current_playlist_index < len(self.playlists)): return
        old = self.playlists[self.current_playlist_index]["name"]
        name, ok = QInputDialog.getText(self, "Zmień nazwę", "Nazwa playlisty:", text=old)
        name = name.strip()
        if not ok or not name or name == old: return
        if any(i != self.current_playlist_index and p["name"].lower() == name.lower() for i,p in enumerate(self.playlists)):
            QMessageBox.warning(self, "Playlisty", "Taka playlista już istnieje.")
            return
        before = self.snapshot_playlists()
        self.playlists[self.current_playlist_index]["name"] = name
        old_folder = self.playlist_folder_map.pop(old, "")
        if old_folder:
            self.playlist_folder_map[name] = old_folder
        if old in self.playlist_generated_map:
            self.playlist_generated_map[name] = self.playlist_generated_map.pop(old)
        self.record_playlist_change(before)
        self.save_playlist_folder_map()
        self.save_playlist_generated_map()
        self.refresh_playlist_list()

    def delete_playlist(self):
        if not (0 <= self.current_playlist_index < len(self.playlists)): return
        name = self.playlists[self.current_playlist_index]["name"]
        answer = QMessageBox.question(self, "Usuń playlistę", f"Usunąć playlistę „{name}”?")
        if answer != QMessageBox.StandardButton.Yes: return
        before = self.snapshot_playlists()
        del self.playlists[self.current_playlist_index]
        self.playlist_folder_map.pop(name, None)
        self.playlist_generated_map.pop(name, None)
        self.current_playlist_index = min(self.current_playlist_index, len(self.playlists)-1)
        self.record_playlist_change(before)
        self.save_playlist_folder_map()
        self.save_playlist_generated_map()
        self.refresh_playlist_list()

    def choose_playlists_for_selected(self):
        paths = [
            song.path
            for song in self.get_selected_songs()
        ]

        if not paths:
            QMessageBox.information(
                self,
                "Playlisty",
                "Najpierw zaznacz przynajmniej jeden utwór."
            )
            return

        if not self.playlists:
            QMessageBox.information(
                self,
                "Playlisty",
                "Najpierw utwórz playlistę."
            )
            self.tabs.setCurrentIndex(1)
            return

        dialog = QDialog(self)
        dialog.setWindowTitle(
            "Dodaj zaznaczone utwory do playlist"
        )
        dialog.resize(440, 430)

        layout = QVBoxLayout(dialog)
        layout.addWidget(
            QLabel(
                f"Wybrano utworów: {len(paths)}"
            )
        )
        layout.addWidget(
            QLabel(
                "Zaznacz jedną lub kilka playlist:"
            )
        )

        playlist_choices = QListWidget()
        playlist_choices.setSelectionMode(
            QAbstractItemView.NoSelection
        )

        for playlist in self.playlists:
            item = QListWidgetItem(
                playlist["name"]
            )
            item.setFlags(
                item.flags()
                | Qt.ItemFlag.ItemIsUserCheckable
                | Qt.ItemFlag.ItemIsEnabled
            )
            item.setCheckState(
                Qt.CheckState.Unchecked
            )
            playlist_choices.addItem(item)

        layout.addWidget(playlist_choices)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(
            QDialogButtonBox.StandardButton.Ok
        ).setText("Dodaj")
        buttons.button(
            QDialogButtonBox.StandardButton.Cancel
        ).setText("Anuluj")
        buttons.accepted.connect(
            dialog.accept
        )
        buttons.rejected.connect(
            dialog.reject
        )
        layout.addWidget(buttons)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        selected_rows = [
            row
            for row in range(
                playlist_choices.count()
            )
            if playlist_choices.item(row).checkState()
            == Qt.CheckState.Checked
        ]

        if not selected_rows:
            QMessageBox.information(
                self,
                "Playlisty",
                "Zaznacz przynajmniej jedną playlistę."
            )
            return

        before = self.snapshot_playlists()
        changed = False

        for row in selected_rows:
            playlist = self.playlists[row]

            for path in paths:
                if path not in playlist["paths"]:
                    playlist["paths"].append(path)
                    changed = True

        if changed:
            self.record_playlist_change(before)

        self.current_playlist_index = selected_rows[0]
        self.refresh_playlist_list()

    def add_paths_to_dropped_playlist(self, playlist_index, paths):
        if not (0 <= playlist_index < len(self.playlists)):
            return

        before = self.snapshot_playlists()
        playlist = self.playlists[playlist_index]

        changed = False
        for path in paths:
            if path not in playlist["paths"]:
                playlist["paths"].append(path)
                changed = True

        if not changed:
            return

        self.current_playlist_index = playlist_index
        self.record_playlist_change(before)
        self.refresh_playlist_list()
        self.playlist_list.setCurrentRow(playlist_index)

    def add_paths_to_current_playlist(self, paths):
        if not (0 <= self.current_playlist_index < len(self.playlists)):
            return

        before = self.snapshot_playlists()
        playlist = self.playlists[self.current_playlist_index]

        changed = False
        for path in paths:
            if path not in playlist["paths"]:
                playlist["paths"].append(path)
                changed = True

        if not changed:
            return

        self.record_playlist_change(before)
        self.refresh_playlist_contents()

    def remove_selected_playlist_tracks(self):
        if not (0 <= self.current_playlist_index < len(self.playlists)): return
        paths = [i.data(Qt.ItemDataRole.UserRole) for i in self.playlist_tracks.selectedItems()]
        if not paths: return
        before = self.snapshot_playlists()
        playlist = self.playlists[self.current_playlist_index]
        playlist["paths"] = [p for p in playlist["paths"] if p not in paths]
        self.record_playlist_change(before)
        self.refresh_playlist_contents()

    def playlist_order_changed(self, before_paths, after_paths):
        if self._history_busy or not (0 <= self.current_playlist_index < len(self.playlists)):
            return

        before = self.snapshot_playlists()
        self.playlists[self.current_playlist_index]["paths"] = list(after_paths)
        self.record_playlist_change(before)

    def export_current_playlist(self):
        if not (0 <= self.current_playlist_index < len(self.playlists)):
            return

        playlist = self.playlists[self.current_playlist_index]
        output_dir = Path(self.app_settings["output_folder"])
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / f"{playlist['name']}.m3u8"

        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write("#EXTM3U\n")
                for song_path in playlist.get("paths", []):
                    f.write(f"{song_path}\n")
            QMessageBox.information(
                self,
                "Eksport",
                f"Playlista została wyeksportowana.\n\n{path}"
            )
        except OSError as exc:
            QMessageBox.critical(
                self,
                "Eksport",
                f"Nie udało się zapisać playlisty:\n{exc}"
            )

    def export_to_djay_pro(self):
        """Eksportuje playlisty w pełniejszej strukturze iTunes XML dla djay Pro."""
        if not self.playlists:
            QMessageBox.information(self, "djay Pro", "Nie masz jeszcze żadnych playlist.")
            return

        output_dir = Path(self.app_settings["output_folder"])
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / "DJLM Library.xml"

        import hashlib
        import plistlib
        from datetime import datetime, timedelta, timezone
        from urllib.parse import quote

        def pid(value):
            return hashlib.md5(str(value).encode("utf-8")).hexdigest()[:16].upper()

        tracks = {}
        path_to_id = {}
        next_track_id = 1
        next_playlist_id = 1000

        for playlist in self.playlists:
            for song_path in playlist.get("paths", []):
                if not song_path or song_path in path_to_id:
                    continue

                track_id = next_track_id
                next_track_id += 1
                path_to_id[song_path] = track_id

                p = Path(song_path)
                song = self.song_by_path.get(song_path)

                title = p.stem
                artist = ""
                album = ""
                genre = ""
                year = None
                bpm = None

                if song is not None:
                    title = getattr(song, "title", None) or title
                    artist = getattr(song, "artist", None) or ""
                    album = getattr(song, "album", None) or ""
                    genre = getattr(song, "genre", None) or ""
                    year = getattr(song, "year", None)
                    bpm = getattr(song, "bpm", None)

                try:
                    size = p.stat().st_size
                except OSError:
                    size = 0

                track = {
                    "Track ID": track_id,
                    "Size": size,
                    "Persistent ID": pid(song_path),
                    "Track Type": "File",
                    "File Folder Count": -1,
                    "Library Folder Count": -1,
                    "Name": title,
                    "Artist": artist,
                    "Album Artist": artist,
                    "Album": album,
                    "Genre": genre,
                    "Kind": "plik audio",
                    "Location": (
                        "file://localhost/"
                        + quote(str(p).replace("\\", "/"), safe="/:")
                    ),
                }

                if year not in (None, ""):
                    try:
                        track["Year"] = int(year)
                    except (TypeError, ValueError):
                        pass

                if bpm not in (None, ""):
                    try:
                        track["BPM"] = int(float(bpm))
                    except (TypeError, ValueError):
                        pass

                tracks[str(track_id)] = track

        playlists_xml = []
        for playlist in self.playlists:
            items = [
                {"Track ID": path_to_id[p]}
                for p in playlist.get("paths", [])
                if p in path_to_id
            ]
            playlists_xml.append({
                "Playlist ID": next_playlist_id,
                "Playlist Persistent ID": pid("playlist:" + playlist["name"]),
                "All Items": True,
                "Visible": True,
                "Name": playlist["name"],
                "Playlist Items": items,
            })
            next_playlist_id += 1

        plist = {
            "Major Version": 1,
            "Minor Version": 1,
            "Application Version": "12.13.10.3",
            "Date": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "Features": 5,
            "Show Content Ratings": True,
            "Library Persistent ID": pid("DJLM Library"),
            "Tracks": tracks,
            "Playlists": playlists_xml,
            "Music Folder": "file://localhost/",
        }

        try:
            with open(path, "wb") as file:
                plistlib.dump(plist, file, fmt=plistlib.FMT_XML, sort_keys=False)
        except OSError as exc:
            QMessageBox.critical(self, "djay Pro", f"Nie udało się zapisać biblioteki XML:\n{exc}")
            return

        QMessageBox.information(
            self,
            "Eksport do djay Pro zakończony",
            f"Zaktualizowano bibliotekę djay Pro.\n\n"
            f"Playlisty: {len(playlists_xml)}\n"
            f"Utwory: {len(tracks)}\n\n"
            f"Plik: {path}\n\n"
            "W djay Pro wskaż ten plik tylko przy pierwszej konfiguracji. "
            "Kolejne eksporty aktualizują ten sam plik."
        )

    # ==================== FILTRY ====================
    def category_filter_changed(self):
        self.update_filter_tag_options(); self.apply_filters()

    def update_filter_tag_options(self):
        current_tag = self.tag_filter.currentData()
        self.tag_filter.blockSignals(True); self.tag_filter.clear(); self.tag_filter.addItem("Wszystkie tagi", "")
        category = self.category_filter.currentData()
        if category:
            for value in self.available_tags.get(category, []): self.tag_filter.addItem(value, value)
        self.tag_filter.blockSignals(False)
        index = self.tag_filter.findData(current_tag); self.tag_filter.setCurrentIndex(index if index >= 0 else 0)

    def apply_filters(self):
        search_text = self.search.text().strip().lower(); category = self.category_filter.currentData(); tag = self.tag_filter.currentData()
        self.filtered_songs = []; self.song_list.blockSignals(True); self.song_list.clear()
        for song in self.songs:
            if search_text and search_text not in song.title.lower() and search_text not in song.artist.lower(): continue
            if category and tag:
                tags = parse_grouping(read_grouping(song.path))
                if tag not in tags.get(category, []): continue
            self.filtered_songs.append(song)
            from PySide6.QtWidgets import QListWidgetItem
            item = QListWidgetItem(f"{song.artist}\n{song.title}")
            item.setData(Qt.ItemDataRole.UserRole, song.path)
            self.song_list.addItem(item)
        self.song_list.blockSignals(False)
        self.counter.setText(f"Znaleziono: {len(self.filtered_songs)} utworów")
        self.update_selected_counter()
        if self.filtered_songs: self.song_list.setCurrentRow(0)
        else:
            self.current_song = None; self.current_grouping = ""; self.title.clear(); self.artist.clear(); self.album.clear(); self.tag_panel.load_song("")

    def clear_filters(self):
        self.search.blockSignals(True); self.search.clear(); self.search.blockSignals(False)
        self.category_filter.blockSignals(True); self.category_filter.setCurrentIndex(0); self.category_filter.blockSignals(False)
        self.update_filter_tag_options(); self.apply_filters()

    # ==================== WYBÓR / TAGI ====================
    def update_selected_counter(self):
        count = len(self.song_list.selectedItems()); self.selected_counter.setText("Wybrano: 1 utwór" if count == 1 else f"Wybrano: {count} utworów")

    def get_selected_songs(self):
        songs=[]
        for item in self.song_list.selectedItems():
            row=self.song_list.row(item)
            if 0 <= row < len(self.filtered_songs): songs.append(self.filtered_songs[row])
        return songs

    def selection_changed(self):
        self.update_selected_counter(); selected=self.get_selected_songs()
        if len(selected)>1: self.tag_panel.load_songs([read_grouping(s.path) for s in selected])

    def song_selected(self,index):
        if index<0 or index>=len(self.filtered_songs): return
        self.current_song=self.filtered_songs[index]; self.title.setText(self.current_song.title); self.artist.setText(self.current_song.artist); self.album.setText(self.current_song.album)
        self.current_grouping=read_grouping(self.current_song.path); selected=self.get_selected_songs()
        if len(selected)>1: self.tag_panel.load_songs([read_grouping(s.path) for s in selected])
        else: self.tag_panel.load_song(self.current_grouping)

    def tags_changed(self):
        if self._history_busy: return
        selected=self.get_selected_songs(); changes=self.tag_panel.get_changes()
        if not selected or not changes: return
        entry=[]
        for song in selected:
            before=read_grouping(song.path); tags=parse_grouping(before)
            for category,value,should_have in changes:
                values=tags.setdefault(category,[])
                if should_have and value not in values: values.append(value)
                elif not should_have and value in values: values.remove(value)
            after=save_grouping(song.path,tags); song.grouping=after; update_song(song); entry.append((song,before,after))
        self.undo_stack.append(("tags",entry)); self.redo_stack.clear(); self.update_history_buttons()

        self.current_grouping=read_grouping(self.current_song.path); self.tag_panel.set_baseline([read_grouping(s.path) for s in selected])
        self.sync_tag_playlists_silent()

    # ==================== UNDO / REDO ====================
    def restore_playlist_snapshot(self, snapshot):
        self.playlists=[{"name":p["name"],"paths":list(p.get("paths",[]))} for p in snapshot]
        save_playlists(self.playlists)

    def apply_history(self, history, undoing):
        kind=history[0]
        if kind=="tags":
            for song,before,after in history[1]:
                grouping=before if undoing else after; tags=parse_grouping(grouping); saved=save_grouping(song.path,tags); song.grouping=saved; update_song(song)
        elif kind=="playlists":
            snapshot=history[1] if undoing else history[2]
            self.restore_playlist_snapshot(snapshot)
            self.current_playlist_index=min(history[3],len(self.playlists)-1)

    def refresh_after_history(self):
        self._history_busy=True
        try:
            if self.current_song is not None:
                self.current_grouping=read_grouping(self.current_song.path)
                selected=self.get_selected_songs()
                if len(selected)>1: self.tag_panel.load_songs([read_grouping(s.path) for s in selected])
                else: self.tag_panel.load_song(self.current_grouping)
            self.refresh_playlist_list()
        finally: self._history_busy=False
        self.update_history_buttons()

    def undo(self):
        if not self.undo_stack:return
        history=self.undo_stack.pop(); self._history_busy=True
        try:self.apply_history(history,True); self.redo_stack.append(history)
        finally:self._history_busy=False
        self.refresh_after_history()

    def redo(self):
        if not self.redo_stack:return
        history=self.redo_stack.pop(); self._history_busy=True
        try:self.apply_history(history,False); self.undo_stack.append(history)
        finally:self._history_busy=False
        self.refresh_after_history()

    def update_history_buttons(self):
        self.undo_button.setEnabled(bool(self.undo_stack)); self.redo_button.setEnabled(bool(self.redo_stack))


def run_gui():
    app=QApplication([]); window=MainWindow(); window.show(); app.exec()
