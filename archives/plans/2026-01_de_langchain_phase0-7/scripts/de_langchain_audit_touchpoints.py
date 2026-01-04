"""
Phase 0（去外部编排框架计划）：触点审计脚本

用途：
- 扫描仓库中对“历史外部依赖触点”的引用位置，输出报告，作为：
  - Phase 0 盘点依据
  - Phase 7 “零引用验收”工具

示例（Windows）：
  .\\.venv\\Scripts\\python.exe archives\\plans\\2026-01_de_langchain_phase0-7\\scripts\\de_langchain_audit_touchpoints.py \\
    --json data\\de_langchain\\touchpoints.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


PLAN_ROOT = Path(__file__).resolve().parent.parent


def _find_repo_root(start: Path) -> Path:
    for candidate in [start, *start.parents]:
        if (candidate / "pyproject.toml").is_file() and (candidate / "src").is_dir():
            return candidate
    return start


REPO_ROOT = _find_repo_root(PLAN_ROOT)


EXCLUDE_DIRS = {
    ".git",
    ".venv",
    ".mypy_cache",
    ".pytest_cache",
    ".pytest_tmp",
    "__pycache__",
    "data",
    "logs",
    "third_party",
}


def _w(*parts: str) -> str:
    return "".join(parts)


_LEGACY_A = _w("lang", "chain")
_LEGACY_B = _w("lang", "graph")
_LEGACY_C = _w("lang", "smith")

DEFAULT_PATTERNS = [
    rf"\b{_LEGACY_A}\b",
    rf"\b{_LEGACY_A}[_-]\w+",
    rf"\b{_LEGACY_B}\b",
    rf"\b{_LEGACY_C}\b",
]


@dataclass(frozen=True)
class Match:
    path: str
    line: int
    text: str
    pattern: str


def _iter_files(root: Path, globs: Iterable[str]) -> Iterable[Path]:
    for pattern in globs:
        yield from root.rglob(pattern)


def _should_skip(path: Path) -> bool:
    for part in path.parts:
        if part in EXCLUDE_DIRS:
            return True
    return False


def _scan_file(
    path: Path,
    regexes: list[tuple[str, re.Pattern[str]]],
    max_matches: int,
    *,
    relative_to_root: Path,
) -> list[Match]:
    if _should_skip(path):
        return []

    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return []

    matches: list[Match] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        for raw, rx in regexes:
            if rx.search(line):
                matches.append(
                    Match(
                        path=str(path.relative_to(relative_to_root)).replace("\\", "/"),
                        line=line_no,
                        text=line.strip(),
                        pattern=raw,
                    )
                )
                if max_matches > 0 and len(matches) >= max_matches:
                    return matches
    return matches


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    parser = argparse.ArgumentParser(
        prog="de_langchain_audit_touchpoints",
        description="Audit legacy dependency touchpoints in this repo.",
    )
    parser.add_argument(
        "--root",
        default=str(REPO_ROOT),
        help="Project root (default: repo root)",
    )
    parser.add_argument(
        "--json",
        default="",
        help="Write JSON report to this path (optional).",
    )
    parser.add_argument(
        "--fail-if-found",
        action="store_true",
        help="Exit with code 2 if any match is found.",
    )
    parser.add_argument(
        "--max-matches-per-file",
        type=int,
        default=50,
        help="Max matches per file (0 = unlimited). Default: 50",
    )
    parser.add_argument(
        "--include",
        action="append",
        default=["src/**/*.py", "tests/**/*.py", "examples/**/*.py", "scripts/**/*.py"],
        help="Glob(s) to include (repeatable). Default: src/tests/examples/scripts Python files.",
    )
    parser.add_argument(
        "--pattern",
        action="append",
        default=[],
        help="Regex pattern(s) to search (repeatable). Default: legacy dependency touchpoints.",
    )

    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    patterns = list(args.pattern) if args.pattern else list(DEFAULT_PATTERNS)
    regexes: list[tuple[str, re.Pattern[str]]] = [(p, re.compile(p)) for p in patterns]

    matches: list[Match] = []
    for file_path in _iter_files(root, args.include):
        matches.extend(
            _scan_file(
                file_path,
                regexes,
                max_matches=args.max_matches_per_file,
                relative_to_root=root,
            )
        )

    report = {
        "root": str(root),
        "patterns": patterns,
        "count": len(matches),
        "matches": [asdict(m) for m in matches],
    }

    if args.json:
        out_path = Path(args.json)
        if not out_path.is_absolute():
            out_path = PLAN_ROOT / out_path
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[OK] Wrote report: {out_path}")

    print(f"[SUMMARY] matches={len(matches)} patterns={len(patterns)}")
    if matches:
        # Print a short preview for quick inspection
        for m in matches[:20]:
            print(f"{m.path}:{m.line}: {m.text}")
        if len(matches) > 20:
            print(f"... ({len(matches) - 20} more)")

    if args.fail_if_found and matches:
        return 2
    return 0


if __name__ == "__main__":
    os.chdir(REPO_ROOT)
    raise SystemExit(main(sys.argv[1:]))
