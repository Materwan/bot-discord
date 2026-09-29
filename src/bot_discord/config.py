import json
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(ROOT / ".env")

# --- Variables d'environnement ("or" : une variable vide retombe sur le défaut) ---
TOKEN = os.environ.get("DISCORD_BOT_TOKEN")
MODEL = os.environ.get("MODEL") or "gemma4:31b-cloud"
BOT_OWNER_ID = 775822432631783445
MEMORY_SIZE = int(os.environ.get("MEMORY_SIZE") or 20)

ALLOWED_BOT_IDS = {
    int(x) for x in (os.environ.get("ALLOWED_BOT_IDS") or "").split(",") if x.strip()
}

# --- Chemins ---
DATA_DIR = ROOT / "src" / "bot_discord" / "data"
UPLOADS_DIR = DATA_DIR / "uploads"
LOG_FILE = DATA_DIR / "bot_log.jsonl"
MEMORY_FILE = DATA_DIR / "memory.json"
STATE_FILE = DATA_DIR / "bot_state.json"
NOTES_FILE = DATA_DIR / "user_notes.sqlite"
LEGACY_NOTES_FILE = DATA_DIR / "user_notes.json"
HISTORY_FILE = DATA_DIR / "history.json"
WHITELIST_FILE = DATA_DIR / "whitelist.json"
USER_NAME_ID = DATA_DIR / "user.json"
PROMPT_FILE = ROOT / "config" / "prompt_instruction.md"
USERS_FILE = ROOT / "config" / "users.json"

ALLOWED_EXTENSIONS = {".md", ".pdf", ".py", ".c", ".h"}

DEFAULT_PROMPT = "Tu es un bot Discord sympa. Réponds en français, de façon concise."

# --- Constantes pour les prompts et mentions ---
MAX_OTHERS = 3  # nombre max d'autres personnes injectées dans le prompt
MIN_NAME_LENGTH = 3  # évite les faux positifs sur les pseudos très courts

# --- Notes automatiques (faits + niveau de relation) ---
# AUTO_NOTES=0 dans le .env désactive l'appel LLM d'extraction après chaque réponse.
AUTO_NOTES = (os.environ.get("AUTO_NOTES") or "1").strip().lower() not in {
    "0",
    "false",
    "no",
    "off",
}
