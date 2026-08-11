from pathlib import Path
import json
import os

from PySide6.QtWidgets import (
    QApplication, QWidget, QListWidget, QLabel, QVBoxLayout, QHBoxLayout,
    QLineEdit, QAbstractItemView, QPushButton, QComboBox, QTabWidget,
    QInputDialog, QMessageBox, QFileDialog, QToolButton, QDialog, QDialogButtonBox, QListWidgetItem,
    QFormLayout, QGroupBox,
)
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtCore import Qt

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
        self.songs = self.load_songs_from_source_folder()
        self.song_by_path = {song.path: song for song in self.songs}
        self.filtered_songs = self.songs.copy()
        self.current_song = None
        self.current_grouping = ""

        self.undo_stack = []
        self.redo_stack = []
        self._history_busy = False

        self.available_tags = get_available_tags()
        self.playlists = load_playlists()
        self.current_playlist_index = 0 if self.playlists else -1

        main_layout = QVBoxLayout(self)

        self.tabs = QTabWidget()
        self.tabs.setTabBar(DragTabBar())
        self.tabs.tabBar().tab_dragged.connect(
            self.dragged_over_tab
        )

        self.library_tab = QWidget()
        self.playlist_tab = QWidget()
        self.settings_tab = QWidget()
        self.tabs.addTab(self.library_tab, "🎵 Biblioteka")
        self.tabs.addTab(self.playlist_tab, "📋 Playlisty")
        self.new_tracks_tab = QWidget()
        self.tabs.addTab(self.new_tracks_tab, "🆕 Nowe utwory")
        self.tabs.addTab(self.settings_tab, "⚙ Ustawienia")
        main_layout.addWidget(self.tabs)

        self.build_library_tab()
        self.build_playlist_tab()
        self.build_new_tracks_tab()
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

    # ==================== NOWE UTWORY ====================
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
            song = self.song_by_path.get(path)
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
                    song = self.song_by_path.get(path)
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
        self.playlist_list = PlaylistListWidget()
        self.playlist_list.currentRowChanged.connect(self.playlist_selected)
        self.playlist_list.songs_dropped.connect(self.add_paths_to_dropped_playlist)
        left.addWidget(self.playlist_list)

        playlist_buttons = QHBoxLayout()
        new_btn = QPushButton("＋ Nowa")
        rename_btn = QPushButton("✏ Zmień nazwę")
        delete_btn = QPushButton("🗑 Usuń")
        new_btn.clicked.connect(self.create_playlist)
        rename_btn.clicked.connect(self.rename_playlist)
        delete_btn.clicked.connect(self.delete_playlist)
        playlist_buttons.addWidget(new_btn); playlist_buttons.addWidget(rename_btn); playlist_buttons.addWidget(delete_btn)
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
        self.playlist_list.blockSignals(True)
        self.playlist_list.clear()
        for playlist in self.playlists:
            self.playlist_list.addItem(playlist["name"])
        self.playlist_list.blockSignals(False)
        if 0 <= self.current_playlist_index < len(self.playlists):
            self.playlist_list.setCurrentRow(self.current_playlist_index)
        elif self.playlists:
            self.current_playlist_index = 0
            self.playlist_list.setCurrentRow(0)
        else:
            self.current_playlist_index = -1
            self.refresh_playlist_contents()

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
            song = self.song_by_path.get(path)
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
        if index < 0 or index >= len(self.playlists): return
        self.current_playlist_index = index
        self.refresh_playlist_contents()
        if self.playlist_tracks.count() > 0:
            self.playlist_tracks.setFocus()

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
        self.current_playlist_index = len(self.playlists) - 1
        self.record_playlist_change(before)
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
        self.record_playlist_change(before)
        self.refresh_playlist_list()

    def delete_playlist(self):
        if not (0 <= self.current_playlist_index < len(self.playlists)): return
        name = self.playlists[self.current_playlist_index]["name"]
        answer = QMessageBox.question(self, "Usuń playlistę", f"Usunąć playlistę „{name}”?")
        if answer != QMessageBox.StandardButton.Yes: return
        before = self.snapshot_playlists()
        del self.playlists[self.current_playlist_index]
        self.current_playlist_index = min(self.current_playlist_index, len(self.playlists)-1)
        self.record_playlist_change(before)
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
        from datetime import datetime, timezone
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
