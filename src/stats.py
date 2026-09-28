import time
from dataclasses import dataclass, field


@dataclass
class SessionStats:
    started_at: float = field(default_factory=time.time)
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

    def summary(self) -> str:
        minutes = (time.time() - self.started_at) / 60
        return (
            f"Session : {minutes:.1f} min | {self.requests} requête(s) | "
            f"tokens : {self.total_tokens} "
            f"(prompt {self.prompt_tokens} + réponse {self.completion_tokens})"
        )
