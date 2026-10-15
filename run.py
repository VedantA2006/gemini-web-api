"""Application launcher and Uvicorn server entrypoint."""

import argparse
import asyncio
import logging
import secrets
import sys
from pathlib import Path
import uvicorn
from dotenv import load_dotenv

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

# Ensure .env is loaded before importing application settings
ENV_FILE = Path(".env")
if not ENV_FILE.exists():
    generated_key = secrets.token_urlsafe(32)
    example_file = Path(".env.example")
    if example_file.exists():
        content = example_file.read_text(encoding="utf-8")
        content = content.replace("replace-with-a-long-random-secret", generated_key)
        ENV_FILE.write_text(content, encoding="utf-8")
        print(f"[*] Created '.env' file with generated local API_KEY: {generated_key}")
    else:
        ENV_FILE.write_text(
            f"HOST=127.0.0.1\nPORT=8000\nAPI_KEY={generated_key}\nHEADLESS=true\n",
            encoding="utf-8",
        )
        print(f"[*] Generated default '.env' with API_KEY: {generated_key}")

load_dotenv()

from app.config import settings

logger = logging.getLogger("run")


def main():
    parser = argparse.ArgumentParser(description="Start Gemini Web -> OpenAI-Compatible API server")
    parser.add_argument("--host", default=settings.HOST, help=f"Host address (default: {settings.HOST})")
    parser.add_argument("--port", type=int, default=settings.PORT, help=f"Port number (default: {settings.PORT})")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload for development")
    args = parser.parse_args()

    print("=" * 65)
    print(f"  Starting Gemini Web OpenAI-Compatible API Server")
    print("=" * 65)
    print(f"  API Endpoint:  http://{args.host}:{args.port}/v1/chat/completions")
    print(f"  Health Check:  http://{args.host}:{args.port}/health")
    print(f"  API Models:    http://{args.host}:{args.port}/v1/models")
    if settings.API_KEY:
        print(f"  Auth:          Bearer token enabled")
    else:
        print(f"  Auth:          None (Unprotected local access)")
    print("=" * 65)

    uvicorn.run(
        "app.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level=settings.LOG_LEVEL.lower(),
    )


if __name__ == "__main__":
    main()
