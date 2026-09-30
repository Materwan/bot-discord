"""What the bot knows about each user, and its relationship with them (SQLite).

    notes(id, user_id, kind, text, created_at)
        kind = 'immutable'      -> PERMANENT: written with /remember, never altered
        kind = 'model_editable' -> LEARNED: discovered automatically, merged and trimmed
    relationships(user_id, value) -> relationship score 0-100 (absent = 0)

The connection is opened once and used from the event loop thread only.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

from ..analysis.injection_guard import looks_like_instruction
from ..analysis.ranking import rank, tokenize

MIN_RELATIONSHIP = 0
MAX_RELATIONSHIP = 100

_SCHEMA = """
CREATE TABLE IF NOT EXISTS notes (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL,
    kind       TEXT    NOT NULL,
    text       TEXT    NOT NULL,
    created_at TEXT    NOT NULL,
    UNIQUE (user_id, kind, text)
);
CREATE INDEX IF NOT EXISTS idx_notes_user ON notes (user_id, kind);
CREATE TABLE IF NOT EXISTS relationships (
    user_id INTEGER PRIMARY KEY,
    value   INTEGER NOT NULL DEFAULT 0
);
"""


class NoteKind(str, Enum):
    # Values are the ones stored in the database
    PERMANENT = "immutable"
    LEARNED = "model_editable"


def clamp_relationship(value: int) -> int:
    return max(MIN_RELATIONSHIP, min(MAX_RELATIONSHIP, int(value)))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _near_duplicate(a: str, b: str) -> bool:
    """Two notes saying roughly the same thing (cautious: no false positives)."""
    tokens_a, tokens_b = tokenize(a), tokenize(b)
    if not tokens_a or not tokens_b:
        return False
    if tokens_a <= tokens_b or tokens_b <= tokens_a:
        return True  # one contains the other
    shared = tokens_a & tokens_b
    return len(shared) >= 2 and len(shared) / max(len(tokens_a), len(tokens_b)) >= 0.6


class UserNotes:
    def __init__(self, path: Path, max_notes_per_kind: int = 20):
        self.path = path
        self.max_notes_per_kind = max_notes_per_kind
        path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path, timeout=10, check_same_thread=False)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.executescript(_SCHEMA)
        self._db.commit()

    def close(self) -> None:
        self._db.commit()
        self._db.close()

    # ------------------------------------------------------------------
    # Reading
    # ------------------------------------------------------------------
    def notes_by_kind(self, user_id: int) -> dict[NoteKind, list[str]]:
        """Notes of a user grouped by kind, oldest first."""
        grouped: dict[NoteKind, list[str]] = {NoteKind.PERMANENT: [], NoteKind.LEARNED: []}
        rows = self._db.execute(
            "SELECT kind, text FROM notes WHERE user_id = ? ORDER BY created_at, id",
            (user_id,),
        )
        for kind, text in rows:
            grouped[NoteKind(kind)].append(text)
        return grouped

    def notes(self, user_id: int) -> list[str]:
        """All notes of a user: permanent ones first, then learned ones."""
        grouped = self.notes_by_kind(user_id)
        return grouped[NoteKind.PERMANENT] + grouped[NoteKind.LEARNED]

    def relevant_notes(self, user_id: int, query: str = "", limit: int = 15) -> list[str]:
        """Notes worth injecting in a prompt.

        Permanent notes are always included; learned notes are ranked by
        relevance to `query` (then recency) and capped, but never to fewer
        than half of `limit`.
        """
        grouped = self.notes_by_kind(user_id)
        permanent = grouped[NoteKind.PERMANENT]
        learned_budget = max(limit - len(permanent), limit // 2)
        # Reversed so that, among equally relevant notes, the newest wins
        learned = rank(grouped[NoteKind.LEARNED][::-1], query, limit=learned_budget)
        return permanent + learned

    def relationship(self, user_id: int) -> int:
        row = self._db.execute(
            "SELECT value FROM relationships WHERE user_id = ?", (user_id,)
        ).fetchone()
        return row[0] if row else MIN_RELATIONSHIP

    def user_ids(self) -> list[int]:
        """Every user with at least one note or a relationship."""
        rows = self._db.execute(
            "SELECT user_id FROM notes UNION SELECT user_id FROM relationships"
        )
        return sorted(row[0] for row in rows)

    # ------------------------------------------------------------------
    # Writing
    # ------------------------------------------------------------------
    def add_learned(self, user_id: int, note: str) -> bool:
        """Store an automatically discovered fact.

        This is the single entry point of automatic writes, so orders
        disguised as facts are rejected here. False if nothing was stored.
        """
        if looks_like_instruction(note):
            return False
        return self._insert(user_id, NoteKind.LEARNED, note)

    def add_permanent(self, user_id: int, note: str) -> bool:
        """Store a note the model can never merge or drop by itself."""
        return self._insert(user_id, NoteKind.PERMANENT, note)

    def _insert(self, user_id: int, kind: NoteKind, note: str) -> bool:
        note = (note or "").strip()
        if not note:
            return False
        try:
            self._db.execute(
                "INSERT INTO notes (user_id, kind, text, created_at) VALUES (?, ?, ?, ?)",
                (user_id, kind.value, note, _now()),
            )
        except sqlite3.IntegrityError:
            return False  # exact duplicate
        self._trim(user_id, kind)
        self._db.commit()
        return True

    def _count(self, user_id: int, kind: NoteKind) -> int:
        return self._db.execute(
            "SELECT COUNT(*) FROM notes WHERE user_id = ? AND kind = ?", (user_id, kind.value)
        ).fetchone()[0]

    def _trim(self, user_id: int, kind: NoteKind) -> None:
        """Enforce the cap: merge near-duplicates first, then drop the oldest notes."""
        if self._count(user_id, kind) <= self.max_notes_per_kind:
            return
        if kind is NoteKind.LEARNED:
            self._merge_duplicates(user_id)
        overflow = self._count(user_id, kind) - self.max_notes_per_kind
        if overflow > 0:
            self._db.execute(
                "DELETE FROM notes WHERE id IN ("
                "  SELECT id FROM notes WHERE user_id = ? AND kind = ?"
                "  ORDER BY created_at, id LIMIT ?)",
                (user_id, kind.value, overflow),
            )

    def consolidate(self, user_id: int | None = None) -> int:
        """Merge near-duplicate learned notes (keeping the most detailed one).

        Permanent notes are never touched. Returns the number of notes removed.
        """
        targets = [user_id] if user_id is not None else self.user_ids()
        removed = sum(self._merge_duplicates(uid) for uid in targets)
        self._db.commit()
        return removed

    def _merge_duplicates(self, user_id: int) -> int:
        rows = self._db.execute(
            "SELECT id, text FROM notes WHERE user_id = ? AND kind = ? ORDER BY created_at, id",
            (user_id, NoteKind.LEARNED.value),
        ).fetchall()

        kept: list[tuple[int, str]] = []
        dropped_ids: list[int] = []
        rewritten: dict[int, str] = {}
        for note_id, text in rows:
            for index, (kept_id, kept_text) in enumerate(kept):
                if _near_duplicate(text, kept_text):
                    if len(text) > len(kept_text):
                        rewritten[kept_id] = text
                        kept[index] = (kept_id, text)
                    dropped_ids.append(note_id)
                    break
            else:
                kept.append((note_id, text))

        # Delete first: a rewritten text may equal one of the dropped rows (UNIQUE)
        self._db.executemany("DELETE FROM notes WHERE id = ?", [(i,) for i in dropped_ids])
        self._db.executemany(
            "UPDATE notes SET text = ? WHERE id = ?",
            [(text, note_id) for note_id, text in rewritten.items()],
        )
        return len(dropped_ids)

    def forget(self, user_id: int) -> None:
        """Erase everything about a user: both kinds of notes and the relationship."""
        self._db.execute("DELETE FROM notes WHERE user_id = ?", (user_id,))
        self._db.execute("DELETE FROM relationships WHERE user_id = ?", (user_id,))
        self._db.commit()

    def set_relationship(self, user_id: int, value: int) -> int:
        """Set the relationship score (clamped to 0-100) and return it."""
        value = clamp_relationship(value)
        if value == MIN_RELATIONSHIP:
            self._db.execute("DELETE FROM relationships WHERE user_id = ?", (user_id,))
        else:
            self._db.execute(
                "INSERT INTO relationships (user_id, value) VALUES (?, ?) "
                "ON CONFLICT(user_id) DO UPDATE SET value = excluded.value",
                (user_id, value),
            )
        self._db.commit()
        return value

    def adjust_relationship(self, user_id: int, delta: int) -> int:
        return self.set_relationship(user_id, self.relationship(user_id) + delta)
