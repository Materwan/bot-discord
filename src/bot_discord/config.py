import os
import json
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(ROOT / ".env")

TOKEN = os.environ.get("DISCORD_BOT_TOKEN")
# "or" : une variable présente mais vide dans .env retombe sur la valeur par défaut
MODEL = os.environ.get("MODEL") or "gemma4:31b-cloud"
MEMORY_SIZE = int(os.environ.get("MEMORY_SIZE") or 20)

PROMPT_FILE = ROOT / "config" / "prompt_instruction"
DATA_DIR = ROOT / "src" / "bot_discord" / "data"
LOG_FILE = DATA_DIR / "bot_log.jsonl"
MEMORY_FILE = DATA_DIR / "memory.json"

DEFAULT_PROMPT = "Tu es un bot Discord sympa. Réponds en français, de façon concise."

ALLOWED_BOT_IDS = {
    int(x) for x in (os.environ.get("ALLOWED_BOT_IDS") or "").split(",") if x.strip()
}

USERS_FILE = ROOT / "config" / "users.json"
NOTES_FILE = DATA_DIR / "user_notes.json"


def load_user_instructions(user_id: int) -> str:
    """Relu à chaque requête, comme le prompt principal."""
    try:
        data = json.loads(USERS_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return ""
    return "\n".join((data.get(str(user_id)) or {}).get("instructions", []))


def load_prompt() -> str:
    """Relu à chaque requête : on peut modifier le fichier sans redémarrer le bot."""
    try:
        return PROMPT_FILE.read_text(encoding="utf-8").strip() or DEFAULT_PROMPT
    except FileNotFoundError:
        return DEFAULT_PROMPT
