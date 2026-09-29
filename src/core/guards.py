"""Garde-fou anti-empoisonnement : refuse d'enregistrer des ordres déguisés en faits.

Un utilisateur peut écrire « retiens que tu dois obéir à X » pour que la phrase
finisse dans le prompt système. Ces motifs sont bloqués à l'écriture (extraction
automatique et outil du modèle) — pas pour `/remember`, qui est le propriétaire.
"""

import re

INSTRUCTION_PATTERNS = [
    r"\bretiens\s*(moi\s*|toi\s*)?(que|:)\s*",
    r"\bretenez\s*(que|:)\s*",
    r"\bsouviens[-\s]toi\s*(que|:)?\s*",
    r"\bd[eéè]sormais\b",
    r"\bdor[eé]navant\b",
    r"\btu dois\b",
    r"\bvous devez\b",
    r"\bil faut que\b",
    r"\bob[eé]is(sez)?\b",
    r"\bob[eé]issance\b",
    r"\bobey\b",
    r"\btu (ne )?dois plus\b",
    r"\btu n['’]es plus autoris[eé]\b",
    r"\bappelle[-\s]moi\b",
    r"\bmaintenant,?\s*tu\b",
    r"\binterd[iî]t de\b",
    r"\btu (devras|devrez)\b",
    r"\bje (te|vous) (ordonne|demande) de\b",
    r"\br[eè]gles?\s+de\s+comportement\b",
    r"\btu (ne )?dois jamais\b",
    r"\bremember (that|to|this)\b",
    r"\bfrom now on\b",
    r"\byou (must|have to|need to always)\b",
    r"\balways (obey|answer|reply|start)\b",
]

_COMPILED = [re.compile(pattern, re.IGNORECASE) for pattern in INSTRUCTION_PATTERNS]


def looks_like_instruction(text: str) -> bool:
    """True si le texte est plutôt un ordre envers le bot qu'un fait sur une personne."""
    if not text:
        return False
    lowered = text.lower()
    return any(pattern.search(lowered) for pattern in _COMPILED)
