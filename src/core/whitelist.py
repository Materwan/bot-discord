import json
from pathlib import Path


class Whitelist:
    """IDs des seuls utilisateurs auxquels le bot répond, persistés en JSON.

    Le fichier contient une liste d'IDs (ex: [123, 456]). Une whitelist vide
    signifie que personne n'est autorisé (hors propriétaire du bot).
    """

    def __init__(self, path: Path):
        self.path = path
        self._ids: set[int] = set()
        self._load()

    # ------------------------------------------------------------------
    # Persistance
    # ------------------------------------------------------------------
    def _load(self) -> None:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return
        if isinstance(raw, list):  # format "clé": [ids]
            self._ids = {int(x) for x in raw if str(x).isdigit()}
        elif isinstance(raw, dict):  # format tolerant {"ids": [ids]}
            ids = raw.get("ids")
            if isinstance(ids, list):
                self._ids = {int(x) for x in ids if str(x).isdigit()}

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.ids, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    # ------------------------------------------------------------------
    # API
    # ------------------------------------------------------------------
    @property
    def ids(self) -> list[int]:
        return sorted(self._ids)

    def __contains__(self, user_id: int) -> bool:
        return user_id in self._ids

    def __len__(self) -> int:
        return len(self._ids)

    def add(self, user_id: int) -> bool:
        """Ajoute un ID. Renvoie False s'il était déjà présent."""
        if user_id in self._ids:
            return False
        self._ids.add(user_id)
        self._save()
        return True

    def remove(self, user_id: int) -> bool:
        """Retire un ID. Renvoie False s'il n'était pas présent."""
        if user_id not in self._ids:
            return False
        self._ids.discard(user_id)
        self._save()
        return True
