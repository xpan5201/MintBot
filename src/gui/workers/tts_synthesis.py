"""
TTS 合成后台任务（线程池复用，减少频繁创建 QThread 的开销）。
"""

from __future__ import annotations

import asyncio
from typing import Any

from PyQt6.QtCore import QObject, QRunnable, pyqtSignal

from src.utils.logger import get_logger

logger = get_logger(__name__)


class TTSSynthesisSignals(QObject):
    audio_ready = pyqtSignal(bytes)
    error = pyqtSignal(str)
    finished = pyqtSignal()


class TTSSynthesisTask(QRunnable):
    """在线程池中执行一次 TTS 合成。"""

    def __init__(self, tts_manager: Any, text: str):
        super().__init__()
        # 重要：由 Python 侧持有引用并负责生命周期，避免 Qt autoDelete 导致潜在悬垂引用
        self.setAutoDelete(False)
        self.tts_manager = tts_manager
        self.text = text
        self.signals = TTSSynthesisSignals()

    def run(self) -> None:  # pragma: no cover - QRunnable
        try:
            audio_data = asyncio.run(self.tts_manager.synthesize_text(self.text))
            if audio_data:
                self.signals.audio_ready.emit(audio_data)
            else:
                self.signals.error.emit("TTS 合成返回空结果")
        except Exception as exc:
            logger.error("TTS 合成失败: %s", exc, exc_info=False)
            self.signals.error.emit(f"TTS 合成失败: {exc}")
        finally:
            self.signals.finished.emit()
