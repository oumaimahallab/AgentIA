@echo off
REM ============================================================================
REM  DIAGNOSTIC SCRIPT - Identify the exact problem
REM ============================================================================

setlocal enabledelayedexpansion

set "AGENT_DIR=C:\Users\maup10458\Desktop\AG\unified-agent"

echo.
echo ╔════════════════════════════════════════════════════════════════╗
echo ║                   DIAGNOSTIC REPORT                           ║
echo ╚════════════════════════════════════════════════════════════════╝
echo.

REM Check directory
echo 1️⃣  CHECKING DIRECTORY...
if exist "%AGENT_DIR%" (
    echo   ✅ Agent directory exists: %AGENT_DIR%
) else (
    echo   ❌ Agent directory NOT FOUND: %AGENT_DIR%
    goto ERROR
)

if exist "%AGENT_DIR%\main.py" (
    echo   ✅ main.py found
) else (
    echo   ❌ main.py NOT FOUND
    goto ERROR
)

if exist "%AGENT_DIR%\requirements.txt" (
    echo   ✅ requirements.txt found
) else (
    echo   ❌ requirements.txt NOT FOUND
)

echo.
echo 2️⃣  CHECKING PYTHON...
python --version >nul 2>&1
if errorlevel 1 (
    echo   ❌ Python not found in PATH
    goto ERROR
) else (
    python --version
    echo   ✅ Python found
)

REM Check Python executable
for /f "tokens=*" %%I in ('python -c "import sys; print(sys.executable)"') do set "PYTHON_EXE=%%I"
echo   Python executable: %PYTHON_EXE%

echo.
echo 3️⃣  CHECKING MODULES...
cd /d "%AGENT_DIR%"

REM Check each required module
set "MODULES=dotenv,groq,sentence_transformers,torch,faiss,rank_bm25,PyPDF2,pptx,PIL,numpy,pydantic,requests"

for %%M in (%MODULES%) do (
    python -c "import %%M" >nul 2>&1
    if errorlevel 1 (
        echo   ❌ MISSING: %%M
    ) else (
        echo   ✅ OK: %%M
    )
)

echo.
echo 4️⃣  RUNNING QUICK TEST...
python -c "from config.settings import UnifiedAgentConfig; print('   ✅ Config loads successfully')" 2>&1
if errorlevel 1 (
    echo   ❌ Config failed to load
) else (
    echo   ✅ Config OK
)

echo.
echo ╔════════════════════════════════════════════════════════════════╗
echo ║                   DIAGNOSIS COMPLETE                          ║
echo ╚════════════════════════════════════════════════════════════════╝
echo.

pause
exit /b 0

:ERROR
echo.
echo ╔════════════════════════════════════════════════════════════════╗
echo ║                   ERROR DETECTED                              ║
echo ╚════════════════════════════════════════════════════════════════╝
echo.
pause
exit /b 1
