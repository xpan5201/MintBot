"""
Phase 0/5（去外部编排框架计划）：Golden 对比脚本

用途：
- 对比两份 golden JSON（例如：不开 pipeline vs 开 pipeline）的流式输出结果，
  给出可量化的差异摘要，辅助 Gate 验收与回归定位。

说明：
- 默认以 prompt 文本作为 key 对齐记录；找不到则按 index 对齐。
- 对比维度：chunks 数量、chars 数量、首包延迟、最终文本相似度（difflib）。
- 该脚本不在 CI/pytest 中自动运行，需要你本机手动执行。

示例（Windows）：
  .\\.venv\\Scripts\\python.exe archives\\plans\\2026-01_de_langchain_phase0-7\\scripts\\de_langchain_compare_golden.py

  # 或指定文件：
  .\\.venv\\Scripts\\python.exe archives\\plans\\2026-01_de_langchain_phase0-7\\scripts\\de_langchain_compare_golden.py ^
    --baseline archives\\plans\\2026-01_de_langchain_phase0-7\\data\\golden\\backend_stream_golden.json ^
    --candidate archives\\plans\\2026-01_de_langchain_phase0-7\\data\\golden\\backend_stream_pipeline_golden.json

  # Gate#5：对比不开 pipeline vs 开 pipeline：
  .\\.venv\\Scripts\\python.exe archives\\plans\\2026-01_de_langchain_phase0-7\\scripts\\de_langchain_compare_golden.py ^
    --preset gate5-native-pipeline
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
PLAN_ROOT = SCRIPT_DIR.parent
GOLDEN_DIR = PLAN_ROOT / "data" / "golden"
CAPTURE_SCRIPT = SCRIPT_DIR / "de_langchain_capture_golden.py"


@dataclass(frozen=True)
class RecordDiff:
    prompt: str
    baseline_chunks: int
    candidate_chunks: int
    baseline_chars: int
    candidate_chars: int
    baseline_first_chunk_latency_s: float | None
    candidate_first_chunk_latency_s: float | None
    text_similarity: float
    ok: bool


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _to_text(record: dict[str, Any]) -> str:
    chunks = record.get("chunks") or []
    if not isinstance(chunks, list):
        return ""
    return "".join(str(c) for c in chunks)


def _match_records(
    baseline_records: list[dict[str, Any]], candidate_records: list[dict[str, Any]]
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    baseline_by_prompt: dict[str, dict[str, Any]] = {}
    for r in baseline_records:
        prompt = str(r.get("prompt") or "")
        if prompt and prompt not in baseline_by_prompt:
            baseline_by_prompt[prompt] = r

    pairs: list[tuple[dict[str, Any], dict[str, Any]]] = []
    used_baseline: set[int] = set()

    for idx, cand in enumerate(candidate_records):
        prompt = str(cand.get("prompt") or "")
        base = baseline_by_prompt.get(prompt)
        if base is None:
            if idx < len(baseline_records):
                base = baseline_records[idx]
            else:
                base = {}
        if base:
            used_baseline.add(id(base))
        pairs.append((base, cand))

    # If candidate has fewer entries, still report extra baselines as unmatched.
    if len(candidate_records) < len(baseline_records):
        for base in baseline_records[len(candidate_records) :]:
            if id(base) in used_baseline:
                continue
            pairs.append((base, {}))

    return pairs


def _similarity(a: str, b: str) -> float:
    if not a and not b:
        return 1.0
    return float(SequenceMatcher(a=a, b=b).ratio())


def _pick_default_path(candidates: list[Path]) -> Path:
    for p in candidates:
        if p.exists():
            return p
    return candidates[0]


def _candidates_for_preset(preset: str) -> tuple[list[Path], list[Path]]:
    if preset == "gate5-native-pipeline":
        # Prefer tool-loop recordings (Phase 4/5), fallback to plain streaming files.
        return (
            [
                # Historical naming (Phase 5/Gate#5 recorded in this archive).
                GOLDEN_DIR / "native_backend_tool_loop_golden.json",
                GOLDEN_DIR / "native_backend_stream_golden.json",
                GOLDEN_DIR / "native_stream_golden.json",
                GOLDEN_DIR / "backend_tool_loop_golden.json",
                GOLDEN_DIR / "backend_stream_golden.json",
                GOLDEN_DIR / "agent_stream_golden.json",
            ],
            [
                # Historical naming (Phase 5/Gate#5 recorded in this archive).
                GOLDEN_DIR / "native_backend_tool_loop_pipeline_golden.json",
                GOLDEN_DIR / "backend_tool_loop_pipeline_golden.json",
                GOLDEN_DIR / "backend_stream_pipeline_golden.json",
                GOLDEN_DIR / "agent_pipeline_stream_golden.json",
            ],
        )

    return _candidates_for_preset("gate5-native-pipeline")


def _sum_event_counts(records: list[dict[str, Any]]) -> dict[str, int]:
    totals: dict[str, int] = {}
    for r in records:
        counts = r.get("event_counts")
        if not isinstance(counts, dict):
            continue
        for k, v in counts.items():
            if not isinstance(v, int):
                continue
            key = str(k)
            totals[key] = totals.get(key, 0) + int(v)
    return totals


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="de_langchain_compare_golden",
        description="Compare golden baselines for streaming output.",
    )
    parser.add_argument(
        "--preset",
        choices=["gate5-native-pipeline"],
        default="gate5-native-pipeline",
        help=(
            "Select default baseline/candidate pair. Still override with " "--baseline/--candidate."
        ),
    )
    parser.add_argument(
        "--baseline",
        default="",
        help="Baseline JSON path. If omitted, uses --preset defaults.",
    )
    parser.add_argument(
        "--candidate",
        default="",
        help="Candidate JSON path. If omitted, uses --preset defaults.",
    )
    parser.add_argument(
        "--require-event-type",
        action="append",
        default=[],
        help=(
            "Require event type to exist (>=1) in BOTH baseline and candidate "
            "(uses record.event_counts). Repeatable."
        ),
    )
    parser.add_argument(
        "--require-stage",
        action="append",
        default=[],
        help=(
            "Require pipeline stage name to appear in candidate record.pipeline_stages. "
            "Repeatable."
        ),
    )
    parser.add_argument(
        "--min-text-similarity",
        type=float,
        default=0.95,
        help="Minimum final text similarity (default: 0.95).",
    )
    parser.add_argument(
        "--max-first-chunk-latency-delta-s",
        type=float,
        default=3.0,
        help="Max allowed first-chunk latency delta in seconds (default: 3.0).",
    )
    parser.add_argument(
        "--max-chars-delta",
        type=int,
        default=250,
        help="Max allowed absolute chars delta (default: 250).",
    )
    parser.add_argument(
        "--max-chunks-delta",
        type=int,
        default=50,
        help="Max allowed absolute chunks delta (default: 50).",
    )
    parser.add_argument(
        "--json",
        default="",
        help="Write diff report to JSON path (optional).",
    )
    args = parser.parse_args(argv)

    if str(args.preset) == "gate5-native-pipeline":
        # Gate#5 compares two *live* runs against a remote model and is expected to have higher
        # variance (provider latency jitter, minor wording differences). Keep the preset focused on
        # pipeline integrity + tool-loop events, while still guarding against drastic regressions.
        if float(args.min_text_similarity) == 0.95:
            args.min_text_similarity = 0.8
        if float(args.max_first_chunk_latency_delta_s) == 3.0:
            args.max_first_chunk_latency_delta_s = 60.0
        if int(args.max_chars_delta) == 250:
            args.max_chars_delta = 800
        if int(args.max_chunks_delta) == 50:
            args.max_chunks_delta = 100

    baseline_candidates, candidate_candidates = _candidates_for_preset(str(args.preset))
    baseline_path = (
        Path(args.baseline) if args.baseline else _pick_default_path(baseline_candidates)
    )
    candidate_path = (
        Path(args.candidate) if args.candidate else _pick_default_path(candidate_candidates)
    )
    print(f"[INPUT] preset={args.preset} baseline={baseline_path} candidate={candidate_path}")

    if not baseline_path.exists():
        print(f"[ERROR] baseline file not found: {baseline_path}")
        if str(args.preset) == "gate5-native-pipeline":
            print(
                "[HINT] Capture baseline first:\n"
                f"  .\\.venv\\Scripts\\python.exe {CAPTURE_SCRIPT} "
                "--backend native --runner backend --tools"
            )
        return 2
    if not candidate_path.exists():
        print(f"[ERROR] candidate file not found: {candidate_path}")
        if str(args.preset) == "gate5-native-pipeline":
            print(
                "[HINT] Capture candidate first:\n"
                f"  .\\.venv\\Scripts\\python.exe {CAPTURE_SCRIPT} "
                "--backend native --runner backend --tools --pipeline"
            )
        return 2

    baseline = _load(baseline_path)
    candidate = _load(candidate_path)

    baseline_records = baseline.get("records") or []
    candidate_records = candidate.get("records") or []
    if not isinstance(baseline_records, list) or not isinstance(candidate_records, list):
        print("[ERROR] invalid input JSON: records must be list")
        return 2

    require_event_types = [
        str(t).strip() for t in (args.require_event_type or []) if str(t).strip()
    ]
    require_stages = [str(s).strip() for s in (args.require_stage or []) if str(s).strip()]

    if str(args.preset) == "gate5-native-pipeline":
        if not require_stages:
            require_stages = [
                "ContextToolUsesTrimStage",
                "PermissionScopedToolsStage",
                "ToolCallLimitStage",
                "ToolTraceStage",
            ]
        if not require_event_types:
            require_event_types = ["tool.result"]

    baseline_event_totals = _sum_event_counts(baseline_records)
    candidate_event_totals = _sum_event_counts(candidate_records)

    candidate_stage_set: set[str] = set()
    for r in candidate_records:
        stages = r.get("pipeline_stages")
        if not isinstance(stages, list):
            continue
        candidate_stage_set.update(str(s) for s in stages if str(s))

    prechecks_ok = True
    if str(args.preset) == "gate5-native-pipeline":
        cand_pipeline = (candidate.get("meta") or {}).get("native_pipeline_enabled")
        if cand_pipeline is not True:
            print(
                "[ERROR] preset gate5-native-pipeline requires "
                "candidate meta.native_pipeline_enabled=true "
                f"(got {cand_pipeline!r})."
            )
            prechecks_ok = False

    if require_event_types:
        missing_base = [t for t in require_event_types if int(baseline_event_totals.get(t, 0)) <= 0]
        missing_cand = [
            t for t in require_event_types if int(candidate_event_totals.get(t, 0)) <= 0
        ]
        if missing_base:
            print(f"[ERROR] baseline missing required event types: {missing_base}")
            prechecks_ok = False
        if missing_cand:
            print(f"[ERROR] candidate missing required event types: {missing_cand}")
            prechecks_ok = False

    if require_stages:
        missing_stages = [s for s in require_stages if s not in candidate_stage_set]
        if missing_stages:
            print(
                "[ERROR] candidate missing required pipeline stages: "
                f"{missing_stages} (found={sorted(candidate_stage_set)})"
            )
            prechecks_ok = False

    diffs: list[RecordDiff] = []
    all_ok = bool(prechecks_ok)

    for base, cand in _match_records(baseline_records, candidate_records):
        prompt = str(
            (cand.get("prompt") if cand else None) or (base.get("prompt") if base else "") or ""
        )
        base_chunks = int(base.get("chunks_count") or len(base.get("chunks") or [])) if base else 0
        cand_chunks = int(cand.get("chunks_count") or len(cand.get("chunks") or [])) if cand else 0

        base_text = _to_text(base) if base else ""
        cand_text = _to_text(cand) if cand else ""

        base_chars = int(base.get("chars_count") or len(base_text)) if base else 0
        cand_chars = int(cand.get("chars_count") or len(cand_text)) if cand else 0

        base_first = base.get("first_chunk_latency_s") if base else None
        cand_first = cand.get("first_chunk_latency_s") if cand else None
        base_first_f = float(base_first) if isinstance(base_first, (int, float)) else None
        cand_first_f = float(cand_first) if isinstance(cand_first, (int, float)) else None

        sim = _similarity(base_text, cand_text)

        ok = True
        if sim < float(args.min_text_similarity):
            ok = False
        if abs(base_chars - cand_chars) > int(args.max_chars_delta):
            ok = False
        if abs(base_chunks - cand_chunks) > int(args.max_chunks_delta):
            ok = False
        if base_first_f is not None and cand_first_f is not None:
            if abs(base_first_f - cand_first_f) > float(args.max_first_chunk_latency_delta_s):
                ok = False

        diffs.append(
            RecordDiff(
                prompt=prompt,
                baseline_chunks=base_chunks,
                candidate_chunks=cand_chunks,
                baseline_chars=base_chars,
                candidate_chars=cand_chars,
                baseline_first_chunk_latency_s=base_first_f,
                candidate_first_chunk_latency_s=cand_first_f,
                text_similarity=round(sim, 6),
                ok=bool(ok),
            )
        )
        all_ok = all_ok and ok

    print(
        f"[SUMMARY] records={len(diffs)} ok={sum(1 for d in diffs if d.ok)}/{len(diffs)} "
        f"min_similarity={min((d.text_similarity for d in diffs), default=1.0):.6f}"
    )
    for d in diffs:
        if d.ok:
            continue
        print(
            f"[DIFF] prompt={d.prompt!r} sim={d.text_similarity:.6f} "
            f"chunks={d.baseline_chunks}->{d.candidate_chunks} "
            f"chars={d.baseline_chars}->{d.candidate_chars} "
            f"first={d.baseline_first_chunk_latency_s}->{d.candidate_first_chunk_latency_s}"
        )

    if args.json:
        out_path = Path(args.json)
        if not out_path.is_absolute():
            out_path = baseline_path.parent / out_path
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(
                {
                    "preset": str(args.preset),
                    "baseline": str(baseline_path),
                    "candidate": str(candidate_path),
                    "requirements": {
                        "event_types": list(require_event_types),
                        "pipeline_stages": list(require_stages),
                    },
                    "event_totals": {
                        "baseline": dict(baseline_event_totals),
                        "candidate": dict(candidate_event_totals),
                    },
                    "candidate_pipeline_stages_found": sorted(candidate_stage_set),
                    "thresholds": {
                        "min_text_similarity": float(args.min_text_similarity),
                        "max_first_chunk_latency_delta_s": float(
                            args.max_first_chunk_latency_delta_s
                        ),
                        "max_chars_delta": int(args.max_chars_delta),
                        "max_chunks_delta": int(args.max_chunks_delta),
                    },
                    "diffs": [asdict(d) for d in diffs],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"[OK] Wrote diff report: {out_path}")

    return 0 if all_ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
