#!/usr/bin/env bash
set -e

echo "==================================================================="
echo "       Gemini Web - OpenAI-Compatible API Server Launcher"
echo "==================================================================="
echo ""

if ! command -v python3 &> /dev/null; then
    echo "[ERROR] Python 3 is not installed or not in PATH."
    exit 1
fi

if [ ! -d ".venv" ]; then
    echo "[*] Creating virtual environment (.venv)..."
    python3 -m venv .venv
fi

echo "[*] Activating virtual environment..."
source .venv/bin/activate

echo "[*] Installing required packages..."
pip install --upgrade pip
pip install -r requirements.txt

echo "[*] Ensuring Playwright browser is installed..."
playwright install chromium

echo ""
echo "==================================================================="
echo "  Starting Local API Server on http://127.0.0.1:8000"
echo "  Open your browser to: http://127.0.0.1:8000"
echo "==================================================================="
echo ""
python run.py
