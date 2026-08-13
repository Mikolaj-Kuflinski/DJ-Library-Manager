from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class SettingsWidget(QWidget):
    """Settings UI; persistence is handled by SettingsService."""

    source_folder_changed = Signal(str)

    def __init__(self, settings, settings_service, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.settings_service = settings_service
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

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
