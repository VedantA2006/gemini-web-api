"""
Build a clean, self-contained distribution ZIP package for transferring to other computers.
Includes all project code, static studio UI, configuration, scripts, start launchers, and .env.
Excludes platform-specific virtual environment (.venv), pycache, and cache databases.
"""

import os
import zipfile
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
OUTPUT_ZIP = ROOT_DIR / "Gemini-Web-API.zip"
DESKTOP_ZIP = Path.home() / "Desktop" / "Gemini-Web-API.zip"

EXCLUDE_DIRS = {
    ".venv",
    "venv",
    "env",
    "__pycache__",
    ".pytest_cache",
    ".git",
    ".idea",
    ".vscode",
    "browser-profile",
}

EXCLUDE_EXTS = {
    ".pyc",
    ".pyo",
    ".pyd",
    ".log",
    ".tmp",
}

EXCLUDE_FILES = {
    "Gemini-Web-API.zip",
}


def make_zip():
    print(f"[*] Packaging project from: {ROOT_DIR}")
    print(f"[*] Destination: {OUTPUT_ZIP}")

    total_files = 0
    with zipfile.ZipFile(OUTPUT_ZIP, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(ROOT_DIR):
            root_path = Path(root)
            rel_dir = root_path.relative_to(ROOT_DIR)

            # Skip excluded directories
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS and not d.startswith(".system_")]

            # Don't add root path if it is an excluded dir
            parts = rel_dir.parts
            if any(p in EXCLUDE_DIRS for p in parts):
                continue

            for file in files:
                file_path = root_path / file
                rel_file = file_path.relative_to(ROOT_DIR)

                # Checks
                if file in EXCLUDE_FILES:
                    continue
                if file_path.suffix in EXCLUDE_EXTS:
                    continue
                if any(p in EXCLUDE_DIRS for p in rel_file.parts):
                    continue

                arcname = str(rel_file)
                zf.write(file_path, arcname)
                total_files += 1

    zip_size_mb = OUTPUT_ZIP.stat().st_size / (1024 * 1024)
    print(f"[OK] Successfully packed {total_files} files into {OUTPUT_ZIP} ({zip_size_mb:.2f} MB)")

    # Also copy to Desktop for easy user access
    try:
        import shutil
        shutil.copy2(OUTPUT_ZIP, DESKTOP_ZIP)
        print(f"[OK] Also saved copy directly to Desktop: {DESKTOP_ZIP}")
    except Exception as e:
        print(f"[WARN] Could not copy to desktop: {e}")


if __name__ == "__main__":
    make_zip()
