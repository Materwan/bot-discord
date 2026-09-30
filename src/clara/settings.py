"""Runtime settings: environment variables (.env) and file locations.

Everything is resolved once at startup into a frozen `Settings` object, which
is then passed explicitly to whatever needs it (no module-level globals).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_MODEL = "gemma4:31b-cloud"
DEFAULT_HISTORY_SIZE = 20

# Attachments saved to disk and readable by the `read_file` tool
ALLOWED_UPLOAD_EXTENSIONS = frozenset({".md", ".pdf", ".py", ".c", ".h"})

_FALSE_VALUES = {"0", "false", "no", "off"}


class SettingsError(RuntimeError):
    """A required setting is missing or malformed."""


def _parse_id_list(raw: str) -> frozenset[int]:
    return frozenset(int(part) for part in raw.split(",") if part.strip())


@dataclass(frozen=True)
class Settings:
    discord_token: str
    owner_id: int
    model: str = DEFAULT_MODEL
    ollama_host: str | None = None
    history_size: int = DEFAULT_HISTORY_SIZE
    auto_insights: bool = True
    allowed_bot_ids: frozenset[int] = field(default_factory=frozenset)
    root_dir: Path = PROJECT_ROOT

    # --- Folders ---
    @property
    def config_dir(self) -> Path:
        return self.root_dir / "config"

    @property
    def data_dir(self) -> Path:
        return self.root_dir / "data"

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    # --- Configuration files (edited by hand) ---
    @property
    def system_prompt_file(self) -> Path:
        return self.config_dir / "system_prompt.md"

    @property
    def user_instructions_file(self) -> Path:
        return self.config_dir / "user_instructions.json"

    # --- Data files (written by the bot) ---
    @property
    def user_notes_file(self) -> Path:
        return self.data_dir / "user_notes.sqlite"

    @property
    def channel_memory_file(self) -> Path:
        return self.data_dir / "channel_memory.json"

    @property
    def channel_history_file(self) -> Path:
        return self.data_dir / "channel_history.json"

    @property
    def whitelist_file(self) -> Path:
        return self.data_dir / "whitelist.json"

    @property
    def permissions_file(self) -> Path:
        return self.data_dir / "permissions.json"

    @property
    def known_users_file(self) -> Path:
        return self.data_dir / "known_users.json"

    @property
    def event_log_file(self) -> Path:
        return self.data_dir / "event_log.jsonl"

    @property
    def console_history_file(self) -> Path:
        return self.data_dir / "console_history.txt"

    @classmethod
    def from_env(cls, root_dir: Path = PROJECT_ROOT) -> Settings:
        """Load `<root_dir>/.env`, then read the environment (empty values use defaults)."""
        load_dotenv(root_dir / ".env")
        env = os.environ

        token = env.get("DISCORD_BOT_TOKEN", "").strip()
        if not token:
            raise SettingsError("DISCORD_BOT_TOKEN is missing (see .env.example)")
        owner_id = env.get("BOT_OWNER_ID", "").strip()
        if not owner_id.isdigit():
            raise SettingsError("BOT_OWNER_ID is missing or not a Discord ID (see .env.example)")

        return cls(
            discord_token=token,
            owner_id=int(owner_id),
            model=env.get("OLLAMA_MODEL") or DEFAULT_MODEL,
            ollama_host=env.get("OLLAMA_HOST") or None,
            history_size=int(env.get("HISTORY_SIZE") or DEFAULT_HISTORY_SIZE),
            auto_insights=(env.get("AUTO_INSIGHTS") or "1").strip().lower() not in _FALSE_VALUES,
            allowed_bot_ids=_parse_id_list(env.get("ALLOWED_BOT_IDS") or ""),
            root_dir=root_dir,
        )
