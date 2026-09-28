from dataclasses import dataclass
from typing import Dict

@dataclass
class RequestState:
    user_name: str
    summary: str
    phase: str

class RequestTracker:
    """Gère l'état des requêtes actives pour le dashboard terminal."""

    def __init__(self):
        self._requests: Dict[int, RequestState] = {}

    def start_request(self, message_id: int, user_name: str, prompt: str):
        summary = (prompt[:50] + '...') if len(prompt) > 50 else prompt
        summary = summary.replace('\n', ' ')
        self._requests[message_id] = RequestState(
            user_name=user_name,
            summary=summary,
            phase="Processing"
        )

    def update_phase(self, message_id: int, phase: str):
        if message_id in self._requests:
            self._requests[message_id].phase = phase

    def complete_request(self, message_id: int):
        self._requests.pop(message_id, None)

    def get_active_requests(self):
        return self._requests.items()
