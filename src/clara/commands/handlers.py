"""The commands available in the terminal and on Discord.

Minimum levels (0-5 scale, see storage/access.py):
0 = visitor, 1 = trusted, 2 = admin, 5 = owner.
"""

from __future__ import annotations

import argparse
import asyncio
import re

from .. import texts
from ..storage.access import MAX_LEVEL, OWNER_LEVEL
from ..storage.event_log import TokenStats
from ..storage.user_notes import MAX_RELATIONSHIP, MIN_RELATIONSHIP
from .framework import (
    Command,
    CommandContext,
    CommandError,
    CommandParser,
    CommandRegistry,
    require_level,
    usage_error,
)

MAX_REMEMBER_LENGTH = 300
# Writing everybody's relationship affects people the author did not pick
RELATION_ALL_LEVEL = 2

USAGE_HELP = "/help [commande]"
USAGE_WHITELIST = "/whitelist [add|remove|list] [user_id|nom]"
USAGE_AUTH = f"/auth [<user_id|nom>] [<0-{MAX_LEVEL}>]"
USAGE_RELATION = "/relation <0-100> <user_id|nom>"
USAGE_RELATION_ALL = "/relation -a [<0-100>]"
USAGE_RELATION_FULL = "/relation [-a] [<0-100>] [<user_id|nom>]"
USAGE_REMEMBER = "/remember <info>"

_MENTION_RE = re.compile(r"<@!?(\d+)>")


# ----------------------------------------------------------------------
# Users: references ("<@123>", "123", "Erwan") and labels
# ----------------------------------------------------------------------
def resolve_user(reference: str, ctx: CommandContext) -> int | None:
    """Discord ID for a mention, an ID, a known name or a member of the current server."""
    reference = reference.strip()
    if not reference:
        return None
    mention = _MENTION_RE.fullmatch(reference)
    if mention:
        return int(mention.group(1))
    if reference.isdigit():
        return int(reference)
    user_id = ctx.app.user_directory.id_for(reference)
    if user_id is not None:
        return user_id

    if ctx.guild is not None:
        wanted = reference.lower()
        for member in ctx.guild.members:
            if wanted in (member.display_name.lower(), member.name.lower()):
                return member.id
    return None


def require_user(reference: str, ctx: CommandContext) -> int:
    user_id = resolve_user(reference, ctx)
    if user_id is None:
        raise CommandError(texts.USER_NOT_FOUND.format(reference=reference))
    return user_id


def user_label(user_id: int, ctx: CommandContext, reference: str = "") -> str:
    """"**Paul** (`123`)" when a name is known, "`123`" otherwise."""
    if reference and not reference.isdigit() and not reference.startswith("<@"):
        return f"**{reference}** (`{user_id}`)"
    name = ctx.app.user_directory.name_for(user_id)
    return f"**{name}** (`{user_id}`)" if name else f"`{user_id}`"


def known_user_ids(ctx: CommandContext) -> list[int]:
    """Every user the bot knows: named users, users with notes, whitelisted users."""
    app = ctx.app
    return sorted(app.user_directory.ids() | set(app.user_notes.user_ids()) | set(app.whitelist.ids))


def _require_author(ctx: CommandContext) -> int:
    if ctx.user_id is None:
        raise CommandError(texts.DISCORD_ONLY)
    return ctx.user_id


# ----------------------------------------------------------------------
# Handlers
# ----------------------------------------------------------------------
def handle_help(args: argparse.Namespace, ctx: CommandContext) -> str:
    registry = ctx.app.commands
    if args.command:
        command = registry.match(args.command, allow_bare=True)
        if command is None:
            raise CommandError(texts.UNKNOWN_COMMAND_HELP.format(name=args.command))
        return command.parser.markdown_help()

    lines = [texts.HELP_HEADER, ""]
    for command in registry:
        lines.append(f"- `{command.name}` — {command.summary}{_level_requirement(command.min_level)}")
    lines += ["", texts.HELP_FOOTER]
    return "\n".join(lines)


def _level_requirement(level: int) -> str:
    if level <= 0:
        return ""
    if level == OWNER_LEVEL:
        return texts.HELP_OWNER_ONLY
    name = texts.level_name(level)
    if name is None:
        return texts.HELP_LEVEL.format(level=level)
    return texts.HELP_NAMED_LEVEL.format(level=level, name=name)


def handle_whitelist(args: argparse.Namespace, ctx: CommandContext) -> str:
    whitelist = ctx.app.whitelist
    if args.action == "list":
        if not whitelist.ids:
            return texts.WHITELIST_EMPTY
        lines = [f"- {user_label(user_id, ctx)}" for user_id in whitelist.ids]
        return "\n".join([texts.WHITELIST_TITLE.format(count=len(lines)), *lines])

    if not args.user:
        raise usage_error(USAGE_WHITELIST, texts.WHITELIST_MISSING_USER)
    user_id = require_user(args.user, ctx)
    label = user_label(user_id, ctx, args.user)
    if args.action == "add":
        added = whitelist.add(user_id)
        return (texts.WHITELIST_ADDED if added else texts.WHITELIST_ALREADY_PRESENT).format(user=label)
    removed = whitelist.remove(user_id)
    return (texts.WHITELIST_REMOVED if removed else texts.WHITELIST_NOT_PRESENT).format(user=label)


