@echo off
REM ============================================================
REM MintChat 浅色主题 GUI 启动脚本 (Windows)
REM 说明: 使用 uv + .venv 启动浅色主题 GUI（scripts/mintchat_light_gui.py）
REM ============================================================

chcp 65001 >nul
setlocal enabledelayedexpansion

pushd "%~dp0.."

echo ======================================================================
echo MintChat 浅色主题 GUI 启动器
echo ======================================================================
echo.

where uv >nul 2>&1
if errorlevel 1 (
    echo [错误] 未检测到 uv
    echo.
    echo 请先安装 uv（推荐使用 pipx）:
    echo   pipx install uv
    echo.
    pause
    popd
    exit /b 1
)

if not exist "config.user.yaml" (
    if exist "config.yaml" (
        echo [信息] 检测到 legacy 配置 config.yaml（仍可兼容读取），建议迁移到 config.user.yaml。
    ) else if exist "config.user.yaml.example" (
        copy "config.user.yaml.example" "config.user.yaml" >nul
        echo [信息] 已创建 config.user.yaml，请编辑并填入 API Key 后再启动。
        echo.
        pause
        popd
        exit /b 0
    ) else (
        echo [错误] 未找到 config.user.yaml.example
        echo.
        pause
        popd
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
    popd
    exit /b 1
)

echo [启动] 正在启动浅色主题 GUI...
echo.
.\.venv\Scripts\python.exe scripts/mintchat_light_gui.py

if errorlevel 1 (
    echo.
    echo [错误] GUI 启动失败
    echo.
    pause
    popd
    exit /b 1
)

popd
