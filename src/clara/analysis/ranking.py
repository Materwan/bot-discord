"""Keyword relevance: pick the notes and memories worth injecting in a prompt."""

from __future__ import annotations

import re
import unicodedata

_TOKEN_RE = re.compile(r"[a-z0-9]{3,}")

# Words too common to tell two texts apart (French, English and chat slang).
# Stored without accents, like the tokens they are compared to.
STOPWORDS = frozenset({
    "alors", "aussi", "autre", "avaient", "avec", "avoir", "bien", "bonjour",
    "bonsoir", "comme", "coucou", "dans", "desormais", "donc", "elle",
    "elles", "encore", "entre", "est", "faire", "fait", "fois", "fort", "hello",
    "ici", "jamais", "leur", "leurs", "long", "mdr", "meme", "merci", "moins",
    "nous", "pour", "plus", "plusieurs", "pourtant", "prend", "rien", "salut",
    "sans", "saura", "sein", "sont", "souvent", "toujours", "tout", "tous",
    "toute", "toutes", "trop", "tres", "vers", "vous", "voyait", "vraiment",
    "the", "and", "for", "you", "are", "with", "that", "this", "not", "his",
    "her", "was", "has", "have", "from", "they", "them", "what", "when",
    "lol", "mdrr", "svp", "oui", "non", "nan", "hein", "quoi",
})

# Minimum length for a prefix match ("foot" <-> "football")
MIN_PREFIX_LENGTH = 4


def tokenize(text: str) -> set[str]:
    """Lowercase, accent-free words of 3+ characters, stopwords removed."""
    if not text:
        return set()
    normalized = (
        unicodedata.normalize("NFKD", str(text).lower()).encode("ascii", "ignore").decode("ascii")
    )
    return {token for token in _TOKEN_RE.findall(normalized) if token not in STOPWORDS}


def _score_tokens(text_tokens: set[str], query_tokens: set[str]) -> int:
    """Shared words, plus prefix matches ("echec" <-> "echecs")."""
    exact = text_tokens & query_tokens
    prefix_hits = 0
    for query_token in query_tokens - exact:
        if len(query_token) < MIN_PREFIX_LENGTH:
            continue
        if any(
            len(text_token) >= MIN_PREFIX_LENGTH
            and (text_token.startswith(query_token) or query_token.startswith(text_token))
            for text_token in text_tokens
        ):
            prefix_hits += 1
    return len(exact) + prefix_hits


def score(text: str, query: str) -> int:
    """Relevance of `text` for `query`."""
    return _score_tokens(tokenize(text), tokenize(query))


def rank(texts: list[str], query: str, limit: int | None = None) -> list[str]:
    """Most relevant texts first.

    Ties keep their original order (recency), and texts with no match are
    kept: `limit` caps the list, it never empties it.
    """
    if limit is not None and limit <= 0:
        return []
    query_tokens = tokenize(query)
    scored = sorted(
        enumerate(texts),
        key=lambda item: (-_score_tokens(tokenize(item[1]), query_tokens), item[0]),
    )
    return [text for _, text in scored[:limit]]
