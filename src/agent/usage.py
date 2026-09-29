"""Comptage des tokens d'une réponse de l'agent.

Depuis le passage du client « ollama » brut à Agno, les compteurs ne sont
plus lus sur la réponse (``resp.prompt_eval_count`` / ``resp.eval_count``)
mais agrégés par Agno dans ``resp.metrics`` : un objet ``RunMetrics`` qui
additionne les tokens de toute la requête (systeme + outils + réponse).

Le modèle ne fournit pas toujours ces mesures (erreur, mock, fournisseur
sans compteur) : dans ce cas on renvoie (0, 0) plutôt que d'échouer.
"""

from __future__ import annotations

from typing import Any

EMPTY_USAGE = (0, 0)


def _as_int(value: Any) -> int:
    """Entier strictement positif, 0 si la valeur n'est pas un nombre."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0
    return max(int(value), 0)


def _field(metrics: Any, *names: str) -> Any:
    """Première valeur trouvée parmi ``names``, que ``metrics`` soit un mapping ou un objet."""
    for name in names:
        if isinstance(metrics, dict):
            if name in metrics:
                return metrics[name]
        else:
            value = getattr(metrics, name, None)
            if value is not None:
                return value
    return None


def token_usage(response: Any) -> tuple[int, int]:
    """Renvoie ``(prompt_tokens, completion_tokens)`` mesurés pour une requête.

    ``response`` est la ``RunOutput`` renvoyée par ``agent.arun()`` ; on tolère
    ``None``, un mock et les anciennes formes (``.usage``).
    """
    if response is None:
        return EMPTY_USAGE

    metrics = getattr(response, "metrics", None) or getattr(response, "usage", None)
    if not metrics:
        return EMPTY_USAGE

    prompt_tokens = _as_int(_field(metrics, "input_tokens", "prompt_tokens"))
    completion_tokens = _as_int(_field(metrics, "output_tokens", "completion_tokens"))
    return prompt_tokens, completion_tokens
