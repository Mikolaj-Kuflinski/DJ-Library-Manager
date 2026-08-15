import json
from pathlib import Path


class SettingsService:
    """Persistent application settings."""

    FILE_NAME = "settings.json"

    def __init__(self, base_dir=None):
        self.base_dir = Path(base_dir) if base_dir else Path(__file__).resolve().parents[2]

    def settings_file_path(self):
        # Keep the established project data location. Playlist metadata,
        # error-book data and existing settings live alongside this file.
        return self.base_dir / "config" / self.FILE_NAME

    def default_settings(self):
        music_folder = Path.home() / "Music"
        documents_folder = Path.home() / "Documents"
        default_output = documents_folder / "DJ Library Manager" / "Exports"
        default_output.mkdir(parents=True, exist_ok=True)

        return {
            "source_folder": str(music_folder),
            "output_folder": str(default_output),
            "spotify_cookie_file": "",
            "player_skip_seconds": 5,
            "library_view_mode": "medium",
            "playlist_view_mode": "medium",
            "new_tracks_view_mode": "medium",
        }

    def load(self):
        settings = self.default_settings()
        try:
            path = self.settings_file_path()
            if path.exists():
                loaded = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    for key in settings:
                        if loaded.get(key) is not None:
                            if key == "player_skip_seconds":
                                try:
                                    settings[key] = int(loaded[key])
                                except (TypeError, ValueError):
                                    pass
                            else:
                                settings[key] = str(loaded[key])
        except (OSError, ValueError, TypeError):
            pass

        Path(settings["output_folder"]).mkdir(
            parents=True,
            exist_ok=True,
        )
        self.save(settings)
        return settings

    def save(self, settings):
        try:
            path = self.settings_file_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(
                    dict(settings or {}),
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
        except OSError:
            pass
