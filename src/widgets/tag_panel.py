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
        self._category_titles = {}
        self._active_category = None
        self._loading = False
        self._baseline = []

    def load_song(self, grouping):
        self.load_songs([grouping])

    def load_songs(self, groupings):

        # Changing the selected track must not reset the user's active
        # tag category. Keep the category name, rebuild the checkboxes
        # for the new track, then restore the same category if it exists.
        previous_category = self._active_category

        self._loading = True
        self._baseline = list(groupings)

        while self.layout.count():
            item = self.layout.takeAt(0)

            if item.widget():
                item.widget().deleteLater()

        self.checkboxes = {}
        self._category_titles = {}
        self._active_category = None

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
            self._category_titles[category] = title

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

        if previous_category in self.checkboxes:
            self._set_active_category(previous_category)

    def focus_category(self, category):
        """Activate a category by its stable name and show it visibly.

        The category name, rather than a positional index, is used so
        shortcuts do not depend on masonry column placement.
        """
        category = str(category or "").strip()
        if category not in self.checkboxes:
            return False

        self._set_active_category(category)

        values = list(self.checkboxes.get(category, {}).keys())
        if values:
            self.checkboxes[category][values[0]].setFocus()

        return True

    def _set_active_category(self, category):
        self._active_category = category

        for name, title in self._category_titles.items():
            if name == category:
                title.setStyleSheet("""
                    font-size:16px;
                    font-weight:bold;
                    margin-top:10px;
                    padding:4px 8px;
                    border:1px solid palette(highlight);
                    border-radius:5px;
                """)
                title.setToolTip(
                    "Aktywna kategoria skrótów klawiszowych"
                )
            else:
                title.setStyleSheet("""
                    font-size:16px;
                    font-weight:bold;
                    margin-top:10px;
                    padding:4px 8px;
                """)
                title.setToolTip("")

    def keyPressEvent(self, event):
        if event.key() in (
            Qt.Key.Key_Return,
            Qt.Key.Key_Enter,
        ):
            focused = self.focusWidget()
            if isinstance(focused, QCheckBox):
                focused.setChecked(not focused.isChecked())
                event.accept()
                return

        if event.key() == Qt.Key.Key_Tab:
            self._focus_next_tag(reverse=bool(
                event.modifiers() & Qt.KeyboardModifier.ShiftModifier
            ))
            event.accept()
            return

        super().keyPressEvent(event)

    def _focus_next_tag(self, reverse=False):
        tags = [
            checkbox
            for category in self.checkboxes.values()
            for checkbox in category.values()
        ]
        if not tags:
            return

        focused = self.focusWidget()
        try:
            index = tags.index(focused)
        except ValueError:
            index = 0 if reverse else -1

        next_index = (
            (index - 1) % len(tags)
            if reverse
            else (index + 1) % len(tags)
        )
        tags[next_index].setFocus()


    def toggle_tag_by_number(self, number):
        """Toggle the Nth tag in the currently focused category."""
        if number < 1:
            return

        focused_category = self._active_category

        if focused_category not in self.checkboxes:
            for category, values in self.checkboxes.items():
                for checkbox in values.values():
                    if checkbox.hasFocus():
                        focused_category = category
                        break
                if focused_category is not None:
                    break

        if focused_category is None:
            return

        values = list(
            self.checkboxes.get(focused_category, {}).items()
        )
        index = number - 1
        if index >= len(values):
            return

        checkbox = values[index][1]
        checkbox.click()

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
