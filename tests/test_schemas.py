"""Tests for OpenAI-compatible Pydantic request and response schemas."""

import time
import pytest
from pydantic import ValidationError

from app.schemas import (
    ChatCompletionChunk,
    ChatCompletionChunkChoice,
    ChatCompletionChunkDelta,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatMessage,
)


def test_chat_message_content_normalization():
    """Verify that multi-part content arrays normalize into plain text."""
    msg = ChatMessage(
        role="user",
        content=[{"type": "text", "text": "First line"}, {"type": "text", "text": "Second line"}],
    )
    assert msg.content == "First line\nSecond line"

    plain_msg = ChatMessage(role="user", content="Direct string")
    assert plain_msg.content == "Direct string"


def test_request_validation_valid():
    """Valid request passes schema validation."""
    req = ChatCompletionRequest(
        model="gemini-web",
        messages=[
            ChatMessage(role="system", content="Be concise"),
            ChatMessage(role="user", content="Hello Gemini"),
        ],
        stream=False,
    )
    assert req.model == "gemini-web"
    assert len(req.messages) == 2


def test_request_validation_rejects_empty_messages():
    """Request with empty messages array must fail."""
    with pytest.raises(ValidationError):
        ChatCompletionRequest(model="gemini-web", messages=[])


def test_request_validation_rejects_no_user_turn():
    """Request without a user message must fail."""
    with pytest.raises(ValidationError):
        ChatCompletionRequest(
            model="gemini-web",
            messages=[ChatMessage(role="system", content="Only system")],
        )


def test_response_structure_valid():
    """Ensure response has valid ID, created timestamp, choices, and no fabricated usage."""
    now = int(time.time())
    resp = ChatCompletionResponse(
        model="gemini-web",
        choices=[
            {
                "index": 0,
                "message": {"role": "assistant", "content": "Here is your response."},
                "finish_reason": "stop",
            }
        ],
    )
    assert resp.id.startswith("chatcmpl-")
    assert resp.object == "chat.completion"
    assert resp.created >= now
    assert resp.choices[0].message.role == "assistant"
    assert resp.choices[0].message.content == "Here is your response."
    assert resp.choices[0].finish_reason == "stop"
    assert resp.usage is None  # Strictly not fabricated


def test_chunk_structure_valid():
    """Ensure SSE chunk conforms to OpenAI specifications."""
    chunk = ChatCompletionChunk(
        id="chatcmpl-test-123",
        created=1700000000,
        model="gemini-web",
        choices=[
            ChatCompletionChunkChoice(
                index=0,
                delta=ChatCompletionChunkDelta(content="world"),
                finish_reason=None,
            )
        ],
    )
    dumped = chunk.model_dump()
    assert dumped["object"] == "chat.completion.chunk"
    assert dumped["choices"][0]["delta"]["content"] == "world"
    assert dumped["choices"][0]["finish_reason"] is None
