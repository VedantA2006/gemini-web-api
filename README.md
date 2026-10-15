# Gemini Web → OpenAI-Compatible API (Python)

A production-quality local API adapter that exposes an authenticated Google Gemini Web consumer session (`https://gemini.google.com/`) as an OpenAI-compatible HTTP interface (`http://127.0.0.1:8000/v1/chat/completions`).

Inspired by [OmniRoute](https://github.com/diegosouzapw/OmniRoute)'s `gemini-web` architecture, this project allows developer tools (Cursor, Cline, OpenCode, Continue, etc.) and OpenAI-compatible client SDKs to query Gemini models through your legitimate browser session without requiring a paid Google Cloud or Google AI Studio developer API key.

> [!IMPORTANT]
> **Consumer Web vs. Official API Disclaimer**  
> This is an **unofficial reverse-engineered local adapter**, not Google's officially supported API. It operates via automated browser session interaction (`gemini.google.com`) rather than Google AI Studio (`generativelanguage.googleapis.com`) or Google Cloud Vertex AI.  
> Usage is subject to Google's Terms of Service, consumer rate limits, session rotation, account security verifications (CAPTCHA/2FA), and potential web UI changes. Do not use for commercial high-concurrency production workflows.

---

## Architecture Overview

```
                                  +------------------------------------+
                                  |    OpenAI Client / SDK / IDE       |
                                  |   (Cursor, Cline, Python, curl)    |
                                  +-----------------+------------------+
                                                    | HTTP / SSE (Bearer Auth)
                                                    v
                                  +------------------------------------+
                                  |   FastAPI OpenAI Adapter Server    |
                                  |      (http://127.0.0.1:8000)       |
                                  +-----------------+------------------+
                                                    |
                                      +-------------+-------------+
                                      |                           |
                                      v                           v
                      +-------------------------------+   +----------------+
                      |   GeminiWebProvider Adapter   |   | SessionManager |
                      |    (Dual Response Capture:    |   | (data/profile, |
                      |   StreamGenerate RPC + DOM)   |   | storage_state) |
                      +---------------+---------------+   +----------------+
                                      | Playwright Automation
                                      v
                      +-------------------------------+
                      |   Managed Chromium Browser    |
                      |   https://gemini.google.com   |
                      +-------------------------------+
```

---

## Key Features

- **Standard OpenAI API Compatibility**: Implements `POST /v1/chat/completions`, `GET /v1/models`, and `GET /health`.
- **True Multi-Turn Prompt Preservation**: Emulates conversation context faithfully using role-labeled transcript flattening (`System`, `Previous conversation`, `Current user message`).
- **Dual Response Extraction Pipeline**:
  - **Primary**: Network-level interception of Google's internal `StreamGenerate` RPC response, extracting clean markdown payloads from `wrb.fr` frames.
  - **Fallback**: Real-time DOM extraction targeting `.model-response-text` and `message-content` if Google modifies RPC protocols.
- **Genuine Streaming Support**: Emits Server-Sent Events (SSE) compatible with OpenAI's `chat.completion.chunk` format as Gemini generates output.
- **Managed Persistent Browser Lifecycle**: Reuses an active Chromium context across requests instead of launching and destroying browsers per prompt.
- **Strict Security**:
  - Localhost-only binding by default (`127.0.0.1`).
  - Constant-time API Key comparison (`secrets.compare_digest`).
  - Automatic zero-credential leak design (cookies and sessions are never logged, echoed, or committed).
  - Restrictive local filesystem permissions.
  - Automated session validation with actionable re-login instructions.

---

## Differences from Official Google Gemini API

| Feature | Official Gemini Developer API | Gemini Web Local Adapter |
| :--- | :--- | :--- |
| **Authentication** | Google AI Studio / Vertex AI API key | Existing Google Web session (`data/browser-profile`) |
| **Billing** | Pay-as-you-go per token / Cloud billing | Free tier consumer account quotas |
| **Interface** | Direct gRPC / REST endpoints | Browser automation via Playwright |
| **Stability** | Documented semantic versioning SLA | Subject to consumer web UI updates |
| **Tool / Function Calling** | Native JSON Schema tool protocol | Plain text chat (tools emulated via prompt contract) |
| **Rate Limits** | Tiered developer RPM/TPM | Consumer web fair-use thresholds |

---

## Directory Structure

```
gemini-web-api/
├── app/
│   ├── __init__.py               # Package metadata
│   ├── main.py                   # FastAPI app, lifespan, size limits, exception handlers
│   ├── config.py                 # Pydantic Settings configuration loader
│   ├── auth.py                   # Bearer token validator with constant-time verification
│   ├── schemas.py                # Strict OpenAI request, response, and SSE chunk schemas
│   ├── errors.py                 # Custom error hierarchy & OpenAI error formatters
│   ├── session_manager.py        # Storage state exporter, permission guards, session checks
│   ├── providers/
│   │   ├── __init__.py
│   │   ├── base.py               # Abstract provider interface
│   │   └── gemini_web.py         # Playwright automation adapter & RPC payload parser
│   └── services/
│       ├── __init__.py
│       ├── chat_service.py       # Completion orchestration & SSE stream builder
│       └── conversation_manager.py # Thread isolation & history manager
├── scripts/
│   └── setup_browser.py          # Interactive browser login & storage state capture
├── tests/
│   ├── test_health.py            # Health check endpoint tests
│   ├── test_auth.py              # Authentication security & rejection tests
│   ├── test_schemas.py           # Request & response schema validation tests
│   ├── test_chat.py              # Mocked unit tests for non-streaming, streaming & errors
│   └── test_integration.py       # Live browser integration test (disabled by default)
├── .env.example                  # Environment configuration template
├── .gitignore                    # Comprehensive ignore rules (guards profiles & cookies)
├── requirements.txt              # Production and testing dependencies
├── pyproject.toml                # Project metadata & pytest configuration
├── README.md                     # Complete documentation
└── run.py                        # Server launch entrypoint
```

---

## Prerequisites

- **Python**: 3.12 or 3.13
- **Operating System**: Windows 10/11, macOS, or Linux (Ubuntu 22.04+)
- **Google Account**: Active access to [https://gemini.google.com/](https://gemini.google.com/)

---

## Installation & Setup

### 1. Clone & Set Up Virtual Environment

#### Windows (PowerShell):
```powershell
# Create virtual environment
python -m venv .venv

# Activate virtual environment
.\.venv\Scripts\Activate.ps1

# Upgrade pip and install dependencies
python -m pip install --upgrade pip
pip install -r requirements.txt

# Ensure Playwright Chromium browser is installed
playwright install chromium
```

#### Linux / macOS:
```bash
# Create virtual environment
python3 -m venv .venv

# Activate virtual environment
source .venv/bin/activate

# Upgrade pip and install dependencies
python3 -m pip install --upgrade pip
pip install -r requirements.txt

# Ensure Playwright Chromium browser is installed
playwright install chromium
```

---

### 2. Manual Browser Authentication (One-time)

Run the interactive session setup utility:

```powershell
python scripts/setup_browser.py
```

1. A visible Chromium browser window will open navigating to `https://gemini.google.com/`.
2. Sign in to your Google Account manually.
3. Complete any Two-Factor Authentication (2FA) or device verification.
4. Once you see the Gemini prompt interface, return to your terminal and press **[ENTER]**.
5. The script automatically exports and verifies your session state into `./data/storage_state.json` and closes the browser cleanly.

To check whether your session is valid at any time without opening a browser:
```powershell
python scripts/setup_browser.py --check
```

---

### 3. Configuration

When running `python run.py` for the first time, a `.env` file is generated automatically with a secure 32-byte random `API_KEY`. You can customize settings in `.env`:

```env
# Server Configuration
HOST=127.0.0.1
PORT=8000

# Security (Leave empty to permit unauthenticated local requests)
API_KEY=your-secure-random-token

# Browser & Profile Paths
BROWSER_PROFILE_DIR=./data/browser-profile
STORAGE_STATE_PATH=./data/storage_state.json
HEADLESS=true

# Operational Controls
LOG_LEVEL=INFO
REQUEST_TIMEOUT_SECONDS=120
MAX_CONCURRENT_REQUESTS=1
DEFAULT_MODEL=gemini-web
```

---

### 4. Launch the Server

```powershell
python run.py
```

The server binds to `http://127.0.0.1:8000` with:
- **Health Check**: `http://127.0.0.1:8000/health`
- **Models Endpoint**: `http://127.0.0.1:8000/v1/models`
- **Completions Endpoint**: `http://127.0.0.1:8000/v1/chat/completions`

---

## API Reference & Usage

### 1. Health Check
```bash
curl http://127.0.0.1:8000/health
```
**Response:**
```json
{
  "status": "ok",
  "browser_connected": true,
  "authenticated": true,
  "version": "0.1.0"
}
```

---

### 2. List Models
```bash
curl http://127.0.0.1:8000/v1/models \
  -H "Authorization: Bearer your-secure-random-token"
```
**Response:**
```json
{
  "object": "list",
  "data": [
    { "id": "gemini-web", "object": "model", "created": 1700000000, "owned_by": "google-web" },
    { "id": "gemini-2.5-pro", "object": "model", "created": 1700000000, "owned_by": "google-web" },
    { "id": "gemini-2.5-flash", "object": "model", "created": 1700000000, "owned_by": "google-web" },
    { "id": "gemini-3.1-pro", "object": "model", "created": 1700000000, "owned_by": "google-web" },
    { "id": "gemini-3.7-flash", "object": "model", "created": 1700000000, "owned_by": "google-web" }
  ]
}
```

---

### 3. Non-Streaming Chat Completion

#### Using `curl`:
```bash
curl http://127.0.0.1:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your-secure-random-token" \
  -d '{
    "model": "gemini-web",
    "messages": [
      { "role": "system", "content": "You are a concise engineering assistant." },
      { "role": "user", "content": "Explain retrieval-augmented generation in 2 sentences." }
    ],
    "stream": false
  }'
```

**Response:**
```json
{
  "id": "chatcmpl-a9f4c32b1e0d",
  "object": "chat.completion",
  "created": 1744548000,
  "model": "gemini-web",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "Retrieval-augmented generation (RAG) grounds language models by retrieving relevant external documents from a knowledge base before generating responses. This mitigates hallucinations and ensures outputs remain accurate and up-to-date."
      },
      "finish_reason": "stop"
    }
  ],
  "usage": null
}
```

---

### 4. Streaming Chat Completion (SSE)

#### Using `curl`:
```bash
curl http://127.0.0.1:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your-secure-random-token" \
  -d '{
    "model": "gemini-web",
    "messages": [
      { "role": "user", "content": "Write a 3-line poem about space." }
    ],
    "stream": true
  }'
```

**Stream Output:**
```
data: {"id":"chatcmpl-a9f4c32b1e0d","object":"chat.completion.chunk","created":1744548000,"model":"gemini-web","choices":[{"index":0,"delta":{"role":"assistant","content":""},"finish_reason":null}]}

data: {"id":"chatcmpl-a9f4c32b1e0d","object":"chat.completion.chunk","created":1744548000,"model":"gemini-web","choices":[{"index":0,"delta":{"content":"Stars whisper in silence,"},"finish_reason":null}]}

data: {"id":"chatcmpl-a9f4c32b1e0d","object":"chat.completion.chunk","created":1744548000,"model":"gemini-web","choices":[{"index":0,"delta":{"content":" across the dark expanse."},"finish_reason":null}]}

data: {"id":"chatcmpl-a9f4c32b1e0d","object":"chat.completion.chunk","created":1744548000,"model":"gemini-web","choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}

data: [DONE]
```

---

### 5. Python OpenAI SDK Client Example

```python
import os
from openai import OpenAI

# Initialize client pointing to local Gemini Web adapter
client = OpenAI(
    base_url="http://127.0.0.1:8000/v1",
    api_key="your-secure-random-token",  # from your .env
)

# Standard non-streaming call
response = client.chat.completions.create(
    model="gemini-web",
    messages=[
        {"role": "system", "content": "You are a helpful Python mentor."},
        {"role": "user", "content": "Explain Python decorators with a clean example."},
    ],
    stream=False,
)
print("Assistant:", response.choices[0].message.content)

# Streaming call
stream = client.chat.completions.create(
    model="gemini-web",
    messages=[
        {"role": "user", "content": "List 3 advantages of asynchronous programming."},
    ],
    stream=True,
)
for chunk in stream:
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="", flush=True)
print()
```

---

## Error Handling & Status Codes

All errors return standard OpenAI-compatible JSON error payloads:

```json
{
  "error": {
    "message": "Human-readable description of what failed",
    "type": "invalid_request_error",
    "param": null,
    "code": "specific_error_code"
  }
}
```

| HTTP Code | Error Code (`code`) | Reason & Recommended Fix |
| :--- | :--- | :--- |
| **400** | `invalid_request` | Empty messages list, missing user message, or malformed schema. |
| **401** | `invalid_api_key` | Missing or mismatched `Authorization: Bearer <API_KEY>`. Check `.env`. |
| **401** | `session_expired` | Gemini Web session not found or redirected to Google login. Run `python scripts/setup_browser.py`. |
| **403** | `account_challenge_required` | Google displayed a security check or CAPTCHA. Run `python scripts/setup_browser.py` in headed mode to solve it. |
| **404** | `model_not_found` | Requested model is unsupported. Query `/v1/models` for available aliases. |
| **413** | `request_too_large` | Request payload exceeded 2MB body limit. |
| **429** | `rate_limit_exceeded` | Gemini Web usage quota reached. Wait before submitting more prompts. |
| **502** | `provider_error` | Gemini Web UI changed or response extraction failed. |
| **503** | `browser_unavailable` | Playwright Chromium executable missing. Run `playwright install chromium`. |
| **504** | `gateway_timeout` | Generation exceeded `REQUEST_TIMEOUT_SECONDS` (default: 120s). |

---

## Session Expiration & Re-Login Workflow

Google rotates web authentication cookies (`__Secure-1PSID`, `__Secure-1PSIDTS`) periodically or invalidates them when security checks are triggered.

If an API request returns `401 session_expired`:
1. Run:
   ```powershell
   python scripts/setup_browser.py
   ```
2. Re-authenticate your Google Account in the browser window.
3. Press **[ENTER]** in the terminal to capture the new storage state.
4. Resume your API client requests without restarting the API server.

---

## Security Practices

- **Localhost Bound**: The server binds to `127.0.0.1` by default. Do not expose this port to public networks or 0.0.0.0 without a TLS reverse proxy and strict firewall rules.
- **Constant-Time Verification**: API tokens are compared using `secrets.compare_digest` to prevent timing analysis attacks.
- **Strict Git Hygiene**: `.gitignore` comprehensively excludes all profile directories, cookies, storage states, and `.env` files.
- **Zero Credential Logging**: Logging statements strictly avoid printing cookie names, values, or authentication tokens.
- **No Remote Code / Arbitrary Navigation**: API callers cannot trigger arbitrary URL navigation or control browser debugging ports.

---

## Known Limitations

1. **Native Function Calling**: Gemini Web does not expose structured function calling schemas. Tool prompts are formatted as text contracts.
2. **Usage Metrics (`usage`)**: Token counts are omitted (`usage: null`) rather than fabricated, preserving integrity.
3. **Concurrency Serialization**: Web browser interfaces can only type and submit one prompt per browser page at a time. The adapter uses an `asyncio.Lock` to serialize prompt submissions cleanly.
4. **No Unlimited Usage**: Google imposes consumer rate limits and anti-abuse safeguards. Excessive automated request rates may trigger temporary cooldowns or CAPTCHAs.

---

## Testing

Run automated unit tests:

```powershell
# Run full unit test suite (22 unit tests)
pytest -v
```

Run real integration test (requires an active user session):
```powershell
$env:RUN_INTEGRATION_TESTS="1"
pytest tests/test_integration.py -v
```
