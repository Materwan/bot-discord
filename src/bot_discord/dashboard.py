"""Tableau des requêtes actives du bot (rich, rendu en ANSI).

Le tableau est rendu en chaîne ANSI puis affiché dans le panneau du haut de
`console.py` : pas de `rich.Live`, qui se battrait avec l'application plein
écran pour le contrôle du terminal.
"""

import io

from rich.console import Console as RichConsole
from rich.markup import escape
from rich.table import Table

from core import RequestTracker


class TerminalDashboard:
    """Tableau « requêtes actives » rendu au format ANSI (rich)."""

    def __init__(self, tracker: RequestTracker):
        self.tracker = tracker

    def table(self) -> Table:
        table = Table(
            # Pas d'emoji ici : la console Windows (codepage OEM) le stocke en
            # U+FFFD et affiche un carré vide. Les accents et les traits de
            # cadre passent, eux, sans problème.
            title="Requêtes actives",
            show_header=True,
            header_style="bold magenta",
        )
        table.add_column("Utilisateur", style="cyan", max_width=20, no_wrap=True)
        table.add_column("Demande", style="white", overflow="ellipsis")
        table.add_column("Phase", style="green", max_width=16, no_wrap=True)

        active = False
        for _, state in self.tracker.get_active_requests():
            active = True
            # Coloration de la phase
            phase_style = "green"
            if state.phase == "Tool Calling":
                phase_style = "yellow"
            elif state.phase == "Processing":
                phase_style = "blue"
            elif state.phase == "Answering":
                phase_style = "magenta"

            table.add_row(
                escape(state.user_name),
                escape(state.summary),
                f"[{phase_style}]{escape(state.phase)}[/{phase_style}]",
            )

        if not active:
            table.add_row("---", "Aucune requête active", "---")

        return table

    def render(self, width: int | None = None) -> str:
        """Tableau en ANSI, prêt à être affiché par prompt_toolkit (`ANSI(...)`)."""
        console = RichConsole(
            record=True,
            force_terminal=True,
            width=width,
            file=io.StringIO(),
            highlight=False,
        )
        console.print(self.table())
        return console.export_text(styles=True)
