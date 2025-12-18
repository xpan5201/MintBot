"""
认证管理器 - Material Design 3

统一管理登录、注册、找回密码界面的切换

架构设计：
- 左侧：固定插画面板（500px 宽）
- 右侧：动态表单切换（登录/注册/找回密码）
- 动画：平滑的交叉淡入淡出效果（300ms）
- 性能：最小化重绘，优化动画性能

特性：
- 无边框窗口，支持拖动
- 启动动画（缩放 + 淡入）
- 表单切换动画（交叉淡入淡出）
- 自定义插画支持
- 阴影效果
"""

from PyQt6.QtWidgets import (
    QWidget, QStackedWidget, QGraphicsOpacityEffect,
    QVBoxLayout, QHBoxLayout, QPushButton
)
from PyQt6.QtCore import Qt, pyqtSignal, QPropertyAnimation, QParallelAnimationGroup, QPoint, QRect
from PyQt6.QtGui import QColor, QMouseEvent, QCursor

from .auth_window import IllustrationPanel
from .login_form import LoginForm
from .register_form import RegisterForm
from .change_password_form import ChangePasswordForm
from .material_design_enhanced import MD3_ENHANCED_DURATION, MD3_ENHANCED_EASING, MD3_ENHANCED_COLORS
from .theme_manager import is_anime_theme

from src.utils.logger import get_logger

logger = get_logger(__name__)


