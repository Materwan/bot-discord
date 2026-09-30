"""Shared fixtures: an App on temporary files, a scripted fake Ollama, Discord fakes."""

from __future__ import annotations

import contextlib
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from ollama import ChatResponse, Message

from clara.app import App
from clara.llm.client import LlmClient
from clara.settings import Settings

OWNER_ID = 1000
BOT_ID = 9000


# ----------------------------------------------------------------------
# Fake Ollama
# ----------------------------------------------------------------------
def chat_response(content: str = "", tool_calls: list[tuple[str, dict]] = (), prompt_tokens=10, completion_tokens=5):
    calls = [
        Message.ToolCall(function=Message.ToolCall.Function(name=name, arguments=arguments))
        for name, arguments in tool_calls
    ]
    return ChatResponse(
        message=Message(role="assistant", content=content, tool_calls=calls or None),
        prompt_eval_count=prompt_tokens,
        eval_count=completion_tokens,
    )


class FakeOllama:
    """Returns the queued responses in order and records every request."""

    def __init__(self, *responses: ChatResponse):
        self.responses = list(responses)
        self.requests: list[dict] = []

    def queue(self, *responses: ChatResponse) -> None:
        self.responses.extend(responses)

    async def chat(self, **request):
        self.requests.append({**request, "messages": list(request["messages"])})
        if not self.responses:
            return chat_response("{}")
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


@pytest.fixture
def ollama() -> FakeOllama:
    return FakeOllama()


@pytest.fixture
def settings(tmp_path) -> Settings:
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "system_prompt.md").write_text("Tu es Clara.", encoding="utf-8")
    return Settings(discord_token="token", owner_id=OWNER_ID, root_dir=tmp_path, history_size=5)


@pytest.fixture
def app(settings, ollama):
    application = App(settings, llm=LlmClient("test-model", client=ollama))
    application.client._connection.user = make_user(BOT_ID, "Clara", bot=True)
    yield application
    application.user_notes.close()


# ----------------------------------------------------------------------
# Discord fakes
# ----------------------------------------------------------------------
def make_user(user_id: int, name: str, bot: bool = False):
    return SimpleNamespace(id=user_id, display_name=name, name=name.lower(), bot=bot)


class FakeChannel:
    def __init__(self, channel_id: int = 500):
        self.id = channel_id
        self.send = AsyncMock()

    @contextlib.asynccontextmanager
    async def typing(self):
        yield


def make_message(author, content: str, mentions=(), members=(), message_id: int = 1, attachments=()):
    return SimpleNamespace(
        id=message_id,
        author=author,
        content=content,
        mentions=list(mentions),
        channel=FakeChannel(),
        guild=SimpleNamespace(id=700, members=list(members)),
        attachments=list(attachments),
        reply=AsyncMock(),
    )


@pytest.fixture
def bot_user(app):
    return app.client.user


@pytest.fixture
def owner():
    return make_user(OWNER_ID, "Erwan")


@pytest.fixture
def friend():
    return make_user(2000, "Paul")
