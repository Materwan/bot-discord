"""Full-screen terminal interface: active requests on top, command line at the bottom.

    ┌ active requests table (rich) ─────────────┐
    ├ command outputs (colored Markdown) ───────┤
    ├ > command line ───────────────────────────┤
    └ toolbar: commands · model · requests ─────┘

The screen is redrawn on input and whenever the request tracker changes,
never on a timer. If the terminal is not interactive (service, CI, pipe),
the interface is disabled and commands remain available from Discord.
"""

from __future__ import annotations

import asyncio
import shutil
from typing import TYPE_CHECKING

from prompt_toolkit import Application
from prompt_toolkit.application import get_app_or_none
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.formatted_text import ANSI, FormattedText
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.keys import Keys
from prompt_toolkit.layout import HSplit, Layout, Window
from prompt_toolkit.layout.controls import BufferControl, FormattedTextControl
from prompt_toolkit.layout.dimension import Dimension
from prompt_toolkit.styles import Style
from rich.markdown import Markdown

from .. import texts
from ..commands.framework import CommandContext, Source
from .completer import CommandCompleter
from .dashboard import Dashboard, render_ansi

if TYPE_CHECKING:
    from ..app import App

MAX_OUTPUT_LINES = 400
PAGE_SCROLL_LINES = 8
WHEEL_SCROLL_LINES = 3

STYLE = Style.from_dict({
    "toolbar": "bg:#17212b #cfd8dc",
    "input": "bg:#101820",
    "prompt": "bold #9ccc65",
})


def terminal_size() -> tuple[int, int]:
    """(columns, rows) of the terminal."""
    app = get_app_or_none()
    if app is not None:
        size = app.output.get_size()
        if size.columns and size.rows:
            return size.columns, size.rows
    columns, rows = shutil.get_terminal_size((100, 30))
    return max(40, columns), max(12, rows)


class Console:
    def __init__(self, app: App):
        self.app = app
        self.dashboard = Dashboard(app.tracker)
        self._output_lines: list[str] = []  # rendered ANSI lines
        self._scroll = 0  # lines scrolled up from the bottom
        self._width = 100
        self._running = False
        self._ui: Application | None = None
        self._ui_task: asyncio.Task | None = None
        self._tasks: set[asyncio.Task] = set()

    @property
    def running(self) -> bool:
        return self._running

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def start(self) -> None:
        """Start the interface as an asyncio task (call from inside the event loop)."""
        try:
            self._ui = self._build_ui()
        except Exception as error:  # not an interactive terminal
            print(texts.CONSOLE_UNAVAILABLE.format(error=error))
            return
        self._running = True
        self.app.tracker.on_change(self._redraw)
        self.print(texts.CONSOLE_READY)
        self._ui_task = asyncio.create_task(self._run_ui())

    async def _run_ui(self) -> None:
        try:
            await self._ui.run_async()
        except Exception as error:
            print(texts.CONSOLE_UNAVAILABLE.format(error=error))
        finally:
            self._running = False

    async def stop(self, timeout: float = 2.0) -> None:
        """Leave full-screen mode and give the terminal back."""
        self._running = False
        if self._ui is None or self._ui_task is None or self._ui_task.done():
            return
        self._ui.exit()
        try:
            await asyncio.wait_for(asyncio.shield(self._ui_task), timeout)
        except (asyncio.TimeoutError, Exception):
            pass

    # ------------------------------------------------------------------
    # Output panel
    # ------------------------------------------------------------------
    def print(self, markdown: str) -> None:
        """Append a Markdown message to the output panel."""
        if not markdown:
            return
        self._output_lines.extend(render_ansi(Markdown(markdown), self._width).split("\n"))
        del self._output_lines[:-MAX_OUTPUT_LINES]
        self._scroll = 0
        self._redraw()

    def _redraw(self) -> None:
        if self._ui is not None and self._running:
            self._ui.invalidate()

    def _spawn(self, coroutine) -> None:
        task = asyncio.get_running_loop().create_task(coroutine)
        self._tasks.add(task)  # keep a reference until done
        task.add_done_callback(self._tasks.discard)

    async def run_line(self, line: str) -> None:
        ctx = CommandContext(self.app, Source.CONSOLE, user_id=self.app.settings.owner_id)
        self.print(await self.app.commands.run(line, ctx))

    def _on_enter(self, buffer: Buffer) -> bool:
        line = buffer.text.strip()
        if line:
            self._spawn(self.run_line(line))
        return False  # False: clear the line (after the history is saved)

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------
    def _render_body(self) -> ANSI:
        columns, rows = terminal_size()
        self._width = columns
        body_rows = max(6, rows - 2)  # minus the command line and the toolbar
        table = self.dashboard.render(columns).split("\n")
        available = max(1, body_rows - len(table) - 1)  # minus a blank separator line

        end = len(self._output_lines) - self._scroll
        visible = self._output_lines[max(0, end - available) : max(0, end)]
        return ANSI("\n".join(table + ([""] if visible else []) + visible))

    def _render_toolbar(self) -> FormattedText:
        columns, _ = terminal_size()
        left = " " + " ".join(self.app.commands.names) + " "
        right = texts.CONSOLE_STATUS.format(model=self.app.llm.model, count=len(self.app.tracker))
        padding = " " * max(1, columns - len(left) - len(right))
        return FormattedText([("class:toolbar", left + padding + right)])

    def _build_ui(self, input=None, output=None) -> Application:
        buffer = Buffer(
            history=FileHistory(str(self.app.settings.console_history_file)),
            completer=CommandCompleter(self.app),
            complete_while_typing=True,
            accept_handler=self._on_enter,
            multiline=False,
        )
        buffer_control = BufferControl(buffer=buffer, focusable=True)
        layout = HSplit([
            Window(FormattedTextControl(self._render_body, show_cursor=False), height=Dimension(weight=1)),
            Window(
                buffer_control,
                height=1,
                style="class:input",
                get_line_prefix=lambda line_number, wrap_count: [("class:prompt", "> ")],
            ),
            Window(FormattedTextControl(self._render_toolbar), height=1),
        ])
        return Application(
            layout=Layout(layout, focused_element=buffer_control),
            key_bindings=self._key_bindings(buffer),
            style=STYLE,
            full_screen=True,  # alternate screen: keeps the scrollback clean
            mouse_support=True,
            input=input,
            output=output,
        )

    def _key_bindings(self, buffer: Buffer) -> KeyBindings:
        bindings = KeyBindings()

        def scroll(lines: int):
            def handler(event) -> None:
                self._scroll = max(0, self._scroll + lines)
                event.app.invalidate()
            return handler

        @bindings.add("c-d")  # EOF on an empty line: clean stop, like /quit
        def _quit(event) -> None:
            if not buffer.text:
                self._spawn(self.run_line("/quit"))

        @bindings.add("c-c")  # clear the line, never kill the bot
        def _clear(event) -> None:
            buffer.text = ""

        bindings.add("pageup")(scroll(PAGE_SCROLL_LINES))
        bindings.add("pagedown")(scroll(-PAGE_SCROLL_LINES))
        bindings.add(Keys.ScrollUp)(scroll(WHEEL_SCROLL_LINES))
        bindings.add(Keys.ScrollDown)(scroll(-WHEEL_SCROLL_LINES))
        return bindings
