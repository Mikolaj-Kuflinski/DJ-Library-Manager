import json
from pathlib import Path


class PlaylistStorageService:
    """Persistence boundary for playlist data."""

    PLAYLISTS_FILE = (
        Path(__file__).resolve().parents[2] / "playlists.json"
    )

    def load(self):
        path = self.PLAYLISTS_FILE
        if not path.exists():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except (OSError, json.JSONDecodeError, TypeError):
            return []

    def save(self, playlists):
        path = self.PLAYLISTS_FILE
        tmp = path.with_suffix(".tmp")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_text(
                json.dumps(
                    playlists or [],
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            tmp.replace(path)
        except OSError:
            try:
                if tmp.exists():
                    tmp.unlink()
            except OSError:
                pass
