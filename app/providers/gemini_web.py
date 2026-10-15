"""Gemini Web Provider Adapter using Playwright automation."""

import asyncio
import json
import logging
import re
import time
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple

from playwright.async_api import BrowserContext, Page, async_playwright

from app.config import settings
from app.errors import (
    AccountChallengeError,
    AuthenticationExpiredError,
    AuthenticationRequiredError,
    BrowserUnavailableError,
    GeminiTimeoutError,
    ModelNotFoundError,
    ProviderError,
    RateLimitError,
)
from app.providers.base import BaseProvider
from app.schemas import ChatMessage
from app.session_manager import session_manager

logger = logging.getLogger(__name__)

# Supported model identifiers mapped to this provider (matching Google Gemini's live UI)
SUPPORTED_MODELS = [
    "gemini-web",
    "gemini-4-argon",
    "4-argon",
    "argon",
    "gemini-3.8-flash",
    "3.8-flash",
    "gemini-3.6-flash",
    "flash",
    "gemini-3.1-pro",
    "3.1-pro",
    "pro",
    "gemini-3.5-flash",
    "3.5-flash",
    "gemini-3.5-flash-lite",
    "3.5-flash-lite",
    "flash-lite",
    "gemini-thinking",
    "gemini-3.6-thinking",
    "thinking",
    "gemini-2.5-pro",
    "gemini-2.5-flash",
]

# Exact configuration for Gemini Web mode switcher matching the live Google interface
MODEL_SPECS = [
    {
        "aliases": ["gemini-3.5-flash", "3.5-flash", "gemini-3.5-flash-lite", "3.5-flash-lite", "flash-lite", "lite"],
        "display_name": "3.5 Flash",
        "btn_matches": ["3.5", "flash-lite", "lite"],
        "btn_excludes": ["3.8"],
        "menu_match": lambda txt: "3.5" in txt.lower() or "lite" in txt.lower() or "fastest answers" in txt.lower(),
        "requires_auth": False,
    },
    {
        "aliases": ["gemini-4-argon", "4-argon", "argon"],
        "display_name": "4 Argon",
        "btn_matches": ["argon"],
        "btn_excludes": [],
        "menu_match": lambda txt: "argon" in txt.lower() or "complex tasks" in txt.lower(),
        "requires_auth": True,
    },
    {
        "aliases": ["gemini-3.1-pro", "3.1-pro", "pro", "gemini-pro", "gemini-2.5-pro"],
        "display_name": "3.1 Pro",
        "btn_matches": ["pro"],
        "btn_excludes": [],
        "menu_match": lambda txt: "pro" in txt.lower() or "advanced reasoning" in txt.lower(),
        "requires_auth": True,
    },
    {
        "aliases": ["gemini-3.8-flash", "3.8-flash", "gemini-3.6-flash", "flash", "gemini-flash", "gemini-2.5-flash"],
        "display_name": "3.8 Flash",
        "btn_matches": ["3.8", "flash"],
        "btn_excludes": ["lite", "3.5"],
        "menu_match": lambda txt: ("flash" in txt.lower() and "lite" not in txt.lower()) or "3.8" in txt.lower() or "all-around help" in txt.lower(),
        "requires_auth": False,
    },
    {
        "aliases": ["gemini-thinking", "gemini-3.6-thinking", "thinking"],
        "display_name": "Thinking",
        "btn_matches": ["thinking"],
        "btn_excludes": [],
        "menu_match": lambda txt: "thinking" in txt.lower() or "solves complex problems" in txt.lower(),
        "requires_auth": True,
    },
]

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# Common selectors across Gemini Web revisions
COMPOSER_SELECTORS = [
    ".ql-editor",
    "[contenteditable='true']",
    "rich-textarea",
    "textarea[aria-label*='prompt' i]",
    "textarea",
]
SEND_BUTTON_SELECTORS = [
    "button[aria-label*='Send message' i]",
    "button[aria-label*='Send' i]",
    "button.send-button",
    "[data-test-id='send-button']",
    "button.mat-mdc-button-base:has(mat-icon[fonticon='send'])",
]
RESPONSE_SELECTORS = [
    ".model-response-text",
    "message-content",
    "[data-test-id='model-response-text']",
    ".response-container-content",
    "model-response",
    ".markdown",
]
STOP_BUTTON_SELECTORS = [
    "button[aria-label*='Stop' i]",
    "button[aria-label*='Parar' i]",
    ".stop-generating-button",
    "button:has(mat-icon[fonticon='stop'])",
]


