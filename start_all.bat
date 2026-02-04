@echo off
chcp 65001 >nul
echo ========================================
echo   Knowledge System 一键启动
echo ========================================
echo.

REM Get script directory
set "ROOT_DIR=%~dp0"

REM ========================================
REM Step 1: Kill existing processes on ports
REM ========================================
echo [1/4] 清理残留进程...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8000 ^| findstr LISTEN 2^>nul') do (
    echo       终止后端残留 PID: %%a
    taskkill /F /PID %%a >nul 2>&1
)
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :3000 ^| findstr LISTEN 2^>nul') do (
    echo       终止前端残留 PID: %%a
    taskkill /F /PID %%a >nul 2>&1
)
echo       完成

REM ========================================
REM Step 2: Start Backend in new window
REM ========================================
echo [2/4] 启动后端服务...
start "Backend Server" cmd /c "cd /d %ROOT_DIR%backend && call venv\Scripts\activate && python -m uvicorn main:app --host 0.0.0.0 --port 8000"
echo       后端启动中: http://localhost:8000

REM Wait for backend to be ready (Port 8000)
echo       正在等待后端就绪... (最多60秒)
set "retries=60"
:wait_backend
timeout /t 1 /nobreak >nul
netstat -an | find ":8000" | find "LISTEN" >nul
if %errorlevel% equ 0 goto backend_ready
set /a retries-=1
if %retries% gtr 0 goto wait_backend
echo [警告] 后端启动超时，但这可能只是因为它还在加载模型...

:backend_ready
echo       后端端口已监听! 再等待5秒确保应用初始化...
timeout /t 5 /nobreak >nul

REM ========================================
REM Step 3: Start Frontend in new window
REM ========================================
echo [3/4] 启动前端服务...
start "Frontend Server" cmd /c "cd /d %ROOT_DIR%frontend && npm run dev"
echo       前端启动中: http://localhost:3000

REM Wait for frontend to be ready (Port 3000)
echo       正在等待前端就绪...
set "retries=30"
:wait_frontend
timeout /t 1 /nobreak >nul
netstat -an | find ":3000" | find "LISTEN" >nul
if %errorlevel% equ 0 goto frontend_ready
set /a retries-=1
if %retries% gtr 0 goto wait_frontend
echo [警告] 前端启动超时...

:frontend_ready
echo       前端端口已监听!

REM ========================================
REM Step 4: Open browser
REM ========================================
echo [4/4] 打开浏览器...
echo       3秒后打开...
timeout /t 3 /nobreak >nul
start "" http://localhost:3000

echo.
echo ========================================
echo   启动完成!
echo ========================================
echo   后端: http://localhost:8000/docs
echo   前端: http://localhost:3000
echo.
echo   提示: 关闭时请用 Ctrl+C 或关闭各窗口
echo ========================================
pause
