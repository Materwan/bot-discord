import json
from pathlib import Path

MIN_RELATIONSHIP = 0
MAX_RELATIONSHIP = 100


def empty_entry() -> dict:
    """Fiche vierge d'un utilisateur."""
    return {"immutable": [], "model_editable": [], "relationship": 0}


def _normalize(value) -> dict:
    """Ramène n'importe quel format rencontré sur disque vers la fiche standard."""
    if isinstance(value, list):  # ancien format : liste de notes
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


class UserNotes:
    """Ce que le bot sait sur chaque utilisateur, persisté dans user_notes.json.

    Fiche par utilisateur :
        {
          "immutable":       [notes écrites par le propriétaire, que le modèle ne peut pas effacer],
          "model_editable":  [notes ajoutées automatiquement par le modèle],
          "relationship":    niveau de relation entre 0 (mauvaise) et 100 (excellente)
        }
    """

    def __init__(self, path: Path, max_notes: int = 20):
        self.path = path
        self.max_notes = max_notes
        self._data: dict[str, dict] = {}
        self._load()

    # ------------------------------------------------------------------
    # Persistance
    # ------------------------------------------------------------------
    def _load(self) -> None:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return
        if not isinstance(raw, dict):
            return
        for user_id, value in raw.items():
            self._data[str(user_id)] = _normalize(value)

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=4), encoding="utf-8"
        )
        tmp.replace(self.path)

    # ------------------------------------------------------------------
    # Lecture
    # ------------------------------------------------------------------
    def get(self, user_id: int) -> dict:
        """Copie de la fiche d'un utilisateur (liste vide / 0 si inconnu)."""
        entry = self._data.get(str(user_id))
        if entry is None:
            return empty_entry()
        return {
            "immutable": list(entry["immutable"]),
            "model_editable": list(entry["model_editable"]),
            "relationship": entry["relationship"],
        }

    def notes(self, user_id: int) -> list[str]:
        """Toutes les notes connues sur un utilisateur (immuables + éditables)."""
        entry = self._data.get(str(user_id))
        if entry is None:
            return []
        return list(entry["immutable"]) + list(entry["model_editable"])

    def relationship(self, user_id: int) -> int:
        """Niveau de relation 0-100 avec un utilisateur."""
        return self._data.get(str(user_id), {}).get("relationship", 0)

    def ids(self) -> list[int]:
        return sorted(int(k) for k in self._data)

    # ------------------------------------------------------------------
    # Écriture
    # ------------------------------------------------------------------
    def _entry(self, user_id: int) -> dict:
        return self._data.setdefault(str(user_id), empty_entry())

    @staticmethod
    def _append(entry: dict, key: str, note: str, max_notes: int) -> bool:
        note = note.strip()
        if not note:
            return False
        notes: list[str] = entry[key]
        if note in notes:
            return False
        notes.append(note)
        del notes[:-max_notes]  # on garde les plus récentes
        return True

    def add(self, user_id: int, note: str) -> bool:
        """Ajoute une note éditable par le modèle (faits découverts automatiquement)."""
        added = self._append(self._entry(user_id), "model_editable", note, self.max_notes)
        self._save()
        return added

    def add_immutable(self, user_id: int, note: str) -> bool:
        """Ajoute une note écrite par le propriétaire (le modèle ne peut pas l'effacer)."""
        added = self._append(self._entry(user_id), "immutable", note, self.max_notes)
        self._save()
        return added

    def clear(self, user_id: int) -> None:
        """Oublie tout : les deux listes de notes et le niveau de relation."""
        self._data[str(user_id)] = empty_entry()
        self._save()

    def set_relationship(self, user_id: int, value: int) -> int:
        """Fixe le niveau de relation (borné entre 0 et 100)."""
        value = max(MIN_RELATIONSHIP, min(MAX_RELATIONSHIP, int(value)))
        self._entry(user_id)["relationship"] = value
        self._save()
        return value

    def adjust_relationship(self, user_id: int, delta: int) -> int:
        """Fait évoluer le niveau de relation (négatif si l'utilisateur parle mal)."""
        current = self.relationship(user_id)
        return self.set_relationship(user_id, current + delta)
