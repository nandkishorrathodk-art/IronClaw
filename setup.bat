@echo off
REM Ironclaw Setup Script for Windows
REM Automates the setup process

echo ========================================
echo    Ironclaw Setup Script
echo    Version: 0.1.0
echo ========================================
echo.

REM Check Python version
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found! Please install Python 3.11+ first.
    pause
    exit /b 1
)

echo [1/6] Checking Python version...
python -c "import sys; exit(0 if sys.version_info >= (3, 11) else 1)"
if %errorlevel% neq 0 (
    echo [ERROR] Python 3.11+ required. Please upgrade Python.
    pause
    exit /b 1
)
echo ✅ Python version OK

echo.
echo [2/6] Creating virtual environment...
if exist venv (
    echo Virtual environment already exists. Skipping...
) else (
    python -m venv venv
    echo ✅ Virtual environment created
)

echo.
echo [3/6] Activating virtual environment...
call venv\Scripts\activate.bat

echo.
echo [4/6] Installing dependencies...
pip install --upgrade pip
pip install -e .
echo ✅ Dependencies installed

echo.
echo [5/6] Setting up environment file...
if exist .env (
    echo .env file already exists. Skipping...
) else (
    copy .env.example .env
    echo ✅ Created .env file from template
    echo.
    echo ⚠️ IMPORTANT: Edit .env and add your API keys!
    echo    - OpenAI: https://platform.openai.com/api-keys
    echo    - Groq (FREE): https://console.groq.com/keys
)

echo.
echo [6/6] Starting Docker services...
docker --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ⚠️ Docker not found. Please install Docker to use PostgreSQL, Redis, and Qdrant.
    echo    You can still run tests without Docker.
) else (
    echo Starting PostgreSQL, Redis, and Qdrant...
    docker-compose up -d
    echo ✅ Docker services started
)

echo.
echo ========================================
echo    Setup Complete! 🎉
echo ========================================
echo.
echo Next steps:
echo   1. Edit .env and add your API keys
echo   2. Run: python -m src.api.main
echo   3. Visit: http://localhost:8000/docs
echo.
echo For help: See README.md
echo.
pause
