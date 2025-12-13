@echo off
REM ============================================================
REM MintChat 命令行启动脚本 (Windows)
REM 版本: v2.8.0
REM 日期: 2025-11-06
REM 说明: 自动激活 conda mintchat 环境并启动 MintChat 命令行版本
REM ============================================================

chcp 65001 >nul
setlocal enabledelayedexpansion

echo.
echo ============================================================
echo   MintChat v2.8.0 - 多模态猫娘女仆智能体 (命令行版本)
echo ============================================================
echo.

REM 检查 conda 是否安装
where conda >nul 2>&1
if errorlevel 1 (
    echo [错误] 未检测到 Conda
    echo.
    echo MintChat 需要 Conda 环境才能正常运行
    echo.
    echo 请先安装 Miniconda 或 Anaconda:
    echo   https://docs.conda.io/en/latest/miniconda.html
    echo.
    echo 安装完成后，请运行以下命令创建环境:
    echo   conda env create -f environment.yml
    echo.
    echo 然后重新运行此脚本
    echo.
    pause
    exit /b 1
)

REM 检查 environment.yml 是否存在
if not exist "environment.yml" (
    echo [错误] 找不到 environment.yml 文件
    echo.
    echo 请确保在 MintChat 项目根目录下运行此脚本
    echo.
    pause
    exit /b 1
)

REM 检查 mintchat 环境是否存在
conda env list | findstr /C:"mintchat" >nul 2>&1
if errorlevel 1 (
    echo [警告] Conda 环境 'mintchat' 不存在
    echo.
    echo 正在创建 mintchat 环境...
    echo 这可能需要几分钟时间，请耐心等待...
    echo.

    conda env create -f environment.yml

    if errorlevel 1 (
        echo.
        echo [错误] 创建环境失败
        echo.
        echo 请检查网络连接，然后手动运行:
        echo   conda env create -f environment.yml
        echo.
        pause
        exit /b 1
    )

    echo.
    echo [成功] 环境创建完成
    echo.
)

REM 显示环境信息
echo [信息] 激活 Conda 环境: mintchat
echo.

REM 激活 mintchat 环境
call conda activate mintchat

if errorlevel 1 (
    echo.
    echo [错误] 激活环境失败
    echo.
    echo 请尝试手动激活环境:
    echo   conda activate mintchat
    echo.
    echo 然后运行:
    echo   python start.py
    echo.
    pause
    exit /b 1
)

REM 显示 Python 版本
echo [信息] Python 版本:
python --version
echo.

REM 启动 MintChat
echo [启动] 正在启动 MintChat...
echo.
python start.py

REM 检查启动结果
if errorlevel 1 (
    echo.
    echo [错误] 启动失败
    echo.
    echo 请检查:
    echo   1. config.yaml 文件是否存在并配置正确
    echo   2. API Key 是否有效
    echo   3. 依赖是否完整安装
    echo.
    echo 如需帮助，请查看 INSTALL.md 或 docs/QUICKSTART.md
    echo.
    pause
    exit /b 1
)

echo.
echo [信息] MintChat 已退出
echo.
pause
