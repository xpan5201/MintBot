"""
联系人管理面板 (v2.23.1 Material Design 3 深度优化版 - 圆形头像)

基于 Google Material Design 3 最新规范（2025）
全方位深度优化：性能、美观度、交互反馈、代码规范

v2.23.1 优化内容：
- 🎨 圆形头像：所有头像显示为真正的圆形
- 🖼️ 自定义头像：支持联系人自定义头像（emoji 和图片路径）
- 📸 图片上传：支持从本地选择图片作为联系人头像
- 🔄 头像刷新：实时更新联系人头像显示

v2.18.0 优化内容：
- 🎨 美观度提升：优化列表项样式、增强悬停效果、统一视觉风格
- ⚡ 性能优化：减少重绘次数、优化动画性能、改进内存管理
- 🎬 动画增强：流畅的微交互、自然的状态过渡、丰富的视觉反馈
- 📝 代码规范：完善注释文档、优化代码结构、提升可维护性
- 🐛 Bug修复：修复右键菜单问题、增强错误处理、提升稳定性
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QLineEdit, QDialog, QPushButton,
    QMenu, QInputDialog, QMessageBox, QFileDialog
)
from PyQt6.QtCore import Qt, pyqtSignal, QPropertyAnimation, QEasingCurve, pyqtProperty
from PyQt6.QtGui import QFont, QPainter, QColor, QBrush, QAction, QPainterPath, QPixmap
from functools import lru_cache
from pathlib import Path

from .material_design_light import MD3_LIGHT_COLORS, MD3_RADIUS, MD3_DURATION, MD3_STATE_LAYERS
from .material_design_enhanced import (
    MD3_ENHANCED_COLORS, MD3_ENHANCED_SPACING, MD3_ENHANCED_RADIUS,
    MD3_ENHANCED_DURATION, MD3_ENHANCED_EASING,
    get_typography_css
)
from .material_icons import MaterialIconButton, MATERIAL_ICONS
from src.auth.user_session import user_session
from src.utils.logger import get_logger

logger = get_logger(__name__)


@lru_cache(maxsize=128)
def _load_rounded_avatar_pixmap(image_path: str, size: int, mtime_ns: int) -> QPixmap:
    """加载并裁剪为圆形头像（带缓存）。"""
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


def _create_contact_avatar_label(avatar_text: str, size: int) -> QLabel:
    """创建联系人头像标签（支持 emoji 和图片路径）- v2.23.1 新增

    Args:
        avatar_text: 头像文本（emoji 或图片路径）
        size: 头像大小（像素）

    Returns:
        QLabel: 配置好的圆形头像标签
    """
    avatar_label = QLabel()
    avatar_label.setFixedSize(size, size)
    avatar_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

    # 检查是否为图片路径
    avatar_path = Path(avatar_text) if avatar_text else None
    if avatar_path and avatar_path.exists() and avatar_path.is_file():
        try:
            mtime_ns = avatar_path.stat().st_mtime_ns
        except OSError:
            mtime_ns = 0

        rounded_pixmap = _load_rounded_avatar_pixmap(str(avatar_path), size, mtime_ns)
        if not rounded_pixmap.isNull():
            avatar_label.setPixmap(rounded_pixmap)
            avatar_label.setScaledContents(False)
        else:
            avatar_label.setText("👤")
    else:
        # emoji 或无效路径：直接显示文本
        avatar_label.setText(avatar_text if avatar_text else "👤")

    # 设置样式
    avatar_label.setStyleSheet(f"""
        QLabel {{
            background: {MD3_LIGHT_COLORS['gradient_mint_cyan']};
            border-radius: {size // 2}px;
            font-size: {size // 2}px;
            color: {MD3_LIGHT_COLORS['on_primary']};
        }}
    """)

    return avatar_label


class ContactItem(QWidget):
    """联系人列表项 - v2.15.1 优化版（支持右键菜单）"""

    clicked = pyqtSignal(str)  # 发送联系人名称
    rename_requested = pyqtSignal(str, str)  # 发送旧名称和新名称
    delete_requested = pyqtSignal(str)  # 发送联系人名称

    def __init__(self, avatar: str, name: str, status: str = "在线", parent=None):
        super().__init__(parent)

        self.contact_name = name
        self.avatar = avatar
        self.status = status
        self.is_hovered = False
        self._hover_opacity = 0.0
        self._scale = 1.0

        # 设置动画
        self.setup_animations()
        self.setup_ui(avatar, name, status)

        # 启用鼠标追踪
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        # 设置最小高度，符合MD3触摸目标
        self.setMinimumHeight(64)

        # 启用右键菜单
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)

    def setup_animations(self):
        """设置动画 - 优化流畅度"""
        # 悬停动画 - 更快的响应
        self.hover_animation = QPropertyAnimation(self, b"hover_opacity")
        self.hover_animation.setDuration(MD3_ENHANCED_DURATION["fast"])
        self.hover_animation.setEasingCurve(MD3_ENHANCED_EASING["smooth_out"])

        # 缩放动画 - 微妙的反馈
        self.scale_animation = QPropertyAnimation(self, b"scale")
        self.scale_animation.setDuration(MD3_ENHANCED_DURATION["short3"])
        self.scale_animation.setEasingCurve(MD3_ENHANCED_EASING["smooth"])

    @pyqtProperty(float)
    def hover_opacity(self):
        return self._hover_opacity

    @hover_opacity.setter
    def hover_opacity(self, value):
        self._hover_opacity = value
        self.update()

    @pyqtProperty(float)
    def scale(self):
        """缩放属性 - v2.25.0 修复：添加缺失的属性定义"""
        return self._scale

    @scale.setter
    def scale(self, value):
        """设置缩放 - v2.25.0 修复：添加缺失的属性定义"""
        self._scale = value
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

    def mousePressEvent(self, event):
        """鼠标点击"""
        super().mousePressEvent(event)
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.contact_name)

    def show_context_menu(self, pos):
        """显示右键菜单 - v2.15.1 新增"""
        menu = QMenu(self)

        # 设置菜单样式 - Material Design 3
        menu.setStyleSheet(f"""
            QMenu {{
                background: {MD3_ENHANCED_COLORS['surface_container_high']};
                color: {MD3_ENHANCED_COLORS['on_surface']};
                border: 1px solid {MD3_ENHANCED_COLORS['outline_variant']};
                border-radius: {MD3_ENHANCED_RADIUS['md']};
                padding: {MD3_ENHANCED_SPACING['1']};
                {get_typography_css('body_medium')}
            }}
            QMenu::item {{
                padding: {MD3_ENHANCED_SPACING['2']} {MD3_ENHANCED_SPACING['4']};
                border-radius: {MD3_ENHANCED_RADIUS['sm']};
                min-height: 40px;
            }}
            QMenu::item:selected {{
                background: {MD3_ENHANCED_COLORS['primary_container']};
                color: {MD3_ENHANCED_COLORS['on_primary_container']};
            }}
            QMenu::separator {{
                height: 1px;
                background: {MD3_ENHANCED_COLORS['outline_variant']};
                margin: {MD3_ENHANCED_SPACING['1']} {MD3_ENHANCED_SPACING['2']};
            }}
        """)

        # 重命名操作
        rename_action = QAction("✏️ 重命名", self)
        rename_action.triggered.connect(self.rename_contact)
        menu.addAction(rename_action)

        # 分隔符
        menu.addSeparator()

        # 删除操作
        delete_action = QAction("🗑️ 删除", self)
        delete_action.triggered.connect(self.delete_contact)
        menu.addAction(delete_action)

        # 显示菜单
        menu.exec(self.mapToGlobal(pos))

    def rename_contact(self):
        """重命名联系人"""
        new_name, ok = QInputDialog.getText(
            self,
            "重命名联系人",
            "请输入新名称：",
            QLineEdit.EchoMode.Normal,
            self.contact_name
        )

        if ok and new_name and new_name != self.contact_name:
            self.rename_requested.emit(self.contact_name, new_name)

    def delete_contact(self):
        """删除联系人"""
        reply = QMessageBox.question(
            self,
            "删除联系人",
            f"确定要删除联系人 '{self.contact_name}' 吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.delete_requested.emit(self.contact_name)

    def paintEvent(self, event):
        """绘制悬停效果 - 优化性能"""
        super().paintEvent(event)

        # 只在需要时绘制悬停效果
        if self.hover_opacity > 0.01:  # 避免不必要的绘制
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)

            # 使用薄荷绿色作为悬停颜色
            hover_color = QColor(MD3_LIGHT_COLORS['primary'])
            hover_color.setAlphaF(self.hover_opacity)

            painter.setBrush(QBrush(hover_color))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(self.rect(), 12, 12)

    def setup_ui(self, avatar: str, name: str, status: str):
        """设置 UI - v2.23.1 优化：使用圆形头像"""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(12)

        # 头像 - v2.23.1 使用圆形头像函数
        self.avatar_label = _create_contact_avatar_label(avatar, 48)
        layout.addWidget(self.avatar_label)

        # 信息区域
        info_layout = QVBoxLayout()
        info_layout.setSpacing(4)

        # 名称
        name_label = QLabel(name)
        name_label.setStyleSheet(f"""
            QLabel {{
                color: {MD3_LIGHT_COLORS['on_surface']};
                font-size: 14px;
                font-weight: 500;
                background: transparent;
            }}
        """)
        info_layout.addWidget(name_label)

        # 状态
        status_label = QLabel(f"● {status}")
        status_label.setStyleSheet(f"""
            QLabel {{
                color: {MD3_LIGHT_COLORS['on_surface_variant']};
                font-size: 12px;
                background: transparent;
            }}
        """)
        info_layout.addWidget(status_label)

        layout.addLayout(info_layout)
        layout.addStretch()

        # 设置背景
        self.setStyleSheet(f"""
            ContactItem {{
                background: transparent;
                border-radius: {MD3_RADIUS['large']};
                padding: 4px;
            }}
        """)


class AddContactDialog(QDialog):
    """添加联系人对话框 - Material Design 3 风格"""

    contact_added = pyqtSignal(str, str)  # 发送 (名称, 头像)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle("添加联系人")
        self.setFixedSize(400, 300)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        # 初始透明度
        self._opacity = 0.0

        self.setup_ui()
        self.setup_animations()

    def setup_animations(self):
        """设置进入/退出动画"""
        # 淡入动画
        self.fade_in_animation = QPropertyAnimation(self, b"windowOpacity")
        self.fade_in_animation.setDuration(MD3_DURATION["medium1"])  # 250ms
        self.fade_in_animation.setStartValue(0.0)
        self.fade_in_animation.setEndValue(1.0)
        self.fade_in_animation.setEasingCurve(QEasingCurve.Type.OutCubic)

        # 淡出动画
        self.fade_out_animation = QPropertyAnimation(self, b"windowOpacity")
        self.fade_out_animation.setDuration(MD3_DURATION["short4"])  # 200ms
        self.fade_out_animation.setStartValue(1.0)
        self.fade_out_animation.setEndValue(0.0)
        self.fade_out_animation.setEasingCurve(QEasingCurve.Type.InCubic)
        self.fade_out_animation.finished.connect(self._on_fade_out_finished)

    def showEvent(self, event):
        """显示时播放淡入动画"""
        super().showEvent(event)
        self.fade_in_animation.start()

    def accept(self):
        """接受时播放淡出动画"""
        self._accepted = True
        self.fade_out_animation.start()

    def reject(self):
        """拒绝时播放淡出动画"""
        self._accepted = False
        self.fade_out_animation.start()

    def _on_fade_out_finished(self):
        """淡出动画完成"""
        if self._accepted:
            super().accept()
        else:
            super().reject()

    def setup_ui(self):
        """设置 UI"""
        # 主容器
        container = QWidget(self)
        container.setStyleSheet(f"""
            QWidget {{
                background: {MD3_LIGHT_COLORS['surface']};
                border-radius: {MD3_RADIUS['extra_large']};
            }}
        """)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # 标题
        title_label = QLabel("添加联系人")
        title_label.setStyleSheet(f"""
            QLabel {{
                color: {MD3_LIGHT_COLORS['on_surface']};
                font-size: 20px;
                font-weight: 600;
                background: transparent;
            }}
        """)
        layout.addWidget(title_label)

        # 名称输入
        name_label = QLabel("联系人名称")
        name_label.setStyleSheet(f"""
            QLabel {{
                color: {MD3_LIGHT_COLORS['on_surface_variant']};
                font-size: 12px;
                background: transparent;
            }}
        """)
        layout.addWidget(name_label)

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("请输入联系人名称")
        self.name_input.setStyleSheet(f"""
            QLineEdit {{
                background: {MD3_LIGHT_COLORS['surface_container']};
                border: 1px solid {MD3_LIGHT_COLORS['outline']};
                border-radius: {MD3_RADIUS['small']};
                color: {MD3_LIGHT_COLORS['on_surface']};
                font-size: 14px;
                padding: 12px 16px;
            }}
            QLineEdit:focus {{
                border: 2px solid {MD3_LIGHT_COLORS['primary']};
            }}
            QLineEdit::placeholder {{
                color: {MD3_LIGHT_COLORS['on_surface_variant']};
            }}
        """)
        layout.addWidget(self.name_input)

        # 头像选择 - v2.23.1 优化：添加图片上传功能
        avatar_label = QLabel("选择头像")
        avatar_label.setStyleSheet(f"""
            QLabel {{
                color: {MD3_LIGHT_COLORS['on_surface_variant']};
                font-size: 12px;
                background: transparent;
            }}
        """)
        layout.addWidget(avatar_label)

        # 头像选项
        avatar_layout = QHBoxLayout()
        avatar_layout.setSpacing(12)

        self.avatar_buttons = []
        self.custom_avatar_path = None  # v2.23.1 存储自定义头像路径
        avatars = ["👤", "👥", "🐱", "🐶", "🐰", "🦊", "🐼", "🐨"]

        for avatar in avatars:
            btn = QPushButton(avatar)
            btn.setFixedSize(48, 48)
            btn.setCheckable(True)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {MD3_LIGHT_COLORS['surface_container']};
                    border: 2px solid {MD3_LIGHT_COLORS['outline']};
                    border-radius: 24px;
                    font-size: 24px;
                }}
                QPushButton:hover {{
                    background: {MD3_LIGHT_COLORS['surface_container_high']};
                }}
                QPushButton:checked {{
                    background: {MD3_LIGHT_COLORS['primary_container']};
                    border: 2px solid {MD3_LIGHT_COLORS['primary']};
                }}
            """)
            btn.clicked.connect(lambda checked, b=btn: self.on_avatar_selected(b))
            avatar_layout.addWidget(btn)
            self.avatar_buttons.append(btn)

        # v2.23.1 添加上传图片按钮
        upload_btn = QPushButton("📸")
        upload_btn.setFixedSize(48, 48)
        upload_btn.setToolTip("上传自定义头像")
        upload_btn.setStyleSheet(f"""
            QPushButton {{
                background: {MD3_LIGHT_COLORS['tertiary_container']};
                border: 2px solid {MD3_LIGHT_COLORS['outline']};
                border-radius: 24px;
                font-size: 24px;
            }}
            QPushButton:hover {{
                background: {MD3_LIGHT_COLORS['tertiary']};
            }}
        """)
        upload_btn.clicked.connect(self.on_upload_avatar)
        avatar_layout.addWidget(upload_btn)

        layout.addLayout(avatar_layout)

        layout.addStretch()

        # 按钮区域
        button_layout = QHBoxLayout()
        button_layout.setSpacing(12)

        # 取消按钮
        cancel_btn = QPushButton("取消")
        cancel_btn.setFixedHeight(40)
        cancel_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: 1px solid {MD3_LIGHT_COLORS['outline']};
                border-radius: {MD3_RADIUS['full']};
                color: {MD3_LIGHT_COLORS['primary']};
                font-size: 14px;
                font-weight: 500;
                padding: 0px 24px;
            }}
            QPushButton:hover {{
                background: {MD3_LIGHT_COLORS['surface_container_high']};
            }}
        """)
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)

        # 确认按钮
        confirm_btn = QPushButton("添加")
        confirm_btn.setFixedHeight(40)
        confirm_btn.setStyleSheet(f"""
            QPushButton {{
                background: {MD3_LIGHT_COLORS['gradient_mint_cyan']};
                border: none;
                border-radius: {MD3_RADIUS['full']};
                color: {MD3_LIGHT_COLORS['on_primary']};
                font-size: 14px;
                font-weight: 500;
                padding: 0px 24px;
            }}
            QPushButton:hover {{
                background: {MD3_LIGHT_COLORS['primary']};
            }}
        """)
        confirm_btn.clicked.connect(self.on_confirm)
        button_layout.addWidget(confirm_btn)

        layout.addLayout(button_layout)

        # 设置容器布局
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(container)

        # 默认选中第一个头像
        if self.avatar_buttons:
            self.avatar_buttons[0].setChecked(True)

    def on_avatar_selected(self, button):
        """头像选择 - v2.23.1 优化：清除自定义头像"""
        # 取消其他按钮的选中状态
        for btn in self.avatar_buttons:
            if btn != button:
                btn.setChecked(False)

        # 清除自定义头像路径
        self.custom_avatar_path = None

    def on_upload_avatar(self):
        """上传自定义头像 - v2.23.1 新增"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择头像图片",
            "",
            "图片文件 (*.png *.jpg *.jpeg *.gif *.bmp *.webp)"
        )

        if file_path:
            # 保存自定义头像路径
            self.custom_avatar_path = file_path

            # 取消所有emoji按钮的选中状态
            for btn in self.avatar_buttons:
                btn.setChecked(False)

            logger.debug("已选择自定义头像: %s", file_path)

    def on_confirm(self):
        """确认添加 - v2.23.1 优化：支持自定义头像"""
        name = self.name_input.text().strip()
        if not name:
            # 显示错误提示
            self.name_input.setStyleSheet(f"""
                QLineEdit {{
                    background: {MD3_LIGHT_COLORS['surface_container']};
                    border: 2px solid {MD3_LIGHT_COLORS['error']};
                    border-radius: {MD3_RADIUS['small']};
                    color: {MD3_LIGHT_COLORS['on_surface']};
                    font-size: 14px;
                    padding: 12px 16px;
                }}
            """)
            return

        # 获取选中的头像
        avatar = "👤"

        # v2.23.1 优先使用自定义头像
        if self.custom_avatar_path:
            avatar = self.custom_avatar_path
        else:
            # 使用emoji头像
            for btn in self.avatar_buttons:
                if btn.isChecked():
                    avatar = btn.text()
                    break

        self.contact_added.emit(name, avatar)
        self._accepted = True
        self.accept()


