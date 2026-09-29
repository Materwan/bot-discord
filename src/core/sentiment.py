"""Ton des messages et évolution du niveau de relation (0-100)."""

import re

DEFAULT_TONE = "neutral"

# Évolution du niveau de relation selon le ton de l'utilisateur envers le bot
TONE_DELTAS: dict[str, int] = {
    "friendly": 4,
    "polite": 2,
    "neutral": 0,
    "rude": -12,
    "hostile": -25,
}

VALID_TONES = tuple(TONE_DELTAS)

# Dernier filet de sécurité : si le modèle ne détecte pas la grossièreté,
# ces expressions font elles-mêmes baisser la relation.
_RUDE_PATTERNS = [
    r"\bconnards?\b",
    r"\bconnasses?\b",
    r"\bencul[eé]s?\b",
    r"\bconneries?\b",
    r"\bcon\b",
    r"\bsale con\b",
    r"\bgrands? cons?\b",
    r"\bcrétins?\b",
    r"\babrutis?\b",
    r"\bimbéciles?\b",
    r"\bdébiles?\b",
    r"\bidiot(e)?s?\b",
    r"\bstupides?\b",
    r"\binutiles?\b",
    r"\bnazes?\b",
    r"\bmerde\b",
    r"\bputains?\b",
    r"\bva te faire\s+mettre\b",
    r"\bva niquer\s+(ta|maman|mère)\b",
    r"\bta m[èe]re\b",
    r"\bta gueule\b",
    r"\bferme (ta gueule|la)\b",
    r"\bd[ée]gage\b",
    r"\bcr[èe]ve\b",
    r"\bntm\b",
    r"\bfdp\b",
    r"\btg\b",
    r"\bt['’]es nul\b",
    r"\btu vaux rien\b",
    r"\bt['’]es (une )?vraie? (merde|pisse)\b",
]


def detect_rudeness(text: str) -> bool:
    """True si le message contient des insultes envers le bot."""
    if not text:
        return False
    lowered = text.lower()
    return any(
        re.search(pattern, lowered)
        for pattern in _RUDE_PATTERNS
    )
