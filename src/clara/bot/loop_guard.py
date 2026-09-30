"""Stop Clara and another bot from tagging each other forever.

In each channel, at most `limit` bot messages in a row get an answer; any
message written by a human in that channel resets the count.
"""

from __future__ import annotations

MAX_CONSECUTIVE_BOT_REPLIES = 3


class BotLoopGuard:
    def __init__(self, limit: int = MAX_CONSECUTIVE_BOT_REPLIES):
        self.limit = limit
        self._bot_streaks: dict[int, int] = {}  # channel ID -> bot messages answered in a row

    def human_spoke(self, channel_id: int) -> None:
        self._bot_streaks.pop(channel_id, None)

    def allow_bot_reply(self, channel_id: int) -> bool:
        """Count one more bot message answered; False once the limit is reached."""
        streak = self._bot_streaks.get(channel_id, 0)
        if streak >= self.limit:
            return False
        self._bot_streaks[channel_id] = streak + 1
        return True
