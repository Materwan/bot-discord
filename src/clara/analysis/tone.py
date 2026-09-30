"""Tone of a message towards the bot, and how it moves the relationship score."""

from __future__ import annotations

import re
from enum import Enum


class Tone(str, Enum):
    FRIENDLY = "friendly"
    POLITE = "polite"
    NEUTRAL = "neutral"
    RUDE = "rude"
    HOSTILE = "hostile"

    @property
    def relationship_delta(self) -> int:
        return _RELATIONSHIP_DELTAS[self]

    @classmethod
    def parse(cls, value: object) -> Tone:
        """Tone named by `value`, NEUTRAL if unrecognized."""
        try:
            return cls(str(value).strip().lower())
        except ValueError:
            return cls.NEUTRAL


_RELATIONSHIP_DELTAS = {
    Tone.FRIENDLY: 4,
    Tone.POLITE: 2,
    Tone.NEUTRAL: 0,
    Tone.RUDE: -12,
    Tone.HOSTILE: -25,
}

# Local safety net: insults lower the relationship even if the model misses them
_RUDE_PATTERNS = [
    # French
    r"\bconnards?\b",
    r"\bconnasses?\b",
    r"\bencul[eé]s?\b",
    r"\bconneries?\b",
    r"\bcon\b",
    r"\bgrands? cons?\b",
    r"\bcr[ée]tins?\b",
    r"\babrutis?\b",
    r"\bimb[ée]ciles?\b",
    r"\bd[ée]biles?\b",
    r"\bidiot(e)?s?\b",
    r"\bstupides?\b",
    r"\binutiles?\b",
    r"\bnazes?\b",
    r"\bmerde\b",
    r"\bputains?\b",
    r"\bva te faire\s+mettre\b",
    r"\bva niquer\s+(ta|maman|m[èe]re)\b",
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
    # English
    r"\bshut up\b",
    r"\bfuck (you|off)\b",
    r"\bstupid\b",
    r"\bdumb\b",
    r"\buseless\b",
]

_RUDE_RE = re.compile("|".join(_RUDE_PATTERNS), re.IGNORECASE)


def is_rude(text: str) -> bool:
    """True if the message contains insults."""
    return bool(text) and _RUDE_RE.search(text) is not None


def effective_tone(model_tone: Tone, text: str) -> Tone:
    """The model's tone, lowered to at least RUDE when the text contains insults."""
    if is_rude(text) and model_tone.relationship_delta > Tone.RUDE.relationship_delta:
        return Tone.RUDE
    return model_tone
