"""浅色主题聊天窗口（Material Design 3、流式输出、自定义头像、性能优化、QQ风格界面）"""

from collections import deque
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QAbstractScrollArea,
    QScrollArea,
    QLabel,
    QSizePolicy,
    QStackedWidget,
    QGraphicsOpacityEffect,
    QGraphicsDropShadowEffect,
)
from PyQt6.QtCore import (
    Qt,
    QThread,
    QThreadPool,
    pyqtSignal,
    QPropertyAnimation,
    QEasingCurve,
    QTimer,
)
from PyQt6.QtGui import QFont, QColor, QPixmap
from pathlib import Path
from functools import lru_cache
from typing import Any, Optional, List, TYPE_CHECKING
import re
import time
import asyncio
import os

STICKER_PATTERN = re.compile(r"\[STICKER:([^\]]+)\]")
# 流式渲染：固定帧率小步追加（更像 ChatGPT 网页端，且避免一次性塞入大段文本导致“段落跳动”）
# 兼容：历史环境变量 MINTCHAT_GUI_STREAM_FLUSH_MS 仍可作为渲染间隔的兜底值。
STREAM_RENDER_INTERVAL_MS = max(
    0,
    int(
        os.getenv(
            "MINTCHAT_GUI_STREAM_RENDER_MS",
            os.getenv("MINTCHAT_GUI_STREAM_FLUSH_MS", "33"),
        )
    ),
)
STREAM_RENDER_TYPEWRITER = os.getenv("MINTCHAT_GUI_STREAM_TYPEWRITER", "1").lower() not in {
    "0",
    "false",
    "no",
    "off",
}
STREAM_RENDER_BASE_CHARS = max(1, int(os.getenv("MINTCHAT_GUI_STREAM_RENDER_CHARS", "16")))
STREAM_RENDER_MAX_CHARS = max(
    STREAM_RENDER_BASE_CHARS, int(os.getenv("MINTCHAT_GUI_STREAM_RENDER_MAX_CHARS", "256"))
)
CHATTHREAD_EMIT_INTERVAL_MS = max(0, int(os.getenv("MINTCHAT_GUI_STREAM_EMIT_MS", "33")))
CHATTHREAD_EMIT_THRESHOLD = max(256, int(os.getenv("MINTCHAT_GUI_STREAM_EMIT_THRESHOLD", "2048")))
STREAM_SCROLL_INTERVAL_MS = max(
    0, int(os.getenv("MINTCHAT_GUI_STREAM_SCROLL_MS", str(STREAM_RENDER_INTERVAL_MS)))
)
# 长对话性能保护：限制一次性渲染的消息气泡数量，避免 widget 数量过多导致滚动掉帧。
# 为 0 表示禁用（保持旧行为）。
MAX_RENDERED_MESSAGES = max(0, int(os.getenv("MINTCHAT_GUI_MAX_RENDERED_MESSAGES", "400")))
TRIM_RENDERED_MESSAGES_BATCH = max(1, int(os.getenv("MINTCHAT_GUI_TRIM_RENDERED_BATCH", "50")))
AUTO_SCROLL_BOTTOM_THRESHOLD_PX = max(0, int(os.getenv("MINTCHAT_GUI_AUTO_SCROLL_BOTTOM_PX", "80")))
SMOOTH_SCROLL_ENABLED = os.getenv("MINTCHAT_GUI_SMOOTH_SCROLL", "0").lower() not in {
    "0",
    "false",
    "no",
    "off",
}
FPS_OVERLAY_ENABLED = os.getenv("MINTCHAT_GUI_FPS_OVERLAY", "0").lower() not in {"0", "false", "no", "off"}
SHADOW_BUDGET = max(0, int(os.getenv("MINTCHAT_GUI_SHADOW_BUDGET", "24")))
GUI_ANIMATIONS_ENABLED = os.getenv(
    "MINTCHAT_GUI_ANIMATIONS",
    os.getenv("MINTCHAT_GUI_ENTRY_ANIMATIONS", "0"),  # 兼容旧变量名
).lower() not in {
    "0",
    "false",
    "no",
    "off",
}

from .light_frameless_window import LightFramelessWindow
from .light_sidebar import LightIconSidebar
from .light_message_bubble import (
    LightMessageBubble,
    LightStreamingMessageBubble,
    LightTypingIndicator,
    LightImageMessageBubble,
)
from .material_design_light import MD3_LIGHT_COLORS, MD3_RADIUS
from .material_design_enhanced import (
    MD3_ENHANCED_COLORS,
    MD3_ENHANCED_SPACING,
    MD3_ENHANCED_RADIUS,
    MD3_ENHANCED_DURATION,
    MD3_ENHANCED_EASING,
    MD3_ENHANCED_ELEVATION,
    get_typography_css,
    get_elevation_shadow,
)
from .material_icons import MaterialIconButton, MATERIAL_ICONS
from .enhanced_rich_input import EnhancedInputWidget
from .loading_states import EmptyState
from .notifications import show_toast, Toast
from .contacts_panel import ContactsPanel
from src.utils.logger import get_logger
from src.auth.user_session import user_session
from src.utils.gui_optimizer import throttle, track_object
from .chat_window_optimizer import ChatWindowOptimizer

logger = get_logger(__name__)

if TYPE_CHECKING:  # pragma: no cover
    from src.agent.core import MintChatAgent


