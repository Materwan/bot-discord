"""Factory pour créer l'agent Agno configuré."""

from agno.agent import Agent
from agno.models.ollama import Ollama

from .tools import create_tool_registry, create_authorization_wrapper, AuthorizationWrapper
from .prompts import load_prompt
from .notes import NOTES_SYSTEM_PROMPT
from core import Memory, UserNotes, BotState, RequestTracker
from bot_discord.config import MODEL
import discord


def create_agent(
    bot: discord.Client,
    memory: Memory,
    user_notes: UserNotes,
    state: BotState,
    tracker: RequestTracker
) -> Agent:
    """
    Crée et configure l'agent Agno avec tous ses outils.

    Args:
        bot: Instance du bot Discord (pour l'autorisation DM)
        memory: Instance Memory pour la mémoire des salons
        user_notes: Instance UserNotes pour les notes utilisateur
        state: Instance BotState pour le niveau d'autorisation
        tracker: Instance RequestTracker pour le dashboard

    Returns:
        Agent Agno configuré et prêt à l'emploi
    """
    # Création du registre d'outils
    tool_registry = create_tool_registry(user_notes, memory)

    # Wrapper d'autorisation
    auth_wrapper = AuthorizationWrapper(bot, tool_registry, state)

    # Outils Agno avec wrapper autorisation + tracking
    agno_tools = []
    for tool in tool_registry.get_all():
        # tool.to_agno_tool() porte le vrai nom de l'outil (et sa description) :
        # sans ça, tous les outils s'appellent "execute", Agno les confond et
        # get_level("execute") renvoie FREE -> aucune autorisation ne s'applique.
        wrapped = create_authorization_wrapper(
            tool.to_agno_tool(),
            auth_wrapper,
            tracker
        )
        agno_tools.append(wrapped)

    # Création de l'agent
    agent = Agent(
        model=Ollama(id=MODEL),
        tools=agno_tools,
        instructions=load_prompt(),
    )

    # On stocke des références pour l'autorisation depuis les vues Discord
    agent._auth_wrapper = auth_wrapper
    agent._tool_registry = tool_registry

    return agent


def create_notes_agent() -> Agent:
    """Agent dédié à l'extraction automatique des notes utilisateurs.

    Aucun outil : il ne fait que renvoyer du JSON (faits + ton de l'auteur),
    ce qui évite qu'une réponse Discord déclenche des écritures parasites.
    """
    return Agent(
        model=Ollama(id=MODEL),
        instructions=NOTES_SYSTEM_PROMPT,
    )