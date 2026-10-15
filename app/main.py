"""FastAPI Application providing OpenAI-compatible API endpoints and Web Studio UI."""

import asyncio
import json
import logging
import subprocess
import sys
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.auth import verify_api_key
from app.config import settings
from app.errors import (
    AuthenticationExpiredError,
    GeminiWebError,
    format_openai_error,
)
from app.providers.gemini_web import GeminiWebProvider
from app.schemas import (
    ChatCompletionChoice,
    ChatCompletionChoiceMessage,
    ChatCompletionChunk,
    ChatCompletionChunkChoice,
    ChatCompletionChunkDelta,
    ChatCompletionRequest,
    ChatCompletionResponse,
    HealthResponse,
    ModelCard,
    ModelListResponse,
)
from app.services.chat_service import ChatService
from app.services.conversation_manager import conversation_manager
from app.session_manager import session_manager

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("gemini_web_api")

# Singleton Provider and Service instances
provider = GeminiWebProvider()
chat_service = ChatService(provider=provider)

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle management for browser resources and connections."""
    logger.info("Starting Gemini Web API v%s on http://%s:%d", __version__, settings.HOST, settings.PORT)
    if not settings.API_KEY:
        logger.warning(
            "SECURITY NOTICE: API_KEY is not configured. "
            "Local requests will be permitted without authentication."
        )
    else:
        logger.info("API Key protection is ENABLED (Bearer token required).")

    auth_status = session_manager.get_auth_status()
    if not auth_status["is_authenticated"]:
        logger.warning(
            "SESSION NOTICE: %s. "
            "Run `python scripts/setup_browser.py` before making chat requests.",
            auth_status["status_message"],
        )
    else:
        logger.info("Session check: %s", auth_status["status_message"])

    yield

    logger.info("Shutting down Gemini Web API application...")
    await provider.shutdown()


app = FastAPI(
    title="Gemini Web -> OpenAI-Compatible API",
    description="Local reverse-engineered OpenAI-compatible API backed by an authenticated Gemini Web session.",
    version=__version__,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url=None,
)

# Mount static files directory if available
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# --- Middlewares ---


@app.middleware("http")
async def limit_request_size(request: Request, call_next):
    """Enforce request size limits to prevent memory exhaustion."""
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > settings.MAX_REQUEST_SIZE_BYTES:
                return JSONResponse(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    content=format_openai_error(
                        message=f"Request entity exceeds max size limit of {settings.MAX_REQUEST_SIZE_BYTES} bytes.",
                        error_type="invalid_request_error",
                        code="request_too_large",
                    ),
                )
        except ValueError:
            pass
    return await call_next(request)


# --- Custom Exception Handlers ---


@app.exception_handler(GeminiWebError)
async def handle_gemini_web_error(request: Request, exc: GeminiWebError):
    """Handle all domain-specific application errors with OpenAI-compatible responses."""
    logger.warning("Handled domain exception [%s]: %s", exc.code, exc.message)
    return JSONResponse(
        status_code=exc.status_code,
        content=exc.to_dict(),
    )


@app.exception_handler(RequestValidationError)
async def handle_validation_error(request: Request, exc: RequestValidationError):
    """Format Pydantic schema validation errors into OpenAI format."""
    details = exc.errors()
    first_msg = details[0].get("msg", "Validation error") if details else "Invalid request body"
    loc = " -> ".join(str(p) for p in details[0].get("loc", [])) if details else None
    logger.info("Request validation failed: %s (at %s)", first_msg, loc)
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content=format_openai_error(
            message=f"{first_msg} (at {loc})" if loc else first_msg,
            error_type="invalid_request_error",
            code="invalid_request",
            param=str(details[0]["loc"][-1]) if details and details[0].get("loc") else None,
        ),
    )


@app.exception_handler(Exception)
async def handle_uncaught_error(request: Request, exc: Exception):
    """Catch unexpected exceptions without leaking sensitive trace information."""
    logger.error("Uncaught server exception: %s", exc, exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=format_openai_error(
            message="An unexpected internal server error occurred.",
            error_type="server_error",
            code="internal_error",
        ),
    )


# --- Helper functions for Test/Mock Simulation Mode ---


async def _generate_mock_stream(request: ChatCompletionRequest):
    cid = f"chatcmpl-mock-{uuid.uuid4().hex[:12]}"
    created = int(time.time())
    user_msg = "your prompt"
    for m in reversed(request.messages):
        if m.role == "user":
            user_msg = str(m.content)
            break

    mock_reply = (
        f"**[Test / Simulation Mode]**\n\n"
        f"Received your prompt: *\"{user_msg}\"*\n\n"
        f"✅ The local OpenAI-compatible API endpoint, Server-Sent Events (SSE) streaming engine, "
        f"and Web Studio UI are **all working properly**!\n\n"
        f"💡 **Next Step:** To switch from simulation to live Google Gemini generation, click **'Browser Login'** "
        f"in the top bar or run `python scripts/setup_browser.py` in your terminal to authenticate your Google session."
    )

    # Initial role chunk
    chunk = ChatCompletionChunk(
        id=cid,
        object="chat.completion.chunk",
        created=created,
        model=request.model,
        choices=[
            ChatCompletionChunkChoice(
                index=0,
                delta=ChatCompletionChunkDelta(role="assistant", content=""),
                finish_reason=None,
            )
        ],
    )
    yield f"data: {json.dumps(chunk.model_dump())}\n\n"

    # Words streaming
    words = mock_reply.split(" ")
    for i, word in enumerate(words):
        token = word if i == 0 else f" {word}"
        chunk = ChatCompletionChunk(
            id=cid,
            object="chat.completion.chunk",
            created=created,
            model=request.model,
            choices=[
                ChatCompletionChunkChoice(
                    index=0,
                    delta=ChatCompletionChunkDelta(content=token),
                    finish_reason=None,
                )
            ],
        )
        yield f"data: {json.dumps(chunk.model_dump())}\n\n"
        await asyncio.sleep(0.03)

    # Final stop chunk
    chunk = ChatCompletionChunk(
        id=cid,
        object="chat.completion.chunk",
        created=created,
        model=request.model,
        choices=[
            ChatCompletionChunkChoice(
                index=0,
                delta=ChatCompletionChunkDelta(),
                finish_reason="stop",
            )
        ],
    )
    yield f"data: {json.dumps(chunk.model_dump())}\n\n"
    yield "data: [DONE]\n\n"


def _generate_mock_completion(request: ChatCompletionRequest) -> ChatCompletionResponse:
    cid = f"chatcmpl-mock-{uuid.uuid4().hex[:12]}"
    created = int(time.time())
    user_msg = "your prompt"
    for m in reversed(request.messages):
        if m.role == "user":
            user_msg = str(m.content)
            break

    mock_reply = (
        f"**[Test / Simulation Mode]**\n\n"
        f"Received your prompt: *\"{user_msg}\"*\n\n"
        f"✅ The local OpenAI-compatible API endpoint and Web Studio UI are **all working properly**!\n\n"
        f"💡 **Next Step:** To switch from simulation to live Google Gemini generation, click **'Browser Login'** "
        f"or run `python scripts/setup_browser.py` in your terminal to authenticate your Google session."
    )

    return ChatCompletionResponse(
        id=cid,
        object="chat.completion",
        created=created,
        model=request.model,
        choices=[
            ChatCompletionChoice(
                index=0,
                message=ChatCompletionChoiceMessage(role="assistant", content=mock_reply),
                finish_reason="stop",
            )
        ],
        usage=None,
    )


# --- UI Routes ---


@app.get("/", response_class=FileResponse)
@app.get("/ui", response_class=FileResponse)
async def serve_ui():
    """Serve the Web Studio interactive testing interface."""
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return HTMLResponse(
        "<h1>Gemini Web Studio</h1><p>UI loading error: static/index.html not found.</p>"
    )


@app.get("/api/client-config")
async def client_config():
    """Expose non-sensitive local configuration to localhost UI client."""
    return {
        "api_key": settings.API_KEY or "",
        "base_url": f"http://{settings.HOST}:{settings.PORT}/v1",
        "has_session": session_manager.has_session(),
    }


@app.post("/api/launch-login")
async def launch_login():
    """Launch the interactive setup_browser.py script in a visible console process."""
    try:
        script_path = Path(__file__).resolve().parent.parent / "scripts" / "setup_browser.py"
        creationflags = subprocess.CREATE_NEW_CONSOLE if sys.platform == "win32" else 0
        subprocess.Popen([sys.executable, str(script_path)], creationflags=creationflags)
        return {
            "status": "ok",
            "message": "Chromium login window and setup console launched. Please complete sign-in in the browser.",
        }
    except Exception as e:
        logger.error("Failed to launch login script: %s", e)
        return {"status": "error", "message": str(e)}


@app.post("/api/import-cookies")
async def import_cookies_endpoint(request: Request):
    """Import raw cookie string or JSON from Web Studio UI."""
    try:
        body = await request.json()
        raw_cookie = body.get("cookie", "")
        if not raw_cookie:
            return JSONResponse(
                status_code=400,
                content={"status": "error", "message": "Cookie string cannot be empty."},
            )

        from scripts.import_cookies import parse_cookie_input, save_cookies_as_storage_state

        cookies = parse_cookie_input(raw_cookie)
        if not cookies:
            return JSONResponse(
                status_code=400,
                content={"status": "error", "message": "No valid cookies found in input."},
            )

        success = save_cookies_as_storage_state(cookies)
        is_valid, msg = session_manager.validate_session_state()
        return {
            "status": "ok" if is_valid else "warning",
            "message": msg,
            "cookies_count": len(cookies),
            "authenticated": is_valid,
        }
    except Exception as e:
        logger.error("Error importing cookies via API: %s", e)
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


# --- API Routes ---


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Service health inspection endpoint (unauthenticated)."""
    provider_health = await provider.check_health()
    auth_status = session_manager.get_auth_status()
    return HealthResponse(
        status="ok",
        browser_connected=provider_health["browser_connected"],
        authenticated=auth_status["is_authenticated"],
        version=__version__,
    )


