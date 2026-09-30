"""Interface terminal : tableau des requêtes + ligne de commande en bas.

Layout plein écran (écran alterné), du haut vers le bas :

    ┌ tableau des requêtes actives (rich) ──────────────────┐
    │ Requêtes actives                                        │
    ├ sorties des commandes (Markdown coloré) ───────────────┤
    │ **Whitelist (2)** : …                                    │
    ├ ligne de commande ─────────────────────────────────────┤
    │ > _                                                      │
    └ barre des tâches (commandes · modèle · requêtes) ──────┘

- `rich` affiche les sorties en Markdown coloré (et le tableau en ANSI) ;
- `prompt_toolkit` garde la saisie en bas, avec auto-complétion, historique
  et défilement (PageUp / PageDown / molette) ;
- `argparse` (voir `commands.py`) parse les commandes : la même couche sert
  au terminal et à Discord.
"""

from __future__ import annotations

import asyncio
import io
import shutil
from pathlib import Path

from prompt_toolkit import Application
from prompt_toolkit.application import get_app
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.formatted_text import ANSI, AnyFormattedText, FormattedText
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.keys import Keys
from prompt_toolkit.layout import HSplit, Layout, Window
from prompt_toolkit.layout.controls import BufferControl, FormattedTextControl
from prompt_toolkit.layout.dimension import D
from prompt_toolkit.styles import Style
from rich.console import Console as RichConsole
from rich.markdown import Markdown

from .commands import (
    Command,
    CommandContext,
    known_user_names,
    match_command,
    run_command,
)
from .config import BOT_OWNER_ID, DATA_DIR, MODEL
from core import MAX_LEVEL

MAX_OUTPUT_LINES = 400  # mémoire du panneau des sorties
REFRESH_INTERVAL = 0.1  # secondes entre deux rafraîchissements du tableau

STYLE = Style.from_dict(
    {
        "tb": "bg:#17212b #cfd8dc",
        "line": "bg:#101820",
        "prompt": "bold #9ccc65",
    }
)


def render_ansi(renderable, width: int | None = None) -> str:
    """Rend un objet rich (Markdown, Table…) en texte ANSI."""
    console = RichConsole(
        record=True,
        force_terminal=True,
        width=width,
        file=io.StringIO(),
        highlight=False,
    )
    console.print(renderable)
    return console.export_text(styles=True)


def terminal_size() -> tuple[int, int]:
    """(colonnes, lignes) du terminal, avec repli hors application."""
    try:
        size = get_app().output.get_size()
        if size.columns and size.rows:
            return size.columns, size.rows
    except Exception:  # pas d'application en cours (ou sortie « dummy »)
        pass
    columns, rows = shutil.get_terminal_size((100, 30))
    return max(40, columns), max(12, rows)


class CommandCompleter(Completer):
    """Auto-complétion : noms de commandes, actions, IDs et noms d'utilisateurs."""

    def __init__(self, bot, commands: dict[str, Command]):
        self.bot = bot
        self.commands = commands

    def _options(self, command: Command, slot: int, words: list[str]) -> list[str]:
        """Mots-clés attendus à la position `slot` de `command` (`words` = ligne entière)."""
        name = command.name
        if name == "/whitelist":
            if slot == 0:
                return ["add", "remove", "list"]
            if slot == 1:
                return [str(uid) for uid in self.bot.whitelist.ids] + list(known_user_names())
        elif name == "/set_auth":
            if slot == 0:
                return ["0", "1", "2"]
        elif name == "/set_relation":
            if slot == 0:
                return ["-a", "0", "50", "100"]
            if slot == 1:
                if len(words) > 1 and words[1] == "-a":
                    return ["0", "50", "100"]  # /set_relation -a <niveau>
                return list(known_user_names()) + [str(uid) for uid in self.bot.user_notes.ids()]
        elif name == "/auth":
            if slot == 0:
                return (
                    [str(BOT_OWNER_ID)]
                    + list(known_user_names())
                    + [str(uid) for uid in self.bot.rights.ids]
                )
            if slot == 1:
                return [str(level) for level in range(MAX_LEVEL + 1)]
        elif name == "/help":
            if slot == 0:
                return sorted(self.commands)
        elif name == "/token":
            if slot == 0:
                return ["-a"]
        return []

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor
        words = text.split()
        trailing_space = not text or text.endswith(" ")

        # Première position : on complète le nom de la commande
        if not words or (len(words) == 1 and not trailing_space):
            prefix = words[0] if words else ""
            for name in sorted(self.commands):
                if name.startswith(prefix):
                    yield Completion(name, start_position=-len(prefix))
                elif not prefix.startswith("/") and name[1:].startswith(prefix):
                    yield Completion(name, start_position=-len(prefix))
            return

        command = match_command(words[0], self.commands, allow_bare=True)
        if command is None:
            return

        if trailing_space:
            slot, prefix = len(words) - 1, ""
        else:
            slot, prefix = len(words) - 2, words[-1]
        slot = max(0, slot)

        for option in self._options(command, slot, words):
            if option.startswith(prefix):
                yield Completion(option, start_position=-len(prefix))


