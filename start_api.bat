@echo off
chcp 65001 >nul
title 灵犀引擎

cd /d "%~dp0"

echo.
echo  提示: 推荐使用「启动灵犀引擎.bat」—— 会自动打开浏览器。
echo.

if exist "config\local.env" (
  for /f "usebackq eol=# tokens=1,* delims==" %%a in ("config\local.env") do (
    if not "%%a"=="" set "%%a=%%b"
  )
)

python api_server.py
