import re

from src.tags import (
    parse_grouping as _parse_grouping,
    read_grouping as _read_grouping,
    save_grouping as _save_grouping,
)


class TagService:
    """Domain boundary for audio grouping/tag operations."""

    LANGUAGE_ALIASES = {
        "language",
        "languages",
        "lang",
        "język",
        "języki",
    }

    def normalize_folder(self, category):
        key = str(category).strip()
        if key.casefold() in self.LANGUAGE_ALIASES:
            return "lang"
        return (
            re.sub(r"[^\w -]+", "", key, flags=re.UNICODE)
            .strip()
            .lower()
            .replace(" ", "_")
        )

    def read_grouping(self, path):
        return _read_grouping(path)

    def parse_grouping(self, grouping):
        return _parse_grouping(grouping)

    def save_grouping(self, path, tags):
        return _save_grouping(path, tags)
