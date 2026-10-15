"""Tests for chat completions endpoint, streaming, provider mocking, and conversation management."""

import json
from typing import AsyncIterator, List
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.errors import GeminiTimeoutError, RateLimitError
from app.main import app, chat_service, provider
from app.providers.base import BaseProvider
from app.providers.gemini_web import build_gemini_prompt, parse_stream_response
from app.schemas import ChatMessage
from app.services.conversation_manager import conversation_manager
from app.session_manager import session_manager


class MockGeminiProvider(BaseProvider):
    """Mock provider mimicking Gemini Web behavior for unit testing."""

    def __init__(self, response_text: str = "This is a mocked Gemini response."):
        self.response_text = response_text
        self.simulate_timeout = False
        self.simulate_rate_limit = False

    def is_model_supported(self, model: str) -> bool:
        return model in ["gemini-web", "gemini-4-argon", "gemini-3.8-flash", "gemini-3.1-pro", "gemini-3.5-flash-lite", "gemini-2.5-pro", "gemini-2.5-flash"]

    def list_supported_models(self) -> List[str]:
        return ["gemini-web", "gemini-4-argon", "gemini-3.8-flash", "gemini-3.1-pro", "gemini-3.5-flash-lite", "gemini-2.5-pro", "gemini-2.5-flash"]

    async def generate(self, messages: List[ChatMessage], model: str, **kwargs) -> str:
        if self.simulate_timeout:
            raise GeminiTimeoutError()
        if self.simulate_rate_limit:
            raise RateLimitError()
        return self.response_text

    async def stream_generate(self, messages: List[ChatMessage], model: str, **kwargs) -> AsyncIterator[str]:
        if self.simulate_timeout:
            raise GeminiTimeoutError()
        if self.simulate_rate_limit:
            raise RateLimitError()
        words = self.response_text.split(" ")
        for i, word in enumerate(words):
            yield word if i == 0 else f" {word}"

    async def check_health(self):
        return {"browser_connected": True, "authenticated": True}

    async def shutdown(self):
        pass


@pytest.fixture(autouse=True)
def setup_test_environment(monkeypatch):
    """Disable API key enforcement by default for chat unit tests."""
    from app.config import settings
    monkeypatch.setattr(settings, "API_KEY", None)


def test_build_gemini_prompt_single_turn_no_system():
    """Single turn prompt contains only the user message."""
    messages = [ChatMessage(role="user", content="Explain quantum computing")]
    prompt = build_gemini_prompt(messages)
    assert prompt == "Explain quantum computing"


def test_build_gemini_prompt_single_turn_with_system():
    """Single turn prompt with system instruction prepends System: header."""
    messages = [
        ChatMessage(role="system", content="You are a physics professor."),
        ChatMessage(role="user", content="Explain quantum computing"),
    ]
    prompt = build_gemini_prompt(messages)
    assert prompt == "System:\nYou are a physics professor.\n\nExplain quantum computing"


def test_build_gemini_prompt_multi_turn():
    """Multi-turn transcript emits system, previous conversation, and current user ask."""
    messages = [
        ChatMessage(role="system", content="Act as a tutor."),
        ChatMessage(role="user", content="I live in Tokyo."),
        ChatMessage(role="assistant", content="Tokyo is a wonderful city!"),
        ChatMessage(role="user", content="What should I wear today?"),
    ]
    prompt = build_gemini_prompt(messages)
    assert "System:\nAct as a tutor." in prompt
    assert "Previous conversation:" in prompt
    assert "User: I live in Tokyo." in prompt
    assert "Assistant: Tokyo is a wonderful city!" in prompt
    assert "Current user message:\nWhat should I wear today?" in prompt


def test_parse_stream_response():
    """Verify parsing of internal wrb.fr payload frames."""
    inner_data = json.dumps([None, None, None, None, [[None, ["Hello ", "world from Gemini!"]]]])
    frame = json.dumps([["wrb.fr", None, inner_data]])
    raw_rpc = f")]}}'\n123\n{frame}\n"

    parsed = parse_stream_response(raw_rpc)
    assert parsed == "Hello world from Gemini!"


