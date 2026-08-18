from pathlib import Path

from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QComboBox,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QInputDialog,
    QCheckBox,
    QScrollArea,
)


from src.config import get_available_tags, save_tags


class SettingsWidget(QWidget):
    """Settings UI; persistence is handled by SettingsService."""

    source_folder_changed = Signal(str)
    player_skip_changed = Signal(int)
    tags_structure_changed = Signal()
    allow_tag_playlist_delete_changed = Signal(bool)
    tag_playlists_sync_requested = Signal()

    def __init__(self, settings, settings_service, tag_service=None, songs=None, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.settings_service = settings_service
        self.tag_service = tag_service
        self.songs = songs if songs is not None else []
        self._build_ui()

    def _build_ui(self):
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(4, 4, 4, 12)
        layout.setSpacing(10)
        scroll.setWidget(content)
        outer_layout.addWidget(scroll)

        title = QLabel("⚙ Ustawienia")
        title.setStyleSheet("font-size:18px;font-weight:bold;")
        layout.addWidget(title)

        group = QGroupBox("Foldery")
        form = QFormLayout(group)

        source_row = QHBoxLayout()
        self.source_folder_edit = QLineEdit(self.settings["source_folder"])
        self.source_folder_edit.setReadOnly(True)
        source_btn = QPushButton("Wybierz…")
        source_btn.clicked.connect(lambda: self.choose_folder("source_folder"))
        source_row.addWidget(self.source_folder_edit, 1)
        source_row.addWidget(source_btn)
        form.addRow("📁 Folder źródłowy:", source_row)

        output_row = QHBoxLayout()
        self.output_folder_edit = QLineEdit(self.settings["output_folder"])
        self.output_folder_edit.setReadOnly(True)
        output_btn = QPushButton("Wybierz…")
        output_btn.clicked.connect(lambda: self.choose_folder("output_folder"))
        output_row.addWidget(self.output_folder_edit, 1)
        output_row.addWidget(output_btn)
        form.addRow("📤 Folder eksportu:", output_row)

        layout.addWidget(group)

        player_group = QGroupBox("Odtwarzacz")
        player_form = QFormLayout(player_group)

        self.player_skip_combo = QComboBox()
        for seconds in (5, 10, 15, 30, 60):
            self.player_skip_combo.addItem(f"{seconds} sekund", seconds)

        current_skip = int(self.settings.get("player_skip_seconds", 5))
        index = self.player_skip_combo.findData(current_skip)
        self.player_skip_combo.setCurrentIndex(index if index >= 0 else 0)
        self.player_skip_combo.currentIndexChanged.connect(
            self._player_skip_changed
        )
        player_form.addRow("⏩ Skok przy strzałkach:", self.player_skip_combo)
        layout.addWidget(player_group)

        safety_group = QGroupBox("Bezpieczeństwo playlist")
        safety_layout = QVBoxLayout(safety_group)

        self.allow_tag_playlist_delete_checkbox = QCheckBox(
            "Zezwól na usuwanie playlist z tagów"
        )
        self.allow_tag_playlist_delete_checkbox.setChecked(
            bool(
                self.settings.get(
                    "allow_delete_tag_playlists", False
                )
            )
        )
        self.allow_tag_playlist_delete_checkbox.setToolTip(
            "Domyślnie wyłączone. Chroni playlisty tworzone automatycznie "
            "na podstawie tagów przed przypadkowym usunięciem."
        )
        self.allow_tag_playlist_delete_checkbox.toggled.connect(
            self._allow_tag_playlist_delete_changed
        )
        safety_layout.addWidget(
            self.allow_tag_playlist_delete_checkbox
        )

        safety_hint = QLabel(
            "Wyłączone = playlisty 🏷️ z tagów są chronione przed usunięciem. "
            "Zwykłe playlisty nadal można usuwać normalnie."
        )
        safety_hint.setWordWrap(True)
        safety_layout.addWidget(safety_hint)
        layout.addWidget(safety_group)

        playlist_sync_group = QGroupBox("Playlisty z tagów")
        playlist_sync_layout = QVBoxLayout(playlist_sync_group)

        playlist_sync_hint = QLabel(
            "Playlisty z tagów synchronizują się automatycznie po zmianach "
            "tagów. Przycisk poniżej pozwala wymusić synchronizację w dowolnym momencie."
        )
        playlist_sync_hint.setWordWrap(True)
        playlist_sync_layout.addWidget(playlist_sync_hint)

        sync_tag_playlists_btn = QPushButton(
            "↻ Synchronizuj playlisty z tagów"
        )
        sync_tag_playlists_btn.setToolTip(
            "Utwórz brakujące playlisty z tagów, zaktualizuj ich zawartość "
            "i uporządkuj foldery według kategorii tagów."
        )
        sync_tag_playlists_btn.clicked.connect(
            self.tag_playlists_sync_requested.emit
        )
        playlist_sync_layout.addWidget(sync_tag_playlists_btn)
        layout.addWidget(playlist_sync_group)

        # ============================================================
        # Zarządzanie tagami
        # ============================================================
        tags_group = QGroupBox("Tagi i kategorie")
        tags_layout = QVBoxLayout(tags_group)

        tags_hint = QLabel(
            "Twórz własne kategorie i tagi oraz zmieniaj ich nazwy. "
            "Zmiana lub usunięcie istniejącego taga aktualizuje również "
            "tagi zapisane w plikach muzycznych."
        )
        tags_hint.setWordWrap(True)
        tags_layout.addWidget(tags_hint)

        manager_row = QHBoxLayout()

        category_col = QVBoxLayout()
        category_col.addWidget(QLabel("Kategorie"))

        self.tag_category_list = QListWidget()
        self.tag_category_list.setMinimumWidth(180)
        self.tag_category_list.currentRowChanged.connect(
            self._tag_category_selected
        )
        category_col.addWidget(self.tag_category_list)

        category_buttons = QHBoxLayout()
        add_category_btn = QPushButton("+ Kategoria")
        rename_category_btn = QPushButton("✎ Zmień")
        delete_category_btn = QPushButton("🗑 Usuń")
        add_category_btn.clicked.connect(self.add_tag_category)
        rename_category_btn.clicked.connect(self.rename_tag_category)
        delete_category_btn.clicked.connect(self.delete_tag_category)
        category_buttons.addWidget(add_category_btn)
        category_buttons.addWidget(rename_category_btn)
        category_buttons.addWidget(delete_category_btn)
        category_col.addLayout(category_buttons)

        tag_col = QVBoxLayout()
        tag_col.addWidget(QLabel("Tagi w kategorii"))

        self.tag_value_list = QListWidget()
        self.tag_value_list.setMinimumWidth(220)
        tag_col.addWidget(self.tag_value_list)

        tag_buttons = QHBoxLayout()
        add_tag_btn = QPushButton("+ Tag")
        rename_tag_btn = QPushButton("✎ Zmień")
        delete_tag_btn = QPushButton("🗑 Usuń")
        add_tag_btn.clicked.connect(self.add_tag)
        rename_tag_btn.clicked.connect(self.rename_tag)
        delete_tag_btn.clicked.connect(self.delete_tag)
        tag_buttons.addWidget(add_tag_btn)
        tag_buttons.addWidget(rename_tag_btn)
        tag_buttons.addWidget(delete_tag_btn)
        tag_col.addLayout(tag_buttons)

        manager_row.addLayout(category_col, 1)
        manager_row.addLayout(tag_col, 1)
        tags_layout.addLayout(manager_row)

        layout.addWidget(tags_group)

        self._reload_tag_manager()

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
        reset_btn.clicked.connect(self.reset_folders)
        layout.addWidget(reset_btn)
        layout.addStretch()

    def _allow_tag_playlist_delete_changed(self, enabled):
        self.settings["allow_delete_tag_playlists"] = bool(enabled)
        self.settings_service.save(self.settings)
        self.allow_tag_playlist_delete_changed.emit(bool(enabled))

    def _reload_tag_manager(self, select_category=None):
        self._tag_manager_data = get_available_tags()

        current = select_category
        if current is None and self.tag_category_list.count():
            item = self.tag_category_list.currentItem()
            current = item.text() if item else None

        self.tag_category_list.blockSignals(True)
        self.tag_category_list.clear()
        for category in self._tag_manager_data:
            self.tag_category_list.addItem(category)
        self.tag_category_list.blockSignals(False)

        index = -1
        if current:
            index = self.tag_category_list.findItems(
                current,
                Qt.MatchFlag.MatchExactly,
            )
            index = self.tag_category_list.row(index[0]) if index else -1

        if index < 0 and self.tag_category_list.count():
            index = 0

        self.tag_category_list.setCurrentRow(index)
        self._tag_category_selected(index)

    def _tag_category_selected(self, row):
        self.tag_value_list.clear()
        if row < 0:
            return

        category = self.tag_category_list.item(row).text()
        for value in self._tag_manager_data.get(category, []):
            self.tag_value_list.addItem(value)

    def _unique_name(self, value, existing):
        value = str(value or "").strip()
        if not value:
            return ""
        if value.casefold() in {str(x).casefold() for x in existing}:
            return ""
        return value

    def add_tag_category(self):
        name, ok = QInputDialog.getText(
            self, "Nowa kategoria", "Nazwa kategorii:"
        )
        if not ok:
            return

        name = self._unique_name(name, self._tag_manager_data.keys())
        if not name:
            QMessageBox.warning(
                self, "Tagi", "Podaj unikalną nazwę kategorii."
            )
            return

        self._tag_manager_data[name] = []
        save_tags(self._tag_manager_data)
        self._reload_tag_manager(name)
        self.tags_structure_changed.emit()

    def rename_tag_category(self):
        item = self.tag_category_list.currentItem()
        if item is None:
            return

        old = item.text()
        name, ok = QInputDialog.getText(
            self,
            "Zmień kategorię",
            "Nowa nazwa kategorii:",
            text=old,
        )
        if not ok:
            return

        name = str(name).strip()
        if not name or (
            name.casefold() != old.casefold()
            and name.casefold() in {
                str(x).casefold()
                for x in self._tag_manager_data
            }
        ):
            QMessageBox.warning(
                self, "Tagi", "Podaj unikalną nazwę kategorii."
            )
            return

        values = self._tag_manager_data.pop(old)
        self._tag_manager_data[name] = values
        self._migrate_category(old, name)
        save_tags(self._tag_manager_data)
        self._reload_tag_manager(name)
        self.tags_structure_changed.emit()

    def delete_tag_category(self):
        item = self.tag_category_list.currentItem()
        if item is None:
            return

        category = item.text()
        values = self._tag_manager_data.get(category, [])

        answer = QMessageBox.question(
            self,
            "Usuń kategorię",
            f"Usunąć kategorię „{category}”"
            f" wraz z {len(values)} tagami?\n\n"
            "Tagi tej kategorii zostaną również usunięte "
            "z plików muzycznych.",
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        self._remove_category_from_songs(category)
        del self._tag_manager_data[category]
        save_tags(self._tag_manager_data)
        self._reload_tag_manager()
        self.tags_structure_changed.emit()

    def add_tag(self):
        category_item = self.tag_category_list.currentItem()
        if category_item is None:
            QMessageBox.information(
                self, "Tagi", "Najpierw wybierz kategorię."
            )
            return

        category = category_item.text()
        name, ok = QInputDialog.getText(
            self, "Nowy tag", f"Nowy tag w kategorii „{category}”:"
        )
        if not ok:
            return

        name = self._unique_name(
            name,
            self._tag_manager_data.get(category, []),
        )
        if not name:
            QMessageBox.warning(
                self, "Tagi", "Podaj unikalną nazwę taga."
            )
            return

        self._tag_manager_data[category].append(name)
        save_tags(self._tag_manager_data)
        self._reload_tag_manager(category)
        self.tags_structure_changed.emit()

    def rename_tag(self):
        category_item = self.tag_category_list.currentItem()
        tag_item = self.tag_value_list.currentItem()
        if category_item is None or tag_item is None:
            return

        category = category_item.text()
        old = tag_item.text()
        name, ok = QInputDialog.getText(
            self,
            "Zmień tag",
            "Nowa nazwa taga:",
            text=old,
        )
        if not ok:
            return

        name = str(name).strip()
        existing = self._tag_manager_data.get(category, [])
        if (
            not name
            or (
                name.casefold() != old.casefold()
                and name.casefold() in {
                    str(x).casefold() for x in existing
                }
            )
        ):
            QMessageBox.warning(
                self, "Tagi", "Podaj unikalną nazwę taga."
            )
            return

        self._tag_manager_data[category] = [
            name if value == old else value
            for value in existing
        ]
        self._migrate_tag(category, old, name)
        save_tags(self._tag_manager_data)
        self._reload_tag_manager(category)
        self.tags_structure_changed.emit()

    def delete_tag(self):
        category_item = self.tag_category_list.currentItem()
        tag_item = self.tag_value_list.currentItem()
        if category_item is None or tag_item is None:
            return

        category = category_item.text()
        value = tag_item.text()

        answer = QMessageBox.question(
            self,
            "Usuń tag",
            f"Usunąć tag „{value}” z kategorii „{category}”?\n\n"
            "Tag zostanie również usunięty z plików muzycznych.",
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        self._remove_tag_from_songs(category, value)
        self._tag_manager_data[category] = [
            item for item in self._tag_manager_data[category]
            if item != value
        ]
        save_tags(self._tag_manager_data)
        self._reload_tag_manager(category)
        self.tags_structure_changed.emit()

    def _migrate_category(self, old, new):
        if self.tag_service is None:
            return

        for song in self.songs:
            try:
                before = self.tag_service.read_grouping(song.path)
                tags = self.tag_service.parse_grouping(before)
                if old not in tags:
                    continue
                values = tags.pop(old)
                tags[new] = values
                after = self.tag_service.save_grouping(song.path, tags)
                song.grouping = after
            except Exception:
                continue

    def _remove_category_from_songs(self, category):
        if self.tag_service is None:
            return

        for song in self.songs:
            try:
                before = self.tag_service.read_grouping(song.path)
                tags = self.tag_service.parse_grouping(before)
                if category not in tags:
                    continue
                tags.pop(category, None)
                song.grouping = self.tag_service.save_grouping(
                    song.path, tags
                )
            except Exception:
                continue

    def _migrate_tag(self, category, old, new):
        if self.tag_service is None:
            return

        for song in self.songs:
            try:
                before = self.tag_service.read_grouping(song.path)
                tags = self.tag_service.parse_grouping(before)
                values = tags.get(category, [])
                if old not in values:
                    continue
                tags[category] = [
                    new if value == old else value
                    for value in values
                ]
                song.grouping = self.tag_service.save_grouping(
                    song.path, tags
                )
            except Exception:
                continue

    def _remove_tag_from_songs(self, category, value):
        if self.tag_service is None:
            return

        for song in self.songs:
            try:
                before = self.tag_service.read_grouping(song.path)
                tags = self.tag_service.parse_grouping(before)
                values = tags.get(category, [])
                if value not in values:
                    continue
                tags[category] = [
                    item for item in values if item != value
                ]
                if not tags[category]:
                    tags.pop(category, None)
                song.grouping = self.tag_service.save_grouping(
                    song.path, tags
                )
            except Exception:
                continue

    def _player_skip_changed(self, _index):
        seconds = int(self.player_skip_combo.currentData() or 5)
        self.settings["player_skip_seconds"] = seconds
        self.settings_service.save(self.settings)
        self.player_skip_changed.emit(seconds)

    def choose_folder(self, setting_name):
        current = self.settings.get(setting_name, str(Path.home()))
        folder = QFileDialog.getExistingDirectory(self, "Wybierz folder", current)
        if not folder:
            return

        folder = str(Path(folder).resolve())
        self.settings[setting_name] = folder

        if setting_name == "source_folder":
            self.source_folder_edit.setText(folder)
            self.settings_service.save(self.settings)
            self.source_folder_changed.emit(folder)
            return

        Path(folder).mkdir(parents=True, exist_ok=True)
        self.output_folder_edit.setText(folder)
        self.settings_service.save(self.settings)

    def reset_folders(self):
        defaults = self.settings_service.default_settings()
        self.settings["source_folder"] = defaults["source_folder"]
        self.settings["output_folder"] = defaults["output_folder"]
        self.source_folder_edit.setText(defaults["source_folder"])
        self.output_folder_edit.setText(defaults["output_folder"])
        self.settings_service.save(self.settings)
        self.source_folder_changed.emit(defaults["source_folder"])
