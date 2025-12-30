#!/usr/bin/env bash
# ============================================================
# MintChat 启动脚本 (Linux/macOS)
# 说明: 使用 uv + .venv 启动 MintChat（交互式示例菜单）
# ============================================================

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo ""
echo "============================================================"
echo "  MintChat - 多模态猫娘女仆智能体 (命令行版本)"
echo "============================================================"
echo ""

if ! command -v uv >/dev/null 2>&1; then
  echo "[错误] 未检测到 uv"
  echo ""
  echo "请先安装 uv（官方安装脚本）:"
  echo "  curl -LsSf https://astral.sh/uv/install.sh | sh"
  echo ""
  exit 1
fi

if [[ ! -f "config.user.yaml" ]]; then
  if [[ -f "config.yaml" ]]; then
    echo "[信息] 检测到 legacy 配置 config.yaml（仍可兼容读取），建议迁移到 config.user.yaml。"
  elif [[ -f "config.user.yaml.example" ]]; then
    cp "config.user.yaml.example" "config.user.yaml"
    echo "[信息] 已创建 config.user.yaml，请编辑并填入 API Key 后再启动。"
    exit 0
  else
    echo "[错误] 未找到 config.user.yaml.example"
    exit 1
  fi
fi

echo "[信息] 正在同步依赖 (uv sync --locked --no-install-project)..."
uv sync --locked --no-install-project

echo ""
echo "[启动] 正在启动 MintChat..."
echo ""
.venv/bin/python scripts/start.py
