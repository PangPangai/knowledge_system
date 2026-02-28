@echo off
chcp 65001 > nul
echo ===================================================
echo      RAG Index Rebuilder (API Mode)
echo ===================================================
echo.

if not exist "venv\Scripts\python.exe" (
    echo ❌ Virtual environment not found!
    pause
    exit /b 1
)

REM -------------------------------------------------------
REM Phase 1: Fast clear - delete chroma_db while service is stopped
REM -------------------------------------------------------
echo 📋 [Phase 1/3] 清空数据库...
echo ⚠️  请确保后端服务已关闭！（否则文件被占用无法删除）
echo.
pause

set CHROMA_DIR=chroma_db
if exist "%CHROMA_DIR%" (
    echo 🗑️  正在删除 %CHROMA_DIR% ...
    rmdir /s /q "%CHROMA_DIR%"
    if exist "%CHROMA_DIR%" (
        echo ❌ 删除失败！请先关闭后端服务再重试。
        pause
        exit /b 1
    )
    echo    ✅ 已删除 %CHROMA_DIR%
) else (
    echo    ℹ️  %CHROMA_DIR% 不存在，跳过删除
)

REM -------------------------------------------------------
REM Phase 2: Start backend in a new window
REM -------------------------------------------------------
echo.
echo 🚀 [Phase 2/3] 启动后端服务...
start "RAG Backend" cmd /k "cd /d %~dp0 && venv\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port 8000"

echo    ⏳ 等待后端启动 (15s)...
timeout /t 15 /nobreak > nul

REM -------------------------------------------------------
REM Phase 3: Upload all PDFs via API
REM -------------------------------------------------------
echo.
echo 📤 [Phase 3/3] 开始上传文档...
.\venv\Scripts\python.exe rebuild_index.py

if %errorlevel% neq 0 (
    echo.
    echo ❌ 上传失败，错误码: %errorlevel%
    pause
    exit /b %errorlevel%
)

echo.
echo ✅ Rebuild 完成！
pause
