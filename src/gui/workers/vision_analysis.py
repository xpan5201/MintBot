"""
Vision/图片识别后台任务。

将图片识别逻辑移出 `light_chat_window.py`，并使用 `QThreadPool + QRunnable` 复用线程，
减少频繁创建/销毁 QThread 的开销。
"""

from __future__ import annotations

from typing import Any, Optional

from PyQt6.QtCore import QObject, QRunnable, pyqtSignal

from src.utils.logger import get_logger

logger = get_logger(__name__)


class VisionAnalyzeSignals(QObject):
    result_ready = pyqtSignal(object)  # dict payload
    error = pyqtSignal(object)  # dict payload
    finished = pyqtSignal()


class VisionAnalyzeTask(QRunnable):
    """单张图片识别任务（在线程池中执行）。"""

    def __init__(
        self,
        image_path: str,
        *,
        mode: str,
        llm: Any,
        index: Optional[int] = None,
    ):
        super().__init__()
        # 重要：由 Python 侧持有引用并负责生命周期，避免 Qt autoDelete 导致潜在悬垂引用
        self.setAutoDelete(False)
        self.image_path = image_path
        self.mode = mode
        self.llm = llm
        self.index = index
        self.signals = VisionAnalyzeSignals()

    def run(self) -> None:  # pragma: no cover - QRunnable
        try:
            from src.multimodal.vision import get_vision_processor_instance

            result = get_vision_processor_instance().smart_analyze(
                self.image_path,
                mode=self.mode,
                llm=self.llm,
            )
            payload = dict(result) if isinstance(result, dict) else {"result": result}
            payload.setdefault("mode", self.mode)
            payload["image_path"] = self.image_path
            if self.index is not None:
                payload["index"] = int(self.index)
            self.signals.result_ready.emit(payload)
        except Exception as exc:
            logger.warning("图片识别失败: %s", exc, exc_info=False)
            self.signals.error.emit(
                {
                    "image_path": self.image_path,
                    "mode": self.mode,
                    "index": int(self.index) if self.index is not None else None,
                    "error": str(exc),
                }
            )
        finally:
            self.signals.finished.emit()
