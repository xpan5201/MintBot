from __future__ import annotations

import json
import re


def infer_state_event_from_text(text: str) -> tuple[str, float] | None:
    """Infer a semantic Live2D state event from free-form text (best-effort).

    This is intentionally lightweight and local-only (no LLM calls). It's used by the GUI to
    provide real-time expression feedback for Live2D. If no strong keyword signal is found,
    callers can fall back to higher-level emotion systems.
    """

    msg = str(text or "").strip()
    if not msg:
        return None

    # Hot path: cap analysis length to keep GUI snappy on very long responses.
    if len(msg) > 1200:
        msg = msg[:1200]

    lower = msg.lower()

    neg_prefixes = (
        "不",
        "别",
        "不要",
        "不用",
        "无需",
        "勿",
        "别再",
        "别太",
        "别这么",
        "不太",
        "没必要",
        "没事别",
    )

    def _is_negated(start: int) -> bool:
        # Look a few chars behind the match start; strip whitespace for robustness.
        left = msg[max(0, start - 4) : start]
        left = re.sub(r"\s+", "", left)
        if any(left.endswith(p) for p in neg_prefixes if p):
            return True
        # Handle duplicated characters like "不要哭哭" where the 2nd "哭" should still be negated.
        try:
            if start > 0 and msg[start - 1] == msg[start]:
                return _is_negated(start - 1)
        except Exception:
            pass
        return False

    def _last_non_negated(token: str) -> int | None:
        token = str(token or "")
        if not token:
            return None
        if token.isascii():
            hay = lower
            needle = token.lower()
        else:
            hay = msg
            needle = token
        pos = hay.find(needle)
        last_ok: int | None = None
        while pos != -1:
            if not _is_negated(pos):
                last_ok = pos
            pos = hay.find(needle, pos + 1)
        return last_ok

    # (event_key, default_intensity, keyword tokens)
    categories: list[tuple[str, float, tuple[str, ...]]] = [
        ("angry", 0.92, ("生气", "气死", "气炸", "恼", "火大", "烦", "凶", "😡", "🤬")),
        ("shy", 0.86, ("害羞", "脸红", "不好意思", "///", "(///", "对不起", "抱歉")),
        ("dizzy", 0.82, ("头晕", "眩晕", "晕", "转圈", "晕了", "晕乎乎")),
        ("love", 0.84, ("心心眼", "喜欢", "爱你", "亲亲", "抱抱", "贴贴", "么么", "❤", "♡", "💕")),
        ("sad", 0.80, ("哭哭", "难过", "伤心", "委屈", "呜呜", "T_T", "QAQ", "😭")),
        ("surprise", 0.72, ("星星眼", "惊讶", "惊呆", "哇", "诶", "欸")),
    ]

    default_intensity = {str(k): float(i) for k, i, _ in categories}
    found: dict[str, int] = {}
    best: tuple[int, float, str] | None = None  # (pos, intensity, event_key)
    for key, intensity, tokens in categories:
        last_pos: int | None = None
        for token in tokens:
            pos = _last_non_negated(token)
            if pos is None:
                continue
            if last_pos is None or pos > last_pos:
                last_pos = pos
        if last_pos is None:
            continue
        found[str(key)] = int(last_pos)
        cand = (int(last_pos), float(intensity), str(key))
        if best is None:
            best = cand
            continue
        # Prefer the emotion appearing later in the text; tie-break by intensity.
        if cand[0] > best[0] or (cand[0] == best[0] and cand[1] > best[1]):
            best = cand

    if best is None:
        # Lightweight yes/no gesture inference (only when no emotion signal is present).
        # Keep it conservative to avoid misfiring on longer messages.
        if len(msg) <= 40:
            affirm_tokens = (
                "是的",
                "对",
                "对呀",
                "对的",
                "好",
                "好的",
                "好呀",
                "可以",
                "行",
                "没问题",
                "当然",
                "ok",
                "okay",
                "sure",
            )
            deny_tokens = ("不行", "不是", "不对", "不可以", "不能", "拒绝", "no", "nope")

            last_affirm: int | None = None
            for tok in affirm_tokens:
                pos = _last_non_negated(tok)
                if pos is None:
                    continue
                if last_affirm is None or pos > last_affirm:
                    last_affirm = pos

            last_deny: int | None = None
            for tok in deny_tokens:
                pos = _last_non_negated(tok)
                if pos is None:
                    continue
                if last_deny is None or pos > last_deny:
                    last_deny = pos

            if last_affirm is not None or last_deny is not None:
                # Prefer the gesture appearing later in the text.
                if last_deny is None or (last_affirm is not None and last_affirm > last_deny):
                    return ("nod", 0.65)
                return ("shake", 0.65)

        return None
    _, intensity, key = best
    # Roleplay replies often include affectionate words ("喜欢/抱抱/贴贴").
    # They can override a stronger explicit angry signal inside the same message.
    # Prefer "angry" when it is present (and not negated).
    try:
        if key == "love" and "angry" in found:
            key = "angry"
            intensity = float(default_intensity.get("angry", intensity))
    except Exception:
        pass
    return (key, max(0.0, min(1.0, float(intensity))))


