#!/usr/bin/env python3
"""
MintChat archive manager (SQLite index for major plans).

This tool keeps the repo tidy by moving plan-only artifacts into archives/plans/<plan_id>/,
then indexing them in a single SQLite DB for easy lookup.

DB file (tracked): archives/archive.sqlite3
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = PROJECT_ROOT / "archives" / "archive.sqlite3"
SCHEMA_VERSION = 1


SCHEMA_SQL = f"""
CREATE TABLE IF NOT EXISTS meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS plans (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'archived',
  start_date TEXT,
  end_date TEXT,
  summary TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS plan_artifacts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  plan_id TEXT NOT NULL,
  kind TEXT NOT NULL DEFAULT 'file',
  path TEXT NOT NULL,
  bytes INTEGER NOT NULL,
  sha256 TEXT NOT NULL,
  note TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(plan_id) REFERENCES plans(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_plan_artifacts_plan_id ON plan_artifacts(plan_id);
CREATE INDEX IF NOT EXISTS idx_plan_artifacts_path ON plan_artifacts(path);

CREATE TABLE IF NOT EXISTS plan_sources (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  plan_id TEXT NOT NULL,
  tool TEXT NOT NULL,
  url TEXT NOT NULL,
  note TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(plan_id) REFERENCES plans(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_plan_sources_plan_id ON plan_sources(plan_id);

CREATE TABLE IF NOT EXISTS plan_checks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  plan_id TEXT NOT NULL,
  name TEXT NOT NULL,
  status TEXT NOT NULL,
  details TEXT NOT NULL DEFAULT '',
  run_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(plan_id) REFERENCES plans(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_plan_checks_plan_id ON plan_checks(plan_id);
"""


def _connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    # Keep a single-file DB (avoid WAL sidecar files for a tracked artifact).
    conn.execute("PRAGMA journal_mode = DELETE;")
    conn.execute("PRAGMA busy_timeout = 5000;")
    return conn


def _init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_SQL)
    current = conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
    if current is None:
        conn.execute(
            "INSERT INTO meta(key, value) VALUES('schema_version', ?)",
            (str(SCHEMA_VERSION),),
        )
    elif int(current["value"]) != SCHEMA_VERSION:
        raise RuntimeError(
            f"Unsupported schema_version={current['value']} (expected {SCHEMA_VERSION})"
        )


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


@dataclass(frozen=True)
class Artifact:
    path: str
    bytes: int
    sha256: str


def _iter_artifacts(root: Path) -> list[Artifact]:
    root = root.resolve()
    artifacts: list[Artifact] = []
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if ".git" in p.parts:
            continue
        artifacts.append(
            Artifact(
                path=str(p.relative_to(PROJECT_ROOT)).replace("\\", "/"),
                bytes=p.stat().st_size,
                sha256=_sha256_file(p),
            )
        )
    return artifacts


def cmd_init(args: argparse.Namespace) -> int:
    with _connect(Path(args.db)) as conn:
        _init_db(conn)
    print(f"[OK] Initialized archive DB: {args.db}")
    return 0


def cmd_add_plan(args: argparse.Namespace) -> int:
    summary = ""
    if args.summary_file:
        summary = _read_text(Path(args.summary_file))
    elif args.summary:
        summary = args.summary

    with _connect(Path(args.db)) as conn:
        _init_db(conn)
        conn.execute(
            """
INSERT INTO plans(id, title, status, start_date, end_date, summary)
VALUES(?, ?, ?, ?, ?, ?)
ON CONFLICT(id) DO UPDATE SET
  title=excluded.title,
  status=excluded.status,
  start_date=excluded.start_date,
  end_date=excluded.end_date,
  summary=excluded.summary,
  updated_at=CURRENT_TIMESTAMP
            """.strip(),
            (
                args.id,
                args.title,
                args.status,
                args.start_date,
                args.end_date,
                summary,
            ),
        )
    print(f"[OK] Upserted plan: {args.id}")
    return 0


def cmd_add_source(args: argparse.Namespace) -> int:
    with _connect(Path(args.db)) as conn:
        _init_db(conn)
        conn.execute(
            "INSERT INTO plan_sources(plan_id, tool, url, note) VALUES(?, ?, ?, ?)",
            (args.plan_id, args.tool, args.url, args.note or ""),
        )
    print(f"[OK] Added source: {args.plan_id} {args.tool} {args.url}")
    return 0


def cmd_add_check(args: argparse.Namespace) -> int:
    with _connect(Path(args.db)) as conn:
        _init_db(conn)
        conn.execute(
            "INSERT INTO plan_checks(plan_id, name, status, details) VALUES(?, ?, ?, ?)",
            (args.plan_id, args.name, args.status, args.details or ""),
        )
    print(f"[OK] Added check: {args.plan_id} {args.name}={args.status}")
    return 0


def cmd_scan_artifacts(args: argparse.Namespace) -> int:
    root = Path(args.root)
    artifacts = _iter_artifacts(root)

    with _connect(Path(args.db)) as conn:
        _init_db(conn)
        conn.execute("DELETE FROM plan_artifacts WHERE plan_id = ?", (args.plan_id,))
        conn.executemany(
            """
INSERT INTO plan_artifacts(plan_id, kind, path, bytes, sha256, note)
VALUES(?, ?, ?, ?, ?, ?)
            """.strip(),
            [(args.plan_id, "file", a.path, a.bytes, a.sha256, "") for a in artifacts],
        )

    print(f"[OK] Indexed artifacts: plan_id={args.plan_id} files={len(artifacts)}")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    with _connect(Path(args.db)) as conn:
        _init_db(conn)
        rows = conn.execute(
            "SELECT id, title, status, start_date, end_date, updated_at FROM plans ORDER BY updated_at DESC"
        ).fetchall()
    for r in rows:
        print(
            f"{r['id']} | {r['status']} | {r['start_date'] or ''}~{r['end_date'] or ''} | {r['title']}"
        )
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    with _connect(Path(args.db)) as conn:
        _init_db(conn)
        plan = conn.execute("SELECT * FROM plans WHERE id = ?", (args.plan_id,)).fetchone()
        if plan is None:
            raise SystemExit(f"plan not found: {args.plan_id}")

        artifacts = conn.execute(
            "SELECT COUNT(*) AS n, COALESCE(SUM(bytes), 0) AS bytes FROM plan_artifacts WHERE plan_id=?",
            (args.plan_id,),
        ).fetchone()
        sources = conn.execute(
            "SELECT COUNT(*) AS n FROM plan_sources WHERE plan_id=?", (args.plan_id,)
        ).fetchone()
        checks = conn.execute(
            "SELECT name, status, run_at FROM plan_checks WHERE plan_id=? ORDER BY run_at DESC",
            (args.plan_id,),
        ).fetchall()

    out = {
        "id": plan["id"],
        "title": plan["title"],
        "status": plan["status"],
        "start_date": plan["start_date"],
        "end_date": plan["end_date"],
        "updated_at": plan["updated_at"],
        "artifact_files": int(artifacts["n"]),
        "artifact_bytes": int(artifacts["bytes"]),
        "sources": int(sources["n"]),
        "checks": [
            {"name": c["name"], "status": c["status"], "run_at": c["run_at"]} for c in checks
        ],
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="archive_manager", description="MintChat plan archive manager."
    )
    p.add_argument("--db", default=str(DEFAULT_DB_PATH), help="Path to archive sqlite3 DB.")
    sub = p.add_subparsers(dest="cmd", required=True)

    s_init = sub.add_parser("init", help="Initialize the archive DB.")
    s_init.set_defaults(func=cmd_init)

    s_plan = sub.add_parser("add-plan", help="Add or update a plan record.")
    s_plan.add_argument("--id", required=True)
    s_plan.add_argument("--title", required=True)
    s_plan.add_argument("--status", default="archived", choices=["archived", "active"])
    s_plan.add_argument("--start-date", default="")
    s_plan.add_argument("--end-date", default="")
    s_plan.add_argument("--summary", default="")
    s_plan.add_argument("--summary-file", default="")
    s_plan.set_defaults(func=cmd_add_plan)

    s_src = sub.add_parser("add-source", help="Add a research source (URL) for a plan.")
    s_src.add_argument("--plan-id", required=True)
    s_src.add_argument("--tool", required=True, help="e.g. Context7, tavily_local, Fetch")
    s_src.add_argument("--url", required=True)
    s_src.add_argument("--note", default="")
    s_src.set_defaults(func=cmd_add_source)

    s_chk = sub.add_parser("add-check", help="Record a verification check result for a plan.")
    s_chk.add_argument("--plan-id", required=True)
    s_chk.add_argument("--name", required=True)
    s_chk.add_argument("--status", required=True, choices=["pass", "fail", "skip"])
    s_chk.add_argument("--details", default="")
    s_chk.set_defaults(func=cmd_add_check)

    s_scan = sub.add_parser("scan-artifacts", help="Scan a plan folder and index all files.")
    s_scan.add_argument("--plan-id", required=True)
    s_scan.add_argument(
        "--root", required=True, help="Root folder to scan (e.g. archives/plans/<id>)"
    )
    s_scan.set_defaults(func=cmd_scan_artifacts)

    s_list = sub.add_parser("list", help="List plans.")
    s_list.set_defaults(func=cmd_list)

    s_show = sub.add_parser("show", help="Show plan summary as JSON.")
    s_show.add_argument("--plan-id", required=True)
    s_show.set_defaults(func=cmd_show)

    return p


def main() -> int:
    args = build_parser().parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