@pytest.mark.asyncio
async def test_chat_completion_non_streaming(monkeypatch):
    """Test successful non-streaming /v1/chat/completions request."""
    # Ensure session check passes
    monkeypatch.setattr(session_manager, "has_session", lambda: True)
    # Inject mock provider
    mock_prov = MockGeminiProvider("Mocked completion output.")
    monkeypatch.setattr(chat_service, "provider", mock_prov)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/chat/completions",
            json={
                "model": "gemini-web",
                "messages": [{"role": "user", "content": "Hello"}],
                "stream": False,
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data["object"] == "chat.completion"
    assert data["model"] == "gemini-web"
    assert len(data["choices"]) == 1
    assert data["choices"][0]["message"]["content"] == "Mocked completion output."
    assert data["choices"][0]["finish_reason"] == "stop"
    assert data["usage"] is None


@pytest.mark.asyncio
async def test_chat_completion_streaming_sse(monkeypatch):
    """Test successful streaming /v1/chat/completions request returning Server-Sent Events."""
    monkeypatch.setattr(session_manager, "has_session", lambda: True)
    mock_prov = MockGeminiProvider("Streaming test response.")
    monkeypatch.setattr(chat_service, "provider", mock_prov)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/chat/completions",
            json={
                "model": "gemini-web",
                "messages": [{"role": "user", "content": "Stream me"}],
                "stream": True,
            },
        )

    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]

    lines = response.text.strip().split("\n\n")
    assert len(lines) >= 3

    # Initial chunk declares role
    first_chunk = json.loads(lines[0].replace("data: ", ""))
    assert first_chunk["object"] == "chat.completion.chunk"
    assert first_chunk["choices"][0]["delta"]["role"] == "assistant"

    # Terminal marker
    assert lines[-1] == "data: [DONE]"


@pytest.mark.asyncio
async def test_chat_completion_unsupported_model(monkeypatch):
    """Test requesting an unsupported model returns 404 with OpenAI error."""
    monkeypatch.setattr(session_manager, "has_session", lambda: True)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/chat/completions",
            json={
                "model": "non-existent-model-gpt-99",
                "messages": [{"role": "user", "content": "Hello"}],
            },
        )

    assert response.status_code == 404
    data = response.json()
    assert data["error"]["code"] == "model_not_found"
    assert data["error"]["type"] == "invalid_request_error"


@pytest.mark.asyncio
async def test_chat_completion_no_session_raises_401(monkeypatch):
    """When no session exists, endpoint returns actionable 401 error."""
    monkeypatch.setattr(session_manager, "has_session", lambda: False)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/chat/completions",
            json={
                "model": "gemini-web",
                "messages": [{"role": "user", "content": "Hello"}],
            },
        )

    assert response.status_code == 401
    data = response.json()
    assert data["error"]["code"] == "session_expired"
    assert "setup_browser.py" in data["error"]["message"]


@pytest.mark.asyncio
async def test_chat_completion_timeout_raises_504(monkeypatch):
    """When provider times out, endpoint returns 504 gateway timeout."""
    monkeypatch.setattr(session_manager, "has_session", lambda: True)
    mock_prov = MockGeminiProvider()
    mock_prov.simulate_timeout = True
    monkeypatch.setattr(chat_service, "provider", mock_prov)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/chat/completions",
            json={
                "model": "gemini-web",
                "messages": [{"role": "user", "content": "Wait forever"}],
            },
        )

    assert response.status_code == 504
    data = response.json()
    assert data["error"]["code"] == "gateway_timeout"


@pytest.mark.asyncio
async def test_conversation_isolation():
    """Verify that multiple conversation IDs maintain isolated histories."""
    cid_a = "client-a-conversation"
    cid_b = "client-b-conversation"

    conversation_manager.record_turn(
        conversation_id=cid_a,
        request_messages=[ChatMessage(role="user", content="Message A")],
        assistant_content="Response A",
    )
    conversation_manager.record_turn(
        conversation_id=cid_b,
        request_messages=[ChatMessage(role="user", content="Message B")],
        assistant_content="Response B",
    )

    _, rec_a, _ = conversation_manager.get_or_create(cid_a)
    _, rec_b, _ = conversation_manager.get_or_create(cid_b)

    assert len(rec_a.messages) == 2
    assert rec_a.messages[0].content == "Message A"
    assert rec_a.messages[1].content == "Response A"

    assert len(rec_b.messages) == 2
    assert rec_b.messages[0].content == "Message B"
    assert rec_b.messages[1].content == "Response B"

    # Reset cid_a should not affect cid_b
    conversation_manager.reset_conversation(cid_a)
    _, rec_a_fresh, is_new = conversation_manager.get_or_create(cid_a)
    assert is_new is True
    _, rec_b_still, _ = conversation_manager.get_or_create(cid_b)
    assert len(rec_b_still.messages) == 2
