"""Start the bot: `clara-discord` (or `python -m clara_discord`)."""

from __future__ import annotations

import asyncio
import logging
from logging.handlers import RotatingFileHandler

from .api import ClaraApi
from .bot import ClaraBot
from .settings import Settings, SettingsError


def configure_logging(settings: Settings) -> None:
    settings.log_file.parent.mkdir(parents=True, exist_ok=True)
    file = RotatingFileHandler(settings.log_file, maxBytes=5_000_000, backupCount=5, encoding="utf-8")
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.StreamHandler(), file],
        force=True,
    )
    logging.getLogger("discord").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)


async def main(settings: Settings) -> None:
    api = ClaraApi(settings.clara_url, settings.clara_token)
    bot = ClaraBot(settings, api)
    try:
        async with bot:
            await bot.start(settings.discord_token)
    finally:
        await api.close()


def run() -> None:
    try:
        settings = Settings.from_env()
    except SettingsError as error:
        raise SystemExit(str(error)) from None
    configure_logging(settings)
    try:
        asyncio.run(main(settings))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    run()
