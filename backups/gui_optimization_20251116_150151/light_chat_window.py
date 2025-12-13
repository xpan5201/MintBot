"""
浅色主题聊天窗口 - Material Design 3 标准规范版

严格遵循 Google Material Design 3 官方规范（2025）
https://m3.material.io/

核心特性：
- 🎨 Material Design 3 设计规范
- 💬 流式输出，实时显示
- 🖼️ 自定义头像（emoji/图片）
- ⚡ 性能优化，流畅体验
- 📱 QQ风格界面设计

详细更新历史请查看 docs/CHANGELOG.md
"""

from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QScrollArea,
    QLabel,
    QSizePolicy,
    QStackedWidget,
    QGraphicsOpacityEffect,
    QGraphicsDropShadowEffect,
    QApplication,  # v2.30.13: 用于强制处理事件
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
from typing import Optional
import re
import time

# 预编译正则表达式，提升性能
STICKER_PATTERN = re.compile(r"\[STICKER:([^\]]+)\]")

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
from .emoji_picker import EmojiPicker
from .settings_panel import SettingsPanel
from .enhanced_rich_input import EnhancedInputWidget
from .loading_states import EmptyState
from .notifications import show_toast, Toast
from .contacts_panel import ContactsPanel
from src.agent.core import MintChatAgent
from src.utils.logger import get_logger
from src.auth.user_session import user_session
from src.utils.gui_optimizer import throttle, track_object

# 初始化 logger
logger = get_logger(__name__)


