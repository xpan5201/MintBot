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
    legacy_config_file = project_root / "config.yaml"
    dev_config_file = project_root / "config.dev.yaml"

    if user_config_file.exists():
        print(f"[OK] exists: {user_config_file}")
        return 0

    if legacy_config_file.exists():
        print(f"[OK] detected legacy config: {legacy_config_file}")
        print(f"Please migrate to {user_config_file} (dev overrides live in {dev_config_file}).")
        return 0

    if not user_example_file.exists():
        print(f"[ERROR] missing template: {user_example_file}")
        return 1

    shutil.copy(user_example_file, user_config_file)
    print(f"[OK] created: {user_config_file}")
    print("Edit it and fill your API key(s), then start MintChat again.")
    if dev_config_file.exists():
        print("[INFO] dev config: edit config.dev.yaml (no secrets; committed).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
