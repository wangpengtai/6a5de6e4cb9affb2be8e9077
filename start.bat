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

REM Check if port 8000 is already in use
netstat -ano | findstr ":8000" >nul 2>&1
if %errorlevel% equ 0 (
    echo.
    echo [WARN] Port 8000 is already in use.
    echo         Killing old server process...
    for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000"') do taskkill /f /pid %%a >nul 2>&1
    timeout /t 2 >nul
    echo         Done.
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
echo Open your browser and visit: http://localhost:8000
echo.
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000

pause
