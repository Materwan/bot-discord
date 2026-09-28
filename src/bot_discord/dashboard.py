import asyncio
from rich.live import Live
from rich.table import Table
from rich.console import Console
from core import RequestTracker

class TerminalDashboard:
    """Affiche en temps réel les requêtes actives du bot dans le terminal."""

    def __init__(self, tracker: RequestTracker):
        self.tracker = tracker
        self.console = Console()
        self._live = None
        self._running = False

    def _generate_table(self) -> Table:
        table = Table(title="🤖 Bot Activity Monitor", show_header=True, header_style="bold magenta")
        table.add_column("Utilisateur", style="cyan", width=20)
        table.add_column("Demande", style="white", width=50)
        table.add_column("Phase", style="green", width=20)

        for _, state in self.tracker.get_active_requests():
            # Coloration de la phase
            phase_style = "green"
            if state.phase == "Tool Calling":
                phase_style = "yellow"
            elif state.phase == "Processing":
                phase_style = "blue"
            elif state.phase == "Answering":
                phase_style = "magenta"

            table.add_row(
                state.user_name,
                state.summary,
                f"[{phase_style}]{state.phase}[/{phase_style}]"
            )

        if not self.tracker._requests:
            table.add_row("---", "Aucune requête active", "---")

        return table

    async def run(self):
        """Boucle de rafraîchissement du dashboard."""
        self._running = True
        with Live(self._generate_table(), console=self.console, refresh_per_second=10) as live:
            self._live = live
            while self._running:
                live.update(self._generate_table())
                await asyncio.sleep(0.1)

    def stop(self):
        self._running = False
