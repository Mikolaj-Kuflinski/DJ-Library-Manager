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
from src.tags import (
    parse_grouping,
    build_grouping,
)


class TagPanel(QWidget):
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

        main_layout.addWidget(self.save_button)

        self.checkboxes = {}

    def load_song(self, grouping):

        while self.layout.count():

            item = self.layout.takeAt(0)

            if item.widget():
                item.widget().deleteLater()

        self.checkboxes = {}

        tags = parse_grouping(grouping)

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

                checkbox.setChecked(
                    value in tags.get(category, [])
                )

                self.layout.addWidget(checkbox)

                self.checkboxes[category][value] = checkbox

            line = QFrame()
            line.setFrameShape(QFrame.HLine)

            self.layout.addWidget(line)

        self.layout.addStretch()

    def get_tags(self):

        tags = {}

        for category, values in self.checkboxes.items():

            tags[category] = []

            for value, checkbox in values.items():

                if checkbox.isChecked():
                    tags[category].append(value)

        return tags

    def get_grouping(self):

        return build_grouping(self.get_tags())