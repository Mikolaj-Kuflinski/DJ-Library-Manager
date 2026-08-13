class SpotifyQueueService:
    """State helpers for the Spotify download queue."""

    def add(self, queue, item):
        if any(entry.get("url") == item.get("url") for entry in queue):
            return False
        queue.append(item)
        return True

    def remove(self, queue, index):
        if not (0 <= index < len(queue)):
            return None
        return queue.pop(index)

    def totals(self, queue, active_index):
        current_remaining = 0
        future_total = 0
        future_unknown = 0
        for index, item in enumerate(queue):
            count = item.get("count")
            remaining = max(0, (count or 0) - item.get("done", 0))
            if index == active_index:
                current_remaining = remaining
            elif index > active_index:
                if count is None:
                    future_unknown += 1
                else:
                    future_total += remaining
        return current_remaining, future_total, future_unknown