@lru_cache(maxsize=32)
def _load_rounded_header_avatar_pixmap(image_path: str, size: int, mtime_ns: int) -> QPixmap:
    """加载并裁剪为圆形头像（用于聊天窗口头部，带缓存）。"""
    _ = mtime_ns  # 仅用于缓存键，文件变更时自动失效

    pixmap = QPixmap(image_path)
    if pixmap.isNull():
        return QPixmap()

    scaled_pixmap = pixmap.scaled(
        size,
        size,
        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
        Qt.TransformationMode.SmoothTransformation,
    )
    if scaled_pixmap.width() > size or scaled_pixmap.height() > size:
        x = (scaled_pixmap.width() - size) // 2
        y = (scaled_pixmap.height() - size) // 2
        scaled_pixmap = scaled_pixmap.copy(x, y, size, size)

    from PyQt6.QtGui import QPainter, QPainterPath

    rounded_pixmap = QPixmap(size, size)
    rounded_pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(rounded_pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

    path = QPainterPath()
    path.addEllipse(0, 0, size, size)
    painter.setClipPath(path)
    painter.drawPixmap(0, 0, scaled_pixmap)
    painter.end()

    return rounded_pixmap


def _create_avatar_label_for_header(avatar_text: str, size: int) -> QLabel:
    """创建聊天窗口头部的头像标签（支持emoji和图片路径）"""
    avatar_label = QLabel()
    avatar_label.setFixedSize(size, size)
    avatar_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

    # 检查是否为图片路径
    avatar_path = Path(avatar_text) if avatar_text else None
    if avatar_path and avatar_path.is_file():
        try:
            mtime_ns = avatar_path.stat().st_mtime_ns
        except OSError:
            mtime_ns = 0

        rounded_pixmap = _load_rounded_header_avatar_pixmap(str(avatar_path), size, mtime_ns)
        if not rounded_pixmap.isNull():
            avatar_label.setPixmap(rounded_pixmap)
            avatar_label.setScaledContents(False)
        else:
            avatar_label.setText("🐱")
    else:
        # emoji 或无效路径：直接显示文本
        avatar_label.setText(avatar_text if avatar_text else "🐱")

    # 设置样式（AI头像）
    avatar_label.setStyleSheet(
        f"""
        QLabel {{
            background: qlineargradient(
                x1:0, y1:0, x2:1, y2:1,
                stop:0 {MD3_ENHANCED_COLORS['primary_40']},
                stop:1 {MD3_ENHANCED_COLORS['secondary_40']}
            );
            border-radius: {size // 2}px;
            font-size: {size // 2}px;
            border: 3px solid {MD3_ENHANCED_COLORS['surface_bright']};
        }}
    """
    )

    return avatar_label


class ChatThread(QThread):
    """聊天线程（简化版，直接调用Agent）"""

    chunk_received = pyqtSignal(str)
    finished = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(
        self,
        agent: "MintChatAgent",
        message: str,
        image_path: Optional[str] = None,
        image_analysis: Optional[dict] = None,
        timeout: float = 300.0,
    ):
        super().__init__()
        self.agent = agent
        self.message = message
        self.image_path = image_path
        self.image_analysis = image_analysis
        self.timeout = timeout
        self._is_running = True
        self._start_time = None

        track_object(self, f"ChatThread-{message[:20]}")

    def run(self):
        """运行线程"""
        try:
            self.setPriority(QThread.Priority.LowPriority)
            self._start_time = time.time()

            logger.info("ChatThread开始运行")

            total_chunks = 0
            emitted_chunks = 0
            chunk_buffer: list[str] = []
            buffer_len = 0
            last_emit_ts = time.monotonic()
            emit_interval_s = max(0.0, CHATTHREAD_EMIT_INTERVAL_MS / 1000.0)
            emit_threshold = CHATTHREAD_EMIT_THRESHOLD

            for chunk in self.agent.chat_stream(
                self.message,
                save_to_long_term=True,
                image_path=self.image_path,
                image_analysis=self.image_analysis
            ):
                if not self._is_running:
                    break

                if time.time() - self._start_time > self.timeout:
                    logger.warning("ChatThread超时 (%s秒)", self.timeout)
                    self.error.emit(f"请求超时（{self.timeout}秒），请稍后重试")
                    return

                # 跳过空片段
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

            if chunk_buffer:
                payload = "".join(chunk_buffer)
                if payload:
                    emitted_chunks += 1
                    self.chunk_received.emit(payload)

            execution_time = time.time() - self._start_time
            logger.info(
                "ChatThread完成，共接收 %s 个chunk（批量emit=%s 次），耗时 %.2f秒",
                total_chunks,
                emitted_chunks,
                execution_time,
            )
            self.finished.emit()

        except Exception as e:
            from src.utils.exceptions import handle_exception
            handle_exception(e, logger, "ChatThread运行失败")
            if self._is_running:
                self.error.emit(str(e))

    def stop(self):
        """停止线程"""
        logger.info("正在停止ChatThread...")
        self._is_running = False
        if self.isRunning():
            self.wait(2000)

    def cleanup(self):
        """清理资源"""
        logger.info("开始清理 ChatThread 资源...")
        self.stop()
        self.agent = None
        self.message = None
        self.image_path = None
        self.image_analysis = None
        self._is_running = False
        self._start_time = None
        logger.info("ChatThread 资源已清理")


class AgentInitThread(QThread):
    """后台初始化 Agent，避免阻塞 GUI 主线程。"""

    agent_ready = pyqtSignal(object)
    error = pyqtSignal(str)

    def __init__(self, user_id: Any):
        super().__init__()
        self.user_id = user_id

    def run(self) -> None:
        try:
            from src.agent.core import MintChatAgent

            agent = MintChatAgent(user_id=self.user_id)
            self.agent_ready.emit(agent)
        except Exception as e:
            logger.error("初始化 Agent 失败: %s", e, exc_info=True)
            self.error.emit(str(e))


class LightChatWindow(LightFramelessWindow):
    """浅色主题聊天窗口 - v2.15.0 优化版"""

    def __init__(self):
        super().__init__("MintChat - 猫娘女仆智能体")

        # Agent：惰性/后台初始化（避免启动阻塞 GUI 主线程）
        self.agent = None
        self._agent_user_id = None
        self._agent_username = None
        self._agent_initializing = True
        self._agent_init_failed = False
        self._agent_init_thread = None
        self._tool_filter_func = None

        try:
            self._agent_user_id = user_session.get_user_id()
            self._agent_username = user_session.get_username()
        except Exception:
            self._agent_user_id = None
            self._agent_username = None

        logger.info(
            "准备初始化 Agent: user=%s (ID=%s), logged_in=%s",
            self._agent_username,
            self._agent_user_id,
            user_session.is_logged_in(),
        )

        # 当前流式消息气泡
        self.current_streaming_bubble = None
        self._stream_model_done = False

        # 自动滚动锁：用户上滑查看历史时不强制拉回底部
        self._auto_scroll_enabled = True

        # 表情选择器
        self.emoji_picker = None

        # 线程池 - 优化多线程性能
        self.thread_pool = QThreadPool.globalInstance()
        self.thread_pool.setMaxThreadCount(4)  # 最多4个线程

        # 当前聊天线程
        self.current_chat_thread = None

        # 当前联系人
        self.current_contact = "小雪糕"  # 默认联系人

        # v2.30.14: 统一消息缓存格式 - 使用消息ID作为键
        # 格式: {contact_name: {msg_id: msg}}
        self._message_cache = {}  # 消息缓存（性能优化：避免重复查询数据库）
        self._loaded_message_count = {}  # 已加载消息数量
        self._total_message_count = {}  # 消息总数

        # v2.30.0: 图片分析相关
        self.current_image_analysis = None  # 当前图片分析结果
        self.current_image_path = None  # 当前图片路径
        self.image_recognition_thread = None  # 图片识别线程

        # v2.30.2: 待发送图片列表（支持多图片上传）
        self.pending_images = []  # 存储待发送的图片路径列表

        # v2.32.0: 性能优化器（延迟初始化，在setup_ui后）
        self.performance_optimizer = None

        # v2.48.13: TTS 相关变量（参考 MoeChat 逻辑，统一由多模态模块管理）
        self.tts_enabled = False  # TTS 是否启用
        self.tts_manager = None  # TTS 管理器
        self.audio_player = None  # 音频播放器
        self.tts_stream_processor = None  # 流式文本处理器
        self.tts_workers = []  # TTS 工作线程列表（防止被垃圾回收）
        self.tts_queue = []  # 待合成的句子队列（顺序播放）
        self.tts_busy = False  # 是否有 TTS 任务正在执行

        # 设置窗口大小
        self.resize(1200, 800)

        # 页面切换动画
        self.page_fade_animation = None

        # 设置内容
        self.setup_content()

        # 初始状态：Agent 未就绪前禁用发送，并显示“初始化中”
        self._update_agent_status_label()
        self._set_send_enabled(True)
        QTimer.singleShot(0, self._init_agent_async)

        # 窗口启动动画（默认关闭，避免影响启动与滚动帧率）
        if GUI_ANIMATIONS_ENABLED:
            self.setup_window_animation()

        # v2.48.12: 延迟初始化 TTS（避免阻塞 GUI 启动）
        QTimer.singleShot(1000, self._init_tts_system)

    def setup_content(self):
        """设置内容"""
        # 主布局
        main_layout = QHBoxLayout(self.content_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 左侧图标导航栏
        self.icon_sidebar = LightIconSidebar()
        self.icon_sidebar.chat_clicked.connect(self._on_chat_clicked)
        self.icon_sidebar.settings_clicked.connect(self._on_settings_clicked)
        self.icon_sidebar.contacts_clicked.connect(self._on_contacts_clicked)
        self.icon_sidebar.logout_clicked.connect(self._on_logout_clicked)
        main_layout.addWidget(self.icon_sidebar)

        # 联系人面板（初始折叠）
        self.contacts_panel = ContactsPanel()
        self.contacts_panel.contact_selected.connect(self._on_contact_selected)
        main_layout.addWidget(self.contacts_panel)

        # 使用 QStackedWidget 来切换聊天区域和设置面板
        self.stacked_widget = QStackedWidget()
        main_layout.addWidget(self.stacked_widget)

        # 聊天区域
        chat_area = QWidget()
        chat_main_layout = QHBoxLayout(chat_area)
        chat_main_layout.setContentsMargins(0, 0, 0, 0)
        chat_main_layout.setSpacing(0)

        # 聊天内容区域
        chat_content = QWidget()
        chat_layout = QVBoxLayout(chat_content)
        chat_layout.setContentsMargins(0, 0, 0, 0)
        chat_layout.setSpacing(0)

        chat_main_layout.addWidget(chat_content)

        # 聊天头部 - MD3 Surface Container + 简洁设计
        header = QWidget()
        header.setFixedHeight(72)  # MD3 标准高度
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(24, 16, 24, 16)

        # 头部背景和分隔线
        header.setStyleSheet(
            f"""
            QWidget {{
                background: {MD3_ENHANCED_COLORS['surface_container']};
                border-bottom: 1px solid {MD3_ENHANCED_COLORS['outline_variant']};
            }}
        """
        )

        # 联系人信息
        contact_info = QHBoxLayout()
        contact_info.setSpacing(16)

        # 头像 - v2.22.0 使用自定义头像
        ai_avatar = user_session.get_ai_avatar() if user_session.is_logged_in() else "🐱"

        self.avatar_label = _create_avatar_label_for_header(ai_avatar, 56)
        contact_info.addWidget(self.avatar_label)

        # 添加头像脉冲动画（在线状态指示）
        self._setup_avatar_pulse_animation()

        # 名称和状态
        name_status_layout = QVBoxLayout()
        name_status_layout.setSpacing(4)

        self.name_label = QLabel("小雪糕")
        self.name_label.setStyleSheet(
            f"""
            QLabel {{
                color: {MD3_ENHANCED_COLORS['on_surface']};
                {get_typography_css('title_large')}
                background: transparent;
                font-weight: 600;
            }}
        """
        )
        name_status_layout.addWidget(self.name_label)

        # 状态标签带动画
        self.status_label = QLabel("● 在线")
        self.status_label.setStyleSheet(
            f"""
            QLabel {{
                color: {MD3_ENHANCED_COLORS['primary_60']};
                {get_typography_css('body_medium')}
                background: transparent;
                font-weight: 500;
            }}
        """
        )
        name_status_layout.addWidget(self.status_label)

        contact_info.addLayout(name_status_layout)

        header_layout.addLayout(contact_info)
        header_layout.addStretch()

        # 可选：FPS 监控（用于定位卡顿/验证优化效果）
        if FPS_OVERLAY_ENABLED:
            self._fps_label = QLabel("FPS --")
            self._fps_label.setStyleSheet(
                f"""
                QLabel {{
                    color: {MD3_ENHANCED_COLORS['on_surface_variant']};
                    background: transparent;
                    font-size: 12px;
                    font-weight: 600;
                }}
            """
            )
            header_layout.addWidget(self._fps_label)
            self._setup_fps_overlay()

        # 工具按钮 - MD3 State Layers (Hover: 8%, Pressed: 12%)
        tools_btn = QPushButton("⚙️")
        tools_btn.setFixedSize(48, 48)
        tools_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        tools_btn.setStyleSheet(
            f"""
            QPushButton {{
                background: transparent;
                border: none;
                border-radius: 24px;
                font-size: 22px;
            }}
            QPushButton:hover {{
                background: rgba(38, 166, 154, 20);  /* 8% opacity state layer */
            }}
            QPushButton:pressed {{
                background: rgba(38, 166, 154, 31);  /* 12% opacity state layer */
            }}
        """
        )
        header_layout.addWidget(tools_btn)

        chat_layout.addWidget(header)

        # 消息区域 - MD3 Surface + 简洁设计
        # 添加圆角，与输入框上方圆角呼应
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        # 性能：减少滚动/内容变化时的无效重绘（不同 PyQt 版本可能不提供该 API，需兼容）
        try:
            if hasattr(self.scroll_area, "setViewportUpdateMode"):
                self.scroll_area.setViewportUpdateMode(
                    QAbstractScrollArea.ViewportUpdateMode.MinimalViewportUpdate
                )
        except Exception:
            pass
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setStyleSheet(
            f"""
            QScrollArea {{
                background: {MD3_ENHANCED_COLORS['surface']};
                border: none;
                border-top-left-radius: 16px;
                border-top-right-radius: 16px;
                border-bottom-left-radius: 0px;
                border-bottom-right-radius: 0px;
            }}
            QScrollBar:vertical {{
                background: transparent;
                width: 8px;
                margin: 4px 2px;
            }}
            QScrollBar::handle:vertical {{
                background: {MD3_ENHANCED_COLORS['outline_variant']};
                border-radius: 4px;
                min-height: 40px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {MD3_ENHANCED_COLORS['outline']};
            }}
            QScrollBar::handle:vertical:pressed {{
                background: {MD3_ENHANCED_COLORS['primary']};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background: none;
            }}
        """
        )

        # 消息容器
        self.messages_widget = QWidget()
        self.messages_layout = QVBoxLayout(self.messages_widget)
        self.messages_layout.setContentsMargins(0, 16, 0, 16)
        self.messages_layout.setSpacing(8)
        self.messages_layout.addStretch()

        self.scroll_area.setWidget(self.messages_widget)
        chat_layout.addWidget(self.scroll_area)

        # v2.30.12: 监听滚动事件，实现滚动到顶部自动加载更多
        scrollbar = self.scroll_area.verticalScrollBar()
        scrollbar.valueChanged.connect(self._on_scroll_changed)
        # 内容高度变化时（尤其是流式气泡逐步扩张）用 rangeChanged 驱动一次“跟随到底部”调度，
        # 比在每个 chunk 都主动滚动更稳定且更省资源。
        scrollbar.rangeChanged.connect(self._on_scroll_range_changed)
        self._is_loading_more = False  # 防止重复加载

        # 输入区域 - 动态高度，向上扩张
        input_area = QWidget()
        # 设置最小高度和最大高度，允许动态调整
        self._input_area_min_height = 140  # 单行时的高度
        self._input_area_max_height = 280  # 4行时的最大高度
        input_area.setMinimumHeight(self._input_area_min_height)
        input_area.setMaximumHeight(self._input_area_max_height)

        input_layout = QVBoxLayout(input_area)
        input_layout.setContentsMargins(24, 16, 24, 16)
        input_layout.setSpacing(12)

        # 输入区域背景
        input_area.setStyleSheet(
            f"""
            QWidget {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 {MD3_ENHANCED_COLORS['surface_bright']},
                    stop:1 {MD3_ENHANCED_COLORS['primary_10']}
                );
                border-top: 1px solid {MD3_ENHANCED_COLORS['outline_variant']};
                border-top-left-radius: 0px;
                border-top-right-radius: 0px;
                border-bottom-left-radius: 0px;
                border-bottom-right-radius: 12px;
            }}
        """
        )

        # 保存 input_area 引用，用于动态调整高度
        self.input_area = input_area

        # v2.30.7: 使用新的增强输入框组件（支持内联显示表情包和文件预览）
        self.enhanced_input = EnhancedInputWidget()
        self.enhanced_input.send_requested.connect(self._on_enhanced_send)
        input_layout.addWidget(self.enhanced_input)

        # 保持向后兼容的引用
        self.input_text = self.enhanced_input.input_text
        self.image_preview_container = self.enhanced_input.file_preview_container
        self.pending_images = []  # 保持兼容性

        # v2.30.8: 添加输入框高度属性的引用（向后兼容）
        self._single_line_height = self.input_text._single_line_height
        self._max_lines = self.input_text._max_lines

        # 按钮区域
        button_layout = QHBoxLayout()
        button_layout.setSpacing(12)

        # 表情按钮 - MD3 Outlined Button + State Layers
        self.emoji_btn = MaterialIconButton("emoji_emotions", "表情", size=40, icon_size=22)
        self.emoji_btn.setCheckable(False)
        self.emoji_btn.clicked.connect(self._on_emoji_clicked)
        self.emoji_btn.setStyleSheet(
            f"""
            QPushButton {{
                background: transparent;
                border: none;
                border-radius: 20px;
                color: {MD3_ENHANCED_COLORS['on_surface_variant']};
            }}
            QPushButton:hover {{
                background: rgba(38, 166, 154, 20);  /* 8% state layer */
                color: {MD3_ENHANCED_COLORS['primary']};
            }}
            QPushButton:pressed {{
                background: rgba(38, 166, 154, 31);  /* 12% state layer */
            }}
        """
        )
        button_layout.addWidget(self.emoji_btn)

        # 附件按钮 - MD3 Outlined Button + State Layers
        self.attach_btn = MaterialIconButton("attach_file", "附件", size=40, icon_size=22)
        self.attach_btn.setCheckable(False)
        self.attach_btn.clicked.connect(self._on_attach_clicked)
        self.attach_btn.setStyleSheet(
            f"""
            QPushButton {{
                background: transparent;
                border: none;
                border-radius: 20px;
                color: {MD3_ENHANCED_COLORS['on_surface_variant']};
            }}
            QPushButton:hover {{
                background: rgba(38, 166, 154, 20);  /* 8% state layer */
                color: {MD3_ENHANCED_COLORS['primary']};
            }}
            QPushButton:pressed {{
                background: rgba(38, 166, 154, 31);  /* 12% state layer */
            }}
        """
        )
        button_layout.addWidget(self.attach_btn)

        button_layout.addStretch()

        # 发送按钮 - 使用 Material Design 图标，增强视觉效果
        send_btn_container = QWidget()
        send_btn_layout = QHBoxLayout(send_btn_container)
        send_btn_layout.setContentsMargins(16, 0, 16, 0)
        send_btn_layout.setSpacing(8)

        # 发送图标
        from PyQt6.QtGui import QFont

        send_icon = QLabel(MATERIAL_ICONS["send"])
        send_icon_font = QFont("Material Symbols Outlined")
        send_icon_font.setPixelSize(20)
        send_icon.setFont(send_icon_font)
        send_icon.setStyleSheet(
            f"""
            QLabel {{
                color: {MD3_ENHANCED_COLORS['on_primary']};
                background: transparent;
            }}
        """
        )
        send_btn_layout.addWidget(send_icon)

        # 发送文本
        send_text = QLabel("发送")
        send_text.setStyleSheet(
            f"""
            QLabel {{
                color: {MD3_ENHANCED_COLORS['on_primary']};
                background: transparent;
                font-size: 15px;
                font-weight: 600;
            }}
        """
        )
        send_btn_layout.addWidget(send_text)

        # 将容器转换为按钮 - MD3 Filled Button + Elevation Level 1
        self.send_btn = QPushButton()
        self.send_btn.setFixedSize(120, 48)
        self.send_btn.setLayout(send_btn_layout)
        self.send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.send_btn.setStyleSheet(
            f"""
            QPushButton {{
                background: {MD3_ENHANCED_COLORS['primary']};
                border: none;
                border-radius: 24px;
            }}
            QPushButton:hover {{
                background: {MD3_ENHANCED_COLORS['primary_60']};
            }}
            QPushButton:pressed {{
                background: {MD3_ENHANCED_COLORS['primary_70']};
            }}
            QPushButton:disabled {{
                background: {MD3_ENHANCED_COLORS['surface_container']};
            }}
        """
        )

        # 添加 MD3 Elevation Level 1 阴影效果
        send_shadow = QGraphicsDropShadowEffect(self.send_btn)
        send_shadow.setBlurRadius(3)  # MD3 Level 1
        send_shadow.setXOffset(0)
        send_shadow.setYOffset(1)  # MD3 Level 1
        send_shadow.setColor(QColor(0, 0, 0, 38))  # 0.15 * 255
        self.send_btn.setGraphicsEffect(send_shadow)

        self.send_btn.clicked.connect(self._send_message)
        button_layout.addWidget(self.send_btn)

        input_layout.addLayout(button_layout)

        chat_layout.addWidget(input_area)

        # 将聊天区域添加到 StackedWidget
        self.stacked_widget.addWidget(chat_area)

        # 设置面板改为懒加载：避免启动即构建大体量 UI（settings_panel.py 较重）
        self.settings_panel = None

        # 默认显示聊天区域
        self.stacked_widget.setCurrentIndex(0)

        # ==================== GUI 性能优化集成 v2.32.0 ====================
        try:
            # v2.32.0: 性能优化器已在__init__中导入
            # 初始化性能优化器
            self.performance_optimizer = ChatWindowOptimizer(
                scroll_area=self.scroll_area,
                enable_gpu=True,
                enable_memory_management=True,
                max_messages=200,
            )

            # 应用优化到现有窗口
            self.performance_optimizer.optimize_existing_window(self)

            logger.info("GUI 性能优化已启用（v2.32.0）")
        except Exception as e:
            logger.warning("GUI 性能优化启用失败: %s", e)
            self.performance_optimizer = None
        # ==================== 集成完成 ====================

    def showEvent(self, event):
        """窗口显示事件 - v2.29.17 确保输入框初始高度正确"""
        super().showEvent(event)
        # 确保输入框保持单行高度
        if hasattr(self, 'input_text') and hasattr(self, '_single_line_height'):
            self.input_text.setFixedHeight(self._single_line_height)
        if hasattr(self, 'input_area') and hasattr(self, '_input_area_min_height'):
            self.input_area.setFixedHeight(self._input_area_min_height)

    def eventFilter(self, obj, event):
        """事件过滤器 - v2.29.11 优化：Enter发送，Shift+Enter换行，优化逻辑"""
        if obj == self.input_text and event.type() == event.Type.KeyPress:
            key = event.key()
            # v2.29.11: 合并Enter和Return的判断，提升可读性
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                # Shift+Enter：插入换行符（默认行为）
                if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                    return False
                # Enter：发送消息（仅当有内容时）
                if self.input_text.toPlainText().strip():
                    self._send_message()
                return True
        return super().eventFilter(obj, event)

    def _set_send_enabled(self, enabled: bool) -> None:
        """统一管理发送按钮状态，避免在 Agent 未就绪时误启用。"""
        try:
            can_send = bool(enabled) and (self.agent is not None) and not bool(
                getattr(self, "_agent_initializing", False)
            )
            self.send_btn.setEnabled(can_send)
        except Exception:
            pass

    def _update_agent_status_label(self) -> None:
        """根据 Agent 状态刷新头部状态文本。"""
        try:
            if not hasattr(self, "status_label") or self.status_label is None:
                return
            if bool(getattr(self, "_agent_initializing", False)):
                self.status_label.setText("● 初始化中")
                return
            if self.agent is None or bool(getattr(self, "_agent_init_failed", False)):
                self.status_label.setText("● 离线")
                return
            self.status_label.setText("● 在线")
        except Exception:
            pass

    def _init_agent_async(self) -> None:
        """后台初始化 Agent，避免启动卡顿；初始化完成后再允许发送。"""
        try:
            thread = getattr(self, "_agent_init_thread", None)
            if thread is not None and thread.isRunning():
                return
        except Exception:
            pass

        self._agent_initializing = True
        self._agent_init_failed = False
        self._update_agent_status_label()
        self._set_send_enabled(True)

        thread = AgentInitThread(user_id=getattr(self, "_agent_user_id", None))
        thread.agent_ready.connect(self._on_agent_ready)
        thread.error.connect(self._on_agent_init_failed)
        self._agent_init_thread = thread
        thread.start()

    def _cleanup_agent_init_thread(self) -> None:
        thread = getattr(self, "_agent_init_thread", None)
        self._agent_init_thread = None
        if thread is None:
            return
        try:
            thread.deleteLater()
        except Exception:
            pass

    def _on_agent_ready(self, agent: object) -> None:
        self.agent = agent
        self._agent_initializing = False
        self._agent_init_failed = False
        self._cleanup_agent_init_thread()

        # 让设置面板（若已创建）获取到最新 agent
        try:
            if getattr(self, "settings_panel", None) is not None:
                self.settings_panel.agent = self.agent
        except Exception:
            pass

        self._update_agent_status_label()
        self._set_send_enabled(True)
        try:
            show_toast(self, "AI 助手已就绪", Toast.TYPE_SUCCESS, duration=1500)
        except Exception:
            pass

    def _on_agent_init_failed(self, error: str) -> None:
        self.agent = None
        self._agent_initializing = False
        self._agent_init_failed = True
        self._cleanup_agent_init_thread()

        self._update_agent_status_label()
        self._set_send_enabled(True)

        logger.error("Agent 初始化失败: %s", error)
        try:
            msg = (error or "").splitlines()[0] if error else "未知错误"
            show_toast(self, f"AI 初始化失败: {msg}", Toast.TYPE_ERROR, duration=3000)
        except Exception:
            pass

    def _adjust_input_height(self):
        """根据内容自动调整输入框高度 - v2.29.17 优化：彻底修复初始化时高度异常问题

        规则：
        - 单行时：56px (MD3 标准单行高度)
        - 多行时：自动扩张，每行约 24px (line-height: 1.5 * 16px)
        - 最多 4 行：56 + 24*3 = 128px
        - 超过 4 行：固定高度，启用滚动条
        - 扩张方向：向上扩张（固定底部位置）

        v2.29.17 修复：
        - 使用setFixedHeight而不是setMinimum/MaximumHeight，避免自动扩展
        - 添加初始化检查，避免初始化时错误调整高度
        - 添加文档高度合理性检查，避免异常值导致错误调整
        - 空内容时强制保持单行高度，不进行任何计算
        """
        # v2.29.16: 如果输入框未初始化，不调整高度
        if not hasattr(self, '_input_initialized') or not self._input_initialized:
            return

        # v2.29.17: 获取文本内容，如果为空则直接保持单行高度
        text_content = self.input_text.toPlainText()
        if not text_content:
            # 空内容时强制保持单行高度
            if self.input_text.height() != self._single_line_height:
                self.input_text.setFixedHeight(self._single_line_height)
            if self.input_area.height() != self._input_area_min_height:
                self.input_area.setFixedHeight(self._input_area_min_height)
            return

        # v2.29.11: 缓存常量，避免重复计算
        PADDING = 32  # 上下 padding 各 16px
        BUTTON_AREA_HEIGHT = 48
        MARGINS = 32
        SPACING = 12

        # 获取文档高度并计算需要的高度
        doc_height = self.input_text.document().size().height()

        # v2.29.17: 检查文档高度是否合理（有内容时才检查）
        # 如果文档高度异常大（>500），说明文档计算错误，使用行数估算
        if doc_height > 500:
            # 使用行数估算高度
            line_count = text_content.count('\n') + 1
            estimated_height = self._single_line_height + (line_count - 1) * 24
            content_height = min(estimated_height, self._single_line_height * self._max_lines)
        else:
            content_height = int(doc_height + PADDING)

        # v2.29.11: 使用clamp函数简化范围限制
        new_input_height = max(
            self._single_line_height,
            min(content_height, self._single_line_height * self._max_lines),
        )

        # 计算 input_area 的新高度
        new_area_height = new_input_height + BUTTON_AREA_HEIGHT + MARGINS + SPACING

        # 限制 input_area 高度
        new_area_height = max(
            self._input_area_min_height, min(new_area_height, self._input_area_max_height)
        )

        # v2.29.11: 只在高度真正改变时才更新，避免不必要的重绘
        if self.input_text.height() != new_input_height:
            self.input_text.setFixedHeight(new_input_height)
        if self.input_area.height() != new_area_height:
            self.input_area.setFixedHeight(new_area_height)

    def _send_message(self):
        """发送消息 - v2.30.2 优化：支持多图片和文本一起发送"""
        # v2.29.11: 提前获取并验证消息
        message = self.input_text.toPlainText().strip()

        # v2.30.2: 检查是否有消息或图片
        has_pending_images = len(self.pending_images) > 0
        if not message and not has_pending_images:
            return

        # Agent 未就绪时不允许发送：避免清空输入/插入气泡后又失败导致体验问题
        if self.agent is None or bool(getattr(self, "_agent_initializing", False)):
            if bool(getattr(self, "_agent_initializing", False)):
                show_toast(self, "AI 正在初始化，请稍候…", Toast.TYPE_INFO, duration=1500)
            else:
                show_toast(self, "AI 未就绪，请检查配置后重试", Toast.TYPE_ERROR, duration=2500)
            self._set_send_enabled(True)
            return

        # v2.29.11: 优化线程停止逻辑
        if self.current_chat_thread is not None and self.current_chat_thread.isRunning():
            self.current_chat_thread.stop()
            self.current_chat_thread.wait(1000)  # 等待最多1秒

        # v2.29.11: 批量更新UI，减少重绘
        self.input_text.setUpdatesEnabled(False)
        self.input_text.clear()
        self.input_text.setFixedHeight(self._single_line_height)
        self.input_text.setUpdatesEnabled(True)
        self.input_area.setFixedHeight(self._input_area_min_height)

        # v2.30.2: 先显示图片消息（如果有）
        if has_pending_images:
            for img_path in self.pending_images:
                self._add_image_message(img_path, is_user=True)

        # 添加用户消息（原始消息，包含表情包标记）
        if message:
            self._add_message(message, is_user=True)

        # v2.30.2: 如果有图片，开始批量识别
        if has_pending_images:
            self._process_multiple_images(self.pending_images.copy(), message)
            # 清空待发送列表和预览区域
            self.pending_images.clear()
            # 清空预览区域
            while self.image_preview_content_layout.count() > 1:  # 保留stretch
                item = self.image_preview_content_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            self.image_preview_container.setVisible(False)
            return

        # 重置流式渲染状态（上一轮残留会影响逐字显示/动画）
        try:
            self._reset_stream_render_state()
        except Exception:
            pass
        self._stream_model_done = False

        # 显示打字指示器
        self._show_typing_indicator()

        # v2.29.11: 提前检查Agent，避免不必要的处理
        if self.agent is None:
            self._hide_typing_indicator()
            self._add_message("抱歉，AI 助手初始化失败，请检查配置。", is_user=False)
            return

        # 将消息中的表情包标记转换为描述性文本（供AI理解）
        ai_message = self._convert_stickers_to_description(message)

        # v2.30.0: 获取图片分析结果（如果有）
        image_analysis = self.current_image_analysis
        image_path = self.current_image_path

        # 清除图片分析缓存（避免影响下一次对话）
        self.current_image_analysis = None
        self.current_image_path = None

        # v2.29.11: 创建并启动聊天线程
        # v2.30.0: 传递图片分析结果
        self.current_chat_thread = ChatThread(
            self.agent,
            ai_message,
            image_path=image_path,
            image_analysis=image_analysis
        )
        self.current_chat_thread.chunk_received.connect(self._on_chunk_received)
        self.current_chat_thread.finished.connect(self._on_chat_finished)
        self.current_chat_thread.error.connect(self._on_chat_error)
        self.current_chat_thread.start()

        # 禁用发送按钮
        self.send_btn.setEnabled(False)

    def _add_message(
        self,
        message: str,
        is_user: bool = True,
        save_to_db: bool = True,
        with_animation: bool = True,
    ):
        """添加消息 - v2.29.10 优化：使用预编译正则表达式

        Args:
            message: 消息内容（可能包含 [STICKER:path] 标记）
            is_user: 是否为用户消息
            save_to_db: 是否保存到数据库（加载历史消息时设为False）
            with_animation: 是否显示入场动画（加载历史消息时设为False以避免闪烁）
        """
        bulk_loading = bool(getattr(self, "_bulk_loading_messages", False))

        # v2.30.8: 防止添加空消息
        if not message or not message.strip():
            logger.warning("尝试添加空消息，已忽略: is_user=%s", is_user)
            return

        # v2.29.10: 使用预编译的正则表达式，提升性能
        has_stickers = bool(STICKER_PATTERN.search(message))
        enable_entry_animation = bool(with_animation and GUI_ANIMATIONS_ENABLED)

        if has_stickers:
            # 混合消息：需要分段处理
            self._add_mixed_message(message, is_user, with_animation)
        elif message.startswith("[STICKER:") and message.endswith("]"):
            # 纯表情包消息（向后兼容）
            sticker_path = message[9:-1]
            bubble = LightImageMessageBubble(
                sticker_path,
                is_user,
                is_sticker=True,
                with_animation=enable_entry_animation,
                enable_shadow=with_animation,
            )
            self.messages_layout.insertWidget(self.messages_layout.count() - 1, bubble)

            if not bulk_loading:
                # v2.30.8: 强制显示气泡
                bubble.show()
                self.messages_layout.update()
                self._schedule_messages_geometry_update()
        else:
            # 纯文本消息
            bubble = LightMessageBubble(message, is_user, enable_shadow=with_animation)

            # v2.30.8: 计算插入位置 - 总是插入到最后（stretch之前）
            insert_position = self.messages_layout.count() - 1

            self.messages_layout.insertWidget(insert_position, bubble)

            if not bulk_loading:
                # v2.30.8: 强制显示气泡
                bubble.show()  # 确保气泡可见

                # v2.30.13: 立即更新布局，避免错位
                self.messages_layout.update()
                self._schedule_messages_geometry_update()
                if enable_entry_animation:
                    bubble.show_with_animation()

        # 保存到数据库和缓存
        if save_to_db:
            if user_session.is_logged_in():
                try:
                    role = "user" if is_user else "assistant"
                    saved = user_session.add_message(self.current_contact, role, message)
                    logger.debug("消息已保存: %s - %s", self.current_contact, role)

                    # v2.30.14: 更新缓存（注意：这里没有msg_id，因为是新消息）
                    # 缓存将在下次加载历史消息时更新
                    # 这里不再维护缓存，避免不一致
                    if saved:
                        contact = self.current_contact
                        if contact:
                            if not hasattr(self, "_loaded_message_count"):
                                self._loaded_message_count = {}
                            if not hasattr(self, "_total_message_count"):
                                self._total_message_count = {}
                            self._loaded_message_count[contact] = self._loaded_message_count.get(contact, 0) + 1
                            self._total_message_count[contact] = self._total_message_count.get(contact, 0) + 1
                except Exception as e:
                    from src.utils.exceptions import handle_exception

                    handle_exception(e, logger, "保存消息到数据库失败")

        if not bulk_loading:
            self._enforce_shadow_budget()
            # 长对话保护：只在用户位于底部（允许自动滚动）时裁剪旧消息，避免影响用户阅读历史
            self._schedule_trim_rendered_messages(force=False)

        if bulk_loading:
            return

        # 滚动策略：用户消息强制到底部；助手消息仅在接近底部时自动跟随（避免用户上滑时被拉回）
        if is_user:
            self._ensure_scroll_to_bottom()
        else:
            self._scroll_to_bottom()

    def _disable_shadow_recursive(self, widget) -> None:
        """递归关闭旧消息的阴影效果，降低大量消息时的渲染开销。"""
        if widget is None:
            return

        # 兜底：如果某个 widget 直接挂了 DropShadowEffect，但没有实现 disable_shadow，也能被预算机制关闭。
        try:
            effect = widget.graphicsEffect() if hasattr(widget, "graphicsEffect") else None
            if isinstance(effect, QGraphicsDropShadowEffect):
                widget.setGraphicsEffect(None)
        except Exception:
            pass

        if hasattr(widget, "disable_shadow"):
            try:
                widget.disable_shadow()
                return
            except Exception:
                pass

        # 容器（混合消息）
        layout = widget.layout() if hasattr(widget, "layout") else None
        if layout is None:
            return

        for i in range(layout.count()):
            item = layout.itemAt(i)
            child = item.widget() if item else None
            if child is not None:
                self._disable_shadow_recursive(child)

    def _enforce_shadow_budget(self) -> None:
        """
        限制带阴影的消息数量（保留最新 N 条的阴影），避免长对话导致 GPU/CPU 开销线性增长。
        """
        shadow_budget = SHADOW_BUDGET
        # layout 的最后一个是 stretch
        message_count = self.messages_layout.count() - 1
        if message_count <= shadow_budget:
            return

        index_to_disable = message_count - shadow_budget - 1
        if index_to_disable < 0:
            return

        item = self.messages_layout.itemAt(index_to_disable)
        widget = item.widget() if item else None
        if widget is None:
            return

        self._disable_shadow_recursive(widget)

    def _schedule_trim_rendered_messages(self, *, force: bool = False) -> None:
        """调度裁剪渲染消息（批量执行，避免一次性删除大量 widget 卡顿）。"""
        if MAX_RENDERED_MESSAGES <= 0:
            return
        if getattr(self, "_bulk_loading_messages", False):
            return
        if not force and not getattr(self, "_auto_scroll_enabled", True):
            return

        # 阈值未触发时不必调度（避免每条消息都排队一个 singleShot）
        if not force:
            try:
                message_count = self.messages_layout.count() - 1  # 末尾是 stretch
            except Exception:
                message_count = 0
            if message_count <= (MAX_RENDERED_MESSAGES + TRIM_RENDERED_MESSAGES_BATCH - 1):
                return

        if getattr(self, "_trim_messages_pending", False):
            if force:
                self._trim_messages_force = True
            return

        self._trim_messages_pending = True
        self._trim_messages_force = bool(force)
        QTimer.singleShot(0, self._trim_rendered_messages_batch)

    def _trim_rendered_messages_batch(self) -> None:
        """裁剪旧消息（移除顶部最旧的若干条），保持滚动流畅。"""
        pending = bool(getattr(self, "_trim_messages_pending", False))
        if pending:
            self._trim_messages_pending = False

        force = bool(getattr(self, "_trim_messages_force", False))
        self._trim_messages_force = False

        max_messages = int(MAX_RENDERED_MESSAGES)
        if max_messages <= 0:
            return
        if getattr(self, "_bulk_loading_messages", False):
            return
        if not force and not getattr(self, "_auto_scroll_enabled", True):
            return

        message_count = self.messages_layout.count() - 1  # 末尾是 stretch
        over = message_count - max_messages
        if over <= 0:
            return

        batch_size = int(TRIM_RENDERED_MESSAGES_BATCH)
        # 频率控制：允许消息数量在 [max, max+batch) 之间小幅波动，减少频繁删 widget 导致的抖动
        if not force and over < batch_size:
            return

        remove_target = min(int(over), batch_size)
        removed = 0

        scrollbar = self.scroll_area.verticalScrollBar()
        scroll_widget = self.scroll_area.widget()
        old_scrollbar_signals = False
        try:
            try:
                old_scrollbar_signals = scrollbar.blockSignals(True)
            except Exception:
                old_scrollbar_signals = False

            # 删除期间禁用更新，避免频繁重绘
            self.scroll_area.setUpdatesEnabled(False)
            if scroll_widget is not None:
                scroll_widget.setUpdatesEnabled(False)

            while removed < remove_target and self.messages_layout.count() > 1:
                item = self.messages_layout.takeAt(0)
                widget = item.widget() if item else None
                if widget is None:
                    continue
                # 极端兜底：避免误删正在流式的气泡
                if widget is getattr(self, "current_streaming_bubble", None):
                    self.messages_layout.insertWidget(self.messages_layout.count() - 1, widget)
                    break
                try:
                    if hasattr(widget, "cleanup"):
                        widget.cleanup()
                except Exception:
                    pass
                try:
                    widget.setParent(None)
                except Exception:
                    pass
                widget.deleteLater()
                removed += 1
        finally:
            if scroll_widget is not None:
                scroll_widget.setUpdatesEnabled(True)
            self.scroll_area.setUpdatesEnabled(True)
            try:
                scrollbar.blockSignals(old_scrollbar_signals)
            except Exception:
                pass

        if removed <= 0:
            return

        # 裁剪属于“UI 侧卸载旧消息”，loaded_count 需要同步减少，否则分页 offset 会跳过缺失段
        contact = getattr(self, "current_contact", None)
        if contact and hasattr(self, "_loaded_message_count"):
            try:
                current_loaded = int(self._loaded_message_count.get(contact, 0))
                self._loaded_message_count[contact] = max(0, current_loaded - removed)
            except Exception:
                pass

        self.messages_layout.update()
        self._schedule_messages_geometry_update()
        if getattr(self, "_auto_scroll_enabled", True):
            self._ensure_scroll_to_bottom()

        # 如果仍超出预算，继续分批裁剪（下一轮事件循环执行）
        if (self.messages_layout.count() - 1) > max_messages:
            self._schedule_trim_rendered_messages(force=force)

    def _add_mixed_message(self, message: str, is_user: bool, with_animation: bool):
        """添加混合消息（文字+表情包）- v2.29.9 优化：性能和内存优化

        Args:
            message: 混合消息内容
            is_user: 是否为用户消息
            with_animation: 是否显示动画
        """
        from PyQt6.QtWidgets import QWidget, QHBoxLayout
        try:
            # 创建容器
            container = QWidget()
            layout = QHBoxLayout(container)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(8)

            enable_entry_animation = bool(with_animation and GUI_ANIMATIONS_ENABLED)

            # v2.29.10: 使用预编译的正则表达式，提升性能
            parts = STICKER_PATTERN.split(message)

            # v2.29.9: 批量创建组件，减少布局更新
            widgets = []
            for i, part in enumerate(parts):
                if not part:
                    continue

                if i % 2 == 0:
                    # 文字部分
                    if part.strip():
                        text_bubble = LightMessageBubble(part, is_user, enable_shadow=with_animation)
                        if enable_entry_animation:
                            text_bubble.show_with_animation()
                        widgets.append(text_bubble)
                else:
                    # 表情包部分（part 是路径）
                    sticker_bubble = LightImageMessageBubble(
                        part,
                        is_user,
                        is_sticker=True,
                        with_animation=enable_entry_animation,
                        enable_shadow=with_animation,
                    )
                    widgets.append(sticker_bubble)

            # v2.29.9: 批量添加组件，减少重绘
            container.setUpdatesEnabled(False)
            for widget in widgets:
                layout.addWidget(widget)
            layout.addStretch()
            container.setUpdatesEnabled(True)

            # 添加到消息列表
            self.messages_layout.insertWidget(self.messages_layout.count() - 1, container)

        except Exception as e:
            logger.error("添加混合消息失败: %s", e, exc_info=True)
            # 降级处理：作为纯文本消息添加
            enable_entry_animation = bool(with_animation and GUI_ANIMATIONS_ENABLED)
            bubble = LightMessageBubble(message, is_user, enable_shadow=with_animation)
            if enable_entry_animation:
                bubble.show_with_animation()
            self.messages_layout.insertWidget(self.messages_layout.count() - 1, bubble)

    def _add_image_message(self, image_path: str, is_user: bool = True):
        """添加图片消息 - v2.18.1 新增

        Args:
            image_path: 图片文件路径
            is_user: 是否为用户消息
        """
        enable_entry_animation = bool(GUI_ANIMATIONS_ENABLED)
        bubble = LightImageMessageBubble(
            image_path,
            is_user,
            with_animation=enable_entry_animation,
            enable_shadow=True,
        )
        self.messages_layout.insertWidget(self.messages_layout.count() - 1, bubble)
        # 动画会持续触发重绘；默认禁用入场动画时，直接滚动到底部即可
        if enable_entry_animation:
            QTimer.singleShot(200, self._ensure_scroll_to_bottom)
        else:
            self._ensure_scroll_to_bottom()

    @throttle(150)
    def _scroll_to_bottom(self):
        """滚动到底部（节流优化，最多每150ms滚动一次）- v2.48.6 优化：添加平滑滚动"""
        if not getattr(self, "_auto_scroll_enabled", True):
            return
        self._smooth_scroll_to_bottom()

    def _ensure_scroll_to_bottom(self):
        """确保滚动到底部（绕过节流限制）- v2.48.6 优化：添加平滑滚动"""
        try:
            # 优先走性能优化器的批量滚动（更省资源，避免频繁创建滚动动画）
            if getattr(self, "performance_optimizer", None) is not None:
                self.performance_optimizer.schedule_scroll(force=True)
                return
        except Exception:
            # 性能优化器异常不应影响正常滚动
            pass

        self._smooth_scroll_to_bottom()

    def _smooth_scroll_to_bottom(self):
        """平滑滚动到底部 - v2.48.6 新增

        使用动画平滑滚动到底部，提升用户体验
        """
        scrollbar = self.scroll_area.verticalScrollBar()
        current_value = scrollbar.value()
        target_value = scrollbar.maximum()

        # 性能优先：默认禁用平滑滚动（会持续触发重绘，长对话很容易掉帧）
        if not SMOOTH_SCROLL_ENABLED:
            scrollbar.setValue(target_value)
            return

        # 如果已经在底部或距离很近（<20px），直接跳转
        if abs(target_value - current_value) < 20:
            scrollbar.setValue(target_value)
            return

        # 创建平滑滚动动画
        if not hasattr(self, '_scroll_animation'):
            self._scroll_animation = QPropertyAnimation(scrollbar, b"value")
            self._scroll_animation.setDuration(200)  # 200ms 平滑滚动
            self._scroll_animation.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._scroll_animation.setStartValue(current_value)
        self._scroll_animation.setEndValue(target_value)
        self._scroll_animation.start()

    def _schedule_messages_geometry_update(self) -> None:
        """合并消息区的 updateGeometry 调用，避免触发同步布局抖动。"""
        if getattr(self, "_messages_geometry_update_pending", False):
            return
        self._messages_geometry_update_pending = True

        def do_update() -> None:
            self._messages_geometry_update_pending = False
            try:
                widget = self.scroll_area.widget() if hasattr(self, "scroll_area") else None
                if widget is not None:
                    widget.updateGeometry()
            except Exception:
                pass

        # 延迟到下一轮事件循环，让 Qt 先完成插入/尺寸 hint 计算
        QTimer.singleShot(0, do_update)

    def _show_typing_indicator(self):
        """显示打字指示器 - v2.30.8 修复：确保插入到正确位置"""
        # 先移除旧的打字指示器（如果存在）
        if hasattr(self, "typing_indicator") and self.typing_indicator is not None:
            self._hide_typing_indicator()

        self.typing_indicator = LightTypingIndicator()
        # v2.30.8: 插入到最后（stretch之前）
        insert_position = self.messages_layout.count() - 1
        logger.debug("显示打字指示器: position=%s, total_count=%s", insert_position, self.messages_layout.count())
        self.messages_layout.insertWidget(insert_position, self.typing_indicator)

        # v2.30.8: 强制显示和更新
        self.typing_indicator.show()
        self.messages_layout.update()
        self._schedule_messages_geometry_update()

    def _ensure_stream_render_state(self) -> None:
        """初始化流式渲染队列与定时器（用于更丝滑的“逐步显示”效果）。"""
        if not hasattr(self, "_stream_render_queue"):
            self._stream_render_queue = deque()
            self._stream_render_pending = ""
            self._stream_render_pending_pos = 0
            self._stream_render_remaining = 0

        if not hasattr(self, "_stream_render_timer"):
            self._stream_render_timer = QTimer()
            self._stream_render_timer.setInterval(STREAM_RENDER_INTERVAL_MS)
            self._stream_render_timer.timeout.connect(self._drain_stream_render_queue)

    def _reset_stream_render_state(self) -> None:
        """停止流式渲染并清空队列（用于结束/错误/切换对话时）。"""
        timer = getattr(self, "_stream_render_timer", None)
        if timer is not None and timer.isActive():
            timer.stop()

        if hasattr(self, "_stream_render_queue"):
            try:
                self._stream_render_queue.clear()
            except Exception:
                self._stream_render_queue = deque()

        self._stream_render_pending = ""
        self._stream_render_pending_pos = 0
        self._stream_render_remaining = 0

    def _schedule_stream_scroll(self) -> None:
        """轻量调度滚动到底部（保持视图跟随，但避免信号风暴）。"""
        if not getattr(self, "_auto_scroll_enabled", True):
            return
        if getattr(self, "performance_optimizer", None) is not None:
            try:
                self.performance_optimizer.schedule_scroll()
                return
            except Exception:
                pass

        if not hasattr(self, "_scroll_timer"):
            self._scroll_timer = QTimer()
            self._scroll_timer.setSingleShot(True)
            # 流式期间更强调“跟随”，这里绕过 _scroll_to_bottom 的节流限制
            self._scroll_timer.timeout.connect(self._ensure_scroll_to_bottom)

        # 关键：不要在高频调用下重复 start()（会不断重置计时器，导致滚动延迟到“最后才跳一下”）
        if self._scroll_timer.isActive():
            return
        self._scroll_timer.start(STREAM_SCROLL_INTERVAL_MS)

    def _get_stream_render_budget(self) -> int:
        """根据积压量动态调整每帧输出量：小积压更细腻，大积压自动加速追赶。"""
        if STREAM_RENDER_TYPEWRITER:
            return 1
        backlog = int(getattr(self, "_stream_render_remaining", 0))
        base = int(STREAM_RENDER_BASE_CHARS)
        max_chars = int(STREAM_RENDER_MAX_CHARS)
        # 平滑加速：积压越大，每帧输出越多；积压较小时保持“ChatGPT 风格”的细粒度流式观感。
        budget = max(base, backlog // 50)
        return max(1, min(max_chars, budget))

    def _enqueue_stream_render_text(self, text: str) -> None:
        """将文本入队，交由渲染定时器按帧追加到气泡。"""
        text = text or ""
        if not text:
            return
        self._ensure_stream_render_state()

        queue = getattr(self, "_stream_render_queue", None)
        if queue is None:
            self._stream_render_queue = deque()
            queue = self._stream_render_queue

        for segment in self._split_large_text(text, max_len=2048):
            if not segment:
                continue
            queue.append(segment)
            self._stream_render_remaining += len(segment)

        timer = getattr(self, "_stream_render_timer", None)
        if timer is not None and not timer.isActive():
            timer.start()

    def _take_stream_render_text(self, max_chars: int) -> str:
        """从队列中取出最多 max_chars 字符，并维护 remaining 计数。"""
        if max_chars <= 0 or int(getattr(self, "_stream_render_remaining", 0)) <= 0:
            return ""

        queue = getattr(self, "_stream_render_queue", None)
        if queue is None:
            return ""

        pending = str(getattr(self, "_stream_render_pending", ""))
        pos = int(getattr(self, "_stream_render_pending_pos", 0))

        out_parts: list[str] = []
        budget = int(max_chars)
        while budget > 0 and int(getattr(self, "_stream_render_remaining", 0)) > 0:
            if not pending:
                if not queue:
                    break
                pending = queue.popleft()
                pos = 0

            available = len(pending) - pos
            if available <= 0:
                pending = ""
                pos = 0
                continue

            take = min(budget, available)
            out_parts.append(pending[pos : pos + take])
            pos += take
            budget -= take
            self._stream_render_remaining -= take

            if pos >= len(pending):
                pending = ""
                pos = 0

        self._stream_render_pending = pending
        self._stream_render_pending_pos = pos
        return "".join(out_parts)

    def _drain_stream_render_queue(self) -> None:
        """按帧把队列里的文本追加到气泡（默认 30fps），实现更自然的流式观感。"""
        if self.current_streaming_bubble is None:
            self._reset_stream_render_state()
            return

        text = self._take_stream_render_text(self._get_stream_render_budget())
        if text:
            self.current_streaming_bubble.append_text(text)
            self._schedule_stream_scroll()

        if int(getattr(self, "_stream_render_remaining", 0)) <= 0:
            timer = getattr(self, "_stream_render_timer", None)
            if timer is not None and timer.isActive():
                timer.stop()
            if getattr(self, "_stream_model_done", False):
                QTimer.singleShot(0, self._finalize_stream_response)

    def _drain_stream_render_all(self) -> None:
        """在收尾阶段一次性排空渲染队列，确保保存/落库的文本完整一致。"""
        timer = getattr(self, "_stream_render_timer", None)
        if timer is not None and timer.isActive():
            timer.stop()

        if self.current_streaming_bubble is None:
            self._reset_stream_render_state()
            return

        while int(getattr(self, "_stream_render_remaining", 0)) > 0:
            text = self._take_stream_render_text(4096)
            if not text:
                break
            self.current_streaming_bubble.append_text(text)

        self._schedule_stream_scroll()

    def _finalize_stream_response(self) -> None:
        """当模型完成且渲染队列已清空后，执行最终收尾（finish/落库/解锁输入）。"""
        # 兼容：若模型未输出任何 chunk，打字指示器可能仍在
        try:
            self._hide_typing_indicator()
        except Exception:
            pass

        if self.current_streaming_bubble is None:
            self._reset_stream_render_state()
            self._stream_model_done = False
            self._set_send_enabled(True)
            return

        full_response = self.current_streaming_bubble.message_text.toPlainText()

        # 最终过滤工具信息（确保保存到数据库的内容也是干净的）
        if full_response and self._needs_tool_filter(full_response):
            filtered_response = self._filter_tool_info_safe(full_response)
            if filtered_response != full_response:
                full_response = filtered_response
                try:
                    self.current_streaming_bubble.message_text.setPlainText(full_response)
                except Exception:
                    pass

        # 完成流式输出（停止 caret、补齐阴影、最终高度）
        try:
            self.current_streaming_bubble.finish()
        except Exception:
            pass
        self.current_streaming_bubble = None
        self._reset_stream_render_state()
        self._stream_model_done = False

        # v2.49.0: 流式气泡也是“新增消息”，需要纳入阴影预算管理，否则长对话会持续掉帧
        try:
            self._enforce_shadow_budget()
        except Exception:
            pass
        try:
            self._schedule_trim_rendered_messages(force=False)
        except Exception:
            pass

        # 保存AI回复到数据库
        if user_session.is_logged_in() and full_response.strip():
            try:
                saved = user_session.add_message(self.current_contact, "assistant", full_response)
                logger.debug("AI回复已保存: %s - assistant", self.current_contact)
                if saved:
                    contact = self.current_contact
                    if contact:
                        if not hasattr(self, "_loaded_message_count"):
                            self._loaded_message_count = {}
                        if not hasattr(self, "_total_message_count"):
                            self._total_message_count = {}
                        self._loaded_message_count[contact] = self._loaded_message_count.get(contact, 0) + 1
                        self._total_message_count[contact] = self._total_message_count.get(contact, 0) + 1
            except Exception as e:
                logger.error("保存AI回复失败: %s", e)

        # 解锁输入
        self._set_send_enabled(True)

        # 清理滚动定时器
        if hasattr(self, "_scroll_timer"):
            try:
                self._scroll_timer.stop()
            except Exception:
                pass
            del self._scroll_timer

        # 最终滚动到底部
        QTimer.singleShot(100, self._scroll_to_bottom)

    def _handle_stream_chunk(self, chunk: str) -> None:
        """处理流式输出块：过滤、创建气泡、入队渲染、TTS。"""
        chunk = chunk or ""
        if not chunk:
            return

        # 过滤工具信息（热路径：仅在看起来包含工具信息时执行，避免无谓开销）
        if self._needs_tool_filter(chunk):
            chunk = self._filter_tool_info_safe(chunk)
            if not chunk:
                return

        # 隐藏打字指示器（只在第一次）
        if hasattr(self, "typing_indicator") and self.typing_indicator is not None:
            self._hide_typing_indicator()
            if (
                hasattr(self, "tts_enabled")
                and self.tts_enabled
                and hasattr(self, "tts_stream_processor")
                and self.tts_stream_processor
            ):
                self.tts_stream_processor.reset()

        # 创建或更新流式消息气泡
        if self.current_streaming_bubble is None:
            self.current_streaming_bubble = LightStreamingMessageBubble()
            self._stream_model_done = False
            self.messages_layout.insertWidget(
                self.messages_layout.count() - 1, self.current_streaming_bubble
            )
            self.messages_layout.update()
            self._schedule_messages_geometry_update()

        # 入队：由渲染定时器分帧追加，避免“大段跳动”
        self._enqueue_stream_render_text(chunk)

        # 流式TTS处理
        if (
            hasattr(self, "tts_enabled")
            and self.tts_enabled
            and hasattr(self, "tts_stream_processor")
            and self.tts_stream_processor
        ):
            for sentence in self.tts_stream_processor.process_chunk(chunk):
                if not sentence or not sentence.strip():
                    continue
                filtered_sentence = (
                    self._filter_tool_info_safe(sentence)
                    if self._needs_tool_filter(sentence)
                    else sentence
                )
                if not filtered_sentence or not filtered_sentence.strip():
                    continue
                self._synthesize_tts_async(filtered_sentence)

    def _get_tool_filter_func(self):
        func = getattr(self, "_tool_filter_func", None)
        if func is not None:
            return func

        try:
            from src.agent.core import MintChatAgent

            func = MintChatAgent._filter_tool_info
        except Exception:
            func = None

        self._tool_filter_func = func
        return func

    def _filter_tool_info_safe(self, text: str) -> str:
        """过滤工具选择/调用信息（惰性加载，避免 import 阶段引入重依赖）。"""
        if not text:
            return text
        func = self._get_tool_filter_func()
        if func is None:
            return text
        try:
            return func(text)
        except Exception:
            return text

    @staticmethod
    def _needs_tool_filter(text: str) -> bool:
        """快速判断是否可能包含工具选择/调用信息，避免在热路径无谓调用过滤器。"""
        if not text:
            return False
        stripped = text.lstrip()
        if stripped.startswith("{") or stripped.startswith("["):
            return True
        if "```" in text:
            return True
        if "ToolSelectionResponse" in text:
            return True
        return ("tool" in text) or ("Tool" in text)

    def _split_large_text(self, text: str, max_len: int = 1024):
        """将过长文本切分为小段以降低单次渲染压力。"""
        if not text or len(text) <= max_len:
            return [text]
        return [text[i:i + max_len] for i in range(0, len(text), max_len)]

    def _hide_typing_indicator(self):
        """隐藏打字指示器"""
        if hasattr(self, "typing_indicator") and self.typing_indicator is not None:
            self.typing_indicator.stop_animation()
            self.messages_layout.removeWidget(self.typing_indicator)
            self.typing_indicator.deleteLater()
            self.typing_indicator = None

    def _on_chunk_received(self, chunk: str):
        """接收到流式输出块 - v2.48.12 修复：添加 TTS 流式处理"""
        self._handle_stream_chunk(chunk)

    def _on_chat_finished(self):
        """聊天完成：模型已结束，逐字渲染继续直到队列耗尽后再收尾。"""
        self._stream_model_done = True

        # v2.48.12: 处理 TTS 剩余文本（模型已结束即可 flush，不必等待 UI 完成逐字渲染）
        if (
            hasattr(self, "tts_enabled")
            and self.tts_enabled
            and hasattr(self, "tts_stream_processor")
            and self.tts_stream_processor
        ):
            remaining = self.tts_stream_processor.flush()
            if remaining:
                filtered_remaining = (
                    self._filter_tool_info_safe(remaining)
                    if self._needs_tool_filter(remaining)
                    else remaining
                )
                if not filtered_remaining or not filtered_remaining.strip():
                    logger.debug("TTS 跳过空剩余文本（过滤后）: %s...", remaining[:30])
                else:
                    self._synthesize_tts_async(filtered_remaining)
                    logger.debug("TTS 发送剩余文本: %s...", filtered_remaining[:30])

        # v2.30.14: 清理聊天线程，防止内存泄漏
        if self.current_chat_thread is not None:
            try:
                # 断开所有信号连接
                try:
                    self.current_chat_thread.chunk_received.disconnect()
                    self.current_chat_thread.finished.disconnect()
                    self.current_chat_thread.error.disconnect()
                except TypeError:
                    # 信号可能已经断开
                    pass

                # 清理线程资源
                self.current_chat_thread.cleanup()
                self.current_chat_thread.deleteLater()
                self.current_chat_thread = None
                logger.debug("ChatThread资源已清理")
            except Exception as e:
                logger.warning("清理ChatThread失败: %s", e)

        # 若渲染队列已空（或没有气泡），立即收尾；否则由渲染定时器在耗尽时触发收尾。
        remaining = int(getattr(self, "_stream_render_remaining", 0))
        if remaining <= 0:
            QTimer.singleShot(0, self._finalize_stream_response)
            return

        timer = getattr(self, "_stream_render_timer", None)
        if timer is not None and not timer.isActive():
            timer.start()

    def _on_chat_error(self, error: str):
        """聊天错误 - v2.30.14 增强资源清理"""
        self._hide_typing_indicator()
        self._add_message(f"错误: {error}", is_user=False)
        self._stream_model_done = False

        # v2.30.14: 清理聊天线程
        if self.current_chat_thread is not None:
            try:
                self.current_chat_thread.cleanup()
                self.current_chat_thread.deleteLater()
                self.current_chat_thread = None
            except Exception as e:
                logger.warning("清理ChatThread失败: %s", e)

        # 清理流式气泡
        if self.current_streaming_bubble is not None:
            try:
                if hasattr(self.current_streaming_bubble, "cleanup"):
                    self.current_streaming_bubble.cleanup()
                self.messages_layout.removeWidget(self.current_streaming_bubble)
                self.current_streaming_bubble.deleteLater()
            except Exception:
                pass
            self.current_streaming_bubble = None

        # 清理流式渲染队列，避免残留内容在错误后继续输出
        try:
            self._reset_stream_render_state()
        except Exception:
            pass

        self._set_send_enabled(True)

    def _on_enhanced_send(self, text: str, sticker_paths: list, file_paths: list):
        """增强输入框发送处理 - v2.30.7 新增

        Args:
            text: 纯文本内容
            sticker_paths: 表情包路径列表
            file_paths: 文件路径列表
        """
        try:
            # 处理表情包
            for sticker_path in sticker_paths:
                # 添加表情包消息
                self._add_image_message(sticker_path, is_user=True)

                # 统一走批量滚动调度（避免频繁创建 singleShot/lambda）
                self._ensure_scroll_to_bottom()

                # 保存到数据库
                if user_session.is_logged_in():
                    try:
                        user_session.add_message(
                            self.current_contact,
                            "user",
                            f"[STICKER:{sticker_path}]"
                        )
                    except Exception as e:
                        logger.error("保存表情包消息失败: %s", e)

            # 处理文件（图片）
            if file_paths:
                # 如果有多张图片，需要识别
                if len(file_paths) > 1:
                    self._process_multiple_images(file_paths, text)
                    return
                else:
                    # 单张图片
                    image_path = file_paths[0]
                    self._add_image_message(image_path, is_user=True)

                    # 统一走批量滚动调度（避免频繁创建 singleShot/lambda）
                    self._ensure_scroll_to_bottom()

                    # 保存到数据库
                    if user_session.is_logged_in():
                        try:
                            user_session.add_message(
                                self.current_contact,
                                "user",
                                f"[IMAGE:{image_path}]"
                            )
                        except Exception as e:
                            logger.error("保存图片消息失败: %s", e)

                    # 识别图片
                    self._recognize_and_send_image(image_path, text)
                    return

            # 处理纯文本
            if text.strip():
                # v2.30.8: 先移除旧的打字指示器（如果存在）
                if hasattr(self, "typing_indicator") and self.typing_indicator is not None:
                    self._hide_typing_indicator()

                # v2.30.13: 修复重复保存问题 - _add_message已经会保存到数据库，不需要再次保存
                # 添加用户消息（save_to_db=True会自动保存到数据库）
                self._add_message(text, is_user=True)

                # 显示打字指示器
                self._show_typing_indicator()

                # v2.30.9: 优化滚动逻辑 - 合并为单次滚动（走批量调度）
                self._ensure_scroll_to_bottom()

                # 创建并启动聊天线程
                self.current_chat_thread = ChatThread(self.agent, text)
                self.current_chat_thread.chunk_received.connect(self._on_chunk_received)
                self.current_chat_thread.finished.connect(self._on_chat_finished)
                self.current_chat_thread.error.connect(self._on_chat_error)
                self.current_chat_thread.start()

                # 禁用发送按钮
                self.send_btn.setEnabled(False)

        except Exception as e:
            logger.error("发送消息失败: %s", e, exc_info=True)
            show_toast(self, f"发送失败: {e}", Toast.TYPE_ERROR)

    def _on_emoji_clicked(self):
        """表情按钮点击 - v2.19.0 升级版"""
        # 创建表情选择器（如果还没有）
        if self.emoji_picker is None:
            from .emoji_picker import EmojiPicker

            # 获取当前用户ID
            user_id = user_session.get_user_id() if user_session.is_logged_in() else None

            self.emoji_picker = EmojiPicker(user_id=user_id, parent=self)
            self.emoji_picker.emoji_selected.connect(self._on_emoji_selected)
            self.emoji_picker.sticker_selected.connect(self._on_sticker_selected)

        # 显示表情选择器
        self.emoji_picker.show_at_button(self.emoji_btn)

    def _on_emoji_selected(self, emoji: str):
        """表情选中 - 插入到输入框 - v2.30.7 优化"""
        self.enhanced_input.insert_emoji(emoji)

    def _analyze_sticker_emotion(self, sticker_path: str) -> str:
        """分析表情包情绪 - v2.29.8 新增

        Args:
            sticker_path: 表情包路径

        Returns:
            情绪描述，如 "开心"、"难过" 等
        """
        sticker_name = Path(sticker_path).stem.lower()

        # 情绪关键词映射
        emotion_keywords = {
            "开心": ["happy", "smile", "laugh", "joy", "开心", "笑", "哈哈", "嘻嘻"],
            "难过": ["sad", "cry", "tear", "难过", "哭", "伤心", "泪"],
            "生气": ["angry", "mad", "rage", "生气", "愤怒", "火"],
            "惊讶": ["surprise", "shock", "wow", "惊讶", "震惊", "哇"],
            "害羞": ["shy", "blush", "embarrass", "害羞", "脸红", "羞"],
            "可爱": ["cute", "kawaii", "adorable", "可爱", "萌", "卡哇伊"],
            "爱心": ["love", "heart", "kiss", "爱", "心", "亲"],
            "疑问": ["question", "confused", "wonder", "疑问", "困惑", "问"],
            "赞": ["thumbs", "good", "nice", "赞", "棒", "好"],
            "无语": ["speechless", "无语", "无奈", "汗"],
        }

        # 匹配情绪
        for emotion, keywords in emotion_keywords.items():
            if any(keyword in sticker_name for keyword in keywords):
                return emotion

        return "表情"

    def _convert_stickers_to_description(self, message: str) -> str:
        """将消息中的表情包标记转换为描述性文本 - v2.29.10 优化：使用预编译正则表达式

        Args:
            message: 原始消息，可能包含 [STICKER:path] 标记

        Returns:
            转换后的消息，表情包标记被替换为描述性文本
        """
        # v2.29.10: 使用预编译的正则表达式，提升性能
        matches = STICKER_PATTERN.findall(message)

        if not matches:
            return message

        # 替换每个表情包标记
        result = message
        for sticker_path in matches:
            emotion = self._analyze_sticker_emotion(sticker_path)

            # 生成描述
            if emotion != "表情":
                description = f"[一个{emotion}的表情包]"
            else:
                description = "[一个表情包]"

            # 替换标记
            result = result.replace(f"[STICKER:{sticker_path}]", description)
            logger.debug("表情包转换: %s -> %s", sticker_path, description)

        logger.debug("消息表情包标记已转换: count=%s", len(matches))
        return result

    def _on_sticker_selected(self, sticker_path: str):
        """自定义表情包选中 - v2.30.7 优化：使用富文本内联显示

        优化内容：
        1. 使用富文本内联显示表情包图片
        2. 可以与文字一起发送
        3. 更直观的视觉效果
        """
        try:
            logger.debug("选中表情包: %s", sticker_path)

            # v2.30.7: 使用增强输入框插入表情包（内联显示）
            self.enhanced_input.insert_sticker(sticker_path)

            logger.debug("表情包已插入到输入框（内联显示）")

        except Exception as e:
            logger.error("插入表情包失败: %s", e, exc_info=True)

    def _on_attach_clicked(self):
        """附件按钮点击 - v2.30.7 优化：使用增强输入框"""
        from PyQt6.QtWidgets import QFileDialog, QMessageBox

        file_paths, _ = QFileDialog.getOpenFileNames(
            self, "选择图片（可多选）", "", "图片文件 (*.png *.jpg *.jpeg *.gif *.bmp *.webp);;所有文件 (*)"
        )

        if file_paths:
            # 检查并添加图片文件
            image_extensions = [".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"]
            for file_path in file_paths:
                file_ext = Path(file_path).suffix.lower()
                if file_ext in image_extensions:
                    # v2.30.7: 使用增强输入框添加文件
                    self.enhanced_input.add_file(file_path)
                    # 保持兼容性
                    if file_path not in self.pending_images:
                        self.pending_images.append(file_path)
                else:
                    # 其他文件类型，显示提示
                    QMessageBox.warning(
                        self,
                        "不支持的文件类型",
                        f"文件 {Path(file_path).name} 不是图片格式，已跳过。"
                    )
                    logger.warning("不支持的文件类型: %s", file_path)

    def _add_pending_image(self, image_path: str):
        """添加待发送图片到预览区域 (v2.30.2 新增)"""
        from PyQt6.QtWidgets import QLabel, QPushButton, QVBoxLayout
        from PyQt6.QtGui import QPixmap
        from PyQt6.QtCore import Qt
        from src.gui.material_design_light import MD3_LIGHT_COLORS

        # 检查是否已添加
        if image_path in self.pending_images:
            logger.debug("图片已在待发送列表中: %s", image_path)
            return

        # 添加到待发送列表
        self.pending_images.append(image_path)

        # 创建图片预览项
        preview_item = QWidget()
        preview_item.setFixedSize(90, 90)
        preview_item.setProperty("image_path", image_path)  # 保存路径用于删除

        item_layout = QVBoxLayout(preview_item)
        item_layout.setContentsMargins(0, 0, 0, 0)
        item_layout.setSpacing(0)

        # 图片容器
        image_container = QWidget()
        image_container.setFixedSize(90, 70)
        image_container_layout = QVBoxLayout(image_container)
        image_container_layout.setContentsMargins(0, 0, 0, 0)

        # 加载并显示缩略图
        image_label = QLabel()
        pixmap = QPixmap(image_path)
        if not pixmap.isNull():
            scaled_pixmap = pixmap.scaled(
                90, 70,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            image_label.setPixmap(scaled_pixmap)
            image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        image_label.setStyleSheet(f"""
            QLabel {{
                background: {MD3_LIGHT_COLORS['surface_container']};
                border: 2px solid {MD3_LIGHT_COLORS['outline_variant']};
                border-radius: 8px;
            }}
        """)
        image_container_layout.addWidget(image_label)
        item_layout.addWidget(image_container)

        # 删除按钮
        remove_btn = QPushButton("×")
        remove_btn.setFixedSize(90, 20)
        remove_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        remove_btn.setStyleSheet(f"""
            QPushButton {{
                background: {MD3_LIGHT_COLORS['error']};
                color: {MD3_LIGHT_COLORS['on_error']};
                border: none;
                border-radius: 4px;
                font-size: 16px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background: {MD3_LIGHT_COLORS['error_light']};
            }}
        """)
        remove_btn.clicked.connect(lambda: self._remove_pending_image(image_path, preview_item))
        item_layout.addWidget(remove_btn)

        # 添加到预览区域（在stretch之前）
        self.image_preview_content_layout.insertWidget(
            self.image_preview_content_layout.count() - 1,
            preview_item
        )

        # 显示预览区域
        self.image_preview_container.setVisible(True)

        logger.debug("添加待发送图片: %s, 当前共 %s 张", image_path, len(self.pending_images))

    def _remove_pending_image(self, image_path: str, preview_item: QWidget):
        """从待发送列表中移除图片 (v2.30.2 新增)"""
        if image_path in self.pending_images:
            self.pending_images.remove(image_path)

        # 移除预览项
        self.image_preview_content_layout.removeWidget(preview_item)
        preview_item.deleteLater()

        # 如果没有待发送图片了，隐藏预览区域
        if not self.pending_images:
            self.image_preview_container.setVisible(False)

        logger.debug("移除待发送图片: %s, 剩余 %s 张", image_path, len(self.pending_images))

    def _process_multiple_images(self, image_paths: list, user_message: str = ""):
        """处理多张图片的识别 (v2.30.2 新增)"""
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton, QHBoxLayout, QRadioButton, QButtonGroup
        from src.gui.material_design_light import MD3_LIGHT_COLORS

        # 创建识别模式选择对话框
        dialog = QDialog(self)
        dialog.setWindowTitle("图片识别")
        dialog.setFixedWidth(400)
        dialog.setStyleSheet(f"""
            QDialog {{
                background: {MD3_LIGHT_COLORS['surface']};
            }}
            QLabel {{
                color: {MD3_LIGHT_COLORS['on_surface']};
                font-size: 14px;
            }}
            QRadioButton {{
                color: {MD3_LIGHT_COLORS['on_surface']};
                font-size: 13px;
                padding: 8px;
            }}
            QPushButton {{
                background: {MD3_LIGHT_COLORS['primary']};
                color: {MD3_LIGHT_COLORS['on_primary']};
                border: none;
                border-radius: 20px;
                padding: 10px 24px;
                font-size: 14px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                background: {MD3_LIGHT_COLORS['primary_light']};
            }}
            QPushButton#cancelBtn {{
                background: {MD3_LIGHT_COLORS['surface_container']};
                color: {MD3_LIGHT_COLORS['on_surface_variant']};
            }}
            QPushButton#cancelBtn:hover {{
                background: {MD3_LIGHT_COLORS['surface_container_high']};
            }}
        """)

        layout = QVBoxLayout(dialog)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 24, 24, 24)

        # 标题
        title = QLabel(f"请选择图片识别模式（共{len(image_paths)}张图片）：")
        title.setStyleSheet("font-size: 16px; font-weight: 500;")
        layout.addWidget(title)

        # 识别模式选项
        mode_group = QButtonGroup(dialog)

        auto_radio = QRadioButton("🤖 智能识别（自动判断）")
        auto_radio.setChecked(True)
        mode_group.addButton(auto_radio, 0)
        layout.addWidget(auto_radio)

        describe_radio = QRadioButton("🖼️ 图片描述（描述图片内容）")
        mode_group.addButton(describe_radio, 1)
        layout.addWidget(describe_radio)

        ocr_radio = QRadioButton("📝 文字提取（OCR识别文字）")
        mode_group.addButton(ocr_radio, 2)
        layout.addWidget(ocr_radio)

        both_radio = QRadioButton("🔍 全面分析（描述+OCR）")
        mode_group.addButton(both_radio, 3)
        layout.addWidget(both_radio)

        # 按钮区域
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        cancel_btn = QPushButton("取消")
        cancel_btn.setObjectName("cancelBtn")
        cancel_btn.setFixedWidth(100)
        cancel_btn.clicked.connect(dialog.reject)
        button_layout.addWidget(cancel_btn)

        confirm_btn = QPushButton("开始识别")
        confirm_btn.setFixedWidth(120)
        confirm_btn.clicked.connect(dialog.accept)
        button_layout.addWidget(confirm_btn)

        layout.addLayout(button_layout)

        # 显示对话框
        if dialog.exec() == QDialog.DialogCode.Accepted:
            # 获取选择的模式
            mode_map = {0: "auto", 1: "describe", 2: "ocr", 3: "both"}
            selected_mode = mode_map[mode_group.checkedId()]

            # 开始批量识别
            self._batch_recognize_images(image_paths, selected_mode, user_message)
        else:
            # 用户取消，显示提示
            self._show_typing_indicator()
            self._hide_typing_indicator()
            self._add_message("已取消图片识别。", is_user=False)

    def _batch_recognize_images(self, image_paths: list, mode: str, user_message: str = ""):
        """批量识别图片 (v2.30.2 新增)"""
        from PyQt6.QtCore import QThread, pyqtSignal
        from src.multimodal.vision import get_vision_processor_instance

        # 显示处理中的消息
        processing_msg = f"🔍 正在识别 {len(image_paths)} 张图片，请稍候..."
        self._add_message(processing_msg, is_user=False, with_animation=True)

        # 创建批量识别线程
        class BatchImageRecognitionThread(QThread):
            """批量图片识别线程 - v2.30.6 增强并发控制"""
            progress = pyqtSignal(int, int, dict)  # 当前索引, 总数, 结果
            finished = pyqtSignal(list)  # 所有结果
            error = pyqtSignal(str)

            def __init__(self, image_paths: list, mode: str, llm, max_concurrent: int = 3):
                super().__init__()
                self.image_paths = image_paths
                self.mode = mode
                self.llm = llm
                self.max_concurrent = max_concurrent  # v2.30.6: 最大并发数
                self._is_running = True  # v2.30.6: 停止标志

            def run(self):
                try:
                    from concurrent.futures import ThreadPoolExecutor, as_completed
                    processor = get_vision_processor_instance()

                    results = []
                    total = len(self.image_paths)

                    # v2.30.6: 使用线程池并发处理
                    with ThreadPoolExecutor(max_workers=self.max_concurrent) as executor:
                        # 提交所有任务
                        future_to_index = {
                            executor.submit(
                                processor.smart_analyze,
                                image_path,
                                mode=self.mode,
                                llm=self.llm
                            ): (i, image_path)
                            for i, image_path in enumerate(self.image_paths)
                        }

                        # 按完成顺序处理结果
                        completed = 0
                        for future in as_completed(future_to_index):
                            if not self._is_running:
                                logger.info("批量识别被取消")
                                break

                            i, image_path = future_to_index[future]
                            try:
                                result = future.result()
                                result['image_path'] = image_path
                                results.append((i, result))  # 保存索引以便排序
                                completed += 1

                                # 发送进度
                                self.progress.emit(completed, total, result)
                            except Exception as e:
                                logger.error("识别图片 %s 失败: %s", image_path, e)
                                # 继续处理其他图片

                    # v2.30.6: 按原始顺序排序结果
                    results.sort(key=lambda x: x[0])
                    sorted_results = [r[1] for r in results]

                    self.finished.emit(sorted_results)
                except Exception as e:
                    logger.error("批量识别失败: %s", e)
                    self.error.emit(str(e))

            def stop(self):
                """停止识别 - v2.30.6 新增"""
                self._is_running = False

        # 创建并启动线程
        self.batch_recognition_thread = BatchImageRecognitionThread(
            image_paths, mode, self.agent.llm if self.agent else None
        )
        self.batch_recognition_thread.progress.connect(
            lambda idx, total, result: logger.debug("图片识别进度: %s/%s", idx, total)
        )
        self.batch_recognition_thread.finished.connect(
            lambda results: self._on_batch_recognition_finished(results, user_message)
        )
        self.batch_recognition_thread.error.connect(
            lambda error: self._add_message(f"❌ 批量识别失败: {error}", is_user=False)
        )
        self.batch_recognition_thread.start()

    def _on_batch_recognition_finished(self, results: list, user_message: str = ""):
        """批量识别完成回调 (v2.30.2 新增)"""
        # 构建识别结果消息
        result_msg = f"✅ {len(results)} 张图片识别完成！\n\n"

        for i, result in enumerate(results, 1):
            result_msg += f"📷 图片 {i}:\n"

            if result.get("description"):
                result_msg += f"  📝 {result['description']}\n"

            if result.get("text") and "没有" not in result["text"] and "失败" not in result["text"]:
                result_msg += f"  📄 文字: {result['text']}\n"

            result_msg += "\n"

        # 显示识别结果
        self._add_message(result_msg, is_user=False, with_animation=True)

        # 合并所有图片分析结果
        combined_analysis = {
            "mode": results[0].get("mode", "auto"),
            "description": "\n\n".join([f"图片{i+1}: {r.get('description', '')}" for i, r in enumerate(results) if r.get('description')]),
            "text": "\n\n".join([f"图片{i+1}: {r.get('text', '')}" for i, r in enumerate(results) if r.get('text')]),
            "success": all(r.get("success", False) for r in results),
            "image_count": len(results)
        }

        # 保存合并后的分析结果
        self.current_image_analysis = combined_analysis
        self.current_image_path = results[0].get('image_path') if results else None

        # 如果有用户消息，自动发送给AI
        if user_message or combined_analysis.get("description") or combined_analysis.get("text"):
            # 构建AI消息
            if user_message:
                ai_message = user_message
            else:
                ai_message = "请帮我分析这些图片。"

            # 显示打字指示器
            self._show_typing_indicator()

            # 创建并启动聊天线程
            self.current_chat_thread = ChatThread(
                self.agent,
                ai_message,
                image_path=self.current_image_path,
                image_analysis=combined_analysis
            )
            self.current_chat_thread.chunk_received.connect(self._on_chunk_received)
            self.current_chat_thread.finished.connect(self._on_chat_finished)
            self.current_chat_thread.error.connect(self._on_chat_error)
            self.current_chat_thread.start()

            # 禁用发送按钮
            self.send_btn.setEnabled(False)

        logger.info("批量识别完成: %s 张图片", len(results))

    def _handle_image_upload(self, image_path: str):
        """处理图片上传和识别 (v2.30.0 新增，v2.30.2 已弃用，保留用于兼容)"""
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton, QHBoxLayout, QRadioButton, QButtonGroup
        from src.gui.material_design_light import MD3_LIGHT_COLORS

        # 显示图片消息气泡
        self._add_image_message(image_path, is_user=True)
        logger.debug("发送图片: %s", image_path)

        # 创建识别模式选择对话框
        dialog = QDialog(self)
        dialog.setWindowTitle("图片识别")
        dialog.setFixedWidth(400)
        dialog.setStyleSheet(f"""
            QDialog {{
                background: {MD3_LIGHT_COLORS['surface']};
            }}
            QLabel {{
                color: {MD3_LIGHT_COLORS['on_surface']};
                font-size: 14px;
            }}
            QRadioButton {{
                color: {MD3_LIGHT_COLORS['on_surface']};
                font-size: 13px;
                padding: 8px;
            }}
            QPushButton {{
                background: {MD3_LIGHT_COLORS['primary']};
                color: {MD3_LIGHT_COLORS['on_primary']};
                border: none;
                border-radius: 20px;
                padding: 10px 24px;
                font-size: 14px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                background: {MD3_LIGHT_COLORS['primary_light']};
            }}
            QPushButton#cancelBtn {{
                background: {MD3_LIGHT_COLORS['surface_container']};
                color: {MD3_LIGHT_COLORS['on_surface_variant']};
            }}
            QPushButton#cancelBtn:hover {{
                background: {MD3_LIGHT_COLORS['surface_container_high']};
            }}
        """)

        layout = QVBoxLayout(dialog)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 24, 24, 24)

        # 标题
        title = QLabel("请选择图片识别模式：")
        title.setStyleSheet("font-size: 16px; font-weight: 500;")
        layout.addWidget(title)

        # 识别模式选项
        mode_group = QButtonGroup(dialog)

        auto_radio = QRadioButton("🤖 智能识别（自动判断）")
        auto_radio.setChecked(True)
        mode_group.addButton(auto_radio, 0)
        layout.addWidget(auto_radio)

        describe_radio = QRadioButton("🖼️ 图片描述（描述图片内容）")
        mode_group.addButton(describe_radio, 1)
        layout.addWidget(describe_radio)

        ocr_radio = QRadioButton("📝 文字提取（OCR识别文字）")
        mode_group.addButton(ocr_radio, 2)
        layout.addWidget(ocr_radio)

        both_radio = QRadioButton("🔍 全面分析（描述+OCR）")
        mode_group.addButton(both_radio, 3)
        layout.addWidget(both_radio)

        # 按钮区域
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        cancel_btn = QPushButton("取消")
        cancel_btn.setObjectName("cancelBtn")
        cancel_btn.setFixedWidth(100)
        cancel_btn.clicked.connect(dialog.reject)
        button_layout.addWidget(cancel_btn)

        confirm_btn = QPushButton("开始识别")
        confirm_btn.setFixedWidth(120)
        confirm_btn.clicked.connect(dialog.accept)
        button_layout.addWidget(confirm_btn)

        layout.addLayout(button_layout)

        # 显示对话框
        if dialog.exec() == QDialog.DialogCode.Accepted:
            # 获取选择的模式
            mode_map = {0: "auto", 1: "describe", 2: "ocr", 3: "both"}
            selected_mode = mode_map[mode_group.checkedId()]

            # 开始识别
            self._process_image_recognition(image_path, selected_mode)

    def _process_image_recognition(self, image_path: str, mode: str):
        """处理图片识别 (v2.30.0 新增)"""
        from PyQt6.QtCore import QThread, pyqtSignal
        from src.multimodal.vision import get_vision_processor_instance

        # 显示处理中的消息
        processing_msg = "🔍 正在识别图片，请稍候..."
        self._add_message(processing_msg, is_user=False, with_animation=True)

        # 创建识别线程
        class ImageRecognitionThread(QThread):
            """图片识别线程"""
            finished = pyqtSignal(dict)
            error = pyqtSignal(str)

            def __init__(self, image_path: str, mode: str, llm):
                super().__init__()
                self.image_path = image_path
                self.mode = mode
                self.llm = llm

            def run(self):
                try:
                    # 使用VisionProcessor进行智能分析
                    result = get_vision_processor_instance().smart_analyze(
                        self.image_path,
                        mode=self.mode,
                        llm=self.llm
                    )
                    self.finished.emit(result)
                except Exception as e:
                    self.error.emit(str(e))

        # 创建并启动线程
        self.image_recognition_thread = ImageRecognitionThread(
            image_path, mode, self.agent.llm if self.agent else None
        )
        self.image_recognition_thread.finished.connect(
            lambda result: self._on_image_recognition_finished(result, image_path)
        )
        self.image_recognition_thread.error.connect(
            lambda error: self._add_message(f"❌ 图片识别失败: {error}", is_user=False)
        )
        self.image_recognition_thread.start()

    def _on_image_recognition_finished(self, result: dict, image_path: str):
        """图片识别完成回调 (v2.30.0 新增)"""
        # 构建识别结果消息
        result_msg = "✅ 图片识别完成！\n\n"

        if result.get("description"):
            result_msg += f"📝 图片描述：\n{result['description']}\n\n"

        if result.get("text") and "没有" not in result["text"] and "失败" not in result["text"]:
            result_msg += f"📄 提取文字：\n{result['text']}\n\n"

        result_msg += "💬 请问您想了解什么呢？"

        # 显示识别结果
        self._add_message(result_msg, is_user=False, with_animation=True)

        # 保存图片分析结果，供后续对话使用
        self.current_image_analysis = result
        self.current_image_path = image_path

        logger.info("图片识别完成: %s, 模式: %s", image_path, result.get("mode"))

    def _on_chat_clicked(self):
        """聊天按钮点击 - 返回聊天界面"""
        # 切换回聊天区域
        self.stacked_widget.setCurrentIndex(0)
        # 显示提示
        show_toast(self, "已返回聊天界面", Toast.TYPE_INFO, duration=1500)

    def _on_settings_clicked(self):
        """设置按钮点击"""
        # 懒加载设置面板：首次打开时才创建，减少启动时的 UI 构建开销
        if self.settings_panel is None:
            from .settings_panel import SettingsPanel

            self.settings_panel = SettingsPanel(agent=self.agent)
            self.settings_panel.back_clicked.connect(self._on_settings_back)
            self.settings_panel.settings_saved.connect(self._on_settings_saved)
            self.stacked_widget.addWidget(self.settings_panel)

        # 切换到设置面板
        self.stacked_widget.setCurrentWidget(self.settings_panel)
        # 折叠联系人面板
        if self.contacts_panel.is_expanded():
            self.contacts_panel.collapse()

    def _on_settings_back(self):
        """设置面板返回按钮点击"""
        # 切换回聊天区域
        self.stacked_widget.setCurrentIndex(0)

    def _on_contacts_clicked(self):
        """联系人按钮点击 - 切换展开/折叠"""
        # 切换联系人面板
        self.contacts_panel.toggle()

    def _on_contact_selected(self, contact_name: str):
        """联系人选中 - 切换到该联系人的消息容器 - v2.21.3 优化：流畅切换，无闪烁"""

        # 停止当前正在运行的聊天线程
        if self.current_chat_thread is not None and self.current_chat_thread.isRunning():
            logger.info("停止当前聊天线程...")
            self.current_chat_thread.stop()
            self.current_chat_thread.wait(1000)  # 等待最多1秒
            self.current_chat_thread = None

        # 清理打字指示器
        if hasattr(self, "typing_indicator") and self.typing_indicator is not None:
            self._hide_typing_indicator()

        # 清理流式消息气泡
        if self.current_streaming_bubble is not None:
            if hasattr(self.current_streaming_bubble, "cleanup"):
                self.current_streaming_bubble.cleanup()
            self.current_streaming_bubble = None
        try:
            self._reset_stream_render_state()
        except Exception:
            pass

        # 保存当前联系人的聊天历史
        if self.current_contact and user_session.is_logged_in():
            self._save_current_chat_history()

        # 切换联系人
        self.current_contact = contact_name
        logger.debug("选中联系人: %s", contact_name)

        # v2.21.3 优化：禁用滚动区域更新，避免闪烁
        self.scroll_area.setUpdatesEnabled(False)

        # 清空当前消息
        self._clear_messages()

        # 加载该联系人的聊天历史（内部会重新启用更新）
        if user_session.is_logged_in():
            self._load_chat_history(contact_name)
        else:
            # 如果未登录，手动重新启用更新
            self.scroll_area.setUpdatesEnabled(True)

        # 更新头部显示
        self.name_label.setText(contact_name)

        # 重新启用发送按钮
        self._set_send_enabled(True)

        # 显示提示
        show_toast(self, f"已切换到 {contact_name} 的对话", Toast.TYPE_INFO, duration=2000)

    def _load_chat_history(self, contact_name: str, limit: int = 20):
        """加载聊天历史 - v2.30.12 优化：分页加载，缓存机制，性能提升

        Args:
            contact_name: 联系人名称
            limit: 加载消息数量（默认20条，避免一次加载过多）
        """

        scroll_widget = self.scroll_area.widget()
        scrollbar = self.scroll_area.verticalScrollBar()
        old_bulk_loading = getattr(self, "_bulk_loading_messages", False)
        old_scrollbar_signals = False
        try:
            logger.debug("开始加载聊天历史: %s (limit=%s)", contact_name, limit)

            # v2.30.12: 初始化消息缓存和分页状态
            if not hasattr(self, '_message_cache'):
                self._message_cache = {}  # {contact_name: {msg_id: msg}}
            if not hasattr(self, '_loaded_message_count'):
                self._loaded_message_count = {}  # {contact_name: count}
            if not hasattr(self, '_total_message_count'):
                self._total_message_count = {}  # {contact_name: total}

            # 重置当前联系人的缓存
            self._message_cache[contact_name] = {}
            self._loaded_message_count[contact_name] = 0

            # v2.30.12: 获取消息总数（用于判断是否还有更多消息）
            total_count = user_session.get_chat_history_count(contact_name)
            self._total_message_count[contact_name] = total_count
            logger.debug("消息总数: %s", total_count)

            # 从数据库加载最近的聊天历史（性能优化：限制数量）
            messages = user_session.get_chat_history(contact_name, limit=limit, offset=0)

            # v2.21.3 优化：禁用滚动区域更新，批量加载消息（包含无历史消息的欢迎提示）
            self._bulk_loading_messages = True
            # 同步屏蔽滚动条信号，避免批量插入期间触发 valueChanged 导致额外逻辑与抖动
            try:
                old_scrollbar_signals = scrollbar.blockSignals(True)
            except Exception:
                old_scrollbar_signals = False
            self.scroll_area.setUpdatesEnabled(False)
            if scroll_widget is not None:
                scroll_widget.setUpdatesEnabled(False)

            # 显示历史消息（v2.21.3 优化：禁用动画，避免闪烁）
            try:
                if not messages:
                    # 没有历史消息，显示欢迎消息（注意：仍需确保最终恢复更新开关）
                    logger.debug("没有历史消息，显示欢迎消息")
                    self._add_message(
                        f"开始与 {contact_name} 的对话吧！",
                        is_user=False,
                        save_to_db=False,
                        with_animation=False,
                    )
                else:
                    logger.debug("开始显示 %s 条历史消息", len(messages))
                    # v2.30.12: 缓存加载的消息（使用消息ID去重）
                    contact_cache = self._message_cache[contact_name]
                    for msg in messages:
                        msg_id = msg.get("id")
                        if msg_id:
                            contact_cache[msg_id] = msg

                    for msg in messages:
                        is_user = msg.get("role") == "user"
                        # v2.21.3 关键优化：with_animation=False 禁用入场动画
                        self._add_message(
                            msg["content"],
                            is_user=is_user,
                            save_to_db=False,
                            with_animation=False,
                        )
            finally:
                self._bulk_loading_messages = old_bulk_loading

            # v2.30.12: 更新已加载消息数量
            self._loaded_message_count[contact_name] = len(messages)

            # v2.48.8 修复：重新启用更新并强制刷新布局
            if scroll_widget is not None:
                scroll_widget.setUpdatesEnabled(True)
            self.scroll_area.setUpdatesEnabled(True)

            # v2.48.8 修复：强制更新布局，避免抖动
            self.messages_layout.update()
            self._schedule_messages_geometry_update()

            # 统一走批量滚动调度：若此刻 maximum 尚未最终确定，rangeChanged 会再次触发跟随到底部
            self._ensure_scroll_to_bottom()

            # v2.30.12: 如果还有更多消息，显示提示
            if total_count > limit:
                logger.debug("还有 %s 条历史消息未加载", total_count - limit)

            logger.info("已加载 %s/%s 条历史消息（联系人: %s）", len(messages), total_count, contact_name)
        except Exception as e:
            from src.utils.exceptions import handle_exception

            handle_exception(e, logger, "加载聊天历史失败")
        finally:
            # 双保险：避免异常/提前返回导致界面不更新
            if scroll_widget is not None:
                scroll_widget.setUpdatesEnabled(True)
            self.scroll_area.setUpdatesEnabled(True)
            try:
                scrollbar.blockSignals(old_scrollbar_signals)
            except Exception:
                pass
            self._bulk_loading_messages = old_bulk_loading

    def _load_more_history(self, contact_name: str, limit: int = 20):
        """加载更多历史消息 (v2.30.12: 新增分页加载功能)

        Args:
            contact_name: 联系人名称
            limit: 每次加载的消息数量
        """
        try:
            # 检查是否还有更多消息
            if not hasattr(self, '_loaded_message_count'):
                logger.warning("未初始化消息计数器")
                return

            loaded_count = self._loaded_message_count.get(contact_name, 0)
            total_count = self._total_message_count.get(contact_name, 0)

            if loaded_count >= total_count:
                logger.info("已加载全部 %s 条消息", total_count)
                show_toast(self, "已加载全部历史消息", Toast.TYPE_INFO, duration=2000)
                return

            # 计算还需要加载的消息数量
            remaining = total_count - loaded_count
            load_count = min(limit, remaining)

            logger.debug("加载更多历史消息: offset=%s, limit=%s", loaded_count, load_count)

            # 从数据库加载更多消息
            messages = user_session.get_chat_history(
                contact_name, limit=load_count, offset=loaded_count
            )

            if not messages:
                logger.warning("没有加载到更多消息")
                return

            # v2.30.12: 缓存新加载的消息
            contact_cache = self._message_cache.setdefault(contact_name, {})
            for msg in messages:
                msg_id = msg.get('id')
                if msg_id and msg_id not in contact_cache:
                    contact_cache[msg_id] = msg

            # 记录当前滚动位置
            scrollbar = self.scroll_area.verticalScrollBar()
            old_value = scrollbar.value()
            old_max = scrollbar.maximum()

            scroll_widget = self.scroll_area.widget()
            old_bulk_loading = getattr(self, "_bulk_loading_messages", False)
            old_scrollbar_signals = False
            try:
                self._bulk_loading_messages = True

                # 禁用滚动区域及其内容区域更新，避免批量插入引发频繁重绘/抖动
                try:
                    old_scrollbar_signals = scrollbar.blockSignals(True)
                except Exception:
                    old_scrollbar_signals = False
                self.scroll_area.setUpdatesEnabled(False)
                if scroll_widget is not None:
                    scroll_widget.setUpdatesEnabled(False)

                # 在顶部插入历史消息（禁用动画）
                logger.debug("在顶部插入 %s 条历史消息", len(messages))
                for msg in reversed(messages):  # 反转以保持时间顺序
                    self._insert_message_at_top(
                        msg["content"],
                        is_user=(msg.get("role") == "user"),
                        with_animation=False,
                    )

                # 更新已加载消息数量
                self._loaded_message_count[contact_name] = loaded_count + len(messages)
            finally:
                if scroll_widget is not None:
                    scroll_widget.setUpdatesEnabled(True)
                self.scroll_area.setUpdatesEnabled(True)
                try:
                    scrollbar.blockSignals(old_scrollbar_signals)
                except Exception:
                    pass
                self._bulk_loading_messages = old_bulk_loading

            # v2.48.8 修复：强制更新布局，避免抖动
            self.messages_layout.update()
            self._schedule_messages_geometry_update()

            # v2.48.8 修复：增加延迟到 100ms，确保布局完全更新后再恢复滚动位置
            QTimer.singleShot(100, lambda: self._restore_scroll_position(old_value, old_max))

            logger.info("已加载 %s/%s 条历史消息", self._loaded_message_count[contact_name], total_count)
            show_toast(
                self,
                f"已加载 {len(messages)} 条历史消息",
                Toast.TYPE_SUCCESS,
                duration=2000
            )
        except Exception as e:
            from src.utils.exceptions import handle_exception

            handle_exception(e, logger, "加载更多历史消息失败")

    def _insert_message_at_top(self, message: str, is_user: bool, with_animation: bool = False):
        """在顶部插入消息 (v2.30.13: 修复导入错误)

        Args:
            message: 消息内容
            is_user: 是否为用户消息
            with_animation: 是否显示动画
        """
        # v2.30.13: 修复导入错误 - 使用LightMessageBubble而不是AnimatedMessageBubble
        bubble = LightMessageBubble(message, is_user, enable_shadow=with_animation)

        # 在顶部插入（索引0）
        self.messages_layout.insertWidget(0, bubble)

        if with_animation and GUI_ANIMATIONS_ENABLED:
            bubble.show_with_animation()

    def _restore_scroll_position(self, old_value: int, old_max: int):
        """恢复滚动位置 (v2.30.12: 新增，避免加载历史消息时跳动)

        Args:
            old_value: 旧的滚动值
            old_max: 旧的最大滚动值
        """
        scrollbar = self.scroll_area.verticalScrollBar()
        new_max = scrollbar.maximum()

        # 计算新的滚动位置（保持相对位置）
        if old_max > 0:
            new_value = old_value + (new_max - old_max)
        else:
            new_value = new_max

        scrollbar.setValue(new_value)

    def _on_scroll_changed(self, value: int):
        """滚动事件处理 (v2.30.12: 新增，实现滚动到顶部自动加载更多)

        Args:
            value: 当前滚动值
        """
        # 自动滚动锁：只有在接近底部时才允许自动滚动，避免用户上滑时被强制拉回
        try:
            scrollbar = self.scroll_area.verticalScrollBar()
            prev_auto = bool(getattr(self, "_auto_scroll_enabled", True))
            self._auto_scroll_enabled = (scrollbar.maximum() - value) <= AUTO_SCROLL_BOTTOM_THRESHOLD_PX
            # 当用户从“上滑查看历史”回到底部时，裁剪旧消息以恢复滚动性能
            if self._auto_scroll_enabled and not prev_auto:
                self._schedule_trim_rendered_messages(force=False)
        except Exception:
            self._auto_scroll_enabled = True

        # 如果正在加载，跳过
        if self._is_loading_more:
            return

        # 如果滚动到顶部（阈值：距离顶部小于100像素）
        if value < 100:
            # 检查是否还有更多消息
            if not hasattr(self, '_loaded_message_count') or not self.current_contact:
                return

            loaded_count = self._loaded_message_count.get(self.current_contact, 0)
            total_count = self._total_message_count.get(self.current_contact, 0)

            if loaded_count < total_count:
                logger.debug("滚动到顶部，自动加载更多历史消息")
                self._is_loading_more = True

                # 延迟加载，避免频繁触发
                QTimer.singleShot(200, lambda: self._load_more_with_reset())

    def _on_scroll_range_changed(self, _min: int, _max: int) -> None:
        """滚动范围变化（内容高度变化）时，按需跟随到底部。

        典型场景：流式输出导致气泡持续增高/换行；新消息插入；窗口尺寸变化。
        """
        if not getattr(self, "_auto_scroll_enabled", True):
            return

        # 优先走批量滚动（更省资源），否则走轻量调度（带去抖）
        if getattr(self, "performance_optimizer", None) is not None:
            try:
                self.performance_optimizer.schedule_scroll()
                return
            except Exception:
                pass

        self._schedule_stream_scroll()

    def _load_more_with_reset(self):
        """加载更多消息并重置加载状态 (v2.30.12: 新增)"""
        try:
            if self.current_contact:
                self._load_more_history(self.current_contact, limit=20)
        finally:
            # 重置加载状态
            QTimer.singleShot(500, lambda: setattr(self, '_is_loading_more', False))

    def _save_current_chat_history(self):
        """保存当前聊天历史（在切换联系人时调用）"""
        # 注意：消息已经在发送时实时保存到数据库，这里不需要额外操作
        pass

    def _clear_messages(self):
        """清空消息区域 - v2.19.2 修复版：正确清理资源"""
        # 移除所有消息气泡
        while self.messages_layout.count() > 1:  # 保留最后的 stretch
            item = self.messages_layout.takeAt(0)
            if item.widget():
                widget = item.widget()

                # 根据类型清理资源
                if hasattr(widget, "cleanup"):
                    try:
                        widget.cleanup()
                    except Exception as e:
                        logger.warning("清理 widget 资源时出错: %s", e)

                # 删除 widget
                widget.deleteLater()

    def _on_settings_saved(self):
        """设置保存后的回调 - v2.22.0 优化：刷新头像"""
        logger.info("设置已保存，需要重启应用以应用新设置")

        # v2.22.0 刷新头像显示
        if user_session.is_logged_in():
            ai_avatar = user_session.get_ai_avatar()
            # 重新创建头像标签
            new_avatar_label = _create_avatar_label_for_header(ai_avatar, 56)
            # 替换旧的头像标签
            old_avatar = self.avatar_label
            parent_layout = old_avatar.parent().layout()
            if parent_layout:
                index = parent_layout.indexOf(old_avatar)
                parent_layout.removeWidget(old_avatar)
                old_avatar.deleteLater()
                parent_layout.insertWidget(index, new_avatar_label)
                self.avatar_label = new_avatar_label
                # 重新设置脉冲动画
                self._setup_avatar_pulse_animation()
            logger.info("AI助手头像已刷新: %s", ai_avatar)

        # 返回聊天区域
        self._on_settings_back()

    def _on_logout_clicked(self):
        """退出登录按钮点击 - 带平滑动画"""
        from PyQt6.QtWidgets import QMessageBox

        # 确认对话框
        reply = QMessageBox.question(
            self,
            "退出登录",
            "确定要退出登录吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            # 清除会话文件
            session_file = Path("data/session.txt")
            if session_file.exists():
                try:
                    session_file.unlink()
                    logger.info("会话已清除")
                except Exception as e:
                    logger.info("清除会话失败: %s", e)

            # 清除用户会话
            user_session.logout()

            # 显示提示
            show_toast(self, "正在退出登录...", Toast.TYPE_INFO, duration=1500)

            # 延迟关闭窗口并显示登录界面
            QTimer.singleShot(1500, self._perform_logout)

    def _perform_logout(self):
        """执行退出登录 - 带淡出动画"""
        # 创建淡出动画
        self.logout_opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.logout_opacity_effect)

        self.logout_fade_out = QPropertyAnimation(self.logout_opacity_effect, b"opacity")
        self.logout_fade_out.setDuration(400)  # 400ms 淡出
        self.logout_fade_out.setStartValue(1.0)
        self.logout_fade_out.setEndValue(0.0)
        self.logout_fade_out.setEasingCurve(QEasingCurve.Type.InCubic)

        # 动画完成后显示登录窗口
        self.logout_fade_out.finished.connect(self._show_login_window)

        # 开始动画
        self.logout_fade_out.start()

    def _show_login_window(self):
        """显示登录窗口"""
        from .auth_manager import AuthManager
        from src.auth.auth_service import AuthService

        # 关闭当前窗口
        self.close()

        # 创建并显示登录窗口
        self.auth_manager = AuthManager(illustration_path="data/images/login_illustration.png")

        # 登录成功后的处理
        def on_login_success(user):

            logger.success(f"登录成功！欢迎，{user['username']}！")

            # 保存会话令牌
            try:
                session_token = user.get("session_token")
                remember_me = user.get("remember_me", False)
                session_file = Path("data/session.txt")

                if session_token and remember_me:
                    session_file.parent.mkdir(parents=True, exist_ok=True)
                    session_file.write_text(session_token)
                    logger.info("会话已保存到: %s", session_file)
                else:
                    if session_file.exists():
                        session_file.unlink()
                        logger.info("已清除保存的会话")

                # 设置用户会话（关键修复：退出登录后再次登录时必须设置）
                user_session.login(user, session_token)
                logger.info("用户会话已设置: %s (ID: %s)", user.get("username"), user.get("id"))
            except Exception as e:
                from src.utils.exceptions import handle_exception

                logger.info("保存会话失败: %s", e)
                handle_exception(e, logger, "保存会话失败")

            # 关闭登录窗口
            self.auth_manager.close()

            # 创建并显示新的聊天窗口
            try:
                new_window = LightChatWindow()
                new_window.show()
                logger.info("新聊天窗口已创建并显示")
            except Exception as e:
                from src.utils.exceptions import handle_exception

                logger.info("创建聊天窗口失败: %s", e)
                handle_exception(e, logger, "创建聊天窗口失败")

        self.auth_manager.login_success.connect(on_login_success)
        self.auth_manager.show()

    def _setup_fps_overlay(self) -> None:
        """启动一个低开销的 FPS 监控（用于验证 GUI 流畅度）。"""
        if not hasattr(self, "_fps_label") or self._fps_label is None:
            return
        if hasattr(self, "_fps_timer") and self._fps_timer is not None:
            return

        self._fps_frame_count = 0
        self._fps_last_ts = time.perf_counter()
        self._fps_timer = QTimer(self)
        self._fps_timer.timeout.connect(self._on_fps_tick)
        # 以 60fps 为目标节奏；若主线程忙，实际 tick 次数会显著降低
        self._fps_timer.start(16)

    def _on_fps_tick(self) -> None:
        self._fps_frame_count += 1
        now = time.perf_counter()
        elapsed = now - self._fps_last_ts
        if elapsed < 1.0:
            return

        fps = self._fps_frame_count / elapsed if elapsed > 0 else 0.0
        try:
            if hasattr(self, "_fps_label") and self._fps_label is not None:
                self._fps_label.setText(f"FPS {fps:.0f}")
        except Exception:
            pass
        self._fps_frame_count = 0
        self._fps_last_ts = now

    def _setup_avatar_pulse_animation(self):
        """设置头像脉冲动画 - 在线状态指示器

        使用缩放动画模拟心跳效果，提升视觉吸引力
        """
        # 性能优化：避免通过 min/max size 动画触发布局重算（会显著拉低帧率）。
        # 改为对状态文字做轻量透明度脉冲，只重绘小区域即可。
        try:
            if not hasattr(self, "status_label") or self.status_label is None:
                return

            effect = QGraphicsOpacityEffect(self.status_label)
            self.status_label.setGraphicsEffect(effect)

            self.status_pulse_animation = QPropertyAnimation(effect, b"opacity")
            self.status_pulse_animation.setDuration(1200)
            self.status_pulse_animation.setStartValue(0.55)
            self.status_pulse_animation.setKeyValueAt(0.5, 1.0)
            self.status_pulse_animation.setEndValue(0.55)
            self.status_pulse_animation.setEasingCurve(QEasingCurve.Type.InOutSine)
            self.status_pulse_animation.setLoopCount(-1)
            self.status_pulse_animation.start()
        except Exception:
            # 动画失败不影响主流程
            return

    def _show_shortcut_help(self):
        """显示快捷键帮助 (v2.42.0: 连接设置信号)"""
        try:
            from src.gui.widgets import ShortcutHelpDialog

            dialog = ShortcutHelpDialog(self)
            # v2.42.0: 连接设置请求信号
            dialog.settings_requested.connect(self._show_shortcut_settings)
            dialog.exec()

        except Exception as e:
            logger.error("显示快捷键帮助失败: %s", e)

    def _show_shortcut_settings(self):
        """显示快捷键设置对话框 (v2.42.0)"""
        try:
            from src.gui.widgets import ShortcutSettingsDialog

            # 获取当前快捷键配置
            current_shortcuts = {}

            # 显示对话框
            dialog = ShortcutSettingsDialog(current_shortcuts, self)
            dialog.shortcuts_changed.connect(self._on_shortcuts_changed)
            dialog.exec()

        except Exception as e:
            logger.error("显示快捷键设置失败: %s", e)

    def _on_shortcuts_changed(self, new_shortcuts: dict):
        """快捷键变更处理 (v2.42.0)"""
        try:
            show_toast(self, "快捷键设置已保存", Toast.TYPE_SUCCESS)
            logger.info("快捷键已更新: %s", new_shortcuts)

        except Exception as e:
            logger.error("快捷键变更处理失败: %s", e)
            show_toast(self, f"快捷键设置失败: {e}", Toast.TYPE_ERROR)

    def closeEvent(self, event):
        """窗口关闭事件 - 清理资源"""
        try:
            logger.info("聊天窗口正在关闭，清理资源...")

            # 1. 停止所有动画
            if hasattr(self, "avatar_pulse_animation") and self.avatar_pulse_animation:
                self.avatar_pulse_animation.stop()
            if hasattr(self, "avatar_pulse_animation_max") and self.avatar_pulse_animation_max:
                self.avatar_pulse_animation_max.stop()
            if hasattr(self, "status_pulse_animation") and self.status_pulse_animation:
                self.status_pulse_animation.stop()
            if hasattr(self, "page_fade_animation") and self.page_fade_animation:
                self.page_fade_animation.stop()
            if hasattr(self, "_fps_timer") and self._fps_timer:
                self._fps_timer.stop()

            # 2. 停止正在运行的聊天线程 (v2.46.1: 增强清理逻辑)
            if self.current_chat_thread is not None:
                try:
                    logger.info("停止聊天线程...")

                    # v2.46.1: 断开所有信号连接，防止信号槽泄漏
                    try:
                        self.current_chat_thread.chunk_received.disconnect()
                        self.current_chat_thread.finished.disconnect()
                        self.current_chat_thread.error.disconnect()
                    except TypeError:
                        # 信号可能已经断开
                        pass

                    # v2.46.2: 停止线程（先停止内部的Python线程）
                    if self.current_chat_thread.isRunning():
                        # 调用stop()方法，这会设置_is_running=False并等待Python线程
                        self.current_chat_thread.stop()

                        # 等待QThread结束，最多5秒（给Python线程足够时间）
                        if not self.current_chat_thread.wait(5000):
                            logger.warning("聊天线程未能在5秒内结束，强制终止")
                            self.current_chat_thread.terminate()
                            self.current_chat_thread.wait(1000)
                        else:
                            logger.info("聊天线程已正常结束")

                    # v2.46.1: 清理线程资源
                    if hasattr(self.current_chat_thread, 'cleanup'):
                        self.current_chat_thread.cleanup()

                    # v2.46.1: 标记为待删除
                    self.current_chat_thread.deleteLater()
                    self.current_chat_thread = None
                    logger.info("聊天线程已清理")
                except Exception as e:
                    logger.error("清理聊天线程失败: %s", e)

            # 2.2. 停止后台初始化线程（若仍在运行）
            if getattr(self, "_agent_init_thread", None) is not None:
                try:
                    logger.info("停止 Agent 初始化线程...")
                    if self._agent_init_thread.isRunning():
                        try:
                            self._agent_init_thread.requestInterruption()
                        except Exception:
                            pass
                        if not self._agent_init_thread.wait(2000):
                            logger.warning("Agent 初始化线程未能在2秒内结束，强制终止")
                            self._agent_init_thread.terminate()
                            self._agent_init_thread.wait(500)
                    self._agent_init_thread.deleteLater()
                    self._agent_init_thread = None
                    logger.info("Agent 初始化线程已清理")
                except Exception as e:
                    logger.error("清理 Agent 初始化线程失败: %s", e)

            # 2.5. 清理图片识别线程 (v2.46.1: 新增)
            if hasattr(self, 'image_recognition_thread') and self.image_recognition_thread is not None:
                try:
                    logger.info("停止图片识别线程...")
                    if self.image_recognition_thread.isRunning():
                        if hasattr(self.image_recognition_thread, 'stop'):
                            self.image_recognition_thread.stop()
                        if not self.image_recognition_thread.wait(2000):
                            logger.warning("图片识别线程未能在2秒内结束，强制终止")
                            self.image_recognition_thread.terminate()
                            self.image_recognition_thread.wait(1000)
                    self.image_recognition_thread.deleteLater()
                    self.image_recognition_thread = None
                    logger.info("图片识别线程已清理")
                except Exception as e:
                    logger.error("清理图片识别线程失败: %s", e)

            # 2.6. 清理批量识别线程 (v2.46.1: 新增)
            if hasattr(self, 'batch_recognition_thread') and self.batch_recognition_thread is not None:
                try:
                    logger.info("停止批量识别线程...")
                    if self.batch_recognition_thread.isRunning():
                        if hasattr(self.batch_recognition_thread, 'stop'):
                            self.batch_recognition_thread.stop()
                        if not self.batch_recognition_thread.wait(2000):
                            logger.warning("批量识别线程未能在2秒内结束，强制终止")
                            self.batch_recognition_thread.terminate()
                            self.batch_recognition_thread.wait(1000)
                    self.batch_recognition_thread.deleteLater()
                    self.batch_recognition_thread = None
                    logger.info("批量识别线程已清理")
                except Exception as e:
                    logger.error("清理批量识别线程失败: %s", e)

            # 3. 清理流式消息气泡
            if self.current_streaming_bubble is not None:
                if hasattr(self.current_streaming_bubble, "cleanup"):
                    self.current_streaming_bubble.cleanup()
                self.current_streaming_bubble = None
            try:
                self._reset_stream_render_state()
            except Exception:
                pass

            # 4. 清理打字指示器
            if hasattr(self, "typing_indicator") and self.typing_indicator is not None:
                if hasattr(self.typing_indicator, "stop_animation"):
                    self.typing_indicator.stop_animation()
                self.typing_indicator = None

            # 5. 清理表情选择器
            if self.emoji_picker is not None:
                self.emoji_picker.close()
                self.emoji_picker = None

            # 5.5 清理设置面板（懒加载情况下可能为 None）
            if getattr(self, "settings_panel", None) is not None:
                try:
                    if hasattr(self.settings_panel, "cleanup"):
                        self.settings_panel.cleanup()
                except Exception as e:
                    logger.debug("清理 SettingsPanel 时出错: %s", e)
                try:
                    self.settings_panel.deleteLater()
                except Exception:
                    pass
                self.settings_panel = None

            # 6. 清理消息缓存
            if hasattr(self, "_message_cache"):
                self._message_cache.clear()

            # 7. 清理 Agent 资源
            if self.agent is not None:
                logger.info("清理 Agent 资源...")
                try:
                    if hasattr(self.agent, 'close'):
                        self.agent.close()
                except Exception as e:
                    logger.warning("关闭 Agent 时出错: %s", e)
                finally:
                    self.agent = None

            # 8. 清理 TTS 工作线程和队列
            if hasattr(self, "tts_workers") and self.tts_workers:
                logger.info("清理 %s 个 TTS 工作线程...", len(self.tts_workers))
                # 先停止所有正在运行的线程
                for worker in self.tts_workers:
                    try:
                        if worker.isRunning():
                            worker.requestInterruption()  # 请求中断
                            if not worker.wait(2000):  # 等待最多2秒
                                worker.terminate()  # 强制终止
                                worker.wait(1000)  # 再等待1秒
                        worker.deleteLater()
                    except Exception as e:
                            logger.debug("清理 TTS worker 时出错: %s", e)
                self.tts_workers.clear()
            
            # 清理TTS队列和状态
            if hasattr(self, "tts_queue"):
                self.tts_queue.clear()
            if hasattr(self, "tts_busy"):
                self.tts_busy = False

            # 9. 清理线程池
            if hasattr(self, "thread_pool"):
                self.thread_pool.waitForDone(1000)  # 等待最多1秒

            logger.info("资源清理完成")
        except Exception as e:
            from src.utils.exceptions import handle_exception

            handle_exception(e, logger, "清理资源时出错")

        # 调用父类的 closeEvent
        super().closeEvent(event)

    def setup_window_animation(self):
        """设置窗口启动动画 - 优雅的淡入效果

        使用透明度动画实现平滑的窗口显示效果
        """
        # 创建透明度效果
        self.window_opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.window_opacity_effect)

        # 淡入动画
        self.window_fade_in = QPropertyAnimation(self.window_opacity_effect, b"opacity")
        self.window_fade_in.setDuration(600)  # 600ms 优雅淡入
        self.window_fade_in.setStartValue(0.0)
        self.window_fade_in.setEndValue(1.0)
        self.window_fade_in.setEasingCurve(QEasingCurve.Type.OutCubic)

        # 动画完成后移除效果，减少GPU负担
        self.window_fade_in.finished.connect(lambda: self.setGraphicsEffect(None))

        # 延迟启动动画，确保窗口已显示
        QTimer.singleShot(50, self.window_fade_in.start)

    def _init_tts_system(self):
        """初始化 TTS 系统 (v2.48.13，参考 MoeChat 逻辑，统一使用多模态初始化结果)"""
        try:
            from src.config.settings import settings
            from src.multimodal import (
                get_tts_manager_instance,
                get_tts_config_instance,
                is_tts_available,
                get_audio_player,
            )
            from src.utils.stream_processor import StreamProcessor

            # 检查 TTS 配置
            if not hasattr(settings, "tts") or not settings.tts or not settings.tts.enabled:
                logger.info("TTS 未启用")
                return

            logger.info("开始初始化 TTS 系统...")

            # 使用多模态模块中已经初始化好的 TTS 管理器 / 配置
            tts_manager = get_tts_manager_instance()
            tts_config = get_tts_config_instance()

            if not tts_manager or not tts_config:
                # init_tts 可能仍在后台初始化：这里不直接“永久禁用”，而是有限次重试，避免启动阻塞。
                retry_count = int(getattr(self, "_tts_init_retry_count", 0))
                if retry_count < 8 and not getattr(self, "_tts_init_retry_scheduled", False):
                    self._tts_init_retry_count = retry_count + 1
                    self._tts_init_retry_scheduled = True
                    delay_ms = 500 if retry_count == 0 else 1500

                    def _retry() -> None:
                        self._tts_init_retry_scheduled = False
                        self._init_tts_system()

                    QTimer.singleShot(delay_ms, _retry)
                    logger.info(
                        "TTS 尚未就绪（等待 init_tts 完成），%0.1fs 后重试 (%d/8)",
                        delay_ms / 1000.0,
                        self._tts_init_retry_count,
                    )
                self.tts_enabled = False
                return

            # 只有当 TTS 连接测试成功时才允许启用 TTS
            if not is_tts_available():
                # 连接测试结果可能仍在后台更新（init_tts 健康检查尚未结束），这里同样做有限次重试。
                retry_count = int(getattr(self, "_tts_health_retry_count", 0))
                if retry_count < 8 and not getattr(self, "_tts_health_retry_scheduled", False):
                    self._tts_health_retry_count = retry_count + 1
                    self._tts_health_retry_scheduled = True
                    delay_ms = 800 if retry_count == 0 else 2000

                    def _retry() -> None:
                        self._tts_health_retry_scheduled = False
                        self._init_tts_system()

                    QTimer.singleShot(delay_ms, _retry)
                    logger.info(
                        "TTS 健康检查未就绪/未通过，%0.1fs 后重试 (%d/8)",
                        delay_ms / 1000.0,
                        self._tts_health_retry_count,
                    )
                else:
                    logger.warning("TTS 服务连接测试未通过，暂不启用 TTS")
                self.tts_enabled = False
                return

            self.tts_manager = tts_manager

            # 获取音频播放器
            self.audio_player = get_audio_player(
                default_volume=settings.tts.default_volume,
                max_queue_size=settings.tts.max_queue_size,
            )

            # 创建流式文本处理器
            # v2.48.13: 将最小句子长度从 5 降低到 3，避免短句（如“好啊！”、“嗯。”）被过滤掉导致 TTS 丢句
            self.tts_stream_processor = StreamProcessor(
                min_sentence_length=3,
                max_buffer_size=500,
            )

            # 启用 TTS
            self.tts_enabled = True

            logger.info("TTS 系统初始化成功")

        except Exception as e:
            logger.error("TTS 系统初始化失败: %s", e)
            self.tts_enabled = False

    def _synthesize_tts_async(self, text: str):
        """异步合成 TTS 音频 (v2.48.13 优化版，单线程队列顺序播放，参考 MoeChat)"""
        if not self.tts_enabled or not self.tts_manager or not self.audio_player:
            return

        if not text or not text.strip():
            return
        
        # v2.48.14: 最终过滤保护层 - 确保工具调用信息不会进入TTS
        # 即使前面的过滤有遗漏，这里也会再次过滤
        if self._needs_tool_filter(text):
            text = self._filter_tool_info_safe(text)
        
        # 如果过滤后为空或只包含空白，直接返回
        if not text or not text.strip():
            logger.debug("TTS 跳过空文本（最终过滤后）")
            return

        # 如果当前已有 TTS 任务在执行，则加入队列，保持顺序播放
        if getattr(self, "tts_busy", False):
            self.tts_queue.append(text)
            logger.debug("TTS 任务加入队列: %s...", text[:20])
            return

        try:
            # 使用 QThread 在后台执行 TTS 合成
            from PyQt6.QtCore import QThread, pyqtSignal
            import asyncio

            class TTSWorker(QThread):
                """TTS 合成工作线程"""
                audio_ready = pyqtSignal(bytes)
                error_occurred = pyqtSignal(str)

                def __init__(self, tts_manager, text):
                    super().__init__()
                    self.tts_manager = tts_manager
                    self.text = text

                def run(self):
                    """运行 TTS 合成"""
                    loop = None
                    try:
                        # 创建新的 event loop
                        loop = asyncio.new_event_loop()
                        # 绑定新的 event loop
                        asyncio.set_event_loop(loop)

                        # 执行异步合成
                        audio_data = loop.run_until_complete(
                            self.tts_manager.synthesize_text(self.text)
                        )

                        # 发送音频数据
                        if audio_data:
                            self.audio_ready.emit(audio_data)
                        else:
                            # 合成返回None，可能是服务不可用或合成失败
                            self.error_occurred.emit("TTS 合成返回空结果")

                    except asyncio.CancelledError:
                        # 任务被取消，不记录错误
                        pass
                    except Exception as e:
                        error_msg = f"TTS 合成失败: {e}"
                        logger.error(error_msg, exc_info=False)
                        self.error_occurred.emit(error_msg)
                    finally:
                        # 确保清理事件循环
                        if loop:
                            try:
                                # 取消所有待处理的任务
                                pending = asyncio.all_tasks(loop)
                                for task in pending:
                                    task.cancel()
                                # 等待所有任务完成
                                if pending:
                                    loop.run_until_complete(
                                        asyncio.gather(*pending, return_exceptions=True)
                                    )
                            except Exception:
                                pass
                            finally:
                                try:
                                    loop.close()
                                except Exception:
                                    pass

            # 标记为忙碌
            self.tts_busy = True

            # 创建并启动 worker
            worker = TTSWorker(self.tts_manager, text)
            
            # 处理音频播放成功
            def on_audio_ready(audio_data: bytes):
                """处理音频数据就绪"""
                try:
                    if self.audio_player:
                        success = self.audio_player.play_audio(audio_data)
                        if not success:
                            logger.warning("音频播放失败，但继续处理队列")
                except Exception as e:
                    logger.error("播放音频时出错: %s", e)
            
            worker.audio_ready.connect(on_audio_ready)
            
            # 处理错误（确保清理状态）
            def on_error_occurred(error_msg: str):
                """处理TTS合成错误"""
                logger.error(error_msg)
                # 错误发生时也要清理状态，避免队列卡住
                if not worker.isRunning():
                    cleanup_worker()
            
            worker.error_occurred.connect(on_error_occurred)

            # 线程完成后清理
            def cleanup_worker():
                """清理完成的工作线程，并调度下一个队列任务"""
                try:
                    if worker in self.tts_workers:
                        self.tts_workers.remove(worker)
                    worker.deleteLater()
                except Exception as e:
                        logger.debug("清理 TTS worker 时出错: %s", e)
                finally:
                    # 当前任务结束
                    self.tts_busy = False
                    # 如果队列中还有待处理的句子，继续下一个
                    if self.tts_queue:
                        next_text = self.tts_queue.pop(0)
                        # 使用定时器避免在回调中同步递归调用
                        QTimer.singleShot(0, lambda: self._synthesize_tts_async(next_text))

            worker.finished.connect(cleanup_worker)

            # 保存到列表，防止被垃圾回收
            self.tts_workers.append(worker)

            # 启动线程
            worker.start()

            logger.debug("TTS 合成任务已启动: %s...", text[:20])

        except Exception as e:
            logger.error("TTS 合成失败: %s", e)
            self.tts_busy = False
