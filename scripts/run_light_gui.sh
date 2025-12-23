#!/usr/bin/env bash

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "======================================================================"
echo "MintChat 浅色主题 GUI 启动器"
echo "======================================================================"
echo ""

if ! command -v uv >/dev/null 2>&1; then
  echo "[错误] 未检测到 uv"
  echo ""
  echo "请先安装 uv（官方安装脚本）:"
  echo "  curl -LsSf https://astral.sh/uv/install.sh | sh"
  echo ""
  exit 1
fi

if [[ ! -f "config.yaml" ]]; then
  if [[ -f "config.yaml.example" ]]; then
    cp "config.yaml.example" "config.yaml"
    echo "[信息] 已创建 config.yaml，请编辑并填入 API Key 后再启动。"
    exit 0
  else
    echo "[错误] 未找到 config.yaml.example"
    exit 1
  fi
fi

echo "[信息] 正在同步依赖 (uv sync --locked --no-install-project)..."
uv sync --locked --no-install-project

echo ""
echo "[启动] 正在启动浅色主题 GUI..."
echo ""
.venv/bin/python scripts/mintchat_light_gui.py
