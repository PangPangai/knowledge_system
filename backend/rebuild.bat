@echo off
chcp 65001 > nul
echo ===================================================
echo      RAG Index Rebuilder (Using venv Python 3.11)
echo ===================================================
echo.

if not exist "venv\Scripts\python.exe" (
    echo ❌ Virtual environment not found!
    echo Please ensure venv is created in backend/venv
    pause
    exit /b 1
)

echo 🚀 Starting rebuild process...
.\venv\Scripts\python.exe rebuild_index.py

if %errorlevel% neq 0 (
    echo.
    echo ❌ Rebuild failed with error code %errorlevel%
    pause
    exit /b %errorlevel%
)

echo.
echo ✅ Rebuild completed successfully.
pause
