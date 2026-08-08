@echo off
chcp 65001 >nul
title 灵犀引擎

cd /d "%~dp0"

echo.
echo  ========================================
echo    灵犀引擎 正在启动，请稍候...
echo  ========================================
echo.

if exist "config\local.env" (
  for /f "usebackq eol=# tokens=1,* delims==" %%a in ("config\local.env") do (
    if not "%%a"=="" set "%%a=%%b"
  )
)

start "灵犀引擎服务" /MIN cmd /c "python api_server.py"

echo  等待服务就绪...
timeout /t 4 /nobreak >nul

start "" "http://127.0.0.1:9200/dashboard"

echo.
echo  浏览器将自动打开操作页面。
echo  若未自动打开，请手动访问: http://127.0.0.1:9200/dashboard
echo.
echo  关闭本窗口不会停止服务；要停止请在任务栏找到「灵犀引擎服务」窗口。
echo.
pause
