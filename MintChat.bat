@echo off
REM ============================================================
REM MintChat GUI 启动脚本 (Windows)
REM 说明: 使用 uv + .venv 启动 GUI (MintChat.py)
REM ============================================================

chcp 65001 >nul
setlocal enabledelayedexpansion

cd /d "%~dp0"

where uv >nul 2>&1
if errorlevel 1 (
    echo [错误] 未检测到 uv
    echo.
    echo 请先安装 uv（推荐使用 pipx）:
    echo   pipx install uv
    echo.
    pause
    exit /b 1
)

if not exist "config.yaml" (
    if exist "config.yaml.example" (
        copy "config.yaml.example" "config.yaml" >nul
        echo [信息] 已创建 config.yaml，请编辑并填入 API Key 后再启动。
        echo.
        pause
        exit /b 0
    ) else (
        echo [错误] 未找到 config.yaml.example
        echo.
        pause
        exit /b 1
    )
)

echo [信息] 正在同步依赖 (uv sync --locked --no-install-project)...
uv sync --locked --no-install-project
if errorlevel 1 (
    echo.
    echo [错误] 依赖同步失败
    echo.
    pause
    exit /b 1
)

echo [启动] 正在启动 MintChat GUI...
echo.
.\.venv\Scripts\python.exe MintChat.py

if errorlevel 1 (
    echo.
    echo [错误] MintChat 启动失败
    echo.
    pause
    exit /b 1
)

pause
