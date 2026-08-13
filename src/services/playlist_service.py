import os
from pathlib import Path

class PlaylistService:
    """Domain operations on playlist data.

    This class deliberately knows nothing about Qt, dialogs, widgets,
    files, or presentation. It only mutates playlist structures.
    """



    @staticmethod
    def normalize_path(path):
        if not path:
            return ""
        try:
            return os.path.normcase(
                os.path.normpath(str(Path(path).resolve()))
            )
        except Exception:
            return os.path.normcase(os.path.normpath(str(path)))

    @classmethod
    def find_song(cls, path, songs, song_by_path):
        key = cls.normalize_path(path)
        song = song_by_path.get(key)
        if song is not None:
            return song

        raw = str(path or "")
        raw_normalized = os.path.normcase(os.path.normpath(raw))
        for candidate in songs:
            candidate_path = str(candidate.path)
            if cls.normalize_path(candidate_path) == key:
                return candidate
            if os.path.normcase(
                os.path.normpath(candidate_path)
            ) == raw_normalized:
                return candidate
        return None

    @staticmethod
    def find_index(playlists, name, exclude_index=-1):
        target = (name or "").strip().lower()
        for index, playlist in enumerate(playlists):
            if index == exclude_index:
                continue
            if playlist.get("name", "").strip().lower() == target:
                return index
        return -1

    @staticmethod
    def rename(
        playlists,
        index,
        new_name,
        folder_map=None,
        generated_map=None,
    ):
        old_name = playlists[index]["name"]
        playlists[index]["name"] = new_name

        if folder_map is not None:
            old_folders = folder_map.pop(old_name, [])
            if isinstance(old_folders, str):
                old_folders = [old_folders] if old_folders else []
            if old_folders:
                folder_map[new_name] = list(old_folders)

        if generated_map is not None and old_name in generated_map:
            generated_map[new_name] = generated_map.pop(old_name)

    @staticmethod
    def delete(
        playlists,
        index,
        folder_map=None,
        generated_map=None,
    ):
        name = playlists[index]["name"]
        del playlists[index]

        if folder_map is not None:
            folder_map.pop(name, None)

        if generated_map is not None:
            generated_map.pop(name, None)

    @staticmethod
    def add_paths(playlists, index, paths):
        playlist = playlists[index]
        existing = set(playlist.get("paths", []))
        for path in paths or []:
            if path not in existing:
                playlist.setdefault("paths", []).append(path)
                existing.add(path)

    @staticmethod
    def remove_paths(playlists, index, paths):
        remove = set(paths or [])
        playlist = playlists[index]
        playlist["paths"] = [
            path for path in playlist.get("paths", [])
            if path not in remove
        ]

    @staticmethod
    def set_paths(playlists, index, paths):
        playlists[index]["paths"] = list(paths or [])
