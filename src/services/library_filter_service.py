class LibraryFilterService:
    """Pure library filtering logic, independent from Qt widgets."""

    def filter_songs(
        self,
        songs,
        search_text="",
        category="",
        tag="",
        tag_service=None,
    ):
        search_text = (search_text or "").strip().lower()
        result = []

        for song in songs:
            title = str(getattr(song, "title", "") or "").lower()
            artist = str(getattr(song, "artist", "") or "").lower()

            if search_text and (
                search_text not in title
                and search_text not in artist
            ):
                continue

            if category and tag:
                if tag_service is None:
                    continue
                grouping = tag_service.read_grouping(song.path)
                tags = tag_service.parse_grouping(grouping)
                if tag not in tags.get(category, []):
                    continue

            result.append(song)

        return result
