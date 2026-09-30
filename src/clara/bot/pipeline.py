"""What happens to a Discord message that mentions the bot:

    filter (author allowed?) -> settle (author done typing/editing?)
    -> answer with the model -> learn from the message

Commands do not go through here: they are native slash commands (slash_commands.py).
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import TYPE_CHECKING

import discord

from .. import texts
from ..llm.prompt_builder import PromptRequest
from ..llm.tools import ToolContext
from ..settings import ALLOWED_UPLOAD_EXTENSIONS
from ..tracking import Phase
from .loop_guard import BotLoopGuard
from .mentions import add_pings, find_cited_members, replace_mentions_with_names, strip_bot_mention
from .settling import MessageSettler

if TYPE_CHECKING:
    from ..app import App

DISCORD_MESSAGE_LIMIT = 2000


def split_message(text: str, limit: int = DISCORD_MESSAGE_LIMIT) -> list[str]:
    """Chunks of at most `limit` characters, cut at a line break or space when possible."""
    chunks: list[str] = []
    while len(text) > limit:
        cut = text.rfind("\n", 0, limit)
        if cut <= 0:
            cut = text.rfind(" ", 0, limit)
        if cut <= 0:
            chunks.append(text[:limit])
            text = text[limit:]
        else:
            chunks.append(text[:cut])
            text = text[cut + 1 :]  # drop the separator itself
    chunks.append(text)
    return chunks


class MessagePipeline:
    def __init__(self, app: App):
        self.app = app
        self.settler = MessageSettler()
        self.loop_guard = BotLoopGuard()

    @property
    def bot_user(self) -> discord.ClientUser:
        return self.app.client.user

    # ------------------------------------------------------------------
    # Entry points (called by the Discord client)
    # ------------------------------------------------------------------
    async def handle_edit(self, before: discord.Message, after: discord.Message) -> None:
        self.settler.record_edit(after)
        # A mention added by editing counts as a new message for the bot
        if self.bot_user in after.mentions and self.bot_user not in before.mentions:
            await self.handle(after)

    async def handle(self, message: discord.Message) -> None:
        bot_user = self.bot_user
        author, channel_id = message.author, message.channel.id
        if author.id == bot_user.id:
            return
        if not author.bot:
            self.loop_guard.human_spoke(channel_id)
        if bot_user not in message.mentions:
            return
        if author.bot and author.id not in self.app.settings.allowed_bot_ids:
            return
        if not self.app.can_talk(author.id):
            # Silently ignored: only a log entry, never a public answer
            self.app.event_log.write("whitelist_denied", channel_id=channel_id, author_id=author.id)
            return
        if author.bot and not self.loop_guard.allow_bot_reply(channel_id):
            self.app.event_log.write("bot_loop_stopped", channel_id=channel_id, author_id=author.id)
            return

        has_text = bool(strip_bot_mention(message.content, bot_user.id))
        message = await self.settler.settle(message, expect_completion=not has_text)
        if message is None or bot_user not in message.mentions:
            return
        text = strip_bot_mention(message.content, bot_user.id)
        if not text:
            return
        self.settler.clear_typing(message.channel.id, author.id)

        if text.startswith("/"):
            # Commands are native slash commands now; "/..." never reaches the model
            await self._reply(message, texts.USE_SLASH_COMMANDS)
            return

        cited = find_cited_members(message, text, bot_user.id)
        # Bots can be tagged, but get no notes, relationship or tool access
        cited_people = [user for user in cited if not user.bot]
        cited_bots = [user for user in cited if user.bot]
        uploaded_files = await self._save_attachments(message)
        text = replace_mentions_with_names(text, message.mentions, bot_user.id)
        await self._answer(message, text, cited_people, cited_bots, uploaded_files)
        await self.app.insights.record([author, *cited_people], text, channel_id)

    # ------------------------------------------------------------------
    # Answering
    # ------------------------------------------------------------------
    async def _save_attachments(self, message: discord.Message) -> list[str]:
        """Save the readable attachments (named `<message_id>_<filename>`) concurrently."""
        uploads_dir = self.app.settings.uploads_dir
        attachments = [
            attachment
            for attachment in message.attachments
            if Path(attachment.filename).suffix.lower() in ALLOWED_UPLOAD_EXTENSIONS
        ]
        if not attachments:
            return []
        uploads_dir.mkdir(parents=True, exist_ok=True)
        names = [f"{message.id}_{Path(attachment.filename).name}" for attachment in attachments]
        await asyncio.gather(
            *(attachment.save(uploads_dir / name) for attachment, name in zip(attachments, names))
        )
        return names

    async def _answer(
        self,
        message: discord.Message,
        text: str,
        cited_people: list[discord.abc.User],
        cited_bots: list[discord.abc.User],
        uploaded_files: list[str],
    ) -> None:
        app = self.app
        author, channel = message.author, message.channel
        request_id = message.id

        messages = app.prompt_builder.build_messages(
            PromptRequest(
                author, text, channel.id, tuple(cited_people), tuple(uploaded_files), tuple(cited_bots)
            )
        )
        tools = app.toolbox.bind(
            ToolContext(
                channel_id=channel.id,
                author_id=author.id,
                participants={person.id: person.display_name for person in (author, *cited_people)},
            )
        )

        def on_tools_running(running: bool) -> None:
            app.tracker.set_phase(request_id, Phase.TOOL_CALLING if running else Phase.PROCESSING)

        app.tracker.start(request_id, author.display_name, text)
        started = time.perf_counter()
        try:
            try:
                async with channel.typing():
                    result = await app.llm.chat(messages, tools, on_tools_running=on_tools_running)
            except Exception as error:
                app.note(texts.LLM_ERROR.format(error=error))
                app.event_log.write("error", channel_id=channel.id, error=repr(error))
                await message.reply(texts.ANSWER_FAILED)
                return

            reply = result.content or "..."
            app.stats.add(result.prompt_tokens, result.completion_tokens)
            app.event_log.write(
                "message",
                channel_id=channel.id,
                guild_id=message.guild.id if message.guild else None,
                author_id=author.id,
                author=author.display_name,
                model=app.llm.model,
                prompt=text,
                response=reply,
                tools=result.tools_called,
                prompt_tokens=result.prompt_tokens,
                completion_tokens=result.completion_tokens,
                duration_s=round(time.perf_counter() - started, 2),
            )

            app.tracker.set_phase(request_id, Phase.ANSWERING)
            # Do not answer in the middle of the author's next message
            await self.settler.wait_until_not_typing(channel.id, author.id)
            members = message.guild.members if message.guild is not None else []
            await self._reply(message, add_pings(reply, app.user_directory, members, self.bot_user.id))
            app.channel_history.add(channel.id, author.display_name, text, reply)
        finally:
            app.tracker.finish(request_id)

    async def _reply(self, message: discord.Message, text: str) -> None:
        """Reply, split into several messages when over Discord's length limit."""
        first, *rest = split_message(text)
        await message.reply(first)
        for chunk in rest:
            await message.channel.send(chunk)