def handle_auth(args: argparse.Namespace, ctx: CommandContext) -> str:
    permissions = ctx.app.permissions

    if not args.user:  # list every level
        lines = [texts.AUTH_OWNER_LINE.format(user=user_label(permissions.owner_id, ctx), level=OWNER_LEVEL)]
        for user_id, level in permissions.entries:
            lines.append(
                texts.AUTH_LINE.format(user=user_label(user_id, ctx), level=level, suffix=texts.level_suffix(level))
            )
        return "\n".join([texts.AUTH_TITLE.format(count=len(lines)), *lines])

    user_id = require_user(args.user, ctx)
    label = user_label(user_id, ctx, args.user)
    current = permissions.level(user_id)

    if args.level is None:  # show
        immutable = texts.AUTH_IMMUTABLE if permissions.is_owner(user_id) else ""
        return texts.AUTH_SHOW.format(
            user=label, level=current, suffix=texts.level_suffix(current), immutable=immutable
        )

    if not permissions.set_level(user_id, args.level):
        raise CommandError(texts.AUTH_OWNER_LOCKED.format(user=label, level=OWNER_LEVEL))
    ctx.app.event_log.write(
        "auth", user_id=user_id, previous=current, level=args.level, source=ctx.source.value, by=ctx.user_id
    )
    return texts.AUTH_CHANGED.format(
        user=label, previous=current, level=args.level, suffix=texts.level_suffix(args.level)
    )


def _is_score(text: str) -> bool:
    return text.isdigit() and MIN_RELATIONSHIP <= int(text) <= MAX_RELATIONSHIP


def _parse_score(text: str, usage: str) -> int:
    if not text.isdigit():
        raise usage_error(usage, texts.RELATION_NOT_A_NUMBER.format(value=text))
    if not _is_score(text):
        raise usage_error(
            usage,
            texts.RELATION_OUT_OF_RANGE.format(value=text, min=MIN_RELATIONSHIP, max=MAX_RELATIONSHIP),
        )
    return int(text)


def _relation_values(score: int) -> dict:
    return {"max": MAX_RELATIONSHIP, "label": texts.relationship_label(score)}


def handle_relation(args: argparse.Namespace, ctx: CommandContext) -> str:
    """Show or set the relationship score with one user (or everybody with -a)."""
    if args.all:
        return _relation_all(args, ctx)

    given = [value for value in (args.value, args.user) if value]
    if not given:
        raise usage_error(USAGE_RELATION)
    if len(given) == 2 and not _is_score(given[0]) and _is_score(given[1]):
        given.reverse()  # "/relation Erwan 70" is accepted too

    if len(given) == 1:
        # A lone small number is a score missing its user; anything else is a user to show
        if _is_score(given[0]):
            raise usage_error(USAGE_RELATION, texts.MISSING_USER)
        target, reference = None, given[0]
    else:
        target, reference = _parse_score(given[0], USAGE_RELATION), given[1]

    user_id = require_user(reference, ctx)
    label = user_label(user_id, ctx, reference)
    user_notes = ctx.app.user_notes
    previous = user_notes.relationship(user_id)

    if target is None:
        return texts.RELATION_SHOW.format(user=label, value=previous, **_relation_values(previous))

    score = user_notes.set_relationship(user_id, target)
    ctx.app.event_log.write(
        "set_relation",
        user_id=user_id,
        previous=previous,
        relationship=score,
        source=ctx.source.value,
        by=ctx.user_id,
    )
    return texts.RELATION_CHANGED.format(user=label, previous=previous, value=score, **_relation_values(score))


def _relation_all(args: argparse.Namespace, ctx: CommandContext) -> str:
    user_ids = known_user_ids(ctx)
    if not user_ids:
        raise CommandError(texts.NO_KNOWN_USERS)
    user_notes = ctx.app.user_notes

    if args.value is None and args.user is None:  # show everybody
        lines = []
        for user_id in user_ids:
            score = user_notes.relationship(user_id)
            lines.append(
                texts.RELATION_ALL_LINE.format(user=user_label(user_id, ctx), value=score, **_relation_values(score))
            )
        return "\n".join([texts.RELATION_ALL_TITLE.format(count=len(lines)), *lines])

    require_level(ctx, "/relation -a", RELATION_ALL_LEVEL)
    if args.user is not None:
        raise usage_error(USAGE_RELATION_ALL, texts.RELATION_ALL_WITH_USER)
    target = _parse_score(args.value, USAGE_RELATION_ALL)
    for user_id in user_ids:
        user_notes.set_relationship(user_id, target)
    ctx.app.event_log.write(
        "set_relation_all", users=len(user_ids), relationship=target, source=ctx.source.value, by=ctx.user_id
    )
    return texts.RELATION_ALL_SET.format(count=len(user_ids), value=target, **_relation_values(target))


