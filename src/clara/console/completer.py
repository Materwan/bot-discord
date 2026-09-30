"""Auto-completion of command names and their arguments in the console."""

from __future__ import annotations

from typing import TYPE_CHECKING, Iterator

from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.document import Document

from ..storage.access import MAX_LEVEL

if TYPE_CHECKING:
    from ..app import App

SCORE_SUGGESTIONS = ["0", "50", "100"]


class CommandCompleter(Completer):
    def __init__(self, app: App):
        self.app = app

    def _user_suggestions(self, *extra_ids: list[int]) -> list[str]:
        suggestions = self.app.user_directory.names()
        for ids in extra_ids:
            suggestions += [str(user_id) for user_id in ids]
        return suggestions

    def argument_suggestions(self, command_name: str, position: int, words: list[str]) -> list[str]:
        """Values expected at argument `position` of a command (`words` = the whole line)."""
        app = self.app
        if command_name == "/whitelist":
            if position == 0:
                return ["add", "remove", "list"]
            if position == 1:
                return self._user_suggestions(app.whitelist.ids)
        elif command_name == "/relation":
            if position == 0:
                return ["-a", *SCORE_SUGGESTIONS]
            if position == 1:
                if words[1] == "-a":
                    return SCORE_SUGGESTIONS
                return self._user_suggestions(app.user_notes.user_ids())
        elif command_name == "/auth":
            if position == 0:
                return self._user_suggestions([app.permissions.owner_id], app.permissions.ids)
            if position == 1:
                return [str(level) for level in range(MAX_LEVEL + 1)]
        elif command_name == "/help":
            if position == 0:
                return app.commands.names
        elif command_name == "/token":
            if position == 0:
                return ["-a"]
        return []

    def get_completions(self, document: Document, complete_event) -> Iterator[Completion]:
        text = document.text_before_cursor
        words = text.split()
        ends_with_space = not text or text.endswith(" ")

        # First word: the command name ("/" optional in the console)
        if not words or (len(words) == 1 and not ends_with_space):
            prefix = words[0] if words else ""
            for name in self.app.commands.names:
                if name.startswith(prefix) or name[1:].startswith(prefix):
                    yield Completion(name, start_position=-len(prefix))
            return

        command = self.app.commands.match(words[0], allow_bare=True)
        if command is None:
            return
        if ends_with_space:
            position, prefix = len(words) - 1, ""
        else:
            position, prefix = len(words) - 2, words[-1]

        for option in self.argument_suggestions(command.name, position, words):
            if option.startswith(prefix):
                yield Completion(option, start_position=-len(prefix))
