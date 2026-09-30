"""Application wiring: builds every service once, runs the bot and the console."""

from __future__ import annotations

import asyncio
import logging
import os
import sys

from . import texts
from .bot.client import DiscordClient
from .bot.pipeline import MessagePipeline
from .commands.handlers import build_command_registry
from .console.app import Console
from .llm.client import LlmClient
from .llm.insights import InsightRecorder
from .llm.prompt_builder import PromptBuilder
from .llm.tools import BotTools
from .settings import Settings, SettingsError
from .storage.access import Permissions, Whitelist
from .storage.channel_history import ChannelHistory
from .storage.channel_memory import ChannelMemory
from .storage.event_log import EventLog, TokenStats
from .storage.user_directory import UserDirectory
from .storage.user_notes import UserNotes
from .tracking import RequestTracker


class App:
    """Owns the services; commands, pipeline and console reach them through it."""

    def __init__(self, settings: Settings, llm: LlmClient | None = None):
        self.settings = settings

        # Storage
        self.user_notes = UserNotes(settings.user_notes_file)
        self.channel_memory = ChannelMemory(settings.channel_memory_file)
        self.channel_history = ChannelHistory(settings.channel_history_file, settings.history_size)
        self.whitelist = Whitelist(settings.whitelist_file)
        self.permissions = Permissions(settings.permissions_file, settings.owner_id)
        self.user_directory = UserDirectory(settings.known_users_file)
        self.event_log = EventLog(settings.event_log_file)
        self.stats = TokenStats()
        self.tracker = RequestTracker()

        # Language model
        self.llm = llm or LlmClient(settings.model, settings.ollama_host)
        self.prompt_builder = PromptBuilder(
            settings.owner_id,
            settings.system_prompt_file,
            settings.user_instructions_file,
            self.user_notes,
            self.channel_memory,
            self.channel_history,
        )
        self.toolbox = BotTools(self.user_notes, self.channel_memory, settings.uploads_dir).toolbox()
        self.insights = InsightRecorder(self.llm, self.user_notes, self.event_log, settings.auto_insights)

        # Front-ends
        self.commands = build_command_registry()
        self.client = DiscordClient(self)
        self.pipeline = MessagePipeline(self)
        self.console: Console | None = None

    def can_talk(self, user_id: int) -> bool:
        """The owner and whitelisted users get answers; everybody else is ignored."""
        return self.permissions.is_owner(user_id) or user_id in self.whitelist

    def note(self, markdown: str) -> None:
        """Show a message to the operator (console panel, or stdout without console)."""
        if self.console is not None and self.console.running:
            self.console.print(markdown)
        else:
            print(markdown)

    async def stop(self) -> None:
        await self.client.close()

    def close(self) -> None:
        """Final save and session summary, whatever the reason of the stop."""
        self.user_notes.close()
        self.event_log.write(
            "stop",
            requests=self.stats.requests,
            prompt_tokens=self.stats.prompt_tokens,
            completion_tokens=self.stats.completion_tokens,
        )
        print(
            texts.TOKENS_SUMMARY.format(
                head=texts.TOKENS_SESSION.format(minutes=self.stats.minutes_elapsed or 0),
                requests=self.stats.requests,
                total=self.stats.total_tokens,
                prompt=self.stats.prompt_tokens,
                completion=self.stats.completion_tokens,
            )
        )

    async def serve(self) -> None:
        self.event_log.write("start", model=self.llm.model)
        self.console = Console(self)
        self.console.start()
        try:
            async with self.client:
                await self.client.start(self.settings.discord_token)
        finally:  # /quit, Ctrl+D, Ctrl+C or crash
            await self.console.stop()  # give the terminal back before the summary
            self.close()


def run() -> None:
    try:
        settings = Settings.from_env()
    except SettingsError as error:
        raise SystemExit(str(error)) from None

    # discord.py INFO logs would be printed over the full-screen interface
    logging.getLogger("discord").setLevel(logging.WARNING)

    try:
        asyncio.run(App(settings).serve())
    except KeyboardInterrupt:
        print(texts.INTERRUPTED)
    sys.stdout.flush()
    # Leftover prompt_toolkit / aiohttp threads must not delay the exit
    os._exit(0)
