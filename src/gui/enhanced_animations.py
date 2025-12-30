"""
增强动画系统

基于 Material Design 3 Expressive Motion System
提供丰富的动画效果和微交互
优化性能，确保 60fps 流畅运行
"""

from PyQt6.QtWidgets import QWidget, QGraphicsOpacityEffect
from PyQt6.QtCore import (
    QPropertyAnimation,
    QEasingCurve,
    QParallelAnimationGroup,
    QPoint,
    QRect,
    pyqtProperty,
    Qt,
)

from .material_design_light import MD3_DURATION


class AnimationMixin:
    """动画混入类 - 为组件添加动画能力"""

    def setup_fade_animation(self, duration: int = None):
        """设置淡入淡出动画"""
        if duration is None:
            duration = MD3_DURATION["medium2"]

        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.opacity_effect)

        self.fade_animation = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.fade_animation.setDuration(duration)
        self.fade_animation.setEasingCurve(QEasingCurve.Type.InOutCubic)

    def fade_in(self, duration: int = None):
        """淡入"""
        if not hasattr(self, "fade_animation"):
            self.setup_fade_animation(duration)

        self.fade_animation.setStartValue(0.0)
        self.fade_animation.setEndValue(1.0)
        self.fade_animation.start()

    def fade_out(self, duration: int = None):
        """淡出"""
        if not hasattr(self, "fade_animation"):
            self.setup_fade_animation(duration)

        self.fade_animation.setStartValue(1.0)
        self.fade_animation.setEndValue(0.0)
        self.fade_animation.start()

    def setup_slide_animation(self, duration: int = None):
        """设置滑动动画"""
        if duration is None:
            duration = MD3_DURATION["medium3"]

        self.slide_animation = QPropertyAnimation(self, b"pos")
        self.slide_animation.setDuration(duration)
        self.slide_animation.setEasingCurve(QEasingCurve.Type.OutCubic)

    def slide_in_from_right(self, distance: int = 300):
        """从右侧滑入"""
        if not hasattr(self, "slide_animation"):
            self.setup_slide_animation()

        start_pos = self.pos() + QPoint(distance, 0)
        end_pos = self.pos()

        self.slide_animation.setStartValue(start_pos)
        self.slide_animation.setEndValue(end_pos)
        self.slide_animation.start()

    def slide_in_from_bottom(self, distance: int = 100):
        """从底部滑入"""
        if not hasattr(self, "slide_animation"):
            self.setup_slide_animation()

        start_pos = self.pos() + QPoint(0, distance)
        end_pos = self.pos()

        self.slide_animation.setStartValue(start_pos)
        self.slide_animation.setEndValue(end_pos)
        self.slide_animation.start()

    def setup_scale_animation(self, duration: int = None):
        """设置缩放动画"""
        if duration is None:
            duration = MD3_DURATION["medium2"]

        self.scale_animation = QPropertyAnimation(self, b"geometry")
        self.scale_animation.setDuration(duration)
        self.scale_animation.setEasingCurve(QEasingCurve.Type.OutBack)

    def scale_in(self, scale_factor: float = 0.8):
        """缩放进入"""
        if not hasattr(self, "scale_animation"):
            self.setup_scale_animation()

        current_rect = self.geometry()
        center = current_rect.center()

        # 计算缩放后的矩形
        scaled_width = int(current_rect.width() * scale_factor)
        scaled_height = int(current_rect.height() * scale_factor)

        start_rect = QRect(
            center.x() - scaled_width // 2,
            center.y() - scaled_height // 2,
            scaled_width,
            scaled_height,
        )

        self.scale_animation.setStartValue(start_rect)
        self.scale_animation.setEndValue(current_rect)
        self.scale_animation.start()


