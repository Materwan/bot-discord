import json
from pathlib import Path

# Repli si aucun chemin n'est fournis (le bot passe STATE_FILE issu de config)
DEFAULT_STATE_FILE = (
    Path(__file__).resolve().parents[2] / "src" / "bot_discord" / "data" / "bot_state.json"
)


class BotState:
    """Gère l'état persistant du bot, notamment le niveau d'autorisation automatique."""

    def __init__(self, path: Path = DEFAULT_STATE_FILE):
        self.path = Path(path)
        self.state = self._load()

    def _load(self) -> dict:
        try:
            if self.path.exists():
                return json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            pass
        return {"auto_auth_level": 0}

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.state, indent=4), encoding="utf-8")

    def get_auth_level(self) -> int:
        """Retourne le niveau actuel d'autorisation automatique."""
        return self.state.get("auto_auth_level", 0)

    def set_auth_level(self, level: int):
        """Modifie le niveau d'autorisation et sauvegarde sur disque."""
        self.state["auto_auth_level"] = level
        self._save()
