"""Append-only JSONL event log, and token statistics built from it."""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Iterator


class EventLog:
    """One JSON object per line: `{"timestamp": ..., "event": ..., **fields}`."""

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def write(self, event: str, **fields) -> None:
        entry = {"timestamp": datetime.now(timezone.utc).isoformat(), "event": event, **fields}
        line = json.dumps(entry, ensure_ascii=False) + "\n"
        with self._lock, self.path.open("a", encoding="utf-8") as file:
            file.write(line)

    def read(self, event: str | None = None) -> Iterator[dict]:
        """Stream the logged entries (optionally of one event type), skipping bad lines."""
        try:
            file = self.path.open(encoding="utf-8")
        except FileNotFoundError:
            return
        with file:
            for line in file:
                try:
                    entry = json.loads(line)
                except ValueError:
                    continue
                if event is None or entry.get("event") == event:
                    yield entry


@dataclass
class TokenStats:
    """Requests and tokens used, for the current session or rebuilt from the log."""

    # None when rebuilt from the log (no session start)
    started_at: float | None = field(default_factory=time.time)
    requests: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    @property
    def minutes_elapsed(self) -> float | None:
        return None if self.started_at is None else (time.time() - self.started_at) / 60

    def add(self, prompt_tokens: int, completion_tokens: int) -> None:
        self.requests += 1
        self.prompt_tokens += prompt_tokens
        self.completion_tokens += completion_tokens

    @classmethod
    def from_entries(cls, entries: Iterable[dict]) -> TokenStats:
        """Sum the tokens of logged "message" events."""
        stats = cls(started_at=None)
        for entry in entries:
            stats.add(entry.get("prompt_tokens") or 0, entry.get("completion_tokens") or 0)
        return stats
