import json
import re
from datetime import datetime


class ErrorBookService:
    """Persistent storage for failed Spotify downloads."""

    FILE_NAME = "spotify_error_book.json"

    def __init__(self, settings_service):
        self.settings_service = settings_service

    def errors_file(self):
        return self.settings_service.settings_file_path().parent / self.FILE_NAME

    def load(self):
        path = self.errors_file()
        try:
            if path.exists():
                data = json.loads(path.read_text(encoding="utf-8"))
                return data if isinstance(data, list) else []
        except (OSError, ValueError, TypeError):
            pass
        return []



    def build_error_entry(
        self,
        error_text,
        raw_line="",
        current_track="",
        active_item=None,
        active_error_count=0,
    ):
        urls = re.findall(r"https?://\S+", raw_line)
        url = urls[0].rstrip(")]>,") if urls else ""
        if not url.startswith("https://open.spotify.com/track/"):
            url = ""

        title = "Nieznany tytuł"
        artist = "Nieznany artysta"

        quoted = re.search(r'"([^"]+)"', error_text)
        label = quoted.group(1).strip() if quoted else ""
        if " - " in label:
            artist, title = label.split(" - ", 1)
        elif label:
            title = label
        elif " - " in current_track:
            artist, title = current_track.rsplit(" - ", 1)

        queue_url = active_item.get("url", "") if active_item else ""
        track_index = None

        if active_item:
            tracks = active_item.get("tracks", [])
            track_index = active_item.get("done", 0) + active_error_count
            title_norm = title.strip().casefold()
            artist_norm = artist.strip().casefold()

            for track in tracks:
                if (
                    track.get("title", "").strip().casefold() == title_norm
                    and track.get("artist", "").strip().casefold() == artist_norm
                ):
                    url = track.get("url", "")
                    break

            if not url and current_track:
                current_norm = current_track.casefold()
                for track in tracks:
                    track_label = (
                        f"{track.get('artist','')} - "
                        f"{track.get('title','')}"
                    ).casefold()
                    if track_label == current_norm:
                        artist = track.get("artist", artist)
                        title = track.get("title", title)
                        url = track.get("url", "")
                        break

            if not url and tracks and track_index is not None:
                if track_index < len(tracks):
                    track = tracks[track_index]
                    artist = track.get("artist", artist)
                    title = track.get("title", title)
                    url = track.get("url", "")

            active_error_count += 1

        if not url and active_item and "/track/" in active_item.get("url", ""):
            url = active_item["url"]

        entry = {
            "time": datetime.now().isoformat(timespec="seconds"),
            "status": "error (nie pobrano)",
            "title": title.strip(),
            "artist": artist.strip(),
            "url": url,
            "queue_url": queue_url,
            "track_index": track_index,
            "error": error_text,
        }
        return entry, active_error_count

    def save(self, errors):
        try:
            path = self.errors_file()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(
                    errors or [],
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
        except OSError:
            pass