@app.get("/v1/models", response_model=ModelListResponse, dependencies=[Depends(verify_api_key)])
async def list_models():
    """List models available through the adapter."""
    models = [
        ModelCard(id=model_id, created=1700000000, owned_by="google-web")
        for model_id in provider.list_supported_models()
    ]
    return ModelListResponse(object="list", data=models)


@app.post(
    "/v1/chat/completions",
    dependencies=[Depends(verify_api_key)],
    response_model=None,
)
async def chat_completions(
    request: ChatCompletionRequest,
    x_mock_mode: Optional[str] = Header(default=None),
):
    """
    OpenAI-compatible Chat Completions endpoint.
    Accepts standard chat completion payload and routes through Gemini Web session.
    """
    is_mock = request.mock_mode or (x_mock_mode and x_mock_mode.lower() == "true")

    # If mock/simulation mode is active, return simulated stream or response
    if is_mock:
        if request.stream:
            return StreamingResponse(
                _generate_mock_stream(request),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                },
            )
        return _generate_mock_completion(request)

    # Pre-flight check: verify that an authentication session is available
    if not session_manager.has_session():
        raise AuthenticationExpiredError()

    if request.stream:
        # Return Server-Sent Events stream
        return StreamingResponse(
            chat_service.create_stream_completion(request),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    # Return standard non-streaming JSON response
    response: ChatCompletionResponse = await chat_service.create_chat_completion(request)
    return response


@app.post(
    "/v1/conversations/{conversation_id}/reset",
    dependencies=[Depends(verify_api_key)],
)
async def reset_conversation(conversation_id: str):
    """Reset a specific conversation history thread."""
    success = conversation_manager.reset_conversation(conversation_id)
    return {"status": "reset" if success else "not_found", "conversation_id": conversation_id}
