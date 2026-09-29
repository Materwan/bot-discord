"""Historique des N derniers échanges par salon (MEMORY_SIZE), persisté en JSON.

Distinct de `Memory` (faits mémorisés par salon) : c'est un contexte de
conversation, oublié dès qu'il dépasse `max_entries` échanges.
"""

import json
from pathlib import Path
import threading


class ChannelHistory:
    def __init__(self, path: Path, max_entries: int = 20, max_text: int = 300):
        self.path = path
        self.max_entries = max(1, int(max_entries))
        self.max_text = max_text
        self._lock = threading.RLock()
        self._data: dict[str, list[dict]] = {}
        self._load()

    # ------------------------------------------------------------------
    # Persistance
    # ------------------------------------------------------------------
    def _load(self) -> None:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return
        if isinstance(raw, dict):
            for channel_id, entries in raw.items():
                if isinstance(entries, list):
                    self._data[str(channel_id)] = [
                        e for e in entries if isinstance(e, dict)
                    ][-self.max_entries :]

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        tmp.replace(self.path)  # écriture atomique

    # ------------------------------------------------------------------
    # API
    # ------------------------------------------------------------------
    def add(self, channel_id: int, author: str, prompt: str, reply: str) -> None:
        """Ajoute un échange et oubli le plus ancien au delà de `max_entries`."""
        if not prompt and not reply:
            return
        entry = {
            "author": str(author)[:80],
            "prompt": str(prompt)[: self.max_text],
            "reply": str(reply)[: self.max_text],
        }
        with self._lock:
            entries = self._data.setdefault(str(channel_id), [])
            entries.append(entry)
            del entries[: -self.max_entries]
            self._save()

    def get(self, channel_id: int) -> list[dict]:
        """Échanges restants, du plus ancien au plus récent."""
        with self._lock:
            return [dict(e) for e in self._data.get(str(channel_id), [])]

    def clear(self, channel_id: int) -> None:
        with self._lock:
            self._data.pop(str(channel_id), None)
            self._save()
