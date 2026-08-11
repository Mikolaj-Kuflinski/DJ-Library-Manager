import json
from pathlib import Path

ROOT = Path(__file__).parent.parent
PLAYLISTS_FILE = ROOT / "playlists.json"


def load_playlists():
    if not PLAYLISTS_FILE.exists():
        return []
    try:
        with open(PLAYLISTS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            return []
        return data
    except (OSError, json.JSONDecodeError):
        return []


def save_playlists(playlists):
    tmp = PLAYLISTS_FILE.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(playlists, f, ensure_ascii=False, indent=2)
    tmp.replace(PLAYLISTS_FILE)
