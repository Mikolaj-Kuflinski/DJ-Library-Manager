from pathlib import Path
from mutagen.easyid3 import EasyID3
from mutagen.mp3 import MP3
from src.database import Song

EasyID3.RegisterTextKey("grouping", "TIT1")


def scan_library(path):
    library = Path(path)

    if not library.exists():
        print("❌ Biblioteka nie istnieje.")
        return []

    print("\nSkanowanie biblioteki...\n")

    songs = []
    files = list(library.rglob("*.mp3"))

    print(f"Znaleziono {len(files)} plików.\n")

    for file in files:
        try:
            audio = EasyID3(file)

            title = audio.get("title", ["Brak"])[0]
            artist = audio.get("artist", ["Brak"])[0]
            album = audio.get("album", ["Brak"])[0]
            grouping = audio.get("grouping", ["Brak"])[0]

            song = Song(
                title=title,
                artist=artist,
                album=album,
                grouping=grouping,
                path=str(file)
            )

            songs.append(song)

            print(f"🎵 {title}")
            print(f"👤 {artist}")
            print(f"💿 {album}")
            print(f"🏷️ {grouping}")
            print()

        except Exception:
            print(file.name)
            print()

    return songs