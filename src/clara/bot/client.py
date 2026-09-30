"""The Discord client: receives gateway events and forwards them to the pipeline."""

from __future__ import annotations

import traceback
from typing import TYPE_CHECKING

import discord
from discord import app_commands

from .. import texts
from .slash_commands import register_slash_commands

if TYPE_CHECKING:
    from ..app import App


class DiscordClient(discord.Client):
    def __init__(self, app: App):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True  # needed to recognize members cited by name
        allowed_mentions = discord.AllowedMentions(
            users=True, roles=False, everyone=False, replied_user=True
        )
        super().__init__(intents=intents, allowed_mentions=allowed_mentions)
        self.app = app
        self.tree = app_commands.CommandTree(self)
        self.tree.on_error = self.on_slash_command_error
        register_slash_commands(self.tree, app)

    async def setup_hook(self) -> None:
        """Publish the slash commands once per start (a single bulk update)."""
        try:
            synced = await self.tree.sync()
        except discord.HTTPException as error:
            self.app.event_log.write("slash_sync_error", error=repr(error))
            self.app.note(texts.SLASH_SYNC_FAILED.format(error=error))
            return
        self.app.event_log.write("slash_sync", commands=[command.name for command in synced])

    async def on_slash_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        trace = "".join(traceback.format_exception(error)).rstrip()
        command = interaction.command.name if interaction.command else "?"
        self.app.event_log.write("exception", event_method=f"/{command}", trace=trace)
        self.app.note(texts.UNHANDLED_EXCEPTION.format(event=f"/{command}", trace=trace))

    async def on_ready(self) -> None:
        self.app.note(texts.CONNECTED.format(user=self.user, model=self.app.llm.model))
        self.app.event_log.write("ready", user=str(self.user))

    async def on_typing(self, channel, user, when) -> None:
        self.app.pipeline.settler.record_typing(channel.id, user.id)

    async def on_message(self, message: discord.Message) -> None:
        await self.app.pipeline.handle(message)

    async def on_message_edit(self, before: discord.Message, after: discord.Message) -> None:
        await self.app.pipeline.handle_edit(before, after)

    async def on_message_delete(self, message: discord.Message) -> None:
        self.app.pipeline.settler.record_deletion(message.id)

    async def on_error(self, event_method: str, *args, **kwargs) -> None:
        trace = traceback.format_exc()
        self.app.event_log.write("exception", event_method=event_method, trace=trace)
        self.app.note(texts.UNHANDLED_EXCEPTION.format(event=event_method, trace=trace.rstrip()))
