"""Base classes and utilities for agent tools."""

from abc import ABC, abstractmethod
from enum import IntEnum
from functools import wraps
from typing import Any, Callable, Awaitable
import asyncio

import discord

from core import BotState
from bot_discord.config import BOT_OWNER_ID
from bot_discord.views import ToolAuthView


class ToolLevel(IntEnum):
    """Niveau d'autorisation requis pour un outil."""
    FREE = 0      # Pas d'autorisation nécessaire
    READ = 1      # Lecture seule (ex: read_file)
    WRITE = 2     # Écriture / modification (ex: remember, forget, save_memory)


class BaseTool(ABC):
    """Classe de base pour tous les outils de l'agent."""

    # À surcharger dans les sous-classes
    name: str
    description: str
    level: ToolLevel = ToolLevel.FREE

    @abstractmethod
    async def execute(self, **kwargs) -> str:
        """Exécute l'outil et retourne le résultat."""
        pass

    def to_agno_tool(self) -> Callable[..., Awaitable[str]]:
        """Convertit l'outil en fonction compatible Agno."""
        @wraps(self.execute)
        async def wrapper(**kwargs) -> str:
            return await self.execute(**kwargs)
        wrapper.__name__ = self.name
        wrapper.__doc__ = self.description
        return wrapper


class ToolRegistry:
    """Registre centralisé des outils de l'agent."""

    def __init__(self):
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        """Enregistre un outil."""
        self._tools[tool.name] = tool

    def get(self, name: str) -> BaseTool | None:
        """Récupère un outil par son nom."""
        return self._tools.get(name)

    def get_all(self) -> list[BaseTool]:
        """Retourne tous les outils enregistrés."""
        return list(self._tools.values())

    def get_agno_tools(self) -> list[Callable[..., Awaitable[str]]]:
        """Retourne la liste des outils sous forme de fonctions Agno."""
        return [tool.to_agno_tool() for tool in self._tools.values()]

    def get_level(self, name: str) -> ToolLevel:
        """Retourne le niveau d'autorisation d'un outil."""
        tool = self._tools.get(name)
        return tool.level if tool else ToolLevel.FREE


class AuthorizationWrapper:
    """Gère l'autorisation des outils via DM au propriétaire du bot."""

    def __init__(self, bot: discord.Client, registry: ToolRegistry, state: BotState):
        self.bot = bot
        self.registry = registry
        self.state = state
        self.pending_auths: dict[tuple[int, str], asyncio.Future] = {}

    async def check_and_request(self, tool_name: str) -> str | None:
        """
        Vérifie l'autorisation pour un outil.
        Retourne un message d'erreur si refusé/expiré, None si autorisé.
        """
        required_level = self.registry.get_level(tool_name)
        current_auth_level = self.state.get_auth_level()

        if required_level <= current_auth_level:
            return None  # Autorisé automatiquement

        # Demande d'autorisation via DM
        future = asyncio.get_running_loop().create_future()
        key = (BOT_OWNER_ID, tool_name)
        self.pending_auths[key] = future

        try:
            owner = await self.bot.fetch_user(BOT_OWNER_ID)
            view = ToolAuthView(self.bot, tool_name, wrapper=self)
            await owner.send(
                f"⚠️ **Demande d'autorisation**\n\n"
                f"L'agent souhaite utiliser l'outil `{tool_name}` (Niveau {required_level}), "
                f"mais votre niveau d'autorisation automatique est à {current_auth_level}.\n\n"
                "Acceptez-vous l'exécution ?",
                view=view
            )

            # Attente de la réponse avec timeout de 60s
            authorized = await asyncio.wait_for(future, timeout=60.0)
            if not authorized:
                return "L'exécution de l'outil a été refusée par l'administrateur."
            return None  # Autorisé

        except asyncio.TimeoutError:
            return "L'autorisation a expiré. L'exécution de l'outil a été annulée."
        except Exception as e:
            return f"Erreur lors de la demande d'autorisation : {e}"
        finally:
            self.pending_auths.pop(key, None)

    def resolve_auth(self, user_id: int, tool_name: str, authorized: bool) -> bool:
        """Résout une réponse d'autorisation (appelé par ToolAuthView)."""
        key = (user_id, tool_name)
        future = self.pending_auths.pop(key, None)
        if future and not future.done():
            future.set_result(authorized)
            return True
        return False


def create_authorization_wrapper(
    tool_func: Callable[..., Awaitable[str]],
    auth_wrapper: AuthorizationWrapper,
    tracker: "RequestTracker" = None
) -> Callable[..., Awaitable[str]]:
    """
    Crée un wrapper qui gère l'autorisation et le tracking pour un outil.
    Utilisé pour convertir les méthodes d'outils en fonctions Agno compatibles.
    """
    @wraps(tool_func)
    async def wrapper(*args, **kwargs) -> str:
        tool_name = tool_func.__name__

        # Vérification autorisation
        auth_error = await auth_wrapper.check_and_request(tool_name)
        if auth_error:
            return auth_error

        # Tracking : phase "Tool Calling"
        if tracker:
            for mid in tracker._requests:
                tracker.update_phase(mid, "Tool Calling")

        # Exécution
        result = await tool_func(*args, **kwargs)

        # Tracking : retour à "Processing"
        if tracker:
            for mid in tracker._requests:
                tracker.update_phase(mid, "Processing")

        return result

    return wrapper