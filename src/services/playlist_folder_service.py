class PlaylistFolderService:
    """Domain operations for user-created playlist folders."""

    FOLDER_KEY = "__folders__"

    @classmethod
    def folders(cls, folder_map):
        return list(folder_map.get(cls.FOLDER_KEY, []))

    @classmethod
    def can_create(cls, folder_map, name):
        name = (name or "").strip()
        if not name:
            return False

        wanted = name.casefold().strip("/")
        for folder in cls.folders(folder_map):
            if str(folder).strip().casefold().strip("/") == wanted:
                return False
        return True

    @classmethod
    def create(cls, folder_map, name):
        name = name.strip()
        folder_map.setdefault(cls.FOLDER_KEY, [])
        if cls.can_create(folder_map, name):
            folder_map[cls.FOLDER_KEY].append(name)
        return name

    @classmethod
    def delete(cls, folder_map, name):
        name = (name or "").strip()
        if not name:
            return

        prefix = name.rstrip("/") + "/"

        for playlist_name, folder in list(folder_map.items()):
            if playlist_name == cls.FOLDER_KEY:
                continue

            values = [folder] if isinstance(folder, str) else list(folder or [])
            kept = [
                value for value in values
                if value != name and not str(value).startswith(prefix)
            ]
            folder_map[playlist_name] = kept

        folders = folder_map.get(cls.FOLDER_KEY, [])
        folder_map[cls.FOLDER_KEY] = [
            folder for folder in folders
            if folder != name
            and not str(folder).startswith(prefix)
        ]

    @classmethod
    def rename(cls, folder_map, old_name, new_name):
        old_name = (old_name or "").strip()
        new_name = (new_name or "").strip()
        if (
            not old_name
            or not new_name
            or old_name == new_name
            or not cls.can_create(folder_map, new_name)
        ):
            return False

        old_prefix = old_name.rstrip("/") + "/"
        new_prefix = new_name.rstrip("/") + "/"

        for playlist_name, folder in list(folder_map.items()):
            if playlist_name == cls.FOLDER_KEY:
                continue

            values = [folder] if isinstance(folder, str) else list(folder or [])
            updated = []
            for value in values:
                if value == old_name:
                    updated.append(new_name)
                elif str(value).startswith(old_prefix):
                    updated.append(
                        new_prefix + str(value)[len(old_prefix):]
                    )
                else:
                    updated.append(value)
            folder_map[playlist_name] = updated

        folders = folder_map.get(cls.FOLDER_KEY, [])
        folder_map[cls.FOLDER_KEY] = [
            (
                new_name
                if folder == old_name
                else new_prefix + str(folder)[len(old_prefix):]
                if str(folder).startswith(old_prefix)
                else folder
            )
            for folder in folders
        ]
        return True
