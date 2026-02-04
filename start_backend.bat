@echo off
chcp 65001 >nul
echo ========================================
echo   启动后端服务 (FastAPI)
echo ========================================
echo.

REM Auto-kill any existing processes on port 8000
echo [信息] 检查端口 8000 是否被占用...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8000 ^| findstr LISTEN 2^>nul') do (
    echo [警告] 发现残留进程 PID: %%a, 正在终止...
    taskkill /F /PID %%a >nul 2>&1
)
echo [信息] 端口 8000 已清理

cd backend

REM Check if virtual environment exists
if not exist "venv\" (
    echo [警告] 未检测到虚拟环境,正在创建 Python 3.11...
    py -3.11 -m venv venv
    call venv\Scripts\activate
    echo [信息] 安装依赖...
    python -m pip install --upgrade pip
    pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
) else (
    call venv\Scripts\activate
)

REM Check if .env exists
if not exist ".env" (
    echo [警告] 未检测到 .env 文件,请先配置!
    echo [提示] 复制 .env.example 为 .env 并填入 API Key
    pause
    exit /b 1
)

echo [信息] 启动 FastAPI 服务器...
echo [地址] http://localhost:8000
echo [文档] http://localhost:8000/docs
echo.

python -c "import uvicorn" >nul 2>&1
if %errorlevel% neq 0 (
    echo [信息] 检测到依赖缺失 uvicorn, 正在自动补全...
    python -m pip install --upgrade pip
    pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
)

python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
if %errorlevel% neq 0 (
    echo [错误] 后端服务启动失败!
    pause
)
pause
