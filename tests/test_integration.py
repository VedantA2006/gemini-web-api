"""
Real integration test for Gemini Web adapter.

NOTE: This test is SKIPPED by default because it requires an active,
user-authenticated Google session.
Run explicitly using:
    RUN_INTEGRATION_TESTS=1 pytest tests/test_integration.py
"""

import os
import pytest
from app.config import settings
from app.providers.gemini_web import GeminiWebProvider
from app.schemas import ChatMessage
from app.session_manager import session_manager

pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_INTEGRATION_TESTS"),
    reason="Live integration test requires RUN_INTEGRATION_TESTS=1 and an authenticated browser profile.",
)


@pytest.mark.asyncio
async def test_live_gemini_web_generation():
    """Live smoke test against real Gemini Web interface."""
    assert session_manager.has_session(), (
        "No browser session found. Run `python scripts/setup_browser.py` first."
    )

    provider = GeminiWebProvider()
    try:
        messages = [
            ChatMessage(role="user", content="Reply with exactly the word 'PONG' and nothing else.")
        ]
        response = await provider.generate(messages=messages, model="gemini-web")
        assert response is not None
        assert len(response.strip()) > 0
        print(f"\nLive Gemini Web output: {response}")
    finally:
        await provider.shutdown()
