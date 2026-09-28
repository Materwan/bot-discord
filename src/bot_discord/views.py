import discord
import asyncio

class ToolAuthView(discord.ui.View):
    """Vue avec boutons pour autoriser ou refuser l'exécution d'un outil."""

    def __init__(self, bot, tool_name: str):
        super().__init__(timeout=60)
        self.bot = bot
        self.tool_name = tool_name

    @discord.ui.button(label="Accepter", style=discord.ButtonStyle.green)
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        key = (interaction.user.id, self.tool_name)
        future = self.bot.pending_auths.pop(key, None)

        if future and not future.done():
            future.set_result(True)
            await interaction.response.edit_message(content=f"✅ Outil `{self.tool_name}` autorisé.", view=None)
        else:
            await interaction.response.edit_message(content="❌ Cette demande d'autorisation a expiré ou a déjà été traitée.", view=None)

    @discord.ui.button(label="Refuser", style=discord.ButtonStyle.red)
    async def deny(self, interaction: discord.Interaction, button: discord.ui.Button):
        key = (interaction.user.id, self.tool_name)
        future = self.bot.pending_auths.pop(key, None)

        if future and not future.done():
            future.set_result(False)
            await interaction.response.edit_message(content=f"🚫 Outil `{self.tool_name}` refusé.", view=None)
        else:
            await interaction.response.edit_message(content="❌ Cette demande d'autorisation a expiré ou a déjà été traitée.", view=None)
