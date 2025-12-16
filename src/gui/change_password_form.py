"""
修改密码表单 - Material Design 3

纯表单组件，不包含插画面板
"""

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel
from PyQt6.QtCore import Qt, pyqtSignal

from typing import TYPE_CHECKING, Optional

from .auth_window import MD3TextField, MD3Button, MD3TextButton
from .material_design_enhanced import MD3_ENHANCED_COLORS
from .notifications import show_toast, Toast
from src.utils.logger import get_logger

logger = get_logger(__name__)

if TYPE_CHECKING:
    from src.auth.auth_service import AuthService


class ChangePasswordForm(QWidget):
    """修改密码表单组件"""

    # 信号
    switch_to_login = pyqtSignal()  # 切换到登录
    password_changed = pyqtSignal()  # 密码修改成功

    def __init__(self, parent=None):
        super().__init__(parent)
        self._auth_service: Optional["AuthService"] = None
        self.setup_ui()

    def _get_auth_service(self) -> "AuthService":
        if self._auth_service is None:
            from src.auth.auth_service import AuthService

            self._auth_service = AuthService()
        return self._auth_service

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
        title_label = QLabel("找回密码")
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
        subtitle_label = QLabel("请输入您的用户名、邮箱和新密码")
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

        self.username_input = MD3TextField("请输入用户名")
        self.username_input.setFocus()
        layout.addWidget(self.username_input)

        layout.addSpacing(20)

        # 邮箱输入框
        email_label = QLabel("邮箱")
        email_label.setStyleSheet(f"""
            QLabel {{
                color: {MD3_ENHANCED_COLORS['on_surface']};
                font-size: 14px;
                font-weight: 600;
                margin-bottom: 8px;
            }}
        """)
        layout.addWidget(email_label)

        self.email_input = MD3TextField("请输入注册邮箱")
        layout.addWidget(self.email_input)

        layout.addSpacing(20)

        # 新密码输入框
        new_password_label = QLabel("新密码")
        new_password_label.setStyleSheet(f"""
            QLabel {{
                color: {MD3_ENHANCED_COLORS['on_surface']};
                font-size: 14px;
                font-weight: 600;
                margin-bottom: 8px;
            }}
        """)
        layout.addWidget(new_password_label)

        self.new_password_input = MD3TextField("至少6个字符，包含字母和数字", is_password=True)
        layout.addWidget(self.new_password_input)

        layout.addSpacing(20)

        # 确认新密码输入框
        confirm_password_label = QLabel("确认新密码")
        confirm_password_label.setStyleSheet(f"""
            QLabel {{
                color: {MD3_ENHANCED_COLORS['on_surface']};
                font-size: 14px;
                font-weight: 600;
                margin-bottom: 8px;
            }}
        """)
        layout.addWidget(confirm_password_label)

        self.confirm_password_input = MD3TextField("请再次输入新密码", is_password=True)
        self.confirm_password_input.returnPressed.connect(self.on_change_password_clicked)
        layout.addWidget(self.confirm_password_input)

        layout.addSpacing(24)

        # 修改密码按钮
        self.change_password_btn = MD3Button("修改密码", is_primary=True)
        self.change_password_btn.setMinimumHeight(56)
        self.change_password_btn.clicked.connect(self.on_change_password_clicked)
        layout.addWidget(self.change_password_btn)

        layout.addSpacing(16)

        # 返回登录提示
        login_layout = QHBoxLayout()
        login_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        login_hint = QLabel("记起密码了？")
        login_hint.setStyleSheet(f"""
            QLabel {{
                color: {MD3_ENHANCED_COLORS['on_surface_variant']};
                font-size: 14px;
            }}
        """)
        login_layout.addWidget(login_hint)

        login_btn = MD3TextButton("返回登录")
        login_btn.clicked.connect(self.on_login_clicked)
        login_layout.addWidget(login_btn)

        layout.addLayout(login_layout)

        layout.addStretch()

    def on_change_password_clicked(self):
        """修改密码按钮点击"""
        try:
            username = self.username_input.text().strip()
            email = self.email_input.text().strip()
            new_password = self.new_password_input.text().strip()
            confirm_password = self.confirm_password_input.text().strip()

            # 表单验证
            if not username:
                self.username_input.set_error(True, "请输入用户名")
                return

            if not email:
                self.email_input.set_error(True, "请输入邮箱")
                return

            if not new_password:
                self.new_password_input.set_error(True, "请输入新密码")
                return

            if not confirm_password:
                self.confirm_password_input.set_error(True, "请确认新密码")
                return

            # 验证密码一致性
            if new_password != confirm_password:
                self.confirm_password_input.set_error(True, "两次输入的密码不一致")
                return

            # 设置加载状态
            self.change_password_btn.set_loading(True)

            # 执行密码重置
            auth_service = self._get_auth_service()
            success, message = auth_service.reset_password(username, email, new_password, confirm_password)

            # 恢复按钮状态
            self.change_password_btn.set_loading(False)

            if success:
                # 修改成功
                # 在顶层窗口显示 Toast
                top_window = self.window()
                show_toast(top_window, "密码修改成功！请使用新密码登录", Toast.TYPE_SUCCESS, duration=3000)
                self.password_changed.emit()
                # 切换到登录界面
                self.switch_to_login.emit()
            else:
                # 修改失败
                # 在顶层窗口显示 Toast
                top_window = self.window()
                show_toast(top_window, message, Toast.TYPE_ERROR, duration=3000)
                # 根据错误消息设置错误状态
                if "用户名" in message or "不存在" in message:
                    self.username_input.set_error(True, message)
                elif "邮箱" in message:
                    self.email_input.set_error(True, message)
                elif "密码" in message:
                    self.new_password_input.set_error(True, message)
        except Exception as e:
            logger.error(f"修改密码失败: {e}")
            self.change_password_btn.set_loading(False)
            # 在顶层窗口显示 Toast
            top_window = self.window()
            show_toast(top_window, "修改密码时发生错误，请重试", Toast.TYPE_ERROR, duration=3000)

    def on_login_clicked(self):
        """返回登录按钮点击"""
        try:
            self.switch_to_login.emit()
        except Exception as e:
            logger.error(f"返回登录失败: {e}")
