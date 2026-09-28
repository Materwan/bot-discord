"""Tools package for the agent."""

from .base import BaseTool, ToolLevel, ToolRegistry, AuthorizationWrapper, create_authorization_wrapper
from .weather import WeatherTool
from .user_memory import RememberUserInfoTool, ForgetUserInfoTool
from .channel_memory import SaveSalonMemoryTool
from .file_ops import ReadFileTool

__all__ = [
    "BaseTool",
    "ToolLevel",
    "ToolRegistry",
    "AuthorizationWrapper",
    "create_authorization_wrapper",
    "WeatherTool",
    "RememberUserInfoTool",
    "ForgetUserInfoTool",
    "SaveSalonMemoryTool",
    "ReadFileTool",
]


def create_tool_registry(
    user_notes: "UserNotes",
    memory: "Memory"
) -> ToolRegistry:
    """
    Crée et configure le registre d'outils avec toutes les dépendances injectées.
    """
    from core import UserNotes, Memory

    registry = ToolRegistry()

    # Outils sans dépendances
    registry.register(WeatherTool())

    # Outils avec dépendances
    registry.register(RememberUserInfoTool(user_notes))
    registry.register(ForgetUserInfoTool(user_notes))
    registry.register(SaveSalonMemoryTool(memory))
    registry.register(ReadFileTool())

    return registry