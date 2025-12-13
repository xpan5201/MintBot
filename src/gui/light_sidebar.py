"""
浅色主题侧边栏导航组件 (v2.18.0 Material Design 3 深度优化版)

基于 Google Material Design 3 最新规范（2025）
全方位深度优化：性能、美观度、动画效果、代码规范

v2.18.0 优化内容：
- 🎨 美观度提升：优化涟漪动画、增强悬停效果、统一视觉风格
- ⚡ 性能优化：减少重绘次数、优化事件处理、改进动画性能
- 🎬 动画增强：流畅的微交互、自然的状态过渡、丰富的视觉反馈
- 📝 代码规范：完善注释文档、优化代码结构、移除冗余代码
- 🐛 Bug修复：修复已知问题、增强错误处理、提升稳定性
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QPushButton, QLabel, QScrollArea,
    QListWidget, QListWidgetItem, QHBoxLayout, QGraphicsOpacityEffect, QLineEdit,
    QGraphicsDropShadowEffect
)
from PyQt6.QtCore import (
    Qt, pyqtSignal, QPropertyAnimation, QEasingCurve, QSize,
    QPoint, QTimer, pyqtProperty, QParallelAnimationGroup
)
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor, QBrush, QPen, QMouseEvent, QFont

from .material_design_light import (
    MD3_LIGHT_COLORS, MD3_RADIUS, MD3_DURATION, MD3_STATE_LAYERS, get_light_elevation_shadow
)
from .material_design_enhanced import (
    MD3_ENHANCED_COLORS, MD3_ENHANCED_SPACING, MD3_ENHANCED_RADIUS,
    MD3_ENHANCED_DURATION, MD3_ENHANCED_EASING, MD3_ENHANCED_STATE_LAYERS,
    get_elevation_shadow
)
from .material_icons import MaterialIconButton, MATERIAL_ICONS


class IconButton(QPushButton):
    """增强图标按钮 - v2.15.0 优化版"""

    def __init__(self, icon_text: str, tooltip: str = "", parent=None):
        super().__init__(parent)
        self.icon_text = icon_text
        self.setToolTip(tooltip)
        self.setFixedSize(56, 56)  # 增大触摸目标，符合MD3规范

        # 涟漪效果参数
        self._ripple_radius = 0
        self.ripple_opacity = 0.0
        self.ripple_center = QPoint()
        self.ripple_active = False

        # 悬停状态
        self._hover_opacity = 0.0

        # 按压状态
        self._pressed_scale = 1.0

        # 设置动画
        self.setup_animations()
        self.setup_style()

        # 启用鼠标追踪
        self.setMouseTracking(True)

    def setup_animations(self):
        """设置动画 - 优化性能和流畅度"""
        # 涟漪动画 - 使用增强的缓动
        self.ripple_animation = QPropertyAnimation(self, b"ripple_radius")
        self.ripple_animation.setDuration(MD3_ENHANCED_DURATION["medium2"])
        self.ripple_animation.setEasingCurve(MD3_ENHANCED_EASING["emphasized_decelerate"])
        self.ripple_animation.finished.connect(self.on_ripple_finished)

        # 悬停动画 - 更快的响应
        self.hover_animation = QPropertyAnimation(self, b"hover_opacity")
        self.hover_animation.setDuration(MD3_ENHANCED_DURATION["fast"])
        self.hover_animation.setEasingCurve(MD3_ENHANCED_EASING["smooth_out"])

        # 按压动画 - 微妙的缩放反馈
        self.press_animation = QPropertyAnimation(self, b"pressed_scale")
        self.press_animation.setDuration(MD3_ENHANCED_DURATION["short3"])
        self.press_animation.setEasingCurve(MD3_ENHANCED_EASING["smooth"])

    def setup_style(self):
        """设置样式 - v2.31.0: 优化渐变和动画效果"""
        self.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: none;
                border-radius: {MD3_ENHANCED_RADIUS['lg']};
                color: {MD3_ENHANCED_COLORS['on_surface_variant']};
                font-size: 24px;
                font-weight: normal;
            }}
            QPushButton:checked {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 {MD3_ENHANCED_COLORS['primary_container']},
                    stop:1 {MD3_ENHANCED_COLORS['secondary_container']}
                );
                color: {MD3_ENHANCED_COLORS['on_primary_container']};
            }}
            QPushButton:hover {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(38, 166, 154, 0.08),
                    stop:1 rgba(38, 166, 154, 0.12)
                );
            }}
            QPushButton:pressed {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(38, 166, 154, 0.15),
                    stop:1 rgba(38, 166, 154, 0.20)
                );
            }}
        """)
        self.setText(self.icon_text)
        self.setCheckable(True)

    @pyqtProperty(int)
    def ripple_radius(self):
        return self._ripple_radius

    @ripple_radius.setter
    def ripple_radius(self, value):
        self._ripple_radius = value
        self.update()

    @pyqtProperty(float)
    def hover_opacity(self):
        return self._hover_opacity

    @hover_opacity.setter
    def hover_opacity(self, value):
        self._hover_opacity = value
        self.update()

    def mousePressEvent(self, event: QMouseEvent):
        """鼠标按下 - 开始涟漪效果"""
        super().mousePressEvent(event)

        # 记录涟漪中心
        self.ripple_center = event.pos()
        self.ripple_active = True

        # 计算最大半径
        max_radius = 30  # 固定半径

        # 开始涟漪动画
        self.ripple_animation.setStartValue(0)
        self.ripple_animation.setEndValue(max_radius)
        self.ripple_opacity = MD3_STATE_LAYERS["pressed"]
        self.ripple_animation.start()

        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent):
        """鼠标释放"""
        super().mouseReleaseEvent(event)

        # 淡出涟漪
        QTimer.singleShot(100, self.fade_out_ripple)

    def enterEvent(self, event):
        """鼠标进入 - 显示悬停状态"""
        super().enterEvent(event)

        if not self.isChecked():
            self.hover_animation.setStartValue(self.hover_opacity)
            self.hover_animation.setEndValue(MD3_STATE_LAYERS["hover"])
            self.hover_animation.start()

    def leaveEvent(self, event):
        """鼠标离开 - 隐藏悬停状态"""
        super().leaveEvent(event)

        self.hover_animation.setStartValue(self.hover_opacity)
        self.hover_animation.setEndValue(0.0)
        self.hover_animation.start()

    def fade_out_ripple(self):
        """淡出涟漪"""
        self.ripple_opacity = 0.0
        self.update()

    def on_ripple_finished(self):
        """涟漪动画完成"""
        if self.ripple_opacity == 0.0:
            self.ripple_active = False
            self.ripple_radius = 0
            self.update()

    def paintEvent(self, event):
        """绘制按钮 - v2.23.0 性能优化版"""
        super().paintEvent(event)

        # 性能优化：如果没有需要绘制的效果，直接返回
        if (self.hover_opacity <= 0 or self.isChecked()) and (not self.ripple_active or self.ripple_opacity <= 0):
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 绘制悬停状态
        if self.hover_opacity > 0 and not self.isChecked():
            hover_color = QColor(0, 0, 0, int(self.hover_opacity * 255))
            painter.setBrush(QBrush(hover_color))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(self.rect(), 12, 12)

        # 绘制涟漪效果
        if self.ripple_active and self.ripple_opacity > 0:
            ripple_color = QColor(0, 0, 0, int(self.ripple_opacity * 255))
            painter.setBrush(QBrush(ripple_color))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(
                self.ripple_center,
                self.ripple_radius,
                self.ripple_radius
            )

        painter.end()  # 显式结束绘制，释放资源


