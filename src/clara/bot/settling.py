"""Wait until an author has finished typing and editing before answering.

Typing and edit events only record timestamps; waiting sleeps exactly until
the quiet period is over instead of polling. The last edited version of a
message comes from the edit event itself, so no `fetch_message` API call is
needed to read it back.
"""

from __future__ import annotations

import asyncio
import time
from typing import Callable

import discord

TYPING_QUIET_SECONDS = 2.0  # no "typing" event for this long = stopped typing
EDIT_QUIET_SECONDS = 2.0  # no edit for this long = final version
MAX_WAIT_SECONDS = 60.0  # never wait longer than this
MAX_TYPING_ENTRIES = 1000  # prune old typing entries past this size


class MessageSettler:
    def __init__(self, clock: Callable[[], float] = time.monotonic):
        self._clock = clock
        self._last_typing: dict[tuple[int, int], float] = {}
        # Only messages currently being settled are tracked below
        self._pending: set[int] = set()
        self._last_edit: dict[int, float] = {}
        self._latest_version: dict[int, discord.Message] = {}
        self._deleted: set[int] = set()

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------
    def record_typing(self, channel_id: int, user_id: int) -> None:
        now = self._clock()
        self._last_typing[(channel_id, user_id)] = now
        if len(self._last_typing) > MAX_TYPING_ENTRIES:
            self._last_typing = {
                key: last for key, last in self._last_typing.items() if now - last < MAX_WAIT_SECONDS
            }

    def clear_typing(self, channel_id: int, user_id: int) -> None:
        self._last_typing.pop((channel_id, user_id), None)

    def record_edit(self, message: discord.Message) -> None:
        if message.id in self._pending:
            self._last_edit[message.id] = self._clock()
            self._latest_version[message.id] = message

    def record_deletion(self, message_id: int) -> None:
        if message_id in self._pending:
            self._deleted.add(message_id)

    # ------------------------------------------------------------------
    # Waiting
    # ------------------------------------------------------------------
    async def _wait_quiet(self, timestamps: dict, key, quiet_seconds: float, deadline: float) -> None:
        while True:
            now = self._clock()
            last = timestamps.get(key)
            if last is None or now - last >= quiet_seconds or now >= deadline:
                return
            await asyncio.sleep(min(last + quiet_seconds, deadline) - now)

    async def wait_until_not_typing(self, channel_id: int, user_id: int) -> None:
        deadline = self._clock() + MAX_WAIT_SECONDS
        await self._wait_quiet(self._last_typing, (channel_id, user_id), TYPING_QUIET_SECONDS, deadline)

    async def settle(self, message: discord.Message, expect_completion: bool = False) -> discord.Message | None:
        """Final version of `message` once its author is done, or None if it was deleted.

        `expect_completion` (e.g. a message with only a mention) grants an
        edit grace period even if no edit has happened yet.
        """
        message_id = message.id
        self._pending.add(message_id)
        if expect_completion:
            self._last_edit[message_id] = self._clock()
        try:
            deadline = self._clock() + MAX_WAIT_SECONDS
            await self._wait_quiet(
                self._last_typing, (message.channel.id, message.author.id), TYPING_QUIET_SECONDS, deadline
            )
            await self._wait_quiet(self._last_edit, message_id, EDIT_QUIET_SECONDS, deadline)
        finally:
            self._pending.discard(message_id)
            self._last_edit.pop(message_id, None)
            latest = self._latest_version.pop(message_id, message)
            deleted = message_id in self._deleted
            self._deleted.discard(message_id)
        return None if deleted else latest
