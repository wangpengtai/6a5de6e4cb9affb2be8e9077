@echo off
REM Packing Monitor - Startup Script

echo ============================================
echo  Packing Monitor - Starting...
echo ============================================
echo.

REM Check Python installation
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in PATH.
    echo Please install Python 3.9+ from https://www.python.org/
    pause
    exit /b 1
)

echo [OK] Python found:
python --version

REM Check virtual environment
if "%VIRTUAL_ENV%"=="" (
    echo [WARN] Not running in a virtual environment.
    echo It is recommended to use a venv. Continuing anyway...
) else (
    echo [OK] Virtual environment: %VIRTUAL_ENV%
)

REM Install dependencies
echo.
echo Installing dependencies...
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install dependencies.
    pause
    exit /b 1
)
echo [OK] Dependencies installed.

REM Start server
echo.
echo Starting server on 0.0.0.0:8000 ...
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000

pause
