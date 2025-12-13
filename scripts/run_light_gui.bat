@echo off
REM MintChat 浅色主题 GUI 启动脚本 (Windows)
REM 版本: v2.8.0
REM Material Design 3 浅色主题 + QQ 风格 + 可爱渐变色

chcp 65001 >nul

echo ======================================================================
echo MintChat 浅色主题 GUI 启动器
echo v2.8.0 - Material Design 3 + QQ 风格
echo ======================================================================
echo.

REM 检查 conda 是否安装
where conda >nul 2>nul
if %errorlevel% neq 0 (
    echo [错误] 未检测到 Conda，请先安装 Miniconda 或 Anaconda
    echo.
    echo 下载地址: https://docs.conda.io/en/latest/miniconda.html
    echo.
    pause
    exit /b 1
)

REM 检查 mintchat 环境是否存在
conda env list | findstr /C:"mintchat" >nul 2>nul
if %errorlevel% neq 0 (
    echo [提示] 未检测到 mintchat 环境，正在创建...
    echo.
    conda create -n mintchat python=3.12 -y
    if %errorlevel% neq 0 (
        echo [错误] 创建环境失败
        pause
        exit /b 1
    )
)

REM 激活环境
echo [1/3] 激活 mintchat 环境...
call conda activate mintchat
if %errorlevel% neq 0 (
    echo [错误] 激活环境失败
    pause
    exit /b 1
)

REM 检查 PyQt6 是否安装
echo [2/3] 检查 PyQt6...
python -c "import PyQt6" >nul 2>nul
if %errorlevel% neq 0 (
    echo [提示] PyQt6 未安装，正在安装...
    pip install "PyQt6>=6.6.0"
    if %errorlevel% neq 0 (
        echo [错误] 安装 PyQt6 失败
        pause
        exit /b 1
    )
)

REM 启动 GUI
echo [3/3] 启动浅色主题 GUI...
echo.
python mintchat_light_gui.py

if %errorlevel% neq 0 (
    echo.
    echo [错误] GUI 启动失败
    pause
    exit /b 1
)

