class HistoryService:
    """Pure undo/redo data operations for tags and playlists."""

    def __init__(self, tag_service, playlist_storage_service):
        self.tag_service = tag_service
        self.playlist_storage_service = playlist_storage_service

    @staticmethod
    def snapshot_playlists(playlists):
        return [
            {
                "name": playlist["name"],
                "paths": list(playlist.get("paths", [])),
            }
            for playlist in playlists
        ]

    def restore_playlist_snapshot(self, snapshot):
        playlists = [
            {
                "name": playlist["name"],
                "paths": list(playlist.get("paths", [])),
            }
            for playlist in snapshot
        ]
        self.playlist_storage_service.save(playlists)
        return playlists

    def apply_tag_history(self, changes, undoing, update_song):
        for song, before, after in changes:
            grouping = before if undoing else after
            tags = self.tag_service.parse_grouping(grouping)
            saved = self.tag_service.save_grouping(song.path, tags)
            song.grouping = saved
            update_song(song)
