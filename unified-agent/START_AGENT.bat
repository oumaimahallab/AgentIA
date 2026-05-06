@echo off
REM ============================================================================
REM  UNIFIED INTELLIGENT AGENT - AUTO LAUNCHER
REM  This script automatically navigates to the correct folder and runs the agent
REM ============================================================================

setlocal enabledelayedexpansion

REM Get the directory where this script is located
for %%I in ("%~dp0") do set "SCRIPT_DIR=%%~fI"

REM Change to unified-agent directory
cd /d "%SCRIPT_DIR%"

REM Verify we're in the right place
if not exist "main.py" (
    echo.
    echo ❌ ERROR: main.py not found in %SCRIPT_DIR%
    echo.
    echo This script must be in the unified-agent folder!
    echo.
    pause
    exit /b 1
)

REM Run the demo
echo.
echo ✅ Starting Unified Intelligent Agent...
echo.
python main.py demo

pause
