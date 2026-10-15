"""Abstract Base Provider for LLM execution."""

from abc import ABC, abstractmethod
from typing import Any, AsyncIterator, Dict, List

from app.schemas import ChatMessage


class BaseProvider(ABC):
    """Abstract interface for all model providers."""

    @abstractmethod
    async def generate(self, messages: List[ChatMessage], model: str, **kwargs: Any) -> str:
        """Execute a completion request and return the full response text."""
        pass

    @abstractmethod
    async def stream_generate(
        self, messages: List[ChatMessage], model: str, **kwargs: Any
    ) -> AsyncIterator[str]:
        """Execute a completion request and stream incremental text tokens."""
        pass

    @abstractmethod
    async def check_health(self) -> Dict[str, Any]:
        """Check provider status, connection, and authentication."""
        pass

    @abstractmethod
    async def shutdown(self) -> None:
        """Clean up provider resources, open tabs, and browser processes."""
        pass

    @abstractmethod
    def is_model_supported(self, model: str) -> bool:
        """Return True if the requested model identifier is supported."""
        pass

    @abstractmethod
    def list_supported_models(self) -> List[str]:
        """Return the list of model identifiers supported by this provider."""
        pass
