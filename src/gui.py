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
    QCheckBox,
)
from PySide6.QtGui import QKeySequence, QShortcut, QDesktopServices
from PySide6.QtCore import Qt, QProcess, QProcessEnvironment, QTimer, QUrl
from PySide6.QtMultimedia import QMediaPlayer

from src.database_service import load_songs, update_song
from src.tags import read_grouping, save_grouping, parse_grouping
from src.config import get_available_tags
from src.services.playlist_storage_service import PlaylistStorageService
from src.widgets.tag_panel import TagPanel
from src.widgets.playlist_widgets import SongListWidget, PlaylistTrackListWidget, PlaylistListWidget, DragTabBar
from src.services.settings_service import SettingsService
from src.widgets.settings_widget import SettingsWidget
from src.widgets.error_book_widget import ErrorBookWidget
from src.widgets.playlists_widget import PlaylistsWidget
from src.widgets.library_widget import LibraryWidget
from src.widgets.spotify_widget import SpotifyWidget
from src.widgets.new_tracks_widget import NewTracksWidget
from src.services.new_tracks_service import NewTracksService
from src.services.playlist_metadata_service import PlaylistMetadataService
from src.services.playlist_service import PlaylistService
from src.services.tag_service import TagService
from src.services.library_export_service import LibraryExportService
from src.services.library_filter_service import LibraryFilterService
from src.services.history_service import HistoryService
from src.services.playlist_folder_service import PlaylistFolderService
from src.services.library_service import LibraryService
from src.services.error_book_service import ErrorBookService
from src.services.spotify_metadata_service import SpotifyMetadataService
from src.services.spotify_queue_service import SpotifyQueueService
from src.services.audio_player_service import AudioPlayerService
from src.services.cover_art_service import CoverArtService
from src.widgets.player_widget import PlayerWidget


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DJ Library Manager")
        self.resize(1400, 800)

        # Ustawienia muszą być wczytane przed biblioteką — folder źródłowy
        # decyduje o tym, jakie utwory trafiają do zakładki „Biblioteka”.
        self.settings_service = SettingsService()
        self.new_tracks_service = NewTracksService(self.settings_service)
        self.playlist_metadata_service = PlaylistMetadataService(self.settings_service)
        self.playlist_service = PlaylistService()
        self.playlist_storage_service = PlaylistStorageService()
        self.tag_service = TagService()
        self.library_export_service = LibraryExportService()
        self.library_filter_service = LibraryFilterService()
        self.history_service = HistoryService(self.tag_service, self.playlist_storage_service)
        self.playlist_folder_service = PlaylistFolderService()
        self.library_service = LibraryService()
        self.error_book_service = ErrorBookService(self.settings_service)
        self.spotify_metadata_service = SpotifyMetadataService()
        self.spotify_queue_service = SpotifyQueueService()
        self.audio_player_service = AudioPlayerService(self)
        self.cover_art_service = CoverArtService()
        self.audio_player_service.player.mediaStatusChanged.connect(
            self._player_media_status_changed
        )
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
        self.playlists = self.playlist_storage_service.load()
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

        self.player_widget = PlayerWidget(
            self.audio_player_service,
            self.cover_art_service,
            self,
        )
        self.player_widget.set_skip_seconds(
            self.app_settings.get("player_skip_seconds", 5)
        )
        main_layout.addWidget(self.player_widget)

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

        self.player_space_shortcut = QShortcut(
            QKeySequence(Qt.Key.Key_Space),
            self,
        )
        self.player_space_shortcut.setContext(
            Qt.ShortcutContext.ApplicationShortcut
        )
        self.player_space_shortcut.activated.connect(
            self.audio_player_service.toggle
        )

        self.player_left_shortcut = QShortcut(
            QKeySequence(Qt.Key.Key_Left),
            self,
        )
        self.player_left_shortcut.setContext(
            Qt.ShortcutContext.ApplicationShortcut
        )
        self.player_left_shortcut.activated.connect(
            self.player_widget.skip_backward
        )

        self.player_right_shortcut = QShortcut(
            QKeySequence(Qt.Key.Key_Right),
            self,
        )
        self.player_right_shortcut.setContext(
            Qt.ShortcutContext.ApplicationShortcut
        )
        self.player_right_shortcut.activated.connect(
            self.player_widget.skip_forward
        )

        self.player_exact_backward_shortcut = QShortcut(
            QKeySequence(","), self
        )
        self.player_exact_backward_shortcut.setContext(
            Qt.ShortcutContext.ApplicationShortcut
        )
        self.player_exact_backward_shortcut.activated.connect(
            lambda: self._exact_seek(-1)
        )
        self.player_exact_forward_shortcut = QShortcut(
            QKeySequence("."), self
        )
        self.player_exact_forward_shortcut.setContext(
            Qt.ShortcutContext.ApplicationShortcut
        )
        self.player_exact_forward_shortcut.activated.connect(
            lambda: self._exact_seek(1)
        )

        # Keyboard navigation between tabs. Ctrl+Tab remains the native
        # QTabWidget shortcut; these two mirror Chrome's Ctrl+PgUp/PgDn.
        self.tab_previous_shortcut = QShortcut(
            QKeySequence("Ctrl+PgUp"), self
        )
        self.tab_previous_shortcut.setContext(
            Qt.ShortcutContext.ApplicationShortcut
        )
        self.tab_previous_shortcut.activated.connect(
            lambda: self._cycle_tab(-1)
        )

        self.tab_next_shortcut = QShortcut(
            QKeySequence("Ctrl+PgDown"), self
        )
        self.tab_next_shortcut.setContext(
            Qt.ShortcutContext.ApplicationShortcut
        )
        self.tab_next_shortcut.activated.connect(
            lambda: self._cycle_tab(1)
        )

        # Up/down always navigate tracks, even when the tag panel currently
        # has focus. Left/right remain dedicated to player seek.
        self.track_previous_shortcut = QShortcut(
            QKeySequence(Qt.Key.Key_Up), self
        )
        self.track_previous_shortcut.setContext(
            Qt.ShortcutContext.ApplicationShortcut
        )
        self.track_previous_shortcut.activated.connect(
            lambda: self._navigate_track_selection(-1)
        )

        self.track_next_shortcut = QShortcut(
            QKeySequence(Qt.Key.Key_Down), self
        )
        self.track_next_shortcut.setContext(
            Qt.ShortcutContext.ApplicationShortcut
        )
        self.track_next_shortcut.activated.connect(
            lambda: self._navigate_track_selection(1)
        )

        self._setup_tag_shortcuts()

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

    def _exact_seek(self, direction):
        seconds = int(
            self.app_settings.get("player_exact_seek_seconds", 5)
        )
        current = int(self.audio_player_service.position())
        duration = int(self.audio_player_service.duration())
        target = max(0, current + direction * seconds * 1000)
        if duration > 0:
            target = min(target, duration)
        self.audio_player_service.seek(target)

    def _cycle_tab(self, delta):
        count = self.tabs.count()
        if count <= 1:
            return
        current = self.tabs.currentIndex()
        self.tabs.setCurrentIndex((current + delta) % count)

    def _current_track_list_for_keyboard(self):
        index = self.tabs.currentIndex()

        if index == self.tabs.indexOf(self.library_tab):
            return self.song_list

        if index == self.tabs.indexOf(self.new_tracks_tab):
            return self.new_tracks_list

        if index == self.tabs.indexOf(self.playlist_tab):
            return self.playlist_tracks

        return None

    def _navigate_track_selection(self, delta):
        track_list = self._current_track_list_for_keyboard()
        if track_list is None or track_list.count() == 0:
            return

        current = track_list.currentRow()
        if current < 0:
            target = 0 if delta > 0 else track_list.count() - 1
        else:
            target = max(
                0,
                min(track_list.count() - 1, current + delta),
            )

        track_list.setCurrentRow(target)

        if not bool(
            self.app_settings.get(
                "arrow_navigation_plays_track",
                False,
            )
        ):
            return

        item = track_list.item(target)
        if item is None:
            return

        if track_list is self.song_list:
            self.play_current_song()
        elif track_list is self.new_tracks_list:
            self.play_new_track(item)
        elif track_list is self.playlist_tracks:
            self.play_playlist_track(item)

    def _focus_tag_category_shortcut(self, category):
        """Activate the named tag category in the current tagging panel."""
        if self.tabs.currentIndex() == self.tabs.indexOf(
            self.new_tracks_tab
        ):
            self.new_tracks_tag_panel.focus_category(category)
        elif self.tabs.currentIndex() == self.tabs.indexOf(
            self.library_tab
        ):
            self.tag_panel.focus_category(category)

    def _clear_tag_category_shortcuts(self):
        for shortcut in getattr(
            self, "_tag_category_shortcuts", []
        ):
            shortcut.setEnabled(False)
            shortcut.deleteLater()
        self._tag_category_shortcuts = []

    def _setup_tag_shortcuts(self):
        self._clear_tag_category_shortcuts()

        # Category shortcuts are mapped by CATEGORY NAME, never by the
        # visual masonry column position. This prevents Ctrl+1 from
        # accidentally selecting a category that happens to be elsewhere.
        saved = self.app_settings.get(
            "tag_category_shortcuts", {}
        )
        if not isinstance(saved, dict):
            saved = {}

        categories = list(self.available_tags.keys())
        defaults = {
            category: f"Ctrl+{index + 1}"
            for index, category in enumerate(categories[:9])
        }

        for category in categories[:9]:
            sequence = str(
                saved.get(
                    category,
                    defaults.get(category, ""),
                )
            ).strip()
            if not sequence:
                continue

            category_shortcut = QShortcut(
                QKeySequence(sequence),
                self,
            )
            category_shortcut.setContext(
                Qt.ShortcutContext.ApplicationShortcut
            )
            category_shortcut.activated.connect(
                lambda name=category:
                self._focus_tag_category_shortcut(name)
            )
            self._tag_category_shortcuts.append(
                category_shortcut
            )

        # Collect digits into one number: 10/57/123 are real tag numbers.
        self._init_tag_number_input()

        for digit in range(10):
            shortcut = QShortcut(QKeySequence(str(digit)), self)
            shortcut.setContext(
                Qt.ShortcutContext.ApplicationShortcut
            )
            shortcut.activated.connect(
                lambda n=digit: self._append_tag_number_digit(n)
            )



    def _tag_category_shortcuts_changed(self, shortcuts):
        self.app_settings["tag_category_shortcuts"] = dict(
            shortcuts or {}
        )
        self.save_app_settings()
        self._setup_tag_shortcuts()

    def _init_tag_number_input(self):
        # Digits use a short debounce so:
        #   1        -> tag 1
        #   1 then 0 -> tag 10
        # No Enter is required.
        self._tag_number_buffer = ""
        self._tag_number_timer = QTimer(self)
        self._tag_number_timer.setSingleShot(True)
        self._tag_number_timer.setInterval(120)
        self._tag_number_timer.timeout.connect(
            self._commit_tag_number_buffer
        )

    def _tag_panel_is_active(self):
        current = self.tabs.currentIndex()
        return current in (
            self.tabs.indexOf(self.library_tab),
            self.tabs.indexOf(self.new_tracks_tab),
        )

    def _append_tag_number_digit(self, digit):
        if not self._tag_panel_is_active():
            return

        self._tag_number_buffer += str(digit)

        # A rapid second digit extends the number (e.g. 1 -> 10).
        # After the user stops typing digits for 450 ms, the whole
        # number is committed automatically.
        self._tag_number_timer.start()

    def _commit_tag_number_buffer(self):
        if not self._tag_number_buffer:
            return

        text = self._tag_number_buffer
        self._tag_number_buffer = ""

        try:
            number = int(text)
        except ValueError:
            return

        current = self.tabs.currentIndex()
        if current == self.tabs.indexOf(self.library_tab):
            self.tag_panel.toggle_tag_by_number(number)
        elif current == self.tabs.indexOf(self.new_tracks_tab):
            self.new_tracks_tag_panel.toggle_tag_by_number(number)


    def _normalize_playlist_path(self, path):
        return self.playlist_service.normalize_path(path)

    def _find_song_for_playlist_path(self, path):
        return self.playlist_service.find_song(
            path,
            self.songs,
            self.song_by_path,
        )

    def dragged_over_tab(self, index):
        # Zakładka Playlisty ma indeks 1.
        # Przełączamy ją podczas trzymania przeciąganego utworu.
        if index == 1 and self.tabs.currentIndex() != 1:
            self.tabs.setCurrentIndex(1)

    # ==================== BIBLIOTEKA ====================
    def build_library_tab(self):
        self.library_widget = LibraryWidget(
            available_tags=self.available_tags,
            cover_art_service=self.cover_art_service,
            parent=self.library_tab,
        )

        self.search = self.library_widget.search
        self.category_filter = self.library_widget.category_filter
        self.tag_filter = self.library_widget.tag_filter
        self.clear_filters_button = self.library_widget.clear_filters_button
        self.counter = self.library_widget.counter
        self.selected_counter = self.library_widget.selected_counter
        self.song_list = self.library_widget.song_list
        self.library_view_mode_button = self.library_widget.view_mode_button
        self.library_view_mode_button.set_mode(
            self.app_settings.get("library_view_mode", "medium")
        )
        self.song_list.set_view_mode(
            self.app_settings.get("library_view_mode", "medium")
        )
        self.library_view_mode_button.mode_changed.connect(
            lambda mode: self._save_view_mode("library_view_mode", mode)
        )
        self.add_to_playlist_button = self.library_widget.add_to_playlist_button
        self.title = self.library_widget.title
        self.artist = self.library_widget.artist
        self.album = self.library_widget.album
        self.library_cover = self.library_widget.cover_label
        self.tag_panel = self.library_widget.tag_panel

        self.search.textChanged.connect(self.apply_filters)
        self.category_filter.currentIndexChanged.connect(
            self.category_filter_changed
        )
        self.tag_filter.currentIndexChanged.connect(self.apply_filters)
        self.clear_filters_button.clicked.connect(self.clear_filters)
        self.song_list.currentRowChanged.connect(self.song_selected)
        self.song_list.itemDoubleClicked.connect(
            lambda _item: self.play_current_song()
        )
        self.song_list.itemSelectionChanged.connect(self.selection_changed)
        self.add_to_playlist_button.clicked.connect(
            self.choose_playlists_for_selected
        )
        self.tag_panel.tags_changed.connect(self.tags_changed)

        layout = QHBoxLayout(self.library_tab)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.library_widget)

    # ==================== SPOTIFY ====================
    def build_spotify_tab(self):
        self.spotify_widget = SpotifyWidget(self.spotify_tab)

        self.spotify_url_edit = self.spotify_widget.url_edit
        self.spotify_download_folder = self.spotify_widget.download_folder
        self.spotify_download_folder.setText(
            self.app_settings.get("source_folder", "")
        )
        self.spotify_cookie_file = self.spotify_widget.cookie_file
        # Restore the persisted cookies path into the actual Spotify widget.
        # Previously it was saved to app_settings but never loaded into this
        # line edit after SpotifyWidget was created.
        self.spotify_cookie_file.setText(
            self.app_settings.get("spotify_cookie_file", "")
        )
        self.spotify_cookie_browse_btn = self.spotify_widget.cookie_browse_btn
        self.spotify_download_btn = self.spotify_widget.download_btn
        self.spotify_add_queue_btn = self.spotify_widget.add_queue_btn
        self.spotify_clear_btn = self.spotify_widget.clear_btn
        self.spotify_pause_btn = self.spotify_widget.pause_btn
        self.spotify_resume_btn = self.spotify_widget.resume_btn
        self.spotify_cancel_btn = self.spotify_widget.cancel_btn
        self.spotify_progress = self.spotify_widget.progress
        self.spotify_progress_bar = self.spotify_widget.progress_bar
        self.spotify_progress_count = self.spotify_widget.progress_count
        self.spotify_speed_label = self.spotify_widget.speed_label
        self.spotify_eta_label = self.spotify_widget.eta_label
        self.spotify_queue_btn = self.spotify_widget.queue_btn
        self.spotify_queue_tree = self.spotify_widget.queue_tree
        self.spotify_remove_queue_btn = self.spotify_widget.remove_queue_btn
        self.spotify_log = self.spotify_widget.log
        self.spotify_errors_btn = self.spotify_widget.errors_btn

        self.spotify_cookie_file.editingFinished.connect(
            self.save_spotify_cookie_path
        )
        self.spotify_cookie_browse_btn.clicked.connect(
            self.choose_spotify_cookie_file
        )
        self.spotify_download_btn.clicked.connect(self.start_spotify_download)
        self.spotify_add_queue_btn.clicked.connect(self.add_spotify_to_queue)
        self.spotify_clear_btn.clicked.connect(self.spotify_url_edit.clear)
        self.spotify_pause_btn.clicked.connect(self.pause_spotify_download)
        self.spotify_resume_btn.clicked.connect(self.resume_spotify_download)
        self.spotify_cancel_btn.clicked.connect(
            self.confirm_cancel_spotify_download
        )
        self.spotify_queue_btn.clicked.connect(self.toggle_spotify_queue)
        self.spotify_remove_queue_btn.clicked.connect(
            self.remove_selected_spotify_queue_item
        )
        self.spotify_queue_tree.itemSelectionChanged.connect(
            self.update_spotify_queue_actions
        )
        self.spotify_queue_tree.itemClicked.connect(
            self.spotify_queue_item_clicked
        )
        self.spotify_errors_btn.clicked.connect(
            lambda: self.tabs.setCurrentWidget(self.error_book_tab)
        )

        layout = QVBoxLayout(self.spotify_tab)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.spotify_widget)

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
        self.spotify_process.setProcessChannelMode(QProcess.MergedChannels)
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

        item = {
            "url": url,
            "name": self._queue_label_from_url(url),
            "count": None,
            "tracks": [],
            "done": 0,
            "status": "queued",
        }
        if not self.spotify_queue_service.add(self.spotify_queue, item):
            self.spotify_progress.setText("ℹ️ Ta pozycja jest już w kolejce.")
            return
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
        return self.spotify_metadata_service.extract_tracks(payload)

    def _extract_collection_name(self, payload):
        return self.spotify_metadata_service.extract_collection_name(payload)

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

        self.playlist_storage_service.save(self.playlists)
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

        removed = self.spotify_queue_service.remove(
            self.spotify_queue,
            index,
        )
        if removed is None:
            return
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
        (
            current_remaining,
            future_total,
            future_unknown,
        ) = self.spotify_queue_service.totals(
            self.spotify_queue,
            self.spotify_active_queue_index,
        )

        for index, item in enumerate(self.spotify_queue):
            count = item.get("count")
            remaining = max(0, (count or 0) - item.get("done", 0))

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
        return self.error_book_service.errors_file()

    def load_spotify_errors(self):
        return self.error_book_service.load()

    def save_spotify_errors(self):
        self.error_book_service.save(self.spotify_errors)

    def build_error_book_tab(self):
        self.error_book_widget = ErrorBookWidget(self.error_book_tab)
        self.error_book_widget.open_requested.connect(
            self.open_selected_error_link
        )
        self.error_book_widget.copy_requested.connect(
            self.copy_selected_error_link
        )
        self.error_book_widget.remove_requested.connect(
            self.remove_selected_error
        )

        layout = QVBoxLayout(self.error_book_tab)
        layout.addWidget(self.error_book_widget)

        # Temporary compatibility alias during the refactor.
        self.error_book_list = self.error_book_widget.list_widget
        self.refresh_error_book()

    def refresh_error_book(self):
        if not hasattr(self, "error_book_widget"):
            return
        self.error_book_widget.set_errors(self.spotify_errors)
        if hasattr(self, "spotify_errors_btn"):
            self.spotify_errors_btn.setText(
                f"📕 Książka błędów ({len(self.spotify_errors)})"
            )

    def selected_error(self):
        if not hasattr(self, "error_book_widget"):
            return None
        return self.error_book_widget.selected_error()

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
        active_item = (
            self.spotify_queue[self.spotify_active_queue_index]
            if 0 <= self.spotify_active_queue_index < len(self.spotify_queue)
            else None
        )

        entry, next_error_count = self.error_book_service.build_error_entry(
            error_text=error_text,
            raw_line=raw_line,
            current_track=self.spotify_current_track,
            active_item=active_item,
            active_error_count=self.spotify_active_error_count,
        )

        self.spotify_errors.append(entry)
        self.spotify_active_error_count = next_error_count
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
        return self.new_tracks_service.status_path()

    def new_track_session_path(self):
        return self.new_tracks_service.session_path()

    def load_new_track_statuses(self):
        self.new_track_statuses = self.new_tracks_service.load_statuses()

    def save_new_track_statuses(self):
        self.new_tracks_service.save_statuses(self.new_track_statuses)

    def load_new_track_session(self):
        self.new_track_session = self.new_tracks_service.load_session()

    def save_new_track_session(self):
        self.new_tracks_service.save_session(self.new_track_session)

    def ensure_new_track_session(self, persist=True):
        if not hasattr(self, "new_track_statuses"):
            self.load_new_track_statuses()
        if not hasattr(self, "new_track_session"):
            self.load_new_track_session()

        (
            self.new_track_statuses,
            self.new_track_session,
        ) = self.new_tracks_service.ensure_session(
            self.songs,
            self.new_track_statuses,
            self.new_track_session,
            persist=persist,
        )

    def new_track_status_label(self, status):
        return {
            "new": "🆕 Nowe",
            "tagged": "🏷️ Otagowane",
            "todo": "⚠️ Do uzupełnienia",
            "ready": "✅ Gotowe",
        }.get(status, "🆕 Nowe")

    def build_new_tracks_tab(self):
        self.new_tracks_widget = NewTracksWidget(
            available_tags=self.available_tags,
            parent=self.new_tracks_tab,
        )

        self.new_tracks_count = self.new_tracks_widget.count_label
        self.new_tracks_status = self.new_tracks_widget.status_filter
        self.new_tracks_search = self.new_tracks_widget.search
        self.new_tracks_list = self.new_tracks_widget.song_list
        self.new_tracks_view_mode_button = self.new_tracks_widget.view_mode_button
        self.new_tracks_view_mode_button.set_mode(
            self.app_settings.get("new_tracks_view_mode", "medium")
        )
        self.new_tracks_list.set_view_mode(
            self.app_settings.get("new_tracks_view_mode", "medium")
        )
        self.new_tracks_list.set_cover_art_service(self.cover_art_service)
        self.new_tracks_view_mode_button.mode_changed.connect(
            lambda mode: self._save_view_mode("new_tracks_view_mode", mode)
        )
        self.new_tracks_tag_panel = self.new_tracks_widget.tag_panel
        self.new_tracks_finish_btn = self.new_tracks_widget.finish_btn
        self.new_tracks_refresh_btn = self.new_tracks_widget.refresh_btn

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
        self.new_tracks_list.itemDoubleClicked.connect(
            self.play_new_track
        )
        self.new_tracks_list.itemSelectionChanged.connect(
            self.update_new_tracks_actions
        )
        self.new_tracks_finish_btn.clicked.connect(
            self.finish_selected_new_tracks
        )
        self.new_tracks_tag_panel.tags_changed.connect(
            self.new_tracks_tags_changed
        )

        layout = QVBoxLayout(self.new_tracks_tab)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.new_tracks_widget)

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

        # Refreshing the visible filter must not write two JSON files.
        # Persistence is handled when the underlying data actually changes.
        self.ensure_new_track_session(persist=False)
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
            self.new_tracks_list._set_item_cover(item, path)

        active_count = len(self.new_track_session)
        self.new_tracks_count.setText(f"{active_count} w sesji")
        self.update_new_tracks_badge()
        self.update_new_tracks_actions()

    def new_track_selected(self, index):
        if index < 0 or index >= self.new_tracks_list.count():
            self.new_tracks_tag_panel.load_song("")
            return

        item = self.new_tracks_list.item(index)
        path = item.data(Qt.UserRole)
        song = self._find_song_for_playlist_path(path)

        if song is None:
            self.new_tracks_tag_panel.load_song("")
            return

        # NewTracksWidget owns the presentation. Resolve the song through
        # the same normalized-path lookup used by multi-selection so the
        # tag panel always receives the actual Song object.
        selected = self.get_selected_new_tracks()
        if len(selected) > 1:
            self.new_tracks_tag_panel.load_songs(
                [self.tag_service.read_grouping(s.path) for s in selected]
            )
        else:
            self.new_tracks_tag_panel.load_song(
                self.tag_service.read_grouping(song.path)
            )

        self.new_tracks_tag_panel.show()
        self.new_tracks_tag_panel.setEnabled(True)

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
        if getattr(self, "_new_tracks_tag_timer_pending", False):
            return
        self._new_tracks_tag_timer_pending = True
        QTimer.singleShot(10, self._apply_new_tracks_tags_changed)

    def _apply_new_tracks_tags_changed(self):
        self._new_tracks_tag_timer_pending = False
        if self._history_busy:
            return
            return

        selected = self.get_selected_new_tracks()
        changes = self.new_tracks_tag_panel.get_changes()
        if not selected or not changes:
            return

        entry = []
        for song in selected:
            before = self.tag_service.read_grouping(song.path)
            tags = self.tag_service.parse_grouping(before)

            for category, value, should_have in changes:
                values = tags.setdefault(category, [])
                if should_have and value not in values:
                    values.append(value)
                elif not should_have and value in values:
                    values.remove(value)

            after = self.tag_service.save_grouping(song.path, tags)
            song.grouping = after
            update_song(song)
            entry.append((song, before, after))

        # Pierwsza zmiana taga oznacza rozpoczęcie pracy nad utworem.
        self.new_track_statuses, self.new_track_session = (
            self.new_tracks_service.mark_started(
                [song.path for song in selected],
                self.new_track_statuses,
                self.new_track_session,
            )
        )

        # Persist after the current UI event has returned so Qt can paint
        # the status change immediately instead of blocking on JSON I/O.
        QTimer.singleShot(
            10,
            lambda: (
                self.save_new_track_statuses(),
                self.save_new_track_session(),
            ),
        )

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

        if selected:
            # We already read and saved the grouping above. Re-reading the
            # same audio files here only adds disk I/O and makes tag clicks
            # feel sluggish.
            self.new_tracks_tag_panel.set_baseline(
                [after for _song, _before, after in entry]
            )

    def finish_selected_new_tracks(self):
        selected = self.get_selected_new_tracks()
        if not selected:
            return

        self.new_track_statuses, self.new_track_session = (
            self.new_tracks_service.finish(
                [song.path for song in selected],
                self.new_track_statuses,
                self.new_track_session,
            )
        )

        self.save_new_track_statuses()
        self.save_new_track_session()
        self.refresh_new_tracks_tab()

    def update_new_tracks_actions(self):
        enabled = bool(self.new_tracks_list.selectedItems())
        self.new_tracks_finish_btn.setEnabled(enabled)

    def playlist_metadata_file(self, name):
        return self.playlist_metadata_service.metadata_file(name)

    def load_playlist_folder_map(self):
        return self.playlist_metadata_service.load_folder_map()

    def save_playlist_folder_map(self):
        self.playlist_metadata_service.save_folder_map(
            self.playlist_folder_map
        )

    def load_playlist_generated_map(self):
        return self.playlist_metadata_service.load_generated_map()

    def save_playlist_generated_map(self):
        self.playlist_metadata_service.save_generated_map(
            self.playlist_generated_map
        )

    def _save_view_mode(self, key, mode):
        self.app_settings[key] = mode
        self.settings_service.save(self.app_settings)

    # ==================== USTAWIENIA ====================
    def load_songs_from_source_folder(self):
        """Skanuje aktualnie wybrany folder źródłowy i zwraca jego utwory."""
        source = Path(self.app_settings["source_folder"])
        if not source.exists() or not source.is_dir():
            return []

        return self.library_service.load_from_folder(
            source,
            fallback_loader=load_songs,
        )

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

        if old_path and old_path in self.song_by_path:
            self.current_song = self.song_by_path[old_path]
        elif hasattr(self, "title"):
            self.title.clear()
            self.artist.clear()
            self.album.clear()
            self.library_widget.set_cover_for_song(None)

    def settings_file_path(self):
        return self.settings_service.settings_file_path()

    def load_app_settings(self):
        self.app_settings = self.settings_service.load()

    def save_app_settings(self):
        self.settings_service.save(self.app_settings)

    def _allow_tag_playlist_delete_changed(self, enabled):
        self.app_settings["allow_delete_tag_playlists"] = bool(enabled)
        self.save_app_settings()

    def _arrow_navigation_plays_track_changed(self, enabled):
        self.app_settings["arrow_navigation_plays_track"] = bool(enabled)
        self.save_app_settings()

    def _manual_sync_tag_playlists(self):
        self.sync_tag_playlists_silent()

        # Keep the currently displayed playlist contents in sync as well.
        if hasattr(self, "playlist_list"):
            self.refresh_playlist_list()

    def build_settings_tab(self):
        layout = QVBoxLayout(self.settings_tab)
        self.settings_widget = SettingsWidget(
            self.app_settings,
            self.settings_service,
            tag_service=self.tag_service,
            songs=self.songs,
            parent=self.settings_tab,
        )
        self.settings_widget.source_folder_changed.connect(
            self._settings_source_folder_changed
        )
        self.settings_widget.player_skip_changed.connect(
            self.player_widget.set_skip_seconds
        )
        self.settings_widget.tags_structure_changed.connect(
            self._tags_structure_changed
        )
        self.settings_widget.tag_category_shortcuts_changed.connect(
            self._tag_category_shortcuts_changed
        )
        self.settings_widget.allow_tag_playlist_delete_changed.connect(
            self._allow_tag_playlist_delete_changed
        )
        self.settings_widget.arrow_navigation_plays_track_changed.connect(
            self._arrow_navigation_plays_track_changed
        )
        self.settings_widget.tag_playlists_sync_requested.connect(
            self._manual_sync_tag_playlists
        )
        layout.addWidget(self.settings_widget)

    def _tags_structure_changed(self):
        self.available_tags = get_available_tags()

        # Keep generated tag playlists synchronized with category/tag
        # changes made in Settings.
        self.sync_tag_playlists_silent()

        if hasattr(self, "library_widget"):
            self.library_widget.refresh_available_tags(
                self.available_tags
            )

        if hasattr(self, "tag_panel"):
            selected = self.get_selected_songs()
            self.tag_panel.load_songs(
                [song.grouping for song in selected]
                if selected else [""]
            )

        if hasattr(self, "new_tracks_tag_panel"):
            selected_new = self.get_selected_new_tracks()
            self.new_tracks_tag_panel.load_songs(
                [song.grouping for song in selected_new]
                if selected_new else [""]
            )

        self.update_filter_tag_options()
        self.apply_filters()

    def _settings_source_folder_changed(self, folder):
        self.app_settings["source_folder"] = folder
        self.save_app_settings()

        # Keep the Spotify download destination synchronized with Settings.
        if hasattr(self, "spotify_download_folder"):
            self.spotify_download_folder.setText(folder)

        self.refresh_library_from_source_folder()
        self.tabs.setCurrentIndex(0)

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
        self.playlists_widget = PlaylistsWidget(self.playlist_tab)

        self.playlist_folder_filter = self.playlists_widget.playlist_folder_filter
        self.playlist_list = self.playlists_widget.playlist_list
        self.playlist_title = self.playlists_widget.playlist_title
        self.playlist_tracks = self.playlists_widget.playlist_tracks
        self.playlist_view_mode_button = self.playlists_widget.playlist_view_mode_button
        self.playlist_view_mode_button.set_mode(
            self.app_settings.get("playlist_view_mode", "medium")
        )
        self.playlist_tracks.set_view_mode(
            self.app_settings.get("playlist_view_mode", "medium")
        )
        self.playlist_tracks.set_cover_art_service(self.cover_art_service)
        self.playlist_view_mode_button.mode_changed.connect(
            lambda mode: self._save_view_mode("playlist_view_mode", mode)
        )
        self.playlist_info = self.playlists_widget.playlist_info

        self.playlist_folder_filter.currentIndexChanged.connect(
            self.refresh_playlist_list
        )
        self.playlist_list.itemClicked.connect(
            self.playlist_tree_item_clicked
        )
        self.playlist_list.folder_selected.connect(
            self._remember_folder_selected_for_delete
        )
        self.playlists_widget.playlist_dropped.connect(
            self.handle_playlist_drop
        )
        self.playlist_tracks.songs_dropped.connect(
            self.add_paths_to_current_playlist
        )
        self.playlist_tracks.itemDoubleClicked.connect(
            self.play_playlist_track
        )
        self.playlist_tracks.order_changed.connect(
            self.playlist_order_changed
        )

        self.playlists_widget.new_requested.connect(self.create_playlist)
        self.playlists_widget.rename_requested.connect(self.rename_playlist)
        self.playlists_widget.delete_requested.connect(self.delete_playlist)
        self.playlists_widget.folder_create_requested.connect(
            self.create_playlist_folder
        )
        self.playlists_widget.folder_delete_requested.connect(
            self.delete_playlist_folder
        )
        self.playlists_widget.remove_tracks_requested.connect(
            self.remove_selected_playlist_tracks
        )
        self.playlists_widget.export_m3u8_requested.connect(
            self.export_current_playlist
        )
        self.playlists_widget.export_djay_requested.connect(
            self.export_to_djay_pro
        )
        # Tag-derived playlists are synchronized automatically.

        layout = QHBoxLayout(self.playlist_tab)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.playlists_widget)

    def playlist_folders_for_all_names(self):
        return [
            playlist.get("name", "")
            for playlist in self.playlists
            if playlist.get("name", "")
        ]

    def playlist_folders_for(self, playlist_name):
        value = self.playlist_folder_map.get(playlist_name, [])
        if isinstance(value, str):
            return [value] if value else []
        if isinstance(value, (list, tuple, set)):
            return [
                str(folder).strip()
                for folder in value
                if str(folder).strip()
            ]
        return []

    def set_playlist_folders(self, playlist_name, folders):
        unique = []
        for folder in folders or []:
            folder = str(folder).strip().strip("/")
            if folder and folder not in unique:
                unique.append(folder)
        self.playlist_folder_map[playlist_name] = unique

    def refresh_playlist_list(self):
        if not hasattr(self, "playlist_list"):
            return

        # Preserve the user's tree state. If this refresh follows a drag,
        # use the state captured BEFORE Qt performed the drag interaction;
        # otherwise Qt may already have collapsed the source branch.
        expanded_folders = set(
            getattr(
                getattr(self, "playlist_list", None),
                "_expanded_before_drag",
                set(),
            )
        )
        if not expanded_folders:
            expanded_folders = set()
        if not expanded_folders:
            for i in range(self.playlist_list.topLevelItemCount()):
                stack = [self.playlist_list.topLevelItem(i)]
                while stack:
                    item = stack.pop()
                    if item.data(0, Qt.ItemDataRole.UserRole) == "folder":
                        path = item.data(
                            0, Qt.ItemDataRole.UserRole + 2
                        ) or ""
                        if item.isExpanded() and path:
                            expanded_folders.add(path)
                    for j in range(item.childCount()):
                        stack.append(item.child(j))

        current_folder = (
            self.playlist_folder_filter.currentData()
            if hasattr(self, "playlist_folder_filter")
            else ""
        )

        folders = list(self.playlist_folder_map.get("__folders__", []))
        for playlist in self.playlists:
            folders.extend(
                self.playlist_folders_for(playlist["name"])
            )

        folders = list(dict.fromkeys(
            str(folder).strip()
            for folder in folders
            if str(folder).strip()
        ))

        self.playlist_folder_filter.blockSignals(True)
        self.playlist_folder_filter.clear()
        self.playlist_folder_filter.addItem("📁 Wszystkie foldery", "")
        for folder in folders:
            self.playlist_folder_filter.addItem(
                f"📁 {folder.replace('/', ' / ')}", folder
            )
        idx = self.playlist_folder_filter.findData(current_folder)
        self.playlist_folder_filter.setCurrentIndex(
            idx if idx >= 0 else 0
        )
        self.playlist_folder_filter.blockSignals(False)

        self.playlist_list.blockSignals(True)
        self.playlist_list.clear()
        folder_items = {}

        def ensure_folder(path):
            path = str(path or "").strip().strip("/")
            if not path:
                return None
            if path in folder_items:
                return folder_items[path]

            parts = [
                part.strip()
                for part in path.split("/")
                if part.strip()
            ]
            parent = None
            built = []

            for part in parts:
                built.append(part)
                current_path = "/".join(built)
                node = folder_items.get(current_path)
                if node is None:
                    node = QTreeWidgetItem([f"📁 {part}"])
                    node.setData(
                        0, Qt.ItemDataRole.UserRole, "folder"
                    )
                    node.setData(
                        0, Qt.ItemDataRole.UserRole + 2,
                        current_path,
                    )
                    if parent is None:
                        self.playlist_list.addTopLevelItem(node)
                    else:
                        parent.addChild(node)
                    folder_items[current_path] = node
                parent = node

            return parent

        # Always render every folder. The filter no longer hides folders;
        # it only controls which playlist memberships are shown.
        for folder in folders:
            ensure_folder(folder)

        for index, playlist in enumerate(self.playlists):
            memberships = self.playlist_folders_for(
                playlist["name"]
            )

            visible_memberships = memberships
            if current_folder:
                visible_memberships = [
                    folder for folder in memberships
                    if folder == current_folder
                    or folder.startswith(current_folder + "/")
                ]

            if not visible_memberships:
                if current_folder:
                    continue
                visible_memberships = [""]

            generated = self.playlist_generated_map.get(
                playlist["name"], False
            )
            icon = "🏷️" if generated else "🎵"

            for folder in visible_memberships:
                if folder:
                    parent = ensure_folder(folder)
                else:
                    parent = folder_items.get("__mine__")
                    if parent is None:
                        parent = QTreeWidgetItem(
                            ["📁 Moje playlisty"]
                        )
                        parent.setData(
                            0, Qt.ItemDataRole.UserRole, "folder"
                        )
                        parent.setData(
                            0, Qt.ItemDataRole.UserRole + 2, ""
                        )
                        self.playlist_list.addTopLevelItem(parent)
                        folder_items["__mine__"] = parent

                child = QTreeWidgetItem(
                    [f"{icon} {playlist['name']}"]
                )
                child.setData(
                    0, Qt.ItemDataRole.UserRole, "playlist"
                )
                child.setData(
                    0, Qt.ItemDataRole.UserRole + 1, index
                )
                child.setData(
                    0, Qt.ItemDataRole.UserRole + 2, folder
                )
                parent.addChild(child)

                if index == self.current_playlist_index:
                    self.playlist_list.setCurrentItem(child)

        # Restore exactly the folder expansion state from before refresh.
        # Restore expanded folders and all their parents. This is important
        # when the moved playlist was the only child that caused a nested
        # branch to be visible before refresh.
        expanded_with_parents = set()
        for path in expanded_folders:
            parts = [part for part in path.split("/") if part]
            for i in range(1, len(parts) + 1):
                expanded_with_parents.add("/".join(parts[:i]))

        for path in expanded_with_parents:
            item = folder_items.get(path)
            if item is not None:
                item.setExpanded(True)

        self.playlist_list.blockSignals(False)
        if hasattr(self.playlist_list, "_expanded_before_drag"):
            self.playlist_list._expanded_before_drag = set()

        if not (
            0 <= self.current_playlist_index < len(self.playlists)
        ):
            self.current_playlist_index = -1
            self.refresh_playlist_contents()

    def _remember_folder_selected_for_delete(self, folder):
        self._selected_playlist_folder_path = str(
            folder or ""
        ).strip().strip("/")

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
        parent_folder = ""
        selected = (
            self.playlist_list.currentItem()
            if hasattr(self, "playlist_list")
            else None
        )

        if selected is not None:
            kind = selected.data(0, Qt.ItemDataRole.UserRole)
            if kind == "folder":
                parent_folder = selected.data(
                    0, Qt.ItemDataRole.UserRole + 2
                ) or ""
            elif kind == "playlist" and selected.parent() is not None:
                parent_folder = selected.parent().data(
                    0, Qt.ItemDataRole.UserRole + 2
                ) or ""

        if not parent_folder and hasattr(self, "playlist_folder_filter"):
            parent_folder = self.playlist_folder_filter.currentData() or ""

        prompt = "Nazwa folderu:"
        if parent_folder:
            prompt = (
                f"Nazwa folderu wewnątrz "
                f"„{parent_folder.replace('/', ' / ')}”:"
            )

        name, ok = QInputDialog.getText(
            self, "Nowy folder playlist", prompt
        )
        name = name.strip().strip("/")
        if not ok or not name:
            return

        full_name = f"{parent_folder}/{name}" if parent_folder else name

        if not self.playlist_folder_service.can_create(
            self.playlist_folder_map, full_name
        ):
            QMessageBox.warning(
                self, "Foldery", "Taki folder już istnieje."
            )
            return

        self.playlist_folder_service.create(
            self.playlist_folder_map, full_name
        )
        self.save_playlist_folder_map()
        self.refresh_playlist_list()


    def delete_playlist_folder(self, folder=""):
        folder = str(
            folder or getattr(
                self, "_selected_playlist_folder_path", ""
            ) or ""
        ).strip().strip("/")

        if not folder:
            QMessageBox.information(
                self,
                "Usuń folder",
                "Najpierw kliknij folder na drzewie po lewej.",
            )
            return

        generated_root = "Playlisty z tagów"
        if (
            folder == generated_root
            or folder.startswith(generated_root + "/")
        ):
            QMessageBox.information(
                self,
                "Folder zarządzany przez tagi",
                "Tego folderu nie usuwa się ręcznie. Jest tworzony "
                "automatycznie na podstawie kategorii i tagów.",
            )
            return

        answer = QMessageBox.question(
            self,
            "Usuń folder",
            f"Usunąć folder „{folder}”?\n\n"
            "Folder zostanie usunięty, ale playlisty pozostaną.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        self.playlist_folder_service.delete(
            self.playlist_folder_map,
            folder,
        )
        self.save_playlist_folder_map()
        self._selected_playlist_folder_path = ""
        self.refresh_playlist_list()

    def normalize_tag_folder(self, category):
        return self.tag_service.normalize_folder(category)

    def sync_tag_playlists_silent(self):
        """Synchronize tag playlists automatically.

        Hierarchy:
            Playlisty z tagów/<category>/<tag>

        Category/tag order comes from config/tags.json. Existing playlist
        order is never rewritten, so manual drag-and-drop order persists.
        """
        available = get_available_tags()
        generated_root = "Playlisty z tagów"
        desired = {}
        desired_order = []

        for category, values in available.items():
            category_name = str(category).strip()
            if not category_name:
                continue
            if not isinstance(values, (list, tuple, set)):
                values = [values]

            for value in values:
                name = str(value).strip()
                if not name:
                    continue
                key = name.casefold()
                if key not in desired:
                    desired_order.append(key)
                    desired[key] = {
                        "name": name,
                        "folder": f"{generated_root}/{category_name}",
                        "paths": [],
                    }

        for song in self.songs:
            try:
                tags = parse_grouping(
                    getattr(song, "grouping", "") or ""
                )
            except Exception:
                tags = {}

            for category, values in tags.items():
                category_name = str(category).strip()
                if not category_name:
                    continue
                if not isinstance(values, (list, tuple, set)):
                    values = [values]

                for value in values:
                    name = str(value).strip()
                    if not name:
                        continue
                    key = name.casefold()
                    if key not in desired:
                        desired_order.append(key)
                        desired[key] = {
                            "name": name,
                            "folder": (
                                f"{generated_root}/{category_name}"
                            ),
                            "paths": [],
                        }

                    path = self._normalize_playlist_path(song.path)
                    if path and path not in desired[key]["paths"]:
                        desired[key]["paths"].append(path)

        # Folder hierarchy in tag-category order.
        folder_order = [generated_root]
        for category in available.keys():
            category_name = str(category).strip()
            if category_name:
                folder_order.append(
                    f"{generated_root}/{category_name}"
                )
        for key in desired_order:
            folder = desired[key]["folder"]
            if folder not in folder_order:
                folder_order.append(folder)

        # Remove old top-level category folders created by previous
        # tag-playlist versions, but only when they contain no manual
        # playlists.
        old_category_roots = {
            str(category).strip()
            for category in available.keys()
            if str(category).strip()
        }
        existing_folders = list(
            self.playlist_folder_map.get("__folders__", [])
        )
        cleaned = []
        for folder in existing_folders:
            if folder in old_category_roots:
                has_manual = any(
                    folder in self.playlist_folders_for(name)
                    and not self.playlist_generated_map.get(name, False)
                    for name in self.playlist_folders_for_all_names()
                ) if hasattr(self, "playlist_folders_for_all_names") else False
                if not has_manual:
                    continue
            if folder not in cleaned:
                cleaned.append(folder)

        for folder in folder_order:
            if folder not in cleaned:
                cleaned.append(folder)
        self.playlist_folder_map["__folders__"] = cleaned

        by_name = {
            playlist.get("name", "").casefold(): playlist
            for playlist in self.playlists
        }
        changed = False

        # Create new playlists in tag order; never move existing playlists.
        for desired_index, key in enumerate(desired_order):
            wanted = desired[key]
            playlist = by_name.get(key)

            if playlist is None:
                playlist = {
                    "name": wanted["name"],
                    "paths": list(wanted["paths"]),
                }
                insert_at = len(self.playlists)

                previous = [
                    by_name[k]
                    for k in desired_order[:desired_index]
                    if k in by_name
                ]
                if previous:
                    insert_at = self.playlists.index(previous[-1]) + 1

                self.playlists.insert(insert_at, playlist)
                by_name[key] = playlist
                changed = True
            else:
                new_paths = list(wanted["paths"])
                if (
                    self.playlist_generated_map.get(
                        wanted["name"], False
                    )
                    and playlist.get("paths", []) != new_paths
                ):
                    playlist["paths"] = new_paths
                    changed = True

            if self.playlist_folders_for(wanted["name"]) != [
                wanted["folder"]
            ]:
                self.set_playlist_folders(
                    wanted["name"],
                    [wanted["folder"]],
                )
                changed = True

            if not self.playlist_generated_map.get(
                wanted["name"], False
            ):
                self.playlist_generated_map[wanted["name"]] = True
                changed = True

        desired_keys=set(desired)
        for playlist in list(self.playlists):
            name=playlist.get("name","")
            key=name.casefold()
            if (
                self.playlist_generated_map.get(name,False)
                and key not in desired_keys
            ):
                self.playlists.remove(playlist)
                self.playlist_generated_map.pop(name,None)
                self.playlist_folder_map.pop(name,None)
                changed=True

        if changed:
            self.playlist_storage_service.save(self.playlists)
        self.save_playlist_folder_map()
        self.save_playlist_generated_map()
        if hasattr(self,"playlist_list"):
            self.refresh_playlist_list()

    def sync_tag_playlists(self):
        """Compatibility entry point; synchronization is automatic."""
        self.sync_tag_playlists_silent()

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
            self.playlist_tracks._set_item_cover(item, path)
            valid_paths.append(path)
        self.playlist_info.setText(f"Nazwa: {playlist['name']}\nUtworów: {len(valid_paths)}")

    def playlist_selected(self, index):
        # Kept for compatibility with older UI code.
        if isinstance(index, int) and index >= 0:
            visible = [
                i for i, p in enumerate(self.playlists)
                if not self.playlist_folder_filter.currentData()
                or self.playlist_folder_filter.currentData() in self.playlist_folders_for(p["name"])
            ]
            if index < len(visible):
                self.current_playlist_index = visible[index]
                self.refresh_playlist_contents()

    def snapshot_playlists(self):
        return self.history_service.snapshot_playlists(self.playlists)

    def record_playlist_change(self, before):
        after = self.snapshot_playlists()
        if before == after:
            return
        self.undo_stack.append(("playlists", before, after, self.current_playlist_index))
        self.redo_stack.clear()
        self.playlist_storage_service.save(self.playlists)
        self.update_history_buttons()

    def handle_playlist_drop(
        self,
        source_index,
        source_folder,
        target_folder,
        target_position,
        action,
    ):
        if not (0 <= source_index < len(self.playlists)):
            return

        name = self.playlists[source_index]["name"]
        source_folder = (source_folder or "").strip().strip("/")
        target_folder = (target_folder or "").strip().strip("/")

        before = self.snapshot_playlists()
        memberships = self.playlist_folders_for(name)

        if action == "copy":
            # COPY means exactly that: keep the source membership and add
            # the target membership. Never remove source_folder.
            if target_folder in memberships:
                return
            memberships.append(target_folder)
            self.set_playlist_folders(name, memberships)

        else:
            # MOVE removes only the membership represented by the tree item.
            memberships = [
                folder for folder in memberships
                if folder != source_folder
            ]
            if target_folder not in memberships:
                memberships.append(target_folder)
            self.set_playlist_folders(name, memberships)

        self.playlist_folder_map.setdefault("__folders__", [])
        if (
            target_folder
            and target_folder not in self.playlist_folder_map["__folders__"]
        ):
            self.playlist_folder_map["__folders__"].append(target_folder)

        # Only a MOVE within the same folder changes ordering.
        if (
            action == "move"
            and source_folder == target_folder
        ):
            playlist = self.playlists.pop(source_index)
            target_position = max(0, int(target_position))

            same_folder_indices = [
                i for i, item in enumerate(self.playlists)
                if target_folder in self.playlist_folders_for(
                    item["name"]
                )
            ]

            if target_position >= len(same_folder_indices):
                insert_at = len(self.playlists)
                for i in range(len(self.playlists) - 1, -1, -1):
                    if target_folder in self.playlist_folders_for(
                        self.playlists[i]["name"]
                    ):
                        insert_at = i + 1
                        break
            else:
                insert_at = same_folder_indices[target_position]

            self.playlists.insert(insert_at, playlist)
            self.current_playlist_index = insert_at

        self.record_playlist_change(before)
        self.save_playlist_folder_map()
        self.refresh_playlist_list()

    def create_playlist(self):
        name, ok = QInputDialog.getText(
            self, "Nowa playlista", "Nazwa playlisty:"
        )
        name = name.strip()
        if not ok or not name:
            return

        if self.playlist_service.find_index(self.playlists, name) >= 0:
            QMessageBox.warning(
                self, "Playlisty", "Taka playlista już istnieje."
            )
            return

        before = self.snapshot_playlists()
        selected_folder = (
            self.playlist_folder_filter.currentData()
            if hasattr(self, "playlist_folder_filter")
            else ""
        )

        self.playlists.append({"name": name, "paths": []})
        if selected_folder:
            self.set_playlist_folders(name, [selected_folder])
            self.playlist_folder_map.setdefault("__folders__", [])
            if selected_folder not in self.playlist_folder_map["__folders__"]:
                self.playlist_folder_map["__folders__"].append(selected_folder)

        self.current_playlist_index = len(self.playlists) - 1
        self.record_playlist_change(before)
        self.save_playlist_folder_map()
        self.refresh_playlist_list()

    def rename_playlist(self):
        if not (0 <= self.current_playlist_index < len(self.playlists)):
            return

        old = self.playlists[self.current_playlist_index]["name"]
        name, ok = QInputDialog.getText(
            self, "Zmień nazwę", "Nazwa playlisty:", text=old
        )
        name = name.strip()
        if not ok or not name or name == old:
            return

        if self.playlist_service.find_index(
            self.playlists, name, exclude_index=self.current_playlist_index
        ) >= 0:
            QMessageBox.warning(
                self, "Playlisty", "Taka playlista już istnieje."
            )
            return

        before = self.snapshot_playlists()
        self.playlist_service.rename(
            self.playlists,
            self.current_playlist_index,
            name,
            self.playlist_folder_map,
            self.playlist_generated_map,
        )
        self.record_playlist_change(before)
        self.save_playlist_folder_map()
        self.save_playlist_generated_map()
        self.refresh_playlist_list()

    def delete_playlist(self):
        index = self.current_playlist_index

        if hasattr(self, "playlist_list"):
            item = self.playlist_list.currentItem()
            if (
                item is not None
                and item.data(0, Qt.ItemDataRole.UserRole) == "playlist"
            ):
                selected_index = item.data(
                    0, Qt.ItemDataRole.UserRole + 1
                )
                if isinstance(selected_index, int):
                    index = selected_index

        if not (0 <= index < len(self.playlists)):
            QMessageBox.information(
                self,
                "Usuń playlistę",
                "Najpierw zaznacz playlistę, którą chcesz usunąć.",
            )
            return

        self.current_playlist_index = index
        name = self.playlists[index]["name"]
        generated = bool(
            self.playlist_generated_map.get(name, False)
        )

        if generated and not bool(
            self.app_settings.get(
                "allow_delete_tag_playlists", False
            )
        ):
            QMessageBox.information(
                self,
                "Playlist z tagów",
                f"„{name}” jest playlistą utworzoną automatycznie z tagu.\n\n"
                "Usuwanie takich playlist jest zablokowane. "
                "Włącz w Ustawieniach opcję "
                "„Zezwól na usuwanie playlist z tagów”, "
                "jeśli chcesz ją usunąć.",
            )
            return

        question = f"Usunąć playlistę „{name}”?"
        if generated:
            question += (
                "\n\nUwaga: jest to playlista z tagów. "
                "Jeżeli odpowiadający tag nadal istnieje, "
                "automatyczna synchronizacja może ją ponownie utworzyć."
            )

        answer = QMessageBox.question(
            self,
            "Usuń playlistę",
            question,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        before = self.snapshot_playlists()
        self.playlist_service.delete(
            self.playlists,
            index,
            self.playlist_folder_map,
            self.playlist_generated_map,
        )
        self.current_playlist_index = min(
            index, len(self.playlists) - 1
        )
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
        self.playlist_service.add_paths(
            self.playlists, playlist_index, paths
        )
        self.record_playlist_change(before)
        self.refresh_playlist_list()

    def add_paths_to_current_playlist(self, paths):
        if not (0 <= self.current_playlist_index < len(self.playlists)):
            return

        before = self.snapshot_playlists()
        self.playlist_service.add_paths(
            self.playlists, self.current_playlist_index, paths
        )
        self.record_playlist_change(before)
        self.refresh_playlist_contents()

    def remove_selected_playlist_tracks(self):
        if not (0 <= self.current_playlist_index < len(self.playlists)):
            return

        selected = self.playlist_tracks.selectedItems()
        if not selected:
            return

        paths = [
            item.data(Qt.ItemDataRole.UserRole)
            for item in selected
            if item.data(Qt.ItemDataRole.UserRole)
        ]
        if not paths:
            return

        before = self.snapshot_playlists()
        self.playlist_service.remove_paths(
            self.playlists, self.current_playlist_index, paths
        )
        self.record_playlist_change(before)
        self.refresh_playlist_contents()

    def playlist_order_changed(self, before_paths, after_paths):
        if not (0 <= self.current_playlist_index < len(self.playlists)):
            return

        before = self.snapshot_playlists()
        self.playlist_service.set_paths(
            self.playlists, self.current_playlist_index, after_paths
        )
        self.record_playlist_change(before)
        self.refresh_playlist_contents()

    def export_current_playlist(self):
        if not (0 <= self.current_playlist_index < len(self.playlists)):
            return

        playlist = self.playlists[self.current_playlist_index]
        output_dir = Path(self.app_settings["output_folder"])
        path = self.library_export_service.export_m3u8(
            playlist,
            output_dir,
        )

        if path is None:
            QMessageBox.critical(
                self,
                "Eksport",
                "Nie udało się zapisać playlisty.",
            )
            return

        QMessageBox.information(
            self,
            "Eksport",
            f"Playlista została wyeksportowana.\n\n{path}",
        )

    def export_to_djay_pro(self):
        """Eksportuje playlisty do XML zgodnego z biblioteką djay Pro."""
        if not self.playlists:
            QMessageBox.information(
                self,
                "djay Pro",
                "Nie masz jeszcze żadnych playlist.",
            )
            return

        output_dir = Path(self.app_settings["output_folder"])
        path = self.library_export_service.export_djay_pro(
            self.playlists,
            self.song_by_path,
            output_dir,
            folder_map=self.playlist_folder_map,
        )

        if path is None:
            QMessageBox.critical(
                self,
                "djay Pro",
                "Nie udało się zapisać biblioteki XML.",
            )
            return

        QMessageBox.information(
            self,
            "Eksport do djay Pro zakończony",
            f"Zaktualizowano bibliotekę djay Pro.\n\n"
            f"Playlisty: {len(self.playlists)}\n"
            f"Plik: {path}",
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
        search_text = self.search.text().strip().lower()
        category = self.category_filter.currentData()
        tag = self.tag_filter.currentData()

        self.filtered_songs = self.library_filter_service.filter_songs(
            self.songs,
            search_text,
            category,
            tag,
            self.tag_service,
        )

        self.song_list.blockSignals(True)
        self.song_list.clear()
        from PySide6.QtWidgets import QListWidgetItem

        for song in self.filtered_songs:
            item = QListWidgetItem(f"{song.artist}\n{song.title}")
            item.setData(Qt.ItemDataRole.UserRole, song.path)
            self.song_list.addItem(item)
            self.song_list._set_item_cover(item, song.path)

        self.song_list.blockSignals(False)
        self.counter.setText(f"Znaleziono: {len(self.filtered_songs)} utworów")
        self.update_selected_counter()
        if self.filtered_songs:
            self.song_list.setCurrentRow(0)
        else:
            self.current_song = None
            self.current_grouping = ""
            self.title.clear()
            self.artist.clear()
            self.album.clear()
            self.library_widget.set_cover_for_song(None)
            self.tag_panel.load_song("")

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
        if len(selected)>1: self.tag_panel.load_songs([self.tag_service.read_grouping(s.path) for s in selected])

    def song_selected(self,index):
        if index<0 or index>=len(self.filtered_songs): return
        self.current_song=self.filtered_songs[index]
        self.title.setText(self.current_song.title)
        self.artist.setText(self.current_song.artist)
        self.album.setText(self.current_song.album)
        self.library_widget.set_cover_for_song(self.current_song.path)
        self.current_grouping=read_grouping(self.current_song.path); selected=self.get_selected_songs()
        if len(selected)>1: self.tag_panel.load_songs([self.tag_service.read_grouping(s.path) for s in selected])
        else: self.tag_panel.load_song(self.current_grouping)

    # ==================== ODTWARZACZ ====================
    def _player_media_status_changed(self, status):
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self.play_next_song()

    def play_song(self, song):
        if song is None:
            return
        if self.audio_player_service.load(song.path):
            self.player_widget.set_track(song.artist, song.title)
            self.player_widget.set_cover(song.path)
            self.audio_player_service.play()

    def play_current_song(self):
        self.play_song(self.current_song)

    def play_playlist_track(self, item):
        path = item.data(Qt.ItemDataRole.UserRole)
        song = self._find_song_for_playlist_path(path)
        self.play_song(song)

    def play_new_track(self, item):
        path = item.data(Qt.ItemDataRole.UserRole)
        song = self._find_song_for_playlist_path(path)
        self.play_song(song)

    def play_previous_song(self):
        if not self.filtered_songs:
            return
        current_index = self.song_list.currentRow()
        target = current_index - 1
        if target < 0:
            target = len(self.filtered_songs) - 1
        self.song_list.setCurrentRow(target)
        self.play_current_song()

    def play_next_song(self):
        if not self.filtered_songs:
            return
        current_index = self.song_list.currentRow()
        target = current_index + 1
        if target >= len(self.filtered_songs):
            target = 0
        self.song_list.setCurrentRow(target)
        self.play_current_song()

    def tags_changed(self):
        if self._history_busy:
            return
        if getattr(self, "_library_tag_timer_pending", False):
            return
        self._library_tag_timer_pending = True
        QTimer.singleShot(10, self._apply_tags_changed)

    def _apply_tags_changed(self):
        self._library_tag_timer_pending = False
        if self._history_busy:
            return
        selected = self.get_selected_songs()
        changes = self.tag_panel.get_changes()
        if not selected or not changes:
            return
        entry = []
        for song in selected:
            before = self.tag_service.read_grouping(song.path)
            tags = self.tag_service.parse_grouping(before)
            for category,value,should_have in changes:
                values=tags.setdefault(category,[])
                if should_have and value not in values: values.append(value)
                elif not should_have and value in values: values.remove(value)
            after = self.tag_service.save_grouping(song.path, tags)
            song.grouping = after
            update_song(song)
            entry.append((song, before, after))
        self.undo_stack.append(("tags",entry)); self.redo_stack.clear(); self.update_history_buttons()

        self.current_grouping = (
            read_grouping(self.current_song.path)
            if self.current_song in selected
            else (selected[0].grouping if selected else "")
        )
        self.tag_panel.set_baseline([song.grouping for song in selected])

        # Tag-derived playlists update immediately from the in-memory
        # groupings, without rescanning the audio files.
        self.sync_tag_playlists_silent()

    # ==================== UNDO / REDO ====================
    def restore_playlist_snapshot(self, snapshot):
        self.playlists = self.history_service.restore_playlist_snapshot(snapshot)

    def apply_history(self, history, undoing):
        kind = history[0]
        if kind == "tags":
            self.history_service.apply_tag_history(
                history[1],
                undoing,
                update_song,
            )
        elif kind == "playlists":
            snapshot = history[1] if undoing else history[2]
            self.restore_playlist_snapshot(snapshot)
            self.current_playlist_index = min(
                history[3],
                len(self.playlists) - 1,
            )

    def refresh_after_history(self):
        self._history_busy=True
        try:
            if self.current_song is not None:
                self.current_grouping=read_grouping(self.current_song.path)
                selected=self.get_selected_songs()
                if len(selected)>1: self.tag_panel.load_songs([self.tag_service.read_grouping(s.path) for s in selected])
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
