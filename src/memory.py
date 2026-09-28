import json
from pathlib import Path


class Memory:
    """Historique de conversation par salon, persisté sur disque."""

    def __init__(self, path: Path, max_messages: int = 20):
        self.path = path
        self.max_messages = max(2, max_messages)
        self._data: dict[str, list[dict]] = {}
        self._load()

    def _load(self) -> None:
        try:
            self._data = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            self._data = {}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._data, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.path)  # écriture atomique

    def get(self, channel_id: int) -> list[dict]:
        return list(self._data.get(str(channel_id), []))

    def add_exchange(self, channel_id: int, user_content: str, reply: str) -> None:
        history = self._data.setdefault(str(channel_id), [])
        history.append({"role": "user", "content": user_content})
        history.append({"role": "assistant", "content": reply})
        del history[: -self.max_messages]
        self.save()
