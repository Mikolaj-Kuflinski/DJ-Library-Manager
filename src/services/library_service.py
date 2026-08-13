from pathlib import Path


class LibraryService:
    """Library scanning/loading boundary."""

    def load_from_folder(self, source, fallback_loader=None):
        source = Path(source)
        if not source.exists() or not source.is_dir():
            return []

        try:
            from src.scanner import scan_library
            from src.database_service import save_songs

            songs = scan_library(source)
            if songs:
                save_songs(songs)
            return songs
        except Exception as exc:
            print(
                f"⚠️ Nie udało się zeskanować folderu źródłowego: {exc}"
            )

            if fallback_loader is None:
                return []

            try:
                return [
                    song
                    for song in fallback_loader()
                    if self.path_is_inside(song.path, source)
                ]
            except Exception:
                return []

    @staticmethod
    def path_is_inside(path, folder):
        try:
            Path(path).resolve().relative_to(
                Path(folder).resolve()
            )
            return True
        except (ValueError, OSError):
            return False
