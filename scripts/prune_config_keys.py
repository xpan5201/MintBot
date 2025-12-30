#!/usr/bin/env python3
"""
Prune keys from YAML config files (in-place), with optional backup.

Safety goals:
- Never print secret values (only file paths and key names).
- Default to non-destructive: create a timestamped backup before writing.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
import argparse

import yaml


@dataclass(frozen=True, slots=True)
class PruneResult:
    removed: list[str]
    missing: list[str]
    backup_path: Path | None


def _load_yaml_mapping(path: Path) -> dict[str, Any]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError(f"YAML must be a mapping/object: {path}")
    return raw


def _backup_file(path: Path) -> Path | None:
    if not path.exists():
        return None
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = path.with_name(f"{path.name}.bak.{ts}")
    path.replace(backup)
    return backup


def prune_top_level_keys(path: Path, keys: list[str], *, backup: bool = True) -> PruneResult:
    data = _load_yaml_mapping(path)

    removed: list[str] = []
    missing: list[str] = []
    for key in keys:
        if key in data:
            data.pop(key, None)
            removed.append(key)
        else:
            missing.append(key)

    backup_path: Path | None = None
    if backup:
        backup_path = _backup_file(path)

    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return PruneResult(removed=removed, missing=missing, backup_path=backup_path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", default="config.user.yaml", help="YAML file to edit")
    parser.add_argument("--no-backup", action="store_true", help="Do not create a backup")
    parser.add_argument("keys", nargs="+", help="Top-level keys to remove")
    args = parser.parse_args()

    target = Path(args.file).resolve()
    if not target.exists():
        print(f"[ERROR] File not found: {target}")
        return 1

    result = prune_top_level_keys(target, list(args.keys), backup=not args.no_backup)
    if result.backup_path is not None:
        print(f"[OK] Backup created: {result.backup_path}")
    if result.removed:
        print(f"[OK] Removed keys from {target}: {', '.join(result.removed)}")
    if result.missing:
        print(f"[INFO] Keys not present (skipped): {', '.join(result.missing)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