def _create_avatar_label_for_header(avatar_text: str, size: int) -> QLabel:
    """创建聊天窗口头部的头像标签（支持 emoji 和图片路径）- v2.23.1 优化：真正的圆形头像

    Args:
        avatar_text: 头像文本（emoji 或图片路径）
        size: 头像大小（像素）

    Returns:
        QLabel: 配置好的头像标签
    """
    from PyQt6.QtGui import QPainter, QBrush, QPainterPath, QRegion

    avatar_label = QLabel()
    avatar_label.setFixedSize(size, size)
    avatar_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

    # 检查是否为图片路径
    if avatar_text and Path(avatar_text).exists() and Path(avatar_text).is_file():
        # 图片路径：加载图片
        pixmap = QPixmap(avatar_text)
        if not pixmap.isNull():
            # 缩放图片
            scaled_pixmap = pixmap.scaled(
                size,
                size,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            # 裁剪为正方形
            if scaled_pixmap.width() > size or scaled_pixmap.height() > size:
                x = (scaled_pixmap.width() - size) // 2
                y = (scaled_pixmap.height() - size) // 2
                scaled_pixmap = scaled_pixmap.copy(x, y, size, size)

            # v2.23.1 创建圆形遮罩
            rounded_pixmap = QPixmap(size, size)
            rounded_pixmap.fill(Qt.GlobalColor.transparent)

            painter = QPainter(rounded_pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

            # 创建圆形路径
            path = QPainterPath()
            path.addEllipse(0, 0, size, size)

            # 裁剪并绘制
            painter.setClipPath(path)
            painter.drawPixmap(0, 0, scaled_pixmap)
            painter.end()

            avatar_label.setPixmap(rounded_pixmap)
            avatar_label.setScaledContents(False)
        else:
            # 图片加载失败，使用默认 emoji
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
    """聊天线程 - v2.30.6 增强资源管理"""

    chunk_received = pyqtSignal(str)
    finished = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(
        self,
        agent: MintChatAgent,
        message: str,
        image_path: Optional[str] = None,
        image_analysis: Optional[dict] = None,
        timeout: float = 300.0,  # v2.30.6: 添加超时控制（5分钟）
    ):
        super().__init__()
        self.agent = agent
        self.message = message
        self.image_path = image_path
        self.image_analysis = image_analysis
        self.timeout = timeout
        self._is_running = True
        self._python_thread = None
        self._start_time = None  # v2.30.6: 记录开始时间

        # v2.29.1: 跟踪线程对象，检测内存泄漏
        track_object(self, f"ChatThread-{message[:20]}")

        # v2.25.0 修复：优先级将在 run() 开始时设置
        # 不能在 __init__ 中设置，因为线程还没有启动

    def run(self):
        """运行线程 - v2.30.6 增强超时控制和资源管理"""
        try:
            # v2.25.0 修复：在线程启动后设置优先级
            # 设置低优先级，避免阻塞UI线程
            self.setPriority(QThread.Priority.LowPriority)

            # v2.30.6: 记录开始时间
            self._start_time = time.time()

            logger.info(f"ChatThread开始运行，消息: {self.message[:50]}...")

            # v2.24.6 修复：使用标准Python线程执行LLM调用
            # 这样可以避免PyQt的QThread与OpenSSL的冲突
            import threading
            import queue

            chunk_queue = queue.Queue()
            error_holder = {"error": None}

            def llm_worker():
                """在标准Python线程中执行LLM调用"""
                try:
                    logger.info("LLM工作线程开始")
                    # v3.3: 默认保存到长期记忆，确保重启后不丢失
                    # v2.30.0: 传递图片分析结果
                    for chunk in self.agent.chat_stream(
                        self.message,
                        save_to_long_term=True,
                        image_path=self.image_path,
                        image_analysis=self.image_analysis
                    ):
                        if not self._is_running:
                            break
                        chunk_queue.put(("chunk", chunk))
                    chunk_queue.put(("done", None))
                    logger.info("LLM工作线程完成")
                except Exception as e:
                    from src.utils.exceptions import handle_exception

                    handle_exception(e, logger, "LLM工作线程错误")
                    error_holder["error"] = e
                    chunk_queue.put(("error", str(e)))

            # 启动标准Python线程
            self._python_thread = threading.Thread(target=llm_worker, daemon=True)
            self._python_thread.start()

            # 从队列读取并发送信号
            chunk_buffer = []
            chunk_count = 0
            total_chunks = 0

            while self._is_running:
                try:
                    # v2.30.6: 检查超时
                    if time.time() - self._start_time > self.timeout:
                        logger.warning(f"ChatThread超时 ({self.timeout}秒)")
                        self.error.emit(f"请求超时（{self.timeout}秒），请稍后重试")
                        break

                    msg_type, data = chunk_queue.get(timeout=0.1)

                    if msg_type == "chunk":
                        total_chunks += 1
                        chunk_buffer.append(data)
                        chunk_count += 1

                        # v2.30.13: 深度优化流式速度，模拟真实打字效果
                        # 每1个字符或遇到标点符号时发送，增加延迟到80-120ms
                        if chunk_count >= 1 or data in "。！？，、；：\n":
                            self.chunk_received.emit("".join(chunk_buffer))
                            chunk_buffer = []
                            chunk_count = 0
                            # v2.30.13: 增加延迟，模拟真实打字速度（80-120ms/字符）
                            # 相当于每秒显示8-12个字符，接近真实打字速度
                            # 标点符号后稍微停顿更久，更自然
                            if data in "。！？\n":
                                self.msleep(150)  # 句子结束，停顿150ms
                            elif data in "，、；：":
                                self.msleep(100)  # 逗号等，停顿100ms
                            else:
                                self.msleep(80)  # 普通字符，停顿80ms

                    elif msg_type == "done":
                        # 发送剩余chunk
                        if chunk_buffer:
                            self.chunk_received.emit("".join(chunk_buffer))

                        # v2.30.6: 记录执行时间
                        execution_time = time.time() - self._start_time
                        logger.info(
                            f"ChatThread完成，共接收 {total_chunks} 个chunk，"
                            f"耗时 {execution_time:.2f}秒"
                        )
                        self.finished.emit()
                        break

                    elif msg_type == "error":
                        self.error.emit(data)
                        break

                except queue.Empty:
                    continue

        except Exception as e:
            from src.utils.exceptions import handle_exception

            handle_exception(e, logger, "ChatThread运行失败")
            if self._is_running:
                self.error.emit(str(e))

    def stop(self):
        """停止线程 - v2.30.6 增强清理"""
        logger.info("正在停止ChatThread...")
        self._is_running = False

        # v2.30.6: 等待Python线程结束
        if self._python_thread and self._python_thread.is_alive():
            self._python_thread.join(timeout=2.0)
            if self._python_thread.is_alive():
                logger.warning("Python线程未能在2秒内结束")

    def cleanup(self):
        """清理资源 - v2.30.6 新增"""
        self.stop()
        self.agent = None
        self.message = None
        self.image_path = None
        self.image_analysis = None
        logger.info("ChatThread资源已清理")


class LightChatWindow(LightFramelessWindow):
    """浅色主题聊天窗口 - v2.15.0 优化版"""

    def __init__(self):
        super().__init__("MintChat - 猫娘女仆智能体")

        # 初始化 Agent - 使用用户特定路径
        try:
            user_id = user_session.get_user_id()
            username = user_session.get_username()

            logger.info(f"开始初始化 Agent...")
            logger.info(f"当前用户: {username} (ID: {user_id})")
            logger.info(f"用户已登录: {user_session.is_logged_in()}")

            self.agent = MintChatAgent(user_id=user_id)
            logger.info(f"✅ Agent 初始化成功 (用户ID: {user_id if user_id else '全局'})")
        except Exception as e:
            from src.utils.exceptions import handle_exception

            handle_exception(e, logger, "初始化 Agent 失败")
            self.agent = None

        # 当前流式消息气泡
        self.current_streaming_bubble = None

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

        # 设置窗口大小
        self.resize(1200, 800)

        # 页面切换动画
        self.page_fade_animation = None

        # 设置内容
        self.setup_content()

        # 窗口启动动画
        self.setup_window_animation()

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
        chat_layout = QVBoxLayout(chat_area)
        chat_layout.setContentsMargins(0, 0, 0, 0)
        chat_layout.setSpacing(0)

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

        # 创建设置面板
        self.settings_panel = SettingsPanel()
        self.settings_panel.back_clicked.connect(self._on_settings_back)
        self.settings_panel.settings_saved.connect(self._on_settings_saved)
        self.stacked_widget.addWidget(self.settings_panel)

        # 默认显示聊天区域
        self.stacked_widget.setCurrentIndex(0)

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
        # v2.30.8: 防止添加空消息
        if not message or not message.strip():
            logger.warning(f"尝试添加空消息，已忽略: is_user={is_user}")
            return

        # v2.29.10: 使用预编译的正则表达式，提升性能
        has_stickers = bool(STICKER_PATTERN.search(message))

        if has_stickers:
            # 混合消息：需要分段处理
            self._add_mixed_message(message, is_user, with_animation)
        elif message.startswith("[STICKER:") and message.endswith("]"):
            # 纯表情包消息（向后兼容）
            sticker_path = message[9:-1]
            bubble = LightImageMessageBubble(sticker_path, is_user, is_sticker=True)
            self.messages_layout.insertWidget(self.messages_layout.count() - 1, bubble)

            # v2.30.8: 强制显示气泡
            bubble.show()
            self.messages_layout.update()
            QTimer.singleShot(10, lambda: self.scroll_area.widget().updateGeometry())
        else:
            # 纯文本消息
            bubble = LightMessageBubble(message, is_user)

            # v2.30.8: 计算插入位置 - 总是插入到最后（stretch之前）
            insert_position = self.messages_layout.count() - 1
            logger.debug(f"插入消息: is_user={is_user}, position={insert_position}, total_count={self.messages_layout.count()}")

            self.messages_layout.insertWidget(insert_position, bubble)

            # v2.30.8: 强制显示气泡
            bubble.show()  # 确保气泡可见

            # v2.30.13: 立即更新布局，避免错位
            self.messages_layout.update()
            self.scroll_area.widget().updateGeometry()
            QApplication.processEvents()  # 强制处理事件，确保布局立即生效

            if with_animation:
                bubble.show_with_animation()

        # 保存到数据库和缓存
        if save_to_db:
            if user_session.is_logged_in():
                try:
                    role = "user" if is_user else "assistant"
                    user_session.add_message(self.current_contact, role, message)
                    logger.debug(f"消息已保存: {self.current_contact} - {role}")

                    # v2.30.14: 更新缓存（注意：这里没有msg_id，因为是新消息）
                    # 缓存将在下次加载历史消息时更新
                    # 这里不再维护缓存，避免不一致
                except Exception as e:
                    from src.utils.exceptions import handle_exception

                    handle_exception(e, logger, "保存消息到数据库失败")

        # v2.30.13 修复：立即滚动到底部，避免错位
        # 先立即滚动一次，确保消息在正确位置
        self._ensure_scroll_to_bottom()

        # 如果有动画，再延迟滚动一次，确保动画完成后也在底部
        if with_animation:
            QTimer.singleShot(200, self._ensure_scroll_to_bottom)

    def _add_mixed_message(self, message: str, is_user: bool, with_animation: bool):
        """添加混合消息（文字+表情包）- v2.29.9 优化：性能和内存优化

        Args:
            message: 混合消息内容
            is_user: 是否为用户消息
            with_animation: 是否显示动画
        """
        from PyQt6.QtWidgets import QWidget, QHBoxLayout
        from src.utils.logger import get_logger

        logger = get_logger(__name__)

        try:
            # 创建容器
            container = QWidget()
            layout = QHBoxLayout(container)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(8)

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
                        text_bubble = LightMessageBubble(part, is_user)
                        if with_animation:
                            text_bubble.show_with_animation()
                        widgets.append(text_bubble)
                else:
                    # 表情包部分（part 是路径）
                    sticker_bubble = LightImageMessageBubble(part, is_user, is_sticker=True)
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
            logger.error(f"添加混合消息失败: {e}", exc_info=True)
            # 降级处理：作为纯文本消息添加
            bubble = LightMessageBubble(message, is_user)
            if with_animation:
                bubble.show_with_animation()
            self.messages_layout.insertWidget(self.messages_layout.count() - 1, bubble)

    def _add_image_message(self, image_path: str, is_user: bool = True):
        """添加图片消息 - v2.18.1 新增

        Args:
            image_path: 图片文件路径
            is_user: 是否为用户消息
        """
        bubble = LightImageMessageBubble(image_path, is_user)
        self.messages_layout.insertWidget(self.messages_layout.count() - 1, bubble)
        # 延迟滚动到底部，等待动画完成
        QTimer.singleShot(200, self._scroll_to_bottom)

    @throttle(150)
    def _scroll_to_bottom(self):
        """滚动到底部（节流优化，最多每150ms滚动一次）"""
        scrollbar = self.scroll_area.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _ensure_scroll_to_bottom(self):
        """确保滚动到底部（绕过节流限制）- v2.30.9 新增"""
        scrollbar = self.scroll_area.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _show_typing_indicator(self):
        """显示打字指示器 - v2.30.8 修复：确保插入到正确位置"""
        # 先移除旧的打字指示器（如果存在）
        if hasattr(self, "typing_indicator") and self.typing_indicator is not None:
            self._hide_typing_indicator()

        self.typing_indicator = LightTypingIndicator()
        # v2.30.8: 插入到最后（stretch之前）
        insert_position = self.messages_layout.count() - 1
        logger.debug(f"显示打字指示器: position={insert_position}, total_count={self.messages_layout.count()}")
        self.messages_layout.insertWidget(insert_position, self.typing_indicator)

        # v2.30.8: 强制显示和更新
        self.typing_indicator.show()
        self.messages_layout.update()
        QTimer.singleShot(10, lambda: self.scroll_area.widget().updateGeometry())

    def _hide_typing_indicator(self):
        """隐藏打字指示器"""
        if hasattr(self, "typing_indicator") and self.typing_indicator is not None:
            self.typing_indicator.stop_animation()
            self.messages_layout.removeWidget(self.typing_indicator)
            self.typing_indicator.deleteLater()
            self.typing_indicator = None

    def _on_chunk_received(self, chunk: str):
        """接收到流式输出块 - v2.30.13 优化：修复布局错位和闪烁问题"""
        # 隐藏打字指示器（只在第一次）
        if hasattr(self, "typing_indicator") and self.typing_indicator is not None:
            self._hide_typing_indicator()

        # 创建或更新流式消息气泡
        if self.current_streaming_bubble is None:
            self.current_streaming_bubble = LightStreamingMessageBubble()
            self.messages_layout.insertWidget(
                self.messages_layout.count() - 1, self.current_streaming_bubble
            )

            # v2.30.13: 立即更新布局，避免错位
            self.messages_layout.update()
            self.scroll_area.widget().updateGeometry()
            QApplication.processEvents()  # 强制处理事件，确保布局立即生效

            # v2.30.10: 显示入场动画
            if hasattr(self.current_streaming_bubble, 'show_with_animation'):
                self.current_streaming_bubble.show_with_animation()

            # v2.30.13: 立即滚动到底部，确保气泡在正确位置
            self._ensure_scroll_to_bottom()

        # 追加文本（内部已优化，使用定时器批量更新）
        self.current_streaming_bubble.append_text(chunk)

        # v2.30.13 优化：使用更短的延迟（100ms），提升响应速度
        if not hasattr(self, "_scroll_timer"):
            self._scroll_timer = QTimer()
            self._scroll_timer.setSingleShot(True)
            self._scroll_timer.timeout.connect(self._ensure_scroll_to_bottom)
        self._scroll_timer.start(100)  # v2.30.13: 100ms 延迟，更快响应

    def _on_chat_finished(self):
        """聊天完成 - v2.30.14 增强资源清理"""
        if self.current_streaming_bubble:
            # 获取完整的AI回复文本
            full_response = self.current_streaming_bubble.message_text.toPlainText()

            # 完成流式输出
            self.current_streaming_bubble.finish()
            self.current_streaming_bubble = None

            # 保存AI回复到数据库
            if user_session.is_logged_in() and full_response.strip():
                try:
                    user_session.add_message(self.current_contact, "assistant", full_response)
                    logger.debug(f"AI回复已保存: {self.current_contact} - assistant")
                except Exception as e:
                    logger.error(f"保存AI回复失败: {e}")

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
                logger.warning(f"清理ChatThread失败: {e}")

        # 启用发送按钮
        self.send_btn.setEnabled(True)

        # 清理滚动定时器
        if hasattr(self, "_scroll_timer"):
            self._scroll_timer.stop()
            del self._scroll_timer

        # 最终滚动到底部
        QTimer.singleShot(100, self._scroll_to_bottom)

    def _on_chat_error(self, error: str):
        """聊天错误 - v2.30.14 增强资源清理"""
        self._hide_typing_indicator()
        self._add_message(f"错误: {error}", is_user=False)

        # v2.30.14: 清理聊天线程
        if self.current_chat_thread is not None:
            try:
                self.current_chat_thread.cleanup()
                self.current_chat_thread.deleteLater()
                self.current_chat_thread = None
            except Exception as e:
                logger.warning(f"清理ChatThread失败: {e}")

        # 清理流式气泡
        if self.current_streaming_bubble is not None:
            self.current_streaming_bubble = None

        self.send_btn.setEnabled(True)

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

                # v2.30.8: 强制立即滚动到底部
                QTimer.singleShot(100, lambda: self.scroll_area.verticalScrollBar().setValue(
                    self.scroll_area.verticalScrollBar().maximum()
                ))

                # 保存到数据库
                if user_session.is_logged_in():
                    try:
                        user_session.add_message(
                            self.current_contact,
                            "user",
                            f"[STICKER:{sticker_path}]"
                        )
                    except Exception as e:
                        logger.error(f"保存表情包消息失败: {e}")

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

                    # v2.30.8: 强制立即滚动到底部
                    QTimer.singleShot(100, lambda: self.scroll_area.verticalScrollBar().setValue(
                        self.scroll_area.verticalScrollBar().maximum()
                    ))

                    # 保存到数据库
                    if user_session.is_logged_in():
                        try:
                            user_session.add_message(
                                self.current_contact,
                                "user",
                                f"[IMAGE:{image_path}]"
                            )
                        except Exception as e:
                            logger.error(f"保存图片消息失败: {e}")

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

                # v2.30.9: 优化滚动逻辑 - 合并为单次滚动，在打字指示器显示后执行
                QTimer.singleShot(150, self._ensure_scroll_to_bottom)

                # 创建并启动聊天线程
                self.current_chat_thread = ChatThread(self.agent, text)
                self.current_chat_thread.chunk_received.connect(self._on_chunk_received)
                self.current_chat_thread.finished.connect(self._on_chat_finished)
                self.current_chat_thread.error.connect(self._on_chat_error)
                self.current_chat_thread.start()

                # 禁用发送按钮
                self.send_btn.setEnabled(False)

        except Exception as e:
            logger.error(f"发送消息失败: {e}", exc_info=True)
            show_toast(self, f"发送失败: {e}", Toast.TYPE_ERROR)

    def _on_emoji_clicked(self):
        """表情按钮点击 - v2.19.0 升级版"""
        # 创建表情选择器（如果还没有）
        if self.emoji_picker is None:
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
        from src.utils.logger import get_logger

        logger = get_logger(__name__)

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
            logger.debug(f"表情包转换: {sticker_path} -> {description}")

        logger.info(f"消息转换: {message} -> {result}")
        return result

    def _on_sticker_selected(self, sticker_path: str):
        """自定义表情包选中 - v2.30.7 优化：使用富文本内联显示

        优化内容：
        1. 使用富文本内联显示表情包图片
        2. 可以与文字一起发送
        3. 更直观的视觉效果
        """
        try:
            logger.info(f"选中表情包: {sticker_path}")

            # v2.30.7: 使用增强输入框插入表情包（内联显示）
            self.enhanced_input.insert_sticker(sticker_path)

            logger.debug("表情包已插入到输入框（内联显示）")

        except Exception as e:
            logger.error(f"插入表情包失败: {e}", exc_info=True)

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
                    logger.warning(f"不支持的文件类型: {file_path}")

    def _add_pending_image(self, image_path: str):
        """添加待发送图片到预览区域 (v2.30.2 新增)"""
        from PyQt6.QtWidgets import QLabel, QPushButton, QVBoxLayout
        from PyQt6.QtGui import QPixmap
        from PyQt6.QtCore import Qt
        from src.gui.material_design_light import MD3_LIGHT_COLORS

        # 检查是否已添加
        if image_path in self.pending_images:
            logger.debug(f"图片已在待发送列表中: {image_path}")
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

        logger.info(f"添加待发送图片: {image_path}, 当前共 {len(self.pending_images)} 张")

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

        logger.info(f"移除待发送图片: {image_path}, 剩余 {len(self.pending_images)} 张")

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
        from src.multimodal.vision import vision_processor

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

                    results = []
                    total = len(self.image_paths)

                    # v2.30.6: 使用线程池并发处理
                    with ThreadPoolExecutor(max_workers=self.max_concurrent) as executor:
                        # 提交所有任务
                        future_to_index = {
                            executor.submit(
                                vision_processor.smart_analyze,
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
                                logger.error(f"识别图片 {image_path} 失败: {e}")
                                # 继续处理其他图片

                    # v2.30.6: 按原始顺序排序结果
                    results.sort(key=lambda x: x[0])
                    sorted_results = [r[1] for r in results]

                    self.finished.emit(sorted_results)
                except Exception as e:
                    logger.error(f"批量识别失败: {e}")
                    self.error.emit(str(e))

            def stop(self):
                """停止识别 - v2.30.6 新增"""
                self._is_running = False

        # 创建并启动线程
        self.batch_recognition_thread = BatchImageRecognitionThread(
            image_paths, mode, self.agent.llm if self.agent else None
        )
        self.batch_recognition_thread.progress.connect(
            lambda idx, total, result: logger.info(f"图片识别进度: {idx}/{total}")
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

        logger.info(f"批量识别完成: {len(results)} 张图片")

    def _handle_image_upload(self, image_path: str):
        """处理图片上传和识别 (v2.30.0 新增，v2.30.2 已弃用，保留用于兼容)"""
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton, QHBoxLayout, QRadioButton, QButtonGroup
        from src.gui.material_design_light import MD3_LIGHT_COLORS

        # 显示图片消息气泡
        self._add_image_message(image_path, is_user=True)
        logger.debug(f"发送图片: {image_path}")

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
        from src.multimodal.vision import vision_processor

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
                    result = vision_processor.smart_analyze(
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

        logger.info(f"图片识别完成: {image_path}, 模式: {result.get('mode')}")

    def _on_chat_clicked(self):
        """聊天按钮点击 - 返回聊天界面"""
        # 切换回聊天区域
        self.stacked_widget.setCurrentIndex(0)
        # 显示提示
        show_toast(self, "已返回聊天界面", Toast.TYPE_INFO, duration=1500)

    def _on_settings_clicked(self):
        """设置按钮点击"""
        # 切换到设置面板
        self.stacked_widget.setCurrentIndex(1)
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

        # 保存当前联系人的聊天历史
        if self.current_contact and user_session.is_logged_in():
            self._save_current_chat_history()

        # 切换联系人
        self.current_contact = contact_name
        logger.info(f"选中联系人: {contact_name}")

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
        self.send_btn.setEnabled(True)

        # 显示提示
        show_toast(self, f"已切换到 {contact_name} 的对话", Toast.TYPE_INFO, duration=2000)

    def _load_chat_history(self, contact_name: str, limit: int = 20):
        """加载聊天历史 - v2.30.12 优化：分页加载，缓存机制，性能提升

        Args:
            contact_name: 联系人名称
            limit: 加载消息数量（默认20条，避免一次加载过多）
        """

        try:
            logger.info(f"开始加载聊天历史: {contact_name} (limit={limit})")
            logger.info(f"用户已登录: {user_session.is_logged_in()}")

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
            logger.info(f"消息总数: {total_count}")

            # 从数据库加载最近的聊天历史（性能优化：限制数量）
            messages = user_session.get_chat_history(contact_name, limit=limit, offset=0)

            if not messages:
                # 没有历史消息，显示欢迎消息
                logger.info(f"没有历史消息，显示欢迎消息")
                self._add_message(
                    f"开始与 {contact_name} 的对话吧！", is_user=False, save_to_db=False
                )
                return

            # v2.30.12: 缓存加载的消息（使用消息ID去重）
            for msg in messages:
                msg_id = msg.get('id')
                if msg_id:
                    self._message_cache[contact_name][msg_id] = msg

            # v2.21.3 优化：禁用滚动区域更新，批量加载消息
            self.scroll_area.setUpdatesEnabled(False)

            # 显示历史消息（v2.21.3 优化：禁用动画，避免闪烁）
            logger.info(f"开始显示 {len(messages)} 条历史消息")
            for i, msg in enumerate(messages):
                is_user = msg["role"] == "user"
                # v2.21.3 关键优化：with_animation=False 禁用入场动画
                self._add_message(
                    msg["content"], is_user=is_user, save_to_db=False, with_animation=False
                )
                if (i + 1) % 10 == 0:
                    logger.debug(f"已显示 {i + 1}/{len(messages)} 条消息")

            # v2.30.12: 更新已加载消息数量
            self._loaded_message_count[contact_name] = len(messages)

            # v2.21.3 优化：重新启用更新并滚动到底部（只滚动一次）
            self.scroll_area.setUpdatesEnabled(True)
            QTimer.singleShot(50, self._scroll_to_bottom)

            # v2.30.12: 如果还有更多消息，显示提示
            if total_count > limit:
                logger.info(f"还有 {total_count - limit} 条历史消息未加载")

            logger.info(f"✅ 已加载 {len(messages)}/{total_count} 条历史消息（联系人: {contact_name}）")
        except Exception as e:
            from src.utils.exceptions import handle_exception

            handle_exception(e, logger, "加载聊天历史失败")

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
                logger.info(f"已加载全部 {total_count} 条消息")
                show_toast(self, "已加载全部历史消息", Toast.TYPE_INFO, duration=2000)
                return

            # 计算还需要加载的消息数量
            remaining = total_count - loaded_count
            load_count = min(limit, remaining)

            logger.info(f"加载更多历史消息: offset={loaded_count}, limit={load_count}")

            # 从数据库加载更多消息
            messages = user_session.get_chat_history(
                contact_name, limit=load_count, offset=loaded_count
            )

            if not messages:
                logger.warning("没有加载到更多消息")
                return

            # v2.30.12: 缓存新加载的消息
            for msg in messages:
                msg_id = msg.get('id')
                if msg_id and msg_id not in self._message_cache.get(contact_name, {}):
                    self._message_cache[contact_name][msg_id] = msg

            # 禁用滚动区域更新
            self.scroll_area.setUpdatesEnabled(False)

            # 记录当前滚动位置
            scrollbar = self.scroll_area.verticalScrollBar()
            old_value = scrollbar.value()
            old_max = scrollbar.maximum()

            # 在顶部插入历史消息（禁用动画）
            logger.info(f"在顶部插入 {len(messages)} 条历史消息")
            for i, msg in enumerate(reversed(messages)):  # 反转以保持时间顺序
                is_user = msg["role"] == "user"
                # 在顶部插入（索引0）
                self._insert_message_at_top(
                    msg["content"], is_user=is_user, with_animation=False
                )

            # 更新已加载消息数量
            self._loaded_message_count[contact_name] += len(messages)

            # 重新启用更新
            self.scroll_area.setUpdatesEnabled(True)

            # v2.30.12: 保持滚动位置（避免跳动）
            QTimer.singleShot(10, lambda: self._restore_scroll_position(old_value, old_max))

            logger.info(
                f"✅ 已加载 {self._loaded_message_count[contact_name]}/{total_count} 条历史消息"
            )
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
        bubble = LightMessageBubble(message, is_user)

        # 在顶部插入（索引0）
        self.messages_layout.insertWidget(0, bubble)

        if with_animation:
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
                logger.info(f"滚动到顶部，自动加载更多历史消息")
                self._is_loading_more = True

                # 延迟加载，避免频繁触发
                QTimer.singleShot(200, lambda: self._load_more_with_reset())

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
                        logger.warning(f"清理 widget 资源时出错: {e}")

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
            logger.info(f"AI助手头像已刷新: {ai_avatar}")

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
                    logger.info(f"清除会话失败: {e}")

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
                    logger.info(f"会话已保存到: {session_file}")
                else:
                    if session_file.exists():
                        session_file.unlink()
                        logger.info("已清除保存的会话")

                # 设置用户会话（关键修复：退出登录后再次登录时必须设置）
                user_session.login(user, session_token)
                logger.info(f"用户会话已设置: {user['username']} (ID: {user['id']})")
            except Exception as e:
                from src.utils.exceptions import handle_exception

                logger.info(f"保存会话失败: {e}")
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

                logger.info(f"创建聊天窗口失败: {e}")
                handle_exception(e, logger, "创建聊天窗口失败")

        self.auth_manager.login_success.connect(on_login_success)
        self.auth_manager.show()

    def _setup_avatar_pulse_animation(self):
        """设置头像脉冲动画 - 在线状态指示器

        使用缩放动画模拟心跳效果，提升视觉吸引力
        """
        # 创建缩放动画
        self.avatar_pulse_animation = QPropertyAnimation(self.avatar_label, b"minimumSize")
        self.avatar_pulse_animation.setDuration(1500)  # 1.5秒一个周期
        self.avatar_pulse_animation.setStartValue(self.avatar_label.size())
        self.avatar_pulse_animation.setKeyValueAt(0.5, self.avatar_label.size() * 1.05)  # 放大5%
        self.avatar_pulse_animation.setEndValue(self.avatar_label.size())
        self.avatar_pulse_animation.setEasingCurve(QEasingCurve.Type.InOutSine)
        self.avatar_pulse_animation.setLoopCount(-1)  # 无限循环

        # 同步最大尺寸动画
        self.avatar_pulse_animation_max = QPropertyAnimation(self.avatar_label, b"maximumSize")
        self.avatar_pulse_animation_max.setDuration(1500)
        self.avatar_pulse_animation_max.setStartValue(self.avatar_label.size())
        self.avatar_pulse_animation_max.setKeyValueAt(0.5, self.avatar_label.size() * 1.05)
        self.avatar_pulse_animation_max.setEndValue(self.avatar_label.size())
        self.avatar_pulse_animation_max.setEasingCurve(QEasingCurve.Type.InOutSine)
        self.avatar_pulse_animation_max.setLoopCount(-1)

        # 延迟启动，避免与窗口动画冲突
        QTimer.singleShot(800, self.avatar_pulse_animation.start)
        QTimer.singleShot(800, self.avatar_pulse_animation_max.start)

    def closeEvent(self, event):
        """窗口关闭事件 - 清理资源（v2.23.0 增强版）"""
        try:
            logger.info("聊天窗口正在关闭，清理资源...")

            # 1. 停止所有动画
            if hasattr(self, "avatar_pulse_animation") and self.avatar_pulse_animation:
                self.avatar_pulse_animation.stop()
            if hasattr(self, "avatar_pulse_animation_max") and self.avatar_pulse_animation_max:
                self.avatar_pulse_animation_max.stop()
            if hasattr(self, "page_fade_animation") and self.page_fade_animation:
                self.page_fade_animation.stop()

            # 2. 停止正在运行的聊天线程
            if self.current_chat_thread is not None and self.current_chat_thread.isRunning():
                logger.info("停止聊天线程...")
                self.current_chat_thread.stop()
                self.current_chat_thread.wait(2000)  # 等待最多2秒
                self.current_chat_thread = None

            # 3. 清理流式消息气泡
            if self.current_streaming_bubble is not None:
                if hasattr(self.current_streaming_bubble, "cleanup"):
                    self.current_streaming_bubble.cleanup()
                self.current_streaming_bubble = None

            # 4. 清理打字指示器
            if hasattr(self, "typing_indicator") and self.typing_indicator is not None:
                if hasattr(self.typing_indicator, "stop_animation"):
                    self.typing_indicator.stop_animation()
                self.typing_indicator = None

            # 5. 清理表情选择器
            if self.emoji_picker is not None:
                self.emoji_picker.close()
                self.emoji_picker = None

            # 6. 清理消息缓存
            if hasattr(self, "_message_cache"):
                self._message_cache.clear()

            # 7. 清理 Agent 资源
            if self.agent is not None:
                logger.info("清理 Agent 资源...")
                self.agent = None

            # 8. 清理线程池
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
