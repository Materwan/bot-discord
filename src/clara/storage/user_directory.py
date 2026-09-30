"""Display name <-> Discord ID mapping, from a hand-edited JSON file.

The file maps names to IDs (`{"Erwan": 775822432631783445, "Flo": ...}`);
several nicknames may point to the same ID. It is re-read only when it
changes on disk.
"""

from __future__ import annotations

import json
from pathlib import Path

from .json_file import CachedFile


def _parse_names(text: str) -> dict[str, int]:
    data = json.loads(text)
    if not isinstance(data, dict):
        return {}
    names: dict[str, int] = {}
    for name, value in data.items():
        try:
            names[str(name)] = int(value)
        except (TypeError, ValueError):
            continue
    return names


class UserDirectory:
    def __init__(self, path: Path):
        self._file = CachedFile(path, _parse_names, default={})
        self._source: dict[str, int] | None = None
        self._by_lower_name: dict[str, int] = {}
        self._first_name_by_id: dict[int, str] = {}

    def _names(self) -> dict[str, int]:
        names = self._file.get()
        if names is not self._source:  # rebuild the indexes only after a reload
            self._source = names
            self._by_lower_name = {name.lower(): uid for name, uid in names.items()}
            self._first_name_by_id = {}
            for name, uid in names.items():
                self._first_name_by_id.setdefault(uid, name)
        return names

    def names(self) -> list[str]:
        return list(self._names())

    def ids(self) -> set[int]:
        return set(self._names().values())

    def id_for(self, name: str) -> int | None:
        """ID for a name (case-insensitive), or None if unknown."""
        self._names()
        return self._by_lower_name.get(name.strip().lower())

    def name_for(self, user_id: int) -> str | None:
        """First name registered for an ID, or None if unknown."""
        self._names()
        return self._first_name_by_id.get(user_id)
