import time
from dataclasses import dataclass, field
from typing import Iterable


@dataclass
class SessionStats:
    # None quand les stats sont reconstruites depuis les logs (pas de notion de session)
    started_at: float | None = field(default_factory=time.time)
    requests: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    def add(self, prompt_tokens: int, completion_tokens: int) -> None:
        self.requests += 1
        self.prompt_tokens += prompt_tokens
        self.completion_tokens += completion_tokens

    @classmethod
    def from_log(cls, entries: Iterable[dict]) -> "SessionStats":
        """Additionne les tokens de tous les événements "message" fournis."""
        stats = cls(started_at=None)
        for entry in entries:
            stats.add(
                entry.get("prompt_tokens") or 0,
                entry.get("completion_tokens") or 0,
            )
        return stats

    def summary(self) -> str:
        if self.started_at is None:
            head = "Total (logs)"
        else:
            head = f"Session : {(time.time() - self.started_at) / 60:.1f} min"
        return (
            f"{head} | {self.requests} requête(s) | "
            f"tokens : {self.total_tokens} "
            f"(prompt {self.prompt_tokens} + réponse {self.completion_tokens})"
        )
