"""Ollama chat client with a native tool-calling loop."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable

from ollama import AsyncClient

if TYPE_CHECKING:
    from .tools import BoundToolbox

MAX_TOOL_ROUNDS = 5


@dataclass
class ChatResult:
    content: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    tools_called: list[str] = field(default_factory=list)


class LlmClient:
    def __init__(
        self,
        model: str,
        host: str | None = None,
        client: Any = None,
        max_tool_rounds: int = MAX_TOOL_ROUNDS,
    ):
        self.model = model
        self.max_tool_rounds = max_tool_rounds
        self._client = client if client is not None else AsyncClient(host=host)

    async def chat(
        self,
        messages: list[dict],
        tools: BoundToolbox | None = None,
        json_output: bool = False,
        on_tools_running: Callable[[bool], None] | None = None,
    ) -> ChatResult:
        """Send `messages` and return the final answer with the tokens used.

        When the model asks for tools, they are run and their output is sent
        back, up to `max_tool_rounds` times; the last round offers no tools
        so the model has to answer. `on_tools_running(True/False)` brackets
        each batch of tool calls (used for the dashboard phase).
        """
        conversation = list(messages)
        result = ChatResult()

        for round_number in range(self.max_tool_rounds + 1):
            offer_tools = tools is not None and round_number < self.max_tool_rounds
            response = await self._client.chat(
                model=self.model,
                messages=conversation,
                tools=tools.schemas if offer_tools else None,
                format="json" if json_output else None,
            )
            result.prompt_tokens += response.prompt_eval_count or 0
            result.completion_tokens += response.eval_count or 0

            message = response.message
            if not (offer_tools and message.tool_calls):
                result.content = (message.content or "").strip()
                return result

            conversation.append(message)
            if on_tools_running:
                on_tools_running(True)
            try:
                for call in message.tool_calls:
                    name = call.function.name
                    output = await tools.run(name, call.function.arguments or {})
                    result.tools_called.append(name)
                    conversation.append({"role": "tool", "tool_name": name, "content": output})
            finally:
                if on_tools_running:
                    on_tools_running(False)

        return result  # not reached: the last round never offers tools
