"""Niveaux de droit par utilisateur : chaque commande exige un niveau minimum.

L'échelle va de `0` (visiteur) à `MAX_LEVEL` (`5`, propriétaire) :

    0 visiteur · 1 confiance · 2 admin · 3 · 4 · 5 propriétaire

- le propriétaire (`owner_id`) vaut **toujours** `MAX_LEVEL` : son niveau n'est
  jamais écrit sur disque et `set()` refuse de le modifier ;
- un utilisateur absent du fichier vaut `0` (niveau de base) ;
- le fichier est un simple objet JSON ``{"<user_id>": <niveau>}``.
"""

from __future__ import annotations

import json
from pathlib import Path

MAX_LEVEL = 5  # niveau le plus élevé de l'échelle
OWNER_LEVEL = MAX_LEVEL  # le propriétaire est au maximum et ne peut pas changer

# Libellés lisibles des niveaux (les autres s'affichent « niveau N »).
LEVEL_LABELS = {
    0: "visiteur",
    1: "confiance",
    2: "admin",
    5: "propriétaire",
}


def level_label(level: int) -> str:
    """« admin » pour 2, « niveau 3 » pour un grade encore sans nom."""
    return LEVEL_LABELS.get(level, f"niveau {level}")


class UserRights:
    """Niveau de droit de chaque utilisateur, persistés en JSON.

    Le propriétaire n'apparaît jamais dans le fichier : il vaut `OWNER_LEVEL`
    par construction, ce qui le rend impossible à modifier (via `/auth` ou
    en éditant le fichier à la main).
    """

    def __init__(self, path: Path, owner_id: int):
        self.path = Path(path)
        self.owner_id = owner_id
        self._levels: dict[int, int] = {}
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
        for key, value in raw.items():
            try:
                user_id, level = int(key), int(value)
            except (TypeError, ValueError):
                continue
            if 0 <= level <= MAX_LEVEL and user_id != self.owner_id:
                self._levels[user_id] = level

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        data = {str(user_id): level for user_id, level in sorted(self._levels.items())}
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    # ------------------------------------------------------------------
    # API
    # ------------------------------------------------------------------
    @property
    def ids(self) -> list[int]:
        """IDs ayant un niveau explicite (le propriétaire n'en a jamais)."""
        return sorted(self._levels)

    @property
    def entries(self) -> list[tuple[int, int]]:
        """Pairs (user_id, niveau) triées du niveau le plus haut au plus bas."""
        return sorted(self._levels.items(), key=lambda item: (-item[1], item[0]))

    def is_owner(self, user_id: int | None) -> bool:
        return user_id is not None and user_id == self.owner_id

    def level(self, user_id: int | None) -> int:
        """Niveau de `user_id` : `OWNER_LEVEL` pour le propriétaire, `0` par défaut."""
        if user_id is None:
            return 0
        if user_id == self.owner_id:
            return OWNER_LEVEL
        return self._levels.get(user_id, 0)

    def set(self, user_id: int, level: int) -> bool:
        """Fixe le niveau de `user_id`.

        Renvoie `False` si c'est le propriétaire (niveau maximum, immuable).
        Lève `ValueError` si `level` est hors bornes.
        """
        if not 0 <= int(level) <= MAX_LEVEL:
            raise ValueError(f"niveau hors bornes (0-{MAX_LEVEL})")
        if user_id == self.owner_id:
            return False
        self._levels[user_id] = int(level)
        self._save()
        return True
