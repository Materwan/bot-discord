"""Who may talk to the bot (whitelist) and which commands they may run (levels).

Permission scale: 0 (visitor) to `MAX_LEVEL` (owner).

- The owner is always `OWNER_LEVEL` and always allowed to talk: that level is
  never written to disk and `Permissions.set_level` refuses to change it.
- A user missing from the permissions file is level 0.
- Being whitelisted only grants level 0.
"""

from __future__ import annotations

from pathlib import Path

from .json_file import read_json, write_json_atomic

MAX_LEVEL = 5
OWNER_LEVEL = MAX_LEVEL


def _parse_ids(values) -> set[int]:
    return {int(value) for value in values if str(value).isdigit()}


class Whitelist:
    """IDs of the users the bot answers to (the owner is implicitly included)."""

    def __init__(self, path: Path):
        self.path = path
        raw = read_json(path, default=[])
        if isinstance(raw, dict):  # tolerated format: {"ids": [...]}
            raw = raw.get("ids", [])
        self._ids = _parse_ids(raw) if isinstance(raw, list) else set()

    @property
    def ids(self) -> list[int]:
        return sorted(self._ids)

    def __contains__(self, user_id: int) -> bool:
        return user_id in self._ids

    def __len__(self) -> int:
        return len(self._ids)

    def add(self, user_id: int) -> bool:
        """False if the ID was already whitelisted."""
        if user_id in self._ids:
            return False
        self._ids.add(user_id)
        self._save()
        return True

    def remove(self, user_id: int) -> bool:
        """False if the ID was not whitelisted."""
        if user_id not in self._ids:
            return False
        self._ids.discard(user_id)
        self._save()
        return True

    def _save(self) -> None:
        write_json_atomic(self.path, self.ids)


class Permissions:
    """Permission level of each user, stored as `{"<user_id>": <level>}`."""

    def __init__(self, path: Path, owner_id: int):
        self.path = path
        self.owner_id = owner_id
        self._levels: dict[int, int] = {}
        raw = read_json(path, default={})
        if isinstance(raw, dict):
            for key, value in raw.items():
                try:
                    user_id, level = int(key), int(value)
                except (TypeError, ValueError):
                    continue
                if 0 <= level <= MAX_LEVEL and user_id != owner_id:
                    self._levels[user_id] = level

    @property
    def ids(self) -> list[int]:
        """Users with an explicit level (never the owner)."""
        return sorted(self._levels)

    @property
    def entries(self) -> list[tuple[int, int]]:
        """(user_id, level) pairs, highest level first."""
        return sorted(self._levels.items(), key=lambda item: (-item[1], item[0]))

    def is_owner(self, user_id: int | None) -> bool:
        return user_id is not None and user_id == self.owner_id

    def level(self, user_id: int | None) -> int:
        if user_id is None:
            return 0
        if user_id == self.owner_id:
            return OWNER_LEVEL
        return self._levels.get(user_id, 0)

    def set_level(self, user_id: int, level: int) -> bool:
        """False for the owner (immutable). Raises ValueError if out of range."""
        if not 0 <= level <= MAX_LEVEL:
            raise ValueError(f"level out of range (0-{MAX_LEVEL})")
        if self.is_owner(user_id):
            return False
        self._levels[user_id] = level
        write_json_atomic(
            self.path, {str(uid): lvl for uid, lvl in sorted(self._levels.items())}
        )
        return True
