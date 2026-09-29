import discord

class ToolAuthView(discord.ui.View):
    """Vue avec boutons pour autoriser ou refuser l'exécution d'un outil.

    `wrapper` est l'AuthorizationWrapper qui détient `pending_auths` : c'est par
    lui que les futures sont résolues (le bot lui-même n'a pas ce dictionnaire).
    """

    def __init__(self, bot, tool_name: str, wrapper=None):
        super().__init__(timeout=60)
        self.bot = bot
        self.tool_name = tool_name
        self.wrapper = wrapper

    def _resolve(self, interaction: discord.Interaction, authorized: bool) -> bool:
        """Renvoie True si la demande existait toujours et vient d'être tranchée."""
        wrapper = self.wrapper
        if wrapper is None:  # repli : bot.agent._auth_wrapper
            agent = getattr(self.bot, "agent", None)
            wrapper = getattr(agent, "_auth_wrapper", None)
        if wrapper is None:
            return False
        return wrapper.resolve_auth(interaction.user.id, self.tool_name, authorized)

    @discord.ui.button(label="Accepter", style=discord.ButtonStyle.green)
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self._resolve(interaction, authorized=True):
            await interaction.response.edit_message(
                content=f"✅ Outil `{self.tool_name}` autorisé.", view=None
            )
        else:
            await interaction.response.edit_message(
                content="❌ Cette demande d'autorisation a expiré ou a déjà été traitée.",
                view=None,
            )

    @discord.ui.button(label="Refuser", style=discord.ButtonStyle.red)
    async def deny(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self._resolve(interaction, authorized=False):
            await interaction.response.edit_message(
                content=f"🚫 Outil `{self.tool_name}` refusé.", view=None
            )
        else:
            await interaction.response.edit_message(
                content="❌ Cette demande d'autorisation a expiré ou a déjà été traitée.",
                view=None,
            )
