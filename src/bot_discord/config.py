import os
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


def load_prompt() -> str:
    """Relu à chaque requête : on peut modifier le fichier sans redémarrer le bot."""
    try:
        return PROMPT_FILE.read_text(encoding="utf-8").strip() or DEFAULT_PROMPT
    except FileNotFoundError:
        return DEFAULT_PROMPT
