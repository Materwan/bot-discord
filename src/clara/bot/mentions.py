"""Mentions in both directions: Discord message -> prompt text, and answer -> pings."""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Iterable

import discord

from ..storage.user_directory import UserDirectory

MIN_NAME_LENGTH = 3  # shorter display names cause too many false positives
MAX_NAME_WORDS = 3
MAX_PINGS_PER_REPLY = 10  # beyond this, "@Name" stays plain text (no mass pings)

# "@Paul" or "@Jean Pierre Dupont" (up to 3 words) not already inside "<@...>"
_PING_RE = re.compile(r"(?<![<\w])@(\w[\w'-]*(?: \w[\w'-]*){0,%d})" % (MAX_NAME_WORDS - 1))


def strip_bot_mention(content: str, bot_id: int) -> str:
    """Message text without the bot's own mention."""
    return content.replace(f"<@{bot_id}>", "").replace(f"<@!{bot_id}>", "").strip()


def replace_mentions_with_names(text: str, mentions: Iterable[discord.abc.User], bot_id: int) -> str:
    """"<@123>" -> "Paul", so the model reads names instead of raw IDs."""
    for user in mentions:
        if user.id != bot_id:
            text = text.replace(f"<@{user.id}>", user.display_name).replace(f"<@!{user.id}>", user.display_name)
    return text


@lru_cache(maxsize=32)
def _names_pattern(names: tuple[str, ...]) -> re.Pattern:
    """One regex matching any of `names` as a whole word (longest names first)."""
    alternatives = "|".join(re.escape(name) for name in sorted(names, key=len, reverse=True))
    return re.compile(rf"(?<!\w)(?:{alternatives})(?!\w)", re.IGNORECASE)


def find_cited_members(message: discord.Message, text: str, bot_id: int) -> list[discord.abc.User]:
    """People and bots the message is about, besides its author and Clara herself:
    mentions first, then names typed in clear.

    Names are matched against the server's display names with a single cached
    regex, instead of one search per member.
    """
    author = message.author
    cited: dict[int, discord.abc.User] = {}
    for user in message.mentions:
        if user.id not in (bot_id, author.id):
            cited[user.id] = user

    if message.guild is not None:
        by_name: dict[str, discord.Member] = {}
        for member in message.guild.members:
            name = member.display_name
            if member.id in (bot_id, author.id) or len(name) < MIN_NAME_LENGTH:
                continue
            by_name.setdefault(name.lower(), member)
        if by_name:
            for match in _names_pattern(tuple(sorted(by_name))).finditer(text):
                member = by_name[match.group(0).lower()]
                cited.setdefault(member.id, member)

    return list(cited.values())


def add_pings(
    text: str,
    directory: UserDirectory,
    members: Iterable[discord.abc.User],
    bot_id: int,
    max_pings: int = MAX_PINGS_PER_REPLY,
) -> str:
    """"@Paul" -> "<@id>", so the model can tag people and bots.

    A name is looked up in the directory first, then among `members` (display
    name or username, case-insensitive); the longest matching name wins. At
    most `max_pings` different people are pinged, and never Clara herself.
    """
    member_ids: dict[str, int] = {}
    for member in members:
        for name in (member.display_name, member.name):
            member_ids.setdefault(name.lower(), member.id)
    pinged: set[int] = set()

    def lookup(name: str) -> int | None:
        user_id = directory.id_for(name)
        return user_id if user_id is not None else member_ids.get(name.lower())

    def replace(match: re.Match) -> str:
        words = match.group(1).split(" ")
        for count in range(len(words), 0, -1):
            user_id = lookup(" ".join(words[:count]))
            if user_id is None or user_id == bot_id:
                continue
            if user_id not in pinged and len(pinged) >= max_pings:
                break
            pinged.add(user_id)
            rest = " ".join(words[count:])
            return f"<@{user_id}>" + (f" {rest}" if rest else "")
        return match.group(0)  # unknown name or ping limit reached: leave the text as is

    return _PING_RE.sub(replace, text)
