import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator


class JsonlLogger:
    """Écrit et relit un événement JSON par ligne."""

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def log(self, event: str, **fields) -> None:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": event,
            **fields,
        }
        with self._lock, self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def read(self, event: str | None = None) -> Iterator[dict]:
        """Relit le fichier de logs (optionnellement filtré par type d'événement).
        Les lignes illisibles sont ignorées."""
        try:
            with self._lock, self.path.open(encoding="utf-8") as f:
                lines = f.readlines()
        except FileNotFoundError:
            return
        for line in lines:
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event is None or entry.get("event") == event:
                yield entry
