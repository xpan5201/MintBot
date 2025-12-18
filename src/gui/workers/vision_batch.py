"""
批量图片识别线程。

当前实现沿用旧逻辑（线程内再做有限并发），但将代码从 `light_chat_window.py` 抽离，
便于复用与维护。
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from PyQt6.QtCore import QThread, pyqtSignal

from src.utils.logger import get_logger

logger = get_logger(__name__)


class BatchImageRecognitionThread(QThread):
    """批量图片识别线程 - 增强并发控制。"""

    progress = pyqtSignal(int, int, dict)  # completed, total, last_result
    finished = pyqtSignal(list)  # list[dict]
    error = pyqtSignal(str)

    def __init__(self, image_paths: list[str], mode: str, llm: Any, max_concurrent: int = 3):
        super().__init__()
        self.image_paths = list(image_paths)
        self.mode = mode
        self.llm = llm
        self.max_concurrent = max(1, int(max_concurrent))
        self._is_running = True

    def run(self) -> None:  # pragma: no cover - QThread
        try:
            from src.multimodal.vision import get_vision_processor_instance

            processor = get_vision_processor_instance()
            results: list[tuple[int, dict]] = []
            total = len(self.image_paths)

            with ThreadPoolExecutor(max_workers=self.max_concurrent) as executor:
                future_to_index = {
                    executor.submit(
                        processor.smart_analyze,
                        image_path,
                        mode=self.mode,
                        llm=self.llm,
                    ): (i, image_path)
                    for i, image_path in enumerate(self.image_paths)
                }

                completed = 0
                for future in as_completed(future_to_index):
                    if not self._is_running:
                        logger.info("批量识别被取消")
                        break

                    i, image_path = future_to_index[future]
                    try:
                        result = future.result()
                        if isinstance(result, dict):
                            result["image_path"] = image_path
                        results.append((i, result))
                        completed += 1
                        try:
                            self.progress.emit(completed, total, result)
                        except Exception:
                            pass
                    except Exception as exc:
                        logger.error("识别图片 %s 失败: %s", image_path, exc)
                        completed += 1
                        try:
                            self.progress.emit(completed, total, {"image_path": image_path, "error": str(exc)})
                        except Exception:
                            pass

            results.sort(key=lambda x: x[0])
            sorted_results = [r[1] for r in results]
            self.finished.emit(sorted_results)
        except Exception as exc:
            logger.error("批量识别失败: %s", exc, exc_info=False)
            self.error.emit(str(exc))

    def stop(self) -> None:
        """请求停止批量识别。"""
        self._is_running = False
