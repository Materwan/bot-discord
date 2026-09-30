"""Tools the model can call while answering a message.

Every call runs inside a `ToolContext` describing the current message, so
tools act on the current channel and on the people involved in the message
only: the model cannot write notes about, or erase, arbitrary users.
"""

from __future__ import annotations

import asyncio
import inspect
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable

from pypdf import PdfReader

from ..settings import ALLOWED_UPLOAD_EXTENSIONS
from ..storage.channel_memory import ChannelMemory
from ..storage.user_notes import UserNotes

MAX_FILE_CHARACTERS = 30_000


@dataclass(frozen=True)
class ToolContext:
    channel_id: int
    author_id: int
    # Author and cited users: ID -> display name
    participants: dict[int, str]

    def resolve_participant(self, reference: Any) -> int | None:
        """ID of the participant named by `reference` (ID or display name)."""
        text = str(reference or "").strip().lstrip("@")
        if not text:
            return self.author_id
        if text.isdigit():
            return int(text) if int(text) in self.participants else None
        lowered = text.lower()
        for user_id, name in self.participants.items():
            if name.lower() == lowered:
                return user_id
        return None


ToolFunction = Callable[..., "str | Awaitable[str]"]


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    function: ToolFunction  # called as function(context, **arguments)
    parameters: dict[str, dict]
    required: tuple[str, ...] = ()

    @property
    def schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": self.parameters,
                    "required": list(self.required),
                },
            },
        }


class Toolbox:
    def __init__(self, tools: list[Tool]):
        self._tools = {tool.name: tool for tool in tools}
        self.schemas = [tool.schema for tool in tools]

    @property
    def names(self) -> list[str]:
        return list(self._tools)

    def bind(self, context: ToolContext) -> BoundToolbox:
        return BoundToolbox(self, context)

    async def run(self, name: str, arguments: dict, context: ToolContext) -> str:
        """Run a tool; failures are reported to the model as text, never raised."""
        tool = self._tools.get(name)
        if tool is None:
            return f"Error: unknown tool '{name}'."
        allowed = {key: value for key, value in arguments.items() if key in tool.parameters}
        try:
            result = tool.function(context, **allowed)
            if inspect.isawaitable(result):
                result = await result
            return str(result)
        except TypeError as error:
            return f"Error: invalid arguments for '{name}': {error}"
        except Exception as error:  # a broken tool must not break the answer
            return f"Error while running '{name}': {error}"


@dataclass(frozen=True)
class BoundToolbox:
    """A toolbox tied to the message being answered."""

    toolbox: Toolbox
    context: ToolContext

    @property
    def schemas(self) -> list[dict]:
        return self.toolbox.schemas

    async def run(self, name: str, arguments: dict) -> str:
        return await self.toolbox.run(name, arguments, self.context)


def read_upload(path: Path) -> str:
    """Text content of an uploaded file (blocking: run it in a thread)."""
    if path.suffix.lower() == ".pdf":
        pages = (page.extract_text() or "" for page in PdfReader(path).pages)
        return "\n".join(pages)
    return path.read_text(encoding="utf-8", errors="replace")


class BotTools:
    """The tool implementations, and the toolbox that exposes them to the model."""

    def __init__(self, user_notes: UserNotes, channel_memory: ChannelMemory, uploads_dir: Path):
        self.user_notes = user_notes
        self.channel_memory = channel_memory
        self.uploads_dir = uploads_dir

    async def read_file(self, context: ToolContext, filename: str) -> str:
        path = self.uploads_dir / Path(str(filename)).name  # no path traversal
        if path.suffix.lower() not in ALLOWED_UPLOAD_EXTENSIONS:
            return f"Error: files with the '{path.suffix}' extension cannot be read."
        if not path.is_file():
            return f"Error: file '{filename}' not found."
        text = await asyncio.to_thread(read_upload, path)
        if not text.strip():
            return "The file is empty or contains no extractable text."
        if len(text) > MAX_FILE_CHARACTERS:
            return text[:MAX_FILE_CHARACTERS] + "\n[... truncated]"
        return text

    def remember_user_info(self, context: ToolContext, info: str, user: str = "") -> str:
        user_id = context.resolve_participant(user)
        if user_id is None:
            return f"Refused: '{user}' is neither the author nor a person cited in the message."
        if self.user_notes.add_learned(user_id, str(info)):
            return f"Saved for {context.participants[user_id]}: {info}"
        return "Nothing saved: already known, empty, or an instruction rather than a fact."

    def forget_user_info(self, context: ToolContext) -> str:
        self.user_notes.forget(context.author_id)
        return f"Everything about {context.participants[context.author_id]} has been erased."

    def save_channel_memory(self, context: ToolContext, fact: str) -> str:
        if self.channel_memory.add(context.channel_id, str(fact)):
            return f"Saved for this channel: {fact}"
        return "Nothing saved: already known or empty."

    def toolbox(self) -> Toolbox:
        return Toolbox([
            Tool(
                name="read_file",
                description="Read a file the user attached to a message.",
                function=self.read_file,
                parameters={
                    "filename": {"type": "string", "description": "Saved file name, as given in the context."},
                },
                required=("filename",),
            ),
            Tool(
                name="remember_user_info",
                description=(
                    "Remember a lasting fact about the author of the message or a person cited in it."
                ),
                function=self.remember_user_info,
                parameters={
                    "info": {"type": "string", "description": "The fact to remember."},
                    "user": {
                        "type": "string",
                        "description": "Display name or ID of the person (default: the author).",
                    },
                },
                required=("info",),
            ),
            Tool(
                name="forget_user_info",
                description="Erase everything remembered about the author of the message, at their request.",
                function=self.forget_user_info,
                parameters={},
            ),
            Tool(
                name="save_channel_memory",
                description="Remember an important fact about the current channel.",
                function=self.save_channel_memory,
                parameters={"fact": {"type": "string", "description": "The fact to remember."}},
                required=("fact",),
            ),
        ])