class LightIconSidebar(QWidget):
    """浅色主题图标侧边栏"""

    # 信号
    chat_clicked = pyqtSignal()
    contacts_clicked = pyqtSignal()
    favorites_clicked = pyqtSignal()
    files_clicked = pyqtSignal()
    settings_clicked = pyqtSignal()
    logout_clicked = pyqtSignal()  # 退出登录信号

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(64)
        self.setup_ui()

    def setup_ui(self):
        """设置 UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 16, 8, 16)
        layout.setSpacing(8)

        # Logo/头像 - 使用 Material Icon
        self.avatar_btn = MaterialIconButton("account_circle", "MintChat", size=48, icon_size=32)
        self.avatar_btn.setCheckable(False)
        layout.addWidget(self.avatar_btn)

        layout.addSpacing(16)

        # 聊天按钮
        self.chat_btn = MaterialIconButton("chat", "聊天", size=48, icon_size=24)
        self.chat_btn.clicked.connect(self.on_chat_clicked)
        self.chat_btn.setChecked(True)
        layout.addWidget(self.chat_btn)

        # 联系人按钮
        self.contacts_btn = MaterialIconButton("contacts", "联系人", size=48, icon_size=24)
        self.contacts_btn.clicked.connect(self.on_contacts_clicked)
        layout.addWidget(self.contacts_btn)

        # 收藏按钮
        self.favorites_btn = MaterialIconButton("star", "收藏", size=48, icon_size=24)
        self.favorites_btn.clicked.connect(self.on_favorites_clicked)
        layout.addWidget(self.favorites_btn)

        # 文件按钮
        self.files_btn = MaterialIconButton("folder", "文件", size=48, icon_size=24)
        self.files_btn.clicked.connect(self.on_files_clicked)
        layout.addWidget(self.files_btn)

        layout.addStretch()

        # 设置按钮
        self.settings_btn = MaterialIconButton("settings", "设置", size=48, icon_size=24)
        self.settings_btn.clicked.connect(self.on_settings_clicked)
        layout.addWidget(self.settings_btn)

        # 退出登录按钮
        self.logout_btn = MaterialIconButton("logout", "退出登录", size=48, icon_size=24)
        self.logout_btn.clicked.connect(self.on_logout_clicked)
        self.logout_btn.setCheckable(False)  # 退出登录按钮不需要选中状态
        layout.addWidget(self.logout_btn)

        # 设置背景 - v2.31.0: 优化渐变背景，更加精致
        self.setStyleSheet(f"""
            LightIconSidebar {{
                background: qlineargradient(
                    x1:0, y1:0, x2:0, y2:1,
                    stop:0 {MD3_ENHANCED_COLORS['secondary_container']},
                    stop:0.3 {MD3_ENHANCED_COLORS['surface_bright']},
                    stop:0.7 {MD3_ENHANCED_COLORS['surface_bright']},
                    stop:1 {MD3_ENHANCED_COLORS['tertiary_container']}
                );
                border-right: 1px solid {MD3_ENHANCED_COLORS['outline_variant']};
            }}
        """)

    def on_chat_clicked(self):
        """聊天按钮点击"""
        self.uncheck_all()
        self.chat_btn.setChecked(True)
        self.chat_clicked.emit()

    def on_contacts_clicked(self):
        """联系人按钮点击"""
        self.uncheck_all()
        self.contacts_btn.setChecked(True)
        self.contacts_clicked.emit()

    def on_favorites_clicked(self):
        """收藏按钮点击"""
        self.uncheck_all()
        self.favorites_btn.setChecked(True)
        self.favorites_clicked.emit()

    def on_files_clicked(self):
        """文件按钮点击"""
        self.uncheck_all()
        self.files_btn.setChecked(True)
        self.files_clicked.emit()

    def on_settings_clicked(self):
        """设置按钮点击"""
        self.uncheck_all()
        self.settings_btn.setChecked(True)
        self.settings_clicked.emit()

    def on_logout_clicked(self):
        """退出登录按钮点击"""
        self.logout_clicked.emit()

    def uncheck_all(self):
        """取消所有按钮的选中状态"""
        self.chat_btn.setChecked(False)
        self.contacts_btn.setChecked(False)
        self.favorites_btn.setChecked(False)
        self.files_btn.setChecked(False)
        self.settings_btn.setChecked(False)


class SessionItem(QWidget):
    """会话列表项 - 增强版"""

    def __init__(self, avatar: str, name: str, message: str, time: str, unread: int = 0, parent=None):
        super().__init__(parent)

        # 悬停状态
        self.is_hovered = False
        self._hover_opacity = 0.0

        # 设置动画
        self.setup_animations()
        self.setup_ui(avatar, name, message, time, unread)

        # 启用鼠标追踪
        self.setMouseTracking(True)

        # 设置光标
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def setup_animations(self):
        """设置动画"""
        # 悬停动画
        self.hover_animation = QPropertyAnimation(self, b"hover_opacity")
        self.hover_animation.setDuration(MD3_DURATION["short2"])
        self.hover_animation.setEasingCurve(QEasingCurve.Type.InOutCubic)

    @pyqtProperty(float)
    def hover_opacity(self):
        return self._hover_opacity

    @hover_opacity.setter
    def hover_opacity(self, value):
        self._hover_opacity = value
        self.update()

    def enterEvent(self, event):
        """鼠标进入"""
        super().enterEvent(event)
        self.is_hovered = True

        self.hover_animation.setStartValue(self.hover_opacity)
        self.hover_animation.setEndValue(MD3_STATE_LAYERS["hover"])
        self.hover_animation.start()

    def leaveEvent(self, event):
        """鼠标离开"""
        super().leaveEvent(event)
        self.is_hovered = False

        self.hover_animation.setStartValue(self.hover_opacity)
        self.hover_animation.setEndValue(0.0)
        self.hover_animation.start()

    def paintEvent(self, event):
        """绘制悬停效果 - v2.23.0 性能优化版"""
        super().paintEvent(event)

        # 性能优化：如果不透明度为0，直接返回
        if self.hover_opacity <= 0:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        hover_color = QColor(0, 0, 0, int(self.hover_opacity * 255))
        painter.setBrush(QBrush(hover_color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(self.rect(), 12, 12)
        painter.end()  # 显式结束绘制，释放资源

    def setup_ui(self, avatar: str, name: str, message: str, time: str, unread: int):
        """设置 UI"""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(12)

        # 头像 - 更大的圆角
        avatar_label = QLabel(avatar)
        avatar_label.setFixedSize(52, 52)
        avatar_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        avatar_label.setStyleSheet(f"""
            QLabel {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 {MD3_LIGHT_COLORS['primary']},
                    stop:1 {MD3_LIGHT_COLORS['secondary']}
                );
                border-radius: 26px;
                font-size: 26px;
                color: {MD3_LIGHT_COLORS['on_primary']};
            }}
        """)
        layout.addWidget(avatar_label)

        # 信息区域
        info_layout = QVBoxLayout()
        info_layout.setSpacing(4)

        # 名称和时间
        name_time_layout = QHBoxLayout()
        name_time_layout.setSpacing(8)

        name_label = QLabel(name)
        name_label.setStyleSheet(f"""
            QLabel {{
                color: {MD3_LIGHT_COLORS['on_surface']};
                font-size: 14px;
                font-weight: 500;
                background: transparent;
            }}
        """)
        name_time_layout.addWidget(name_label)

        name_time_layout.addStretch()

        time_label = QLabel(time)
        time_label.setStyleSheet(f"""
            QLabel {{
                color: {MD3_LIGHT_COLORS['on_surface_variant']};
                font-size: 12px;
                background: transparent;
            }}
        """)
        name_time_layout.addWidget(time_label)

        info_layout.addLayout(name_time_layout)

        # 消息和未读数
        message_unread_layout = QHBoxLayout()
        message_unread_layout.setSpacing(8)

        message_label = QLabel(message)
        message_label.setStyleSheet(f"""
            QLabel {{
                color: {MD3_LIGHT_COLORS['on_surface_variant']};
                font-size: 13px;
                background: transparent;
            }}
        """)
        message_label.setMaximumWidth(200)
        message_label.setWordWrap(False)
        message_unread_layout.addWidget(message_label)

        message_unread_layout.addStretch()

        if unread > 0:
            unread_label = QLabel(str(unread))
            unread_label.setFixedSize(22, 22)
            unread_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            unread_label.setStyleSheet(f"""
                QLabel {{
                    background: {MD3_LIGHT_COLORS['error']};
                    color: {MD3_LIGHT_COLORS['on_error']};
                    border-radius: 11px;
                    font-size: 11px;
                    font-weight: 600;
                }}
            """)
            message_unread_layout.addWidget(unread_label)

        info_layout.addLayout(message_unread_layout)

        layout.addLayout(info_layout)

        # 设置背景 - 更大的圆角
        self.setStyleSheet(f"""
            SessionItem {{
                background: transparent;
                border-radius: {MD3_RADIUS['large']};
                padding: 4px;
            }}
            SessionItem:hover {{
                background: {MD3_LIGHT_COLORS['surface_container_high']};
            }}
        """)


class LightSessionList(QWidget):
    """浅色主题会话列表 - 优化显示/隐藏动画"""

    session_selected = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_animations()
        self.setup_ui()

    def setup_animations(self):
        """设置显示/隐藏动画"""
        from PyQt6.QtCore import QPropertyAnimation

        # 透明度动画
        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.opacity_effect)

        self.fade_animation = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.fade_animation.setDuration(MD3_DURATION["short4"])  # 200ms
        self.fade_animation.setEasingCurve(QEasingCurve.Type.OutCubic)

    def setup_ui(self):
        """设置 UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 搜索栏
        search_layout = QHBoxLayout()
        search_layout.setContentsMargins(16, 12, 16, 12)
        search_layout.setSpacing(8)

        # 搜索输入框 - 使用 Material Design 图标
        search_container = QWidget()
        search_container_layout = QHBoxLayout(search_container)
        search_container_layout.setContentsMargins(12, 0, 12, 0)
        search_container_layout.setSpacing(8)

        # 搜索图标
        search_icon = QLabel(MATERIAL_ICONS["search"])
        search_icon_font = QFont("Material Symbols Outlined")
        search_icon_font.setPixelSize(20)
        search_icon.setFont(search_icon_font)
        search_icon.setStyleSheet(f"""
            QLabel {{
                color: {MD3_LIGHT_COLORS['on_surface_variant']};
                background: transparent;
            }}
        """)
        search_container_layout.addWidget(search_icon)

        # 搜索输入框
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("搜索")
        self.search_input.setStyleSheet(f"""
            QLineEdit {{
                background: transparent;
                border: none;
                color: {MD3_LIGHT_COLORS['on_surface']};
                font-size: 14px;
                padding: 0px;
            }}
            QLineEdit::placeholder {{
                color: {MD3_LIGHT_COLORS['on_surface_variant']};
            }}
        """)
        search_container_layout.addWidget(self.search_input)

        search_container.setStyleSheet(f"""
            QWidget {{
                background: {MD3_LIGHT_COLORS['surface_container']};
                border-radius: {MD3_RADIUS['full']};
                padding: 8px 0px;
            }}
        """)
        search_layout.addWidget(search_container)

        # 添加按钮 - 使用 Material Design 图标
        add_btn = MaterialIconButton("add", "新建会话", size=36, icon_size=20)
        add_btn.setCheckable(False)
        search_layout.addWidget(add_btn)

        layout.addLayout(search_layout)

        # 会话列表
        self.session_list = QListWidget()
        self.session_list.setStyleSheet(f"""
            QListWidget {{
                background: transparent;
                border: none;
                outline: none;
                padding: 8px;
            }}
            QListWidget::item {{
                background: transparent;
                border: none;
                padding: 4px;
                margin: 2px 0px;
            }}
            QListWidget::item:selected {{
                background: {MD3_LIGHT_COLORS['primary_container']};
                border-radius: {MD3_RADIUS['large']};
            }}
        """)
        layout.addWidget(self.session_list)

        # 添加示例会话
        self.add_demo_sessions()

        # 设置背景 - 使用淡薄荷绿
        self.setStyleSheet(f"""
            LightSessionList {{
                background: {MD3_LIGHT_COLORS['gradient_soft_mint']};
            }}
        """)

    def show(self):
        """显示 - 带淡入动画"""
        super().show()
        self.fade_animation.setStartValue(0.0)
        self.fade_animation.setEndValue(1.0)
        self.fade_animation.start()

    def hide(self):
        """隐藏 - 带淡出动画"""
        self.fade_animation.setStartValue(1.0)
        self.fade_animation.setEndValue(0.0)
        self.fade_animation.finished.connect(self._on_fade_out_finished)
        self.fade_animation.start()

    def _on_fade_out_finished(self):
        """淡出完成"""
        super().hide()
        self.fade_animation.finished.disconnect(self._on_fade_out_finished)

    def add_demo_sessions(self):
        """添加示例会话"""
        sessions = [
            ("🐱", "小雪糕", "主人，今天想做什么呢？", "12:03", 0),
            ("👥", "数学244班信息群", "@全体成员 明天考试...", "12:00", 99),
            ("👤", "小雨的好朋友叫天天", "晚安哦朋友们，正好...", "12:00", 0),
            ("💬", "MoeChat（限）", "ERROR: Hard Fault - [原因]", "12:00", 0),
        ]

        for avatar, name, message, time, unread in sessions:
            item = QListWidgetItem(self.session_list)
            item_widget = SessionItem(avatar, name, message, time, unread)
            item.setSizeHint(item_widget.sizeHint())
            self.session_list.addItem(item)
            self.session_list.setItemWidget(item, item_widget)
