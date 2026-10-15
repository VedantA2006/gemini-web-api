"""Application configuration module using Pydantic Settings."""

from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Server Configuration
    HOST: str = "127.0.0.1"
    PORT: int = 8000

    # API Security (Optional key. When set, requests must provide 'Bearer <API_KEY>')
    API_KEY: Optional[str] = None

    # Browser & Profile Management
    BROWSER_PROFILE_DIR: str = "./data/browser-profile"
    STORAGE_STATE_PATH: str = "./data/storage_state.json"
    HEADLESS: bool = True

    # Direct Cookie Authentication via .env
    GEMINI_COOKIES: Optional[str] = None
    GEMINI_COOKIE: Optional[str] = None
    COOKIE: Optional[str] = None
    GEMINI_1PSID: Optional[str] = None
    SECURE_1PSID: Optional[str] = None
    GEMINI_1PSIDTS: Optional[str] = None
    SECURE_1PSIDTS: Optional[str] = None

    # Performance & Concurrency Limits
    LOG_LEVEL: str = "INFO"
    REQUEST_TIMEOUT_SECONDS: int = 120
    MAX_CONCURRENT_REQUESTS: int = 3
    MAX_REQUEST_SIZE_BYTES: int = 2 * 1024 * 1024  # 2MB request body cap

    # Model Defaults & URLs
    DEFAULT_MODEL: str = "gemini-web"
    GEMINI_URL: str = "https://gemini.google.com/app"

    @property
    def browser_profile_path(self) -> Path:
        """Resolve absolute path to persistent browser profile directory."""
        return Path(self.BROWSER_PROFILE_DIR).resolve()

    @property
    def storage_state_file(self) -> Path:
        """Resolve absolute path to storage state JSON file."""
        return Path(self.STORAGE_STATE_PATH).resolve()


settings = Settings()
