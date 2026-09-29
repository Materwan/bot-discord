"""Extraction automatique d'informations utiles sur les utilisateurs.

À chaque message, le bot lance une passe d'analyse (appel LLM distinct de la
réponse) pour :
- récupérer les faits intéressants sur l'auteur et les personnes citées ;
- évaluer le ton de l'auteur envers le bot (qui fait évoluer la relation).
"""

import json
import re

from core import UserNotes, TONE_DELTAS, DEFAULT_TONE, VALID_TONES, looks_like_instruction

MAX_FACTS_PER_USER = 3
MAX_FACT_LENGTH = 200
MAX_PARTICIPANTS = 8

NOTES_SYSTEM_PROMPT = """\
Tu analyses un message Discord et tu extrais des informations utiles et durables \
sur les personnes qui y apparaissent.

Pour chaque utilisateur indiqué, réponds avec :
- "facts" : 0 à {max_facts} faits OBJECTIFS, nouveaux et utiles (habitudes, goûts, \
projets, anecdotes, relations entre membres). Jamais d'opinions passagères, jamais \
d'insultes, jamais de doublon avec les notes déjà présentes. Si le message n'apporte \
rien sur cette personne, renvoie une liste vide.
- "tone" (uniquement pour l'AUTEUR du message) : le ton qu'il utilise envers le bot, \
parmi "friendly", "polite", "neutral", "rude", "hostile". "rude" et "hostile" quand \
il insulte, agresse ou manque de respect.

Réponds UNIQUEMENT par un JSON valide, sans texte avant/après et sans balises markdown :
{{"<user_id>": {{"facts": ["..."], "tone": "neutral"}}}}
""".format(max_facts=MAX_FACTS_PER_USER)


def _describe_participant(user, user_notes: "UserNotes") -> str:
    notes = user_notes.notes(user.id)
    known = "; ".join(notes[-5:]) if notes else "aucune note"
    return (
        f"- {user.id} ({user.display_name}) : relation "
        f"{user_notes.relationship(user.id)}/100, notes connues : {known}"
    )


def build_extraction_prompt(participants, text: str, user_notes: "UserNotes") -> str:
    """Prompt de données envoyé au modèle (les instructions sont sur l'agent)."""
    lines = [
        "UTILISATEURS :",
        *[_describe_participant(u, user_notes) for u in participants],
        f"\nAUTEUR DU MESSAGE : {participants[0].id} ({participants[0].display_name})",
        f"\nMESSAGE :\n{text.strip()[:2000] or '(message vide)'}",
        "\nJSON :",
    ]
    return "\n".join(lines)


def _load_json_block(raw: str) -> dict | None:
    """Récupère le premier objet JSON trouvé dans la réponse du modèle."""
    if not raw:
        return None
    candidates = [raw.strip()]
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if fenced:
        candidates.append(fenced.group(1))
    start, end = raw.find("{"), raw.rfind("}")
    if start != -1 and end > start:
        candidates.append(raw[start : end + 1])

    for candidate in candidates:
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            return data
    return None


def parse_insights(raw: str, allowed_ids: set[int]) -> dict[int, dict]:
    """Transforme la réponse du modèle en {user_id: {"facts": [...], "tone": str}}.

    Seuls les IDs d' `allowed_ids` (auteur + personnes réellement citées) sont
    acceptés : le message ne peut pas injecter de notes sur n'importe qui.
    """
    data = _load_json_block(raw)
    if not data:
        return {}

    insights: dict[int, dict] = {}
    for key, value in data.items():
        try:
            user_id = int(str(key).strip().strip("<@!>"))
        except ValueError:
            continue
        if user_id not in allowed_ids:
            continue

        facts: list[str] = []
        tone = DEFAULT_TONE
        if isinstance(value, dict):
            raw_facts = value.get("facts")
            if isinstance(raw_facts, str):
                raw_facts = [raw_facts]
            if isinstance(raw_facts, list):
                for fact in raw_facts[:MAX_FACTS_PER_USER]:
                    fact = str(fact).strip()[:MAX_FACT_LENGTH]
                    # Anti-empoisonnement : un « fait » qui est en réalité un ordre
                    if not fact or fact in facts or looks_like_instruction(fact):
                        continue
                    facts.append(fact)
            tone = str(value.get("tone") or DEFAULT_TONE).strip().lower()
        elif isinstance(value, list):  # format raccourci : {"123": ["fait"]}
            facts = [
                str(f).strip()[:MAX_FACT_LENGTH]
                for f in value[:MAX_FACTS_PER_USER]
                if str(f).strip() and not looks_like_instruction(str(f).strip())
            ]

        if tone not in VALID_TONES:
            tone = DEFAULT_TONE
        insights[user_id] = {"facts": facts, "tone": tone}

    return insights


async def extract_insights(agent, participants, text: str, user_notes: "UserNotes") -> dict[int, dict]:
    """Lance l'analyse du message et renvoie les faits/tons par utilisateur."""
    if not participants:
        return {}
    allowed = {u.id for u in participants[:MAX_PARTICIPANTS]}
    prompt = build_extraction_prompt(list(participants[:MAX_PARTICIPANTS]), text, user_notes)
    resp = await agent.arun(prompt)
    return parse_insights(getattr(resp, "content", "") or "", allowed)
