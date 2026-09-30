"""The last N exchanges (question + answer) of each channel.

Unlike `ChannelMemory` (durable facts), this is short-term conversation
context: the oldest exchange is dropped once `max_entries` is reached.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from .json_file import read_json, write_json_atomic

MAX_AUTHOR_LENGTH = 80
MAX_TEXT_LENGTH = 300


@dataclass(frozen=True)
class Exchange:
    author: str
    prompt: str
    reply: str


class ChannelHistory:
    def __init__(self, path: Path, max_entries: int = 20):
        self.path = path
        self.max_entries = max(1, max_entries)
        self._exchanges: dict[str, list[Exchange]] = {}
        raw = read_json(path, default={})
        if isinstance(raw, dict):
            for channel_id, entries in raw.items():
                if isinstance(entries, list):
                    self._exchanges[str(channel_id)] = [
                        Exchange(
                            str(entry.get("author", "?")),
                            str(entry.get("prompt", "")),
                            str(entry.get("reply", "")),
                        )
                        for entry in entries
                        if isinstance(entry, dict)
                    ][-self.max_entries :]

    def exchanges(self, channel_id: int) -> list[Exchange]:
        """Exchanges of a channel, oldest first."""
        return list(self._exchanges.get(str(channel_id), []))

    def add(self, channel_id: int, author: str, prompt: str, reply: str) -> None:
        if not prompt and not reply:
            return
        exchange = Exchange(
            author[:MAX_AUTHOR_LENGTH], prompt[:MAX_TEXT_LENGTH], reply[:MAX_TEXT_LENGTH]
        )
        entries = self._exchanges.setdefault(str(channel_id), [])
        entries.append(exchange)
        del entries[: -self.max_entries]
        self._save()

    def clear(self, channel_id: int) -> None:
        if self._exchanges.pop(str(channel_id), None) is not None:
            self._save()

    def _save(self) -> None:
        data = {
            channel_id: [asdict(exchange) for exchange in entries]
            for channel_id, entries in self._exchanges.items()
        }
        write_json_atomic(self.path, data)
