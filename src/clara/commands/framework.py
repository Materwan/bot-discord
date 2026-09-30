"""Command framework shared by the terminal and Discord.

The same handlers run in both places:

    terminal:  /relation 70 Erwan                  (typed line, parsed here)
    Discord:   /relation valeur:70 utilisateur:@Erwan   (native slash command,
               turned into the same line by bot/slash_commands.py)

Each command has an argparse parser, a handler returning Markdown, and a
minimum permission level. The terminal is the owner's machine, so a console
context always has the owner level. Execution never raises: errors come back
as Markdown messages ("Usage : ..." / "**Erreur** : ...").
"""

from __future__ import annotations

import argparse
import inspect
import shlex
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Iterator

from .. import texts
from ..storage.access import OWNER_LEVEL

if TYPE_CHECKING:
    import discord

    from ..app import App


class Source(str, Enum):
    CONSOLE = "console"
    DISCORD = "discord"


class CommandError(Exception):
    """A message for the user (Markdown), not an internal failure."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def usage_error(usage: str, detail: str = "") -> CommandError:
    text = texts.USAGE.format(usage=usage)
    return CommandError(f"{text}\n\n{detail}" if detail else text)


def _translate_argparse(message: str) -> str:
    for english, french in texts.ARGPARSE_TRANSLATIONS:
        if english in message:
            return message.replace(english, french)
    return message


class CommandParser(argparse.ArgumentParser):
    """ArgumentParser raising CommandError instead of printing and exiting."""

    def __init__(self, prog: str, description: str, usage: str):
        super().__init__(prog=prog, description=description, usage=usage)

    def error(self, message: str) -> None:
        raise usage_error(self.usage, texts.ERROR.format(detail=_translate_argparse(message)))

    def exit(self, status: int = 0, message: str | None = None) -> None:
        raise CommandError(self.markdown_help())

    def print_help(self, file: Any = None) -> None:
        raise CommandError(self.markdown_help())

    def markdown_help(self) -> str:
        lines = [f"**{self.prog}** — {self.description}", "", f"```{self.usage}```", ""]
        for action in self._actions:
            if action.dest == "help" or not action.help:
                continue
            flag = " ".join(action.option_strings) or action.metavar or action.dest
            lines.append(f"- `{flag}` — {action.help}")
        return "\n".join(lines)


@dataclass
class CommandContext:
    app: App
    source: Source
    user_id: int | None = None
    guild: discord.Guild | None = None  # server the command was used in, if any
    # Sends a message right away (before the handler returns), if the front-end can
    respond: Callable[[str], Awaitable[None]] | None = None

    @property
    def level(self) -> int:
        if self.source is Source.CONSOLE:
            return OWNER_LEVEL
        return self.app.permissions.level(self.user_id)


Handler = Callable[[argparse.Namespace, CommandContext], "str | Awaitable[str]"]


@dataclass
class Command:
    name: str  # "/whitelist"
    summary: str
    parser: CommandParser
    handler: Handler
    min_level: int = OWNER_LEVEL
    require_slash: bool = False  # never match the bare form ("quit" is just a word)
    free_text: bool = False  # everything after the name is one raw argument

    def split_arguments(self, line: str) -> list[str]:
        """Arguments of `line`, without the command name.

        Free-text commands get the raw rest of the line (shlex would choke on
        "j'aime"); the others are split with shlex to support quotes, falling
        back to whitespace if a quote is never closed.
        """
        parts = line.strip().split(maxsplit=1)
        rest = parts[1] if len(parts) > 1 else ""
        if not rest:
            return []
        if self.free_text:
            return [rest]
        try:
            return shlex.split(rest)
        except ValueError:
            return rest.split()


def require_level(ctx: CommandContext, command_name: str, required: int) -> None:
    """Raise an "access denied" CommandError (and log it) if the level is too low."""
    level = ctx.level
    if level >= required:
        return
    ctx.app.event_log.write(
        "permission_denied",
        command=command_name,
        required=required,
        level=level,
        source=ctx.source.value,
        by=ctx.user_id,
    )
    raise CommandError(
        texts.ACCESS_DENIED.format(
            command=command_name,
            required=required,
            required_suffix=texts.level_suffix(required),
            level=level,
            level_suffix=texts.level_suffix(level),
        )
    )


class CommandRegistry:
    def __init__(self, commands: list[Command]):
        self._commands = {command.name: command for command in commands}

    def __iter__(self) -> Iterator[Command]:
        return iter(sorted(self._commands.values(), key=lambda command: command.name))

    @property
    def names(self) -> list[str]:
        return sorted(self._commands)

    def match(self, line: str, allow_bare: bool = False) -> Command | None:
        """Command named by the first word of `line` ("/x", or "x" if `allow_bare`)."""
        words = line.split(maxsplit=1)
        if not words:
            return None
        first = words[0].lower()
        if first.startswith("/"):
            return self._commands.get(first)
        if not allow_bare:
            return None
        command = self._commands.get(f"/{first}")
        return None if command is None or command.require_slash else command

    async def execute(self, command: Command, line: str, ctx: CommandContext) -> str:
        """Check the level, parse and run; always returns Markdown."""
        try:
            require_level(ctx, command.name, command.min_level)
            namespace = command.parser.parse_args(command.split_arguments(line))
            result = command.handler(namespace, ctx)
            if inspect.isawaitable(result):
                result = await result
            return result or ""
        except CommandError as error:
            return error.message
        except ValueError as error:
            return texts.SYNTAX_ERROR.format(error=error)
        except Exception as error:  # never show a traceback to the user
            return texts.INTERNAL_ERROR.format(kind=type(error).__name__, error=error)

    async def run(self, line: str, ctx: CommandContext) -> str:
        """Run a line typed in the terminal (the leading "/" is optional there)."""
        command = self.match(line, allow_bare=True)
        if command is None:
            words = line.split(maxsplit=1)
            return texts.UNKNOWN_COMMAND_NAMED.format(name=words[0] if words else line)
        return await self.execute(command, line, ctx)
