from pathlib import Path
from mutagen import File as MutagenFile
from mutagen.easyid3 import EasyID3
from src.database import Song

EasyID3.RegisterTextKey("grouping", "TIT1")

AUDIO_EXTENSIONS = {
    ".mp3", ".m4a", ".mp4", ".flac", ".wav",
    ".aac", ".ogg", ".opus", ".wma", ".aiff",
}

def _tag(tags, key, default="Brak"):
    if not tags:
        return default
    value = tags.get(key)
    if value is None:
        return default
    if isinstance(value, (list, tuple)):
        value = value[0] if value else default
    return str(value) if value not in (None, "") else default

def scan_library(path):
    library = Path(path)
    if not library.exists() or not library.is_dir():
        return []

    songs = []
    for file in library.rglob("*"):
        if not file.is_file() or file.suffix.lower() not in AUDIO_EXTENSIONS:
            continue
        try:
            audio = MutagenFile(file, easy=True)
            if audio is None:
                continue
            tags = audio.tags
            songs.append(Song(
                title=_tag(tags, "title"),
                artist=_tag(tags, "artist"),
                album=_tag(tags, "album"),
                grouping=_tag(tags, "grouping"),
                path=str(file),
            ))
        except Exception:
            continue
    return songs
