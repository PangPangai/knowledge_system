@echo off
chcp 65001 > nul
echo ===================================================
echo      强制清空知识库 (Force Clean Knowledge Base)
echo ===================================================
echo.
echo ⚠️  警告: 此操作将强制关闭所有 Python 后端进程，
echo    并永久删除所有知识库数据!
echo.
set /p confirm="确认要继续吗? (y/N): "
if /i not "%confirm%"=="y" goto :eof

echo.
echo [1/3] 正在强制关闭后端进程...
taskkill /F /IM python.exe /FI "WINDOWTITLE eq *uvicorn*" > nul 2>&1
taskkill /F /IM uvicorn.exe > nul 2>&1
echo ✅ 后端进程已清理 (如有)

echo.
echo [2/3] 正在删除数据库文件...
if exist "chroma_db" (
    rmdir /s /q "chroma_db"
    if exist "chroma_db" (
        echo ❌ 删除失败!可能有其他程序占用,请手动删除 backend/chroma_db
        pause
        exit /b 1
    ) else (
        echo ✅ 数据库已删除
    )
) else (
    echo ℹ️  数据库不存在,无需删除
)

echo.
echo [3/3] 清理完成! 
echo.
echo 请重新启动后端服务:
echo   py -m uvicorn main:app --reload
echo.
pause