class RippleEffect(QWidget):
    """涟漪效果组件"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setStyleSheet("background: transparent;")

        # 涟漪参数
        self._radius = 0
        self._opacity = 0.3

        # 设置动画
        self.radius_animation = QPropertyAnimation(self, b"radius")
        self.radius_animation.setDuration(MD3_DURATION["medium4"])
        self.radius_animation.setEasingCurve(QEasingCurve.Type.OutCubic)

        self.opacity_animation = QPropertyAnimation(self, b"opacity")
        self.opacity_animation.setDuration(MD3_DURATION["medium4"])
        self.opacity_animation.setEasingCurve(QEasingCurve.Type.OutCubic)

        # 并行动画组
        self.animation_group = QParallelAnimationGroup()
        self.animation_group.addAnimation(self.radius_animation)
        self.animation_group.addAnimation(self.opacity_animation)
        self.animation_group.finished.connect(self.hide)

    @pyqtProperty(int)
    def radius(self):
        return self._radius

    @radius.setter
    def radius(self, value):
        self._radius = value
        self.update()

    @pyqtProperty(float)
    def opacity(self):
        return self._opacity

    @opacity.setter
    def opacity(self, value):
        self._opacity = value
        self.update()

    def start_ripple(self, pos: QPoint, max_radius: int = None):
        """开始涟漪动画"""
        if max_radius is None:
            max_radius = max(self.parent().width(), self.parent().height())

        self.show()
        self.raise_()

        # 设置涟漪中心
        self.ripple_center = pos

        # 设置动画
        self.radius_animation.setStartValue(0)
        self.radius_animation.setEndValue(max_radius)

        self.opacity_animation.setStartValue(0.3)
        self.opacity_animation.setEndValue(0.0)

        # 开始动画
        self.animation_group.start()

    def paintEvent(self, event):
        """绘制涟漪"""
        if not hasattr(self, "ripple_center"):
            return

        from PyQt6.QtGui import QPainter, QBrush, QColor

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 设置颜色和透明度
        color = QColor(0, 0, 0, int(self._opacity * 255))
        painter.setBrush(QBrush(color))
        painter.setPen(Qt.PenStyle.NoPen)

        # 绘制圆形
        painter.drawEllipse(self.ripple_center, self._radius, self._radius)


class LoadingAnimation(QWidget):
    """加载动画组件"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(40, 40)

        # 旋转角度
        self._rotation = 0

        # 设置动画
        self.rotation_animation = QPropertyAnimation(self, b"rotation")
        self.rotation_animation.setDuration(MD3_DURATION["extra_long4"])
        self.rotation_animation.setStartValue(0)
        self.rotation_animation.setEndValue(360)
        self.rotation_animation.setLoopCount(-1)  # 无限循环
        self.rotation_animation.setEasingCurve(QEasingCurve.Type.Linear)

    @pyqtProperty(int)
    def rotation(self):
        return self._rotation

    @rotation.setter
    def rotation(self, value):
        self._rotation = value
        self.update()

    def start(self):
        """开始动画"""
        self.rotation_animation.start()
        self.show()

    def stop(self):
        """停止动画"""
        self.rotation_animation.stop()
        self.hide()

    def paintEvent(self, event):
        """绘制加载动画"""
        from PyQt6.QtGui import QPainter, QPen, QColor

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 设置画笔
        pen = QPen(QColor("#9C27B0"))
        pen.setWidth(3)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)

        # 绘制圆弧
        center_x = self.width() / 2
        center_y = self.height() / 2
        radius = 15

        # 计算起始角度
        start_angle = self._rotation * 16  # Qt 使用 1/16 度
        span_angle = 270 * 16  # 3/4 圆

        painter.drawArc(
            int(center_x - radius),
            int(center_y - radius),
            int(radius * 2),
            int(radius * 2),
            start_angle,
            span_angle,
        )


def create_bounce_animation(
    widget: QWidget, property_name: bytes, start_value, end_value, duration: int = None
):
    """创建弹跳动画"""
    if duration is None:
        duration = MD3_DURATION["medium3"]

    animation = QPropertyAnimation(widget, property_name)
    animation.setDuration(duration)
    animation.setStartValue(start_value)
    animation.setEndValue(end_value)
    animation.setEasingCurve(QEasingCurve.Type.OutBounce)

    return animation


def create_smooth_scroll_animation(scroll_area, target_value: int, duration: int = None):
    """创建平滑滚动动画"""
    if duration is None:
        duration = MD3_DURATION["long2"]

    animation = QPropertyAnimation(scroll_area.verticalScrollBar(), b"value")
    animation.setDuration(duration)
    animation.setEndValue(target_value)
    animation.setEasingCurve(QEasingCurve.Type.OutCubic)

    return animation
