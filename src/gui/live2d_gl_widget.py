"""Live2D OpenGL widget (QOpenGLWidget) backed by `live2d-py`.

Why this approach:
- Pure Qt + OpenGL (no WebEngine / JS runtime).
- `live2d-py` wraps Cubism Native SDK, supports `.model3.json/.moc3` models.

Notes:
- This widget is best-effort and degrades gracefully when `live2d-py` is missing.
- All Live2D / GL calls must happen on the GUI thread with a current GL context.
"""

from __future__ import annotations

import importlib
from importlib.machinery import PathFinder
import importlib.util
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import math
import time
import random
from typing import Any

from PyQt6.QtCore import QElapsedTimer, QEvent, QPointF, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QCursor, QSurfaceFormat
from PyQt6.QtOpenGLWidgets import QOpenGLWidget

from src.utils.logger import get_logger

logger = get_logger(__name__)


def _repo_root() -> Path:
    try:
        return Path(__file__).resolve().parents[2]
    except Exception:
        return Path.cwd()


def _sys_path_excluding_repo_root(repo_root: Path) -> list[str]:
    root = str(repo_root)
    result: list[str] = []
    for entry in sys.path:
        # "" and "." both mean current working directory (repo root when running MintChat.py)
        if entry in ("", "."):
            continue
        try:
            if str(Path(entry).resolve()) == root:
                continue
        except Exception:
            pass
        result.append(entry)
    return result


def _try_import_live2d_v3() -> tuple[Any | None, str]:
    """Import `live2d.v3` even if the repo's `live2d/` asset folder shadows the package name."""

    try:
        return importlib.import_module("live2d.v3"), ""
    except Exception as exc:
        first_error = repr(exc)

    repo_root = _repo_root()
    search_path = _sys_path_excluding_repo_root(repo_root)

    try:
        pkg_spec = PathFinder.find_spec("live2d", search_path)
        if pkg_spec is None or pkg_spec.loader is None:
            raise ModuleNotFoundError("live2d-py not installed (missing live2d package)")

        # Force-load the pip package into sys.modules, replacing any namespace package created
        # from the repo's `live2d/` assets directory.
        pkg_mod = importlib.util.module_from_spec(pkg_spec)
        sys.modules["live2d"] = pkg_mod
        pkg_spec.loader.exec_module(pkg_mod)

        v3_spec = None
        try:
            v3_spec = PathFinder.find_spec("live2d.v3", getattr(pkg_mod, "__path__", None))
        except Exception:
            v3_spec = None
        if v3_spec is None or v3_spec.loader is None:
            raise ModuleNotFoundError("live2d-py not installed (missing live2d.v3)")

        v3_mod = importlib.util.module_from_spec(v3_spec)
        sys.modules["live2d.v3"] = v3_mod
        v3_spec.loader.exec_module(v3_mod)
        return v3_mod, ""
    except Exception as exc:
        # Keep the most actionable message.
        # Prefer the second attempt which can surface shadowing issues.
        return None, repr(exc) or first_error


def _is_ascii(s: str) -> bool:
    try:
        s.encode("ascii")
        return True
    except Exception:
        return False


def _relpath_posix(target: Path, start: Path) -> str:
    return Path(os.path.relpath(str(target), str(start))).as_posix()


def _stable_ascii_token(value: str, *, prefix: str) -> str:
    """Return an ASCII-only token for potentially non-ASCII strings.

    CubismJson can reject Unicode.
    """
    s = str(value or "")
    if _is_ascii(s):
        return s
    digest = hashlib.sha1(s.encode("utf-8", "ignore")).hexdigest()[:10]
    return f"{prefix}_{digest}"


def _sanitize_json_ascii(data: Any) -> Any:
    """Recursively replace non-ASCII strings/keys with stable ASCII tokens."""
    if isinstance(data, str):
        return data if _is_ascii(data) else _stable_ascii_token(data, prefix="u")
    if isinstance(data, list):
        return [_sanitize_json_ascii(item) for item in data]
    if isinstance(data, dict):
        sanitized: dict[str, Any] = {}
        for k, v in data.items():
            key = str(k)
            if not _is_ascii(key):
                key = _stable_ascii_token(key, prefix="k")
            sanitized[key] = _sanitize_json_ascii(v)
        return sanitized
    return data


def _cache_root_for_model(src_model_json: Path, *, cache_base: Path | None = None) -> Path:
    # Bump this when the sanitizer output layout/schema changes (forces a rebuild).
    LIVE2D_CACHE_SCHEMA_VERSION = 2
    base = Path(cache_base) if cache_base is not None else (_repo_root() / "data" / "live2d_cache")
    try:
        key_src = str(Path(src_model_json).resolve())
    except Exception:
        key_src = str(src_model_json)
    digest = hashlib.sha1(str(key_src).encode("utf-8", "ignore")).hexdigest()[:12]
    return base / f"model_{digest}_ascii_v{LIVE2D_CACHE_SCHEMA_VERSION}"


