"""
Agent 聊天相关后台线程。

将聊天流式输出与 Agent 初始化移出 `light_chat_window.py`，降低主窗口文件复杂度，
同时便于复用与测试。
"""

from __future__ import annotations

import time
from threading import Event
from typing import Any, Optional, TYPE_CHECKING

from PyQt6.QtCore import QThread, pyqtSignal

from src.utils.gui_optimizer import track_object
from src.utils.logger import get_logger

logger = get_logger(__name__)

if TYPE_CHECKING:  # pragma: no cover
    from src.agent.core import MintChatAgent


class ChatThread(QThread):
    """聊天线程：在后台消费 `agent.chat_stream()`，并批量 emit 文本块。"""

    chunk_received = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(
        self,
        agent: "MintChatAgent",
        message: str,
        *,
        image_path: Optional[str] = None,
        image_analysis: Optional[dict] = None,
        timeout: float = 300.0,
        emit_interval_ms: int = 33,
        emit_threshold: int = 2048,
    ):
        super().__init__()
        self.agent = agent
        self.message = message
        self.image_path = image_path
        self.image_analysis = image_analysis
        self.timeout = float(timeout)
        self.emit_interval_ms = max(0, int(emit_interval_ms))
        self.emit_threshold = max(256, int(emit_threshold))

        self._is_running = True
        self._cancel_event = Event()
        self._had_error = False
        self._start_ts = 0.0

        safe_preview = (message or "").replace("\n", " ")[:20]
        track_object(self, f"ChatThread-{safe_preview}")

    def run(self) -> None:  # pragma: no cover - QThread
        try:
            self.setPriority(QThread.Priority.LowPriority)
            self._start_ts = time.monotonic()

            logger.info("ChatThread 开始运行")

            total_chunks = 0
            emitted_chunks = 0
            chunk_buffer: list[str] = []
            buffer_len = 0
            last_emit_ts = time.monotonic()
            emit_interval_s = max(0.0, self.emit_interval_ms / 1000.0)
            emit_threshold = self.emit_threshold
            drain_on_exit = False
            timeout_error: Optional[str] = None

            stream_iter = self.agent.chat_stream(
                self.message,
                save_to_long_term=True,
                image_path=self.image_path,
                image_analysis=self.image_analysis,
                cancel_event=self._cancel_event,
            )
            try:
                for chunk in stream_iter:
                    if self.isInterruptionRequested() and not self._cancel_event.is_set():
                        self._cancel_event.set()
                    if (
                        (not self._is_running)
                        or self._cancel_event.is_set()
                        or self.isInterruptionRequested()
                    ):
                        drain_on_exit = True
                        break

                    if (time.monotonic() - self._start_ts) > self.timeout:
                        logger.warning("ChatThread 超时 (%s 秒)", self.timeout)
                        timeout_error = f"请求超时（{self.timeout}秒），请稍后重试"
                        self._cancel_event.set()
                        self._had_error = True
                        self.error.emit(timeout_error)
                        drain_on_exit = True
                        break

                    if not chunk:
                        continue

                    total_chunks += 1
                    chunk_buffer.append(chunk)
                    buffer_len += len(chunk)

                    now = time.monotonic()
                    if buffer_len >= emit_threshold or (now - last_emit_ts) >= emit_interval_s:
                        payload = "".join(chunk_buffer)
                        chunk_buffer.clear()
                        buffer_len = 0
                        last_emit_ts = now
                        if payload:
                            emitted_chunks += 1
                            self.chunk_received.emit(payload)
            finally:
                if drain_on_exit:
                    # Best-effort drain to trigger Agent generator cleanup.
                    deadline = time.monotonic() + 1.0
                    try:
                        for _ in stream_iter:
                            if time.monotonic() >= deadline:
                                break
                    except Exception:
                        pass

            if chunk_buffer:
                payload = "".join(chunk_buffer)
                if payload:
                    emitted_chunks += 1
                    self.chunk_received.emit(payload)

            if timeout_error:
                return

            execution_time = time.monotonic() - self._start_ts
            logger.info(
                "ChatThread 完成，共接收 %s 个chunk（批量emit=%s 次），耗时 %.2f 秒",
                total_chunks,
                emitted_chunks,
                execution_time,
            )
        except Exception as exc:
            from src.utils.exceptions import handle_exception

            handle_exception(exc, logger, "ChatThread 运行失败")
            if self._is_running and (not self._cancel_event.is_set()):
                self._had_error = True
                self.error.emit(str(exc))

    def stop(self) -> None:
        """请求停止线程。"""
        logger.info("正在停止 ChatThread...")
        self._is_running = False
        self._cancel_event.set()
        try:
            self.requestInterruption()
        except Exception:
            pass

    def cleanup(self) -> None:
        """清理资源（供 UI 侧调用）。"""
        logger.info("开始清理 ChatThread 资源...")
        self.stop()
        if self.isRunning():
            logger.debug("ChatThread 仍在运行，延迟清理引用")
            return
        self.agent = None
        self.message = None
        self.image_path = None
        self.image_analysis = None
        self._is_running = False
        self._cancel_event = Event()
        self._start_ts = 0.0
        logger.info("ChatThread 资源已清理")


class AgentInitThread(QThread):
    """后台初始化 Agent，避免阻塞 GUI 主线程。"""

    agent_ready = pyqtSignal(object)
    error = pyqtSignal(str)

    def __init__(self, user_id: Any):
        super().__init__()
        self.user_id = user_id

    def run(self) -> None:  # pragma: no cover - QThread
        try:
            from src.agent.core import MintChatAgent

            agent = MintChatAgent(user_id=self.user_id)
            self.agent_ready.emit(agent)
        except Exception as exc:
            logger.error("初始化 Agent 失败: %s", exc, exc_info=True)
            self.error.emit(str(exc))
