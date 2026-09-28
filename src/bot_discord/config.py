import json
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(ROOT / ".env")

# --- Variables d'environnement ("or" : une variable vide retombe sur le défaut) ---
TOKEN = os.environ.get("DISCORD_BOT_TOKEN")
MODEL = os.environ.get("MODEL") or "gemma4:31b-cloud"
MEMORY_SIZE = int(os.environ.get("MEMORY_SIZE") or 20)
ALLOWED_BOT_IDS = {
    int(x) for x in (os.environ.get("ALLOWED_BOT_IDS") or "").split(",") if x.strip()
}

# --- Chemins ---
DATA_DIR = ROOT / "src" / "bot_discord" / "data"
LOG_FILE = DATA_DIR / "bot_log.jsonl"
MEMORY_FILE = DATA_DIR / "memory.json"
NOTES_FILE = DATA_DIR / "user_notes.json"
USER_NAME_ID = DATA_DIR / "user.json"
PROMPT_FILE = ROOT / "config" / "prompt_instruction"
USERS_FILE = ROOT / "config" / "users.json"

DEFAULT_PROMPT = "Tu es un bot Discord sympa. Réponds en français, de façon concise."


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def find_user_id(user_name: str) -> int | str | None:
    """ID Discord associé à un nom, ou None si inconnu."""
    return _read_json(USER_NAME_ID).get(user_name)


def load_user_instructions(user_id: int) -> str:
    """Relu à chaque requête, comme le prompt principal."""
    data = _read_json(USERS_FILE)
    return "\n".join((data.get(str(user_id)) or {}).get("instructions", []))


def load_prompt() -> str:
    """Relu à chaque requête : on peut modifier le fichier sans redémarrer le bot."""
    try:
        return PROMPT_FILE.read_text(encoding="utf-8").strip() or DEFAULT_PROMPT
    except FileNotFoundError:
        return DEFAULT_PROMPT
