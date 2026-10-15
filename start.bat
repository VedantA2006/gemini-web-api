@echo off
setlocal enabledelayedexpansion

echo ===================================================================
echo        Gemini Web - OpenAI-Compatible API Server Launcher
echo ===================================================================
echo.

:: Check for python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not in PATH!
    echo Please install Python 3.10+ from https://www.python.org/
    pause
    exit /b 1
)

:: Create virtual environment if it does not exist
if not exist .venv (
    echo [*] Creating virtual environment (.venv)...
    python -m venv .venv
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
)

echo [*] Activating virtual environment...
call .venv\Scripts\activate.bat

echo [*] Installing required packages...
python -m pip install --upgrade pip
pip install -r requirements.txt

echo [*] Ensuring Playwright browser is installed...
playwright install chromium

echo.
echo ===================================================================
echo   Starting Local API Server on http://127.0.0.1:8000
echo   Open your browser to: http://127.0.0.1:8000
echo ===================================================================
echo.
python run.py

pause
