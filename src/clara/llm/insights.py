"""After each answer: learn facts about the people involved, and update the
author's relationship score from the tone of their message.

A separate LLM call (no tools, JSON output) returns, for the author and the
people cited in the message, new facts plus the author's tone. A local insult
detector acts as a safety net when the model misses rudeness.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from ..analysis.injection_guard import looks_like_instruction
from ..analysis.tone import Tone, effective_tone
from ..storage.event_log import EventLog
from ..storage.user_notes import UserNotes
from .client import LlmClient
from .prompt_builder import Person

MAX_FACTS_PER_USER = 3
MAX_FACT_LENGTH = 200
MAX_PARTICIPANTS = 8
MAX_MESSAGE_LENGTH = 2000
KNOWN_NOTES_SHOWN = 5

INSIGHTS_SYSTEM_PROMPT = f"""\
Tu analyses un message Discord et tu extrais des informations utiles et durables \
sur les personnes qui y apparaissent.

Pour chaque utilisateur indiqué, réponds avec :
- "facts" : 0 à {MAX_FACTS_PER_USER} faits OBJECTIFS, nouveaux et utiles (habitudes, goûts, \
projets, anecdotes, relations entre membres). Jamais d'opinions passagères, jamais \
d'insultes, jamais de doublon avec les notes déjà présentes. Si le message n'apporte \
rien sur cette personne, renvoie une liste vide.
- "tone" (uniquement pour l'AUTEUR du message) : le ton qu'il utilise envers le bot, \
parmi "friendly", "polite", "neutral", "rude", "hostile". "rude" et "hostile" quand \
il insulte, agresse ou manque de respect.

Réponds UNIQUEMENT par un JSON valide :
{{"<user_id>": {{"facts": ["..."], "tone": "neutral"}}}}
"""


@dataclass
class UserInsight:
    facts: list[str] = field(default_factory=list)
    tone: Tone = Tone.NEUTRAL


def build_insights_prompt(participants: list[Person], text: str, user_notes: UserNotes) -> str:
    """Data sent to the model (participants[0] is the author)."""
    lines = ["UTILISATEURS :"]
    for person in participants:
        notes = user_notes.notes(person.id)
        known = "; ".join(notes[-KNOWN_NOTES_SHOWN:]) if notes else "aucune note"
        lines.append(
            f"- {person.id} ({person.display_name}) : relation "
            f"{user_notes.relationship(person.id)}/100, notes connues : {known}"
        )
    author = participants[0]
    lines.append(f"\nAUTEUR DU MESSAGE : {author.id} ({author.display_name})")
    lines.append(f"\nMESSAGE :\n{text.strip()[:MAX_MESSAGE_LENGTH] or '(message vide)'}")
    return "\n".join(lines)


def _first_json_object(raw: str) -> dict | None:
    """The JSON object in the model output, even if wrapped in text or a code fence."""
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
        except ValueError:
            continue
        if isinstance(data, dict):
            return data
    return None


def _clean_facts(raw_facts: object) -> list[str]:
    if isinstance(raw_facts, str):
        raw_facts = [raw_facts]
    if not isinstance(raw_facts, list):
        return []
    facts: list[str] = []
    for raw_fact in raw_facts[:MAX_FACTS_PER_USER]:
        fact = str(raw_fact).strip()[:MAX_FACT_LENGTH]
        if fact and fact not in facts and not looks_like_instruction(fact):
            facts.append(fact)
    return facts


def parse_insights(raw: str, allowed_ids: set[int]) -> dict[int, UserInsight]:
    """Model output -> insights, keeping only the IDs in `allowed_ids`.

    The allow-list (author + people actually cited) prevents a message from
    injecting notes about anybody else.
    """
    data = _first_json_object(raw or "")
    if not data:
        return {}

    insights: dict[int, UserInsight] = {}
    for key, value in data.items():
        try:
            user_id = int(str(key).strip().strip("<@!>"))
        except ValueError:
            continue
        if user_id not in allowed_ids:
            continue
        if isinstance(value, dict):
            insights[user_id] = UserInsight(_clean_facts(value.get("facts")), Tone.parse(value.get("tone")))
        elif isinstance(value, list):  # shorthand: {"123": ["fact"]}
            insights[user_id] = UserInsight(_clean_facts(value))
    return insights


class InsightRecorder:
    def __init__(self, llm: LlmClient, user_notes: UserNotes, event_log: EventLog, enabled: bool = True):
        self.llm = llm
        self.user_notes = user_notes
        self.event_log = event_log
        self.enabled = enabled

    async def extract(self, participants: list[Person], text: str) -> dict[int, UserInsight]:
        participants = participants[:MAX_PARTICIPANTS]
        messages = [
            {"role": "system", "content": INSIGHTS_SYSTEM_PROMPT},
            {"role": "user", "content": build_insights_prompt(participants, text, self.user_notes)},
        ]
        result = await self.llm.chat(messages, json_output=True)
        return parse_insights(result.content, {person.id for person in participants})

    async def record(self, participants: list[Person], text: str, channel_id: int) -> None:
        """Save new facts and update the author's relationship (participants[0])."""
        author = participants[0]
        insights: dict[int, UserInsight] = {}
        if self.enabled:
            try:
                insights = await self.extract(participants, text)
            except Exception as error:  # analysis must never break the conversation
                self.event_log.write("insights_error", error=repr(error))

        facts_saved = sum(
            self.user_notes.add_learned(user_id, fact)
            for user_id, insight in insights.items()
            for fact in insight.facts
        )
        tone = effective_tone(insights.get(author.id, UserInsight()).tone, text)
        relationship = self.user_notes.adjust_relationship(author.id, tone.relationship_delta)

        self.event_log.write(
            "insights",
            channel_id=channel_id,
            author_id=author.id,
            facts_saved=facts_saved,
            tone=tone.value,
            relationship_delta=tone.relationship_delta,
            relationship=relationship,
        )
