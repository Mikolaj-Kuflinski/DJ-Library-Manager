import json
from datetime import datetime


class SpotifySyncService:
    """Persist playlists watched for Spotify synchronization."""

    SETTING_KEY = "spotify_sync_playlists"

    def __init__(self, settings_service):
        self.settings_service = settings_service

    def load(self, settings):
        raw = (settings or {}).get(self.SETTING_KEY, [])
        if not isinstance(raw, list):
            return []
        result = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            url = str(item.get("url", "")).strip()
            if not url:
                continue
            result.append({
                "url": url,
                "name": str(item.get("name") or "Spotify"),
                "track_urls": list(item.get("track_urls") or []),
                "last_checked": str(item.get("last_checked") or ""),
                "new_count": int(item.get("new_count") or 0),
                "has_updates": bool(item.get("has_updates", False)),
                "track_count": int(item.get("track_count") or 0),
            })
        return result

    def save(self, settings, playlists):
        settings[self.SETTING_KEY] = list(playlists or [])
        self.settings_service.save(settings)

    def snapshot(self, item, tracks):
        item["track_urls"] = [
            str(t.get("url")) for t in tracks
            if isinstance(t, dict) and t.get("url")
        ]
        item["track_count"] = len(tracks)
        item["new_count"] = 0
        item["has_updates"] = False
        item["last_checked"] = datetime.now().isoformat(timespec="seconds")
