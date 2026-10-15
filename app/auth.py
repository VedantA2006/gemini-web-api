"""API Key authentication dependency and timing-safe token verification."""

import logging
import secrets
from typing import Optional
from fastapi import Header

from app.config import settings
from app.errors import AuthenticationRequiredError

logger = logging.getLogger(__name__)


def is_token_valid(token: Optional[str]) -> bool:
    """Validate a bearer token against the configured API_KEY in constant time."""
    expected_key = settings.API_KEY
    if not expected_key:
        # No API key configured: allow local unauthenticated access
        return True

    if not token:
        return False

    return secrets.compare_digest(token, expected_key)


async def verify_api_key(authorization: Optional[str] = Header(default=None)) -> None:
    """FastAPI dependency to enforce Bearer token authentication."""
    expected_key = settings.API_KEY
    if not expected_key:
        return

    if not authorization:
        logger.warning("Rejected unauthenticated request: missing Authorization header")
        raise AuthenticationRequiredError(
            "Missing Authorization header. Provide 'Authorization: Bearer <API_KEY>'."
        )

    parts = authorization.strip().split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        logger.warning("Rejected unauthenticated request: invalid header scheme")
        raise AuthenticationRequiredError(
            "Invalid Authorization scheme. Format must be 'Bearer <API_KEY>'."
        )

    token = parts[1].strip()
    if not secrets.compare_digest(token, expected_key):
        logger.warning("Rejected request: incorrect API key supplied")
        raise AuthenticationRequiredError("Incorrect API key provided.")
