"""
增强交互组件

基于 Material Design 3 最佳实践
提供丰富的交互反馈和微交互效果
包含涟漪效果、悬停状态、按压反馈等
"""

from PyQt6.QtWidgets import QPushButton, QWidget
from PyQt6.QtCore import (
    Qt, QPropertyAnimation, QEasingCurve, QPoint, QTimer,
    pyqtSignal, QSequentialAnimationGroup, pyqtProperty
)
from PyQt6.QtGui import QPainter, QColor, QBrush, QMouseEvent

from .material_design_light import (
    MD3_DURATION, MD3_STATE_LAYERS
)


class InteractiveButton(QPushButton):
    """增强交互按钮 - 带涟漪效果和状态反馈"""

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)

        # 涟漪效果参数
        self._ripple_radius = 0
        self.ripple_opacity = 0.0
        self.ripple_center = QPoint()
        self.ripple_active = False

        # 悬停状态
        self.is_hovered = False
        self._hover_opacity = 0.0

        # 设置动画
        self.setup_animations()

        # 启用鼠标追踪
        self.setMouseTracking(True)

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

    def setup_animations(self):
        """设置动画"""
        # 涟漪动画
        self.ripple_animation = QPropertyAnimation(self, b"ripple_radius")
        self.ripple_animation.setDuration(MD3_DURATION["medium4"])
        self.ripple_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.ripple_animation.finished.connect(self.on_ripple_finished)

        # 悬停动画
        self.hover_animation = QPropertyAnimation(self, b"hover_opacity")
        self.hover_animation.setDuration(MD3_DURATION["short2"])
        self.hover_animation.setEasingCurve(QEasingCurve.Type.InOutCubic)

    def mousePressEvent(self, event: QMouseEvent):
        """鼠标按下 - 开始涟漪效果"""
        super().mousePressEvent(event)

        # 记录涟漪中心
        self.ripple_center = event.pos()
        self.ripple_active = True

        # 计算最大半径
        max_radius = max(
            self.ripple_center.x(),
            self.width() - self.ripple_center.x(),
            self.ripple_center.y(),
            self.height() - self.ripple_center.y()
        ) * 1.5

        # 开始涟漪动画
        self.ripple_animation.setStartValue(0)
        self.ripple_animation.setEndValue(int(max_radius))
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
        self.is_hovered = True

        self.hover_animation.setStartValue(self.hover_opacity)
        self.hover_animation.setEndValue(MD3_STATE_LAYERS["hover"])
        self.hover_animation.start()

    def leaveEvent(self, event):
        """鼠标离开 - 隐藏悬停状态"""
        super().leaveEvent(event)
        self.is_hovered = False

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
        """绘制按钮"""
        super().paintEvent(event)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 绘制悬停状态
        if self.hover_opacity > 0:
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


class InteractiveCard(QWidget):
    """交互式卡片 - 带悬停效果和点击反馈"""

    clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)

        # 悬停状态
        self.is_hovered = False
        self._elevation = 1

        # 设置动画
        self.setup_animations()

        # 启用鼠标追踪
        self.setMouseTracking(True)

        # 设置光标
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    @pyqtProperty(int)
    def elevation(self):
        return self._elevation

    @elevation.setter
    def elevation(self, value):
        self._elevation = value
        self.update()

    def setup_animations(self):
        """设置动画"""
        # 阴影动画（通过改变 elevation 实现）
        self.elevation_animation = QPropertyAnimation(self, b"elevation")
        self.elevation_animation.setDuration(MD3_DURATION["short3"])
        self.elevation_animation.setEasingCurve(QEasingCurve.Type.InOutCubic)

    def enterEvent(self, event):
        """鼠标进入 - 提升阴影"""
        super().enterEvent(event)
        self.is_hovered = True

        self.elevation_animation.setStartValue(self.elevation)
        self.elevation_animation.setEndValue(3)
        self.elevation_animation.start()

    def leaveEvent(self, event):
        """鼠标离开 - 降低阴影"""
        super().leaveEvent(event)
        self.is_hovered = False

        self.elevation_animation.setStartValue(self.elevation)
        self.elevation_animation.setEndValue(1)
        self.elevation_animation.start()

    def mousePressEvent(self, event: QMouseEvent):
        """鼠标按下 - 按压反馈"""
        super().mousePressEvent(event)

        # 快速降低阴影
        self.elevation_animation.setDuration(MD3_DURATION["short1"])
        self.elevation_animation.setStartValue(self.elevation)
        self.elevation_animation.setEndValue(1)
        self.elevation_animation.start()

    def mouseReleaseEvent(self, event: QMouseEvent):
        """鼠标释放"""
        super().mouseReleaseEvent(event)

        # 恢复动画时长
        self.elevation_animation.setDuration(MD3_DURATION["short3"])

        # 如果鼠标还在卡片内，恢复悬停状态
        if self.rect().contains(event.pos()):
            self.elevation_animation.setStartValue(self.elevation)
            self.elevation_animation.setEndValue(3)
            self.elevation_animation.start()

            # 发送点击信号
            self.clicked.emit()


