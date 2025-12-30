"""
用户认证窗口 - Material Design 3

提供登录、注册、修改密码界面
左侧显示插画，右侧显示表单
"""

from PyQt6.QtWidgets import (
    QWidget,
    QLabel,
    QLineEdit,
    QPushButton,
    QGraphicsDropShadowEffect,
    QGraphicsOpacityEffect,
)
from PyQt6.QtCore import Qt, pyqtSignal, QPropertyAnimation
from PyQt6.QtGui import QColor, QPixmap

from .material_design_enhanced import (
    MD3_ENHANCED_COLORS,
    MD3_ENHANCED_RADIUS,
    MD3_ENHANCED_DURATION,
    MD3_ENHANCED_EASING,
)
from .qss_utils import qss_rgba
from ..auth import AuthService
from src.utils.logger import get_logger

logger = get_logger(__name__)


class MD3TextField(QLineEdit):
    """Material Design 3 文本输入框 - 增强版

    特性：
    - 聚焦动画（边框颜色渐变）
    - 悬停状态反馈
    - 错误状态支持
    - 平滑的状态转换动画
    """

    def __init__(
        self, placeholder: str = "", is_password: bool = False, max_length: int = None, parent=None
    ):
        super().__init__(parent)
        self.setPlaceholderText(placeholder)
        self._is_password = is_password
        self._has_error = False
        self._is_focused = False

        if is_password:
            self.setEchoMode(QLineEdit.EchoMode.Password)

        if max_length:
            self.setMaxLength(max_length)

        # 设置基础样式
        self.setMinimumHeight(52)
        self._update_style()

        # 连接信号
        self.textChanged.connect(self._on_text_changed)

    def _update_style(self):
        """更新样式 - 根据状态动态调整"""
        # 确定边框颜色和背景色
        if self._has_error:
            border_color = MD3_ENHANCED_COLORS["error"]
            border_color_focus = MD3_ENHANCED_COLORS["error"]
            background = MD3_ENHANCED_COLORS["error_container"]
            background_focus = MD3_ENHANCED_COLORS["error_container"]
        else:
            border_color = MD3_ENHANCED_COLORS["outline"]
            border_color_focus = MD3_ENHANCED_COLORS["primary"]
            background = MD3_ENHANCED_COLORS["surface_container_highest"]
            background_focus = MD3_ENHANCED_COLORS["surface_container_high"]

        # 应用样式
        self.setStyleSheet(
            f"""
            QLineEdit {{
                background: {background};
                color: {MD3_ENHANCED_COLORS['on_surface']};
                border: 2px solid {border_color};
                border-radius: {MD3_ENHANCED_RADIUS['md']};
                padding: 14px 16px;
                font-size: 15px;
                font-family: "Microsoft YaHei UI", "Segoe UI", sans-serif;
                selection-background-color: {MD3_ENHANCED_COLORS['primary_container']};
                selection-color: {MD3_ENHANCED_COLORS['on_primary_container']};
            }}
            QLineEdit:focus {{
                border: 2px solid {border_color_focus};
                background: {background_focus};
            }}
            QLineEdit:hover:!focus {{
                border: 2px solid {MD3_ENHANCED_COLORS['on_surface_variant']};
                background: {background_focus};
            }}
            QLineEdit:disabled {{
                background: {MD3_ENHANCED_COLORS['surface_container']};
                color: {MD3_ENHANCED_COLORS['on_surface_variant']};
                border: 2px solid {MD3_ENHANCED_COLORS['outline_variant']};
            }}
        """
        )

    def _on_text_changed(self, text: str):
        """文本改变时的处理"""
        # 如果有错误状态，输入时自动清除
        if self._has_error and text:
            self.set_error(False)

    def set_error(self, has_error: bool, error_message: str = ""):
        """设置错误状态

        Args:
            has_error: 是否有错误
            error_message: 错误消息（可选）
        """
        try:
            self._has_error = has_error
            self._update_style()

            if has_error:
                self.setToolTip(error_message)
            else:
                self.setToolTip("")
        except Exception as e:
            logger.error(f"设置错误状态失败: {e}")

    def clear_with_animation(self):
        """带动画的清除"""
        try:
            # 创建淡出效果
            effect = QGraphicsOpacityEffect(self)
            self.setGraphicsEffect(effect)

            animation = QPropertyAnimation(effect, b"opacity")
            animation.setDuration(MD3_ENHANCED_DURATION["short2"])
            animation.setStartValue(1.0)
            animation.setEndValue(0.3)
            animation.setEasingCurve(MD3_ENHANCED_EASING["standard"])

            def on_finished():
                self.clear()
                effect.setOpacity(1.0)
                self.setGraphicsEffect(None)

            animation.finished.connect(on_finished)
            animation.start()
        except Exception as e:
            logger.error(f"清除动画失败: {e}")


