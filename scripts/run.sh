#!/bin/bash
# ============================================================
# MintChat 启动脚本 (Linux/Mac)
# 版本: v2.5.1
# 日期: 2025-11-06
# 说明: 自动激活 conda mintchat 环境并启动 MintChat
# ============================================================

set -e  # 遇到错误立即退出

echo ""
echo "============================================================"
echo "  MintChat v2.5.1 - 多模态猫娘女仆智能体"
echo "============================================================"
echo ""

# 检查 conda 是否安装
if ! command -v conda &> /dev/null; then
    echo "[错误] 未检测到 Conda"
    echo ""
    echo "MintChat 需要 Conda 环境才能正常运行"
    echo ""
    echo "请先安装 Miniconda 或 Anaconda:"
    echo "  https://docs.conda.io/en/latest/miniconda.html"
    echo ""
    echo "安装完成后，请运行以下命令创建环境:"
    echo "  conda env create -f environment.yml"
    echo ""
    echo "然后重新运行此脚本"
    echo ""
    exit 1
fi

# 检查 environment.yml 是否存在
if [ ! -f "environment.yml" ]; then
    echo "[错误] 找不到 environment.yml 文件"
    echo ""
    echo "请确保在 MintChat 项目根目录下运行此脚本"
    echo ""
    exit 1
fi

# 初始化 conda（支持不同的 shell）
if [ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]; then
    source "$HOME/miniconda3/etc/profile.d/conda.sh"
elif [ -f "$HOME/anaconda3/etc/profile.d/conda.sh" ]; then
    source "$HOME/anaconda3/etc/profile.d/conda.sh"
elif [ -f "/opt/conda/etc/profile.d/conda.sh" ]; then
    source "/opt/conda/etc/profile.d/conda.sh"
else
    # 尝试使用 conda init 的默认路径
    eval "$(conda shell.bash hook 2>/dev/null)" || {
        echo "[错误] 无法初始化 Conda"
        echo ""
        echo "请运行以下命令初始化 Conda:"
        echo "  conda init bash"
        echo ""
        echo "然后重新打开终端并运行此脚本"
        echo ""
        exit 1
    }
fi

# 检查 mintchat 环境是否存在
if ! conda env list | grep -q "^mintchat "; then
    echo "[警告] Conda 环境 'mintchat' 不存在"
    echo ""
    echo "正在创建 mintchat 环境..."
    echo "这可能需要几分钟时间，请耐心等待..."
    echo ""

    conda env create -f environment.yml

    if [ $? -ne 0 ]; then
        echo ""
        echo "[错误] 创建环境失败"
        echo ""
        echo "请检查网络连接，然后手动运行:"
        echo "  conda env create -f environment.yml"
        echo ""
        exit 1
    fi

    echo ""
    echo "[成功] 环境创建完成"
    echo ""
fi

# 显示环境信息
echo "[信息] 激活 Conda 环境: mintchat"
echo ""

# 激活 mintchat 环境
conda activate mintchat

if [ $? -ne 0 ]; then
    echo ""
    echo "[错误] 激活环境失败"
    echo ""
    echo "请尝试手动激活环境:"
    echo "  conda activate mintchat"
    echo ""
    echo "然后运行:"
    echo "  python start.py"
    echo ""
    exit 1
fi

# 显示 Python 版本
echo "[信息] Python 版本:"
python --version
echo ""

# 启动 MintChat
echo "[启动] 正在启动 MintChat..."
echo ""
python start.py

# 检查启动结果
if [ $? -ne 0 ]; then
    echo ""
    echo "[错误] 启动失败"
    echo ""
    echo "请检查:"
    echo "  1. config.yaml 文件是否存在并配置正确"
    echo "  2. API Key 是否有效"
    echo "  3. 依赖是否完整安装"
    echo ""
    echo "如需帮助，请查看 INSTALL.md 或 docs/QUICKSTART.md"
    echo ""
    exit 1
fi

echo ""
echo "[信息] MintChat 已退出"
echo ""