def parse_stream_response(raw_text: str) -> str:
    """
    Parse Gemini's internal StreamGenerate RPC response envelope.
    Extracts text from the wrb.fr payload frame.
    """
    lines = raw_text.split("\n")
    last_text = ""

    for raw_line in lines:
        line = raw_line.strip()
        if not line or line == ")]}'" or line.isdigit():
            continue
        if "wrb.fr" not in line:
            continue
        try:
            arr = json.loads(line)
            if not isinstance(arr, list) or not arr or not isinstance(arr[0], list):
                continue
            if arr[0][0] != "wrb.fr":
                continue
            payload = arr[0][2]
            if not isinstance(payload, str):
                continue
            inner = json.loads(payload)
            # Response text array is at inner[4][0][1]
            if isinstance(inner, list) and len(inner) > 4 and isinstance(inner[4], list) and len(inner[4]) > 0:
                first_item = inner[4][0]
                if isinstance(first_item, list) and len(first_item) > 1 and isinstance(first_item[1], list):
                    text = "".join(c for c in first_item[1] if isinstance(c, str))
                    if text:
                        last_text = text
        except Exception:
            continue

    return last_text


def build_gemini_prompt(messages: List[ChatMessage]) -> str:
    """
    Format multi-turn conversation messages into a coherent prompt string.
    Preserves system instructions, prior turn history, and last user ask.
    """
    text_messages = [
        m for m in messages if isinstance(m.content, str) and m.content.strip()
    ]
    if not text_messages:
        return ""

    user_messages = [m for m in text_messages if m.role == "user"]
    if not user_messages:
        return ""

    last_user = user_messages[-1]
    last_user_idx = len(text_messages) - 1 - list(reversed(text_messages)).index(last_user)
    last_user_content = str(last_user.content).strip()

    prior_turns = [
        m for i, m in enumerate(text_messages)
        if i < last_user_idx and m.role in ("user", "assistant")
    ]

    system_text = "\n\n".join(
        str(m.content).strip() for m in text_messages if m.role == "system"
    ).strip()

    # Case 1: Single user message without system prompt
    if not prior_turns and not system_text:
        return last_user_content

    # Case 2: Single user message with system prompt
    if not prior_turns:
        return f"System:\n{system_text}\n\n{last_user_content}"

    # Case 3: Multi-turn conversation with history
    parts: List[str] = []
    if system_text:
        parts.append(f"System:\n{system_text}")

    history_lines = [
        f"{'Assistant' if m.role == 'assistant' else 'User'}: {m.content}"
        for m in prior_turns
    ]
    parts.append(f"Previous conversation:\n" + "\n\n".join(history_lines))
    parts.append(f"Current user message:\n{last_user_content}")

    return "\n\n".join(parts)


