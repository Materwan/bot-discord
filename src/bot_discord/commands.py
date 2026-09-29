"""Commandes partagées : le terminal et Discord exécutent le même code.

Chaque commande = un `argparse.ArgumentParser` (parsing stable, messages
d'erreur uniformes) + un handler qui renvoie du Markdown :

    terminal :  /set_relation 70 Erwan
    Discord  :  @NomDuBot /set_relation 70 Erwan

Les deux passent par `run_command()` ; seule la `CommandContext.source` change
(`"console"` ou `"discord"`). La console étant l'ordinateur du propriétaire,
`source="console"` vaut toujours propriétaire.

`run_command()` renvoie **toujours** du Markdown : soit le résultat, soit un
message d'erreur commençant par « Usage : … ». La console l'affiche avec
`rich.Markdown`, Discord l'envoie tel quel (mêmes sé Markdown).
"""

from __future__ import annotations

import argparse
import asyncio
import inspect
import json
import re
import shlex
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from core import MAX_RELATIONSHIP, MIN_RELATIONSHIP

from .config import BOT_OWNER_ID, USER_NAME_ID
from .stats import SessionStats

REMEMBER_PREFIX = "/remember"
FORGET_CMD = "/forget"
MAX_NOTE_LENGTH = 300

USAGE_WHITELIST = "/whitelist [add|remove|list] [user_id]"
USAGE_SET_AUTH = "/set_auth <0|1|2>"
USAGE_SET_RELATION = "/set_relation <0-100> <user_id|nom>"

Handler = Callable[[argparse.Namespace, "CommandContext"], "str | Awaitable[str]"]


# ----------------------------------------------------------------------
# Erreurs : jamais de traceback chez l'utilisateur
# ----------------------------------------------------------------------
class CommandError(Exception):
    """Message destiné à l'utilisateur (Markdown), pas une panne interne."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


# Traductions des messages les plus courants d'argparse (sinon anglais brut).
_ARGPARSE_FR = (
    ("the following arguments are required:", "argument(s) obligatoire(s) manquant(s) :"),
    ("expected one argument", "argument attendu après"),
    ("expected at least one argument", "au moins un argument attendu"),
    ("unrecognized arguments:", "argument(s) inconnu(s) :"),
    ("invalid choice:", "choix invalide :"),
    ("invalid int value:", "nombre entier invalide :"),
    ("ambiguous option:", "option ambiguë :"),
    ("not allowed with argument", "incompatible avec l'argument"),
)


def _translate(message: str) -> str:
    for english, french in _ARGPARSE_FR:
        if english in message:
            return message.replace(english, french)
    return message


def _usage(usage: str, detail: str = "") -> CommandError:
    """Erreur « Usage : … » : commence toujours par l'usage, le détail ensuite."""
    text = f"Usage : {usage}"
    if detail:
        text = f"{text}\n\n{detail}"
    return CommandError(text)


class CommandParser(argparse.ArgumentParser):
    """`ArgumentParser` qui lève `CommandError` au lieu de quitter Python.

    argparse appelle `error()` sur une mauvaise ligne de commande et
    `print_help()` / `exit()` pour `-h` : tout est redirigé vers
    `CommandError`, que `run_command()` convertit en Markdown.
    """

    def error(self, message: str) -> None:
        raise _usage(self.usage or self.format_usage().strip(),
                     f"**Erreur** : {_translate(message)}")

    def exit(self, status: int = 0, message: str | None = None) -> None:
        raise CommandError(self.build_help())

    def print_help(self, file: Any = None) -> None:
        raise CommandError(self.build_help())

    def build_help(self) -> str:
        """Aide `-h` en Markdown (usage dans un bloc de code + chaque argument)."""
        lines = [
            f"**{self.prog}** — {self.description or 'commande'}",
            "",
            f"```{self.usage or self.format_usage().strip()}```",
            "",
        ]
        for action in self._actions:
            if action.dest == "help" or action.help in (None, argparse.SUPPRESS):
                continue
            if action.option_strings:
                lines.append(f"- `{' '.join(action.option_strings)}` — {action.help}")
            else:
                lines.append(f"- `{action.metavar or action.dest}` — {action.help}")
        return "\n".join(lines)


