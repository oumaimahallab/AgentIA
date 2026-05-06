@echo off
REM ============================================================================
REM  UNIFIED INTELLIGENT AGENT - MASTER LAUNCHER
REM  Run this from ANYWHERE to start the agent
REM ============================================================================

setlocal enabledelayedexpansion

REM Defined paths
set "AGENT_DIR=C:\Users\maup10458\Desktop\AG\unified-agent"

echo.
echo ╔════════════════════════════════════════════════════════════════╗
echo ║                                                                ║
echo ║     🚀 UNIFIED INTELLIGENT AGENT - AUTO LAUNCHER 🚀           ║
echo ║                                                                ║
echo ╚════════════════════════════════════════════════════════════════╝
echo.

REM Check if agent directory exists
if not exist "%AGENT_DIR%" (
    echo ❌ ERROR: Agent directory not found!
    echo    Expected: %AGENT_DIR%
    echo.
    pause
    exit /b 1
)

REM Check if main.py exists
if not exist "%AGENT_DIR%\main.py" (
    echo ❌ ERROR: main.py not found in agent directory!
    echo    Expected: %AGENT_DIR%\main.py
    echo.
    pause
    exit /b 1
)

echo ✅ Agent directory verified: %AGENT_DIR%
echo.
echo 📝 Navigating to agent folder...
cd /d "%AGENT_DIR%"

if errorlevel 1 (
    echo ❌ ERROR: Failed to change directory!
    pause
    exit /b 1
)

echo ✅ Current directory: !cd!
echo.
REM Run the unified agent from its virtual environment
echo 🚀 Launching Unified Agent...
.\venv\Scripts\python.exe main.py demo

pause
