@echo off
REM ==========================================================
REM  PackingMonitor single-file EXE build script
REM  Requires: .NET 8 SDK (https://dotnet.microsoft.com/download/dotnet/8.0)
REM  Output: .\publish\PackingMonitor.exe (self-contained, no runtime needed)
REM ==========================================================
setlocal enabledelayedexpansion

set "OUTDIR=publish"

echo =====================================================
echo   PackingMonitor - Build Single-File EXE
echo =====================================================
echo.

where dotnet >nul 2>nul
if errorlevel 1 (
    echo [ERROR] .NET SDK not found!
    echo         Please install .NET 8 SDK x64 from:
    echo         https://dotnet.microsoft.com/download/dotnet/8.0
    echo.
    echo         After installation, close this window and run build.bat again.
    echo.
    pause
    exit /b 1
)

echo [1/4] Cleaning previous build...
if exist "%OUTDIR%" rmdir /s /q "%OUTDIR%"
if exist bin rmdir /s /q bin
if exist obj rmdir /s /q obj

echo.
echo [2/4] Restoring NuGet packages...
dotnet restore
if errorlevel 1 (
    echo.
    echo [ERROR] Restore failed. See output above.
    pause
    exit /b 1
)

echo.
echo [3/4] Building and publishing (self-contained single-file)...
dotnet publish -c Release -r win-x64 --self-contained true ^
    /p:PublishSingleFile=true ^
    /p:IncludeNativeLibrariesForSelfExtract=true ^
    /p:EnableCompressionInSingleFile=true ^
    /p:PublishReadyToRun=true ^
    -o "%OUTDIR%"

if errorlevel 1 (
    echo.
    echo [ERROR] Publish FAILED. Scroll up to see the error message.
    pause
    exit /b 1
)

echo.
echo [4/4] Copying config.json...
copy /Y config.json "%OUTDIR%\config.json" >nul 2>nul

echo.
echo =====================================================
echo   BUILD SUCCESSFUL!
echo.
echo   Output folder: %cd%\%OUTDIR%
echo   EXE file:      %OUTDIR%\PackingMonitor.exe
echo   Config file:   %OUTDIR%\config.json
echo =====================================================
echo.
echo Opening output folder...
explorer "%OUTDIR%"
pause
endlocal
