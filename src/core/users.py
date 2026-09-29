"""Notes utilisateur + niveau de relation, stockés dans SQLite.

Une note est horodatée et typée :

    notes(id, user_id, kind, text, created_at)
      kind = 'immutable'      -> écrit par le propriétaire (/remember), sacré
      kind = 'model_editable' -> découvert automatiquement, consolidable

    relationships(user_id, value)  -> niveau de relation 0-100

L'ancien `user_notes.json` est importé automatiquement à la première ouverture
puis conservé en sauvegarde (`.bak`) : aucune donnée n'est perdue.
"""

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

from .ranking import rank, tokenize
from .guards import looks_like_instruction

MIN_RELATIONSHIP = 0
MAX_RELATIONSHIP = 100

KIND_IMMUTABLE = "immutable"
KIND_EDITABLE = "model_editable"

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

_SQLITE_HEADER = b"SQLite format 3\x00"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def empty_entry() -> dict:
    """Fiche vierge d'un utilisateur."""
    return {"immutable": [], "model_editable": [], "relationship": 0}


def _normalize(value) -> dict:
    """Ramène une entrée de l'ancien JSON vers la fiche standard."""
    if isinstance(value, list):  # tout ancien format : liste de notes
        return {
            "immutable": [str(v) for v in value],
            "model_editable": [],
            "relationship": 0,
        }
    if not isinstance(value, dict):
        return empty_entry()

    def str_list(raw) -> list[str]:
        return [str(x) for x in raw] if isinstance(raw, list) else []

    try:
        relationship = int(value.get("relationship", 0))
    except (TypeError, ValueError):
        relationship = 0

    return {
        "immutable": str_list(value.get("immutable")),
        "model_editable": str_list(value.get("model_editable")),
        "relationship": max(MIN_RELATIONSHIP, min(MAX_RELATIONSHIP, relationship)),
    }


def _parse_legacy(payload: str) -> dict[str, dict] | None:
    try:
        raw = json.loads(payload)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(raw, dict):
        return None
    entries: dict[str, dict] = {}
    for key, value in raw.items():
        if str(key).isdigit():  # un ID illisible n'est pas importable
            entries[str(key)] = _normalize(value)
    return entries


def _near_duplicate(a: str, b: str) -> bool:
    """Deux notes disant sensiblement la même chose (prudent : jamais de faux positif)."""
    tokens_a, tokens_b = tokenize(a), tokenize(b)
    if not tokens_a or not tokens_b:
        return False
    if tokens_a <= tokens_b or tokens_b <= tokens_a:
        return True  # l'une contient l'autre
    shared = tokens_a & tokens_b
    return len(shared) >= 2 and len(shared) / max(len(tokens_a), len(tokens_b)) >= 0.6