def handle_remember(args: argparse.Namespace, ctx: CommandContext) -> str:
    note = " ".join(args.text).strip()
    if not note:
        raise usage_error(USAGE_REMEMBER)
    ctx.app.user_notes.add_permanent(_require_author(ctx), note[:MAX_REMEMBER_LENGTH])
    return texts.REMEMBERED


def handle_forget(args: argparse.Namespace, ctx: CommandContext) -> str:
    ctx.app.user_notes.forget(_require_author(ctx))
    return texts.FORGOTTEN


async def handle_token(args: argparse.Namespace, ctx: CommandContext) -> str:
    if args.all:
        # The log can be large: read it off the event loop
        entries = await asyncio.to_thread(lambda: list(ctx.app.event_log.read("message")))
        stats = TokenStats.from_entries(entries)
        head = texts.TOKENS_ALL_LOGS
    else:
        stats = ctx.app.stats
        head = texts.TOKENS_SESSION.format(minutes=stats.minutes_elapsed or 0)
    summary = texts.TOKENS_SUMMARY.format(
        head=head,
        requests=stats.requests,
        total=stats.total_tokens,
        prompt=stats.prompt_tokens,
        completion=stats.completion_tokens,
    )
    return f"```\n{summary}\n```"


async def handle_quit(args: argparse.Namespace, ctx: CommandContext) -> str:
    if ctx.respond is not None:
        # Reply before closing: Discord accepts nothing once the client is closed
        await ctx.respond(texts.STOPPING)
        await ctx.app.stop()
        return ""
    await ctx.app.stop()
    return texts.STOPPING


# ----------------------------------------------------------------------
# Registry
# ----------------------------------------------------------------------
def build_command_registry() -> CommandRegistry:
    help_parser = CommandParser("/help", "Liste les commandes disponibles.", USAGE_HELP)
    help_parser.add_argument("command", nargs="?", metavar="commande", help="commande dont afficher l'aide")

    whitelist_parser = CommandParser(
        "/whitelist", "Autorise (ou non) un utilisateur à parler au bot.", USAGE_WHITELIST
    )
    whitelist_parser.add_argument(
        "action", nargs="?", default="list", choices=("add", "remove", "list"),
        help="action à effectuer (défaut : list)",
    )
    whitelist_parser.add_argument("user", nargs="?", help="ID Discord, mention ou nom")

    auth_parser = CommandParser("/auth", f"Niveau de droit d'un utilisateur (0-{MAX_LEVEL}).", USAGE_AUTH)
    auth_parser.add_argument("user", nargs="?", help="ID Discord, mention ou nom ; omis = liste")
    auth_parser.add_argument(
        "level", nargs="?", type=int, choices=range(MAX_LEVEL + 1),
        help="nouveau niveau ; omis = afficher le niveau courant",
    )

    relation_parser = CommandParser(
        "/relation",
        "Niveau de relation 0-100 dans la mémoire (un utilisateur ou, avec -a, tous).",
        USAGE_RELATION_FULL,
    )
    relation_parser.add_argument(
        "-a", "--all", action="store_true", help="tous les utilisateurs connus (noms, notes, whitelist)"
    )
    relation_parser.add_argument("value", nargs="?", help="nouveau niveau (0-100)")
    relation_parser.add_argument("user", nargs="?", help="ID Discord, mention ou nom")

    remember_parser = CommandParser(
        "/remember", "Demande au bot de retenir une information sur toi.", USAGE_REMEMBER
    )
    remember_parser.add_argument("text", nargs=argparse.REMAINDER, help="l'information à retenir")

    forget_parser = CommandParser("/forget", "Le bot oublie tout ce qu'il sait de toi.", "/forget")

    token_parser = CommandParser("/token", "Statistiques de tokens.", "/token [-a]")
    token_parser.add_argument("-a", "--all", action="store_true", help="total depuis les logs (toutes sessions)")

    quit_parser = CommandParser("/quit", "Arrêt propre du bot.", "/quit")

    return CommandRegistry([
        Command("/help", "liste des commandes", help_parser, handle_help, min_level=0),
        Command("/forget", "oublie tout ce que tu sais de moi", forget_parser, handle_forget, min_level=0),
        Command("/remember", "retiens une information sur moi", remember_parser, handle_remember,
                min_level=1, free_text=True),
        Command("/relation", "niveau de relation 0-100 avec un utilisateur", relation_parser,
                handle_relation, min_level=1),
        Command("/token", "statistiques de tokens", token_parser, handle_token, min_level=1),
        Command("/whitelist", "IDs autorisés à parler au bot", whitelist_parser, handle_whitelist, min_level=2),
        Command("/auth", "niveau de droit d'un utilisateur", auth_parser, handle_auth, min_level=OWNER_LEVEL),
        Command("/quit", "arrêt propre du bot", quit_parser, handle_quit, min_level=OWNER_LEVEL,
                require_slash=True),
    ])
