#!/usr/bin/env python3
"""
Create `config.yaml` from `config.yaml.example` if missing.

This keeps the repo safe (example is committed; real keys stay local and ignored by Git).
"""

from __future__ import annotations

from pathlib import Path
import shutil
import sys


def main() -> int:
    project_root = Path(__file__).resolve().parent.parent
    config_file = project_root / "config.yaml"
    example_file = project_root / "config.yaml.example"

    if config_file.exists():
        print(f"[OK] 已存在: {config_file}")
        return 0

    if not example_file.exists():
        print(f"[ERROR] 未找到配置模板: {example_file}")
        return 1

    shutil.copy(example_file, config_file)
    print(f"[OK] 已创建: {config_file}")
    print("请编辑并填入你的 API Key / 配置后再启动 MintChat。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
