"""Multi-conversation state management and client isolation."""

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from app.schemas import ChatMessage

logger = logging.getLogger(__name__)


@dataclass
class ConversationRecord:
    """Internal record tracking an isolated conversation thread."""

    id: str
    created_at: float = field(default_factory=time.time)
    last_accessed_at: float = field(default_factory=time.time)
    messages: List[ChatMessage] = field(default_factory=list)


class ConversationManager:
    """
    Manages client conversation isolation.
    Ensures that independent client requests do not collide,
    and supports explicit conversation ID threading.
    """

    def __init__(self, ttl_seconds: int = 3600):
        self._conversations: Dict[str, ConversationRecord] = {}
        self.ttl_seconds = ttl_seconds

    def get_or_create(
        self, conversation_id: Optional[str] = None
    ) -> Tuple[str, ConversationRecord, bool]:
        """
        Retrieve existing conversation record or initialize a new one.
        Returns: (conversation_id, record, is_new)
        """
        self.cleanup_expired()

        if conversation_id and conversation_id in self._conversations:
            record = self._conversations[conversation_id]
            record.last_accessed_at = time.time()
            return conversation_id, record, False

        # Generate new conversation ID if none provided
        cid = conversation_id or f"conv-{uuid.uuid4().hex[:12]}"
        record = ConversationRecord(id=cid)
        self._conversations[cid] = record
        return cid, record, True

    def record_turn(
        self,
        conversation_id: str,
        request_messages: List[ChatMessage],
        assistant_content: str,
    ) -> None:
        """Append user messages and the resulting assistant response."""
        _, record, _ = self.get_or_create(conversation_id)
        record.last_accessed_at = time.time()
        record.messages = list(request_messages)
        record.messages.append(
            ChatMessage(role="assistant", content=assistant_content)
        )

    def reset_conversation(self, conversation_id: str) -> bool:
        """Reset and remove an active conversation thread."""
        if conversation_id in self._conversations:
            del self._conversations[conversation_id]
            logger.info("Reset conversation thread: %s", conversation_id)
            return True
        return False

    def cleanup_expired(self) -> int:
        """Prune conversations older than the TTL limit."""
        now = time.time()
        expired_ids = [
            cid
            for cid, rec in self._conversations.items()
            if now - rec.last_accessed_at > self.ttl_seconds
        ]
        for cid in expired_ids:
            del self._conversations[cid]
        if expired_ids:
            logger.debug("Pruned %d expired conversation records", len(expired_ids))
        return len(expired_ids)


conversation_manager = ConversationManager()