class GeminiWebProvider(BaseProvider):
    """Browser automation adapter that interfaces with an authenticated Gemini Web session."""

    def __init__(self):
        self._playwright = None
        self._browser = None
        self._context: Optional[BrowserContext] = None
        self._page_pool: asyncio.Queue = asyncio.Queue()
        self._all_pages: List[Page] = []
        self._pool_lock = asyncio.Lock()
        self._initialized = False
        self._max_concurrency = settings.MAX_CONCURRENT_REQUESTS

    def is_model_supported(self, model: str) -> bool:
        return model.lower() in [m.lower() for m in SUPPORTED_MODELS]

    def list_supported_models(self) -> List[str]:
        return list(SUPPORTED_MODELS)

    async def _ensure_context(self) -> BrowserContext:
        """Initialize or reuse the managed browser context."""
        if self._context:
            return self._context

        logger.info("Initializing Playwright browser context for Gemini Web (pool size: %d)...", self._max_concurrency)
        if not self._playwright:
            self._playwright = await async_playwright().start()

        launch_options = {
            "headless": settings.HEADLESS,
            "user_agent": DEFAULT_USER_AGENT,
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        }

        session_manager.sync_cookies_from_env()
        storage_state = str(session_manager.storage_state_file) if session_manager.has_storage_state() else None
        is_auth, _ = session_manager.validate_session_state()

        if is_auth and session_manager.has_storage_state():
            logger.info("Launching authenticated Chromium session with storage state: %s", storage_state)
            self._browser = await self._playwright.chromium.launch(
                headless=settings.HEADLESS,
                args=launch_options["args"],
            )
            self._context = await self._browser.new_context(
                user_agent=DEFAULT_USER_AGENT,
                storage_state=storage_state,
            )
        elif session_manager.has_profile_dir():
            logger.info("Using persistent browser profile at: %s", settings.browser_profile_path)
            self._context = await self._playwright.chromium.launch_persistent_context(
                user_data_dir=str(settings.browser_profile_path),
                **launch_options,
            )
            if session_manager.has_storage_state():
                try:
                    with open(session_manager.storage_state_file, "r", encoding="utf-8") as f:
                        sdata = json.load(f)
                    if "cookies" in sdata and sdata["cookies"]:
                        await self._context.add_cookies(sdata["cookies"])
                        logger.info("Injected %d storage state cookies into persistent context", len(sdata["cookies"]))
                except Exception as e:
                    logger.warning("Could not sync storage_state cookies to persistent context: %s", e)
        else:
            self._browser = await self._playwright.chromium.launch(
                headless=settings.HEADLESS,
                args=launch_options["args"],
            )
            self._context = await self._browser.new_context(
                user_agent=DEFAULT_USER_AGENT,
                storage_state=storage_state,
            )
        return self._context

    async def _create_tab(self) -> Page:
        """Create a fresh tab in the authenticated context, navigate to Gemini Web, and verify state."""
        ctx = await self._ensure_context()
        page = await ctx.new_page()
        tab_idx = len(self._all_pages) + 1
        logger.info("Spinning up tab %d/%d in pool. Navigating to %s", tab_idx, self._max_concurrency, settings.GEMINI_URL)
        await page.goto(settings.GEMINI_URL, wait_until="domcontentloaded", timeout=30000)
        await self._check_page_state(page)
        try:
            lets_go = await page.query_selector("button:has-text('Let\\'s go')")
            if lets_go and await lets_go.is_visible():
                await lets_go.click()
                await page.wait_for_timeout(200)
        except Exception:
            pass

        try:
            combined = ", ".join(COMPOSER_SELECTORS)
            await page.wait_for_selector(combined, timeout=8000, state="attached")
        except Exception:
            pass
        return page

    async def _acquire_page(self) -> Page:
        """Acquire an active tab from the pool, expanding dynamically up to MAX_CONCURRENT_REQUESTS."""
        async with self._pool_lock:
            while not self._page_pool.empty():
                p = self._page_pool.get_nowait()
                if not p.is_closed():
                    return p
                if p in self._all_pages:
                    self._all_pages.remove(p)

            if len(self._all_pages) < self._max_concurrency:
                new_p = await self._create_tab()
                self._all_pages.append(new_p)
                return new_p

        p = await self._page_pool.get()
        if p.is_closed():
            async with self._pool_lock:
                if p in self._all_pages:
                    self._all_pages.remove(p)
                new_p = await self._create_tab()
                self._all_pages.append(new_p)
                return new_p
        return p

    async def _release_page(self, page: Page) -> None:
        """Return an active tab to the pool for reuse."""
        if not page.is_closed():
            await self._page_pool.put(page)
        else:
            async with self._pool_lock:
                if page in self._all_pages:
                    self._all_pages.remove(page)

    async def _ensure_browser(self) -> Page:
        """Backward-compatibility helper returning a pool page."""
        return await self._acquire_page()

    async def _check_page_state(self, page: Page) -> None:
        """Inspect the current page to detect auth expiration or challenges."""
        current_url = page.url.lower()

        if "accounts.google.com" in current_url or "signin" in current_url:
            logger.warning("Detected redirect to Google Sign-in: %s", current_url)
            raise AuthenticationExpiredError(
                "Gemini Web session redirected to Google Sign-in. "
                "Please run `python scripts/setup_browser.py` to authenticate your session."
            )

        if "sorry/index" in current_url or "recaptcha" in current_url or "challenge" in current_url:
            logger.warning("Detected Google verification challenge: %s", current_url)
            raise AccountChallengeError(
                "Google verification or CAPTCHA challenge encountered. "
                "Please open `python scripts/setup_browser.py` to resolve interactively."
            )

    async def _find_element(self, page: Page, selectors: List[str], timeout_ms: int = 2000):
        """Find the first matching selector using instant query and combined wait."""
        for sel in selectors:
            try:
                el = await page.query_selector(sel)
                if el and await el.is_visible():
                    return el, sel
            except Exception:
                continue
        try:
            combined = ", ".join(selectors)
            el = await page.wait_for_selector(combined, timeout=timeout_ms, state="visible")
            if el:
                for sel in selectors:
                    try:
                        m = await page.query_selector(sel)
                        if m and await m.is_visible():
                            return m, sel
                    except Exception:
                        pass
                return el, selectors[0]
        except Exception:
            pass
        return None, None

    async def _reset_chat_if_needed(self, page: Page) -> None:
        """Navigate to a clean chat session or click New Chat button."""
        new_chat_btn = None
        for sel in ["button[aria-label*='New chat' i]", "a[href*='/app']", "[data-test-id='new-chat-button']"]:
            try:
                new_chat_btn = await page.query_selector(sel)
                if new_chat_btn and await new_chat_btn.is_visible():
                    await new_chat_btn.click()
                    await page.wait_for_timeout(1000)
                    return
            except Exception:
                pass

        # If button not found, navigate directly
        if not page.url.endswith("/app"):
            await page.goto(settings.GEMINI_URL, wait_until="domcontentloaded", timeout=15000)

    async def _select_model(self, page: Page, model: str) -> bool:
        """Switch Gemini Web UI mode to the requested model if different from current."""
        model_lower = model.strip().lower()
        if model_lower in ("gemini-web", "default"):
            return True  # Preserve current active model

        # Find matching spec (prioritize exact alias match)
        target_spec = None
        for spec in MODEL_SPECS:
            if model_lower in spec["aliases"]:
                target_spec = spec
                break
        if not target_spec:
            for spec in MODEL_SPECS:
                if any(alias in model_lower for alias in spec["aliases"]):
                    target_spec = spec
                    break

        # Check in-memory model cache for this tab to avoid redundant DOM operations
        if getattr(page, "__active_gemini_model__", None) == target_spec["display_name"]:
            return True

        try:
            picker = await page.query_selector(
                "[data-test-id='bard-mode-menu-button'], button[aria-label*='mode picker' i]"
            )
            if not picker or not await picker.is_visible():
                logger.debug("Mode picker button not active/visible in DOM (active chat thread); retaining %s", target_spec["display_name"])
                page.__active_gemini_model__ = target_spec["display_name"]
                return True

            curr_text = (await picker.inner_text()).strip().lower()

            # Check if target model is already active
            is_active = any(bm in curr_text for bm in target_spec["btn_matches"])
            if is_active and not any(be in curr_text for be in target_spec["btn_excludes"]):
                page.__active_gemini_model__ = target_spec["display_name"]
                logger.info("Model '%s' is already active in Gemini Web (%s)", target_spec["display_name"], curr_text)
                return True

            try:
                await picker.click(force=True, timeout=1500)
            except Exception:
                await page.evaluate("(el) => el.click()", picker)
            await page.wait_for_timeout(300)

            # Query all options in the popup menu
            options = await page.query_selector_all(
                "[role='menuitem'], [role='option'], .mat-mdc-menu-item, button.mode-item"
            )
            target_option = None
            for opt in options:
                txt = (await opt.inner_text()).strip()
                if target_spec["menu_match"](txt):
                    target_option = opt
                    break

            if not target_option:
                logger.warning("Could not find menu option for model '%s'", target_spec["display_name"])
                # Close popup by clicking picker again
                try:
                    await page.keyboard.press("Escape")
                except Exception:
                    pass
                return False

            # Check if option is disabled (e.g. requires sign-in for 4 Argon)
            is_disabled = (
                await target_option.get_attribute("disabled") is not None
                or await target_option.get_attribute("aria-disabled") == "true"
                or "disabled" in (await target_option.get_attribute("class") or "")
            )

            if is_disabled:
                # Close picker
                try:
                    await page.keyboard.press("Escape")
                except Exception:
                    pass

                # If this model does not require auth or is Flash, disabled in menu simply means it's already active
                if not target_spec.get("requires_auth", True) or "flash" in target_spec["display_name"].lower():
                    logger.info("Model '%s' is already active or free (marked disabled in menu)", target_spec["display_name"])
                    page.__active_gemini_model__ = target_spec["display_name"]
                    return True

                msg = (
                    f"Gemini model '{target_spec['display_name']}' is locked in this browser session. "
                    f"Please log in with your Google account via 'Browser Login' or import cookies."
                )
                logger.warning(msg)
                raise AuthenticationRequiredError(msg)

            try:
                await target_option.click(force=True, timeout=1500)
            except Exception:
                try:
                    await page.evaluate("(el) => el.click()", target_option)
                except Exception:
                    pass
            await page.wait_for_timeout(300)
            page.__active_gemini_model__ = target_spec["display_name"]
            logger.info("Mode successfully switched to: %s", target_spec["display_name"])
            return True

        except AuthenticationRequiredError:
            raise
        except Exception as e:
            logger.warning("Could not switch to model '%s': %s", model, e)
            return False
        return False

    async def _type_and_submit_prompt(self, page: Page, prompt: str) -> None:
        """Insert the prompt atomically and submit via send button or Enter."""
        composer_el, composer_sel = await self._find_element(page, COMPOSER_SELECTORS, timeout_ms=5000)
        if not composer_el:
            await self._check_page_state(page)
            raise ProviderError(
                "Could not locate Gemini composer input. The web interface may have changed."
            )

        try:
            lets_go = await page.query_selector("button:has-text('Let\\'s go')")
            if lets_go and await lets_go.is_visible():
                await lets_go.click()
                await page.wait_for_timeout(100)
        except Exception:
            pass

        try:
            await page.click(composer_sel, timeout=1500)
        except Exception:
            await page.evaluate("(el) => { el.focus(); el.click(); }", composer_el)

        await page.keyboard.press("Control+A")
        await page.keyboard.press("Backspace")
        await page.keyboard.insert_text(prompt)

        # Trigger input events so Angular / Quill editor registers changes and activates the Send button
        await page.evaluate("""(sel) => {
            const el = document.querySelector(sel);
            if (el) {
                el.dispatchEvent(new Event('input', { bubbles: true }));
                el.dispatchEvent(new Event('change', { bubbles: true }));
            }
        }""", composer_sel)
        await page.wait_for_timeout(150)

        submitted = False
        send_btn, _ = await self._find_element(page, SEND_BUTTON_SELECTORS, timeout_ms=800)
        if send_btn:
            try:
                is_disabled = await send_btn.get_attribute("aria-disabled") == "true" or await send_btn.get_attribute("disabled") is not None
                if not is_disabled:
                    await send_btn.click(timeout=800)
                    logger.debug("Submitted prompt via enabled send button click")
                    submitted = True
            except Exception:
                pass

        if not submitted:
            logger.debug("Submitting prompt via Enter key press on composer")
            try:
                await page.click(composer_sel, timeout=800)
            except Exception:
                pass
            await page.keyboard.press("Enter")

    async def _ensure_fresh_chat(self, page: Page) -> None:
        """Start a clean conversation thread to prevent context overflow or Google error banners."""
        try:
            await self._stop_generating(page)
            has_history = await page.evaluate("() => document.querySelectorAll('message-content, .model-response-text').length > 0")
            if has_history:
                clicked = await page.evaluate("""
                () => {
                    const btn = document.querySelector('a[href="/app"], button[aria-label*="New chat" i]');
                    if (btn) { btn.click(); return true; }
                    return false;
                }
                """)
                if clicked:
                    # Actively wait until previous messages are completely removed from DOM
                    for _ in range(25):
                        await page.wait_for_timeout(100)
                        still_has = await page.evaluate("() => document.querySelectorAll('message-content, .model-response-text').length > 0")
                        if not still_has:
                            break
                else:
                    await page.goto(settings.GEMINI_URL, wait_until="domcontentloaded", timeout=10000)
                    await page.wait_for_timeout(200)

            # Ensure composer is ready and attached
            combined_composer = ", ".join(COMPOSER_SELECTORS)
            await page.wait_for_selector(combined_composer, timeout=5000, state="attached")
        except Exception as e:
            logger.debug("Fresh chat reset note: %s", e)

    async def _extract_latest_dom_text(self, page: Page) -> str:
        """Extract the assistant's latest response or pure code block from the DOM."""
        js_extractor = """
        () => {
            // 1. Direct code block extraction (targets pure Python code inside pre code)
            const codeEls = document.querySelectorAll('model-response pre code, .model-response-text pre code, pre code');
            if (codeEls.length > 0) {
                const lastCode = codeEls[codeEls.length - 1];
                let cText = lastCode.innerText || lastCode.textContent || '';
                if (cText.includes('def calculate_signals') || cText.includes('# CONCEPT')) {
                    return '```python\\n' + cText.replace(/\\u00a0/g, ' ').replace(/\\u200b/g, '').replace(/\\ufeff/g, '').trim() + '\\n```';
                }
            }

            // 2. Error detection (Google conversational error messages)
            const textEls = document.querySelectorAll('.model-response-text, message-content');
            if (textEls.length > 0) {
                const lastText = textEls[textEls.length - 1].innerText || '';
                if (lastText.includes('I encountered an error') || lastText.includes('Something went wrong') || lastText.includes('unreachable')) {
                    return '__GOOGLE_ERROR__';
                }
            }

            // 3. Fallback standard markdown selectors
            const selectors = [
                '.model-response-text',
                'message-content',
                '[data-test-id="model-response-text"]',
                '.response-container-content',
                'model-response',
                '.markdown'
            ];
            for (const sel of selectors) {
                const els = document.querySelectorAll(sel);
                if (els.length > 0) {
                    const lastEl = els[els.length - 1];
                    const text = lastEl.innerText || lastEl.textContent || '';
                    if (text.trim().length > 0) {
                        return text.replace(/\\u00a0/g, ' ').replace(/\\u200b/g, '').replace(/\\ufeff/g, '').trim();
                    }
                }
            }
            return '';
        }
        """
        try:
            result = await page.evaluate(js_extractor)
            if not result:
                return ""
            text = str(result)
            text = text.replace("\xa0", " ").replace("\u200b", "").replace("\ufeff", "")
            if text.startswith("Copy code\n"):
                text = text[len("Copy code\n"):]
            if text.startswith("Python\n") or text.startswith("python\n"):
                text = text[len("Python\n"):]
            return text.strip()
        except Exception:
            return ""

    async def _extract_completed_code(self, page: Page) -> Optional[str]:
        """Fast DOM extraction that checks if a complete Python strategy is rendered."""
        js_code = """
        () => {
            // 1. Error detection
            const textEls = document.querySelectorAll('.model-response-text, message-content');
            if (textEls.length > 0) {
                const lastText = textEls[textEls.length - 1].innerText || '';
                if (lastText.includes('I encountered an error') || lastText.includes('Something went wrong') || lastText.includes('unreachable')) {
                    return '__GOOGLE_ERROR__';
                }
            }
            // 2. Direct code block extraction (targets code inside pre code)
            const codeEls = document.querySelectorAll('model-response pre code, .model-response-text pre code, pre code');
            if (codeEls.length > 0) {
                const lastCode = codeEls[codeEls.length - 1];
                let cText = lastCode.innerText || lastCode.textContent || '';
                cText = cText.replace(/\\u00a0/g, ' ').replace(/\\u200b/g, '').replace(/\\ufeff/g, '').trim();
                if ((cText.includes('def calculate_signals') || cText.includes('# CONCEPT')) && (cText.includes('return df') || cText.includes('return '))) {
                    return '```python\\n' + cText + '\\n```';
                }
            }
            return '';
        }
        """
        try:
            res = await page.evaluate(js_code)
            return str(res) if res else None
        except Exception:
            return None

    async def _is_generating(self, page: Page) -> bool:
        """Check if Gemini is actively generating output."""
        js_check = """
        () => {
            const stopSelectors = [
                'button[aria-label*="Stop" i]',
                'button[aria-label*="Parar" i]',
                '.stop-generating-button',
                'button:has(mat-icon[fonticon="stop"])',
                'button:has(mat-icon[data-mat-icon-name="stop"])',
                'mat-icon[fonticon="stop"]',
                '[data-test-id="stop-button"]'
            ];
            for (const sel of stopSelectors) {
                try {
                    const btn = document.querySelector(sel);
                    if (btn && btn.offsetParent !== null) {
                        return true;
                    }
                } catch(e) {}
            }
            return false;
        }
        """
        try:
            return bool(await page.evaluate(js_check))
        except Exception:
            return False

    async def _stop_generating(self, page: Page) -> None:
        """Click stop button if active to halt browser-side typewriter rendering."""
        js_stop = """
        () => {
            const stopSelectors = [
                'button[aria-label*="Stop" i]',
                'button[aria-label*="Parar" i]',
                '.stop-generating-button',
                'button:has(mat-icon[fonticon="stop"])',
                'button:has(mat-icon[data-mat-icon-name="stop"])',
                'mat-icon[fonticon="stop"]',
                '[data-test-id="stop-button"]'
            ];
            for (const sel of stopSelectors) {
                try {
                    const btn = document.querySelector(sel);
                    if (btn && btn.offsetParent !== null) {
                        btn.click();
                        return true;
                    }
                } catch(e) {}
            }
            return false;
        }
        """
        try:
            await page.evaluate(js_stop)
        except Exception:
            pass

    async def generate(self, messages: List[ChatMessage], model: str, **kwargs: Any) -> str:
        """Non-streaming response generation across the parallel tab pool."""
        if not self.is_model_supported(model):
            raise ModelNotFoundError(model)

        prompt = build_gemini_prompt(messages)
        if not prompt:
            raise ProviderError("No valid prompt content found in request messages.")

        page = await self._acquire_page()
        try:
            await self._check_page_state(page)

            # Listen for network StreamGenerate payload
            captured_network_text = {"text": ""}
            response_event = asyncio.Event()

            async def handle_response(resp):
                try:
                    if "StreamGenerate" in resp.url or "batchexecute" in resp.url:
                        raw = await resp.text()
                        parsed = parse_stream_response(raw)
                        if parsed:
                            captured_network_text["text"] = parsed
                            response_event.set()
                except Exception:
                    pass

            page.on("response", handle_response)

            try:
                # 1. Clean chat reset
                await self._ensure_fresh_chat(page)

                # 2. Switch model mode if specific model requested
                await self._select_model(page, model)

                old_dom_text = await self._extract_latest_dom_text(page)

                # 3. Type and submit
                await self._type_and_submit_prompt(page, prompt)

                # Brief 400ms pause for UI submit animation
                await page.wait_for_timeout(400)

                # 4. Instant Code-Block / Network Observer Loop (Fast Path)
                timeout_sec = settings.REQUEST_TIMEOUT_SECONDS
                start_time = time.time()
                saw_generation = False
                last_code = None
                stable_ticks = 0
                retried_enter = False

                while time.time() - start_time < timeout_sec:
                    # Fast Path 1: Instant Network StreamGenerate interception (Zero Typewriter Delay!)
                    if response_event.is_set() and captured_network_text["text"]:
                        logger.info("⚡ Fast Path: Captured response via StreamGenerate interception in %.1fs", time.time() - start_time)
                        await self._stop_generating(page)
                        return captured_network_text["text"]

                    is_generating = await self._is_generating(page)
                    if is_generating:
                        saw_generation = True

                    # Fast Path 2: Check instant code completion in DOM (only for Python strategy requests)
                    is_code_request = not ("json" in prompt.lower() and "slug" in prompt.lower())
                    if is_code_request:
                        completed_code = await self._extract_completed_code(page)
                        if completed_code == "__GOOGLE_ERROR__":
                            logger.warning("Detected Google error banner. Resetting chat...")
                            await page.goto(settings.GEMINI_URL, wait_until="domcontentloaded", timeout=15000)
                            raise ProviderError("Google session error banner encountered. Reset completed.")

                        if completed_code:
                            saw_generation = True
                            if completed_code == last_code:
                                stable_ticks += 1
                            else:
                                last_code = completed_code
                                stable_ticks = 0

                            # If code has reached 'return df' and remained stable for 200ms (2 ticks)
                            # OR if is_generating has turned False, return immediately!
                            if stable_ticks >= 2 or not is_generating:
                                logger.info("⚡ Fast Path: Instant Code Observer captured complete strategy in %.1fs", time.time() - start_time)
                                await self._stop_generating(page)
                                return completed_code

                    # Fast Path 3: DOM fallback for non-code responses once generation stops
                    if saw_generation and not is_generating and time.time() - start_time > 1.0:
                        dom_text = await self._extract_latest_dom_text(page)
                        if dom_text and dom_text != old_dom_text and dom_text != "__GOOGLE_ERROR__":
                            logger.info("Captured response text via DOM fallback in %.1fs", time.time() - start_time)
                            return dom_text

                    # Safeguard: If after 3.5s neither generation nor network event has started, retry pressing Enter
                    if not saw_generation and not retried_enter and (time.time() - start_time > 3.5):
                        retried_enter = True
                        try:
                            logger.warning("Generation hasn't started after 3.5s; re-focusing composer and pressing Enter")
                            composer_el, composer_sel = await self._find_element(page, COMPOSER_SELECTORS, timeout_ms=1000)
                            if composer_el:
                                await page.click(composer_sel, timeout=1000)
                                await page.keyboard.press("Enter")
                        except Exception as e:
                            logger.debug("Retry enter note: %s", e)

                    await page.wait_for_timeout(100)

                # Timeout reached: final check
                if response_event.is_set() and captured_network_text["text"]:
                    return captured_network_text["text"]

                dom_text = await self._extract_latest_dom_text(page)
                if dom_text and dom_text != old_dom_text and dom_text != "__GOOGLE_ERROR__":
                    return dom_text

                raise GeminiTimeoutError()
            finally:
                page.remove_listener("response", handle_response)

        finally:
            await self._release_page(page)

    async def stream_generate(
        self, messages: List[ChatMessage], model: str, **kwargs: Any
    ) -> AsyncIterator[str]:
        """Incremental streaming generation via DOM polling."""
        if not self.is_model_supported(model):
            raise ModelNotFoundError(model)

        prompt = build_gemini_prompt(messages)
        if not prompt:
            raise ProviderError("No valid prompt content found in request messages.")

        page = await self._acquire_page()
        try:
            await self._check_page_state(page)
            await self._select_model(page, model)
            await self._type_and_submit_prompt(page, prompt)

            timeout_sec = settings.REQUEST_TIMEOUT_SECONDS
            start_time = time.time()
            emitted_len = 0
            saw_generation = False
            stable_count = 0

            await page.wait_for_timeout(400)

            while time.time() - start_time < timeout_sec:
                current_text = await self._extract_latest_dom_text(page)
                is_generating = await self._is_generating(page)

                if is_generating:
                    saw_generation = True

                if len(current_text) > emitted_len:
                    delta = current_text[emitted_len:]
                    emitted_len = len(current_text)
                    stable_count = 0
                    yield delta

                if saw_generation and not is_generating:
                    stable_count += 1
                    if stable_count >= 2:
                        if len(current_text) > emitted_len:
                            yield current_text[emitted_len:]
                        break

                await page.wait_for_timeout(100)

        finally:
            await self._release_page(page)

    async def check_health(self) -> Dict[str, Any]:
        """Check provider connection status across tab pool."""
        has_session = session_manager.has_session()
        active_tabs = len([p for p in self._all_pages if not p.is_closed()])
        return {
            "browser_connected": active_tabs > 0 or self._context is not None,
            "authenticated": has_session,
            "provider": "gemini-web",
            "active_tabs": active_tabs,
            "max_concurrency": self._max_concurrency,
            "supported_models": SUPPORTED_MODELS,
        }

    async def shutdown(self) -> None:
        """Gracefully close all browser tabs and Playwright process."""
        logger.info("Shutting down Gemini Web provider...")
        async with self._pool_lock:
            try:
                for p in self._all_pages:
                    if not p.is_closed():
                        await p.close()
                self._all_pages.clear()
                while not self._page_pool.empty():
                    self._page_pool.get_nowait()
                if self._context:
                    await self._context.close()
                if self._browser:
                    await self._browser.close()
                if self._playwright:
                    await self._playwright.stop()
            except Exception as e:
                logger.debug("Error during provider shutdown: %s", e)
            finally:
                self._context = None
                self._browser = None
                self._playwright = None
                self._initialized = False
