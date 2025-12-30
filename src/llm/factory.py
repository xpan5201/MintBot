"""
LLM 工厂：统一创建与缓存 LangChain Chat Model 实例。

说明：
- 该模块只做“构造与复用”，不在此处做任何网络调用。
- 默认读取 src.config.settings.settings.llm 配置。
"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Any, Dict, Optional

from src.config.settings import settings
from src.utils.logger import get_logger

logger = get_logger(__name__)
_WARNED_EMPTY_KEY = False
_WARNED_EMPTY_VISION_KEY = False
_WARNED_VISION_FALLBACK_MODEL = False


def reset_llm_cache() -> None:
    """清空 LLM 缓存（用于运行时变更配置后重新初始化）。"""
    _build_openai_llm.cache_clear()


def get_llm(
    *,
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    extra_config: Optional[Dict[str, Any]] = None,
) -> Any:
    """
    获取（并缓存）默认 LLM 实例。

    Args:
        model: 覆盖模型名（默认 settings.llm.model）
        temperature: 覆盖温度（默认 settings.llm.temperature）
        max_tokens: 覆盖最大 tokens（默认 settings.llm.max_tokens）
        extra_config: 覆盖/附加额外参数（默认 settings.llm.extra_config）
    """
    cfg = settings.llm
    resolved_model = model or cfg.model
    resolved_temperature = float(temperature if temperature is not None else cfg.temperature)
    resolved_max_tokens = int(max_tokens if max_tokens is not None else cfg.max_tokens)
    resolved_api = str(cfg.api or "").strip()
    resolved_key = str(cfg.key or "").strip()

    merged_extra: Dict[str, Any] = dict(cfg.extra_config or {})
    if extra_config:
        merged_extra.update(extra_config)
    extra_json = json.dumps(merged_extra, ensure_ascii=False, sort_keys=True)

    if not resolved_key:
        # 允许通过环境变量提供 key；这里只做提示，不抛异常，避免阻断启动流程
        global _WARNED_EMPTY_KEY
        if not _WARNED_EMPTY_KEY:
            _WARNED_EMPTY_KEY = True
            logger.warning(
                "LLM API Key 为空，若使用云端模型请在 config.user.yaml 配置 LLM.key（或通过环境变量提供）。"
            )

    return _build_openai_llm(
        resolved_model,
        resolved_temperature,
        resolved_max_tokens,
        resolved_api,
        resolved_key,
        extra_json,
    )


def get_vision_llm() -> Optional[Any]:
    """
    获取（并缓存）视觉 LLM 实例。

    说明：
    - 视觉 LLM 独立于主 LLM（主 LLM 可能是纯文本模型）。
    - 当 settings.vision_llm.enabled=False 或未配置时，返回 None，上层应回退到 OCR/基础信息。
    """
    cfg = getattr(settings, "vision_llm", None)
    if cfg is None or not bool(getattr(cfg, "enabled", False)):
        return None

    try:
        resolved_cfg = cfg.resolve(settings.llm)
    except Exception:
        # 极端情况下（旧配置/旧对象），回退为主 LLM 配置
        resolved_cfg = settings.llm

    resolved_model = str(resolved_cfg.model or "").strip()
    resolved_temperature = float(resolved_cfg.temperature)
    resolved_max_tokens = int(resolved_cfg.max_tokens)
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

    merged_extra: Dict[str, Any] = dict(getattr(resolved_cfg, "extra_config", {}) or {})
    extra_json = json.dumps(merged_extra, ensure_ascii=False, sort_keys=True)

    return _build_openai_llm(
        resolved_model,
        resolved_temperature,
        resolved_max_tokens,
        resolved_api,
        resolved_key,
        extra_json,
    )


@lru_cache(maxsize=8)
def _build_openai_llm(
    model: str,
    temperature: float,
    max_tokens: int,
    base_url: str,
    api_key: str,
    extra_json: str,
) -> Any:
    """
    构造并缓存 ChatOpenAI 实例。
    注意：该函数不会发起网络请求，只负责创建客户端对象。
    """
    try:
        from langchain_openai import ChatOpenAI
    except Exception as exc:  # pragma: no cover
        raise ImportError("langchain-openai 未安装，无法创建 ChatOpenAI") from exc

    extra = {}
    try:
        extra = json.loads(extra_json) if extra_json else {}
    except Exception:
        extra = {}

    kwargs: Dict[str, Any] = {
        "model": model,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if api_key:
        kwargs["api_key"] = api_key
    if base_url:
        kwargs["base_url"] = base_url
    kwargs.update(extra)

    # 兼容不同版本的参数名（base_url/openai_api_base）
    try:
        return ChatOpenAI(**kwargs)
    except TypeError:
        if "base_url" in kwargs:
            fallback_kwargs = dict(kwargs)
            base = fallback_kwargs.pop("base_url", None)
            if base:
                fallback_kwargs["openai_api_base"] = base
            return ChatOpenAI(**fallback_kwargs)
        raise
