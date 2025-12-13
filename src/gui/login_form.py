"""
登录表单 - Material Design 3

纯表单组件，不包含插画面板
"""

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QCheckBox
from PyQt6.QtCore import Qt, pyqtSignal

from .auth_window import MD3TextField, MD3Button, MD3TextButton
from .material_design_enhanced import MD3_ENHANCED_COLORS
from .notifications import show_toast, Toast


class LoginForm(QWidget):
    """登录表单组件"""

    # 信号
    login_success = pyqtSignal(object)  # 登录成功，传递用户信息
    switch_to_register = pyqtSignal()  # 切换到注册
    switch_to_reset_password = pyqtSignal()  # 切换到重置密码

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()

    def setup_ui(self):
        """设置 UI - 优化布局和间距"""
        # 设置背景样式
        self.setStyleSheet(f"""
            QWidget {{
                background: {MD3_ENHANCED_COLORS['surface_bright']};
                border-top-right-radius: 16px;
                border-bottom-right-radius: 16px;
            }}
        """)

        # 主布局 - 优化边距和间距
        layout = QVBoxLayout(self)
        layout.setContentsMargins(56, 48, 56, 48)
        layout.setSpacing(0)

        # 标题区域
        title_label = QLabel("登录")
        title_label.setStyleSheet(f"""
            QLabel {{
                color: {MD3_ENHANCED_COLORS['on_surface']};
                font-size: 36px;
                font-weight: 700;
                letter-spacing: 0.5px;
                margin-bottom: 8px;
            }}
        """)
        layout.addWidget(title_label)

        # 副标题
        subtitle_label = QLabel("欢迎回来！请登录您的账户")
        subtitle_label.setStyleSheet(f"""
            QLabel {{
                color: {MD3_ENHANCED_COLORS['on_surface_variant']};
                font-size: 15px;
                line-height: 1.6;
            }}
        """)
        layout.addWidget(subtitle_label)

        layout.addSpacing(32)

        # 用户名输入框
        username_label = QLabel("用户名")
        username_label.setStyleSheet(f"""
            QLabel {{
                color: {MD3_ENHANCED_COLORS['on_surface']};
                font-size: 14px;
                font-weight: 600;
                margin-bottom: 8px;
            }}
        """)
        layout.addWidget(username_label)

        self.username_input = MD3TextField("请输入用户名或邮箱")
        self.username_input.setFocus()
        layout.addWidget(self.username_input)

        layout.addSpacing(20)

        # 密码输入框
        password_label = QLabel("密码")
        password_label.setStyleSheet(f"""
            QLabel {{
                color: {MD3_ENHANCED_COLORS['on_surface']};
                font-size: 14px;
                font-weight: 600;
                margin-bottom: 8px;
            }}
        """)
        layout.addWidget(password_label)

        self.password_input = MD3TextField("请输入密码", is_password=True)
        self.password_input.returnPressed.connect(self.on_login_clicked)
        layout.addWidget(self.password_input)

        layout.addSpacing(16)

        # 记住我 & 忘记密码
        options_layout = QHBoxLayout()
        options_layout.setSpacing(0)

        self.remember_checkbox = QCheckBox("记住我")
        self.remember_checkbox.setCursor(Qt.CursorShape.PointingHandCursor)
        self.remember_checkbox.setStyleSheet(f"""
            QCheckBox {{
                color: {MD3_ENHANCED_COLORS['on_surface_variant']};
                font-size: 14px;
                spacing: 8px;
            }}
            QCheckBox::indicator {{
                width: 20px;
                height: 20px;
                border-radius: 6px;
                border: 2px solid {MD3_ENHANCED_COLORS['outline']};
                background: {MD3_ENHANCED_COLORS['surface_container_highest']};
            }}
            QCheckBox::indicator:hover {{
                border: 2px solid {MD3_ENHANCED_COLORS['primary']};
                background: rgba(38, 166, 154, 0.08);
            }}
            QCheckBox::indicator:checked {{
                background: {MD3_ENHANCED_COLORS['primary']};
                border: 2px solid {MD3_ENHANCED_COLORS['primary']};
                image: url(data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMTYiIGhlaWdodD0iMTYiIHZpZXdCb3g9IjAgMCAxNiAxNiIgZmlsbD0ibm9uZSIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj4KPHBhdGggZD0iTTEzLjMzMzMgNC42NjY2N0w2IDEyTDIuNjY2NjcgOC42NjY2NyIgc3Ryb2tlPSJ3aGl0ZSIgc3Ryb2tlLXdpZHRoPSIyIiBzdHJva2UtbGluZWNhcD0icm91bmQiIHN0cm9rZS1saW5lam9pbj0icm91bmQiLz4KPC9zdmc+);
            }}
        """)
        options_layout.addWidget(self.remember_checkbox)

        options_layout.addStretch()

        forgot_password_btn = MD3TextButton("忘记密码？")
        forgot_password_btn.clicked.connect(self.on_forgot_password_clicked)
        options_layout.addWidget(forgot_password_btn)

        layout.addLayout(options_layout)

        layout.addSpacing(24)

        # 登录按钮
        self.login_btn = MD3Button("登录", is_primary=True)
        self.login_btn.setMinimumHeight(56)
        self.login_btn.clicked.connect(self.on_login_clicked)
        layout.addWidget(self.login_btn)

        layout.addSpacing(16)

        # 注册提示
        register_layout = QHBoxLayout()
        register_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        register_hint = QLabel("还没有账户？")
        register_hint.setStyleSheet(f"""
            QLabel {{
                color: {MD3_ENHANCED_COLORS['on_surface_variant']};
                font-size: 14px;
            }}
        """)
        register_layout.addWidget(register_hint)

        register_btn = MD3TextButton("立即注册")
        register_btn.clicked.connect(self.on_register_clicked)
        register_layout.addWidget(register_btn)

        layout.addLayout(register_layout)

        layout.addStretch()

        # 键盘导航
        self.username_input.setTabOrder(self.username_input, self.password_input)

    def on_login_clicked(self):
        """登录按钮点击"""
        try:
            username = self.username_input.text().strip()
            password = self.password_input.text().strip()

            # 表单验证
            if not username:
                self.username_input.set_error(True, "请输入用户名或邮箱")
                return

            if not password:
                self.password_input.set_error(True, "请输入密码")
                return

            # 设置加载状态
            self.login_btn.set_loading(True)

            # 执行登录
            from src.auth.auth_service import AuthService
            auth_service = AuthService()
            remember_me = self.remember_checkbox.isChecked()
            success, message = auth_service.login(username, password, remember_me)

            # 恢复按钮状态
            self.login_btn.set_loading(False)

            if success:
                # 登录成功，获取用户信息和会话令牌
                user = auth_service.get_current_user()
                session_token = auth_service.current_session

                if user and session_token:
                    # 将会话令牌添加到用户信息中
                    user['session_token'] = session_token
                    user['remember_me'] = remember_me

                    # 在顶层窗口显示 Toast
                    top_window = self.window()
                    show_toast(top_window, f"欢迎回来，{user['username']}！", Toast.TYPE_SUCCESS, duration=3000)
                    self.login_success.emit(user)
                else:
                    # 用户信息或会话令牌获取失败
                    top_window = self.window()
                    show_toast(top_window, "登录成功，但获取用户信息失败", Toast.TYPE_WARNING, duration=3000)
            else:
                # 登录失败
                # 在顶层窗口显示 Toast
                top_window = self.window()
                show_toast(top_window, message, Toast.TYPE_ERROR, duration=3000)
                # 根据错误消息设置错误状态
                if "用户名" in message or "不存在" in message or "错误" in message:
                    self.username_input.set_error(True, message)
                elif "密码" in message:
                    self.password_input.set_error(True, message)
        except Exception as e:
            from src.utils.exceptions import handle_exception
            from src.utils.logger import get_logger
            logger = get_logger(__name__)
            handle_exception(e, logger, "登录时发生错误")
            self.login_btn.set_loading(False)
            # 在顶层窗口显示 Toast
            top_window = self.window()
            show_toast(top_window, "登录时发生错误，请重试", Toast.TYPE_ERROR, duration=3000)

    def on_register_clicked(self):
        """注册按钮点击"""
        try:
            self.switch_to_register.emit()
        except Exception as e:
            logger.error(f"切换到注册页面失败: {e}")

    def on_forgot_password_clicked(self):
        """忘记密码按钮点击"""
        try:
            self.switch_to_reset_password.emit()
        except Exception as e:
            logger.error(f"切换到重置密码页面失败: {e}")
