"""Small JSON helpers shared by every file-backed store."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Generic, TypeVar

T = TypeVar("T")


def read_json(path: Path, default: Any = None) -> Any:
    """Parsed content of `path`, or `default` if the file is missing or unreadable."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def write_json_atomic(path: Path, data: Any, indent: int | None = 2) -> None:
    """Write through a temporary file so a crash never leaves a half-written file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=indent), encoding="utf-8")
    tmp.replace(path)


class CachedFile(Generic[T]):
    """A hand-edited file parsed once, and re-parsed only when its mtime changes.

    Replaces the old "read and parse the file on every call" pattern: a lookup
    now costs one `stat()` instead of a read + parse.
    """

    def __init__(self, path: Path, parse: Callable[[str], T], default: T):
        self.path = path
        self._parse = parse
        self._default = default
        self._mtime: float | None = None
        self._value: T = default

    def get(self) -> T:
        try:
            mtime = self.path.stat().st_mtime
        except OSError:
            self._mtime, self._value = None, self._default
            return self._value
        if mtime != self._mtime:
            try:
                self._value = self._parse(self.path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                self._value = self._default
            self._mtime = mtime
        return self._value
