@echo off
chcp 65001 >nul
echo ========================================
echo   启动前端服务 (Next.js)
echo ========================================
echo.

cd frontend

REM Check if node_modules exists
if not exist "node_modules\" (
    echo [警告] 未检测到依赖,正在安装...
    npm install
)

echo [信息] 启动 Next.js 开发服务器...
echo [地址] http://localhost:3000
echo.

npm run dev
