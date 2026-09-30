"""Native Discord slash commands.

Each slash command turns its typed options back into the line the terminal
would use (`/relation 70 123`) and runs it through the shared command
registry: handlers, permission levels and replies are the same everywhere.
Only the owner and whitelisted users may use them; replies are ephemeral
(visible to the invoker only).

Option names and descriptions are French: they are shown in Discord.
"""

import shlex
from typing import TYPE_CHECKING, Optional

import discord
from discord import app_commands

from .. import texts
from ..commands.framework import CommandContext, Source
from ..storage.access import MAX_LEVEL
from .pipeline import split_message

if TYPE_CHECKING:
    from ..app import App

USER_DESCRIPTION = "la personne concernée"


async def run_slash_command(
    interaction: discord.Interaction,
    app: "App",
    name: str,
    arguments: list[str],
    free_text: str | None = None,
    error: str | None = None,
) -> None:
    """Run `name` with `arguments` (or one raw `free_text` argument) for the invoker.

    `error` reports an invalid combination of options instead of running anything.
    """
    user = interaction.user
    if not app.can_talk(user.id):
        app.event_log.write("whitelist_denied", channel_id=interaction.channel_id, author_id=user.id, command=name)
        await interaction.response.send_message(texts.NOT_ALLOWED, ephemeral=True)
        return

    async def respond(text: str) -> None:
        for chunk in split_message(text):
            if interaction.response.is_done():
                await interaction.followup.send(chunk, ephemeral=True)
            else:
                await interaction.response.send_message(chunk, ephemeral=True)

    if error is not None:
        await respond(error)
        return

    line = f"{name} {free_text}" if free_text is not None else shlex.join([name, *arguments])
    ctx = CommandContext(app, Source.DISCORD, user.id, guild=interaction.guild, respond=respond)
    output = await app.commands.execute(app.commands.match(line), line, ctx)
    if output:
        await respond(output)


def register_slash_commands(tree: app_commands.CommandTree, app: "App") -> None:
    summaries = {command.name: command.summary for command in app.commands}

    def run(interaction: discord.Interaction, name: str, *arguments: str, free_text=None, error=None):
        return run_slash_command(interaction, app, name, list(arguments), free_text, error)

    def user_id(user: Optional[discord.User]) -> tuple[str, ...]:
        return (str(user.id),) if user is not None else ()

    @tree.command(name="help", description=summaries["/help"])
    @app_commands.rename(command="commande")
    @app_commands.describe(command="commande dont afficher l'aide")
    @app_commands.choices(command=[app_commands.Choice(name=name, value=name) for name in app.commands.names])
    async def help_command(interaction: discord.Interaction, command: Optional[str] = None) -> None:
        await run(interaction, "/help", *([command] if command else []))

    @tree.command(name="forget", description=summaries["/forget"])
    async def forget_command(interaction: discord.Interaction) -> None:
        await run(interaction, "/forget")

    @tree.command(name="remember", description=summaries["/remember"])
    @app_commands.rename(info="info")
    @app_commands.describe(info="l'information à retenir")
    async def remember_command(interaction: discord.Interaction, info: app_commands.Range[str, 1, 300]) -> None:
        await run(interaction, "/remember", free_text=info)

    @tree.command(name="relation", description=summaries["/relation"])
    @app_commands.rename(user="utilisateur", value="valeur", everyone="tous")
    @app_commands.describe(
        user=USER_DESCRIPTION,
        value="nouveau niveau (0-100) ; omis = afficher le niveau actuel",
        everyone="tous les utilisateurs connus (sans utilisateur)",
    )
    async def relation_command(
        interaction: discord.Interaction,
        user: Optional[discord.User] = None,
        value: Optional[app_commands.Range[int, 0, 100]] = None,
        everyone: bool = False,
    ) -> None:
        arguments = ["-a"] if everyone else []
        if value is not None:
            arguments.append(str(value))
        await run(interaction, "/relation", *arguments, *user_id(user))

    @tree.command(name="token", description=summaries["/token"])
    @app_commands.rename(everyone="tout")
    @app_commands.describe(everyone="total depuis les logs (toutes sessions)")
    async def token_command(interaction: discord.Interaction, everyone: bool = False) -> None:
        await run(interaction, "/token", *(["-a"] if everyone else []))

    @tree.command(name="whitelist", description=summaries["/whitelist"])
    @app_commands.rename(user="utilisateur")
    @app_commands.describe(action="action à effectuer (défaut : list)", user=USER_DESCRIPTION)
    @app_commands.choices(
        action=[app_commands.Choice(name=action, value=action) for action in ("list", "add", "remove")]
    )
    async def whitelist_command(
        interaction: discord.Interaction,
        action: str = "list",
        user: Optional[discord.User] = None,
    ) -> None:
        await run(interaction, "/whitelist", action, *user_id(user))

    @tree.command(name="auth", description=summaries["/auth"])
    @app_commands.rename(user="utilisateur", level="niveau")
    @app_commands.describe(
        user="omis = liste de tous les niveaux",
        level="nouveau niveau ; omis = afficher le niveau actuel",
    )
    async def auth_command(
        interaction: discord.Interaction,
        user: Optional[discord.User] = None,
        level: Optional[app_commands.Range[int, 0, MAX_LEVEL]] = None,
    ) -> None:
        if user is None and level is not None:
            await run(interaction, "/auth", error=texts.MISSING_USER)
            return
        await run(interaction, "/auth", *user_id(user), *([str(level)] if level is not None else []))

    @tree.command(name="quit", description=summaries["/quit"])
    async def quit_command(interaction: discord.Interaction) -> None:
        await run(interaction, "/quit")
