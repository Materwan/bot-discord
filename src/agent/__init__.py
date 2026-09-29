"""Agent package - Couche IA du bot."""

from .agent import create_agent, create_notes_agent
from .prompts import (
    load_prompt,
    load_user_instructions,
    find_user_id,
    describe_user,
    has_info,
    find_related_users,
    collect_cited_users,
    build_system_prompt,
    resolve_mentions,
    extract_prompt,
    ajouter_pings,
)
from .notes import (
    NOTES_SYSTEM_PROMPT,
    build_extraction_prompt,
    parse_insights,
    extract_insights,
)
from .usage import token_usage
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
    "create_notes_agent",
    # Tokens
    "token_usage",
    # Prompts
    "load_prompt",
    "load_user_instructions",
    "find_user_id",
    "describe_user",
    "has_info",
    "find_related_users",
    "collect_cited_users",
    "build_system_prompt",
    "resolve_mentions",
    "extract_prompt",
    "ajouter_pings",
    # Notes automatiques
    "NOTES_SYSTEM_PROMPT",
    "build_extraction_prompt",
    "parse_insights",
    "extract_insights",
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