_LIVE2D_DIRECTIVE_PREFIX = "[[live2d:"
_LIVE2D_DIRECTIVE_SUFFIX = "]]"
# Compatibility: some models may emit a single-bracket form (missing one '['/']').
# We keep the double-bracket JSON directive as the recommended/authoritative syntax,
# but accept the single-bracket variant to avoid leaking control tags into the UI.
_LIVE2D_DIRECTIVE_PATTERNS: tuple[tuple[str, str], ...] = (
    (_LIVE2D_DIRECTIVE_PREFIX, _LIVE2D_DIRECTIVE_SUFFIX),
    ("[live2d:", "]"),
)


def _find_next_directive_start(
    low: str, start: int
) -> tuple[int, str, str] | None:  # (pos, prefix, suffix)
    best: tuple[int, str, str] | None = None
    for prefix, suffix in _LIVE2D_DIRECTIVE_PATTERNS:
        pos = low.find(prefix, start)
        if pos == -1:
            continue
        if best is None or pos < best[0]:
            best = (pos, prefix, suffix)
    return best


def _parse_state_event_payload(payload: str) -> tuple[str, float | None, float | None] | None:
    payload = str(payload or "").strip()
    if not payload:
        return None

    def _clamp01(value: object) -> float | None:
        if value is None:
            return None
        try:
            v = float(value)
        except Exception:
            return None
        if not (v == v):  # NaN
            return None
        return max(0.0, min(1.0, float(v)))

    def _clamp_hold_s(value: object) -> float | None:
        if value is None:
            return None
        try:
            v = float(value)
        except Exception:
            return None
        if not (v == v):  # NaN
            return None
        return max(0.2, min(30.0, float(v)))

    def _coerce_event(value: object) -> str | None:
        if value is None:
            return None
        if isinstance(value, str):
            v = value.strip()
            return v or None
        try:
            v = str(value).strip()
        except Exception:
            return None
        return v or None

    def _parse_json_obj(obj: object) -> tuple[str, float | None, float | None] | None:
        if isinstance(obj, str):
            ev = _coerce_event(obj)
            if ev is None:
                return None
            return (ev, None, None)
        if not isinstance(obj, dict):
            return None

        # Allow a light wrapper: {"live2d": {...}} or {"state_event": {...}}
        inner = obj.get("live2d") or obj.get("state_event") or obj.get("stateEvent")
        if isinstance(inner, dict):
            obj = inner

        event = _coerce_event(
            obj.get("event")
            or obj.get("state")
            or obj.get("expression")
            or obj.get("exp")
            or obj.get("name")
            or obj.get("key")
        )
        if event is None:
            return None

        intensity = _clamp01(
            obj.get("intensity") or obj.get("strength") or obj.get("level") or obj.get("weight")
        )
        hold_s = _clamp_hold_s(
            obj.get("hold_s") or obj.get("hold") or obj.get("seconds") or obj.get("duration_s")
        )
        return (event, intensity, hold_s)

    # JSON payload mode (recommended): `[[live2d:{"event":"angry","intensity":0.8,"hold_s":4}]]`
    # Note: keep it as a JSON object to avoid ambiguous `]]` suffix overlap with list payloads.
    if payload.startswith("{"):
        try:
            obj = json.loads(payload)
        except Exception:
            obj = None
        if obj is not None:
            parsed = _parse_json_obj(obj)
            if parsed is not None:
                return parsed

    # Legacy pipe mode: `[[live2d:EVENT|INTENSITY|HOLD_S]]`
    parts = [p.strip() for p in payload.split("|")]
    if not parts:
        return None
    event = str(parts[0] or "").strip()
    if not event:
        return None
    intensity = _clamp01(parts[1]) if len(parts) >= 2 and parts[1] else None
    hold_s = _clamp_hold_s(parts[2]) if len(parts) >= 3 and parts[2] else None
    return (event, intensity, hold_s)


