#!/bin/bash

echo "======================================================================"
echo "MintChat 浅色主题 GUI 启动器"
echo "======================================================================"
echo ""

# 检查 conda 是否安装
if ! command -v conda &> /dev/null; then
    echo "[错误] 未检测到 Conda，请先安装 Miniconda 或 Anaconda"
    echo ""
    echo "下载地址: https://docs.conda.io/en/latest/miniconda.html"
    echo ""
    exit 1
fi

# 检查 mintchat 环境是否存在
if ! conda env list | grep -q "mintchat"; then
    echo "[提示] 未检测到 mintchat 环境，正在创建..."
    echo ""
    conda create -n mintchat python=3.12 -y
    if [ $? -ne 0 ]; then
        echo "[错误] 创建环境失败"
        exit 1
    fi
fi

# 激活环境
echo "[1/3] 激活 mintchat 环境..."
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate mintchat
if [ $? -ne 0 ]; then
    echo "[错误] 激活环境失败"
    exit 1
fi

# 检查 PyQt6 是否安装
echo "[2/3] 检查 PyQt6..."
python -c "import PyQt6" &> /dev/null
if [ $? -ne 0 ]; then
    echo "[提示] PyQt6 未安装，正在安装..."
    pip install "PyQt6>=6.6.0"
    if [ $? -ne 0 ]; then
        echo "[错误] 安装 PyQt6 失败"
        exit 1
    fi
fi

# 启动 GUI
echo "[3/3] 启动浅色主题 GUI..."
echo ""
python mintchat_light_gui.py

if [ $? -ne 0 ]; then
    echo ""
    echo "[错误] GUI 启动失败"
    exit 1
fi

