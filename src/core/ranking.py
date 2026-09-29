"""Sélection des informations pertinentes à injecter dans le prompt."""

import re
import unicodedata

TOKEN_RE = re.compile(r"[a-z0-9]{3,}")

# Mots trop courants pour discriminer (français + anglais + tchatche de serveur)
STOPWORDS = {
    "alors", "aussi", "autre", "avaient", "avec", "avoir", "bien", "bonjour",
    "bonsoir", "comme", "coucou", "dans", "desormais", "donc", "elle",
    "elles", "encore", "entre", "est", "faire", "fait", "fois", "fort", "hello",
    "ici", "jamais", "leur", "leurs", "long", "mdr", "meme", "merci", "moins",
    "nous", "pour", "plus", "plusieurs", "pourtant", "prend", "rien", "salut",
    "sans", "saura", "sein", "sont", "souvent", "toujours", "tout", "tous",
    "toute", "toutes", "trop", "tres", "vers", "vous", "voyait", "vraiment",
    "the", "and", "for", "you", "are", "with", "that", "this", "not", "his",
    "her", "was", "has", "have", "from", "they", "them", "what", "when",
    "lol", "mdrr", "svp", "ok", "oui", "non", "nan", "hein", "quoi", "hein",
}


def tokenize(text) -> set[str]:
    """Jeton normalisés (sans accents, sans stopwords), pour comparer deux textes."""
    if not text:
        return set()
    if not isinstance(text, str):  # anciennes mémoires stockées en dict
        text = str(text)
    normalized = (
        unicodedata.normalize("NFKD", text.lower())
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    return {t for t in TOKEN_RE.findall(normalized) if t not in STOPWORDS}


MIN_PREFIX = 4  # longueur minimale pour une correspondance par préfixe (foot/football)


def _prefix_hits(text_tokens: set[str], query_tokens: set[str]) -> int:
    """Correspondances approchées : « foot » <-> « football », « échec » <-> « échecs »."""
    hits = 0
    for query_token in query_tokens:
        if len(query_token) < MIN_PREFIX or query_token in text_tokens:
            continue
        if any(
            len(text_token) >= MIN_PREFIX
            and (
                text_token.startswith(query_token)
                or query_token.startswith(text_token)
            )
            for text_token in text_tokens
        ):
            hits += 1
    return hits


def score(text: str, query: str) -> int:
    """Pertinence d'un texte pour une requête (jetons partagés + préfixes)."""
    text_tokens = tokenize(text)
    query_tokens = tokenize(query)
    return len(text_tokens & query_tokens) + _prefix_hits(text_tokens, query_tokens)


def rank(texts: list[str], query: str, limit: int | None = None) -> list[str]:
    """Classe les textes du plus pertinent au moins pertinent pour `query`.

    Les ex æquo gardent l'ordre d'origine (la récence), et un texte sans
    correspondance reste injecté : le plafond filtre, il ne supprime pas tout.
    """
    if limit is not None and limit <= 0:
        return []
    scored = [(score(t, query), i, t) for i, t in enumerate(texts)]
    scored.sort(key=lambda item: (-item[0], item[1]))
    if limit is not None:
        scored = scored[:limit]
    return [t for _, _, t in scored]
