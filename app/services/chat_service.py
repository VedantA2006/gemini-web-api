"""Chat completion orchestration service."""

import json
import logging
import time
import uuid
from typing import AsyncIterator, List

from app.errors import ModelNotFoundError
from app.providers.base import BaseProvider
from app.schemas import (
    ChatCompletionChoice,
    ChatCompletionChoiceMessage,
    ChatCompletionChunk,
    ChatCompletionChunkChoice,
    ChatCompletionChunkDelta,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatMessage,
)
from app.services.conversation_manager import conversation_manager

logger = logging.getLogger(__name__)


class ChatService:
    """Orchestrates model completions, streaming SSE formatting, and state management."""

    def __init__(self, provider: BaseProvider):
        self.provider = provider

    def _resolve_messages(
        self, request: ChatCompletionRequest
    ) -> List[ChatMessage]:
        """
        Merge conversation manager history if conversation_id was provided
        and request only provided the latest delta turn.
        """
        if not request.conversation_id:
            return request.messages

        _, record, is_new = conversation_manager.get_or_create(request.conversation_id)
        if is_new or not record.messages:
            return request.messages

        # If caller sent full history in messages, use caller's messages
        if len(request.messages) > 1:
            return request.messages

        # Caller only sent 1 message, prepend prior recorded turns
        combined = list(record.messages) + list(request.messages)
        return combined

    async def create_chat_completion(
        self, request: ChatCompletionRequest
    ) -> ChatCompletionResponse:
        """Handle non-streaming OpenAI chat completion requests."""
        if not self.provider.is_model_supported(request.model):
            raise ModelNotFoundError(request.model)

        effective_messages = self._resolve_messages(request)

        # Generate response text from provider
        response_text = await self.provider.generate(
            messages=effective_messages,
            model=request.model,
            temperature=request.temperature,
            top_p=request.top_p,
            max_tokens=request.max_tokens,
        )

        # Record turn in conversation manager if conversation_id was given
        if request.conversation_id:
            conversation_manager.record_turn(
                conversation_id=request.conversation_id,
                request_messages=request.messages,
                assistant_content=response_text,
            )

        # Construct OpenAI-compatible response
        completion_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
        created_timestamp = int(time.time())

        return ChatCompletionResponse(
            id=completion_id,
            object="chat.completion",
            created=created_timestamp,
            model=request.model,
            choices=[
                ChatCompletionChoice(
                    index=0,
                    message=ChatCompletionChoiceMessage(
                        role="assistant",
                        content=response_text,
                    ),
                    finish_reason="stop",
                )
            ],
            usage=None,  # Never fabricate token counts per strict specification
        )

    async def create_stream_completion(
        self, request: ChatCompletionRequest
    ) -> AsyncIterator[str]:
        """Handle streaming OpenAI chat completion requests returning SSE lines."""
        if not self.provider.is_model_supported(request.model):
            raise ModelNotFoundError(request.model)

        effective_messages = self._resolve_messages(request)
        completion_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
        created_timestamp = int(time.time())

        # 1. Initial role declaration chunk
        initial_chunk = ChatCompletionChunk(
            id=completion_id,
            object="chat.completion.chunk",
            created=created_timestamp,
            model=request.model,
            choices=[
                ChatCompletionChunkChoice(
                    index=0,
                    delta=ChatCompletionChunkDelta(role="assistant", content=""),
                    finish_reason=None,
                )
            ],
        )
        yield f"data: {json.dumps(initial_chunk.model_dump())}\n\n"

        # 2. Stream incremental content deltas
        full_response_parts: List[str] = []
        async for delta_text in self.provider.stream_generate(
            messages=effective_messages,
            model=request.model,
            temperature=request.temperature,
            top_p=request.top_p,
            max_tokens=request.max_tokens,
        ):
            if delta_text:
                full_response_parts.append(delta_text)
                chunk = ChatCompletionChunk(
                    id=completion_id,
                    object="chat.completion.chunk",
                    created=created_timestamp,
                    model=request.model,
                    choices=[
                        ChatCompletionChunkChoice(
                            index=0,
                            delta=ChatCompletionChunkDelta(content=delta_text),
                            finish_reason=None,
                        )
                    ],
                )
                yield f"data: {json.dumps(chunk.model_dump())}\n\n"

        # 3. Final termination chunk with finish_reason='stop'
        final_chunk = ChatCompletionChunk(
            id=completion_id,
            object="chat.completion.chunk",
            created=created_timestamp,
            model=request.model,
            choices=[
                ChatCompletionChunkChoice(
                    index=0,
                    delta=ChatCompletionChunkDelta(),
                    finish_reason="stop",
                )
            ],
        )
        yield f"data: {json.dumps(final_chunk.model_dump())}\n\n"

        # 4. Standard OpenAI terminal marker
        yield "data: [DONE]\n\n"

        # Record conversation turn if applicable
        if request.conversation_id:
            full_text = "".join(full_response_parts)
            conversation_manager.record_turn(
                conversation_id=request.conversation_id,
                request_messages=request.messages,
                assistant_content=full_text,
            )