class ContactsPanel(QWidget):
    """联系人面板 - 可折叠的联系人列表"""

    contact_selected = pyqtSignal(str)  # 发送联系人名称

    def __init__(self, parent=None):
        super().__init__(parent)

        # 折叠状态
        self._is_expanded = False
        self._current_width = 0
        self._target_width = 300

        # 联系人数据
        self.contacts = []

        # 设置动画
        self.setup_animations()
        self.setup_ui()

        # 初始状态为折叠
        self.setFixedWidth(0)

        # 加载用户的联系人
        self.load_user_contacts()

    def setup_animations(self):
        """设置动画 - 优化性能"""
        # 宽度动画 - 使用 emphasized_decelerate 缓动
        self.width_animation = QPropertyAnimation(self, b"current_width")
        self.width_animation.setDuration(MD3_DURATION["medium2"])  # 300ms，更快响应
        self.width_animation.setEasingCurve(QEasingCurve.Type.OutCubic)

        # 启用硬件加速
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, False)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, False)

    @pyqtProperty(int)
    def current_width(self):
        return self._current_width

    @current_width.setter
    def current_width(self, value):
        self._current_width = value
        self.setFixedWidth(value)

    def setup_ui(self):
        """设置 UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 搜索栏
        search_layout = QHBoxLayout()
        search_layout.setContentsMargins(16, 12, 16, 12)
        search_layout.setSpacing(8)

        # 搜索输入框容器
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
        self.search_input.setPlaceholderText("搜索联系人")
        self.search_input.textChanged.connect(self.filter_contacts)  # 实时搜索
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
                background: {MD3_ENHANCED_COLORS['surface_container_high']};
                border: 2px solid {MD3_ENHANCED_COLORS['outline_variant']};
                border-radius: {MD3_ENHANCED_RADIUS['xl']};
                padding: 8px 0px;
            }}
        """)
        search_layout.addWidget(search_container)

        # 添加按钮
        add_btn = MaterialIconButton("add", "添加联系人", size=36, icon_size=20)
        add_btn.setCheckable(False)
        add_btn.clicked.connect(self.on_add_contact)
        search_layout.addWidget(add_btn)

        layout.addLayout(search_layout)

        # 联系人列表
        self.contact_list = QListWidget()
        self.contact_list.setStyleSheet(f"""
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
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 {MD3_ENHANCED_COLORS['primary_container']},
                    stop:1 {MD3_ENHANCED_COLORS['secondary_container']}
                );
                border-radius: {MD3_ENHANCED_RADIUS['lg']};
            }}
        """)
        layout.addWidget(self.contact_list)

        # 设置背景 - 使用渐变背景，增强视觉效果
        self.setStyleSheet(f"""
            ContactsPanel {{
                background: qlineargradient(
                    x1:0, y1:0, x2:0, y2:1,
                    stop:0 {MD3_ENHANCED_COLORS['surface_bright']},
                    stop:0.5 {MD3_ENHANCED_COLORS['primary_10']},
                    stop:1 {MD3_ENHANCED_COLORS['surface_bright']}
                );
                border-right: 1px solid {MD3_ENHANCED_COLORS['outline_variant']};
            }}
        """)

    def load_user_contacts(self):
        """从数据库加载用户的联系人"""
        # 清空现有联系人
        self.contacts = []
        self.contact_list.clear()

        # 如果用户已登录，加载其联系人
        if user_session.is_logged_in():
            contacts = user_session.get_contacts()
            for contact in contacts:
                self.add_contact(
                    contact['name'],
                    contact.get('avatar', '👤'),
                    contact.get('status', '在线'),
                    save_to_db=False  # 已经在数据库中，不需要再保存
                )
        else:
            # 未登录时添加示例联系人
            self.add_demo_contacts()

    def add_demo_contacts(self):
        """添加示例联系人 - 仅用于未登录状态"""
        demo_contacts = [
            ("🐱", "小雪糕", "在线"),
            ("👥", "数学244班信息群", "在线"),
            ("🐶", "小雨的好朋友们", "在线"),
            ("🦊", "MoeChat (限)", "离线"),
        ]

        for avatar, name, status in demo_contacts:
            self.add_contact(name, avatar, status, save_to_db=False)

    def add_contact(self, name: str, avatar: str = "👤", status: str = "在线", save_to_db: bool = True):
        """添加联系人

        Args:
            name: 联系人名称
            avatar: 头像
            status: 状态
            save_to_db: 是否保存到数据库
        """

        # 检查是否已存在
        for contact in self.contacts:
            if contact["name"] == name:
                return

        # 保存到数据库
        if save_to_db and user_session.is_logged_in():
            success = user_session.add_contact(name, avatar, status)
            if not success:
                # 添加失败（可能已存在）
                return

        # 添加到数据
        self.contacts.append({
            "name": name,
            "avatar": avatar,
            "status": status
        })

        # 添加到列表
        item = QListWidgetItem(self.contact_list)
        item_widget = ContactItem(avatar, name, status)
        item_widget.clicked.connect(self.on_contact_clicked)
        item_widget.rename_requested.connect(self.on_contact_renamed)
        item_widget.delete_requested.connect(self.on_contact_deleted)
        item.setSizeHint(item_widget.sizeHint())
        self.contact_list.addItem(item)
        self.contact_list.setItemWidget(item, item_widget)

    def toggle(self):
        """切换展开/折叠状态"""
        if self._is_expanded:
            self.collapse()
        else:
            self.expand()

    def expand(self):
        """展开"""
        if self._is_expanded:
            return

        self._is_expanded = True
        self.width_animation.setStartValue(self.current_width)
        self.width_animation.setEndValue(self._target_width)
        self.width_animation.start()

    def collapse(self):
        """折叠"""
        if not self._is_expanded:
            return

        self._is_expanded = False
        self.width_animation.setStartValue(self.current_width)
        self.width_animation.setEndValue(0)
        self.width_animation.start()

    def is_expanded(self):
        """是否展开"""
        return self._is_expanded

    def on_add_contact(self):
        """添加联系人按钮点击"""
        dialog = AddContactDialog(self)
        dialog.contact_added.connect(self.add_contact)
        dialog.exec()

    def on_contact_clicked(self, name: str):
        """联系人点击"""
        self.contact_selected.emit(name)

    def filter_contacts(self, text: str):
        """过滤联系人 - 实时搜索"""
        text = text.lower().strip()

        for i in range(self.contact_list.count()):
            item = self.contact_list.item(i)

            if not text:
                # 显示所有联系人
                item.setHidden(False)
            else:
                # 根据名称过滤
                contact_name = self.contacts[i]["name"].lower()
                item.setHidden(text not in contact_name)

    def on_contact_renamed(self, old_name: str, new_name: str):
        """处理联系人重命名 - v2.15.1 新增"""

        # 检查新名称是否已存在
        for contact in self.contacts:
            if contact["name"] == new_name:
                QMessageBox.warning(
                    self,
                    "重命名失败",
                    f"联系人 '{new_name}' 已存在！",
                    QMessageBox.StandardButton.Ok
                )
                return

        # 更新数据库
        if user_session.is_logged_in():
            success = user_session.update_contact(old_name, new_name)
            if not success:
                QMessageBox.warning(
                    self,
                    "重命名失败",
                    "更新数据库失败！",
                    QMessageBox.StandardButton.Ok
                )
                return

        # 更新数据
        for contact in self.contacts:
            if contact["name"] == old_name:
                contact["name"] = new_name
                break

        # 更新UI
        for i in range(self.contact_list.count()):
            item = self.contact_list.item(i)
            widget = self.contact_list.itemWidget(item)
            if isinstance(widget, ContactItem) and widget.contact_name == old_name:
                # 重新创建联系人项
                avatar = widget.avatar
                status = widget.status

                # 移除旧项
                self.contact_list.takeItem(i)

                # 添加新项
                new_item = QListWidgetItem(self.contact_list)
                new_widget = ContactItem(avatar, new_name, status)
                new_widget.clicked.connect(self.on_contact_clicked)
                new_widget.rename_requested.connect(self.on_contact_renamed)
                new_widget.delete_requested.connect(self.on_contact_deleted)
                new_item.setSizeHint(new_widget.sizeHint())
                self.contact_list.insertItem(i, new_item)
                self.contact_list.setItemWidget(new_item, new_widget)
                break

    def on_contact_deleted(self, name: str):
        """处理联系人删除 - v2.15.1 新增"""

        # 从数据库中删除
        if user_session.is_logged_in():
            user_session.delete_contact(name)
            # 同时清除该联系人的聊天历史
            user_session.clear_chat_history(name)

        # 从数据中移除
        self.contacts = [c for c in self.contacts if c["name"] != name]

        # 从UI中移除
        for i in range(self.contact_list.count()):
            item = self.contact_list.item(i)
            widget = self.contact_list.itemWidget(item)
            if isinstance(widget, ContactItem) and widget.contact_name == name:
                self.contact_list.takeItem(i)
                break
