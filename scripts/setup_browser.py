"""
Interactive browser authentication and session setup utility.

Launches a visible Chromium window with a persistent user profile directory,
allowing the user to authenticate manually to their Google Gemini account.
Once authenticated, exports and secures the session storage state for the API server.
"""

import argparse
import asyncio
import logging
import sys
import time
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from playwright.async_api import async_playwright

from app.config import settings
from app.session_manager import session_manager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("setup_browser")

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


async def check_existing_session() -> int:
    """Inspect and report the status of any existing local session files."""
    print("=" * 60)
    print("Checking Gemini Web Session Status")
    print("=" * 60)
    status = session_manager.get_auth_status()
    print(f"Profile directory present: {status['has_profile_dir']} ({settings.browser_profile_path})")
    print(f"Storage state file present: {status['has_storage_state']} ({settings.storage_state_file})")
    print(f"Authenticated session:     {status['is_authenticated']}")
    print(f"Status detail:             {status['status_message']}")
    print("=" * 60)

    if status["is_authenticated"]:
        print("[OK] You have an active authentication session. The API server is ready to use.")
        return 0
    else:
        print("[WARN] No active session found. Please run this script without --check to log in.")
        return 1


async def run_interactive_login() -> int:
    """Launch visible browser, wait for user login, and export storage state."""
    print("=" * 70)
    print("  Gemini Web Authentication Setup")
    print("=" * 70)
    print("\n1. Launching a Chromium browser window...")
    print(f"   Persistent profile directory: {settings.browser_profile_path}")
    print("2. Navigate to https://gemini.google.com/ and log in with your Google account.")
    print("3. Complete any required Two-Factor Authentication (2FA) or security prompts.")
    print("4. When you see the Gemini chat interface, return here and press [ENTER].\n")

    session_manager.ensure_data_directories()

    async with async_playwright() as playwright:
        try:
            context = await playwright.chromium.launch_persistent_context(
                user_data_dir=str(settings.browser_profile_path),
                headless=False,
                user_agent=DEFAULT_USER_AGENT,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                ],
            )
        except Exception as e:
            logger.error("Failed to launch Chromium: %s", e)
            print("\n[ERROR] Playwright could not launch Chromium.")
            print("Please ensure Playwright Chromium is installed by running:")
            print("    playwright install chromium")
            return 1

        page = context.pages[0] if context.pages else await context.new_page()

        print(f"Opening {settings.GEMINI_URL} ...")
        try:
            await page.goto(settings.GEMINI_URL, wait_until="domcontentloaded", timeout=45000)
        except Exception as e:
            print(f"Note: Page navigation notification: {e}")

        print("\n>>> BROWSER IS READY <<<")
        print("Please complete sign-in in the browser window.")
        print("Waiting for login... (Will auto-detect, or press [ENTER] once you see the prompt)")

        # Poll for successful login or Enter key
        login_detected = False
        start_wait = time.time()
        max_wait = 300  # 5 minutes

        while time.time() - start_wait < max_wait:
            try:
                # Check cookies for recognized Google auth tokens
                cookies = await context.cookies()
                has_auth_cookie = any(
                    c["name"] in RECOGNIZED_AUTH_COOKIES and ("google.com" in c["domain"] or "gemini.google" in c["domain"])
                    for c in cookies
                )
                curr_url = page.url.lower()

                if has_auth_cookie and "accounts.google.com" not in curr_url:
                    print("\n[DETECTED] Google authentication session cookies found!")
                    login_detected = True
                    break

                # Also check if composer editor element appears
                composer = await page.query_selector(".ql-editor, [contenteditable='true']")
                if composer and await composer.is_visible() and "accounts.google.com" not in curr_url:
                    print("\n[DETECTED] Gemini chat interface loaded!")
                    login_detected = True
                    break
            except Exception:
                pass

            await asyncio.sleep(2)

        if not login_detected:
            print("\nTimeout waiting for login or checking session...")

        print("\nVerifying session and capturing storage state...")

        # Save storage state
        saved_file = await session_manager.save_storage_state_from_context(context)
        print(f"Session storage state saved to: {saved_file}")

        # Validate saved session
        is_valid, msg = session_manager.validate_session_state()
        print(f"Validation result: {msg}")

        await context.close()

        if is_valid:
            print("\n" + "=" * 70)
            print("  SUCCESS: Gemini Web Authentication Configured!")
            print("=" * 70)
            print("\nYour authenticated session has been securely stored locally.")
            print("You can now start the OpenAI-compatible API server:")
            print("    python run.py\n")
            return 0
        else:
            print("\n" + "=" * 70)
            print("  WARNING: Google authentication cookies were not detected.")
            print("=" * 70)
            print("If login did not complete, please run `python scripts/setup_browser.py` again.")
            return 1


def main():
    parser = argparse.ArgumentParser(description="Authenticate and setup Gemini Web browser profile")
    parser.add_argument("--check", action="store_true", help="Check current session validity without launching browser")
    args = parser.parse_args()

    if args.check:
        exit_code = asyncio.run(check_existing_session())
    else:
        exit_code = asyncio.run(run_interactive_login())
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
