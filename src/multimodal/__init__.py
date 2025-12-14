"""
多模态处理模块

提供视觉、音频等多模态输入输出处理功能。

性能说明：
- 该包通常会被 GUI 启动路径间接导入（例如初始化 TTS），因此避免在 import 阶段做重实例化或重依赖导入；
- 使用模块级 `__getattr__` 实现按需懒加载，减少 GUI 启动卡顿与无意义日志。
"""

from __future__ import annotations

from typing import Any

__all__ = [
    # Audio
    "AudioProcessor",
    "get_audio_processor_instance",
    # Vision
    "VisionProcessor",
    "get_vision_processor_instance",
    # TTS
    "AgentSpeechProfile",
    "GPTSoVITSClient",
    "TTSManager",
    "TTSConfig",
    "get_tts_manager",
    "AudioPlayer",
    "get_audio_player",
    "init_tts",
    "get_tts_manager_instance",
    "get_tts_config_instance",
    "is_tts_available",
]


def __getattr__(name: str) -> Any:  # pragma: no cover - 仅用于 import 懒加载
    if name in {"AudioProcessor", "get_audio_processor_instance"}:
        from .audio import AudioProcessor, get_audio_processor_instance

        return AudioProcessor if name == "AudioProcessor" else get_audio_processor_instance

    if name in {"VisionProcessor", "get_vision_processor_instance"}:
        from .vision import VisionProcessor, get_vision_processor_instance

        return VisionProcessor if name == "VisionProcessor" else get_vision_processor_instance

    if name == "GPTSoVITSClient":
        from .gpt_sovits_client import GPTSoVITSClient

        return GPTSoVITSClient

    if name in {"AgentSpeechProfile", "TTSConfig", "TTSManager", "get_tts_manager"}:
        from .tts_manager import AgentSpeechProfile, TTSConfig, TTSManager, get_tts_manager

        mapping = {
            "AgentSpeechProfile": AgentSpeechProfile,
            "TTSConfig": TTSConfig,
            "TTSManager": TTSManager,
            "get_tts_manager": get_tts_manager,
        }
        return mapping[name]

    if name in {"AudioPlayer", "get_audio_player"}:
        from .audio_player import AudioPlayer, get_audio_player

        return AudioPlayer if name == "AudioPlayer" else get_audio_player

    if name in {
        "init_tts",
        "get_tts_manager_instance",
        "get_tts_config_instance",
        "is_tts_available",
    }:
        from .tts_initializer import (
            init_tts,
            get_tts_manager_instance,
            get_tts_config_instance,
            is_tts_available,
        )

        mapping = {
            "init_tts": init_tts,
            "get_tts_manager_instance": get_tts_manager_instance,
            "get_tts_config_instance": get_tts_config_instance,
            "is_tts_available": is_tts_available,
        }
        return mapping[name]

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:  # pragma: no cover
    return sorted(set(globals().keys()) | set(__all__))

