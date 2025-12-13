"""
GUI组件模块 - v2.45.0

提供可复用的GUI组件
"""

from .tts_status_panel import TTSStatusPanel
from .reference_audio_selector import ReferenceAudioSelector
from .voice_control_panel import VoiceControlPanel
from .tts_queue_list import TTSQueueList  # v2.38.0
from .audio_waveform import AudioWaveform  # v2.38.0
from .tts_history_panel import TTSHistoryPanel  # v2.40.0
from .shortcut_help_dialog import ShortcutHelpDialog  # v2.41.0
from .shortcut_settings_dialog import ShortcutSettingsDialog  # v2.42.0
from .export_template_dialog import ExportTemplateDialog  # v2.42.0
from .tts_performance_monitor import TTSPerformanceMonitor  # v2.44.0
from .performance_chart import PerformanceChart  # v2.45.0

__all__ = [
    "TTSStatusPanel",
    "ReferenceAudioSelector",
    "VoiceControlPanel",
    "TTSQueueList",  # v2.38.0
    "AudioWaveform",  # v2.38.0
    "TTSHistoryPanel",  # v2.40.0
    "ShortcutHelpDialog",  # v2.41.0
    "ShortcutSettingsDialog",  # v2.42.0
    "ExportTemplateDialog",  # v2.42.0
    "TTSPerformanceMonitor",  # v2.44.0
    "PerformanceChart",  # v2.45.0
]

