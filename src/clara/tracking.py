"""Requests being processed, shown live in the terminal dashboard."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable

SUMMARY_LENGTH = 50


class Phase(str, Enum):
    PROCESSING = "Processing"
    TOOL_CALLING = "Tool Calling"
    ANSWERING = "Answering"


@dataclass
class ActiveRequest:
    user_name: str
    summary: str
    phase: Phase = Phase.PROCESSING


def summarize(prompt: str) -> str:
    summary = prompt.replace("\n", " ")
    return summary[:SUMMARY_LENGTH] + "..." if len(summary) > SUMMARY_LENGTH else summary


class RequestTracker:
    """Active requests keyed by Discord message ID.

    `version` increases on every change, so the dashboard re-renders only
    when something actually changed; `on_change` listeners are notified too.
    """

    def __init__(self) -> None:
        self._requests: dict[int, ActiveRequest] = {}
        self._listeners: list[Callable[[], None]] = []
        self.version = 0

    def on_change(self, listener: Callable[[], None]) -> None:
        self._listeners.append(listener)

    def _changed(self) -> None:
        self.version += 1
        for listener in self._listeners:
            listener()

    def start(self, request_id: int, user_name: str, prompt: str) -> None:
        self._requests[request_id] = ActiveRequest(user_name, summarize(prompt))
        self._changed()

    def set_phase(self, request_id: int, phase: Phase) -> None:
        request = self._requests.get(request_id)
        if request is not None and request.phase is not phase:
            request.phase = phase
            self._changed()

    def finish(self, request_id: int) -> None:
        if self._requests.pop(request_id, None) is not None:
            self._changed()

    def active(self) -> list[ActiveRequest]:
        return list(self._requests.values())

    def __len__(self) -> int:
        return len(self._requests)