class UserNotes:
    """Ce que le bot sait sur chaque utilisateur, et sa relation avec eux."""

    def __init__(self, path: Path, max_notes: int = 20, legacy_path: Path | None = None):
        self.max_notes = max_notes
        self._lock = threading.RLock()
        self._conn: sqlite3.Connection | None = None
        self._legacy = Path(legacy_path) if legacy_path else None
        self._path = Path(path)

    # ------------------------------------------------------------------
    # Connexion (ouverte à la première requête)
    # ------------------------------------------------------------------
    @property
    def path(self) -> Path:
        return self._path

    @path.setter
    def path(self, value) -> None:
        """Change l'emplacement de la base (les tests en profitent) : fermeture immédiate.

        On perd aussi le lien avec l'ancien JSON : une base redirigée est une base
        de test, elle ne doit jamais importer (ni renommer) le fichier de prod.
        """
        with self._lock:
            self._close()
            self._path = Path(value)
            self._legacy = None

    def _db(self) -> sqlite3.Connection:
        with self._lock:
            if self._conn is None:
                self._open()
            return self._conn

    def _open(self) -> None:
        path = self._path
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = self._take_over_legacy_file(path)

        conn = sqlite3.connect(path, timeout=10, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.executescript(_SCHEMA)
        conn.commit()
        self._conn = conn

        self._import_legacy(payload)

    def _take_over_legacy_file(self, path: Path) -> str | None:
        """Si `path` contient encore l'ancien JSON (et pas une base), on le met de côté."""
        if not path.exists() or _is_sqlite(path):
            return None
        try:
            payload = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return None
        backup = path.with_name(path.name + ".bak")
        try:
            if backup.exists():
                backup.unlink()
            path.replace(backup)
        except OSError:  # on garde au moins le contenu en mémoire
            pass
        return payload

    def _import_legacy(self, payload: str | None) -> None:
        """Importe l'ancien JSON une seule fois (uniquement si la base est vide)."""
        entries = _parse_legacy(payload) if payload else None
        legacy_path = self._legacy
        if not entries and legacy_path and legacy_path.exists() and legacy_path != self._path:
            try:
                entries = _parse_legacy(legacy_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError):
                entries = None
        if not entries:
            return

        conn = self._db()
        if conn.execute("SELECT COUNT(*) FROM notes").fetchone()[0]:
            return  # la base a déjà des données : on n'écrase rien

        for user_id, entry in entries.items():
            created = _now()
            for kind in (KIND_IMMUTABLE, KIND_EDITABLE):
                for text in entry[kind]:
                    conn.execute(
                        "INSERT OR IGNORE INTO notes (user_id, kind, text, created_at) "
                        "VALUES (?, ?, ?, ?)",
                        (int(user_id), kind, text, created),
                    )
            if entry["relationship"]:
                conn.execute(
                    "INSERT OR IGNORE INTO relationships (user_id, value) VALUES (?, ?)",
                    (int(user_id), entry["relationship"]),
                )
        conn.commit()

        # L'ancien fichier devient une sauvegarde explicite
        if legacy_path and legacy_path.exists():
            try:
                legacy_path.replace(legacy_path.with_name(legacy_path.name + ".bak"))
            except OSError:
                pass

    def _close(self) -> None:
        if self._conn is not None:
            try:
                self._conn.commit()
                self._conn.close()
            finally:
                self._conn = None

    def close(self) -> None:
        with self._lock:
            self._close()

    # ------------------------------------------------------------------
    # Lecture
    # ------------------------------------------------------------------
    def _rows(self, user_id: int) -> list[sqlite3.Row]:
        return self._db().execute(
            "SELECT kind, text FROM notes WHERE user_id = ? "
            "ORDER BY kind, created_at, id",
            (int(user_id),),
        ).fetchall()

    def get(self, user_id: int) -> dict:
        """Copie de la fiche d'un utilisateur (valeurs par défaut si inconnu)."""
        rows = self._rows(user_id)
        entry = {
            KIND_IMMUTABLE: [r["text"] for r in rows if r["kind"] == KIND_IMMUTABLE],
            KIND_EDITABLE: [r["text"] for r in rows if r["kind"] == KIND_EDITABLE],
            "relationship": self.relationship(user_id),
        }
        return entry

    def notes(self, user_id: int) -> list[str]:
        """Toutes les notes connues sur un utilisateur (immuables puis éditables)."""
        rows = self._rows(user_id)
        return (
            [r["text"] for r in rows if r["kind"] == KIND_IMMUTABLE]
            + [r["text"] for r in rows if r["kind"] == KIND_EDITABLE]
        )

    def relevant(self, user_id: int, query: str = "", limit: int = 15) -> list[str]:
        """Les notes à injecter dans le prompt : immuables d'abord, éditables triées
        par pertinence pour `query` puis par récence, le tout plafonné."""
        rows = self._rows(user_id)
        immutable = [r["text"] for r in rows if r["kind"] == KIND_IMMUTABLE]
        editable = [r["text"] for r in rows if r["kind"] == KIND_EDITABLE]
        # Le plafond ne doit jamais manger toutes les notes éditables
        editable_budget = max(limit - len(immutable), limit // 2)
        return immutable + rank(editable, query, limit=editable_budget)

    def relationship(self, user_id: int) -> int:
        """Niveau de relation 0-100 avec un utilisateur."""
        row = self._db().execute(
            "SELECT value FROM relationships WHERE user_id = ?", (int(user_id),)
        ).fetchone()
        return row["value"] if row else MIN_RELATIONSHIP

    def ids(self) -> list[int]:
        """Tous les utilisateurs qui ont au moins une note ou une relation."""
        rows = self._db().execute(
            "SELECT user_id FROM notes "
            "UNION SELECT user_id FROM relationships"
        ).fetchall()
        return sorted(int(r[0]) for r in rows)

    # ------------------------------------------------------------------
    # Écriture
    # ------------------------------------------------------------------
    def _insert(self, user_id: int, kind: str, note: str) -> bool:
        note = (note or "").strip()
        if not note:
            return False
        with self._lock:
            conn = self._db()
            try:
                conn.execute(
                    "INSERT INTO notes (user_id, kind, text, created_at) VALUES (?, ?, ?, ?)",
                    (int(user_id), kind, note, _now()),
                )
            except sqlite3.IntegrityError:
                return False  # doublon exact : rien à écrire, donc rien à sauvegarder
            conn.commit()
            self._trim(int(user_id), kind)
            return True

    def add(self, user_id: int, note: str) -> bool:
        """Ajoute une note éditable par le modèle (faits découverts automatiquement).

        Un « fait » qui est en réalité un ordre envers le bot est refusé ici même :
        c'est le seul point d'entrée des écritures automatiques. `/remember` passe
        par `add_immutable` et n'est pas filtré (c'est le propriétaire).
        """
        if looks_like_instruction(note):
            return False
        return self._insert(user_id, KIND_EDITABLE, note)

    def add_immutable(self, user_id: int, note: str) -> bool:
        """Ajoute une note du propriétaire (le modèle ne peut pas l'effacer)."""
        return self._insert(user_id, KIND_IMMUTABLE, note)

    def _trim(self, user_id: int, kind: str) -> None:
        """Plafonne une catégorie : on consolide d'abord, puis on retire la plus ancienne."""
        conn = self._db()

        def count() -> int:
            return conn.execute(
                "SELECT COUNT(*) FROM notes WHERE user_id = ? AND kind = ?",
                (user_id, kind),
            ).fetchone()[0]

        if count() <= self.max_notes:
            return
        if kind == KIND_EDITABLE:
            self.consolidate(user_id)
        overflow = count() - self.max_notes
        if overflow > 0:
            conn.execute(
                "DELETE FROM notes WHERE id IN ("
                "  SELECT id FROM notes WHERE user_id = ? AND kind = ?"
                "  ORDER BY created_at, id LIMIT ?)",
                (user_id, kind, overflow),
            )
            conn.commit()

    def consolidate(self, user_id: int | None = None) -> int:
        """Fusionne les notes éditables quasi identiques (garde la plus détaillée).

        Les notes immuables ne sont jamais touchées : ce sont les mots du
        propriétaire. Retourne le nombre de notes fusionnées.
        """
        with self._lock:
            conn = self._db()
            targets = [int(user_id)] if user_id is not None else self.ids()
            removed = 0
            for uid in targets:
                rows = conn.execute(
                    "SELECT id, text FROM notes WHERE user_id = ? AND kind = ? "
                    "ORDER BY created_at, id",
                    (uid, KIND_EDITABLE),
                ).fetchall()

                kept: list[tuple[int, str]] = []
                drop: list[int] = []
                updates: dict[int, str] = {}
                for row in rows:
                    text = row["text"]
                    for index, (kept_id, kept_text) in enumerate(kept):
                        if _near_duplicate(text, kept_text):
                            if len(text) > len(kept_text):
                                updates[kept_id] = text
                                kept[index] = (kept_id, text)
                            drop.append(row["id"])
                            break
                    else:
                        kept.append((row["id"], text))

                for note_id in drop:
                    conn.execute("DELETE FROM notes WHERE id = ?", (note_id,))
                for note_id, text in updates.items():
                    conn.execute("UPDATE notes SET text = ? WHERE id = ?", (text, note_id))
                removed += len(drop)

            if removed:
                conn.commit()
            return removed

    def clear(self, user_id: int) -> None:
        """Oublie tout : les deux listes de notes et le niveau de relation."""
        with self._lock:
            conn = self._db()
            conn.execute("DELETE FROM notes WHERE user_id = ?", (int(user_id),))
            conn.execute("DELETE FROM relationships WHERE user_id = ?", (int(user_id),))
            conn.commit()

    def set_relationship(self, user_id: int, value: int) -> int:
        """Fixe le niveau de relation (borné entre 0 et 100)."""
        value = max(MIN_RELATIONSHIP, min(MAX_RELATIONSHIP, int(value)))
        with self._lock:
            conn = self._db()
            if value == MIN_RELATIONSHIP:
                conn.execute(
                    "DELETE FROM relationships WHERE user_id = ?", (int(user_id),)
                )
            else:
                conn.execute(
                    "INSERT INTO relationships (user_id, value) VALUES (?, ?) "
                    "ON CONFLICT(user_id) DO UPDATE SET value = excluded.value",
                    (int(user_id), value),
                )
            conn.commit()
        return value

    def adjust_relationship(self, user_id: int, delta: int) -> int:
        """Fait évoluer le niveau de relation (négatif si l'utilisateur parle mal)."""
        return self.set_relationship(user_id, self.relationship(user_id) + delta)


def _is_sqlite(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            return handle.read(len(_SQLITE_HEADER)) == _SQLITE_HEADER
    except OSError:
        return False
