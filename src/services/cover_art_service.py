from pathlib import Path


class CoverArtService:
    """Reads embedded cover art from common audio formats using Mutagen."""

    def __init__(self):
        self._cache = {}

    def get_cover_bytes(self, path):
        if not path:
            return None

        try:
            file_path = Path(path)
            stat = file_path.stat()
            key = (str(file_path.resolve()).lower(), stat.st_mtime_ns, stat.st_size)
        except (OSError, ValueError):
            return None

        cached = self._cache.get(key)
        if cached is not None:
            return cached

        # Drop older cache entries for the same file.
        prefix = key[0]
        for old_key in list(self._cache):
            if old_key[0] == prefix and old_key != key:
                self._cache.pop(old_key, None)

        try:
            from mutagen import File
            audio = File(str(file_path))
        except Exception:
            self._cache[key] = None
            return None

        cover = self._extract_cover(audio)
        self._cache[key] = cover
        return cover

    @staticmethod
    def _extract_cover(audio):
        if audio is None:
            return None

        # FLAC / Ogg FLAC / other formats exposing pictures directly.
        pictures = getattr(audio, "pictures", None)
        if pictures:
            picture = pictures[0]
            data = getattr(picture, "data", None)
            if data:
                return bytes(data)

        tags = getattr(audio, "tags", None)
        if not tags:
            return None

        # MP3 / ID3.
        try:
            apic_items = tags.getall("APIC")
        except (AttributeError, TypeError):
            apic_items = []
        if apic_items:
            data = getattr(apic_items[0], "data", None)
            if data:
                return bytes(data)

        # MP4 / M4A.
        try:
            covr = tags.get("covr")
        except AttributeError:
            covr = None
        if covr:
            data = covr[0]
            if hasattr(data, "getvalue"):
                data = data.getvalue()
            if data:
                return bytes(data)

        return None

    def clear_cache(self):
        self._cache.clear()
