"""
Cookie and session import utility for Gemini Web.

Allows importing cookies directly from your existing authenticated browser
(e.g., Chrome, Edge, Firefox) into the local Playwright storage state.

Usage via Console:
    python scripts/import_cookies.py "__Secure-1PSID=...; __Secure-1PSIDTS=..."
Or run interactively:
    python scripts/import_cookies.py
"""

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings
from app.session_manager import session_manager, RECOGNIZED_AUTH_COOKIES

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("import_cookies")


def parse_cookie_input(raw: str) -> List[Dict[str, Any]]:
    """
    Parse cookies from raw string or JSON format.
    Accepts:
      1. Semicolon-separated string: "name1=val1; name2=val2"
      2. JSON array: [{"name": "...", "value": "...", "domain": "..."}, ...]
    """
    raw = raw.strip()
    if (raw.startswith('"') and raw.endswith('"')) or (raw.startswith("'") and raw.endswith("'")):
        raw = raw[1:-1].strip()
    if not raw:
        return []

    # Try JSON array first (e.g. from Cookie-Editor extension)
    if raw.startswith("[") and raw.endswith("]"):
        try:
            data = json.loads(raw)
            if isinstance(data, list):
                cookies = []
                for item in data:
                    if isinstance(item, dict) and "name" in item and "value" in item:
                        cookies.append({
                            "name": str(item["name"]).strip(),
                            "value": str(item["value"]).strip(),
                            "domain": str(item.get("domain", ".google.com")),
                            "path": str(item.get("path", "/")),
                            "expires": int(item.get("expirationDate", time.time() + 31536000)),
                            "httpOnly": bool(item.get("httpOnly", True)),
                            "secure": bool(item.get("secure", True)),
                            "sameSite": "None",
                        })
                return cookies
        except Exception:
            pass

    # Standard semicolon-separated key=value string
    cookies = []
    parts = raw.split(";")
    for part in parts:
        part = part.strip()
        if not part or "=" not in part:
            continue
        eq_idx = part.find("=")
        name = part[:eq_idx].strip().strip('"').strip("'")
        value = part[eq_idx + 1:].strip().strip('"').strip("'")

        # Filter out cookie attributes that aren't credentials
        if name.lower() in ["path", "domain", "expires", "max-age", "secure", "httponly", "samesite"]:
            continue
        if not name or not value:
            continue

        cookies.append({
            "name": name,
            "value": value,
            "domain": ".google.com",
            "path": "/",
            "expires": int(time.time() + 31536000),  # +1 year
            "httpOnly": True,
            "secure": True,
            "sameSite": "None",
        })

    return cookies


def save_cookies_as_storage_state(cookies: List[Dict[str, Any]], validate: bool = True) -> bool:
    """Save parsed cookies as Playwright storage_state.json with secure permissions."""
    if not cookies:
        print("[ERROR] No cookies found in input.")
        return False

    session_manager.ensure_data_directories()
    storage_state = {
        "cookies": cookies,
        "origins": [
            {
                "origin": "https://gemini.google.com",
                "localStorage": [],
            }
        ],
    }

    target_path = session_manager.storage_state_file
    with open(target_path, "w", encoding="utf-8") as f:
        json.dump(storage_state, f, indent=2)

    session_manager.set_restrictive_file_permissions(target_path)

    if not validate:
        return True

    # Validate
    is_valid, msg = session_manager.validate_session_state()
    print("=" * 65)
    print("Cookie Import Result")
    print("=" * 65)
    print(f"Total cookies imported: {len(cookies)}")
    print(f"Saved to:               {target_path}")
    print(f"Validation status:      {'SUCCESS' if is_valid else 'WARNING'}")
    print(f"Details:                {msg}")
    print("=" * 65)

    if is_valid:
        print("\n[OK] Authentication is now ACTIVE. You can use the Web Studio or API immediately!")
        return True
    else:
        print("\n[WARN] Cookies were saved, but none matched recognized Google authentication tokens.")
        print(f"Expected tokens like: {', '.join(sorted(RECOGNIZED_AUTH_COOKIES))}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Import Gemini Web session cookies")
    parser.add_argument("cookies", nargs="?", help="Cookie string or JSON")
    args = parser.parse_args()

    raw_input = args.cookies
    if not raw_input:
        print("=" * 65)
        print("  Gemini Web — Console Cookie Import")
        print("=" * 65)
        print("How to get your cookies from your existing browser:")
        print("1. Open Chrome/Edge/Firefox where you are logged into https://gemini.google.com/")
        print("2. Press F12 (DevTools) -> Application -> Cookies -> https://gemini.google.com")
        print("3. Copy the value of __Secure-1PSID (or copy the entire Cookie header from Network tab)")
        print("=" * 65)
        print("Paste your cookie string (e.g., __Secure-1PSID=...):")
        try:
            raw_input = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nAborted.")
            sys.exit(1)

    if not raw_input:
        print("[ERROR] No input provided.")
        sys.exit(1)

    parsed = parse_cookie_input(raw_input)
    success = save_cookies_as_storage_state(parsed)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
