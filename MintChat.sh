#!/usr/bin/env bash

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

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

uv sync --locked --no-install-project
.venv/bin/python MintChat.py
