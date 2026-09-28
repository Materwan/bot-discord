"""Hooks Agno pour le tracking des requêtes."""

from core import RequestTracker


def create_tracker_hooks(tracker: RequestTracker) -> dict:
    """
    Crée les hooks Agno pour mettre à jour le tracker.
    Agno appelle ces hooks automatiquement lors de l'exécution des outils.
    """
    def on_tool_start(tool_name: str, **kwargs):
        """Appelé avant l'exécution d'un outil."""
        for mid in tracker._requests:
            tracker.update_phase(mid, "Tool Calling")

    def on_tool_end(tool_name: str, result: str, **kwargs):
        """Appelé après l'exécution d'un outil."""
        for mid in tracker._requests:
            tracker.update_phase(mid, "Processing")

    return {
        "on_tool_start": on_tool_start,
        "on_tool_end": on_tool_end,
    }