class PulsingWidget(QWidget):
    """脉冲动画组件 - 用于吸引注意力"""

    def __init__(self, parent=None):
        super().__init__(parent)

        # 脉冲参数
        self._pulse_scale = 1.0

        # 设置动画
        self.pulse_animation = QPropertyAnimation(self, b"pulse_scale")
        self.pulse_animation.setDuration(MD3_DURATION["long2"])
        self.pulse_animation.setStartValue(1.0)
        self.pulse_animation.setEndValue(1.1)
        self.pulse_animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self.pulse_animation.setLoopCount(-1)  # 无限循环

        # 设置反向动画
        self.pulse_animation.setDirection(QPropertyAnimation.Direction.Forward)
        self.pulse_animation.finished.connect(self.reverse_pulse)

    def start_pulsing(self):
        """开始脉冲"""
        self.pulse_animation.start()

    def stop_pulsing(self):
        """停止脉冲"""
        self.pulse_animation.stop()
        self._pulse_scale = 1.0
        self.update()

    def reverse_pulse(self):
        """反转脉冲方向"""
        if self.pulse_animation.direction() == QPropertyAnimation.Direction.Forward:
            self.pulse_animation.setDirection(QPropertyAnimation.Direction.Backward)
        else:
            self.pulse_animation.setDirection(QPropertyAnimation.Direction.Forward)
        self.pulse_animation.start()

    @pyqtProperty(float)
    def pulse_scale(self):
        """脉冲缩放属性 - v2.25.0 修复：添加缺失的属性定义"""
        return self._pulse_scale

    @pulse_scale.setter
    def pulse_scale(self, value):
        """设置脉冲缩放 - v2.25.0 修复：添加缺失的属性定义"""
        self._pulse_scale = value
        self.update()


class ShakeAnimation:
    """抖动动画 - 用于错误提示"""

    @staticmethod
    def shake_widget(widget: QWidget, intensity: int = 10, duration: int = None):
        """抖动组件"""
        if duration is None:
            duration = MD3_DURATION["medium2"]

        original_pos = widget.pos()

        # 创建序列动画
        shake_sequence = QSequentialAnimationGroup()

        # 左右抖动
        for i in range(4):
            # 向右
            anim_right = QPropertyAnimation(widget, b"pos")
            anim_right.setDuration(duration // 8)
            anim_right.setEndValue(original_pos + QPoint(intensity, 0))
            anim_right.setEasingCurve(QEasingCurve.Type.InOutCubic)
            shake_sequence.addAnimation(anim_right)

            # 向左
            anim_left = QPropertyAnimation(widget, b"pos")
            anim_left.setDuration(duration // 8)
            anim_left.setEndValue(original_pos - QPoint(intensity, 0))
            anim_left.setEasingCurve(QEasingCurve.Type.InOutCubic)
            shake_sequence.addAnimation(anim_left)

            # 逐渐减小强度
            intensity = int(intensity * 0.7)

        # 回到原位
        anim_back = QPropertyAnimation(widget, b"pos")
        anim_back.setDuration(duration // 8)
        anim_back.setEndValue(original_pos)
        anim_back.setEasingCurve(QEasingCurve.Type.InOutCubic)
        shake_sequence.addAnimation(anim_back)

        shake_sequence.start()

        return shake_sequence
