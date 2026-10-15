"""Standardized error classes and OpenAI-compatible error formatting."""

from typing import Any, Dict, Optional


def format_openai_error(
    message: str,
    error_type: str = "invalid_request_error",
    code: Optional[str] = None,
    param: Optional[str] = None,
) -> Dict[str, Any]:
    """Format an error payload according to OpenAI API conventions."""
    return {
        "error": {
            "message": message,
            "type": error_type,
            "param": param,
            "code": code,
        }
    }


class GeminiWebError(Exception):
    """Base exception for all Gemini Web API errors."""

    def __init__(
        self,
        message: str,
        status_code: int = 500,
        error_type: str = "server_error",
        code: Optional[str] = None,
        param: Optional[str] = None,
    ):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.error_type = error_type
        self.code = code
        self.param = param

    def to_dict(self) -> Dict[str, Any]:
        return format_openai_error(
            message=self.message,
            error_type=self.error_type,
            code=self.code,
            param=self.param,
        )


class AuthenticationRequiredError(GeminiWebError):
    """Raised when an API key is required but missing or invalid."""

    def __init__(self, message: str = "Incorrect or missing API key."):
        super().__init__(
            message=message,
            status_code=401,
            error_type="authentication_error",
            code="invalid_api_key",
        )


class AuthenticationExpiredError(GeminiWebError):
    """Raised when the Gemini Web session has expired or requires user re-login."""

    def __init__(
        self,
        message: str = (
            "Gemini Web session has expired or is unauthenticated. "
            "Please run `python scripts/setup_browser.py` to authenticate your session."
        ),
    ):
        super().__init__(
            message=message,
            status_code=401,
            error_type="authentication_error",
            code="session_expired",
        )


class AccountChallengeError(GeminiWebError):
    """Raised when Google presents a bot check, CAPTCHA, or verification challenge."""

    def __init__(
        self,
        message: str = (
            "Google account verification or CAPTCHA challenge detected. "
            "Automated bypass is not supported. Please run `python scripts/setup_browser.py` "
            "in headed mode to complete verification interactively."
        ),
    ):
        super().__init__(
            message=message,
            status_code=403,
            error_type="permission_error",
            code="account_challenge_required",
        )


class RateLimitError(GeminiWebError):
    """Raised when Gemini Web rate limit or usage quota is reached."""

    def __init__(
        self,
        message: str = "Gemini Web rate limit reached. Please wait before submitting further requests.",
    ):
        super().__init__(
            message=message,
            status_code=429,
            error_type="rate_limit_error",
            code="rate_limit_exceeded",
        )


class BrowserUnavailableError(GeminiWebError):
    """Raised when the browser automation engine or executable is unavailable."""

    def __init__(
        self,
        message: str = (
            "Browser automation engine failed to initialize or Playwright Chromium is missing. "
            "Run `playwright install chromium` to verify the installation."
        ),
    ):
        super().__init__(
            message=message,
            status_code=503,
            error_type="server_error",
            code="browser_unavailable",
        )


class GeminiTimeoutError(GeminiWebError):
    """Raised when waiting for a response from Gemini Web exceeds the timeout."""

    def __init__(
        self,
        message: str = "Request timed out waiting for Gemini Web generation to complete.",
    ):
        super().__init__(
            message=message,
            status_code=504,
            error_type="server_error",
            code="gateway_timeout",
        )


class ModelNotFoundError(GeminiWebError):
    """Raised when the requested model is not supported by the adapter."""

    def __init__(self, model: str):
        super().__init__(
            message=f"Model '{model}' does not exist or is not supported by this provider.",
            status_code=404,
            error_type="invalid_request_error",
            code="model_not_found",
            param="model",
        )


class InvalidRequestError(GeminiWebError):
    """Raised when client sends an invalid request (empty messages, bad schema, etc.)."""

    def __init__(self, message: str, param: Optional[str] = None):
        super().__init__(
            message=message,
            status_code=400,
            error_type="invalid_request_error",
            code="invalid_request",
            param=param,
        )


class ProviderError(GeminiWebError):
    """Raised when an unexpected error occurs during web interaction or response extraction."""

    def __init__(self, message: str = "Failed to extract response from Gemini Web interface."):
        super().__init__(
            message=message,
            status_code=502,
            error_type="server_error",
            code="provider_error",
        )
