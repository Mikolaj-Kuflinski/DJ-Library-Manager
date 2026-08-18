from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
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
        self.layout = QHBoxLayout(self.container)
        self.layout.setContentsMargins(4, 4, 4, 4)
        self.layout.setSpacing(18)
        self.layout.setAlignment(
            Qt.AlignmentFlag.AlignTop
        )

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

        # Masonry-style columns.
        #
        # Categories are kept intact (title + all checkboxes), but each
        # category is placed into the currently shortest column. This avoids
        # the large empty spaces produced by a normal row/column grid when
        # categories contain different numbers of tags.
        category_widgets = []

        for category, values in available.items():

            category_widget = QWidget()
            category_layout = QVBoxLayout(category_widget)
            category_layout.setContentsMargins(0, 0, 0, 0)
            category_layout.setSpacing(3)

            title = QLabel(category)
            title.setStyleSheet("""
                font-size:16px;
                font-weight:bold;
                margin-top:10px;
            """)
            category_layout.addWidget(title)

            self.checkboxes[category] = {}

            for value in values:

                checkbox = QCheckBox(value)

                has_tag = any(
                    value in tags.get(category, [])
                    for tags in parsed
                )

                checkbox.setChecked(has_tag)
                checkbox.stateChanged.connect(
                    self._checkbox_changed
                )

                category_layout.addWidget(checkbox)
                self.checkboxes[category][value] = checkbox

            line = QFrame()
            line.setFrameShape(QFrame.HLine)
            category_layout.addWidget(line)

            # Approximate height used only for distribution. A category is
            # never split between columns.
            estimated_height = 42 + (len(values) * 28)
            category_widgets.append(
                (estimated_height, category_widget)
            )

        # Keep four columns on normal desktop widths. If there are fewer
        # categories, don't create empty columns.
        column_count = min(4, max(1, len(category_widgets)))
        columns = []

        for _ in range(column_count):
            column = QWidget()
            column_layout = QVBoxLayout(column)
            column_layout.setContentsMargins(0, 0, 0, 0)
            column_layout.setSpacing(8)
            column_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
            self.layout.addWidget(column)
            columns.append((0, column_layout))

        # Largest blocks first -> much better balancing between columns.
        for estimated_height, category_widget in sorted(
            category_widgets,
            key=lambda item: item[0],
            reverse=True,
        ):
            index = min(
                range(len(columns)),
                key=lambda i: columns[i][0]
            )
            current_height, column_layout = columns[index]
            column_layout.addWidget(category_widget)
            columns[index] = (
                current_height + estimated_height,
                column_layout,
            )

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

                current_state = checkbox.isChecked()

                had_tag = any(
                    value in tags.get(category, [])
                    for tags in before
                )

                if current_state == had_tag:
                    continue

                changes.append(
                    (category, value, current_state)
                )

        return changes

    def get_grouping(self):
        return build_grouping(self.get_tags())
