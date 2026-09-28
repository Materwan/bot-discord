import json
from pathlib import Path


class UserNotes:
    """Choses que chaque utilisateur a demandé au bot de retenir, persistées sur disque."""

    def __init__(self, path: Path, max_notes: int = 20):
        self.path = path
        self.max_notes = max_notes
        try:
            self._data: dict[str, list[str]] = json.loads(
                path.read_text(encoding="utf-8")
            )
        except (FileNotFoundError, json.JSONDecodeError):
            self._data = {}

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        tmp.replace(self.path)

    def get(self, user_id: int) -> list[str]:
        return list(self._data.get(str(user_id), []))

    def add(self, user_id: int, note: str) -> None:
        notes = self._data.setdefault(str(user_id), [])
        notes.append(note)
        del notes[: -self.max_notes]  # on garde les plus récentes
        self._save()

    def clear(self, user_id: int) -> None:
        self._data.pop(str(user_id), None)
        self._save()
