@echo off
chcp 65001 >nul
title Antigravity 启动与汉化守护程序
cd /d "%~dp0"

echo [*] 正在检查 Antigravity 主题与汉化状态...
python scripts\patch_asar.py verify >nul 2>&1
if %errorlevel% neq 0 (
    echo [!] 检测到 Antigravity 官方版本已更新并覆盖了补丁。
    echo [*] 正在自动重新注入 Claude Code 主题与汉化钩子...
    powershell -NoProfile -ExecutionPolicy Bypass -File install.ps1
    echo.
)

set "APP_PATH=%LOCALAPPDATA%\Programs\antigravity\Antigravity.exe"
if exist "%APP_PATH%" (
    echo [*] 正在启动 Antigravity...
    start "" "%APP_PATH%"
) else (
    echo [ERROR] 未找到 Antigravity.exe，请检查安装路径。
    pause
)