def extract_explicit_state_directive(
    text: str,
) -> tuple[str, tuple[str, float | None, float | None] | None]:
    """Extract and strip explicit Live2D state directives from text.

    Syntax:
      - JSON payload (recommended):
        - `[[live2d:{"event":"angry"}]]`
        - `[[live2d:{"event":"shy","intensity":0.6}]]`
        - `[[live2d:{"event":"dizzy","intensity":0.7,"hold_s":4}]]`
      - Legacy pipe payload:
        - `[[live2d:EVENT]]`
        - `[[live2d:EVENT|INTENSITY]]` (0..1)
        - `[[live2d:EVENT|INTENSITY|HOLD_S]]`

    Returns `(clean_text, directive)` where directive is `(event, intensity, hold_s)`.
    """

    msg = str(text or "")
    if not msg:
        return ("", None)

    directive: tuple[str, float | None, float | None] | None = None

    def parse_payload(payload: str) -> tuple[str, float | None, float | None] | None:
        return _parse_state_event_payload(payload)

    # Find all complete directives; last one wins.
    low = msg.lower()
    i = 0
    out_parts: list[str] = []
    while True:
        found = _find_next_directive_start(low, i)
        if found is None:
            out_parts.append(msg[i:])
            break
        start, prefix, suffix = found
        out_parts.append(msg[i:start])
        end = low.find(suffix, start + len(prefix))
        if end == -1:
            # Incomplete directive: keep it as plain text (avoid losing content).
            out_parts.append(msg[start:])
            break
        payload = msg[start + len(prefix) : end]
        parsed = parse_payload(payload)
        if parsed is not None:
            directive = parsed
        i = end + len(suffix)

    cleaned = "".join(out_parts)
    # Avoid leaving behind ugly blank lines/spaces.
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return (cleaned.strip(), directive)


def filter_explicit_state_directives_stream(
    buffer: str,
    chunk: str,
) -> tuple[str, str, tuple[str, float | None, float | None] | None]:
    """Incrementally strip directives from streamed chunks.

    Returns `(clean_chunk, new_buffer, directive)` where `new_buffer` keeps
    any partial directive prefix for the next call.
    """

    buf = str(buffer or "")
    chunk = str(chunk or "")
    if not chunk and not buf:
        return ("", "", None)

    data = buf + chunk
    low = data.lower()
    directive: tuple[str, float | None, float | None] | None = None

    def parse_payload(payload: str) -> tuple[str, float | None, float | None] | None:
        return _parse_state_event_payload(payload)

    out_parts: list[str] = []
    i = 0
    max_buf = 4096
    while True:
        found = _find_next_directive_start(low, i)
        if found is None:
            tail = data[i:]
            # Keep a small suffix if it can be a partial prefix (to handle boundary splits).
            keep = ""
            try:
                best_k = 0
                for prefix, _suffix in _LIVE2D_DIRECTIVE_PATTERNS:
                    max_k = len(prefix) - 1
                    for k in range(max_k, 0, -1):
                        if tail.lower().endswith(prefix[:k]):
                            if k > best_k:
                                best_k = k
                            break
                if best_k > 0:
                    keep = tail[-best_k:]
                    tail = tail[:-best_k]
            except Exception:
                keep = ""
            out_parts.append(tail)
            new_buffer = keep
            break
        start, prefix, suffix = found
        out_parts.append(data[i:start])
        end = low.find(suffix, start + len(prefix))
        if end == -1:
            # Keep the incomplete directive in buffer.
            new_buffer = data[start:]
            if len(new_buffer) > max_buf:
                # Not a real directive (or never closed): flush it back to output
                # to avoid dropping content.
                out_parts.append(new_buffer)
                new_buffer = ""
            break
        payload = data[start + len(prefix) : end]
        parsed = parse_payload(payload)
        if parsed is not None:
            directive = parsed
        i = end + len(suffix)

    clean = "".join(out_parts)
    return (clean, new_buffer, directive)


# Fast-path tokens used to decide if it's worth attempting Live2D state inference on a small chunk.
STATE_EVENT_FAST_TOKENS: tuple[str, ...] = (
    "生气",
    "气死",
    "气炸",
    "脸红",
    "害羞",
    "头晕",
    "眩晕",
    "晕",
    "心心眼",
    "喜欢",
    "爱你",
    "亲亲",
    "抱抱",
    "哭哭",
    "难过",
    "伤心",
    "委屈",
    "星星眼",
    "惊讶",
    "///",
    "T_T",
    "QAQ",
)