class Console:
    """Tableau des requêtes + ligne de commande en bas (prompt_toolkit + rich)."""

    def __init__(
        self,
        bot,
        commands: dict[str, Command] | None = None,
        history_path=None,
    ):
        self.bot = bot
        self.commands = commands if commands is not None else bot.commands
        self.history_path = Path(history_path or DATA_DIR / "console_history.txt")
        self._lines: list[str] = []  # lignes ANSI des sorties de commandes
        self._scroll = 0  # lignes remontées depuis la dernière
        self._width = 100  # largeur du terminal (mise à jour à chaque rendu)
        self._running = False
        self._app_running = False
        self._loop: asyncio.AbstractEventLoop | None = None
        self._app: Application | None = None
        self._buffer: Buffer | None = None

    @property
    def running(self) -> bool:
        """True tant que l'interface plein écran est active."""
        return self._running

    # ------------------------------------------------------------------
    # Cycle de vie
    # ------------------------------------------------------------------
    def start(self, loop: asyncio.AbstractEventLoop) -> None:
        """Lance l'interface (tâche asyncio : plus de thread bloqué sur input())."""
        self._loop = loop
        try:
            self._app = self._build_app()
        except Exception as exc:  # terminal non interactif (service, pipe, CI)
            # Pas d'interface : le bot tourne quand même, et les commandes
            # restent utilisables depuis Discord.
            print(f"[terminal] interface indisponible : {exc}")
            return
        self._running = True
        self.note(
            "**Terminal prêt** — tape `help` pour les commandes, "
            "`Ctrl+D` pour quitter."
        )
        loop.create_task(self._run_app())

    async def _run_app(self) -> None:
        self._app_running = True
        try:
            await self._app.run_async()
        except Exception as exc:  # terminal non interactif (service, CI)
            print(f"[terminal] interface indisponible : {exc}")
        finally:
            self._app_running = False
            self._running = False

    async def stop(self, timeout: float = 2.0) -> None:
        """Quitte l'interface plein écran et rend le terminal à l'appelant."""
        self._running = False
        if self._app is None:
            return
        try:
            self._app.exit()
        except Exception:
            return
        for _ in range(int(timeout / 0.05)):  # laisse l'application se refermer
            if not self._app_running:
                return
            await asyncio.sleep(0.05)

    # ------------------------------------------------------------------
    # Panneau des sorties
    # ------------------------------------------------------------------
    def push(self, text: str) -> None:
        """Ajoute un message (Markdown) en bas des sorties et redessine."""
        if not text:
            return
        ansi = render_ansi(Markdown(text), width=self._width)
        self._lines.extend(ansi.split("\n"))
        del self._lines[:-MAX_OUTPUT_LINES]
        self._scroll = 0
        if self._app is not None:
            self._app.invalidate()

    def note(self, text: str) -> None:
        """Message du bot dans le panneau (remplace un `print()`)."""
        self.push(text)

    async def run_line(self, line: str) -> None:
        """Exécute une ligne tapée et affiche le résultat (Markdown)."""
        ctx = CommandContext(bot=self.bot, source="console", user_id=BOT_OWNER_ID)
        self.push(await run_command(line, ctx, commands=self.commands))

    def _accept(self, buffer: Buffer) -> bool:
        """Entrée pressée : on lance la commande, prompt_toolkit vide ensuite la ligne."""
        line = buffer.text.strip()
        if line and self._loop is not None:
            self._loop.create_task(self.run_line(line))
        return False  # False = « reset » du buffer, mais APRÈS la sauvegarde de l'historique

    # ------------------------------------------------------------------
    # Rendu
    # ------------------------------------------------------------------
    def _render_body(self) -> AnyFormattedText:
        """Tableau en haut, sorties de commandes en dessous (défilables)."""
        columns, rows = terminal_size()
        self._width = columns

        # -1 : ligne de commande, -1 : barre des tâches
        body_rows = max(6, rows - 2)
        dashboard = self.bot.dashboard.render(width=columns).split("\n")
        available = max(1, body_rows - len(dashboard) - 1)  # -1 : ligne vide

        end = len(self._lines) - max(0, self._scroll)
        start = max(0, end - available)
        visible = self._lines[start : max(0, end)]

        blocks = dashboard + ([""] if visible else []) + visible
        return ANSI("\n".join(blocks))

    def _render_toolbar(self) -> FormattedText:
        """Barre des tâches en bas : commandes à gauche, état à droite."""
        columns, _ = terminal_size()
        left = " " + " ".join(sorted(self.commands)) + " "
        right = (
            f" modèle : {MODEL} · requêtes : {len(self.bot.tracker.get_active_requests())}"
            " · Ctrl+C vide · Ctrl+D quitte "
        )
        padding = max(1, columns - len(left) - len(right))
        return FormattedText(
            [
                ("class:tb", left),
                ("class:tb", " " * padding),
                ("class:tb", right),
            ]
        )

    # ------------------------------------------------------------------
    # Application prompt_toolkit
    # ------------------------------------------------------------------
    def _build_app(self, input=None, output=None) -> Application:
        buffer = Buffer(
            history=FileHistory(str(self.history_path)),
            completer=CommandCompleter(self.bot, self.commands),
            complete_while_typing=True,
            accept_handler=self._accept,
            multiline=False,
        )
        self._buffer = buffer
        buffer_control = BufferControl(buffer=buffer, focusable=True)

        body = Window(
            FormattedTextControl(self._render_body, focusable=False, show_cursor=False),
            height=D(weight=1),  # prend toute la place restante
        )
        line = Window(
            buffer_control,
            height=1,
            style="class:line",
            get_line_prefix=lambda lineno, wrap: [("class:prompt", "> ")],
        )
        toolbar = Window(
            FormattedTextControl(self._render_toolbar, focusable=False),
            height=1,
        )

        return Application(
            layout=Layout(HSplit([body, line, toolbar]), focused_element=buffer_control),
            key_bindings=self._key_bindings(),
            style=STYLE,
            full_screen=True,  # écran alterné : ne pollue pas le défilement
            mouse_support=True,
            refresh_interval=REFRESH_INTERVAL,
            input=input,
            output=output,
        )

    def _key_bindings(self) -> KeyBindings:
        buffer = self._buffer
        kb = KeyBindings()

        @kb.add("c-d")  # EOF : arrêt propre (comme /quit)
        def _(event):
            if not buffer.text and self._loop is not None:
                self._loop.create_task(self.run_line("/quit"))

        @kb.add("c-c")  # vide la ligne, ne tue pas le bot
        def _(event):
            buffer.text = ""

        @kb.add("pageup")
        def _(event):
            self._scroll += 8
            event.app.invalidate()

        @kb.add("pagedown")
        def _(event):
            self._scroll = max(0, self._scroll - 8)
            event.app.invalidate()

        @kb.add(Keys.ScrollUp)
        def _(event):
            self._scroll += 3
            event.app.invalidate()

        @kb.add(Keys.ScrollDown)
        def _(event):
            self._scroll = max(0, self._scroll - 3)
            event.app.invalidate()

        return kb
