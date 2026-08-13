class SpotifyMetadataService:
    """Pure parsing helpers for spotDL Spotify metadata."""

    TRACK_PREFIX = "https://open.spotify.com/track/"

    def extract_tracks(self, payload):
        tracks = []
        seen = set()

        def add_song(value):
            if not isinstance(value, dict):
                return

            url = value.get("url")
            if not (
                isinstance(url, str)
                and url.startswith(self.TRACK_PREFIX)
            ):
                return
            if url in seen:
                return

            artists = value.get("artists") or value.get("artist") or []
            if isinstance(artists, list):
                names = []
                for artist in artists:
                    if isinstance(artist, dict):
                        names.append(str(artist.get("name", "")))
                    else:
                        names.append(str(artist))
                artist_text = ", ".join(x for x in names if x)
            else:
                artist_text = str(artists)

            tracks.append({
                "url": url,
                "title": str(
                    value.get("name")
                    or value.get("title")
                    or "Nieznany tytuł"
                ),
                "artist": artist_text or "Nieznany artysta",
                "list_name": value.get("list_name"),
                "list_url": value.get("list_url"),
                "list_position": value.get("list_position"),
                "list_length": value.get("list_length"),
                "album_name": value.get("album_name"),
            })
            seen.add(url)

        def walk(value):
            if isinstance(value, dict):
                add_song(value)
                for child in value.values():
                    walk(child)
            elif isinstance(value, list):
                for child in value:
                    walk(child)

        walk(payload)
        return tracks

    def extract_collection_name(self, payload):
        def walk(value):
            if isinstance(value, dict):
                name = value.get("list_name")
                url = value.get("list_url")
                if isinstance(name, str) and name.strip():
                    return name.strip(), url
                for child in value.values():
                    found = walk(child)
                    if found:
                        return found
            elif isinstance(value, list):
                for child in value:
                    found = walk(child)
                    if found:
                        return found
            return None

        return walk(payload)
