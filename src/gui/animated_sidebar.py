"""
MintChat GUI - 动画侧边栏组件

提供可折叠的侧边栏，带有平滑的展开/收起动画
遵循 Material Design 3 规范
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QListWidget, QListWidgetItem, QFrame
)
from PyQt6.QtCore import (
    Qt, QPropertyAnimation, QEasingCurve, QSize,
    pyqtSignal, QParallelAnimationGroup
)

from .material_design import (
    MD3_COLORS, MD3_RADIUS, MD3_DURATION,
    get_typography_style
)


class AnimatedSidebar(QWidget):
    """带动画效果的侧边栏"""

    # 信号
    session_selected = pyqtSignal(int)  # 会话选中
    new_session_clicked = pyqtSignal()  # 新建会话

    def __init__(self, parent=None):
        super().__init__(parent)
        self.is_expanded = True
        self.expanded_width = 280
        self.collapsed_width = 64

        self._init_ui()
        self._apply_styles()
        self._setup_animations()

    def _init_ui(self):
        """初始化 UI"""
        # 主布局
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 顶部区域
        top_widget = QWidget()
        top_widget.setObjectName("topWidget")
        top_layout = QHBoxLayout(top_widget)
        top_layout.setContentsMargins(16, 16, 16, 16)
        top_layout.setSpacing(12)

        # Logo/标题
        self.logo_label = QLabel("🐱")
        self.logo_label.setObjectName("logoLabel")
        self.logo_label.setFixedSize(32, 32)
        self.logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        top_layout.addWidget(self.logo_label)

        self.title_label = QLabel("MintChat")
        self.title_label.setObjectName("titleLabel")
        top_layout.addWidget(self.title_label)

        top_layout.addStretch()

        # 折叠/展开按钮
        self.toggle_button = QPushButton("☰")
        self.toggle_button.setObjectName("toggleButton")
        self.toggle_button.setFixedSize(32, 32)
        self.toggle_button.clicked.connect(self.toggle)
        top_layout.addWidget(self.toggle_button)

        main_layout.addWidget(top_widget)

        # 分隔线
        separator1 = QFrame()
        separator1.setFrameShape(QFrame.Shape.HLine)
        separator1.setObjectName("separator")
        main_layout.addWidget(separator1)

        # 新建会话按钮
        new_session_widget = QWidget()
        new_session_layout = QHBoxLayout(new_session_widget)
        new_session_layout.setContentsMargins(16, 12, 16, 12)
        new_session_layout.setSpacing(12)

        self.new_session_button = QPushButton("➕ 新建会话")
        self.new_session_button.setObjectName("newSessionButton")
        self.new_session_button.clicked.connect(self.new_session_clicked.emit)
        new_session_layout.addWidget(self.new_session_button)

        main_layout.addWidget(new_session_widget)

        # 分隔线
        separator2 = QFrame()
        separator2.setFrameShape(QFrame.Shape.HLine)
        separator2.setObjectName("separator")
        main_layout.addWidget(separator2)

        # 会话列表
        self.session_list = QListWidget()
        self.session_list.setObjectName("sessionList")
        self.session_list.currentRowChanged.connect(self.session_selected.emit)
        main_layout.addWidget(self.session_list)

        # 添加示例会话
        self._add_sample_sessions()

        # 设置初始宽度
        self.setFixedWidth(self.expanded_width)

    def _add_sample_sessions(self):
        """添加示例会话"""
        sessions = [
            "💬 当前会话",
            "📝 工作讨论",
            "🎨 创意灵感",
            "📚 学习笔记",
        ]

        for session in sessions:
            item = QListWidgetItem(session)
            item.setSizeHint(QSize(0, 48))
            self.session_list.addItem(item)

        # 选中第一个
        self.session_list.setCurrentRow(0)

    def _apply_styles(self):
        """应用样式"""
        self.setStyleSheet(f"""
            AnimatedSidebar {{
                background-color: {MD3_COLORS['surface_container']};
                border-right: 1px solid {MD3_COLORS['outline_variant']};
            }}

            #topWidget {{
                background-color: transparent;
            }}

            #logoLabel {{
                font-size: 24px;
                background-color: {MD3_COLORS['primary_container']};
                border-radius: {MD3_RADIUS['medium']};
            }}

            #titleLabel {{
                color: {MD3_COLORS['on_surface']};
                {get_typography_style('title_large')}
            }}

            #toggleButton {{
                background-color: transparent;
                color: {MD3_COLORS['on_surface']};
                border: none;
                border-radius: {MD3_RADIUS['small']};
                font-size: 18px;
            }}

            #toggleButton:hover {{
                background-color: {MD3_COLORS['surface_container_highest']};
            }}

            #separator {{
                background-color: {MD3_COLORS['outline_variant']};
                border: none;
                max-height: 1px;
            }}

            #newSessionButton {{
                background-color: {MD3_COLORS['primary_container']};
                color: {MD3_COLORS['on_primary_container']};
                border: none;
                border-radius: {MD3_RADIUS['medium']};
                padding: 12px 16px;
                {get_typography_style('label_large')}
                text-align: left;
            }}

            #newSessionButton:hover {{
                background-color: {MD3_COLORS['primary']};
                color: {MD3_COLORS['on_primary']};
            }}

            #sessionList {{
                background-color: transparent;
                border: none;
                outline: none;
                padding: 8px;
            }}

            #sessionList::item {{
                background-color: transparent;
                color: {MD3_COLORS['on_surface']};
                border-radius: {MD3_RADIUS['medium']};
                padding: 12px 16px;
                {get_typography_style('body_large')}
            }}

            #sessionList::item:hover {{
                background-color: {MD3_COLORS['surface_container_highest']};
            }}

            #sessionList::item:selected {{
                background-color: {MD3_COLORS['secondary_container']};
                color: {MD3_COLORS['on_secondary_container']};
            }}
        """)

    def _setup_animations(self):
        """设置动画"""
        # 宽度动画
        self.width_animation = QPropertyAnimation(self, b"maximumWidth")
        self.width_animation.setDuration(MD3_DURATION['medium3'])
        self.width_animation.setEasingCurve(QEasingCurve.Type.InOutCubic)

        # 最小宽度动画
        self.min_width_animation = QPropertyAnimation(self, b"minimumWidth")
        self.min_width_animation.setDuration(MD3_DURATION['medium3'])
        self.min_width_animation.setEasingCurve(QEasingCurve.Type.InOutCubic)

        # 组合动画
        self.animation_group = QParallelAnimationGroup()
        self.animation_group.addAnimation(self.width_animation)
        self.animation_group.addAnimation(self.min_width_animation)

    def toggle(self):
        """切换展开/收起状态"""
        if self.is_expanded:
            self.collapse()
        else:
            self.expand()

    def expand(self):
        """展开侧边栏"""
        if self.is_expanded:
            return

        self.is_expanded = True

        # 设置动画
        self.width_animation.setStartValue(self.collapsed_width)
        self.width_animation.setEndValue(self.expanded_width)
        self.min_width_animation.setStartValue(self.collapsed_width)
        self.min_width_animation.setEndValue(self.expanded_width)

        # 启动动画
        self.animation_group.start()

        # 显示文字
        self.title_label.show()
        self.new_session_button.setText("➕ 新建会话")

    def collapse(self):
        """收起侧边栏"""
        if not self.is_expanded:
            return

        self.is_expanded = False

        # 设置动画
        self.width_animation.setStartValue(self.expanded_width)
        self.width_animation.setEndValue(self.collapsed_width)
        self.min_width_animation.setStartValue(self.expanded_width)
        self.min_width_animation.setEndValue(self.collapsed_width)

        # 启动动画
        self.animation_group.start()

        # 隐藏文字
        self.title_label.hide()
        self.new_session_button.setText("➕")

    def add_session(self, name: str):
        """添加会话"""
        item = QListWidgetItem(name)
        item.setSizeHint(QSize(0, 48))
        self.session_list.addItem(item)

    def remove_session(self, index: int):
        """删除会话"""
        self.session_list.takeItem(index)

    def clear_sessions(self):
        """清空会话列表"""
        self.session_list.clear()
