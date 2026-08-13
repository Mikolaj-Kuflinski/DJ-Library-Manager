import json
from pathlib import Path


class NewTracksService:
    """Persistence and state storage for the New Tracks workflow."""

    STATUS_FILE = "new_tracks_status.json"
    SESSION_FILE = "new_tracks_session.json"

    def __init__(self, settings_service):
        self.settings_service = settings_service

    def _base_path(self):
        return self.settings_service.settings_file_path().parent

    def status_path(self):
        return self._base_path() / self.STATUS_FILE

    def session_path(self):
        return self._base_path() / self.SESSION_FILE

    def load_statuses(self):
        try:
            path = self.status_path()
            if not path.exists():
                return {}
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return {str(k): str(v) for k, v in data.items()}
        except (OSError, ValueError, TypeError):
            pass
        return {}

    def save_statuses(self, statuses):
        try:
            path = self.status_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(
                    dict(statuses or {}),
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
        except OSError:
            pass

    def load_session(self):
        try:
            path = self.session_path()
            if not path.exists():
                return set()
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return {
                    str(Path(path_value).resolve())
                    for path_value in data
                }
        except (OSError, ValueError, TypeError):
            pass
        return set()



    def ensure_session(self, songs, statuses, session, persist=True):
        current_paths = {
            str(Path(song.path).resolve())
            for song in songs
        }

        for path in current_paths:
            if path not in statuses:
                statuses[path] = "new"
                session.add(path)

        for path, status in statuses.items():
            if status in ("new", "todo") and path in current_paths:
                session.add(path)

        session.intersection_update(current_paths)

        cleaned_statuses = {
            path: status
            for path, status in statuses.items()
            if path in current_paths
        }

        if persist:
            self.save_statuses(cleaned_statuses)
            self.save_session(session)

        return cleaned_statuses, session



    def mark_started(self, paths, statuses, session):
        for path in paths:
            normalized = str(Path(path).resolve())
            if statuses.get(normalized) == "new":
                statuses[normalized] = "todo"
            session.add(normalized)
        return statuses, session

    def finish(self, paths, statuses, session):
        for path in paths:
            normalized = str(Path(path).resolve())
            statuses[normalized] = "tagged"
            session.discard(normalized)
        return statuses, session

    def save_session(self, session):
        try:
            path = self.session_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(
                    sorted(str(Path(p).resolve()) for p in (session or set())),
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
        except OSError:
            pass
