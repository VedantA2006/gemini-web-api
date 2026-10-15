"""OpenAI-compatible request and response schemas."""

import time
import uuid
from typing import Any, Dict, List, Literal, Optional, Union
from pydantic import BaseModel, Field, field_validator


class ChatMessage(BaseModel):
    """Chat message in conversation history."""

    role: Literal["system", "user", "assistant", "tool"]
    content: Union[str, List[Dict[str, Any]]] = Field(..., description="Message content string or parts")
    name: Optional[str] = None

    @field_validator("content", mode="before")
    @classmethod
    def normalize_content(cls, v: Any) -> Union[str, List[Any]]:
        if isinstance(v, str):
            return v
        if isinstance(v, list):
            # Extract text elements if content is array of parts: [{"type": "text", "text": "..."}]
            extracted_parts = []
            for part in v:
                if isinstance(part, dict) and part.get("type") == "text":
                    extracted_parts.append(part.get("text", ""))
                elif isinstance(part, str):
                    extracted_parts.append(part)
            if extracted_parts:
                return "\n".join(extracted_parts)
            return str(v)
        return str(v) if v is not None else ""


class ChatCompletionRequest(BaseModel):
    """Standard OpenAI Chat Completions API request schema."""

    model: str = Field(default="gemini-web", description="Target model ID")
    messages: List[ChatMessage] = Field(..., min_length=1, description="Array of conversation messages")
    stream: bool = Field(default=False, description="Whether to stream response via SSE")
    temperature: Optional[float] = Field(default=None, ge=0.0, le=2.0)
    top_p: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    n: Optional[int] = Field(default=1)
    max_tokens: Optional[int] = Field(default=None)
    conversation_id: Optional[str] = Field(
        default=None,
        description="Optional conversation thread ID extension to maintain chat state",
    )
    mock_mode: Optional[bool] = Field(
        default=False,
        description="Enable simulated response mode for testing UI and API without live browser",
    )

    @field_validator("messages")
    @classmethod
    def validate_messages(cls, v: List[ChatMessage]) -> List[ChatMessage]:
        if not v:
            raise ValueError("Messages list cannot be empty.")
        # Ensure at least one message contains non-empty user input or system prompt
        has_user = any(m.role == "user" and isinstance(m.content, str) and m.content.strip() for m in v)
        if not has_user:
            raise ValueError("Request must contain at least one user message with non-empty content.")
        return v


class ChatCompletionChoiceMessage(BaseModel):
    """Response message for non-streaming choice."""

    role: Literal["assistant"] = "assistant"
    content: str


class ChatCompletionChoice(BaseModel):
    """Choice object in chat completion response."""

    index: int = 0
    message: ChatCompletionChoiceMessage
    finish_reason: Optional[Literal["stop", "length", "content_filter"]] = "stop"


class ChatCompletionUsage(BaseModel):
    """Token usage metrics (only included when true provider counts exist)."""

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class ChatCompletionResponse(BaseModel):
    """Complete non-streaming OpenAI-compatible chat completion response."""

    id: str = Field(default_factory=lambda: f"chatcmpl-{uuid.uuid4().hex[:12]}")
    object: Literal["chat.completion"] = "chat.completion"
    created: int = Field(default_factory=lambda: int(time.time()))
    model: str
    choices: List[ChatCompletionChoice]
    usage: Optional[ChatCompletionUsage] = None


# --- Streaming SSE Schemas ---


class ChatCompletionChunkDelta(BaseModel):
    """Delta object in streaming chunk."""

    role: Optional[Literal["assistant"]] = None
    content: Optional[str] = None


class ChatCompletionChunkChoice(BaseModel):
    """Choice object in streaming chunk."""

    index: int = 0
    delta: ChatCompletionChunkDelta
    finish_reason: Optional[Literal["stop", "length", "content_filter"]] = None


class ChatCompletionChunk(BaseModel):
    """Server-Sent Event chunk in streaming mode."""

    id: str
    object: Literal["chat.completion.chunk"] = "chat.completion.chunk"
    created: int
    model: str
    choices: List[ChatCompletionChunkChoice]


# --- Model Listing Schemas ---


class ModelCard(BaseModel):
    """Individual model metadata."""

    id: str
    object: Literal["model"] = "model"
    created: int = Field(default=1700000000)
    owned_by: str = "google-web"


class ModelListResponse(BaseModel):
    """List of available models."""

    object: Literal["list"] = "list"
    data: List[ModelCard]


# --- Health Schema ---


class HealthResponse(BaseModel):
    """System health status."""

    status: str
    browser_connected: bool
    authenticated: bool
    version: str
