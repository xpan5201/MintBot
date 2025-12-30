#!/usr/bin/env python3
"""
Create `config.user.yaml` from `config.user.yaml.example` if missing.

This keeps the repo safe (example is committed; real keys stay local and ignored by Git).
"""

from __future__ import annotations

from pathlib import Path
import shutil


def main() -> int:
    project_root = Path(__file__).resolve().parent.parent
    user_config_file = project_root / "config.user.yaml"
    user_example_file = project_root / "config.user.yaml.example"
    dev_example_file = project_root / "config.dev.yaml.example"
    legacy_config_file = project_root / "config.yaml"

    if user_config_file.exists():
        print(f"[OK] 已存在: {user_config_file}")
        return 0

    if legacy_config_file.exists():
        print(f"[OK] 检测到 legacy 配置文件: {legacy_config_file}")
        print(f"建议迁移为: {user_config_file}（可选叠加 config.dev.yaml）")
        return 0

    if not user_example_file.exists():
        print(f"[ERROR] 未找到用户配置模板: {user_example_file}")
        return 1

    shutil.copy(user_example_file, user_config_file)
    print(f"[OK] 已创建: {user_config_file}")
    print("请编辑并填入你的 API Key / 配置后再启动 MintChat。")
    if dev_example_file.exists():
        print("开发者可选：复制 config.dev.yaml.example 为 config.dev.yaml，用于高级覆盖。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