class MD3Button(QPushButton):
    """Material Design 3 按钮 - 增强版

    特性：
    - 加载状态（显示加载动画）
    - 悬停/按压状态反馈
    - 平滑的状态转换
    - 阴影效果（主按钮）
    """

    def __init__(self, text: str, is_primary: bool = True, parent=None):
        super().__init__(text, parent)
        self.is_primary = is_primary
        self._is_loading = False
        self._original_text = text

        # 设置样式
        self.setMinimumHeight(52)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        # 更新样式
        self._update_style()

        # 添加阴影效果（仅主按钮）
        if is_primary:
            self._setup_shadow()

    def _setup_shadow(self):
        """设置阴影效果 - 提升按钮层次感"""
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(16)
        shadow.setXOffset(0)
        shadow.setYOffset(6)
        shadow.setColor(QColor(0, 0, 0, 50))
        self.setGraphicsEffect(shadow)

    def _update_style(self):
        """更新样式 - 符合 MD3 规范"""
        if self.is_primary:
            # 填充按钮（Filled Button）
            self.setStyleSheet(
                f"""
                QPushButton {{
                    background: {MD3_ENHANCED_COLORS['primary']};
                    color: {MD3_ENHANCED_COLORS['on_primary']};
                    border: none;
                    border-radius: {MD3_ENHANCED_RADIUS['full']};
                    padding: 16px 32px;
                    font-size: 15px;
                    font-weight: 600;
                    font-family: "Microsoft YaHei UI", "Segoe UI", sans-serif;
                    letter-spacing: 0.5px;
                }}
                QPushButton:hover {{
                    background: {MD3_ENHANCED_COLORS['primary_40']};
                }}
                QPushButton:pressed {{
                    background: {MD3_ENHANCED_COLORS['primary_60']};
                }}
                QPushButton:disabled {{
                    background: {MD3_ENHANCED_COLORS['surface_container_highest']};
                    color: {MD3_ENHANCED_COLORS['on_surface_variant']};
                }}
            """
            )
        else:
            # 轮廓按钮（Outlined Button）
            hover_bg = qss_rgba(MD3_ENHANCED_COLORS["primary"], 0.08)
            pressed_bg = qss_rgba(MD3_ENHANCED_COLORS["primary"], 0.16)
            self.setStyleSheet(
                f"""
                QPushButton {{
                    background: transparent;
                    color: {MD3_ENHANCED_COLORS['primary']};
                    border: 2px solid {MD3_ENHANCED_COLORS['outline']};
                    border-radius: {MD3_ENHANCED_RADIUS['full']};
                    padding: 14px 32px;
                    font-size: 15px;
                    font-weight: 600;
                    font-family: "Microsoft YaHei UI", "Segoe UI", sans-serif;
                    letter-spacing: 0.5px;
                }}
                QPushButton:hover {{
                    background: {hover_bg};
                    border: 2px solid {MD3_ENHANCED_COLORS['primary']};
                }}
                QPushButton:pressed {{
                    background: {pressed_bg};
                }}
                QPushButton:disabled {{
                    background: transparent;
                    color: {MD3_ENHANCED_COLORS['on_surface_variant']};
                    border: 2px solid {MD3_ENHANCED_COLORS['outline_variant']};
                }}
            """
            )

    def set_loading(self, loading: bool):
        """设置加载状态

        Args:
            loading: 是否加载中
        """
        try:
            self._is_loading = loading

            if loading:
                self.setEnabled(False)
                self.setText("加载中...")
            else:
                self.setEnabled(True)
                self.setText(self._original_text)
        except Exception as e:
            logger.error(f"设置加载状态失败: {e}")


