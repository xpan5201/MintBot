"""
聊天历史加载线程（移出 UI 线程，避免滚动/切换联系人卡顿）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from PyQt6.QtCore import QThread, pyqtSignal

from src.auth.user_session import user_session
from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class ChatHistoryLoadRequest:
    request_id: int
    mode: str  # "initial" | "more"
    contact_name: str
    limit: int
    before_id: Optional[int] = None
    offset: int = 0
    include_total: bool = False


class ChatHistoryLoaderThread(QThread):
    """在后台线程加载聊天历史。"""

    result_ready = pyqtSignal(object)  # dict payload
    error = pyqtSignal(object)  # dict payload

    def __init__(self, request: ChatHistoryLoadRequest):
        super().__init__()
        self.request = request

    def run(self) -> None:  # pragma: no cover - QThread
        req = self.request
        try:
            self.setPriority(QThread.Priority.LowPriority)

            if self.isInterruptionRequested():
                return

            total_count: int | None
            if req.include_total:
                total_count = int(user_session.get_chat_history_count(req.contact_name))
            else:
                total_count = None

            if self.isInterruptionRequested():
                return

            messages: list[dict[str, Any]]
            if req.mode == "more" and req.before_id is None and req.offset > 0:
                # 向上翻页但缺少 before_id 时，必须走 OFFSET；否则 before_id=None 会取到最新页导致重复/乱序
                messages = user_session.get_chat_history(
                    req.contact_name, limit=req.limit, offset=req.offset
                )
            elif req.before_id is not None:
                messages = user_session.get_chat_history_page(
                    req.contact_name, limit=req.limit, before_id=req.before_id
                )
            else:
                messages = user_session.get_chat_history_page(
                    req.contact_name, limit=req.limit, before_id=None
                )

            if self.isInterruptionRequested():
                return

            self.result_ready.emit(
                {
                    "request_id": req.request_id,
                    "mode": req.mode,
                    "contact_name": req.contact_name,
                    "limit": req.limit,
                    "before_id": req.before_id,
                    "offset": req.offset,
                    "total_count": total_count,
                    "messages": messages,
                }
            )
        except Exception as exc:
            logger.warning("聊天历史加载失败: %s", exc, exc_info=True)
            self.error.emit(
                {
                    "request_id": req.request_id,
                    "mode": req.mode,
                    "contact_name": req.contact_name,
                    "error": str(exc),
                }
            )