def _sanitize_model3_json_for_cubism(
    src_model_json: Path, *, cache_base: Path | None = None
) -> Path:
    """
    Return a model3.json path that is safe for Cubism's limited JSON parser.

    Empirically, CubismJson (live2d-py / Cubism Native SDK) may reject Unicode
    (UTF-8 bytes or \\u escapes) and can even crash on invalid documents.
    We generate an ASCII-only wrapper under `data/live2d_cache/`.
    We copy only required assets with non-ASCII names.
    If the source path contains Unicode, we also copy core assets.
    """
    src_model_json = Path(src_model_json)
    if not src_model_json.exists():
        return src_model_json

    model_dir = src_model_json.parent
    exp_files = sorted(model_dir.glob("*.exp3.json"))
    motion_files = sorted(model_dir.glob("*.motion3.json"))

    try:
        base = json.loads(src_model_json.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Failed to parse base model json for sanitizing: %s", exc)
        return src_model_json
    if not isinstance(base, dict):
        return src_model_json

    src_refs = base.get("FileReferences") or {}
    if not isinstance(src_refs, dict):
        src_refs = {}

    try:
        src_path_str = str(src_model_json.resolve())
    except Exception:
        src_path_str = str(src_model_json)
    must_copy_core_assets = not _is_ascii(src_path_str)

    needs_ascii = must_copy_core_assets
    for p in exp_files + motion_files:
        if not _is_ascii(p.name):
            needs_ascii = True
            break
    if not needs_ascii:
        try:
            for k, v in src_refs.items():
                if isinstance(k, str) and not _is_ascii(k):
                    needs_ascii = True
                    break
                if isinstance(v, str) and not _is_ascii(v):
                    needs_ascii = True
                    break
                if isinstance(v, list) and any(
                    isinstance(it, str) and not _is_ascii(it) for it in v
                ):
                    needs_ascii = True
                    break
        except Exception:
            pass

    if not needs_ascii:
        return src_model_json

    cache_root = _cache_root_for_model(src_model_json, cache_base=cache_base)
    expressions_dir = cache_root / "expressions"
    motions_dir = cache_root / "motions"
    assets_dir = cache_root / "assets"
    sanitized_path = cache_root / "model.model3.json"

    def resolve_ref(ref: str) -> Path:
        p = Path(ref)
        if p.is_absolute():
            return p
        return model_dir / p

    def copy_file(src: Path, dest: Path) -> None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy2(src, dest)
        except Exception:
            shutil.copyfile(src, dest)

    def from_model_ref(ref: str) -> str:
        return _relpath_posix(resolve_ref(ref), cache_root)

    copy_jobs: list[tuple[Path, Path]] = []
    expected: list[Path] = []
    max_src_mtime = 0.0

    def note_src(src: Path) -> None:
        nonlocal max_src_mtime
        try:
            max_src_mtime = max(max_src_mtime, float(src.stat().st_mtime))
        except Exception:
            pass

    note_src(src_model_json)

    def emit_core_ref(ref: str) -> str:
        ref_s = str(ref or "")
        if not ref_s:
            return ref_s
        src = resolve_ref(ref_s)
        if not src.exists():
            return ref_s
        note_src(src)
        if not must_copy_core_assets and _is_ascii(ref_s):
            rel = from_model_ref(ref_s)
            if _is_ascii(rel):
                return rel
        if not must_copy_core_assets and _is_ascii(ref_s) and not _is_ascii(Path(ref_s).name):
            pass
        dest_rel: Path
        if _is_ascii(ref_s) and not Path(ref_s).is_absolute():
            dest_rel = Path(ref_s)
        else:
            suffix = "".join(src.suffixes) or src.suffix
            digest = hashlib.sha1(str(src).encode("utf-8", "ignore")).hexdigest()[:10]
            dest_rel = Path("assets") / f"asset_{digest}{suffix}"
        dest = cache_root / dest_rel
        copy_jobs.append((src, dest))
        expected.append(dest)
        return dest_rel.as_posix()

    def emit_expression_entry(src_path: Path, *, idx: int, name: str | None) -> dict[str, str]:
        expressions_dir.mkdir(parents=True, exist_ok=True)
        note_src(src_path)
        expr_name = str(name or "").strip()
        if not expr_name or not _is_ascii(expr_name):
            expr_name = f"expr_{idx:02d}"
        dest_rel = Path("expressions") / f"expr_{idx:02d}.exp3.json"
        dest = cache_root / dest_rel
        copy_jobs.append((src_path, dest))
        expected.append(dest)
        return {"Name": expr_name, "File": dest_rel.as_posix()}

    def emit_motion_entry(
        group: str, src_path: Path, *, idx: int, original: dict[str, Any] | None
    ) -> dict[str, Any]:
        motions_dir.mkdir(parents=True, exist_ok=True)
        note_src(src_path)
        safe_group = _stable_ascii_token(group, prefix="motion")
        safe_group = re.sub(r"[^A-Za-z0-9_]+", "_", safe_group).strip("_") or "motion"
        dest_rel = Path("motions") / f"{safe_group.lower()}_{idx:02d}.motion3.json"
        dest = cache_root / dest_rel
        copy_jobs.append((src_path, dest))
        expected.append(dest)
        item: dict[str, Any] = {}
        if isinstance(original, dict):
            item.update(original)
        item["File"] = dest_rel.as_posix()
        if "Sound" in item and isinstance(item["Sound"], str):
            item["Sound"] = emit_core_ref(item["Sound"])
        return item

    new_refs: dict[str, Any] = {}
    for key, value in src_refs.items():
        if key in {"Expressions", "Motions"}:
            continue
        if isinstance(value, str):
            new_refs[str(key)] = emit_core_ref(value)
        elif isinstance(value, list):
            converted: list[Any] = []
            for item in value:
                if isinstance(item, str):
                    converted.append(emit_core_ref(item))
                else:
                    converted.append(item)
            new_refs[str(key)] = converted
        else:
            new_refs[str(key)] = value

    base_expr = src_refs.get("Expressions")
    expressions: list[dict[str, str]] = []
    if isinstance(base_expr, list) and base_expr:
        seen_expr_files: set[str] = set()
        base_expr_count = len(base_expr)
        for idx, entry in enumerate(base_expr, start=1):
            if not isinstance(entry, dict):
                continue
            file_ref = entry.get("File")
            if not isinstance(file_ref, str) or not file_ref:
                continue
            src = resolve_ref(file_ref)
            if not src.exists():
                continue
            try:
                seen_expr_files.add(src.name)
            except Exception:
                pass
            name = entry.get("Name") if isinstance(entry.get("Name"), str) else None
            if (
                must_copy_core_assets
                or (not _is_ascii(file_ref))
                or (name is not None and not _is_ascii(name))
            ):
                expressions.append(emit_expression_entry(src, idx=idx, name=name))
            else:
                expr_name = name or f"expr_{idx:02d}"
                expr_name = expr_name if _is_ascii(expr_name) else f"expr_{idx:02d}"
                expressions.append({"Name": expr_name, "File": from_model_ref(file_ref)})
        # Some community models ship extra `.exp3.json` files without listing them in model3.json.
        # Include them so the UI can still trigger expressions by file name.
        extra_idx = base_expr_count + 1
        for src in exp_files:
            try:
                if src.name in seen_expr_files:
                    continue
            except Exception:
                continue
            try:
                expressions.append(emit_expression_entry(src, idx=extra_idx, name=None))
                extra_idx += 1
            except Exception:
                continue
    elif exp_files:
        for idx, src in enumerate(exp_files, start=1):
            if not _is_ascii(src.name) or must_copy_core_assets:
                expressions.append(emit_expression_entry(src, idx=idx, name=None))
    if expressions:
        new_refs["Expressions"] = expressions

    base_motions = src_refs.get("Motions")
    motions: dict[str, list[dict[str, Any]]] = {}
    if isinstance(base_motions, dict) and base_motions:
        for group, items in base_motions.items():
            if not isinstance(items, list):
                continue
            group_name = str(group)
            safe_group = (
                group_name
                if _is_ascii(group_name)
                else _stable_ascii_token(group_name, prefix="motion")
            )
            safe_group = re.sub(r"[^A-Za-z0-9_]+", "_", safe_group).strip("_") or "motion"
            out_items: list[dict[str, Any]] = []
            for idx, item in enumerate(items, start=1):
                if not isinstance(item, dict):
                    continue
                file_ref = item.get("File")
                if not isinstance(file_ref, str) or not file_ref:
                    continue
                src = resolve_ref(file_ref)
                if not src.exists():
                    continue
                if must_copy_core_assets or (not _is_ascii(file_ref)):
                    out_items.append(emit_motion_entry(safe_group, src, idx=idx, original=item))
                else:
                    copied = dict(item)
                    copied["File"] = from_model_ref(file_ref)
                    if "Sound" in copied and isinstance(copied["Sound"], str):
                        copied["Sound"] = emit_core_ref(copied["Sound"])
                    out_items.append(copied)
            if out_items:
                motions[safe_group] = out_items
    elif motion_files:
        idle: list[dict[str, Any]] = []
        for idx, src in enumerate(motion_files, start=1):
            if not _is_ascii(src.name) or must_copy_core_assets:
                idle.append(emit_motion_entry("Idle", src, idx=idx, original=None))
        if idle:
            motions["Idle"] = idle
    if motions:
        new_refs["Motions"] = motions

    sanitized: dict[str, Any] = dict(base)
    sanitized["Version"] = int(base.get("Version") or 3)
    sanitized["FileReferences"] = new_refs
    sanitized = _sanitize_json_ascii(sanitized)

    try:
        if sanitized_path.exists():
            cache_mtime = float(sanitized_path.stat().st_mtime)
            if cache_mtime >= float(max_src_mtime) and all(p.exists() for p in expected):
                return sanitized_path
    except Exception:
        pass

    try:
        cache_root.mkdir(parents=True, exist_ok=True)
        assets_dir.mkdir(parents=True, exist_ok=True)
        for src, dest in copy_jobs:
            try:
                if dest.exists() and float(dest.stat().st_mtime) >= float(src.stat().st_mtime):
                    continue
            except Exception:
                pass
            try:
                copy_file(src, dest)
            except Exception as exc:
                logger.warning("Failed to copy Live2D asset %s: %s", src, exc)
        sanitized_path.write_text(
            json.dumps(sanitized, ensure_ascii=True, indent=2), encoding="utf-8"
        )
        return sanitized_path
    except Exception as exc:
        logger.warning("Live2D model sanitizer failed: %s", exc, exc_info=True)
        return src_model_json


_CSS_RGB_RE = re.compile(
    r"^\s*rgba?\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*(?:,\s*([0-9.]+)\s*)?\)\s*$",
    re.IGNORECASE,
)


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def _css_color_to_rgba(
    css: str, *, force_alpha: float | None = None
) -> tuple[float, float, float, float]:
    s = str(css or "").strip()
    if not s:
        return (0.0, 0.0, 0.0, 1.0)

    if s.startswith("#"):
        hex_str = s[1:]
        if len(hex_str) == 3:
            r = int(hex_str[0] * 2, 16)
            g = int(hex_str[1] * 2, 16)
            b = int(hex_str[2] * 2, 16)
            a = 1.0
        elif len(hex_str) == 6:
            r = int(hex_str[0:2], 16)
            g = int(hex_str[2:4], 16)
            b = int(hex_str[4:6], 16)
            a = 1.0
        else:
            return (0.0, 0.0, 0.0, 1.0)
        if force_alpha is not None:
            a = float(force_alpha)
        return (r / 255.0, g / 255.0, b / 255.0, _clamp01(a))

    m = _CSS_RGB_RE.match(s)
    if m:
        r = min(255, max(0, int(m.group(1))))
        g = min(255, max(0, int(m.group(2))))
        b = min(255, max(0, int(m.group(3))))
        a = 1.0
        if m.group(4) is not None:
            try:
                a = float(m.group(4))
            except Exception:
                a = 1.0
        if force_alpha is not None:
            a = float(force_alpha)
        return (r / 255.0, g / 255.0, b / 255.0, _clamp01(a))

    return (0.0, 0.0, 0.0, 1.0)


def _choose_expression_file_for_event(event: str, available: list[str]) -> str | None:
    """Pick a `.exp3.json` file name from `available` given a semantic event token."""
    event = str(event or "").strip()
    if not event or not available:
        return None

    available_set = set(available)

    # Direct file name.
    if event.endswith(".exp3.json") and event in available_set:
        return event

    # Common semantic mapping (best-effort; falls back to keyword search).
    key = event.lower().strip()
    direct: dict[str, list[str]] = {
        "angry": ["生气.exp3.json"],
        "mad": ["生气.exp3.json"],
        "shy": ["脸红.exp3.json"],
        "blush": ["脸红.exp3.json"],
        "dizzy": ["晕.exp3.json"],
        "love": ["心心眼.exp3.json"],
        "like": ["心心眼.exp3.json"],
        "sad": ["哭哭.exp3.json"],
        "cry": ["哭哭.exp3.json"],
        "surprise": ["星星眼.exp3.json"],
        "surprised": ["星星眼.exp3.json"],
        # Extra semantic keys for models that ship many expressions (e.g. Blue_cat).
        "tail": ["猫尾.exp3.json"],
        "cat_tail": ["猫尾.exp3.json"],
        "ears": ["耳朵.exp3.json"],
        "ear": ["耳朵.exp3.json"],
        "headphones": ["耳机.exp3.json"],
        "headset": ["耳机.exp3.json"],
        "fog": ["雾气.exp3.json"],
        "mist": ["雾气.exp3.json"],
        "tongue": ["舌头.exp3.json"],
        "fish": ["鱼干.exp3.json"],
        "snack": ["鱼干.exp3.json"],
        "small": ["变小.exp3.json"],
        "smol": ["变小.exp3.json"],
        "black": ["脸黑.exp3.json"],
        "flower": ["花花.exp3.json"],
        "rice": ["打米.exp3.json"],
        "armor": ["钢板.exp3.json"],
        "plate": ["钢板.exp3.json"],
        "only_head": ["只有头.exp3.json"],
        "head_only": ["只有头.exp3.json"],
        "small_chest": ["小胸.exp3.json"],
        "chest": ["小胸.exp3.json"],
    }
    for cand in direct.get(key, []):
        if cand in available_set:
            return cand

    # Keyword match against file stems (Chinese/English).
    keywords: dict[str, tuple[str, ...]] = {
        "angry": ("生气", "怒", "气死", "恼", "火"),
        "shy": ("脸红", "害羞", "羞", "不好意思"),
        "dizzy": ("晕", "头晕", "眩晕"),
        "love": ("心心眼", "喜欢", "爱", "亲", "抱"),
        "sad": ("哭哭", "哭", "难过", "伤心", "委屈"),
        "surprise": ("星星眼", "惊", "哇", "诶"),
        "tail": ("猫尾", "尾巴", "tail"),
        "ears": ("耳朵", "ears", "ear"),
        "headphones": ("耳机", "耳麦", "headset", "headphones"),
        "fog": ("雾气", "雾", "fog", "mist"),
        "tongue": ("舌头", "吐舌", "blep", "tongue"),
        "fish": ("鱼干", "小鱼", "fish"),
        "small": ("变小", "小小", "small", "smol"),
        "black": ("脸黑", "黑脸", "black"),
        "flower": ("花花", "花", "flower"),
        "rice": ("打米", "米", "rice"),
        "armor": ("钢板", "装甲", "armor", "plate"),
        "only_head": ("只有头", "只剩头", "headonly", "onlyhead"),
        "small_chest": ("小胸", "胸", "chest"),
    }

    # If the event itself is a meaningful token (e.g. "生气"), treat it as a keyword.
    search_terms: list[str] = [event]
    if key in keywords:
        search_terms.extend(list(keywords[key]))
    else:
        # Non-English tokens (e.g. "头晕") may not match the dict keys; try detecting by inclusion.
        try:
            for _k, terms in keywords.items():
                if any(t and t in event for t in terms):
                    search_terms.extend(list(terms))
                    break
        except Exception:
            pass

    def norm(s: str) -> str:
        s = str(s or "").strip().lower()
        return re.sub(r"\s+", "", s)

    needle_terms = [norm(t) for t in search_terms if t]
    if not needle_terms:
        return None

    for fname in available:
        stem = fname[:-9] if fname.endswith(".exp3.json") else fname
        hay = norm(stem)
        if any(term and term in hay for term in needle_terms):
            return fname
    return None


def _gesture_kind_for_event(event: str) -> str | None:
    """Map a semantic event token to a Live2D gesture kind (best-effort).

    Gestures are implemented by parameter-driven VTuber motion.
    No dedicated motion assets required.
    """

    raw = str(event or "").strip()
    if not raw:
        return None
    key = raw.lower().strip()

    # Direct gesture keys (English).
    direct: dict[str, str] = {
        "nod": "nod",
        "yes": "nod",
        "affirm": "nod",
        "affirmative": "nod",
        "agree": "nod",
        "shake": "shake",
        "no": "shake",
        "deny": "shake",
        "negative": "shake",
        "disagree": "shake",
        "tilt": "tilt",
        "lean": "lean",
        "look_left": "look_left",
        "look_right": "look_right",
        "look_up": "look_up",
        "look_down": "look_down",
    }
    if key in direct:
        return direct[key]

    # Direct gesture keys (Chinese).
    direct_cn: dict[str, str] = {
        "点头": "nod",
        "点点头": "nod",
        "肯定": "nod",
        "摇头": "shake",
        "摇摇头": "shake",
        "否定": "shake",
    }
    if raw in direct_cn:
        return direct_cn[raw]

    # Reasonable defaults for emotion-like events.
    emo: dict[str, str] = {
        "angry": "shake",
        "mad": "shake",
        "love": "tilt",
        "like": "tilt",
        "shy": "look_down",
        "dizzy": "tilt",
        "sad": "look_down",
        "surprise": "look_up",
        "surprised": "look_up",
    }
    if key in emo:
        return emo[key]

    # Also accept explicit Chinese emotion keywords in the event token.
    if any(tok in raw for tok in ("生气", "气死", "气炸", "愤怒")):
        return "shake"
    if any(tok in raw for tok in ("喜欢", "爱", "心心眼", "亲亲", "抱抱")):
        return "tilt"
    if any(tok in raw for tok in ("害羞", "脸红")):
        return "look_down"
    if any(tok in raw for tok in ("头晕", "晕")):
        return "tilt"
    if any(tok in raw for tok in ("难过", "哭", "哭哭")):
        return "look_down"
    if any(tok in raw for tok in ("惊讶", "星星眼")):
        return "look_up"

    return None


def _hit_test_any_area(model: Any, names: tuple[str, ...], x: float, y: float) -> bool:
    """Return True if any hit-area name matches at (x, y)."""
    try:
        hit_test = getattr(model, "HitTest", None)
        if not callable(hit_test):
            return False
    except Exception:
        return False

    for name in names:
        try:
            if hit_test(str(name), float(x), float(y)):
                return True
        except Exception:
            continue
    return False


def _event_key_for_hit_parts(parts: object) -> str | None:
    """Infer a semantic event key from `model.HitPart(x, y)` results (best-effort)."""
    if parts is None:
        return None
    if isinstance(parts, str):
        part_ids = [parts]
    elif isinstance(parts, (list, tuple, set)):
        part_ids = [str(x) for x in parts if str(x)]
    else:
        try:
            part_ids = [str(parts)]
        except Exception:
            part_ids = []
    if not part_ids:
        return None

    tokens = " ".join(part_ids).lower()

    # Prefer more specific parts first.
    if any(t in tokens for t in ("tail", "尾")):
        return "tail"
    if any(t in tokens for t in ("headphone", "headset", "耳机")):
        return "headphones"
    if any(t in tokens for t in ("ear", "耳")):
        return "ears"
    if any(t in tokens for t in ("tongue", "舌")):
        return "tongue"
    if any(t in tokens for t in ("fish", "鱼")):
        return "fish"
    if any(t in tokens for t in ("flower", "花")):
        return "flower"
    if any(t in tokens for t in ("armor", "plate", "钢板")):
        return "armor"
    if any(t in tokens for t in ("black", "黑")):
        return "black"

    return None


class Live2DGlWidget(QOpenGLWidget):
    """Render a Live2D Cubism 3+ model inside QOpenGLWidget."""

    VIEW_MODE_FULL = "full"
    VIEW_MODE_PORTRAIT = "portrait"
    DEFAULT_EXPRESSION_FILE = "手势 抱娃娃.exp3.json"

    status_changed = pyqtSignal()
    # Thread-safe bridge: external callers can request a state event.
    # No need to worry about Qt thread affinity.
    # (Signal emission from non-GUI threads is delivered via queued connection.)
    state_event_requested = pyqtSignal(str, float, float, str)

    def __init__(self, *, model_json: Path | None = None, parent=None) -> None:
        super().__init__(parent)

        # Performance: prefer an inexpensive surface format for continuous animation.
        # - Disable multisampling (MSAA) which can be costly for a constantly updating side panel.
        # - Prefer vsync when available to reduce needless GPU churn.
        try:
            fmt = QSurfaceFormat.defaultFormat()
            try:
                fmt.setSamples(0)
            except Exception:
                pass
            try:
                fmt.setSwapInterval(1)
            except Exception:
                pass
            self.setFormat(fmt)
        except Exception:
            pass

        self._model_json = Path(model_json) if model_json is not None else None
        self._model: Any = None
        self._live2d: Any = None
        self._gl_resources_released = False
        self._ready = False
        self._paused = False  # effective paused state
        self._requested_paused = False
        self._visibility_paused = False
        self._error_message = ""
        self._clear_rgba: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 1.0)
        self._auto_view_enabled = True
        self._view_mode = self.VIEW_MODE_FULL
        self._interaction_locked = False
        # Expression policy: keep a stable default.
        # Only change expressions via explicit user actions.
        self._default_expression_file = str(self.DEFAULT_EXPRESSION_FILE)
        self._base_expression_id: str | None = None
        self._base_expression_mode = ""  # "set" (override) or "add" (stack) for the base expression
        self._state_expression_id: str | None = None
        self._state_expression_mode = ""  # "set" (override) or "add" (stack) when active
        self._state_expression_expire_t = 0.0
        self._state_expression_event = ""
        self._state_expression_last_apply_t = 0.0
        self._expr_files_cache_dir: Path | None = None
        self._expr_files_cache_mtime = 0.0
        self._expr_files_cache_dir_mtime = 0.0
        self._expr_files_cache_model_json_mtime = 0.0
        self._expr_files_cache: list[str] = []
        self._expr_candidates_cache: dict[str, list[str]] = {}
        self._model_expression_ids: list[str] = []
        self._update_accepts_dt: bool | None = None
        self._param_setter = None
        self._lipsync_supported: bool | None = None
        self._lipsync_target = 0.0
        self._lipsync_value = 0.0
        self._lipsync_form = 0.45
        self._lipsync_last_boost_t = 0.0
        self._param_setter_supports_weight: bool | None = None
        self._param_supported: dict[str, bool] = {}
        self._param_index_cache: dict[str, int] = {}

        try:
            self.state_event_requested.connect(
                self._on_state_event_requested, type=Qt.ConnectionType.QueuedConnection
            )
        except Exception:
            try:
                self.state_event_requested.connect(self._on_state_event_requested)
            except Exception:
                pass

        # "VTuber" idle layer: subtle motion + blinking + occasional expressions.
        # Implemented best-effort on top of the model without requiring a dedicated motion set.
        self._vtuber_enabled = True
        self._vtuber_t0 = time.monotonic()
        self._vtuber_next_idle_motion_t = self._vtuber_t0 + random.uniform(14.0, 22.0)
        self._vtuber_next_expression_t = self._vtuber_t0 + random.uniform(14.0, 28.0)
        self._vtuber_blink_supported: bool | None = None
        self._vtuber_blink_next_t = self._vtuber_t0 + random.uniform(2.4, 5.0)
        self._vtuber_blink_start_t = 0.0
        self._vtuber_blink_end_t = 0.0
        self._vtuber_blink_hold_s = 0.018
        self._vtuber_next_gesture_t = self._vtuber_t0 + random.uniform(4.0, 7.0)
        self._vtuber_gesture_kind = ""
        self._vtuber_gesture_start_t = 0.0
        self._vtuber_gesture_end_t = 0.0
        self._vtuber_gesture_ax = 0.0
        self._vtuber_gesture_ay = 0.0
        self._vtuber_gesture_az = 0.0
        self._vtuber_gesture_bx = 0.0
        self._vtuber_gesture_by = 0.0
        self._vtuber_gesture_bz = 0.0
        self._vtuber_gesture_ex = 0.0
        self._vtuber_gesture_ey = 0.0
        self._vtuber_gesture_freq = 0.0
        self._vtuber_gesture_phase = 0.0
        self._vtuber_gesture_skew = 0.0
        self._vtuber_eye_open_last: float | None = None

        # Smooth pose state (prevents robotic "teleporting" between targets).
        self._pose_angle_x = 0.0
        self._pose_angle_y = 0.0
        self._pose_angle_z = 0.0
        self._pose_body_x = 0.0
        self._pose_body_y = 0.0
        self._pose_body_z = 0.0
        self._pose_eye_x = 0.0
        self._pose_eye_y = 0.0
        self._pose_breath = 0.5

        # Low-frequency noise (breaks periodic sine stiffness).
        self._noise_ax = 0.0
        self._noise_ay = 0.0
        self._noise_az = 0.0
        self._noise_bx = 0.0
        self._noise_by = 0.0
        self._noise_bz = 0.0
        self._noise_ex = 0.0
        self._noise_ey = 0.0

        # Eye micro-saccades (tiny fast glances).
        self._saccade_next_t = self._vtuber_t0 + random.uniform(0.8, 2.0)
        self._saccade_start_t = 0.0
        self._saccade_end_t = 0.0
        self._saccade_from_x = 0.0
        self._saccade_from_y = 0.0
        self._saccade_to_x = 0.0
        self._saccade_to_y = 0.0
        self._idle_drag_next_t = 0.0
        self._micro_params_next_t = self._vtuber_t0
        self._user_scale_mul = 1.0
        self._user_offset_x = 0.0
        self._user_offset_y = 0.0
        self._drag_pos: QPointF | None = None
        self._drag_smooth_pos: QPointF | None = None
        self._drag_smooth_t = 0.0
        self._panning = False
        self._pan_button: Qt.MouseButton | None = None
        self._pan_last_pos: QPointF | None = None
        self._pan_candidate = False
        self._pan_candidate_pos: QPointF | None = None
        self._pan_candidate_threshold_px = 6.0
        self._view_apply_pending = False
        self._last_viewport_px: tuple[int, int] = (0, 0)

        # Normal FPS target: keep it conservative for a side panel, but smooth enough for
        # idle motion. Temporarily boost during interaction / speech for a snappier feel.
        self._tick_ms_normal = 33  # ~30 FPS
        self._tick_ms_boost = 16  # ~60 FPS
        # Adaptive FPS under load: when the UI thread is under pressure,
        # temporarily reduce FPS to keep
        # the app responsive instead of stuttering.
        self._tick_ms_medium = 40  # ~25 FPS
        self._tick_ms_heavy = 50  # ~20 FPS
        self._fps_load_mode = 0  # 0=normal, 1=medium, 2=heavy
        self._fps_load_hold_until = 0.0
        self._fps_load_last_eval_t = 0.0
        self._render_ms_ema = 0.0
        self._render_ms_last = 0.0

        self._tick_timer = QTimer(self)
        self._tick_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._tick_timer.setInterval(self._tick_ms_normal)  # ~30 FPS, good balance for side panel
        self._tick_timer.timeout.connect(self._on_tick)

        self._fps_boost_reset = QTimer(self)
        self._fps_boost_reset.setSingleShot(True)
        self._fps_boost_reset.timeout.connect(self._restore_fps_normal)

        self._elapsed = QElapsedTimer()
        self._last_dt_s = 1.0 / 30.0

        self.setMouseTracking(True)
        self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))
        try:
            # Allow dragging `.model3.json` into the panel to switch characters quickly.
            self.setAcceptDrops(True)
        except Exception:
            pass
        try:
            self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        except Exception:
            pass
        try:
            self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
            self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        except Exception:
            pass

        # QOpenGLWidget transparency is fragile on Windows.
        # (Often becomes black or causes artifacts.)
        # We render an opaque background by default and let the panel style handle the "glass" look.
        try:
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
            self.setAutoFillBackground(False)
        except Exception:
            pass
        try:
            # Prefer the default non-preserved update behavior (better performance on Qt 5.5+).
            # QOpenGLWidget always redraws each frame anyway (Live2D).
            # Preserving content adds overhead.
            self.setUpdateBehavior(QOpenGLWidget.UpdateBehavior.NoPartialUpdate)
        except Exception:
            pass

    # -------------------------
    # Public API
    # -------------------------

    @property
    def is_ready(self) -> bool:
        return bool(self._ready)

    @property
    def is_paused(self) -> bool:
        return bool(self._paused)

    @property
    def error_message(self) -> str:
        return str(self._error_message or "")

    @property
    def view_mode(self) -> str:
        return str(self._view_mode)

    @property
    def interaction_locked(self) -> bool:
        return bool(self._interaction_locked)

    def set_interaction_locked(self, locked: bool) -> None:
        locked = bool(locked)
        if locked == self._interaction_locked:
            return
        self._interaction_locked = locked
        if locked:
            self._end_pan()
        try:
            self.status_changed.emit()
        except Exception:
            pass

    def set_view_mode(self, mode: str) -> None:
        mode = str(mode or "").strip().lower()
        if mode not in {self.VIEW_MODE_FULL, self.VIEW_MODE_PORTRAIT}:
            mode = self.VIEW_MODE_FULL
        if mode == self._view_mode:
            return
        self._view_mode = mode
        ww, hh = self._last_viewport_px
        if ww > 0 and hh > 0:
            self._apply_default_view(ww, hh)
        self.update()

    def toggle_view_mode(self) -> str:
        next_mode = (
            self.VIEW_MODE_PORTRAIT
            if self._view_mode == self.VIEW_MODE_FULL
            else self.VIEW_MODE_FULL
        )
        self.set_view_mode(next_mode)
        return str(self._view_mode)

    def trigger_reaction(self, kind: str = "manual", *, pos: QPointF | None = None) -> None:
        """Trigger a light, non-intrusive reaction (motion + optional expression)."""
        if not self._ready or self._model is None:
            return

        try:
            self._boost_fps(1200)
        except Exception:
            pass

        model = self._model

        preferred = "TapHead"
        alt = "TapBody"
        if str(kind) in {"user_send", "user"}:
            preferred, alt = alt, preferred

        # When triggered by an actual click on the model, prefer HitTest/HitPart.
        # Use it to decide reactions.
        # This makes interactions feel more natural and prevents non-click triggers (e.g. button)
        # from unexpectedly changing the base expression.
        hit_head = False
        part_event: str | None = None
        xy: tuple[float, float] | None = None
        if pos is not None:
            try:
                xy = self._drag_pos_to_model_px(pos)
            except Exception:
                xy = None

        if xy is not None:
            x, y = xy
            # Hit-area names vary across models; try common variants.
            head_areas = ("Head", "HitAreaHead", "Face", "HitArea_Face", "head", "face")
            body_areas = (
                "Body",
                "HitAreaBody",
                "Bust",
                "HitArea_Body",
                "HitAreaBust",
                "body",
                "bust",
            )
            try:
                if _hit_test_any_area(model, head_areas, x, y):
                    preferred, alt = "TapHead", "TapBody"
                    hit_head = True
                elif _hit_test_any_area(model, body_areas, x, y):
                    preferred, alt = "TapBody", "TapHead"
            except Exception:
                hit_head = False

            # Optional part-level detection for richer interactions (e.g. tail/ears).
            if not hit_head and hasattr(model, "HitPart"):
                try:
                    part_ids = model.HitPart(float(x), float(y))
                    part_event = _event_key_for_hit_parts(part_ids)
                except Exception:
                    part_event = None

        group = None
        try:
            motions = model.GetMotionGroups() if hasattr(model, "GetMotionGroups") else {}
            names: set[str] = set()
            if isinstance(motions, dict):
                try:
                    names = {str(k) for k in motions.keys() if str(k)}
                except Exception:
                    names = set()
            elif isinstance(motions, (list, tuple, set)):
                try:
                    names = {str(x) for x in motions if str(x)}
                except Exception:
                    names = set()
            if preferred in names:
                group = preferred
            elif alt in names:
                group = alt
        except Exception:
            group = None

        if group:
            try:
                model.StartRandomMotion(group, 3)
            except Exception:
                pass
        else:
            try:
                model.StartRandomMotion("Idle", 1)
            except Exception:
                pass

        # Part-level reactions are transient: keep the user's base expression stable.
        if part_event:
            try:
                self.apply_state_event(
                    str(part_event), intensity=0.82, hold_s=3.8, source="manual_part"
                )
            except Exception:
                pass

        # Keep the default expression stable.
        # Only allow expression changes on explicit user interaction.
        # (assistant/user auto reactions should not override the user's chosen look).
        try:
            allow_expression = bool(pos is not None and hit_head)
            if allow_expression and model is not None:
                # Prefer AddExpression for base expression changes.
                # This allows chat-driven state events to still stack.
                if hasattr(model, "AddExpression") and hasattr(model, "RemoveExpression"):
                    try:
                        try:
                            expr_ids = list(getattr(self, "_model_expression_ids", []) or [])
                            if not expr_ids:
                                self._refresh_model_expression_ids()
                                expr_ids = list(getattr(self, "_model_expression_ids", []) or [])
                        except Exception:
                            expr_ids = []

                        if expr_ids:
                            # Clear any SetExpression override so additive expressions are visible.
                            try:
                                if hasattr(model, "ResetExpression"):
                                    model.ResetExpression()
                            except Exception:
                                pass

                            base_id = str(getattr(self, "_base_expression_id", "") or "").strip()
                            base_mode = str(getattr(self, "_base_expression_mode", "") or "")
                            if base_id and base_mode == "add":
                                try:
                                    model.RemoveExpression(base_id)
                                except Exception:
                                    pass

                            # User action wins: cancel any transient state expression.
                            try:
                                state_id = str(
                                    getattr(self, "_state_expression_id", "") or ""
                                ).strip()
                                state_mode = str(getattr(self, "_state_expression_mode", "") or "")
                                if state_id and state_mode == "add":
                                    if not (base_mode == "add" and base_id and state_id == base_id):
                                        model.RemoveExpression(state_id)
                                elif state_id and state_mode == "set":
                                    if hasattr(model, "ResetExpression"):
                                        model.ResetExpression()
                            except Exception:
                                pass
                            self._state_expression_id = None
                            self._state_expression_mode = ""
                            self._state_expression_expire_t = 0.0
                            self._state_expression_event = ""

                            choices = expr_ids
                            if base_id and len(expr_ids) > 1:
                                try:
                                    filtered = [
                                        str(x) for x in expr_ids if str(x) and str(x) != base_id
                                    ]
                                except Exception:
                                    filtered = []
                                if filtered:
                                    choices = filtered
                            new_id = str(random.choice(choices))
                            model.AddExpression(new_id)
                            self._base_expression_id = new_id
                            self._base_expression_mode = "add"
                    except Exception:
                        pass
                elif hasattr(model, "SetRandomExpression"):
                    # Fallback: older behavior (may prevent AddExpression stacking for a while).
                    try:
                        exp_id = model.SetRandomExpression()
                        if exp_id:
                            self._base_expression_id = str(exp_id)
                            self._base_expression_mode = "set"
                        self._state_expression_id = None
                        self._state_expression_mode = ""
                        self._state_expression_expire_t = 0.0
                        self._state_expression_event = ""
                    except Exception:
                        pass
        except Exception:
            pass

        try:
            self.update()
        except Exception:
            pass

    def set_lipsync_level(self, level: float) -> None:
        """Set a 0-1 lipsync level (mouth open). Applied on the next frame."""
        try:
            lv = float(level)
        except Exception:
            lv = 0.0
        lv = max(0.0, min(1.0, lv))
        self._lipsync_target = lv
        if lv > 0.02:
            try:
                now = time.monotonic()
                last = float(getattr(self, "_lipsync_last_boost_t", 0.0) or 0.0)
                # Avoid spamming QTimer reconfiguration (set_lipsync_level can be called at 60Hz).
                if now - last > 0.35:
                    self._lipsync_last_boost_t = now
                    self._boost_fps(1300)
            except Exception:
                pass

    def reset_view(self) -> None:
        self._user_scale_mul = 1.0
        self._user_offset_x = 0.0
        self._user_offset_y = 0.0
        self._auto_view_enabled = True
        self._end_pan()
        ww, hh = self._last_viewport_px
        if ww > 0 and hh > 0:
            self._apply_default_view(ww, hh)
        self.update()

    def set_clear_color(self, r: float, g: float, b: float, a: float = 1.0) -> None:
        self._clear_rgba = (_clamp01(r), _clamp01(g), _clamp01(b), _clamp01(a))
        self.update()

    def set_clear_color_css(self, css: str, *, force_alpha: float | None = 1.0) -> None:
        self._clear_rgba = _css_color_to_rgba(css, force_alpha=force_alpha)
        self.update()

    def set_model(self, model_json: Path | None) -> None:
        self._model_json = Path(model_json) if model_json is not None else None
        self._update_accepts_dt = None
        if self._model_json is None:
            self._set_error("未配置 Live2D 模型。")
        elif not self._model_json.exists():
            self._set_error(f"未找到模型文件：{self._model_json}")
        else:
            self._set_error("")
        if self._ready:
            # Recreate renderer under current GL context.
            try:
                self.makeCurrent()
                self._destroy_model()
                self._create_model()
            finally:
                try:
                    self.doneCurrent()
                except Exception:
                    pass
            self.update()

    def set_paused(self, paused: bool) -> None:
        self._requested_paused = bool(paused)
        self._apply_pause_state()

    # -------------------------
    # Qt: GL lifecycle
    # -------------------------

    def initializeGL(self) -> None:  # noqa: N802 - Qt API naming
        live2d_mod, err = _try_import_live2d_v3()
        if live2d_mod is None:
            hint = "未检测到 / 无法加载 live2d-py（Cubism Native SDK）。\n"
            hint += f"当前 Python: {sys.executable}\n"
            hint += "请先在同一环境中同步依赖：uv sync --locked --no-install-project\n"
            if err:
                hint += f"\n错误信息：{err}"
            self._live2d = None
            self._set_ready(False)
            self._set_error(hint)
            return

        self._live2d = live2d_mod
        self._gl_resources_released = False
        try:
            ctx = self.context()
            if ctx is not None:
                ctx.aboutToBeDestroyed.connect(self._on_context_about_to_be_destroyed)
        except Exception:
            pass

        try:
            # Keep logs quiet unless user explicitly enables them.
            try:
                if hasattr(self._live2d, "enableLog"):
                    self._live2d.enableLog(False)
                elif hasattr(self._live2d, "setLogEnable"):
                    self._live2d.setLogEnable(False)
            except Exception:
                pass

            # Framework init (safe to call multiple times according to upstream docs).
            try:
                self._live2d.init()
            except Exception:
                pass

            # Init GL shaders / pipeline used by live2d-py.
            try:
                self._live2d.glInit()
            except Exception:
                try:
                    self._live2d.glewInit()
                    self._live2d.glInit()
                except Exception:
                    pass

            self._create_model()
            self._set_ready(self._model is not None)
            if self._ready:
                self._set_error("")

            self._apply_pause_state()
        except Exception as exc:
            logger.error("Live2D initializeGL failed: %s", exc, exc_info=True)
            self._set_ready(False)
            self._set_error("Live2D 初始化失败。")

    def resizeGL(self, w: int, h: int) -> None:  # noqa: N802 - Qt API naming
        if self._model is None:
            return
        ww = max(1, int(w))
        hh = max(1, int(h))

        # Qt's `resizeGL` parameters may already be device-pixel sizes.
        # (Depends on Qt version/platform.)
        # Avoid double-multiplying by DPR, otherwise the model appears "squeezed"/tiny on HiDPI.
        try:
            dpr = float(self.devicePixelRatioF() or 1.0)
        except Exception:
            dpr = 1.0
        try:
            expected_w = int(round(self.width() * dpr))
            expected_h = int(round(self.height() * dpr))
        except Exception:
            expected_w, expected_h = ww, hh

        if abs(ww - expected_w) > 2 or abs(hh - expected_h) > 2:
            ww = max(1, int(round(ww * dpr)))
            hh = max(1, int(round(hh * dpr)))

        try:
            self._model.Resize(ww, hh)
        except Exception:
            pass
        self._last_viewport_px = (int(ww), int(hh))
        self._apply_default_view(ww, hh)

    def paintGL(self) -> None:  # noqa: N802 - Qt API naming
        if not self._ready or self._model is None or self._live2d is None:
            return

        try:
            render_t0 = float(time.perf_counter())
        except Exception:
            render_t0 = 0.0

        dt_s = self._last_dt_s
        try:
            if self._elapsed.isValid():
                dt_s = max(0.0, min(0.1, self._elapsed.restart() / 1000.0))
        except Exception:
            dt_s = 1.0 / 30.0
        self._last_dt_s = dt_s

        try:
            now = time.monotonic()
        except Exception:
            now = 0.0

        # Coalesce expensive view updates: apply at most once per frame.
        # (Mouse events can fire at 500+ Hz.)
        try:
            if self._view_apply_pending:
                self._view_apply_pending = False
                ww, hh = self._last_viewport_px
                if ww > 0 and hh > 0:
                    self._apply_default_view(ww, hh)
        except Exception:
            pass

        # Feed pointer/idle movement to Live2D once per frame (instead of per mouse event).
        # This keeps interaction smooth without overwhelming the UI thread on high-frequency mice,
        # and also enables a subtle "VTuber" idle motion when the user isn't interacting.
        try:
            self._vtuber_pre_update(now)
        except Exception:
            pass

        try:
            # Some implementations want delta, others use internal timer.
            if hasattr(self._model, "Update"):
                if self._update_accepts_dt is None:
                    try:
                        self._model.Update(float(dt_s))
                        self._update_accepts_dt = True
                    except TypeError:
                        self._update_accepts_dt = False
                        self._model.Update()
                elif self._update_accepts_dt:
                    self._model.Update(float(dt_s))
                else:
                    self._model.Update()
        except Exception:
            pass

        # VTuber layer: blink / occasional expressions (post-update to avoid being overwritten).
        try:
            self._vtuber_post_update(now, dt_s)
        except Exception:
            pass

        # Lip-sync: apply after motion/physics update so it isn't immediately overwritten.
        try:
            self._apply_lipsync(dt_s)
        except Exception:
            pass

        try:
            r, g, b, a = self._clear_rgba
            self._live2d.clearBuffer(float(r), float(g), float(b), float(a))
        except Exception:
            pass
        try:
            self._model.Draw()
        except Exception:
            pass

        # Adapt FPS under load based on real render cost. This is intentionally best-effort:
        # failure to measure must not break rendering.
        if render_t0:
            try:
                render_ms = max(0.0, (float(time.perf_counter()) - float(render_t0)) * 1000.0)
            except Exception:
                render_ms = 0.0
            try:
                self._maybe_adapt_fps_under_load(now, dt_s, float(render_ms))
            except Exception:
                pass

    def _cleanup_gl_resources(self) -> None:
        if bool(getattr(self, "_gl_resources_released", False)):
            return
        self._gl_resources_released = True

        try:
            self._tick_timer.stop()
        except Exception:
            pass
        try:
            self._fps_boost_reset.stop()
        except Exception:
            pass

        try:
            self._destroy_model()
        except Exception:
            pass
        try:
            if self._live2d is not None:
                self._live2d.glRelease()
        except Exception:
            pass

        try:
            self._set_ready(False)
        except Exception:
            pass

    def _on_context_about_to_be_destroyed(self) -> None:
        try:
            self.makeCurrent()
        except Exception:
            try:
                self._cleanup_gl_resources()
            except Exception:
                pass
            return
        try:
            self._cleanup_gl_resources()
        finally:
            try:
                self.doneCurrent()
            except Exception:
                pass

    def closeEvent(self, event):  # noqa: N802 - Qt API naming
        try:
            self.makeCurrent()
        except Exception:
            self._cleanup_gl_resources()
            return super().closeEvent(event)
        try:
            self._cleanup_gl_resources()
        finally:
            try:
                self.doneCurrent()
            except Exception:
                pass
        super().closeEvent(event)

    # -------------------------
    # Interaction
    # -------------------------

    def event(self, event: QEvent):  # noqa: N802 - Qt API naming
        # Pause when the widget is not visible to save CPU/GPU.
        try:
            if event.type() == QEvent.Type.Show:
                self._visibility_paused = False
                self._apply_pause_state()
            elif event.type() == QEvent.Type.Hide:
                self._visibility_paused = True
                self._apply_pause_state()
        except Exception:
            pass
        return super().event(event)

    def mouseMoveEvent(self, event):  # noqa: N802 - Qt API naming
        if not self._ready or self._model is None:
            return super().mouseMoveEvent(event)
        try:
            pos: QPointF = event.position()
            if self._panning and self._pan_last_pos is not None:
                self._boost_fps()
                delta = pos - self._pan_last_pos
                self._pan_last_pos = pos
                try:
                    w = max(1.0, float(self.width()))
                    h = max(1.0, float(self.height()))
                    k = 1.4
                    try:
                        zoom = float(self._user_scale_mul)
                    except Exception:
                        zoom = 1.0
                    zoom = max(0.55, min(2.2, zoom))
                    k /= max(0.6, zoom)
                    self._user_offset_x += float(delta.x()) / w * k
                    # Cubism coordinate space is Y-up; Qt mouse coords are Y-down.
                    # Invert Y so "drag up -> model up" matches user expectation.
                    self._user_offset_y -= float(delta.y()) / h * k
                    # Clamp to a sane range to avoid losing the model.
                    self._user_offset_x = max(-0.8, min(0.8, self._user_offset_x))
                    self._user_offset_y = max(-0.8, min(0.6, self._user_offset_y))
                except Exception:
                    pass
                self._request_view_apply()
                event.accept()
                return

            # Left drag pan (when unlocked): delay pan until the cursor moves enough
            # that simple clicks still trigger Tap animations.
            if (
                (not self._interaction_locked)
                and self._pan_candidate
                and (event.buttons() & Qt.MouseButton.LeftButton)
                and (self._pan_candidate_pos is not None)
            ):
                try:
                    dx = float(pos.x() - self._pan_candidate_pos.x())
                    dy = float(pos.y() - self._pan_candidate_pos.y())
                    thr = float(self._pan_candidate_threshold_px)
                    if (dx * dx + dy * dy) >= (thr * thr):
                        self._pan_candidate = False
                        self._pan_candidate_pos = None
                        self._start_pan(pos, Qt.MouseButton.LeftButton)
                        event.accept()
                        return
                except Exception:
                    pass

            # Store the latest pointer pos; `paintGL` will feed it to the model once per frame.
            self._drag_pos = pos

            # Dragging is light feedback; no need to boost to 60 FPS on every hover move.
            try:
                if event.buttons() != Qt.MouseButton.NoButton:
                    self._boost_fps()
            except Exception:
                pass
            event.accept()
            return
        except Exception:
            pass
        return super().mouseMoveEvent(event)

    def mousePressEvent(self, event):  # noqa: N802 - Qt API naming
        if not self._ready or self._model is None:
            return super().mousePressEvent(event)
        try:
            self._boost_fps()
            pos: QPointF = event.position()

            # View pan: Right-drag (or Alt+Left-drag) when unlocked.
            if not self._interaction_locked:
                try:
                    if event.button() == Qt.MouseButton.RightButton or (
                        event.button() == Qt.MouseButton.LeftButton
                        and (event.modifiers() & Qt.KeyboardModifier.AltModifier)
                    ):
                        self._start_pan(pos, event.button())
                        event.accept()
                        return
                except Exception:
                    pass

                # Left press becomes a pan candidate (move beyond threshold => pan).
                # Otherwise, Tap on release.
                try:
                    if event.button() == Qt.MouseButton.LeftButton:
                        self._pan_candidate = True
                        self._pan_candidate_pos = pos
                        self._drag_pos = pos
                        event.accept()
                        return
                except Exception:
                    pass
            else:
                # Locked: keep click interactions, disable only drag/zoom.
                try:
                    if event.button() == Qt.MouseButton.LeftButton:
                        self._pan_candidate = True
                        self._pan_candidate_pos = pos
                        self._drag_pos = pos
                        event.accept()
                        return
                except Exception:
                    pass
        except Exception:
            pass
        return super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):  # noqa: N802 - Qt API naming
        # Safety: end pan even if modifiers/buttons mismatch (avoids sticky pan on some platforms).
        try:
            if self._panning:
                if self._pan_button is None or event.button() == self._pan_button:
                    self._end_pan()
                    event.accept()
                    return
        except Exception:
            pass

        # Tap action: only when the pointer didn't become a pan gesture.
        try:
            if event.button() == Qt.MouseButton.LeftButton and self._pan_candidate:
                self._pan_candidate = False
                self._pan_candidate_pos = None
                try:
                    pos: QPointF = event.position()
                except Exception:
                    pos = None
                self.trigger_reaction("manual", pos=pos)
                event.accept()
                return
        except Exception:
            # Always clear candidate state.
            self._pan_candidate = False
            self._pan_candidate_pos = None
        return super().mouseReleaseEvent(event)

    def wheelEvent(self, event):  # noqa: N802 - Qt API naming
        if self._interaction_locked:
            return super().wheelEvent(event)
        try:
            dy = int(event.angleDelta().y())
        except Exception:
            dy = 0
        if dy == 0:
            return super().wheelEvent(event)

        try:
            self._boost_fps(1500)
            steps = float(dy) / 120.0
            factor = pow(1.12, steps)
            self._user_scale_mul *= float(factor)
            self._user_scale_mul = max(0.55, min(2.2, self._user_scale_mul))
            self._request_view_apply()
            event.accept()
            return
        except Exception:
            return super().wheelEvent(event)

    def dragEnterEvent(self, event):  # noqa: N802 - Qt API naming
        try:
            mime = event.mimeData()
            if mime is None or not mime.hasUrls():
                return super().dragEnterEvent(event)
            for url in mime.urls():
                try:
                    local = str(url.toLocalFile() or "")
                    if not local:
                        continue
                    p = Path(local)
                except Exception:
                    continue
                model = self._find_dropped_model_json(p)
                if model is not None:
                    event.acceptProposedAction()
                    return
        except Exception:
            pass
        return super().dragEnterEvent(event)

    def dropEvent(self, event):  # noqa: N802 - Qt API naming
        try:
            mime = event.mimeData()
            if mime is None or not mime.hasUrls():
                return super().dropEvent(event)
            chosen: Path | None = None
            for url in mime.urls():
                try:
                    local = str(url.toLocalFile() or "")
                    if not local:
                        continue
                    p = Path(local)
                except Exception:
                    continue
                chosen = self._find_dropped_model_json(p)
                if chosen is not None:
                    break
            if chosen is None:
                return super().dropEvent(event)

            self.set_model(chosen)
            try:
                from src.gui.notifications import Toast, show_toast

                show_toast(
                    self.window(),
                    f"已加载 Live2D：{chosen.name}",
                    Toast.TYPE_SUCCESS,
                    duration=1800,
                )
            except Exception:
                pass
            event.acceptProposedAction()
            return
        except Exception:
            return super().dropEvent(event)

    # -------------------------
    # Internals
    # -------------------------

    def _set_ready(self, ready: bool) -> None:
        ready = bool(ready)
        if ready == self._ready:
            return
        self._ready = ready
        self._apply_pause_state()
        try:
            self.status_changed.emit()
        except Exception:
            pass

    def _set_error(self, message: str) -> None:
        message = str(message or "")
        if message == self._error_message:
            return
        self._error_message = message
        try:
            self.status_changed.emit()
        except Exception:
            pass

    def _apply_pause_state(self) -> None:
        should_pause = bool(self._requested_paused or self._visibility_paused or (not self._ready))
        if should_pause == self._paused:
            return
        self._paused = should_pause
        if self._paused:
            try:
                self._tick_timer.stop()
            except Exception:
                pass
        else:
            try:
                if self._ready and not self._tick_timer.isActive():
                    self._elapsed.restart()
                    self._apply_tick_interval()
                    self._tick_timer.start()
            except Exception:
                pass
        try:
            self.status_changed.emit()
        except Exception:
            pass

    def _on_tick(self) -> None:
        if self._paused or not self._ready or self._model is None:
            return
        try:
            expire = float(getattr(self, "_state_expression_expire_t", 0.0) or 0.0)
        except Exception:
            expire = 0.0
        if expire > 0.0:
            try:
                now = float(time.monotonic())
            except Exception:
                now = 0.0
            if now and now >= float(expire):
                try:
                    self._maybe_restore_base_expression(now)
                except Exception:
                    pass
        self.update()

    def _create_model(self) -> None:
        self._destroy_model()
        self._update_accepts_dt = None
        self._param_setter = None
        self._param_setter_supports_weight = None
        self._param_supported = {}
        self._param_index_cache = {}
        self._lipsync_supported = None
        try:
            t0 = time.monotonic()
        except Exception:
            t0 = 0.0
        self._vtuber_t0 = t0
        self._vtuber_next_idle_motion_t = t0 + random.uniform(14.0, 22.0)
        self._vtuber_next_expression_t = t0 + random.uniform(14.0, 28.0)
        self._vtuber_blink_supported = None
        self._vtuber_blink_next_t = t0 + random.uniform(2.4, 5.0)
        self._vtuber_blink_start_t = 0.0
        self._vtuber_blink_end_t = 0.0
        self._vtuber_blink_hold_s = 0.018
        self._vtuber_next_gesture_t = t0 + random.uniform(4.0, 7.0)
        self._vtuber_gesture_kind = ""
        self._vtuber_gesture_start_t = 0.0
        self._vtuber_gesture_end_t = 0.0
        self._vtuber_gesture_ax = 0.0
        self._vtuber_gesture_ay = 0.0
        self._vtuber_gesture_az = 0.0
        self._vtuber_gesture_bx = 0.0
        self._vtuber_gesture_by = 0.0
        self._vtuber_gesture_bz = 0.0
        self._vtuber_gesture_ex = 0.0
        self._vtuber_gesture_ey = 0.0
        self._vtuber_eye_open_last = None
        self._idle_drag_next_t = 0.0
        self._micro_params_next_t = t0
        if self._live2d is None:
            self._set_error("未检测到 live2d-py。")
            return
        if self._model_json is None:
            self._set_error("未配置 Live2D 模型。")
            return
        src_model_json = Path(self._model_json)
        if not src_model_json.exists():
            self._set_error(f"未找到模型文件：{src_model_json}")
            return

        # live2d-py / CubismJson on Windows can crash on non-ASCII JSON documents.
        # If the model folder contains non-ASCII expressions/motions, generate an ASCII-only
        # model3.json in a cache dir and copy small assets there (expressions/motions only).
        model_path = self._prepare_ascii_model_json(src_model_json)

        try:
            model = self._live2d.LAppModel()
        except Exception:
            try:
                model = self._live2d.Model()
            except Exception:
                model = None
        if model is None:
            return

        try:
            model.LoadModelJson(str(model_path))
        except Exception as exc:
            logger.error("Live2D LoadModelJson failed: %s", exc, exc_info=True)
            self._set_error("Live2D 模型加载失败。")
            return

        # Create GPU resources.
        try:
            if hasattr(model, "CreateRenderer"):
                model.CreateRenderer()
        except Exception:
            pass
        self._model = model
        try:
            self._refresh_model_expression_ids()
        except Exception:
            pass
        self._end_pan()

        # Initial size & pose.
        try:
            self.resizeGL(int(self.width()), int(self.height()))
        except Exception:
            pass

        # Start a gentle idle motion if possible (prefer model-provided groups).
        try:
            self._start_default_idle_motion()
        except Exception:
            pass

        # Default expression: keep "hugging doll" gesture as the stable baseline.
        try:
            self._apply_default_expression(src_model_json)
        except Exception:
            pass

        self._set_error("")

    def _pick_idle_motion_group(self, groups: Any) -> str | None:
        keys: list[str] = []
        if isinstance(groups, dict):
            keys = [str(k) for k in groups.keys()]
        elif isinstance(groups, (list, tuple, set)):
            keys = [str(k) for k in groups]
        elif isinstance(groups, str):
            keys = [str(groups)]

        keys = [k for k in keys if k]
        if not keys:
            return None

        prefer_exact = {"idle", "default", "standby", "waiting"}
        for k in keys:
            if k.lower() in prefer_exact:
                return k

        prefer_tokens = ("idle", "standby", "default", "wait", "stand")
        prefer_cn = ("待机", "站立", "默认", "呼吸")
        for k in keys:
            low = k.lower()
            if any(tok in low for tok in prefer_tokens) or any(tok in k for tok in prefer_cn):
                return k

        return keys[0]

    def _set_param_cached(self, setter, pid: str, value: float, weight: float) -> bool:
        """Set a Cubism parameter while caching missing IDs to avoid per-frame exceptions."""
        pid = str(pid or "")
        if not pid:
            return False
        cached = self._param_supported.get(pid)
        if cached is False:
            return False
        try:
            setter(pid, float(value), float(weight))
            self._param_supported[pid] = True
            return True
        except Exception:
            self._param_supported[pid] = False
            return False

    def _smooth_to(self, current: float, target: float, *, k: float, dt: float) -> float:
        try:
            kk = max(0.0, float(k))
        except Exception:
            kk = 0.0
        if kk <= 0.0:
            return float(target)
        try:
            d = max(0.0, min(0.2, float(dt)))
        except Exception:
            d = 0.0
        if d <= 0.0:
            return float(current)
        try:
            alpha = 1.0 - math.exp(-kk * d)
        except Exception:
            alpha = min(1.0, kk * d)
        return float(current) + (float(target) - float(current)) * max(0.0, min(1.0, float(alpha)))

    def _ou_step(self, x: float, *, dt: float, tau: float, sigma: float) -> float:
        """Ornstein–Uhlenbeck step (smooth noise)."""
        try:
            d = max(0.0, min(0.2, float(dt)))
        except Exception:
            d = 0.0
        if d <= 0.0:
            return float(x)
        t = max(1e-3, float(tau))
        s = max(0.0, float(sigma))
        try:
            n = random.gauss(0.0, 1.0)
        except Exception:
            n = 0.0
        dx = (-float(x) / t) * d + s * math.sqrt(d) * float(n)
        return float(x) + float(dx)

    def _start_default_idle_motion(self) -> None:
        model = self._model
        if model is None or not hasattr(model, "StartRandomMotion"):
            return
        groups = None
        try:
            groups = model.GetMotionGroups() if hasattr(model, "GetMotionGroups") else None
        except Exception:
            groups = None
        group = self._pick_idle_motion_group(groups) or "Idle"
        try:
            model.StartRandomMotion(str(group), 1)
        except Exception:
            pass

    # -------------------------
    # VTuber idle layer
    # -------------------------

    def set_vtuber_mode(self, enabled: bool) -> None:
        self._vtuber_enabled = bool(enabled)
        try:
            self.status_changed.emit()
        except Exception:
            pass

    def _vtuber_maybe_start_gesture(self, now: float) -> None:
        if not now:
            return
        try:
            now_f = float(now)
        except Exception:
            return

        # Clear finished gesture.
        try:
            end_t = float(getattr(self, "_vtuber_gesture_end_t", 0.0) or 0.0)
        except Exception:
            end_t = 0.0
        if end_t > 0.0 and now_f >= end_t:
            self._vtuber_gesture_kind = ""
            self._vtuber_gesture_start_t = 0.0
            self._vtuber_gesture_end_t = 0.0
            self._vtuber_gesture_ax = 0.0
            self._vtuber_gesture_ay = 0.0
            self._vtuber_gesture_az = 0.0
            self._vtuber_gesture_bx = 0.0
            self._vtuber_gesture_by = 0.0
            self._vtuber_gesture_bz = 0.0
            self._vtuber_gesture_ex = 0.0
            self._vtuber_gesture_ey = 0.0
            self._vtuber_gesture_freq = 0.0
            self._vtuber_gesture_phase = 0.0
            self._vtuber_gesture_skew = 0.0

        # Still active.
        if float(getattr(self, "_vtuber_gesture_end_t", 0.0) or 0.0) > now_f:
            return

        try:
            next_t = float(getattr(self, "_vtuber_next_gesture_t", 0.0) or 0.0)
        except Exception:
            next_t = 0.0
        if now_f < next_t:
            return

        speaking = float(getattr(self, "_lipsync_value", 0.0) or 0.0) > 0.08

        kinds = [
            "nod",
            "shake",
            "tilt",
            "look_left",
            "look_right",
            "look_up",
            "look_down",
            "lean",
        ]
        weights = [1.2, 1.0, 0.9, 0.8, 0.8, 0.7, 0.7, 0.9]
        if speaking:
            # More "talking with head" while speaking.
            weights = [1.8, 1.3, 0.8, 0.55, 0.55, 0.45, 0.45, 0.7]

        try:
            kind = random.choices(kinds, weights=weights, k=1)[0]
        except Exception:
            kind = "nod"

        # Gesture amplitude (degrees / eye params) and duration.
        dur = 1.25
        ax = ay = az = bx = by = bz = ex = ey = 0.0
        if kind == "nod":
            dur = random.uniform(1.0, 1.35)
            ay = random.uniform(18.0, 26.0)
        elif kind == "shake":
            dur = random.uniform(1.05, 1.45)
            ax = random.uniform(22.0, 32.0)
        elif kind == "tilt":
            dur = random.uniform(1.0, 1.3)
            az = random.uniform(10.0, 16.0)
        elif kind == "look_left":
            dur = random.uniform(1.2, 1.7)
            ex = -random.uniform(0.42, 0.68)
            ax = -random.uniform(8.0, 14.0)
        elif kind == "look_right":
            dur = random.uniform(1.2, 1.7)
            ex = random.uniform(0.42, 0.68)
            ax = random.uniform(8.0, 14.0)
        elif kind == "look_up":
            dur = random.uniform(1.1, 1.6)
            ey = random.uniform(0.28, 0.50)
            ay = random.uniform(12.0, 18.0)
        elif kind == "look_down":
            dur = random.uniform(1.1, 1.6)
            ey = -random.uniform(0.26, 0.48)
            ay = -random.uniform(14.0, 21.0)
        elif kind == "lean":
            dur = random.uniform(1.4, 2.1)
            bx = random.uniform(-18.0, 18.0)
            by = random.uniform(-6.0, 6.0)
            bz = random.uniform(-12.0, 12.0)
            az = random.uniform(-8.0, 8.0)

        self._vtuber_gesture_kind = str(kind)
        self._vtuber_gesture_start_t = now_f
        self._vtuber_gesture_end_t = now_f + float(dur)
        self._vtuber_gesture_ax = float(ax)
        self._vtuber_gesture_ay = float(ay)
        self._vtuber_gesture_az = float(az)
        self._vtuber_gesture_bx = float(bx)
        self._vtuber_gesture_by = float(by)
        self._vtuber_gesture_bz = float(bz)
        self._vtuber_gesture_ex = float(ex)
        self._vtuber_gesture_ey = float(ey)
        base_cycles = 1.0
        if kind == "nod":
            base_cycles = 2.0
        elif kind == "shake":
            base_cycles = 3.0
        elif kind in {"tilt", "lean"}:
            base_cycles = 1.15
        self._vtuber_gesture_freq = float(base_cycles) * random.uniform(0.92, 1.08)
        self._vtuber_gesture_phase = random.uniform(-0.45, 0.45)
        self._vtuber_gesture_skew = random.uniform(-0.12, 0.12)
        self._vtuber_next_gesture_t = (now_f + float(dur)) + random.uniform(3.2, 6.2)

    def _vtuber_force_gesture(
        self,
        kind: str,
        *,
        intensity: float = 0.7,
        duration_s: float | None = None,
    ) -> bool:
        """Force-start a VTuber gesture (used by chat-driven state events).

        This is best-effort and does not require motion assets.
        """

        if self._model is None:
            return False

        kind = str(kind or "").strip().lower()
        if not kind:
            return False

        allowed = {
            "nod",
            "shake",
            "tilt",
            "look_left",
            "look_right",
            "look_up",
            "look_down",
            "lean",
        }
        if kind not in allowed:
            return False

        try:
            now_f = float(time.monotonic())
        except Exception:
            now_f = 0.0
        if not now_f:
            return False

        iv = _clamp01(float(intensity))
        amp_scale = 0.62 + 0.80 * float(iv)  # 0.62..1.42

        dur = None
        if duration_s is not None:
            try:
                dur = float(duration_s)
            except Exception:
                dur = None
        if dur is None:
            if kind == "nod":
                dur = random.uniform(0.95, 1.25)
            elif kind == "shake":
                dur = random.uniform(0.95, 1.30)
            elif kind == "tilt":
                dur = random.uniform(0.95, 1.25)
            elif kind.startswith("look_"):
                dur = random.uniform(1.05, 1.55)
            else:
                dur = random.uniform(1.20, 1.85)
        dur = max(0.35, min(4.0, float(dur)))

        ax = ay = az = bx = by = bz = ex = ey = 0.0
        if kind == "nod":
            ay = random.uniform(18.0, 26.0) * amp_scale
        elif kind == "shake":
            ax = random.uniform(22.0, 32.0) * amp_scale
        elif kind == "tilt":
            az = random.uniform(10.0, 16.0) * amp_scale
        elif kind == "look_left":
            ex = -random.uniform(0.42, 0.68) * amp_scale
            ax = -random.uniform(8.0, 14.0) * amp_scale
        elif kind == "look_right":
            ex = random.uniform(0.42, 0.68) * amp_scale
            ax = random.uniform(8.0, 14.0) * amp_scale
        elif kind == "look_up":
            ey = random.uniform(0.28, 0.50) * amp_scale
            ay = random.uniform(12.0, 18.0) * amp_scale
        elif kind == "look_down":
            ey = -random.uniform(0.26, 0.48) * amp_scale
            ay = -random.uniform(14.0, 21.0) * amp_scale
        elif kind == "lean":
            bx = random.uniform(-18.0, 18.0) * amp_scale
            by = random.uniform(-6.0, 6.0) * amp_scale
            bz = random.uniform(-12.0, 12.0) * amp_scale
            az = random.uniform(-8.0, 8.0) * amp_scale

        # Clamp eye params to avoid extreme values on rigs with narrow ranges.
        ex = max(-1.0, min(1.0, float(ex)))
        ey = max(-1.0, min(1.0, float(ey)))

        self._vtuber_gesture_kind = str(kind)
        self._vtuber_gesture_start_t = float(now_f)
        self._vtuber_gesture_end_t = float(now_f + dur)
        self._vtuber_gesture_ax = float(ax)
        self._vtuber_gesture_ay = float(ay)
        self._vtuber_gesture_az = float(az)
        self._vtuber_gesture_bx = float(bx)
        self._vtuber_gesture_by = float(by)
        self._vtuber_gesture_bz = float(bz)
        self._vtuber_gesture_ex = float(ex)
        self._vtuber_gesture_ey = float(ey)

        base_cycles = 1.0
        if kind == "nod":
            base_cycles = 2.0
        elif kind == "shake":
            base_cycles = 3.0
        elif kind in {"tilt", "lean"}:
            base_cycles = 1.15
        self._vtuber_gesture_freq = float(base_cycles) * random.uniform(0.95, 1.07)
        self._vtuber_gesture_phase = random.uniform(-0.25, 0.25)
        self._vtuber_gesture_skew = random.uniform(-0.10, 0.10)
        self._vtuber_next_gesture_t = (now_f + float(dur)) + random.uniform(3.6, 6.8)

        try:
            self._boost_fps(1200)
        except Exception:
            pass
        try:
            self.update()
        except Exception:
            pass
        return True

    def _vtuber_gesture_offsets(
        self, now: float
    ) -> tuple[float, float, float, float, float, float, float, float]:
        if not now:
            return (0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
        try:
            now_f = float(now)
        except Exception:
            return (0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

        try:
            start_t = float(getattr(self, "_vtuber_gesture_start_t", 0.0) or 0.0)
            end_t = float(getattr(self, "_vtuber_gesture_end_t", 0.0) or 0.0)
        except Exception:
            start_t = 0.0
            end_t = 0.0
        if start_t <= 0.0 or end_t <= 0.0 or now_f < start_t or now_f >= end_t:
            return (0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

        dur = max(1e-3, end_t - start_t)
        p = max(0.0, min(1.0, (now_f - start_t) / dur))
        tau = 2.0 * math.pi

        kind = str(getattr(self, "_vtuber_gesture_kind", "") or "")
        ax = float(getattr(self, "_vtuber_gesture_ax", 0.0) or 0.0)
        ay = float(getattr(self, "_vtuber_gesture_ay", 0.0) or 0.0)
        az = float(getattr(self, "_vtuber_gesture_az", 0.0) or 0.0)
        bx = float(getattr(self, "_vtuber_gesture_bx", 0.0) or 0.0)
        by = float(getattr(self, "_vtuber_gesture_by", 0.0) or 0.0)
        bz = float(getattr(self, "_vtuber_gesture_bz", 0.0) or 0.0)
        ex = float(getattr(self, "_vtuber_gesture_ex", 0.0) or 0.0)
        ey = float(getattr(self, "_vtuber_gesture_ey", 0.0) or 0.0)
        freq = float(getattr(self, "_vtuber_gesture_freq", 0.0) or 0.0)
        phase = float(getattr(self, "_vtuber_gesture_phase", 0.0) or 0.0)
        skew = float(getattr(self, "_vtuber_gesture_skew", 0.0) or 0.0)

        if freq <= 0.0:
            if kind == "nod":
                freq = 2.0
            elif kind == "shake":
                freq = 3.0
            else:
                freq = 1.0

        # Naturalize gesture timing: apply a small non-linear warp + skew so the movement
        # isn't perfectly symmetric/robotic.
        p_warp = float(p) + 0.10 * float(skew) * math.sin(math.pi * float(p))
        p_warp = max(0.0, min(1.0, p_warp))
        env = math.sin(math.pi * p_warp)
        try:
            env = pow(max(0.0, min(1.0, env)), 1.15)
        except Exception:
            pass

        ox = oy = oz = obx = oby = obz = oex = oey = 0.0
        if kind == "nod":
            # 2 nods.
            oy = ay * math.sin(tau * float(freq) * p_warp + phase) * env
            oz = (
                (0.18 * float(ay)) * math.sin(tau * 0.55 * float(freq) * p_warp + phase + 1.3) * env
            )
        elif kind == "shake":
            # 3 shakes.
            ox = ax * math.sin(tau * float(freq) * p_warp + phase) * env
            oz = (
                (0.08 * float(ax)) * math.sin(tau * 0.55 * float(freq) * p_warp + phase + 0.7) * env
            )
        elif kind == "tilt":
            oz = az * math.sin(tau * float(freq) * p_warp + phase) * env
        elif kind.startswith("look_"):
            # Look then return.
            oex = ex * env
            oey = ey * env
            ox = ax * env
            oy = ay * env
        elif kind == "lean":
            obx = bx * env
            oby = by * env
            obz = bz * env
            oz = az * math.sin(tau * float(freq) * p_warp + phase) * env

        return (ox, oy, oz, obx, oby, obz, oex, oey)

    def _drag_pos_to_model_px(self, pos: QPointF) -> tuple[float, float]:
        """Convert a Qt local mouse pos to the coordinate space expected by `model.Drag`.

        live2d-py typically works in the same pixel space as `model.Resize`.
        Qt events provide logical coordinates, while `resizeGL` may pass device-pixel sizes.
        mismatch (more consistent interaction across DPI settings).
        """

        try:
            ww_px, hh_px = self._last_viewport_px
        except Exception:
            ww_px, hh_px = 0, 0
        try:
            w_log = max(1.0, float(self.width()))
            h_log = max(1.0, float(self.height()))
        except Exception:
            w_log, h_log = 1.0, 1.0

        try:
            ww_f = float(ww_px) if ww_px and ww_px > 0 else float(w_log)
            hh_f = float(hh_px) if hh_px and hh_px > 0 else float(h_log)
        except Exception:
            ww_f, hh_f = float(w_log), float(h_log)

        sx = ww_f / max(1.0, float(w_log))
        sy = hh_f / max(1.0, float(h_log))
        try:
            x = float(pos.x()) * float(sx)
            y = float(pos.y()) * float(sy)
        except Exception:
            x = float(getattr(pos, "x", 0.0)() if callable(getattr(pos, "x", None)) else 0.0)
            y = float(getattr(pos, "y", 0.0)() if callable(getattr(pos, "y", None)) else 0.0)
        return (float(x), float(y))

    def _vtuber_pre_update(self, now: float) -> None:
        """Per-frame pre-update hooks: pointer drag + subtle idle movement."""
        model = self._model
        if model is None:
            return
        if self._panning:
            self._drag_smooth_pos = None
            self._drag_smooth_t = 0.0
            return

        # 1) User pointer interaction takes precedence.
        #    (Even when locked; lock only disables pan/zoom.)
        hovering = False
        try:
            hovering = bool(self.underMouse())
        except Exception:
            hovering = False

        if hovering and (self._drag_pos is not None):
            try:
                target = self._drag_pos
                use = target

                try:
                    now_f = float(now)
                except Exception:
                    now_f = 0.0
                if now_f:
                    if self._drag_smooth_pos is None or self._drag_smooth_t <= 0.0:
                        self._drag_smooth_pos = QPointF(float(target.x()), float(target.y()))
                        self._drag_smooth_t = now_f
                    else:
                        dt = max(0.0, min(0.25, now_f - float(self._drag_smooth_t)))
                        self._drag_smooth_t = now_f
                        tau = 0.075
                        try:
                            alpha = 1.0 - math.exp(-dt / tau)
                        except Exception:
                            alpha = 0.22
                        alpha = max(0.05, min(0.9, float(alpha)))
                        sp = self._drag_smooth_pos
                        sx = float(sp.x()) + (float(target.x()) - float(sp.x())) * alpha
                        sy = float(sp.y()) + (float(target.y()) - float(sp.y())) * alpha
                        self._drag_smooth_pos = QPointF(sx, sy)
                    use = self._drag_smooth_pos or target

                x, y = self._drag_pos_to_model_px(use)
                model.Drag(float(x), float(y))
            except Exception:
                pass
        else:
            self._drag_smooth_pos = None
            self._drag_smooth_t = 0.0
            # 2) VTuber idle motion: a gentle "follow" point wobble.
            if bool(getattr(self, "_vtuber_enabled", True)):
                should_drag = True
                try:
                    now_f = float(now)
                except Exception:
                    now_f = 0.0
                if not now_f:
                    should_drag = False
                else:
                    try:
                        lv_seen = float(getattr(self, "_lipsync_value", 0.0) or 0.0)
                    except Exception:
                        lv_seen = 0.0
                    interval_s = 0.04 if lv_seen > 0.02 else 0.085
                    try:
                        next_t = float(getattr(self, "_idle_drag_next_t", 0.0) or 0.0)
                    except Exception:
                        next_t = 0.0
                    if now_f < next_t:
                        should_drag = False
                    else:
                        self._idle_drag_next_t = now_f + float(interval_s)

                if not should_drag:
                    # Skip `Drag` this frame.
                    # Still allow periodic motion/expression scheduling below.
                    pass
                else:
                    try:
                        try:
                            vw, vh = self._last_viewport_px
                        except Exception:
                            vw, vh = 0, 0
                        ww = max(1.0, float(vw) if vw and vw > 0 else float(self.width()))
                        hh = max(1.0, float(vh) if vh and vh > 0 else float(self.height()))
                        t0 = float(getattr(self, "_vtuber_t0", 0.0) or 0.0)
                        t = max(0.0, float(now) - t0) if now and t0 else 0.0
                        tau = 2.0 * math.pi

                        base_x = ww * 0.52
                        base_y = hh * 0.34

                        # A slightly stronger idle drag makes subtle Live2D rigs more readable.
                        amp_x = ww * 0.088
                        amp_y = hh * 0.078

                        wobble_x = math.sin(tau * 0.16 * t) + 0.35 * math.sin(tau * 0.47 * t + 0.4)
                        wobble_y = math.sin(tau * 0.13 * t + 1.2) + 0.28 * math.sin(
                            tau * 0.41 * t + 2.1
                        )

                        x = base_x + amp_x * wobble_x
                        y = base_y + amp_y * wobble_y

                        # Speaking bob: tiny head bob tied to lip-sync intensity.
                        lv_seen = float(getattr(self, "_lipsync_value", 0.0) or 0.0)
                        if lv_seen > 0.01:
                            bob = hh * 0.018 * min(1.0, lv_seen)
                            x += (ww * 0.010 * lv_seen) * math.sin(tau * 0.9 * t + 0.8)
                            y += bob * (0.55 + 0.45 * math.sin(tau * 1.1 * t))

                        x = max(0.0, min(ww, x))
                        y = max(0.0, min(hh, y))
                        model.Drag(float(x), float(y))
                    except Exception:
                        pass

        # Periodic auto motion to keep the model feeling alive.
        if bool(getattr(self, "_vtuber_enabled", True)) and now:
            try:
                if float(now) >= float(getattr(self, "_vtuber_next_idle_motion_t", 0.0) or 0.0):
                    self._vtuber_next_idle_motion_t = float(now) + random.uniform(14.0, 22.0)
                    try:
                        self._start_default_idle_motion()
                    finally:
                        self._boost_fps(1100)
            except Exception:
                pass

    def _vtuber_post_update(self, now: float, dt_s: float) -> None:
        """Post-update: apply parameter tweaks (blink/breath) so they aren't overwritten."""
        vtuber_enabled = bool(getattr(self, "_vtuber_enabled", True))
        gesture_active = False
        try:
            if now:
                now_f = float(now)
                start_t = float(getattr(self, "_vtuber_gesture_start_t", 0.0) or 0.0)
                end_t = float(getattr(self, "_vtuber_gesture_end_t", 0.0) or 0.0)
                gesture_active = bool(start_t > 0.0 and end_t > 0.0 and now_f < end_t)
        except Exception:
            gesture_active = False
        if not (vtuber_enabled or gesture_active):
            return
        if self._model is None:
            return

        setter = self._param_setter
        if setter is None:
            setter = self._discover_param_setter()
            self._param_setter = setter
        if setter is None:
            return

        if vtuber_enabled:
            # Eye blink (best-effort).
            try:
                self._apply_vtuber_blink(now, setter)
            except Exception:
                pass

        # VTuber: subtle idle motion + periodic gestures (nod/shake/look/lean).
        if now:
            if vtuber_enabled:
                try:
                    self._vtuber_maybe_start_gesture(now)
                except Exception:
                    pass
            try:
                ox, oy, oz, obx, oby, obz, oex, oey = self._vtuber_gesture_offsets(now)
            except Exception:
                ox = oy = oz = obx = oby = obz = oex = oey = 0.0

            supports_weight = bool(getattr(self, "_param_setter_supports_weight", False))
            w = 0.72 if supports_weight else 1.0
            amp_gain = 1.35 if supports_weight else 1.18
            if self._view_mode == self.VIEW_MODE_PORTRAIT:
                amp_gain *= 1.09

            hovering = False
            try:
                hovering = bool(self.underMouse())
            except Exception:
                hovering = False
            if hovering and (not bool(getattr(self, "_interaction_locked", False))):
                amp_gain *= 0.78

            try:
                t0 = float(getattr(self, "_vtuber_t0", 0.0) or 0.0)
            except Exception:
                t0 = 0.0
            try:
                t = max(0.0, float(now) - t0) if t0 else 0.0
            except Exception:
                t = 0.0
            tau = 2.0 * math.pi
            try:
                dt = max(0.0, min(0.1, float(dt_s)))
            except Exception:
                dt = 1.0 / 30.0

            # Base idle: seated upper-body motion.
            angle_x = 11.2 * math.sin(tau * 0.12 * t) + 2.8 * math.sin(tau * 0.31 * t + 0.4)
            angle_y = 6.4 * math.sin(tau * 0.10 * t + 1.1) + 2.0 * math.sin(tau * 0.24 * t + 2.0)
            angle_z = 4.8 * math.sin(tau * 0.09 * t + 0.2)
            body_x = 7.6 * math.sin(tau * 0.08 * t + 0.4)
            body_y = 3.2 * math.sin(tau * 0.06 * t + 0.8)
            body_z = 3.8 * math.sin(tau * 0.07 * t + 2.0)
            breath = 0.5 + 0.5 * math.sin(tau * 0.18 * t + 0.7)

            eye_x = 0.22 * math.sin(tau * 0.19 * t + 1.0) + 0.06 * math.sin(tau * 0.57 * t)
            eye_y = 0.14 * math.sin(tau * 0.17 * t + 2.3)

            # Smooth noise: breaks the "too periodic" feel.
            try:
                self._noise_ax = self._ou_step(
                    float(getattr(self, "_noise_ax", 0.0) or 0.0), dt=dt, tau=2.2, sigma=1.1
                )
                self._noise_ay = self._ou_step(
                    float(getattr(self, "_noise_ay", 0.0) or 0.0), dt=dt, tau=2.6, sigma=0.9
                )
                self._noise_az = self._ou_step(
                    float(getattr(self, "_noise_az", 0.0) or 0.0), dt=dt, tau=2.8, sigma=0.7
                )
                self._noise_bx = self._ou_step(
                    float(getattr(self, "_noise_bx", 0.0) or 0.0), dt=dt, tau=3.1, sigma=0.6
                )
                self._noise_by = self._ou_step(
                    float(getattr(self, "_noise_by", 0.0) or 0.0), dt=dt, tau=3.4, sigma=0.5
                )
                self._noise_bz = self._ou_step(
                    float(getattr(self, "_noise_bz", 0.0) or 0.0), dt=dt, tau=3.6, sigma=0.5
                )
                self._noise_ex = self._ou_step(
                    float(getattr(self, "_noise_ex", 0.0) or 0.0), dt=dt, tau=1.4, sigma=0.06
                )
                self._noise_ey = self._ou_step(
                    float(getattr(self, "_noise_ey", 0.0) or 0.0), dt=dt, tau=1.4, sigma=0.05
                )
            except Exception:
                pass
            angle_x += max(-3.0, min(3.0, float(getattr(self, "_noise_ax", 0.0) or 0.0)))
            angle_y += max(-3.0, min(3.0, float(getattr(self, "_noise_ay", 0.0) or 0.0)))
            angle_z += max(-2.2, min(2.2, float(getattr(self, "_noise_az", 0.0) or 0.0)))
            body_x += max(-1.8, min(1.8, float(getattr(self, "_noise_bx", 0.0) or 0.0)))
            body_y += max(-1.6, min(1.6, float(getattr(self, "_noise_by", 0.0) or 0.0)))
            body_z += max(-1.6, min(1.6, float(getattr(self, "_noise_bz", 0.0) or 0.0)))
            eye_x += max(-0.20, min(0.20, float(getattr(self, "_noise_ex", 0.0) or 0.0)))
            eye_y += max(-0.16, min(0.16, float(getattr(self, "_noise_ey", 0.0) or 0.0)))

            # Speaking: tiny pitch bob so the avatar "talks with the head".
            try:
                lv = float(getattr(self, "_lipsync_value", 0.0) or 0.0)
            except Exception:
                lv = 0.0
            if lv > 0.02:
                angle_y += (6.6 * min(1.0, lv)) * math.sin(tau * 0.9 * t + 0.6)
                body_x += (3.3 * min(1.0, lv)) * math.sin(tau * 0.6 * t + 1.2)

            # Eye micro-saccade: quick tiny glances.
            try:
                now_f = float(now)
            except Exception:
                now_f = 0.0
            if now_f:
                try:
                    if self._saccade_end_t <= 0.0 and now_f >= float(
                        getattr(self, "_saccade_next_t", 0.0) or 0.0
                    ):
                        self._saccade_start_t = now_f
                        self._saccade_end_t = now_f + random.uniform(0.22, 0.34)
                        self._saccade_to_x = random.uniform(-0.18, 0.18)
                        self._saccade_to_y = random.uniform(-0.12, 0.12)
                        self._saccade_from_x = float(getattr(self, "_pose_eye_x", 0.0) or 0.0)
                        self._saccade_from_y = float(getattr(self, "_pose_eye_y", 0.0) or 0.0)
                except Exception:
                    pass

                if float(getattr(self, "_saccade_end_t", 0.0) or 0.0) > 0.0:
                    st = float(getattr(self, "_saccade_start_t", 0.0) or 0.0)
                    et = float(getattr(self, "_saccade_end_t", 0.0) or 0.0)
                    dur = max(1e-3, et - st)
                    p = max(0.0, min(1.0, (now_f - st) / dur))

                    def _smoothstep(x: float) -> float:
                        x = max(0.0, min(1.0, float(x)))
                        return x * x * (3.0 - 2.0 * x)

                    if p < 0.18:
                        env = _smoothstep(p / 0.18)
                    elif p < 0.70:
                        env = 1.0
                    else:
                        env = 1.0 - _smoothstep((p - 0.70) / 0.30)

                    eye_x += float(getattr(self, "_saccade_to_x", 0.0) or 0.0) * env
                    eye_y += float(getattr(self, "_saccade_to_y", 0.0) or 0.0) * env

                    if now_f >= et:
                        self._saccade_end_t = 0.0
                        self._saccade_start_t = 0.0
                        self._saccade_next_t = now_f + random.uniform(0.9, 2.2)

            # Gesture overlay.
            angle_x += ox
            angle_y += oy
            angle_z += oz
            body_x += obx
            body_y += oby
            body_z += obz
            eye_x += oex
            eye_y += oey

            angle_x *= amp_gain
            angle_y *= amp_gain
            angle_z *= amp_gain
            body_x *= amp_gain
            body_y *= amp_gain
            body_z *= amp_gain
            eye_x *= amp_gain
            eye_y *= amp_gain

            # Clamp to common Cubism ranges.
            angle_x = max(-30.0, min(30.0, float(angle_x)))
            angle_y = max(-30.0, min(30.0, float(angle_y)))
            angle_z = max(-30.0, min(30.0, float(angle_z)))
            body_x = max(-20.0, min(20.0, float(body_x)))
            body_y = max(-20.0, min(20.0, float(body_y)))
            body_z = max(-20.0, min(20.0, float(body_z)))
            breath = max(0.0, min(1.0, float(breath)))
            eye_x = max(-1.0, min(1.0, float(eye_x)))
            eye_y = max(-1.0, min(1.0, float(eye_y)))

            # Smooth pose blending to avoid robotic movement.
            try:
                gesture_active = float(getattr(self, "_vtuber_gesture_end_t", 0.0) or 0.0) > float(
                    now_f
                )
            except Exception:
                gesture_active = False
            k_head = 11.5 * (1.35 if gesture_active else 1.0)
            k_body = 8.5 * (1.25 if gesture_active else 1.0)
            k_eye = 16.0 * (
                1.4 if float(getattr(self, "_saccade_end_t", 0.0) or 0.0) > 0.0 else 1.0
            )
            k_breath = 5.0
            if lv > 0.05:
                k_head *= 1.25
                k_body *= 1.15

            self._pose_angle_x = self._smooth_to(
                float(getattr(self, "_pose_angle_x", 0.0) or 0.0), angle_x, k=k_head, dt=dt
            )
            self._pose_angle_y = self._smooth_to(
                float(getattr(self, "_pose_angle_y", 0.0) or 0.0), angle_y, k=k_head, dt=dt
            )
            self._pose_angle_z = self._smooth_to(
                float(getattr(self, "_pose_angle_z", 0.0) or 0.0), angle_z, k=k_head, dt=dt
            )
            self._pose_body_x = self._smooth_to(
                float(getattr(self, "_pose_body_x", 0.0) or 0.0), body_x, k=k_body, dt=dt
            )
            self._pose_body_y = self._smooth_to(
                float(getattr(self, "_pose_body_y", 0.0) or 0.0), body_y, k=k_body, dt=dt
            )
            self._pose_body_z = self._smooth_to(
                float(getattr(self, "_pose_body_z", 0.0) or 0.0), body_z, k=k_body, dt=dt
            )
            self._pose_eye_x = self._smooth_to(
                float(getattr(self, "_pose_eye_x", 0.0) or 0.0), eye_x, k=k_eye, dt=dt
            )
            self._pose_eye_y = self._smooth_to(
                float(getattr(self, "_pose_eye_y", 0.0) or 0.0), eye_y, k=k_eye, dt=dt
            )
            self._pose_breath = self._smooth_to(
                float(getattr(self, "_pose_breath", 0.5) or 0.5), breath, k=k_breath, dt=dt
            )

            for pid, val in (
                ("ParamAngleX", self._pose_angle_x),
                ("ParamAngleY", self._pose_angle_y),
                ("ParamAngleZ", self._pose_angle_z),
                ("ParamBodyAngleX", self._pose_body_x),
                ("ParamBodyAngleY", self._pose_body_y),
                ("ParamBodyAngleZ", self._pose_body_z),
                ("ParamBreath", self._pose_breath),
                ("ParamEyeBallX", self._pose_eye_x),
                ("ParamEyeBallY", self._pose_eye_y),
            ):
                self._set_param_cached(setter, pid, float(val), w)

            # Micro facial movement: update at a lower cadence to save CPU while keeping the
            # avatar feeling alive (only when we can blend via weights).
            if supports_weight and now_f:
                try:
                    due = now_f >= float(getattr(self, "_micro_params_next_t", 0.0) or 0.0)
                except Exception:
                    due = True
                if due:
                    self._micro_params_next_t = now_f + 0.09  # ~11Hz
                    try:
                        brow = 0.12 * math.sin(tau * 0.07 * t + 1.1) + 0.03 * math.sin(
                            tau * 0.19 * t
                        )
                        brow += 0.02 * float(getattr(self, "_noise_ay", 0.0) or 0.0)
                        brow = max(-1.0, min(1.0, float(brow)))
                        self._set_param_cached(setter, "ParamBrowLY", brow, 0.28)
                        self._set_param_cached(setter, "ParamBrowRY", brow, 0.28)
                    except Exception:
                        pass
                    try:
                        lv2 = float(getattr(self, "_lipsync_value", 0.0) or 0.0)
                    except Exception:
                        lv2 = 0.0
                    try:
                        eye_smile = max(0.0, min(1.0, 0.10 + 0.55 * lv2))
                        self._set_param_cached(setter, "ParamEyeSmile", float(eye_smile), 0.22)
                    except Exception:
                        pass

    def _apply_vtuber_blink(self, now: float, setter) -> None:
        if self._vtuber_blink_supported is False:
            return

        if not now:
            return

        try:
            now_f = float(now)
        except Exception:
            return

        # Schedule next blink if we're idle.
        if self._vtuber_blink_end_t <= 0.0 and now_f >= float(
            getattr(self, "_vtuber_blink_next_t", 0.0) or 0.0
        ):
            close_s = 0.055
            open_s = 0.095
            hold_s = float(getattr(self, "_vtuber_blink_hold_s", 0.018) or 0.018)
            self._vtuber_blink_start_t = now_f
            self._vtuber_blink_end_t = now_f + close_s + hold_s + open_s

        open_v = 1.0
        if self._vtuber_blink_end_t > 0.0:
            close_s = 0.055
            open_s = 0.095
            hold_s = float(getattr(self, "_vtuber_blink_hold_s", 0.018) or 0.018)
            t = max(0.0, now_f - float(getattr(self, "_vtuber_blink_start_t", now_f)))

            def _smoothstep(x: float) -> float:
                x = max(0.0, min(1.0, float(x)))
                return x * x * (3.0 - 2.0 * x)

            if t < close_s:
                p = _smoothstep(t / close_s)
                open_v = 1.0 - p
            elif t < close_s + hold_s:
                open_v = 0.0
            else:
                p = _smoothstep((t - close_s - hold_s) / max(1e-6, open_s))
                open_v = p

            if now_f >= float(getattr(self, "_vtuber_blink_end_t", 0.0) or 0.0):
                self._vtuber_blink_end_t = 0.0
                self._vtuber_blink_start_t = 0.0
                # Natural variation: occasionally do a quick double-blink.
                if random.random() < 0.18:
                    self._vtuber_blink_next_t = now_f + random.uniform(0.22, 0.45)
                else:
                    self._vtuber_blink_next_t = now_f + random.uniform(2.4, 5.2)
                open_v = 1.0

        # Avoid writing eye-open every frame when fully open (saves per-frame param calls).
        try:
            last = getattr(self, "_vtuber_eye_open_last", None)
            if (
                last is not None
                and self._vtuber_blink_end_t <= 0.0
                and abs(float(open_v) - float(last)) < 0.01
            ):
                return
        except Exception:
            pass
        self._vtuber_eye_open_last = float(open_v)

        # Apply blink to common parameters. Some models use only one eye parameter; try both.
        ok = 0
        ok += 1 if self._set_param_cached(setter, "ParamEyeLOpen", float(open_v), 1.0) else 0
        ok += 1 if self._set_param_cached(setter, "ParamEyeROpen", float(open_v), 1.0) else 0
        if ok <= 0:
            self._vtuber_blink_supported = False
        else:
            self._vtuber_blink_supported = True

    def _apply_lipsync(self, dt_s: float) -> None:
        if self._model is None:
            return

        if self._lipsync_supported is False:
            return

        target = float(getattr(self, "_lipsync_target", 0.0) or 0.0)
        value = float(getattr(self, "_lipsync_value", 0.0) or 0.0)
        try:
            dt = max(0.0, min(0.1, float(dt_s)))
        except Exception:
            dt = 1.0 / 30.0

        # Smooth: fast open, slightly slower close for a more "vtuber" mouth feel.
        k_open = 16.0
        k_close = 10.0
        k = k_open if target > value else k_close
        try:
            alpha = 1.0 - math.exp(-k * dt)
        except Exception:
            alpha = min(1.0, dt * 12.0)
        value = value + (target - value) * max(0.0, min(1.0, alpha))
        self._lipsync_value = max(0.0, min(1.0, float(value)))

        setter = self._param_setter
        if setter is None:
            setter = self._discover_param_setter()
            self._param_setter = setter
            self._lipsync_supported = bool(setter is not None)
        if setter is None:
            return

        # Common Cubism 3 params:
        # - ParamMouthOpenY: [0..1] open amount
        # - ParamMouthForm: [-1..1] smile/frown; optionally blend lightly if setter supports weight
        try:
            setter("ParamMouthOpenY", float(self._lipsync_value), 1.0)
        except Exception:
            self._lipsync_supported = False
            return
        # Keep `ParamMouthForm` mostly free so expressions remain visible. When the setter supports
        # weights, we can blend a tiny smile during speech to look more "alive".
        try:
            supports_weight = bool(getattr(self, "_param_setter_supports_weight", False))
        except Exception:
            supports_weight = False
        if supports_weight:
            try:
                lv = float(getattr(self, "_lipsync_value", 0.0) or 0.0)
            except Exception:
                lv = 0.0
            # 0.25..0.65 mild smile range while speaking.
            form = 0.25 + 0.40 * max(0.0, min(1.0, float(lv)))
            form = max(-1.0, min(1.0, float(form)))
            try:
                self._set_param_cached(setter, "ParamMouthForm", float(form), 0.35)
            except Exception:
                pass

    def _discover_param_setter(self):
        """Best-effort discover a parameter setter on the current live2d-py model."""
        model = self._model
        if model is None:
            return None

        objs: list[Any] = []
        try:
            objs.append(model)
        except Exception:
            pass

        for attr in ("model", "_model", "_impl", "_core", "cubism_model"):
            try:
                obj = getattr(model, attr, None)
                if obj is not None and obj not in objs:
                    objs.append(obj)
            except Exception:
                pass

        try:
            get_model = getattr(model, "GetModel", None)
            if callable(get_model):
                obj = get_model()
                if obj is not None and obj not in objs:
                    objs.append(obj)
        except Exception:
            pass

        test_id = "ParamMouthOpenY"

        # 1) Index based (prefer: avoids per-frame id lookups once indices are cached).
        for obj in objs:
            try:
                get_idx = getattr(obj, "GetParameterIndex", None)
                set_by_idx = getattr(obj, "SetParameterValueByIndex", None)
                if not callable(get_idx) or not callable(set_by_idx):
                    continue
                idx = int(get_idx(test_id))
                try:
                    set_by_idx(idx, 0.0)
                    self._param_setter_supports_weight = False
                    cache = self._param_index_cache
                    sentinel = object()

                    def _setter(
                        pid: str, v: float, w: float = 1.0, *, _get=get_idx, _set=set_by_idx
                    ) -> None:
                        key = str(pid or "")
                        if not key:
                            raise KeyError("empty param id")
                        cached = cache.get(key, sentinel)
                        if cached is sentinel:
                            i = int(_get(key))
                            if i < 0:
                                raise KeyError(key)
                            cache[key] = int(i)
                            cached = i
                        _set(int(cached), float(v))

                    return _setter
                except TypeError:
                    set_by_idx(idx, 0.0, 1.0)
                    self._param_setter_supports_weight = True
                    cache = self._param_index_cache
                    sentinel = object()

                    def _setter(
                        pid: str, v: float, w: float = 1.0, *, _get=get_idx, _set=set_by_idx
                    ) -> None:
                        key = str(pid or "")
                        if not key:
                            raise KeyError("empty param id")
                        cached = cache.get(key, sentinel)
                        if cached is sentinel:
                            i = int(_get(key))
                            if i < 0:
                                raise KeyError(key)
                            cache[key] = int(i)
                            cached = i
                        _set(int(cached), float(v), float(w))

                    return _setter
            except Exception:
                continue

        # 2) Direct setter by id.
        for obj in objs:
            for name in ("SetParameterValueById", "SetParameterValueByID", "SetParameterValue"):
                try:
                    fn = getattr(obj, name, None)
                    if not callable(fn):
                        continue

                    try:
                        fn(test_id, 0.0)
                        self._param_setter_supports_weight = False
                        return lambda pid, v, w=1.0, _fn=fn: _fn(pid, float(v))
                    except TypeError:
                        try:
                            fn(test_id, 0.0, 1.0)
                            self._param_setter_supports_weight = True
                            return lambda pid, v, w=1.0, _fn=fn: _fn(pid, float(v), float(w))
                        except Exception:
                            continue
                except Exception:
                    continue

        return None

    def _end_pan(self) -> None:
        try:
            if self._panning:
                self._panning = False
                self._pan_button = None
                self._pan_last_pos = None
                self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))
        except Exception:
            pass
        self._pan_candidate = False
        self._pan_candidate_pos = None

    def _start_pan(self, pos: QPointF, button: Qt.MouseButton) -> None:
        if self._interaction_locked:
            return
        self._pan_candidate = False
        self._pan_candidate_pos = None
        self._panning = True
        self._pan_button = button
        self._pan_last_pos = pos
        try:
            self.setCursor(QCursor(Qt.CursorShape.ClosedHandCursor))
        except Exception:
            pass
        self._boost_fps()

    def _request_view_apply(self) -> None:
        self._view_apply_pending = True
        try:
            self.update()
        except Exception:
            pass

    def _find_dropped_model_json(self, src: Path) -> Path | None:
        try:
            p = Path(src)
        except Exception:
            return None
        if not p.exists():
            return None
        if p.is_file():
            if p.suffix.lower() == ".json" and p.name.lower().endswith(".model3.json"):
                return p
            return None
        # Directory: pick the first `.model3.json` in that directory (no recursion).
        try:
            models = sorted(p.glob("*.model3.json"))
        except Exception:
            models = []
        return models[0] if models else None

    def _boost_fps(self, duration_ms: int = 1200) -> None:
        if self._paused or not self._ready:
            return
        try:
            self._fps_boost_reset.start(max(200, int(duration_ms)))
            self._apply_tick_interval()
        except Exception:
            pass

    def _restore_fps_normal(self) -> None:
        if self._paused or not self._ready:
            return
        try:
            self._apply_tick_interval()
        except Exception:
            pass

    def _desired_tick_interval_ms(self) -> int:
        base = self._tick_ms_boost if self._fps_boost_reset.isActive() else self._tick_ms_normal
        try:
            mode = int(getattr(self, "_fps_load_mode", 0) or 0)
        except Exception:
            mode = 0
        if mode >= 2:
            return int(max(int(base), int(self._tick_ms_heavy)))
        if mode == 1:
            return int(max(int(base), int(self._tick_ms_medium)))
        return int(base)

    def _desired_tick_timer_type(self) -> Qt.TimerType:
        """Choose a timer type that balances smoothness and overhead.

        On Windows, PreciseTimer may use a higher-resolution timer source and can be more expensive.
        When the UI is under heavy load and we are already reducing FPS, a coarse timer can reduce
        scheduling overhead without harming perceived smoothness.
        """

        try:
            interval = int(self._desired_tick_interval_ms())
        except Exception:
            interval = int(self._tick_ms_normal)
        try:
            mode = int(getattr(self, "_fps_load_mode", 0) or 0)
        except Exception:
            mode = 0

        if interval <= 20:
            return Qt.TimerType.PreciseTimer
        if mode >= 2:
            return Qt.TimerType.CoarseTimer
        return Qt.TimerType.PreciseTimer

    def _apply_tick_interval(self) -> None:
        if self._paused or not self._ready:
            return
        try:
            interval = int(self._desired_tick_interval_ms())
        except Exception:
            interval = int(self._tick_ms_normal)
        try:
            try:
                timer_type = self._desired_tick_timer_type()
                if getattr(self._tick_timer, "timerType", None) is not None:
                    if self._tick_timer.timerType() != timer_type:
                        self._tick_timer.setTimerType(timer_type)
            except Exception:
                pass
            self._tick_timer.setInterval(int(interval))
        except Exception:
            pass

    def _maybe_adapt_fps_under_load(self, now: float, dt_s: float, render_ms: float) -> None:
        """Adaptive FPS: keep the UI responsive under load by reducing Live2D FPS temporarily.

        This is intentionally conservative and uses hysteresis to avoid oscillation.
        """
        if self._paused or not self._ready or (not now):
            return
        if render_ms <= 0.0:
            return

        try:
            self._render_ms_last = float(render_ms)
            ema = float(getattr(self, "_render_ms_ema", 0.0) or 0.0)
            if ema <= 0.0:
                ema = float(render_ms)
            else:
                ema = 0.85 * float(ema) + 0.15 * float(render_ms)
            self._render_ms_ema = float(ema)
        except Exception:
            return

        try:
            last_eval = float(getattr(self, "_fps_load_last_eval_t", 0.0) or 0.0)
        except Exception:
            last_eval = 0.0
        if now - last_eval < 0.35:
            return
        self._fps_load_last_eval_t = float(now)

        try:
            dt_ms = max(0.0, float(dt_s) * 1000.0)
        except Exception:
            dt_ms = 0.0

        # Suggested mode from current measurements.
        suggested = 0
        if float(ema) > 28.0 or dt_ms > 90.0:
            suggested = 2
        elif float(ema) > 20.0 or dt_ms > 60.0:
            suggested = 1

        try:
            current = int(getattr(self, "_fps_load_mode", 0) or 0)
        except Exception:
            current = 0
        try:
            hold_until = float(getattr(self, "_fps_load_hold_until", 0.0) or 0.0)
        except Exception:
            hold_until = 0.0

        # Escalate quickly; downshift only after hold time and good metrics.
        if suggested > current:
            self._fps_load_mode = int(suggested)
            self._fps_load_hold_until = float(now + 1.25)
            try:
                if suggested == 2:
                    logger.debug(
                        "Live2D FPS: heavy mode (ema=%.1fms, dt=%.1fms)", float(ema), float(dt_ms)
                    )
                else:
                    logger.debug(
                        "Live2D FPS: medium mode (ema=%.1fms, dt=%.1fms)", float(ema), float(dt_ms)
                    )
            except Exception:
                pass
            self._apply_tick_interval()
            return

        if suggested < current:
            if now < hold_until:
                return
            # Hysteresis thresholds for de-escalation.
            if current >= 2:
                if float(ema) < 22.0 and dt_ms < 70.0:
                    self._fps_load_mode = int(suggested)
                    self._fps_load_hold_until = float(now + 0.6)
                    try:
                        logger.debug(
                            "Live2D FPS: leave heavy (ema=%.1fms, dt=%.1fms)",
                            float(ema),
                            float(dt_ms),
                        )
                    except Exception:
                        pass
                    self._apply_tick_interval()
            elif current == 1:
                if float(ema) < 18.0 and dt_ms < 55.0:
                    self._fps_load_mode = int(suggested)
                    self._fps_load_hold_until = float(now + 0.6)
                    try:
                        logger.debug(
                            "Live2D FPS: leave medium (ema=%.1fms, dt=%.1fms)",
                            float(ema),
                            float(dt_ms),
                        )
                    except Exception:
                        pass
                    self._apply_tick_interval()
            return

        # Keep degraded mode a bit longer while still under load.
        if current:
            try:
                self._fps_load_hold_until = max(float(hold_until), float(now + 0.75))
            except Exception:
                pass

    def _apply_default_view(self, ww: int, hh: int) -> None:
        """Apply a pleasant default view (scale/offset) for the current viewport."""

        if self._model is None:
            return

        if not self._auto_view_enabled:
            return

        try:
            # Use logical pixels for heuristics so HiDPI doesn't change framing.
            logical_w = float(self.width() or 0)
            logical_h = float(self.height() or 0)
            if logical_w <= 0 or logical_h <= 0:
                logical_w = float(ww)
                logical_h = float(hh)
            aspect = float(logical_w) / float(max(1.0, logical_h))
        except Exception:
            aspect = 0.5

        def clamp(x: float, lo: float, hi: float) -> float:
            return max(lo, min(hi, float(x)))

        # Height matters a lot: a short viewport shouldn't be aggressively zoomed-in.
        height_factor = clamp((float(logical_h) - 520.0) / 220.0, 0.0, 1.0)
        aspect_factor = clamp((float(aspect) - 0.55) / 0.45, 0.0, 1.0)

        if self._view_mode == self.VIEW_MODE_PORTRAIT:
            base_scale = 1.12 + 0.38 * height_factor + 0.14 * aspect_factor
            base_offset_x = 0.0
            base_offset_y = -0.10 - 0.10 * height_factor
        else:
            # Full-body framing: conservative zoom by default.
            base_scale = 0.90 + 0.20 * height_factor + 0.06 * aspect_factor
            base_offset_x = 0.0
            base_offset_y = -0.03 - 0.06 * height_factor

        scale = float(base_scale) * float(self._user_scale_mul)
        offset_x = float(base_offset_x) + float(self._user_offset_x)
        offset_y = float(base_offset_y) + float(self._user_offset_y)

        scale = clamp(scale, 0.55, 2.2)
        offset_x = clamp(offset_x, -0.8, 0.8)
        offset_y = clamp(offset_y, -0.8, 0.6)

        try:
            if hasattr(self._model, "SetScale"):
                self._model.SetScale(float(scale))
        except Exception:
            pass
        try:
            if hasattr(self._model, "SetOffset"):
                self._model.SetOffset(float(offset_x), float(offset_y))
        except Exception:
            pass

    def _destroy_model(self) -> None:
        if self._model is None:
            return
        try:
            if hasattr(self._model, "DestroyRenderer"):
                self._model.DestroyRenderer()
        except Exception:
            pass
        try:
            self._base_expression_id = None
            self._base_expression_mode = ""
            self._state_expression_id = None
            self._state_expression_mode = ""
            self._state_expression_expire_t = 0.0
            self._state_expression_event = ""
            self._model_expression_ids = []
        except Exception:
            pass
        try:
            self._expr_files_cache_dir = None
            self._expr_files_cache_mtime = 0.0
            self._expr_files_cache_dir_mtime = 0.0
            self._expr_files_cache_model_json_mtime = 0.0
            self._expr_files_cache = []
            self._expr_candidates_cache = {}
        except Exception:
            pass
        self._model = None

    def _refresh_model_expression_ids(self) -> None:
        """Best-effort cache of expression IDs available on the loaded model."""
        model = self._model
        if model is None:
            self._model_expression_ids = []
            return

        expr_ids: list[str] = []
        try:
            getter = getattr(model, "GetExpressionIds", None)
            if callable(getter):
                raw = getter() or []
                if isinstance(raw, (list, tuple, set)):
                    expr_ids = [str(x) for x in raw if str(x)]
        except Exception:
            expr_ids = []

        if not expr_ids:
            try:
                getter = getattr(model, "GetExpressions", None)
                if callable(getter):
                    raw = getter() or []
                    if isinstance(raw, dict):
                        expr_ids = [str(k) for k in raw.keys() if str(k)]
                    elif isinstance(raw, (list, tuple, set)):
                        tmp: list[str] = []
                        for item in raw:
                            if isinstance(item, str):
                                tmp.append(item)
                            elif (
                                isinstance(item, (list, tuple))
                                and item
                                and isinstance(item[0], str)
                            ):
                                tmp.append(item[0])
                        expr_ids = [str(x) for x in tmp if str(x)]
            except Exception:
                expr_ids = []

        try:
            # Deduplicate while preserving order (stable for random choice).
            self._model_expression_ids = list(dict.fromkeys(expr_ids))
        except Exception:
            self._model_expression_ids = list(expr_ids)

    def _refresh_expression_cache(self) -> None:
        model_json = self._model_json
        if model_json is None:
            return
        try:
            model_dir = Path(model_json).parent
        except Exception:
            return
        try:
            now = float(time.monotonic())
        except Exception:
            now = 0.0

        try:
            src_model_json = Path(model_json)
        except Exception:
            return

        # Cache invalidation based on filesystem mtimes (avoid periodic disk IO/JSON parsing
        # on the GUI thread).
        model_json_mtime = 0.0
        dir_mtime = 0.0
        try:
            model_json_mtime = float(src_model_json.stat().st_mtime)
        except Exception:
            model_json_mtime = 0.0
        try:
            dir_mtime = float(model_dir.stat().st_mtime)
        except Exception:
            dir_mtime = 0.0

        try:
            if (
                self._expr_files_cache_dir is not None
                and Path(self._expr_files_cache_dir) == model_dir
            ):
                if model_json_mtime > 0.0 and dir_mtime > 0.0:
                    if (
                        float(getattr(self, "_expr_files_cache_model_json_mtime", 0.0) or 0.0)
                        == model_json_mtime
                        and float(getattr(self, "_expr_files_cache_dir_mtime", 0.0) or 0.0)
                        == dir_mtime
                    ):
                        return
                else:
                    # Fallback: if stat fails (rare), use a conservative TTL to avoid
                    # hot-loop refresh.
                    if (now - float(self._expr_files_cache_mtime or 0.0)) < 10.0:
                        return
        except Exception:
            pass

        files: list[str] = []
        candidates: dict[str, list[str]] = {}

        try:
            exp_paths = sorted(model_dir.glob("*.exp3.json"))
        except Exception:
            exp_paths = []
        exp_name_set = set()
        try:
            exp_name_set = {p.name for p in exp_paths}
        except Exception:
            exp_name_set = set()

        # Prefer explicit mapping from model3.json if present.
        try:
            base = json.loads(src_model_json.read_text(encoding="utf-8"))
        except Exception:
            base = None

        refs = base.get("FileReferences") if isinstance(base, dict) else None
        exprs = refs.get("Expressions") if isinstance(refs, dict) else None
        if isinstance(exprs, list) and exprs:
            base_count = len(exprs)
            included: set[str] = set()
            for idx, entry in enumerate(exprs, start=1):
                if not isinstance(entry, dict):
                    continue
                file_ref = entry.get("File")
                if not isinstance(file_ref, str) or not file_ref:
                    continue
                try:
                    fname = Path(file_ref).name
                except Exception:
                    fname = str(file_ref)
                if not fname:
                    continue
                if exp_name_set and fname not in exp_name_set:
                    continue
                name = entry.get("Name") if isinstance(entry.get("Name"), str) else None
                cand: list[str] = []
                if isinstance(name, str) and name.strip():
                    cand.append(name.strip())
                # Sanitizer fallback assigns `expr_{idx:02d}` when the name is missing or non-ASCII.
                cand.append(f"expr_{idx:02d}")
                candidates[fname] = cand
                files.append(fname)
                included.add(fname)

            # Include any extra exp files not referenced in model3.json.
            # (Matches sanitizer behavior.)
            extra_idx = base_count + 1
            for p in exp_paths:
                try:
                    if p.name in included:
                        continue
                except Exception:
                    continue
                candidates[p.name] = [f"expr_{extra_idx:02d}"]
                files.append(p.name)
                extra_idx += 1

        # Fallback: model3.json may omit Expressions; mimic sanitizer ordering for *.exp3.json.
        if not files:
            files = [p.name for p in exp_paths]
            for idx, fname in enumerate(files, start=1):
                candidates[fname] = [f"expr_{idx:02d}"]

        try:
            self._expr_files_cache_dir = model_dir
            self._expr_files_cache = list(files)
            self._expr_candidates_cache = dict(candidates)
            self._expr_files_cache_mtime = float(now)
            self._expr_files_cache_dir_mtime = float(dir_mtime)
            self._expr_files_cache_model_json_mtime = float(model_json_mtime)
        except Exception:
            pass

    def _prepare_ascii_model_json(self, src_model_json: Path) -> Path:
        return _sanitize_model3_json_for_cubism(src_model_json)

    def _resolve_expression_id_candidates_for_file(
        self, src_model_json: Path, filename: str
    ) -> list[str]:
        filename = str(filename or "").strip()
        if not filename:
            return []

        # Hot path: resolve from a small cache built from `model3.json`.
        try:
            if self._model_json is not None and Path(src_model_json) == Path(self._model_json):
                self._refresh_expression_cache()
                cached = self._expr_candidates_cache.get(filename)
                if cached:
                    return list(cached)
                # If the model3.json has an explicit Expressions list and the file isn't referenced
                # don't guess an ID (it likely won't exist on the loaded model anyway).
                if self._expr_candidates_cache:
                    return []
        except Exception:
            pass

        src_model_json = Path(src_model_json)
        model_dir = src_model_json.parent

        # 1) Prefer explicit mapping from model3.json if present.
        try:
            base = json.loads(src_model_json.read_text(encoding="utf-8"))
        except Exception:
            base = None

        refs = base.get("FileReferences") if isinstance(base, dict) else None
        exprs = refs.get("Expressions") if isinstance(refs, dict) else None
        if isinstance(exprs, list):
            for idx, entry in enumerate(exprs, start=1):
                if not isinstance(entry, dict):
                    continue
                file_ref = entry.get("File")
                if not isinstance(file_ref, str) or not file_ref:
                    continue
                try:
                    if Path(file_ref).name != filename:
                        continue
                except Exception:
                    if str(file_ref) != filename:
                        continue
                name = entry.get("Name") if isinstance(entry.get("Name"), str) else None
                candidates: list[str] = []
                if isinstance(name, str) and name.strip():
                    candidates.append(name.strip())
                # Sanitizer fallback assigns `expr_{idx:02d}` when the name is missing or non-ASCII.
                candidates.append(f"expr_{idx:02d}")
                return candidates

        # 2) Fallback: model3.json may omit Expressions; mimic sanitizer ordering for *.exp3.json.
        try:
            exp_files = sorted(model_dir.glob("*.exp3.json"))
        except Exception:
            exp_files = []
        for idx, p in enumerate(exp_files, start=1):
            try:
                if p.name == filename:
                    return [f"expr_{idx:02d}"]
            except Exception:
                continue
        return []

    def _apply_default_expression(self, src_model_json: Path) -> None:
        model = self._model
        if model is None:
            return
        expr_file = str(getattr(self, "_default_expression_file", "") or "").strip()
        if not expr_file:
            return
        if not (hasattr(model, "AddExpression") or hasattr(model, "SetExpression")):
            return

        # Prefer additive base expression so transient state expressions can stack naturally.
        try:
            if hasattr(model, "ResetExpressions"):
                model.ResetExpressions()
        except Exception:
            pass
        try:
            if hasattr(model, "ResetExpression"):
                model.ResetExpression()
        except Exception:
            pass

        candidates = self._resolve_expression_id_candidates_for_file(
            Path(src_model_json), expr_file
        )
        if not candidates:
            return
        for exp_id in candidates:
            try:
                if hasattr(model, "AddExpression") and hasattr(model, "RemoveExpression"):
                    model.AddExpression(str(exp_id))
                    self._base_expression_mode = "add"
                else:
                    model.SetExpression(str(exp_id))
                    self._base_expression_mode = "set"
                self._base_expression_id = str(exp_id)
                self._state_expression_id = None
                self._state_expression_mode = ""
                self._state_expression_expire_t = 0.0
                self._state_expression_event = ""
                self._boost_fps(900)
                return
            except Exception:
                continue

    def _list_expression_files(self) -> list[str]:
        if self._model_json is None:
            return []
        try:
            self._refresh_expression_cache()
        except Exception:
            pass
        try:
            return list(self._expr_files_cache)
        except Exception:
            return []

    def _resolve_expression_file_for_event(self, event: str) -> str | None:
        event = str(event or "").strip()
        if not event:
            return None
        available = self._list_expression_files()
        if not available:
            return None
        return _choose_expression_file_for_event(event, available)

    def apply_state_event(
        self,
        event: str,
        *,
        intensity: float = 0.7,
        hold_s: float | None = None,
        source: str = "",
    ) -> bool:
        """Apply a temporary expression based on a semantic state event.

        The base/persistent expression is only changed by user actions.
        State events are transient and will revert back to the base expression after a short TTL.
        """
        if not self._ready or self._model is None:
            return False
        model = self._model
        if self._model_json is None:
            return False
        if not (hasattr(model, "AddExpression") or hasattr(model, "SetExpression")):
            return False

        gesture_applied = False
        try:
            gk = _gesture_kind_for_event(event)
            if gk:
                gesture_applied = bool(
                    self._vtuber_force_gesture(gk, intensity=float(intensity), duration_s=hold_s)
                )
        except Exception:
            gesture_applied = False

        file_name = self._resolve_expression_file_for_event(event)
        if not file_name:
            return bool(gesture_applied)

        candidates = self._resolve_expression_id_candidates_for_file(
            Path(self._model_json), file_name
        )
        if not candidates:
            return bool(gesture_applied)

        try:
            now = float(time.monotonic())
        except Exception:
            now = 0.0

        try:
            iv = float(intensity)
        except Exception:
            iv = 0.7
        iv = max(0.0, min(1.0, iv))
        if hold_s is None:
            # 2.8s .. 7.5s based on intensity.
            hold_s = 2.8 + 4.7 * iv
        try:
            ttl = max(1.2, min(10.0, float(hold_s)))
        except Exception:
            ttl = 4.8

        # If the previous state expired but the next tick hasn't run yet, clear it now to avoid
        # getting "stuck" in an old SetExpression state.
        try:
            expire = float(getattr(self, "_state_expression_expire_t", 0.0) or 0.0)
        except Exception:
            expire = 0.0
        if expire > 0.0 and now and now >= expire:
            try:
                self._maybe_restore_base_expression(float(now))
            except Exception:
                pass

        # If the same state is already active, just extend TTL (avoid reapplying expression).
        try:
            if (
                self._state_expression_id is not None
                and str(self._state_expression_id) in candidates
                and float(self._state_expression_expire_t or 0.0) > now
            ):
                self._state_expression_expire_t = max(
                    float(self._state_expression_expire_t), now + ttl
                )
                self._state_expression_last_apply_t = float(now)
                return True
        except Exception:
            pass

        # Prefer additive state expressions when possible so the base expression stays stable.
        # If a previous `SetExpression` override is still active, clear it.
        # This ensures `AddExpression` takes effect.
        try:
            active_id = str(getattr(self, "_state_expression_id", "") or "").strip()
            active_mode = str(getattr(self, "_state_expression_mode", "") or "")
        except Exception:
            active_id = ""
            active_mode = ""

        try:
            base_id = str(getattr(self, "_base_expression_id", "") or "").strip()
            base_mode = str(getattr(self, "_base_expression_mode", "") or "")
        except Exception:
            base_id = ""
            base_mode = ""

        can_add = hasattr(model, "AddExpression") and hasattr(model, "RemoveExpression")
        if can_add:
            try:
                if active_id and active_mode == "set" and hasattr(model, "ResetExpression"):
                    model.ResetExpression()
            except Exception:
                pass
            try:
                if active_id and active_mode == "add":
                    if not (base_mode == "add" and base_id and active_id == base_id):
                        model.RemoveExpression(active_id)
            except Exception:
                pass

            for exp_id in candidates:
                try:
                    eid = str(exp_id)
                except Exception:
                    continue
                if base_mode == "add" and base_id and eid == base_id:
                    # Avoid turning the persistent base expression into a transient state.
                    return True
                try:
                    model.AddExpression(eid)
                    self._state_expression_id = eid
                    self._state_expression_mode = "add"
                    self._state_expression_expire_t = float(now + ttl)
                    self._state_expression_event = str(event or source or "")
                    self._state_expression_last_apply_t = float(now)
                    self._boost_fps(1200)
                    self.update()
                    return True
                except Exception:
                    continue

        # Fallback: override via SetExpression and restore base on TTL.
        try:
            if active_id and active_mode == "add" and hasattr(model, "RemoveExpression"):
                if not (base_mode == "add" and base_id and active_id == base_id):
                    model.RemoveExpression(active_id)
        except Exception:
            pass
        for exp_id in candidates:
            try:
                model.SetExpression(str(exp_id))
                self._state_expression_id = str(exp_id)
                self._state_expression_mode = "set"
                self._state_expression_expire_t = float(now + ttl)
                self._state_expression_event = str(event or source or "")
                self._state_expression_last_apply_t = float(now)
                self._boost_fps(1200)
                self.update()
                return True
            except Exception:
                continue
        return False

    def request_state_event(
        self,
        event: str,
        *,
        intensity: float = 0.7,
        hold_s: float | None = None,
        source: str = "",
    ) -> None:
        """Thread-safe wrapper for applying a state event.

        This emits a Qt signal so calls from worker threads are queued onto the GUI thread.
        """
        try:
            hs = float(hold_s) if hold_s is not None else -1.0
        except Exception:
            hs = -1.0
        try:
            self.state_event_requested.emit(
                str(event), float(intensity), float(hs), str(source or "")
            )
        except Exception:
            pass

    def _on_state_event_requested(
        self, event: str, intensity: float, hold_s: float, source: str
    ) -> None:
        try:
            hs = float(hold_s)
        except Exception:
            hs = -1.0
        self.apply_state_event(
            str(event),
            intensity=float(intensity),
            hold_s=None if hs < 0 else float(hs),
            source=str(source or ""),
        )

    def _maybe_restore_base_expression(self, now: float) -> None:
        if self._model is None:
            return
        if not (
            hasattr(self._model, "RemoveExpression")
            or hasattr(self._model, "ResetExpression")
            or hasattr(self._model, "SetExpression")
        ):
            return
        try:
            expire = float(getattr(self, "_state_expression_expire_t", 0.0) or 0.0)
        except Exception:
            expire = 0.0
        if expire <= 0.0 or now < expire:
            return
        if self._state_expression_id is None:
            self._state_expression_expire_t = 0.0
            return

        state_id = str(getattr(self, "_state_expression_id", "") or "").strip()
        mode = str(getattr(self, "_state_expression_mode", "") or "")
        self._state_expression_id = None
        self._state_expression_mode = ""
        self._state_expression_expire_t = 0.0
        self._state_expression_event = ""

        try:
            base_id = str(getattr(self, "_base_expression_id", "") or "").strip()
            base_mode = str(getattr(self, "_base_expression_mode", "") or "")
        except Exception:
            base_id = ""
            base_mode = ""

        if state_id and mode == "add" and hasattr(self._model, "RemoveExpression"):
            try:
                if not (base_mode == "add" and base_id and state_id == base_id):
                    self._model.RemoveExpression(state_id)
            except Exception:
                pass
            try:
                self._boost_fps(700)
            except Exception:
                pass
            try:
                self.update()
            except Exception:
                pass
            return

        # If our base expression is additive, clearing the SetExpression override is enough
        # to reveal it again.
        if base_mode == "add" and hasattr(self._model, "ResetExpression"):
            try:
                self._model.ResetExpression()
            except Exception:
                return
            try:
                self._boost_fps(700)
            except Exception:
                pass
            try:
                self.update()
            except Exception:
                pass
            return

        if not base_id:
            try:
                self._apply_default_expression(
                    Path(self._model_json) if self._model_json is not None else Path()
                )
            except Exception:
                return
        else:
            try:
                self._model.SetExpression(base_id)
            except Exception:
                return

        try:
            self._boost_fps(700)
        except Exception:
            pass
        try:
            self.update()
        except Exception:
            pass
