from __future__ import annotations

from collections.abc import Mapping
from typing import Any

# This module defines the "supported and documented" configuration surface.
#
# - The Settings schema (src/config/settings.py) contains many tuning knobs.
# - For long-term maintainability and to reduce user misconfiguration risk, we only
#   document a curated subset in the example YAMLs.
# - Developer/advanced knobs live in config.dev.yaml (optional), while user-safe
#   knobs live in config.user.yaml.


USER_EXAMPLE_REQUIRED_PATHS: tuple[str, ...] = (
    # LLM
    "LLM.api",
    "LLM.key",
    "LLM.model",
    "LLM.temperature",
    "LLM.max_tokens",
    "LLM.extra_config",
    # Vision LLM
    "VISION_LLM.enabled",
    "VISION_LLM.api",
    "VISION_LLM.key",
    "VISION_LLM.model",
    "VISION_LLM.temperature",
    "VISION_LLM.max_tokens",
    "VISION_LLM.extra_config",
    # Agent (user-facing)
    "Agent.char",
    "Agent.user",
    "Agent.prompt",
    "Agent.message_example",
    "Agent.enable_streaming",
    "Agent.max_history_length",
    "Agent.enable_tools",
    "Agent.mood_system_enabled",
    "Agent.emotion_memory_enabled",
    "Agent.long_memory",
    # TTS (basic)
    "TTS.enabled",
    "TTS.api_url",
    "TTS.ref_audio_path",
    "TTS.ref_audio_text",
    "TTS.text_lang",
    "TTS.prompt_lang",
    # ASR (basic)
    "ASR.enabled",
    "ASR.realtime_mode",
    "ASR.model",
    "ASR.device",
    "ASR.sample_rate",
    # External services
    "TAVILY.api_key",
    "AMAP.api_key",
    # GUI (read by GUI modules; not part of Settings schema)
    "GUI.theme",
    "GUI.live2d.state_events.enabled",
    "GUI.live2d.state_events.allow_directives",
    "GUI.live2d.state_events.stream_feedback",
    "GUI.live2d.state_events.debounce_ms",
    "GUI.live2d.state_events.stream_tail_chars",
    # Paths
    "data_dir",
    "vector_db_path",
    "memory_path",
    "cache_path",
    # Embeddings (user-facing, but safe defaults exist)
    "embedding_model",
    "embedding_api_base",
    "use_local_embedding",
    "enable_embedding_cache",
    # Limits
    "max_image_size",
    "max_audio_duration",
    # Basic logging
    "log_level",
    "log_dir",
)


DEV_CONFIG_REQUIRED_PATHS: tuple[str, ...] = (
    # MCP
    "MCP.enable",
    "MCP.servers",
    # Advanced logging
    "log_json",
    "log_rotation",
    "log_retention",
    "log_quiet_libs",
    "log_quiet_level",
    "log_drop_keywords",
    # ASR streaming tuning (advanced)
    "ASR.streaming_model",
    "ASR.streaming_hub",
    "ASR.streaming_chunk_size",
    "ASR.streaming_encoder_chunk_look_back",
    "ASR.streaming_decoder_chunk_look_back",
    "ASR.dual_emit_streaming_final",
    # Tavily defaults
    "TAVILY.search_depth",
    "TAVILY.include_answer",
)


def has_config_path(config: Mapping[str, Any], path: str) -> bool:
    """Return True if the nested key path exists in the mapping."""
    current: Any = config
    for part in (path or "").split("."):
        if not part:
            return False
        if not isinstance(current, Mapping):
            return False
        if part not in current:
            return False
        current = current.get(part)
    return True
