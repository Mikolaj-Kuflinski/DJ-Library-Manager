from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QCheckBox,
    QScrollArea,
    QFrame,
    QPushButton,
)

from src.config import get_available_tags
from src.tags import parse_grouping, build_grouping


class TagPanel(QWidget):

    tags_changed = Signal()

    def __init__(self):
        super().__init__()

        main_layout = QVBoxLayout(self)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)

        self.container = QWidget()
        self.layout = QVBoxLayout(self.container)

        self.scroll.setWidget(self.container)
        main_layout.addWidget(self.scroll)

        self.save_button = QPushButton("💾 Zapisz")
        self.save_button.hide()
        main_layout.addWidget(self.save_button)

        self.checkboxes = {}
        self._loading = False
        self._baseline = []

    def load_song(self, grouping):
        self.load_songs([grouping])

    def load_songs(self, groupings):

        self._loading = True
        self._baseline = list(groupings)

        while self.layout.count():
            item = self.layout.takeAt(0)

            if item.widget():
                item.widget().deleteLater()

        self.checkboxes = {}

        parsed = [
            parse_grouping(grouping)
            for grouping in groupings
        ]

        available = get_available_tags()

        for category, values in available.items():

            title = QLabel(category)
            title.setStyleSheet("""
                font-size:16px;
                font-weight:bold;
                margin-top:10px;
            """)
            self.layout.addWidget(title)

            self.checkboxes[category] = {}

            for value in values:

                checkbox = QCheckBox(value)

                # W trybie multi-select tag jest pokazany jako
                # zaznaczony, jeżeli ma go CHOCIAŻ JEDEN
                # z zaznaczonych utworów.
                #
                # Dzięki temu brak tagu w jednym utworze nie
                # powoduje jego usunięcia przy dodawaniu innego.
                has_tag = any(
                    value in tags.get(category, [])
                    for tags in parsed
                )

                checkbox.setChecked(has_tag)

                checkbox.stateChanged.connect(
                    self._checkbox_changed
                )

                self.layout.addWidget(checkbox)
                self.checkboxes[category][value] = checkbox

            line = QFrame()
            line.setFrameShape(QFrame.HLine)
            self.layout.addWidget(line)

        self.layout.addStretch()
        self._loading = False

    def set_baseline(self, groupings):
        self._baseline = list(groupings)

    def _checkbox_changed(self, _state):

        if self._loading:
            return

        self.tags_changed.emit()

    def get_tags(self):

        tags = {}

        for category, values in self.checkboxes.items():

            tags[category] = []

            for value, checkbox in values.items():

                if checkbox.isChecked():
                    tags[category].append(value)

        return tags

    def get_changes(self):

        if not self._baseline:
            return []

        before = [
            parse_grouping(grouping)
            for grouping in self._baseline
        ]

        changes = []

        for category, values in self.checkboxes.items():

            for value, checkbox in values.items():

                # Aktualny stan checkboxa mówi wyłącznie o
                # tym, co użytkownik właśnie wybrał.
                #
                # CHECKED  -> dodaj tag wszystkim
                # UNCHECKED -> usuń tag wszystkim
                current_state = checkbox.isChecked()

                had_tag = any(
                    value in tags.get(category, [])
                    for tags in before
                )

                # Jeżeli nic się nie zmieniło względem stanu,
                # nie robimy żadnego zapisu.
                if current_state == had_tag:
                    continue

                changes.append(
                    (category, value, current_state)
                )

        return changes

    def get_grouping(self):
        return build_grouping(self.get_tags())