class MD3TextButton(QPushButton):
    """Material Design 3 文本按钮"""

    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)

        self.setCursor(Qt.CursorShape.PointingHandCursor)
        hover_bg = qss_rgba(MD3_ENHANCED_COLORS["primary"], 0.08)
        pressed_bg = qss_rgba(MD3_ENHANCED_COLORS["primary"], 0.12)
        self.setStyleSheet(
            f"""
            QPushButton {{
                background: transparent;
                color: {MD3_ENHANCED_COLORS['primary']};
                border: none;
                padding: 8px 12px;
                font-size: 14px;
                font-weight: 500;
                font-family: "Microsoft YaHei UI", "Segoe UI", sans-serif;
            }}
            QPushButton:hover {{
                background: {hover_bg};
                border-radius: {MD3_ENHANCED_RADIUS['sm']};
            }}
            QPushButton:pressed {{
                background: {pressed_bg};
            }}
        """
        )


class IllustrationPanel(QWidget):
    """插画面板 - 左侧显示，插画填充整个区域

    增强特性：
    - 动态渐变背景
    - 图片加载动画
    - 渐变遮罩效果
    - 响应式缩放
    """

    def __init__(self, image_path: str = None, parent=None):
        super().__init__(parent)
        self.image_path = image_path
        self.original_pixmap = None  # 保存原始图片
        self._is_loading = False
        self.setup_ui()

    def setup_ui(self):
        """设置 UI"""
        # 设置面板背景渐变
        self.setStyleSheet(
            f"""
            IllustrationPanel {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 {MD3_ENHANCED_COLORS['primary_10']},
                    stop:0.3 {MD3_ENHANCED_COLORS['primary_20']},
                    stop:0.6 {MD3_ENHANCED_COLORS['secondary_20']},
                    stop:1 {MD3_ENHANCED_COLORS['tertiary_20']}
                );
                border-top-left-radius: 16px;
                border-bottom-left-radius: 16px;
            }}
        """
        )

        # ========== 添加阴影效果（层次感） ==========
        from PyQt6.QtWidgets import QGraphicsDropShadowEffect
        from PyQt6.QtGui import QColor

        self.shadow_effect = QGraphicsDropShadowEffect(self)
        self.shadow_effect.setBlurRadius(24)  # 阴影模糊半径
        self.shadow_effect.setXOffset(4)  # 向右偏移 4px
        self.shadow_effect.setYOffset(0)  # 垂直不偏移
        self.shadow_effect.setColor(QColor(0, 0, 0, 60))  # 黑色，透明度 60
        self.setGraphicsEffect(self.shadow_effect)

        # 插画标签（直接作为面板的子控件，填充整个面板）
        self.illustration_label = QLabel(self)
        self.illustration_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.illustration_label.setScaledContents(False)  # 不使用自动缩放
        # 让标签扩展以填充可用空间
        from PyQt6.QtWidgets import QSizePolicy

        self.illustration_label.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored
        )
        self.illustration_label.setStyleSheet(
            """
            QLabel {
                background: transparent;
            }
        """
        )

        # 欢迎文本（在默认显示时显示，叠加在插画标签上方）
        self.welcome_text = QLabel(self)
        self.welcome_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.welcome_text.setStyleSheet(
            f"""
            QLabel {{
                color: {MD3_ENHANCED_COLORS['primary_70']};
                font-size: 20px;
                font-weight: 500;
                line-height: 1.8;
                background: transparent;
                letter-spacing: 0.5px;
            }}
        """
        )
        # 初始时隐藏欢迎文本
        self.welcome_text.hide()

        # 在所有 UI 元素创建完成后加载插画
        self._load_illustration()

        # 标记需要启动动画（延迟到 showEvent）
        self._animation_pending = True

    def showEvent(self, event):
        """窗口显示时启动动画"""
        try:
            super().showEvent(event)
            # 只在第一次显示时启动动画
            if hasattr(self, "_animation_pending") and self._animation_pending:
                self._animation_pending = False
                # 延迟一帧启动动画，确保布局已完成
                from PyQt6.QtCore import QTimer

                QTimer.singleShot(50, self._setup_slide_in_animation)
        except Exception as e:
            logger.error(f"显示事件处理失败: {e}")

    def resizeEvent(self, event):
        """窗口大小改变时调整子控件尺寸"""
        try:
            super().resizeEvent(event)
            # 让插画标签和欢迎文本填充整个面板
            self.illustration_label.setGeometry(0, 0, self.width(), self.height())
            self.welcome_text.setGeometry(0, 0, self.width(), self.height())
            # 如果有自定义插画，重新缩放
            if self.original_pixmap:
                self._update_illustration()
        except Exception as e:
            logger.error(f"窗口大小调整事件处理失败: {e}")

    def _setup_slide_in_animation(self):
        """设置滑入动画 - 淡入效果，保持阴影

        使用透明度动画，动画完成后重新创建阴影效果。
        符合 Material Design 3 的强调减速曲线。
        """
        try:
            from PyQt6.QtCore import QPropertyAnimation
            from PyQt6.QtWidgets import QGraphicsOpacityEffect, QGraphicsDropShadowEffect

            # 创建临时透明度效果用于动画
            temp_opacity_effect = QGraphicsOpacityEffect(self)
            temp_opacity_effect.setOpacity(0.0)

            # 临时替换阴影效果为透明度效果
            self.setGraphicsEffect(temp_opacity_effect)

            # 创建透明度动画
            self.fade_in_animation = QPropertyAnimation(temp_opacity_effect, b"opacity")
            self.fade_in_animation.setDuration(MD3_ENHANCED_DURATION["long1"])  # 450ms
            self.fade_in_animation.setStartValue(0.0)
            self.fade_in_animation.setEndValue(1.0)
            self.fade_in_animation.setEasingCurve(MD3_ENHANCED_EASING["emphasized_decelerate"])

            # 动画完成后重新创建阴影效果
            def on_animation_finished():
                # 重新创建阴影效果
                shadow = QGraphicsDropShadowEffect(self)
                shadow.setBlurRadius(24)
                shadow.setXOffset(4)
                shadow.setYOffset(0)
                shadow.setColor(QColor(0, 0, 0, 60))
                self.setGraphicsEffect(shadow)
                self.shadow_effect = shadow

            self.fade_in_animation.finished.connect(on_animation_finished)

            # 启动动画
            self.fade_in_animation.start()
        except Exception as e:
            logger.error(f"滑入动画设置失败: {e}")

    def _load_illustration(self):
        """加载插画"""
        if self.image_path:
            # 尝试加载用户提供的插画
            from pathlib import Path
            import os

            image_file = Path(self.image_path)

            # 如果是相对路径，尝试相对于当前工作目录和项目根目录
            if not image_file.is_absolute():
                # 尝试相对于当前工作目录
                if not image_file.exists():
                    # 尝试相对于脚本所在目录（项目根目录）
                    # 获取当前文件所在目录的父目录的父目录（项目根目录）
                    current_file = Path(__file__)
                    project_root = current_file.parent.parent.parent
                    image_file = project_root / self.image_path

            logger.debug(f"尝试加载插画: {image_file}")
            logger.debug(f"文件是否存在: {image_file.exists()}")

            if image_file.exists():
                pixmap = QPixmap(str(image_file))
                if not pixmap.isNull():
                    logger.info(f"插画加载成功: {image_file}")
                    logger.debug(f"图片尺寸: {pixmap.width()}x{pixmap.height()}")
                    self.original_pixmap = pixmap
                    # 有自定义插画时，隐藏欢迎文本
                    self.welcome_text.hide()
                    # 显示插画标签
                    self.illustration_label.show()
                    # 更新插画显示
                    self._update_illustration()
                    return
                else:
                    logger.warning(f"无法加载插画 {image_file}（QPixmap 为空），使用默认显示")
            else:
                logger.warning(f"插画文件不存在 {image_file}，使用默认显示")
                logger.debug(f"当前工作目录: {os.getcwd()}")

        # 默认显示：显示猫咪图标和欢迎文本 - 优化视觉效果
        logger.debug("使用默认显示（猫咪图标）")
        self.original_pixmap = None
        self.illustration_label.clear()
        self.illustration_label.setText("🐱\n\nMintChat")
        self.illustration_label.setStyleSheet(
            f"""
            QLabel {{
                color: {MD3_ENHANCED_COLORS['primary_60']};
                font-size: 80px;
                font-weight: 700;
                background: transparent;
                letter-spacing: 2px;
            }}
        """
        )
        self.illustration_label.show()
        # 显示欢迎文本
        self.welcome_text.show()

    def _update_illustration(self):
        """更新插画显示（根据当前尺寸）- 应用圆角遮罩"""
        try:
            if self.original_pixmap and not self.original_pixmap.isNull():
                # 获取整个面板的尺寸
                panel_size = self.size()

                # 如果面板尺寸无效，使用默认尺寸
                if panel_size.width() <= 0 or panel_size.height() <= 0:
                    # 使用默认尺寸
                    panel_size.setWidth(500)
                    panel_size.setHeight(600)

                logger.debug(f"面板尺寸: {panel_size.width()}x{panel_size.height()}")

                # 缩放图片以填充整个面板，保持宽高比
                scaled_pixmap = self.original_pixmap.scaled(
                    panel_size,
                    Qt.AspectRatioMode.KeepAspectRatioByExpanding,  # 填充整个区域
                    Qt.TransformationMode.SmoothTransformation,
                )

                logger.debug(f"缩放后图片尺寸: {scaled_pixmap.width()}x{scaled_pixmap.height()}")

                # 如果缩放后的图片比面板大，需要裁剪
                if (
                    scaled_pixmap.width() > panel_size.width()
                    or scaled_pixmap.height() > panel_size.height()
                ):
                    # 计算裁剪位置（居中裁剪）
                    x = (scaled_pixmap.width() - panel_size.width()) // 2
                    y = (scaled_pixmap.height() - panel_size.height()) // 2
                    scaled_pixmap = scaled_pixmap.copy(
                        x, y, panel_size.width(), panel_size.height()
                    )
                    logger.debug(
                        f"裁剪后图片尺寸: {scaled_pixmap.width()}x{scaled_pixmap.height()}"
                    )

                # ========== 应用圆角遮罩 ==========
                # 创建一个新的 pixmap 用于绘制圆角图片
                from PyQt6.QtGui import QPainter, QPainterPath

                rounded_pixmap = QPixmap(panel_size)
                rounded_pixmap.fill(Qt.GlobalColor.transparent)

                # 创建画家
                painter = QPainter(rounded_pixmap)
                painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

                # 创建圆角路径（左上角和左下角有圆角）
                path = QPainterPath()
                radius = 16  # 圆角半径
                path.addRoundedRect(0, 0, panel_size.width(), panel_size.height(), radius, radius)

                # 设置裁剪路径
                painter.setClipPath(path)

                # 绘制图片
                painter.drawPixmap(0, 0, scaled_pixmap)
                painter.end()

                # 设置圆角图片
                self.illustration_label.setPixmap(rounded_pixmap)
                logger.debug(f"已应用圆角遮罩（半径: {radius}px）")
        except Exception as e:
            logger.error(f"更新插画失败: {e}")

    def set_image(self, image_path: str):
        """设置插画图片

        Args:
            image_path: 图片路径（支持绝对路径和相对路径）
        """
        try:
            self.image_path = image_path
            self._load_illustration()
        except Exception as e:
            logger.error(f"设置图片失败: {e}")

    def set_welcome_text(self, text: str):
        """设置欢迎文本

        Args:
            text: 欢迎文本
        """
        if hasattr(self, "welcome_text"):
            self.welcome_text.setText(text)

    def show_welcome_text(self, show: bool = True):
        """显示或隐藏欢迎文本

        Args:
            show: True 显示，False 隐藏
        """
        if hasattr(self, "welcome_text"):
            if show:
                self.welcome_text.show()
            else:
                self.welcome_text.hide()


class AuthWindow(QWidget):
    """认证窗口基类 - 作为子控件使用，不是独立窗口"""

    # 信号
    login_success = pyqtSignal(dict)  # 登录成功，传递用户信息

    def __init__(self, illustration_path: str = None, parent=None):
        super().__init__(parent)

        # 认证服务
        self.auth_service = AuthService()

        # 插画路径
        self.illustration_path = illustration_path

        # 圆角半径
        self.border_radius = 16

        # 设置 UI
        self.setup_ui()

    def setup_ui(self):
        """设置 UI - 将在子类中实现"""
        pass
