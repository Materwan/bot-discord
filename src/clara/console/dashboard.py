"""Active requests table (rich), rendered to ANSI for the console."""

from __future__ import annotations

import io

from rich.console import Console as RichConsole
from rich.markup import escape
from rich.table import Table

from .. import texts
from ..tracking import Phase, RequestTracker

PHASE_STYLES = {
    Phase.PROCESSING: "blue",
    Phase.TOOL_CALLING: "yellow",
    Phase.ANSWERING: "magenta",
}


def render_ansi(renderable, width: int | None = None) -> str:
    """Render any rich object (Markdown, Table...) to an ANSI string."""
    console = RichConsole(record=True, force_terminal=True, width=width, file=io.StringIO(), highlight=False)
    console.print(renderable)
    return console.export_text(styles=True)


class Dashboard:
    """Re-renders only when the tracker or the terminal width changed."""

    def __init__(self, tracker: RequestTracker):
        self.tracker = tracker
        self._cache_key: tuple[int, int | None] | None = None
        self._cached = ""

    def table(self) -> Table:
        # No emoji: the Windows console (OEM codepage) shows them as empty squares
        table = Table(title=texts.DASHBOARD_TITLE, header_style="bold magenta")
        table.add_column(texts.DASHBOARD_USER, style="cyan", max_width=20, no_wrap=True)
        table.add_column(texts.DASHBOARD_REQUEST, style="white", overflow="ellipsis")
        table.add_column(texts.DASHBOARD_PHASE, max_width=16, no_wrap=True)

        requests = self.tracker.active()
        for request in requests:
            style = PHASE_STYLES[request.phase]
            table.add_row(
                escape(request.user_name),
                escape(request.summary),
                f"[{style}]{request.phase.value}[/{style}]",
            )
        if not requests:
            table.add_row("---", texts.DASHBOARD_EMPTY, "---")
        return table

    def render(self, width: int | None = None) -> str:
        key = (self.tracker.version, width)
        if key != self._cache_key:
            self._cached = render_ansi(self.table(), width)
            self._cache_key = key
        return self._cached
