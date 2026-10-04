"""Configuration, from the environment (and `.env`)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import load_dotenv


class SettingsError(Exception):
    """The configuration cannot work; the text says how to fix it."""


@dataclass(frozen=True)
class Settings:
    discord_token: str = field(repr=False)
    clara_url: str  # the Clara server, e.g. http://127.0.0.1:8765 or https://box.tail1234.ts.net
    clara_token: str = field(repr=False)  # a client token of CLARA_TOKENS on the server
    timezone: str | None = None  # IANA name for the date and time Clara is told; None: the server's
    data_dir: Path = Path("data")
    surface: str = "discord"

    @property
    def log_file(self) -> Path:
        return self.data_dir / "logs" / "clara-discord.log"

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        if env is None:
            load_dotenv()
            env = os.environ

        def text(key: str, default: str = "") -> str:
            return env.get(key, "").strip() or default

        discord_token = text("DISCORD_BOT_TOKEN")
        if not discord_token:
            raise SettingsError("DISCORD_BOT_TOKEN is missing: put the bot's token in .env")
        clara_token = text("CLARA_TOKEN")
        if not clara_token:
            raise SettingsError(
                "CLARA_TOKEN is missing: give the bot one of the server's client tokens (CLARA_TOKENS=discord:<token> "
                "on the server, CLARA_TOKEN=<token> here)"
            )
        timezone = text("CLARA_TIMEZONE") or None
        if timezone:
            try:
                ZoneInfo(timezone)
            except (ZoneInfoNotFoundError, ValueError):
                raise SettingsError(f"CLARA_TIMEZONE: unknown timezone {timezone!r} (e.g. Europe/Paris)") from None
        return cls(
            discord_token=discord_token,
            clara_url=text("CLARA_URL", "http://127.0.0.1:8765").rstrip("/"),
            clara_token=clara_token,
            timezone=timezone,
            data_dir=Path(text("CLARA_DISCORD_DATA_DIR", "data")),
        )
