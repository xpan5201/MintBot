"""
加载状态和骨架屏组件 (v2.15.0 增强版)

基于 Material Design 3 最新规范
优化视觉层次、交互反馈、性能
增强用户体验和可访问性
"""

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGraphicsOpacityEffect
from PyQt6.QtCore import Qt, QPropertyAnimation, QEasingCurve, QTimer, pyqtProperty
from PyQt6.QtGui import QPainter, QColor, QLinearGradient, QPainterPath

from .material_design_light import MD3_LIGHT_COLORS, MD3_DURATION
from .material_design_enhanced import (
    MD3_ENHANCED_DURATION,
    MD3_ENHANCED_EASING,
)


class SkeletonLoader(QWidget):
    """骨架屏加载器 - v2.15.0 优化版"""

    def __init__(self, width: int = 300, height: int = 60, parent=None):
        super().__init__(parent)
        self.setFixedSize(width, height)

        # 动画参数
        self._shimmer_position = 0.0

        # 设置动画
        self.setup_animation()

    def setup_animation(self):
        """设置闪烁动画 - 优化性能"""
        self.shimmer_animation = QPropertyAnimation(self, b"shimmer_position")
        self.shimmer_animation.setDuration(MD3_ENHANCED_DURATION["extra_long2"])
        self.shimmer_animation.setStartValue(0.0)
        self.shimmer_animation.setEndValue(1.0)
        self.shimmer_animation.setEasingCurve(MD3_ENHANCED_EASING["smooth"])
        self.shimmer_animation.setLoopCount(-1)  # 无限循环
        self.shimmer_animation.start()

    @pyqtProperty(float)
    def shimmer_position(self):
        return self._shimmer_position

    @shimmer_position.setter
    def shimmer_position(self, value):
        self._shimmer_position = value
        self.update()

    def paintEvent(self, event):
        """绘制骨架屏"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 基础颜色
        base_color = QColor(MD3_LIGHT_COLORS["surface_container"])
        highlight_color = QColor(MD3_LIGHT_COLORS["surface_container_high"])

        # 绘制背景
        painter.setBrush(base_color)
        painter.setPen(Qt.PenStyle.NoPen)

        # 绘制三行骨架
        y_positions = [10, 30, 50]
        widths = [self.width() * 0.8, self.width() * 0.6, self.width() * 0.4]

        for y, width in zip(y_positions, widths):
            path = QPainterPath()
            path.addRoundedRect(10, y, width, 12, 6, 6)
            painter.fillPath(path, base_color)

        # 绘制闪烁效果
        gradient = QLinearGradient(
            self._shimmer_position * self.width() - 100,
            0,
            self._shimmer_position * self.width() + 100,
            0,
        )
        gradient.setColorAt(0.0, base_color)
        gradient.setColorAt(0.5, highlight_color)
        gradient.setColorAt(1.0, base_color)

        for y, width in zip(y_positions, widths):
            path = QPainterPath()
            path.addRoundedRect(10, y, width, 12, 6, 6)
            painter.fillPath(path, gradient)

    def stop(self):
        """停止动画"""
        self.shimmer_animation.stop()


class PulsingDot(QWidget):
    """脉冲点 - 用于加载指示"""

    def __init__(self, size: int = 8, color: str = None, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)

        self.dot_size = size
        self.dot_color = color or MD3_LIGHT_COLORS["primary"]

        # 动画参数
        self._opacity = 1.0

        # 设置透明度效果
        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.opacity_effect)

    def start_animation(self, delay: int = 0):
        """启动脉冲动画"""
        # 透明度动画
        self.pulse_animation = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.pulse_animation.setDuration(MD3_DURATION["long4"])
        self.pulse_animation.setStartValue(0.3)
        self.pulse_animation.setEndValue(1.0)
        self.pulse_animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self.pulse_animation.setLoopCount(-1)  # 无限循环

        # 延迟启动
        if delay > 0:
            QTimer.singleShot(delay, self.pulse_animation.start)
        else:
            self.pulse_animation.start()

    def stop_animation(self):
        """停止动画"""
        if hasattr(self, "pulse_animation"):
            self.pulse_animation.stop()

    def paintEvent(self, event):
        """绘制点"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 绘制圆点
        painter.setBrush(QColor(self.dot_color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(0, 0, self.dot_size, self.dot_size)


class LoadingIndicator(QWidget):
    """加载指示器 - 三个脉冲点"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()

    def setup_ui(self):
        """设置 UI"""
        # 主布局
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # 创建三个点
        self.dots = []
        for i in range(3):
            dot = PulsingDot()
            dot.start_animation(delay=i * 200)
            self.dots.append(dot)
            layout.addWidget(dot)

    def stop(self):
        """停止动画"""
        for dot in self.dots:
            dot.stop_animation()


class CircularProgress(QWidget):
    """圆形进度指示器"""

    def __init__(self, size: int = 24, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)

        self.progress_size = size
        self._rotation = 0.0

        # 设置旋转动画
        self.setup_animation()

    def setup_animation(self):
        """设置旋转动画"""
        self.rotation_animation = QPropertyAnimation(self, b"rotation")
        self.rotation_animation.setDuration(MD3_DURATION["extra_long3"])
        self.rotation_animation.setStartValue(0.0)
        self.rotation_animation.setEndValue(360.0)
        self.rotation_animation.setEasingCurve(QEasingCurve.Type.Linear)
        self.rotation_animation.setLoopCount(-1)  # 无限循环
        self.rotation_animation.start()

    @pyqtProperty(float)
    def rotation(self):
        return self._rotation

    @rotation.setter
    def rotation(self, value):
        self._rotation = value
        self.update()

    def paintEvent(self, event):
        """绘制圆形进度"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 移动到中心
        painter.translate(self.width() / 2, self.height() / 2)
        painter.rotate(self._rotation)

        # 绘制圆弧
        painter.setPen(Qt.PenStyle.NoPen)

        # 绘制背景圆
        painter.setBrush(QColor(MD3_LIGHT_COLORS["surface_container"]))
        painter.drawEllipse(
            -self.progress_size // 2,
            -self.progress_size // 2,
            self.progress_size,
            self.progress_size,
        )

        # 绘制进度弧
        painter.setBrush(QColor(MD3_LIGHT_COLORS["primary"]))
        path = QPainterPath()
        path.moveTo(0, 0)
        path.arcTo(
            -self.progress_size // 2,
            -self.progress_size // 2,
            self.progress_size,
            self.progress_size,
            90,  # 起始角度
            270,  # 扫描角度（3/4 圆）
        )
        path.closeSubpath()
        painter.fillPath(path, QColor(MD3_LIGHT_COLORS["primary"]))

        # 绘制中心白色圆
        inner_size = self.progress_size - 6
        painter.setBrush(QColor(MD3_LIGHT_COLORS["surface"]))
        painter.drawEllipse(-inner_size // 2, -inner_size // 2, inner_size, inner_size)

    def stop(self):
        """停止动画"""
        self.rotation_animation.stop()


class EmptyState(QWidget):
    """空状态组件 - 用于无消息时显示"""

    def __init__(
        self,
        icon: str = "chat",
        title: str = "开始对话",
        subtitle: str = "发送消息开始与 AI 助手对话",
        parent=None,
    ):
        super().__init__(parent)

        self.icon_name = icon
        self.title_text = title
        self.subtitle_text = subtitle

        self.setup_ui()

    def setup_ui(self):
        """设置 UI"""
        # 主布局
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(16)

        # 图标（使用 Material Icons）
        from .material_icons import MaterialIcon

        icon = MaterialIcon(self.icon_name, 64)
        icon.setStyleSheet(f"color: {MD3_LIGHT_COLORS['on_surface_variant']};")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon)

        # 标题
        title = QLabel(self.title_text)
        title.setStyleSheet(
            f"""
            QLabel {{
                color: {MD3_LIGHT_COLORS['on_surface']};
                font-size: 20px;
                font-weight: 500;
                background: transparent;
            }}
        """
        )
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        # 副标题
        subtitle = QLabel(self.subtitle_text)
        subtitle.setStyleSheet(
            f"""
            QLabel {{
                color: {MD3_LIGHT_COLORS['on_surface_variant']};
                font-size: 14px;
                background: transparent;
            }}
        """
        )
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)
