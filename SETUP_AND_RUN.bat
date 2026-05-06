@echo off
REM ============================================================================
REM  UNIFIED INTELLIGENT AGENT - COMPLETE SETUP & RUN
REM  This script installs all dependencies and runs the agent
REM ============================================================================

setlocal enabledelayedexpansion

set "AGENT_DIR=C:\Users\maup10458\Desktop\AG\unified-agent"

echo.
echo ╔════════════════════════════════════════════════════════════════╗
echo ║                                                                ║
echo ║  🚀 UNIFIED AGENT - COMPLETE SETUP & RUN                     ║
echo ║                                                                ║
echo ╚════════════════════════════════════════════════════════════════╝
echo.

REM Verify directory
if not exist "%AGENT_DIR%" (
    echo ❌ Agent directory not found: %AGENT_DIR%
    pause
    exit /b 1
)

cd /d "%AGENT_DIR%"
echo ✅ Working directory: %cd%
echo.

REM Check Python
echo 🔍 Checking Python installation...
python --version
if errorlevel 1 (
    echo ❌ Python not found!
    pause
    exit /b 1
)
echo ✅ Python OK
echo.

REM Install dependencies
echo 📦 Installing dependencies...
echo.
pip install -q --upgrade pip
pip install -q python-dotenv
pip install -q groq
pip install -q sentence-transformers
pip install -q torch
pip install -q faiss-cpu
pip install -q rank-bm25
pip install -q PyPDF2
pip install -q python-pptx
pip install -q Pillow
pip install -q numpy
pip install -q pydantic
pip install -q requests

if errorlevel 1 (
    echo ⚠️  Some packages may have failed, but continuing...
)
echo.
echo ✅ Dependencies installed
echo.

REM Verify dotenv is installed
echo 🔍 Verifying dotenv module...
python -c "import dotenv; print('✅ python-dotenv is installed')" 2>nul
if errorlevel 1 (
    echo ❌ python-dotenv not found, installing...
    pip install python-dotenv
)
echo.

REM Run the agent
echo 🎯 Starting Unified Intelligent Agent...
echo.
python main.py demo

pause
