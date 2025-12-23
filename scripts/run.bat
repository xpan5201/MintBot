@echo off
REM ============================================================
REM MintChat 命令行启动脚本 (Windows)
REM 说明: 使用 uv + .venv 启动 MintChat（交互式示例菜单）
REM ============================================================

chcp 65001 >nul
setlocal enabledelayedexpansion

pushd "%~dp0.."

echo.
echo ============================================================
echo   MintChat - 多模态猫娘女仆智能体 (命令行版本)
echo ============================================================
echo.

REM 检查 uv 是否安装
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

REM 初始化 config.yaml（如缺失则从模板创建）
if not exist "config.yaml" (
    if exist "config.yaml.example" (
        copy "config.yaml.example" "config.yaml" >nul
        echo [信息] 已创建 config.yaml，请编辑并填入 API Key 后再启动。
        echo.
        pause
        popd
        exit /b 0
    ) else (
        echo [错误] 未找到 config.yaml.example
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

echo [启动] 正在启动 MintChat...
echo.
.\.venv\Scripts\python.exe scripts/start.py

if errorlevel 1 (
    echo.
    echo [错误] 启动失败
    echo.
    echo 请检查:
    echo   1. config.yaml 文件是否存在并配置正确
    echo   2. API Key 是否有效
    echo   3. 依赖是否完整安装（可重试: uv sync --locked --no-install-project）
    echo.
    pause
    popd
    exit /b 1
)

echo.
echo [信息] MintChat 已退出
echo.
pause
popd
