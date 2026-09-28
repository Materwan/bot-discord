"""Agent package - Couche IA du bot."""

from .agent import create_agent
from .prompts import (
    load_prompt,
    load_user_instructions,
    find_user_id,
    describe_user,
    has_info,
    find_related_users,
    build_system_prompt,
    resolve_mentions,
    extract_prompt,
    ajouter_pings,
)
from .tools import (
    BaseTool,
    ToolLevel,
    ToolRegistry,
    AuthorizationWrapper,
    create_authorization_wrapper,
    create_tool_registry,
    WeatherTool,
    RememberUserInfoTool,
    ForgetUserInfoTool,
    SaveSalonMemoryTool,
    ReadFileTool,
)
from .hooks import create_tracker_hooks

__all__ = [
    # Agent factory
    "create_agent",
    # Prompts
    "load_prompt",
    "load_user_instructions",
    "find_user_id",
    "describe_user",
    "has_info",
    "find_related_users",
    "build_system_prompt",
    "resolve_mentions",
    "extract_prompt",
    "ajouter_pings",
    # Tools
    "BaseTool",
    "ToolLevel",
    "ToolRegistry",
    "AuthorizationWrapper",
    "create_authorization_wrapper",
    "create_tool_registry",
    "WeatherTool",
    "RememberUserInfoTool",
    "ForgetUserInfoTool",
    "SaveSalonMemoryTool",
    "ReadFileTool",
    # Hooks
    "create_tracker_hooks",
]