#!/usr/bin/env python3
"""
Project cleanup helper (cross-platform).

Removes common Python caches and test/artifact outputs.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil


def _rm_tree(path: Path) -> bool:
    if not path.exists():
        return False
    shutil.rmtree(path, ignore_errors=True)
    return not path.exists()


def _rm_file(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        path.unlink(missing_ok=True)
        return True
    except Exception:
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Clean build/test artifacts for MintChat.")
    parser.add_argument(
        "--tts-cache",
        action="store_true",
        help="Also remove data/tts_cache (safe, but will lose cached audio).",
    )
    parser.add_argument(
        "--data-tests",
        action="store_true",
        help="Also remove data/test* and data/pytest* artifacts (safe, but will lose local test data).",
    )
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent

    removed_dirs = 0
    removed_files = 0

    # Directories
    dir_names = {
        "__pycache__",
        ".pytest_cache",
        ".pytest_tmp",
        ".mypy_cache",
        "htmlcov",
        "build",
        "dist",
    }
    for p in project_root.rglob("*"):
        if p.is_dir():
            if p.name in dir_names or p.name.endswith(".egg-info"):
                if ".venv" in p.parts:
                    continue
                if _rm_tree(p):
                    removed_dirs += 1

    # Files
    file_names = {".coverage", "coverage.xml"}
    for p in project_root.rglob("*"):
        if p.is_file():
            if ".venv" in p.parts:
                continue
            if p.name in file_names or p.suffix == ".pyc":
                if _rm_file(p):
                    removed_files += 1

    # Optional: runtime caches (safe subset)
    if args.tts_cache:
        tts_cache_dir = project_root / "data" / "tts_cache"
        if tts_cache_dir.exists():
            if _rm_tree(tts_cache_dir):
                removed_dirs += 1

    # Optional: local test artifacts under data/
    if args.data_tests:
        data_dir = project_root / "data"
        if data_dir.exists():
            for child in data_dir.iterdir():
                name = child.name
                if child.is_dir() and (name.startswith("test") or name.startswith("pytest")):
                    if _rm_tree(child):
                        removed_dirs += 1
                    continue
                if child.is_file() and name.startswith("test"):
                    if _rm_file(child):
                        removed_files += 1

    print(f"[OK] 已清理目录: {removed_dirs} 个，文件: {removed_files} 个")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
