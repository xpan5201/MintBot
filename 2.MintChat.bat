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

if not exist "config.user.yaml" (
    if exist "config.yaml" (
        echo [信息] 检测到 legacy 配置 config.yaml（仍可兼容读取），建议迁移到 config.user.yaml。
    ) else (
        if exist "config.user.yaml.example" (
            copy "config.user.yaml.example" "config.user.yaml" >nul
            echo [信息] 已创建 config.user.yaml，请编辑并填入 API Key 后再启动。
            echo.
            pause
            exit /b 0
        ) else (
            echo [错误] 未找到 config.user.yaml.example
            echo.
            pause
            exit /b 1
        )
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
