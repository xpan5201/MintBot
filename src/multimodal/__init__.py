"""
多模态处理模块

提供视觉、音频等多模态输入输出处理功能。
"""

# 音频处理模块（必需）
from .audio import AudioProcessor

# 视觉处理模块（可选）
try:
    from .vision import VisionProcessor
    _has_vision = True
except ImportError:
    VisionProcessor = None
    _has_vision = False

# TTS 模块（可选）
try:
    from .gpt_sovits_client import GPTSoVITSClient
    from .tts_manager import (
        AgentSpeechProfile,
        TTSConfig,
        TTSManager,
        get_tts_manager,
    )
    from .audio_player import AudioPlayer, get_audio_player
    from .tts_initializer import (
        init_tts,
        get_tts_manager_instance,
        get_tts_config_instance,
        is_tts_available,
    )
    _has_tts = True
except ImportError as e:
    GPTSoVITSClient = None
    TTSManager = None
    TTSConfig = None
    get_tts_manager = None
    AudioPlayer = None
    get_audio_player = None
    init_tts = None
    get_tts_manager_instance = None
    get_tts_config_instance = None
    is_tts_available = None
    _has_tts = False

# 导出列表
__all__ = ["AudioProcessor"]
if _has_vision:
    __all__.extend(["VisionProcessor"])
if _has_tts:
    __all__.extend([
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
    ])