# ----------------------------------------------------------------------
# Description d'une commande
# ----------------------------------------------------------------------
@dataclass
class CommandContext:
    """Ce dont les handlers ont besoin (jamais le message Discord en dur)."""

    bot: Any
    source: str = "console"  # "console" | "discord"
    user_id: int | None = None  # auteur du message Discord
    message: Any = None  # message d'origine (résolution des pseudos)
    markdown: bool = True  # False = sortie sans backticks (ancien mode terminal)


@dataclass
class Command:
    name: str  # "/whitelist"
    summary: str
    parser: CommandParser
    handler: Handler
    owner_only: bool = True
    require_slash: bool = False  # interdit la forme sans « / » (ex. /quit)
    free_text: bool = False  # dernier argument = texte brut (apostrophes…)


def is_owner(user_id: int | None) -> bool:
    return user_id == BOT_OWNER_ID


# ----------------------------------------------------------------------
# Noms <-> IDs (config/data/user.json)
# ----------------------------------------------------------------------
def known_user_names() -> dict[str, int]:
    """Nom d'affichage -> ID Discord (vide si le fichier est absent/cassé)."""
    try:
        data = json.loads(USER_NAME_ID.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    names: dict[str, int] = {}
    for name, value in data.items():
        try:
            names[str(name)] = int(value)
        except (TypeError, ValueError):
            continue
    return names


def resolve_user_id(reference: str, ctx: CommandContext | None = None) -> int | None:
    """ID Discord pour un argument écrit sous forme de mention, d'ID ou de nom."""
    reference = (reference or "").strip()
    if not reference:
        return None

    mention = re.fullmatch(r"<@!?(\d+)>", reference)
    if mention:
        return int(mention.group(1))
    if reference.isdigit():
        return int(reference)

    names = known_user_names()
    if reference in names:
        return names[reference]
    lowered = {name.lower(): user_id for name, user_id in names.items()}
    if reference.lower() in lowered:
        return lowered[reference.lower()]

    # Dernier recours (Discord) : le pseudo dans le serveur courant
    message = getattr(ctx, "message", None) if ctx else None
    guild = getattr(message, "guild", None)
    members = getattr(guild, "members", None) if guild is not None else None
    if isinstance(members, list):  # un mock n'est pas une liste de membres
        wanted = reference.lower()
        for member in members:
            for candidate in (getattr(member, "display_name", None), getattr(member, "name", None)):
                if candidate and str(candidate).lower() == wanted:
                    return member.id
    return None


def _user_label(user_id: int, reference: str = "") -> str:
    """« **Paul** (`123`) » : nom connu si possible, sinon l'ID tout seul."""
    if reference and not reference.isdigit() and not reference.startswith("<@"):
        return f"**{reference}** (`{user_id}`)"
    for name, known_id in known_user_names().items():
        if known_id == user_id:
            return f"**{name}** (`{user_id}`)"
    return f"`{user_id}`"


# ----------------------------------------------------------------------
# /whitelist : logique historique, partagée Discord <-> terminal
# ----------------------------------------------------------------------
def whitelist_action(bot, args: list[str], markdown: bool = True) -> str:
    """Logique de la commande /whitelist (inchangée).

    Usage : /whitelist [add|remove|list] <user_id>
    """

    def fmt(user_id: int) -> str:
        return f"`{user_id}`" if markdown else str(user_id)

    usage_add = "Usage : `/whitelist <add|remove> <user_id>`" if markdown else "Usage : /whitelist <add|remove> <user_id>"
    usage_all = "Usage : `/whitelist <add|remove|list> [user_id]`" if markdown else "Usage : /whitelist <add|remove|list> [user_id]"

    action = args[0] if args else "list"

    if action == "list":
        ids = bot.whitelist.ids
        if not ids:
            return "Whitelist vide : seul le propriétaire est autorisé."
        lignes = "\n".join(f"- {fmt(user_id)}" for user_id in ids)
        return f"Whitelist ({len(ids)}) :\n{lignes}"

    if action in ("add", "remove"):
        if len(args) != 2 or not args[1].isdigit():
            return usage_add
        user_id = int(args[1])
        if action == "add":
            if bot.whitelist.add(user_id):
                return f"{fmt(user_id)} ajouté à la whitelist."
            return f"{fmt(user_id)} est déjà dans la whitelist."
        if bot.whitelist.remove(user_id):
            return f"{fmt(user_id)} retiré de la whitelist."
        return f"{fmt(user_id)} n'était pas dans la whitelist."

    return usage_all


# ----------------------------------------------------------------------
# Handlers
# ----------------------------------------------------------------------
def _handle_help(namespace: argparse.Namespace, ctx: CommandContext) -> str:
    if namespace.commande:
        command = match_command(namespace.commande, ctx.bot.commands, allow_bare=True)
        if command is None:
            raise CommandError(f"**Commande inconnue** : `{namespace.commande}`.")
        return command.parser.build_help()

    # La liste est la même des deux côtés : tout ce qui marche dans le terminal
    # marche aussi depuis Discord (et inversement).
    lines = ["**Commandes disponibles**", ""]
    for command in sorted(ctx.bot.commands.values(), key=lambda c: c.name):
        owner = " *(propriétaire)*" if command.owner_only else ""
        lines.append(f"- `{command.name}` — {command.summary}{owner}")
    lines += [
        "",
        "Même syntaxe partout : dans le terminal (`/set_relation 70 Erwan`) "
        "et dans Discord (`@NomDuBot /set_relation 70 Erwan`).",
    ]
    return "\n".join(lines)


def _handle_whitelist(namespace: argparse.Namespace, ctx: CommandContext) -> str:
    args = [namespace.action] if namespace.action else []
    if namespace.user_id:
        args.append(namespace.user_id)
    return whitelist_action(ctx.bot, args, markdown=ctx.markdown)


def _handle_set_auth(namespace: argparse.Namespace, ctx: CommandContext) -> str:
    ctx.bot.state.set_auth_level(namespace.level)
    ctx.bot.logger.log(
        "set_auth", level=namespace.level, source=ctx.source, by=ctx.user_id
    )
    return f"Le niveau d'autorisation automatique a été fixé à **{namespace.level}**."


def _is_value(text: str) -> bool:
    return text.isdigit() and MIN_RELATIONSHIP <= int(text) <= MAX_RELATIONSHIP


def _parse_value(text: str) -> int:
    if not text.isdigit():
        raise _usage(USAGE_SET_RELATION, f"**Erreur** : `{text}` n'est pas un nombre.")
    value = int(text)
    if not MIN_RELATIONSHIP <= value <= MAX_RELATIONSHIP:
        raise _usage(
            USAGE_SET_RELATION,
            f"**Erreur** : `{text}` est hors bornes "
            f"({MIN_RELATIONSHIP}-{MAX_RELATIONSHIP}).",
        )
    return value


def _handle_set_relation(namespace: argparse.Namespace, ctx: CommandContext) -> str:
    """Fixe le niveau de relation 0-100 avec un utilisateur (ou l'affiche)."""
    from agent.prompts import relation_label

    given = [value for value in (namespace.value, namespace.user) if value]
    if not given:
        raise _usage(USAGE_SET_RELATION)
    if len(given) == 2 and not _is_value(given[0]) and _is_value(given[1]):
        given = [given[1], given[0]]  # ordre inversé : valeur après l'utilisateur

    if len(given) == 1:
        # Un seul mot : un petit nombre est une valeur orpheline (il manque
        # l'utilisateur) ; un ID ou un nom demande l'affichage courant.
        if _is_value(given[0]):
            raise _usage(USAGE_SET_RELATION, "**Erreur** : il manque l'utilisateur.")
        target: int | None = None
        reference = given[0]
    else:
        target, reference = _parse_value(given[0]), given[1]

    user_id = resolve_user_id(reference, ctx)
    if user_id is None:
        raise CommandError(
            f"**Utilisateur introuvable** : `{reference}` — donne son ID Discord "
            "ou son nom exact (voir `data/user.json`)."
        )

    label = _user_label(user_id, reference)
    previous = ctx.bot.user_notes.relationship(user_id)

    if target is None:
        return (
            f"Relation avec {label} : **{previous}/{MAX_RELATIONSHIP}** "
            f"— {relation_label(previous)}."
        )

    relationship = ctx.bot.user_notes.set_relationship(user_id, target)
    ctx.bot.logger.log(
        "set_relation",
        user_id=user_id,
        previous=previous,
        relationship=relationship,
        source=ctx.source,
        by=ctx.user_id,
    )
    return (
        f"Relation avec {label} : **{previous} → {relationship}** sur "
        f"{MAX_RELATIONSHIP} — {relation_label(relationship)}."
    )


def _handle_remember(namespace: argparse.Namespace, ctx: CommandContext) -> str:
    note = " ".join(namespace.text or []).strip()
    if not note:
        raise _usage(f"{REMEMBER_PREFIX} <info>")
    if ctx.user_id is None:
        raise CommandError("**Erreur** : commande reservée à Discord (il faut un auteur).")
    ctx.bot.user_notes.add_immutable(ctx.user_id, note[:MAX_NOTE_LENGTH])
    return "C'est noté !"


def _handle_forget(namespace: argparse.Namespace, ctx: CommandContext) -> str:
    if ctx.user_id is None:
        raise CommandError("**Erreur** : commande reservée à Discord (il faut un auteur).")
    ctx.bot.user_notes.clear(ctx.user_id)
    return "J'ai tout oublié te concernant."


async def _handle_token(namespace: argparse.Namespace, ctx: CommandContext) -> str:
    if namespace.all:
        # Lecture du fichier de logs hors de la boucle asyncio (peut être gros)
        entries = await asyncio.to_thread(lambda: list(ctx.bot.logger.read("message")))
        stats = SessionStats.from_log(entries)
    else:
        stats = ctx.bot.stats
    return f"```\n{stats.summary()}\n```"


async def _handle_quit(namespace: argparse.Namespace, ctx: CommandContext) -> str:
    if ctx.source == "discord" and ctx.message is not None:
        # Réponse AVANT la fermeture : après close() Discord n'accepte plus rien
        await ctx.message.reply("Arrêt du bot en cours…")
        await ctx.bot.close()  # fait sortir bot.start()
        return ""  # déjà répondu
    await ctx.bot.close()
    return "Arrêt du bot en cours…"


# ----------------------------------------------------------------------
# Registre
# ----------------------------------------------------------------------
def _parser(prog: str, description: str, usage: str) -> CommandParser:
    return CommandParser(prog=prog, description=description, usage=usage, add_help=True)


def build_commands() -> dict[str, Command]:
    """Toutes les commandes, dans les deux front-ends (terminal et Discord)."""
    help_parser = _parser("/help", "Liste les commandes disponibles.", "/help")
    help_parser.add_argument("commande", nargs="?", help="commande dont afficher l'aide")

    whitelist_parser = _parser("/whitelist", "Autorise (ou non) un utilisateur à parler au bot.", USAGE_WHITELIST)
    whitelist_parser.add_argument(
        "action", nargs="?", choices=("add", "remove", "list"),
        help="action à effectuer (défaut : list)",
    )
    whitelist_parser.add_argument("user_id", nargs="?", help="ID Discord à ajouter ou retirer")

    set_auth_parser = _parser("/set_auth", "Niveau d'autorisation automatique des outils.", USAGE_SET_AUTH)
    set_auth_parser.add_argument("level", type=int, choices=(0, 1, 2), help="0 = jamais, 1 = sans confirmation, 2 = toujours demander")

    set_relation_parser = _parser("/set_relation", "Niveau de relation 0-100 dans la mémoire.", USAGE_SET_RELATION)
    set_relation_parser.add_argument("value", nargs="?", help="nouveau niveau (0-100)")
    set_relation_parser.add_argument("user", nargs="?", help="user_id ou nom (data/user.json)")

    remember_parser = _parser(REMEMBER_PREFIX, "Demande au bot de retenir une information sur toi.", f"{REMEMBER_PREFIX} <info>")
    remember_parser.add_argument("text", nargs=argparse.REMAINDER, help="l'information à retenir")

    forget_parser = _parser(FORGET_CMD, "Le bot oublie tout ce qu'il sait de toi.", FORGET_CMD)

    token_parser = _parser("/token", "Statistiques de tokens.", "/token [-a]")
    token_parser.add_argument("-a", "--all", action="store_true", help="total depuis les logs (toutes sessions)")

    quit_parser = _parser("/quit", "Arrêt propre du bot.", "/quit")

    commands = [
        Command("/help", "liste des commandes", help_parser, _handle_help, owner_only=False),
        Command("/whitelist", "IDs autorisés à parler au bot", whitelist_parser, _handle_whitelist),
        Command("/set_auth", "niveau d'autorisation des outils (0|1|2)", set_auth_parser, _handle_set_auth),
        Command("/set_relation", "niveau de relation 0-100 avec un utilisateur", set_relation_parser, _handle_set_relation),
        Command(REMEMBER_PREFIX, "retiens une information sur moi", remember_parser, _handle_remember,
                owner_only=False, free_text=True),
        Command(FORGET_CMD, "oublie tout ce que tu sais de moi", forget_parser, _handle_forget,
                owner_only=False),
        Command("/token", "statistiques de tokens", token_parser, _handle_token),
        # « quit » sans slash ne doit jamais éteindre le bot depuis Discord
        Command("/quit", "arrêt propre du bot", quit_parser, _handle_quit, require_slash=True),
    ]
    return {command.name: command for command in commands}


# ----------------------------------------------------------------------
# Exécution
# ----------------------------------------------------------------------
def match_command(
    line: str, commands: dict[str, Command], allow_bare: bool = False
) -> Command | None:
    """Commande correspondant au début de `line` (« /x », ou « x » si autorisé)."""
    text = (line or "").strip()
    if not text:
        return None
    first = text.split(maxsplit=1)[0]
    if first.startswith("/"):
        return commands.get(f"/{first[1:].lower()}")
    if not allow_bare:
        return None
    command = commands.get(f"/{first.lower()}")
    if command is not None and command.require_slash:
        return None
    return command


def _split_arguments(command: Command, line: str) -> list[str]:
    """Arguments de `line`, nom de commande en moins.

    Texte brut pour les commandes à message libre (`/remember j'aime le café` :
    `shlex` casserait sur l'apostrophe), `shlex` ailleurs pour accepter les
    guillemets — avec repli si un guillemet n'est jamais fermé.
    """
    parts = line.strip().split(maxsplit=1)
    rest = parts[1] if len(parts) > 1 else ""
    if not rest:
        return []
    if command.free_text:
        return [rest]
    try:
        return shlex.split(rest)
    except ValueError:
        return rest.split()


async def execute_command(
    command: Command, line: str, ctx: CommandContext
) -> str:
    """Parse avec argparse puis exécute : renvoie du Markdown dans tous les cas."""
    try:
        argv = _split_arguments(command, line)
        namespace = command.parser.parse_args(argv)
        result = command.handler(namespace, ctx)
        if inspect.isawaitable(result):
            result = await result
        return result or ""
    except CommandError as exc:
        return exc.message
    except ValueError as exc:
        return f"**Erreur de syntaxe** : `{exc}`"
    except Exception as exc:  # jamais de traceback chez l'utilisateur
        return f"**Erreur** : `{type(exc).__name__} : {exc}`"


async def run_command(
    line: str, ctx: CommandContext, commands: dict[str, Command] | None = None
) -> str:
    """Parse + exécute une ligne tapée dans le terminal ou reçue sur Discord."""
    commands = commands if commands is not None else ctx.bot.commands
    command = match_command(line, commands, allow_bare=True)
    if command is None:
        first = line.strip().split(maxsplit=1)[0] if line.strip() else line
        return f"**Commande inconnue** : `{first}` — tape `help` pour la liste."
    return await execute_command(command, line, ctx)