class AuthManager(QWidget):
    """认证管理器 - 统一管理认证界面

    负责管理登录、注册、找回密码三个表单的切换，
    提供统一的插画面板和平滑的切换动画。
    """

    # 信号定义
    login_success = pyqtSignal(object)  # 登录成功信号，传递用户信息字典

    def __init__(self, illustration_path: str = None, parent=None):
        """初始化认证管理器

        Args:
            illustration_path: 自定义插画路径（可选）
            parent: 父窗口（可选）
        """
        super().__init__(parent)

        # 窗口属性设置
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |  # 无边框
            Qt.WindowType.WindowStaysOnTopHint   # 置顶显示
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)  # 透明背景

        # 插画配置
        self.illustration_path = illustration_path

        # 窗口拖动状态
        self._is_dragging = False
        self._drag_start_position = QPoint()

        # 构建用户界面
        self.setup_ui()

        # 设置窗口尺寸（1100x600 符合 MD3 规范）
        self.resize(1100, 600)

        # 窗口居中显示
        self.center_on_screen()

        # 启动入场动画
        self._setup_startup_animation()

    def setup_ui(self):
        """构建用户界面

        布局结构：
        ┌─────────────────────────────────────┐
        │  ┌──────────┬──────────────────┐   │
        │  │          │  [关闭按钮]       │   │
        │  │  插画    │                  │   │
        │  │  面板    │  表单切换区域     │   │
        │  │  500px   │  (登录/注册/找回) │   │
        │  │          │                  │   │
        │  └──────────┴──────────────────┘   │
        └─────────────────────────────────────┘
        """
        # ========== 主布局 ==========
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)  # 为阴影留出空间
        main_layout.setSpacing(0)

        # ========== 主容器 ==========
        self.container = QWidget()
        container_background = MD3_ENHANCED_COLORS["surface_bright"]
        if is_anime_theme():
            container_background = MD3_ENHANCED_COLORS.get("gradient_surface", container_background)
        self.container.setStyleSheet(f"""
            QWidget {{
                background: {container_background};
                border-radius: 16px;
            }}
        """)

        # 容器布局：水平分割（左侧插画 + 右侧内容）
        container_layout = QHBoxLayout(self.container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)

        # ========== 左侧：插画面板 ==========
        self.illustration_panel = IllustrationPanel(self.illustration_path)
        self.illustration_panel.setFixedWidth(500)  # 固定宽度
        container_layout.addWidget(self.illustration_panel)

        # ========== 右侧：内容区域 ==========
        right_content = QWidget()
        right_content.setStyleSheet("background: transparent;")
        right_layout = QVBoxLayout(right_content)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        # --- 顶部栏：关闭按钮 ---
        top_bar = QWidget()
        top_bar.setStyleSheet("background: transparent;")
        top_bar_layout = QHBoxLayout(top_bar)
        top_bar_layout.setContentsMargins(0, 8, 8, 0)
        top_bar_layout.addStretch()

        # 关闭按钮
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(32, 32)
        close_btn.clicked.connect(self.close)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {MD3_ENHANCED_COLORS['on_surface_variant']};
                border: none;
                border-radius: 16px;
                font-size: 20px;
            }}
            QPushButton:hover {{
                background: {MD3_ENHANCED_COLORS['error_container']};
                color: {MD3_ENHANCED_COLORS['on_error_container']};
            }}
        """)
        top_bar_layout.addWidget(close_btn)
        right_layout.addWidget(top_bar)

        # --- 表单堆叠：登录/注册/找回密码 ---
        self.form_stack = QStackedWidget()
        self.form_stack.setStyleSheet("background: transparent;")

        # 登录表单
        self.login_form = LoginForm()
        self.login_form.login_success.connect(self.on_login_success)
        self.login_form.switch_to_register.connect(self.show_register)
        self.login_form.switch_to_reset_password.connect(self.show_change_password)
        self.form_stack.addWidget(self.login_form)

        # 注册表单
        self.register_form = RegisterForm()
        self.register_form.switch_to_login.connect(self.show_login)
        self.register_form.register_success.connect(self.on_register_success)
        self.form_stack.addWidget(self.register_form)

        # 找回密码表单
        self.change_password_form = ChangePasswordForm()
        self.change_password_form.switch_to_login.connect(self.show_login)
        self.change_password_form.password_changed.connect(self.on_password_changed)
        self.form_stack.addWidget(self.change_password_form)

        # 将表单堆叠添加到右侧布局
        right_layout.addWidget(self.form_stack)

        # ========== 组装布局 ==========
        container_layout.addWidget(right_content)
        main_layout.addWidget(self.container)

        # 默认显示登录表单
        self.form_stack.setCurrentWidget(self.login_form)

        # 添加阴影效果
        from PyQt6.QtWidgets import QGraphicsDropShadowEffect
        shadow = QGraphicsDropShadowEffect(self.container)
        shadow.setBlurRadius(30)
        shadow.setXOffset(0)
        shadow.setYOffset(8)
        shadow.setColor(QColor(0, 0, 0, 60))
        self.container.setGraphicsEffect(shadow)

    def center_on_screen(self):
        """窗口居中显示"""
        try:
            from PyQt6.QtWidgets import QApplication
            screen = QApplication.primaryScreen().geometry()
            x = (screen.width() - self.width()) // 2
            y = (screen.height() - self.height()) // 2
            self.move(x, y)
        except Exception as e:
            logger.error(f"窗口居中失败: {e}")

    def _setup_startup_animation(self):
        """设置启动动画 - 缩放 + 淡入 + 轻微弹性

        使用 Material Design 3 的强调减速曲线，
        创建更流畅、更有活力的启动效果。

        动画效果：
        - 从 92% 缩放到 100%（更明显的缩放效果）
        - 透明度从 0 到 1
        - 持续时间 500ms（更流畅）
        """
        try:
            # 淡入效果
            self.opacity_effect = QGraphicsOpacityEffect(self)
            self.setGraphicsEffect(self.opacity_effect)

            self.fade_animation = QPropertyAnimation(self.opacity_effect, b"opacity")
            self.fade_animation.setDuration(MD3_ENHANCED_DURATION["long1"])  # 450ms
            self.fade_animation.setStartValue(0.0)
            self.fade_animation.setEndValue(1.0)
            self.fade_animation.setEasingCurve(MD3_ENHANCED_EASING["emphasized_decelerate"])

            # 缩放效果
            original_geometry = self.geometry()
            center = original_geometry.center()

            # 从 92% 缩放到 100%（更明显的效果）
            start_width = int(original_geometry.width() * 0.92)
            start_height = int(original_geometry.height() * 0.92)
            start_geometry = QRect(0, 0, start_width, start_height)
            start_geometry.moveCenter(center)

            self.setGeometry(start_geometry)

            self.scale_animation = QPropertyAnimation(self, b"geometry")
            self.scale_animation.setDuration(MD3_ENHANCED_DURATION["long1"])  # 450ms
            self.scale_animation.setStartValue(start_geometry)
            self.scale_animation.setEndValue(original_geometry)
            self.scale_animation.setEasingCurve(MD3_ENHANCED_EASING["emphasized_decelerate"])

            # 并行动画组
            self.startup_animation_group = QParallelAnimationGroup(self)
            self.startup_animation_group.addAnimation(self.fade_animation)
            self.startup_animation_group.addAnimation(self.scale_animation)

            # 动画完成后移除效果
            def on_finished():
                self.setGraphicsEffect(None)

            self.startup_animation_group.finished.connect(on_finished)
            self.startup_animation_group.start()
        except Exception as e:
            logger.error(f"启动动画设置失败: {e}")

    def show_login(self):
        """显示登录表单"""
        self.switch_form(self.login_form)

    def show_register(self):
        """显示注册表单"""
        self.switch_form(self.register_form)

    def show_change_password(self):
        """显示修改密码表单"""
        self.switch_form(self.change_password_form)

    def switch_form(self, target_form: QWidget):
        """切换表单 - 交叉淡入淡出动画（优化版）

        使用交叉淡入淡出效果实现平滑的表单切换，
        符合 Material Design 3 动画规范（400ms，强调减速曲线）。

        动画效果：
        - 当前表单：淡出（强调加速）
        - 目标表单：淡入（强调减速）

        Args:
            target_form: 目标表单组件
        """
        # 如果已经是当前表单，直接返回
        if self.form_stack.currentWidget() == target_form:
            return

        current_form = self.form_stack.currentWidget()

        # 立即切换到目标表单
        self.form_stack.setCurrentWidget(target_form)

        # ========== 当前表单：淡出 ==========
        self._fade_out_effect = QGraphicsOpacityEffect(current_form)
        current_form.setGraphicsEffect(self._fade_out_effect)

        self._fade_out_animation = QPropertyAnimation(self._fade_out_effect, b"opacity")
        self._fade_out_animation.setDuration(MD3_ENHANCED_DURATION["medium4"])  # 400ms
        self._fade_out_animation.setStartValue(1.0)
        self._fade_out_animation.setEndValue(0.0)
        self._fade_out_animation.setEasingCurve(MD3_ENHANCED_EASING["emphasized_accelerate"])

        # ========== 目标表单：淡入 ==========
        self._fade_in_effect = QGraphicsOpacityEffect(target_form)
        target_form.setGraphicsEffect(self._fade_in_effect)

        self._fade_in_animation = QPropertyAnimation(self._fade_in_effect, b"opacity")
        self._fade_in_animation.setDuration(MD3_ENHANCED_DURATION["medium4"])  # 400ms
        self._fade_in_animation.setStartValue(0.0)
        self._fade_in_animation.setEndValue(1.0)
        self._fade_in_animation.setEasingCurve(MD3_ENHANCED_EASING["emphasized_decelerate"])

        # 动画完成后清理效果（性能优化：移除不再需要的图形效果）
        def on_animation_finished():
            target_form.setGraphicsEffect(None)
            current_form.setGraphicsEffect(None)

        self._fade_in_animation.finished.connect(on_animation_finished)

        # 同时启动淡出和淡入动画（交叉动画，平滑过渡）
        self._fade_out_animation.start()
        self._fade_in_animation.start()

    def on_login_success(self, user: dict):
        """登录成功处理

        Args:
            user: 用户信息
        """
        try:
            # 发送登录成功信号
            self.login_success.emit(user)

            # 延迟关闭认证管理器，确保主窗口已完全创建和显示
            # 增加延迟时间到500ms，确保主窗口完全显示
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(500, self.close)
        except Exception as e:
            from src.utils.exceptions import handle_exception
            handle_exception(e, logger, "登录成功处理失败")

    def on_register_success(self):
        """注册成功处理"""
        try:
            # 注册成功后，RegisterWindow 会自动切换到登录窗口
            # 这里不需要额外处理
            pass
        except Exception as e:
            logger.info("on_register_success error: %s", e)

    def on_password_changed(self):
        """密码修改成功处理"""
        try:
            # 密码修改成功后，ChangePasswordWindow 会自动切换到登录窗口
            # 这里不需要额外处理
            pass
        except Exception as e:
            logger.info("on_password_changed error: %s", e)

    def set_illustration(self, image_path: str):
        """设置插画图片（优化：只需设置一次）

        Args:
            image_path: 图片路径
        """
        try:
            self.illustration_path = image_path
            self.illustration_panel.set_image(image_path)
        except Exception as e:
            logger.info("set_illustration error: %s", e)

    def mousePressEvent(self, event: QMouseEvent):
        """鼠标按下事件 - 开始拖动窗口"""
        try:
            if event.button() == Qt.MouseButton.LeftButton:
                # 检查是否点击在可拖动区域（避免点击输入框等控件时拖动）
                pos = event.position().toPoint() if hasattr(event, 'position') else event.pos()
                widget_under_mouse = self.childAt(pos)

                # 如果点击的是输入框、按钮等交互控件，不启动拖动
                from PyQt6.QtWidgets import QLineEdit, QCheckBox
                if widget_under_mouse and isinstance(widget_under_mouse, (QLineEdit, QPushButton, QCheckBox)):
                    event.ignore()
                    return

                # 启动拖动
                self._is_dragging = True
                # 记录鼠标相对于窗口的位置
                global_pos = event.globalPosition().toPoint() if hasattr(event, 'globalPosition') else event.globalPos()
                self._drag_start_position = global_pos - self.frameGeometry().topLeft()

                # 设置鼠标样式
                self.setCursor(QCursor(Qt.CursorShape.ClosedHandCursor))
                event.accept()
        except Exception as e:
            logger.info("mousePressEvent error: %s", e)
            event.ignore()

    def mouseMoveEvent(self, event: QMouseEvent):
        """鼠标移动事件 - 拖动窗口"""
        try:
            if self._is_dragging and event.buttons() == Qt.MouseButton.LeftButton:
                # 拖动窗口
                global_pos = event.globalPosition().toPoint() if hasattr(event, 'globalPosition') else event.globalPos()
                self.move(global_pos - self._drag_start_position)
                event.accept()
            else:
                event.ignore()
        except Exception as e:
            logger.info("mouseMoveEvent error: %s", e)
            event.ignore()

    def mouseReleaseEvent(self, event: QMouseEvent):
        """鼠标释放事件 - 停止拖动"""
        try:
            if event.button() == Qt.MouseButton.LeftButton:
                self._is_dragging = False
                self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))
                event.accept()
        except Exception as e:
            logger.info("mouseReleaseEvent error: %s", e)
            event.ignore()
