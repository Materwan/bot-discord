"""Facts worth remembering about each channel, saved by the model."""

from __future__ import annotations

from pathlib import Path

from .json_file import read_json, write_json_atomic

MAX_FACTS_PER_CHANNEL = 100


class ChannelMemory:
    def __init__(self, path: Path, max_facts: int = MAX_FACTS_PER_CHANNEL):
        self.path = path
        self.max_facts = max_facts
        self._facts: dict[str, list[str]] = {}
        raw = read_json(path, default={})
        if isinstance(raw, dict):
            for channel_id, facts in raw.items():
                if isinstance(facts, list):
                    # Non-string entries are leftovers of an old chat-log format
                    self._facts[str(channel_id)] = [f for f in facts if isinstance(f, str)]

    def facts(self, channel_id: int) -> list[str]:
        """Facts of a channel, oldest first."""
        return list(self._facts.get(str(channel_id), []))

    def add(self, channel_id: int, fact: str) -> bool:
        """Store a fact. False if it is empty or already known."""
        fact = fact.strip()
        facts = self._facts.setdefault(str(channel_id), [])
        if not fact or fact in facts:
            return False
        facts.append(fact)
        del facts[: -self.max_facts]
        write_json_atomic(self.path, self._facts, indent=None)
        return True
