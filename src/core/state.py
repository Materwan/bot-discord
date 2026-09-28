import json
from pathlib import Path
from bot_discord.config import DATA_DIR

STATE_FILE = DATA_DIR / "bot_state.json"

class BotState:
    """Gère l'état persistant du bot, notamment le niveau d'autorisation automatique."""

    def __init__(self):
        self.state = self._load()

    def _load(self) -> dict:
        try:
            if STATE_FILE.exists():
                return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
        return {"auto_auth_level": 0}

    def _save(self):
        STATE_FILE.write_text(json.dumps(self.state, indent=4), encoding="utf-8")

    def get_auth_level(self) -> int:
        """Retourne le niveau actuel d'autorisation automatique."""
        return self.state.get("auto_auth_level", 0)

    def set_auth_level(self, level: int):
        """Modifie le niveau d'autorisation et sauvegarde sur disque."""
        self.state["auto_auth_level"] = level
        self._save()
