import json


class PlaylistMetadataService:
    """Persistence for playlist folders and generated-playlist metadata."""

    FOLDER_MAP_FILE = "playlist_folders.json"
    GENERATED_MAP_FILE = "playlist_generated.json"

    def __init__(self, settings_service):
        self.settings_service = settings_service

    def metadata_file(self, name):
        return self.settings_service.settings_file_path().parent / name

    def load_folder_map(self):
        path = self.metadata_file(self.FOLDER_MAP_FILE)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {"__folders__": []}
        except (OSError, ValueError, TypeError):
            return {"__folders__": []}

    def save_folder_map(self, folder_map):
        try:
            self.metadata_file(self.FOLDER_MAP_FILE).write_text(
                json.dumps(
                    folder_map or {"__folders__": []},
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
        except OSError:
            pass

    def load_generated_map(self):
        path = self.metadata_file(self.GENERATED_MAP_FILE)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError, TypeError):
            return {}

    def save_generated_map(self, generated_map):
        try:
            self.metadata_file(self.GENERATED_MAP_FILE).write_text(
                json.dumps(
                    generated_map or {},
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
        except OSError:
            pass
