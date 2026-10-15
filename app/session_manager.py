"""Browser profile and session state persistence manager."""

import json
import logging
import os
import stat
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.config import settings

logger = logging.getLogger(__name__)

# Key Google authentication cookies that signify an active Google login session
RECOGNIZED_AUTH_COOKIES = {
    "__Secure-1PSID",
    "__Secure-3PSID",
    "__Secure-1PSIDTS",
    "SID",
    "HSID",
    "SSID",
}


class SessionManager:
    """Manages secure storage, validation, and permissions for browser sessions."""

    def __init__(self):
        self.profile_dir: Path = settings.browser_profile_path
        self.storage_state_file: Path = settings.storage_state_file
        self.ensure_data_directories()

    def ensure_data_directories(self) -> None:
        """Create storage directories with secure local permissions."""
        self.profile_dir.parent.mkdir(parents=True, exist_ok=True)
        self.profile_dir.mkdir(parents=True, exist_ok=True)

        # On POSIX systems, apply chmod 700 (read/write/exec for owner only)
        if os.name == "posix":
            try:
                os.chmod(self.profile_dir.parent, stat.S_IRWXU)
                os.chmod(self.profile_dir, stat.S_IRWXU)
            except OSError as e:
                logger.debug("Failed to set POSIX permissions on profile dir: %s", e)

    def set_restrictive_file_permissions(self, file_path: Path) -> None:
        """Apply owner-only permissions (0600) to sensitive session files on POSIX."""
        if not file_path.exists():
            return

        if os.name == "posix":
            try:
                os.chmod(file_path, stat.S_IRUSR | stat.S_IWUSR)
            except OSError as e:
                logger.debug("Failed to set POSIX permissions on %s: %s", file_path, e)

    def get_cookies_from_env(self) -> List[Dict[str, Any]]:
        """Read and parse cookies defined in .env or environment variables."""
        try:
            from dotenv import load_dotenv
            load_dotenv(override=True)
        except Exception:
            pass

        raw_cookie = (
            os.getenv("GEMINI_COOKIES")
            or os.getenv("GEMINI_COOKIE")
            or os.getenv("COOKIE")
            or os.getenv("GOOGLE_COOKIES")
            or getattr(settings, "GEMINI_COOKIES", None)
            or getattr(settings, "GEMINI_COOKIE", None)
            or getattr(settings, "COOKIE", None)
            or ""
        )

        cookies: List[Dict[str, Any]] = []
        if raw_cookie and raw_cookie.strip():
            from scripts.import_cookies import parse_cookie_input
            cookies.extend(parse_cookie_input(raw_cookie))

        # Support individual environment variables
        psid = (
            os.getenv("GEMINI_1PSID")
            or os.getenv("SECURE_1PSID")
            or os.getenv("__Secure-1PSID")
            or getattr(settings, "GEMINI_1PSID", None)
            or getattr(settings, "SECURE_1PSID", None)
        )
        if psid and psid.strip():
            cookies.append({
                "name": "__Secure-1PSID",
                "value": psid.strip().strip('"').strip("'"),
                "domain": ".google.com",
                "path": "/",
                "expires": int(time.time() + 31536000),
                "httpOnly": True,
                "secure": True,
                "sameSite": "None",
            })

        psidts = (
            os.getenv("GEMINI_1PSIDTS")
            or os.getenv("SECURE_1PSIDTS")
            or os.getenv("__Secure-1PSIDTS")
            or getattr(settings, "GEMINI_1PSIDTS", None)
            or getattr(settings, "SECURE_1PSIDTS", None)
        )
        if psidts and psidts.strip():
            cookies.append({
                "name": "__Secure-1PSIDTS",
                "value": psidts.strip().strip('"').strip("'"),
                "domain": ".google.com",
                "path": "/",
                "expires": int(time.time() + 31536000),
                "httpOnly": True,
                "secure": True,
                "sameSite": "None",
            })

        return cookies

    def sync_cookies_from_env(self) -> Tuple[bool, int]:
        """Save any cookies defined in .env directly into storage_state.json."""
        env_cookies = self.get_cookies_from_env()
        if not env_cookies:
            return False, 0

        from scripts.import_cookies import save_cookies_as_storage_state
        save_cookies_as_storage_state(env_cookies, validate=False)
        has_auth = any(
            ("google.com" in c.get("domain", "") or "gemini.google" in c.get("domain", ""))
            and c.get("name") in RECOGNIZED_AUTH_COOKIES
            for c in env_cookies
        )
        logger.info("Synchronized %d cookies from .env into storage_state.json (auth_valid=%s)", len(env_cookies), has_auth)
        return has_auth, len(env_cookies)

    def has_storage_state(self) -> bool:
        """Check if storage_state.json exists and is not empty."""
        return self.storage_state_file.exists() and self.storage_state_file.stat().st_size > 10

    def has_profile_dir(self) -> bool:
        """Check if persistent browser-profile directory exists and has browser data."""
        if not self.profile_dir.exists():
            return False
        return any(self.profile_dir.iterdir())

    def has_session(self) -> bool:
        """Check if cookies in .env, storage_state.json, or browser-profile exists."""
        return bool(self.get_cookies_from_env()) or self.has_storage_state() or self.has_profile_dir()

    def validate_session_state(self) -> Tuple[bool, str]:
        """
        Validate whether the stored session holds Google auth cookies.
        Checks .env first and syncs to storage_state.json if present.
        """
        # 1. Sync from .env if configured
        has_env_auth, count = self.sync_cookies_from_env()
        if has_env_auth:
            return True, f"Valid Google authentication session active (loaded {count} cookies from .env)."

        if not self.has_storage_state():
            if self.has_profile_dir():
                return True, "Persistent browser profile directory found."
            return False, "No session state or persistent browser profile found."

        try:
            with open(self.storage_state_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            cookies = data.get("cookies", [])
            google_auth_found = False

            for cookie in cookies:
                domain = cookie.get("domain", "")
                name = cookie.get("name", "")
                if ("google.com" in domain or "gemini.google" in domain) and name in RECOGNIZED_AUTH_COOKIES:
                    google_auth_found = True
                    break

            if google_auth_found:
                return True, "Valid Google authentication session detected."
            return False, "Session state file exists but contains no recognized Google authentication cookies."
        except Exception as e:
            return False, f"Failed to inspect storage state: {str(e)}"

    async def save_storage_state_from_context(self, context: Any, destination: Optional[Path] = None) -> Path:
        """Export the current browser context state into storage_state.json safely."""
        target = destination or self.storage_state_file
        target.parent.mkdir(parents=True, exist_ok=True)

        temp_target = target.with_suffix(".tmp.json")
        await context.storage_state(path=str(temp_target))

        try:
            with open(temp_target, "r", encoding="utf-8") as f:
                new_data = json.load(f)
            new_cookies = new_data.get("cookies", [])
            has_auth = any(
                ("google.com" in c.get("domain", "") or "gemini.google" in c.get("domain", ""))
                and c.get("name") in RECOGNIZED_AUTH_COOKIES
                for c in new_cookies
            )

            # If existing target is authenticated and new one has no auth cookies, do not clobber
            if target.exists() and not has_auth:
                is_curr_auth, _ = self.validate_session_state()
                if is_curr_auth:
                    logger.warning("Preserving existing authenticated session state; ignoring unauthenticated export.")
                    if temp_target.exists():
                        temp_target.unlink()
                    return target

            if temp_target.exists():
                temp_target.replace(target)
        except Exception as e:
            logger.warning("Error processing exported session state: %s", e)
            if temp_target.exists():
                temp_target.replace(target)

        self.set_restrictive_file_permissions(target)
        logger.info("Saved browser storage state to %s", target)
        return target

    def get_auth_status(self) -> Dict[str, Any]:
        """Return high-level session status without exposing credentials."""
        is_valid, message = self.validate_session_state()
        return {
            "has_session": self.has_session(),
            "has_storage_state": self.has_storage_state(),
            "has_profile_dir": self.has_profile_dir(),
            "is_authenticated": is_valid,
            "status_message": message,
        }


session_manager = SessionManager()
