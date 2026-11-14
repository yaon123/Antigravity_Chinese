@echo off
chcp 65001 >nul
title Antigravity 汉化与主题一键修复
echo ========================================================
echo   Antigravity 仿 Claude Code 主题与汉化一键修复程序
echo ========================================================
echo.
echo [*] 正在修复并注入启动钩子...
cd /d "%~dp0"
python scripts\patch_asar.py install
echo.
if %errorlevel% equ 0 (
    echo [√] 修复成功！请重新启动 Antigravity 即可生效。
) else (
    echo [X] 修复出现异常，请确认 Antigravity 是否已完全退出后重试。
)
echo.
pause
