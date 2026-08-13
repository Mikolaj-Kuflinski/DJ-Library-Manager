import hashlib
import plistlib
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote


class LibraryExportService:
    """Pure file-export operations for DJ Library Manager."""

    @staticmethod
    def export_m3u8(playlist, output_dir):
        try:
            output_dir = Path(output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            path = output_dir / f"{playlist['name']}.m3u8"

            with path.open("w", encoding="utf-8") as file:
                file.write("#EXTM3U\n")
                for song_path in playlist.get("paths", []):
                    file.write(f"{song_path}\n")

            return path
        except (OSError, KeyError, TypeError):
            return None

    @staticmethod
    def _persistent_id(value):
        return hashlib.md5(
            str(value).encode("utf-8")
        ).hexdigest()[:16].upper()

    def export_djay_pro(self, playlists, song_by_path, output_dir):
        try:
            output_dir = Path(output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            path = output_dir / "DJLM Library.xml"

            tracks = {}
            path_to_id = {}
            next_track_id = 1
            next_playlist_id = 1000

            for playlist in playlists:
                for song_path in playlist.get("paths", []):
                    if not song_path or song_path in path_to_id:
                        continue

                    track_id = next_track_id
                    next_track_id += 1
                    path_to_id[song_path] = track_id

                    p = Path(song_path)
                    song = song_by_path.get(song_path)

                    title = p.stem
                    artist = ""
                    album = ""
                    genre = ""
                    year = None
                    bpm = None

                    if song is not None:
                        title = getattr(song, "title", None) or title
                        artist = getattr(song, "artist", None) or ""
                        album = getattr(song, "album", None) or ""
                        genre = getattr(song, "genre", None) or ""
                        year = getattr(song, "year", None)
                        bpm = getattr(song, "bpm", None)

                    try:
                        size = p.stat().st_size
                    except OSError:
                        size = 0

                    track = {
                        "Track ID": track_id,
                        "Size": size,
                        "Persistent ID": self._persistent_id(song_path),
                        "Track Type": "File",
                        "File Folder Count": -1,
                        "Library Folder Count": -1,
                        "Name": title,
                        "Artist": artist,
                        "Album Artist": artist,
                        "Album": album,
                        "Genre": genre,
                        "Kind": "plik audio",
                        "Location": (
                            "file://localhost/"
                            + quote(
                                str(p).replace("\\", "/"),
                                safe="/:",
                            )
                        ),
                    }

                    if year not in (None, ""):
                        try:
                            track["Year"] = int(year)
                        except (TypeError, ValueError):
                            pass

                    if bpm not in (None, ""):
                        try:
                            track["BPM"] = int(float(bpm))
                        except (TypeError, ValueError):
                            pass

                    tracks[str(track_id)] = track

            playlists_xml = []
            for playlist in playlists:
                items = [
                    {"Track ID": path_to_id[p]}
                    for p in playlist.get("paths", [])
                    if p in path_to_id
                ]
                playlists_xml.append({
                    "Playlist ID": next_playlist_id,
                    "Playlist Persistent ID": self._persistent_id(
                        "playlist:" + playlist["name"]
                    ),
                    "All Items": True,
                    "Visible": True,
                    "Name": playlist["name"],
                    "Playlist Items": items,
                })
                next_playlist_id += 1

            plist = {
                "Major Version": 1,
                "Minor Version": 1,
                "Application Version": "12.13.10.3",
                "Date": datetime.now(timezone.utc)
                .replace(microsecond=0)
                .isoformat(),
                "Features": 5,
                "Show Content Ratings": True,
                "Library Persistent ID": self._persistent_id(
                    "DJLM Library"
                ),
                "Tracks": tracks,
                "Playlists": playlists_xml,
                "Music Folder": "file://localhost/",
            }

            with path.open("wb") as file:
                plistlib.dump(
                    plist,
                    file,
                    fmt=plistlib.FMT_XML,
                    sort_keys=False,
                )

            return path
        except (OSError, KeyError, TypeError, ValueError):
            return None
