import json
from pathlib import Path


class Memory:
    """Mémoires persistantes par salon, distillées par le modèle."""

    def __init__(self, path: Path):
        self.path = path
        self._data: dict[str, list[str]] = {}
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

    def get(self, channel_id: int) -> list[str]:
        return self._data.get(str(channel_id), [])

    def add_memory(self, channel_id: int, content: str) -> None:
        history = self._data.setdefault(str(channel_id), [])
        if content not in history:
            history.append(content)
            self.save()
