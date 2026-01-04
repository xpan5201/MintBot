"""LLM 工厂：统一创建与缓存 OpenAI-compatible 后端实例。

说明：
- 该模块只做“构造与复用”，不在此处做任何网络调用。
- 默认读取 `src.config.settings.settings.llm` 配置。
"""

from __future__ import annotations

from functools import lru_cache
from urllib.parse import urlparse
from typing import Any, Optional

from src.config.settings import settings
from src.llm_native.backend import BackendConfig
from src.llm_native.openai_backend import OpenAICompatibleBackend
from src.utils.logger import get_logger

logger = get_logger(__name__)
_WARNED_EMPTY_KEY = False
_WARNED_EMPTY_VISION_KEY = False
_WARNED_VISION_FALLBACK_MODEL = False


def reset_llm_cache() -> None:
    """清空 LLM 缓存（用于运行时变更配置后重新初始化）。"""
    _build_openai_backend_cached.cache_clear()


def get_llm(
    *,
    model: Optional[str] = None,
    timeout_s: Optional[float] = None,
    max_retries: Optional[int] = None,
) -> Any:
    """获取（并缓存）默认 OpenAI-compatible 后端实例。"""
    cfg = settings.llm
    resolved_model = str(model or cfg.model or "").strip()
    resolved_api = str(cfg.api or "").strip()
    resolved_key = str(cfg.key or "").strip()

    if not resolved_key:
        global _WARNED_EMPTY_KEY
        if not _WARNED_EMPTY_KEY:
            _WARNED_EMPTY_KEY = True
            logger.warning(
                "LLM API Key 为空，若使用云端模型请在 config.user.yaml 配置 LLM.key（或通过环境变量提供）。"
            )

    try:
        resolved_timeout_s = float(timeout_s) if timeout_s is not None else 60.0
    except Exception:
        resolved_timeout_s = 60.0

    try:
        resolved_max_retries = int(max_retries) if max_retries is not None else 2
    except Exception:
        resolved_max_retries = 2

    return _build_openai_backend(
        resolved_model,
        resolved_api,
        resolved_key,
        timeout_s=resolved_timeout_s,
        max_retries=resolved_max_retries,
    )


def get_vision_llm() -> Optional[Any]:
    """获取（并缓存）视觉后端实例；未启用则返回 None。"""
    cfg = getattr(settings, "vision_llm", None)
    if cfg is None or not bool(getattr(cfg, "enabled", False)):
        return None

    try:
        resolved_cfg = cfg.resolve(settings.llm)
    except Exception:
        resolved_cfg = settings.llm

    resolved_model = str(resolved_cfg.model or "").strip()
    resolved_api = str(resolved_cfg.api or "").strip()
    resolved_key = str(resolved_cfg.key or "").strip()

    global _WARNED_EMPTY_VISION_KEY, _WARNED_VISION_FALLBACK_MODEL
    if not resolved_model:
        if not _WARNED_VISION_FALLBACK_MODEL:
            _WARNED_VISION_FALLBACK_MODEL = True
            logger.warning("VISION_LLM 已启用但模型名为空，将回退为 settings.llm.model")
        resolved_model = str(settings.llm.model or "").strip()

    if not resolved_key and not _WARNED_EMPTY_VISION_KEY:
        _WARNED_EMPTY_VISION_KEY = True
        logger.warning(
            "VISION_LLM 已启用但 API Key 为空；若使用云端视觉模型，请在 config.user.yaml 配置 VISION_LLM.key "
            "（或通过环境变量提供）。"
        )

    return _build_openai_backend(
        resolved_model,
        resolved_api,
        resolved_key,
        timeout_s=60.0,
        max_retries=2,
    )


def _normalize_openai_base_url(base_url: str) -> str:
    raw = str(base_url or "").strip()
    if not raw:
        return ""
    raw = raw.rstrip("/")
    try:
        parsed = urlparse(raw)
    except Exception:
        return raw
    if not parsed.scheme or not parsed.netloc:
        return raw
    # Only append /v1 when user provides a bare host (or host + "/").
    if parsed.path in ("", "/"):
        return f"{raw}/v1"
    return raw


def _build_openai_backend(
    model: str,
    base_url: str,
    api_key: str,
    *,
    timeout_s: float,
    max_retries: int,
) -> OpenAICompatibleBackend:
    """构造并缓存 OpenAICompatibleBackend 实例（仅构造，不发起请求）。"""
    normalized = _normalize_openai_base_url(base_url)
    normalized_model = str(model or "").strip() or str(getattr(settings.llm, "model", "gpt-4o"))
    return _build_openai_backend_cached(
        normalized_model,
        normalized or "https://api.openai.com/v1",
        str(api_key or "").strip(),
        timeout_s=max(1.0, float(timeout_s)),
        max_retries=max(0, int(max_retries)),
    )


@lru_cache(maxsize=8)
def _build_openai_backend_cached(
    model: str,
    base_url: str,
    api_key: str,
    *,
    timeout_s: float,
    max_retries: int,
) -> OpenAICompatibleBackend:
    cfg = BackendConfig(
        base_url=base_url,
        api_key=api_key,
        model=model,
        timeout_s=timeout_s,
        max_retries=max_retries,
    )
    return OpenAICompatibleBackend(cfg)
