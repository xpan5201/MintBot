"""
性能图表组件 - v2.45.0

实时折线图，用于显示TTS性能趋势
"""

from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import Qt, QPointF, QRectF
from PyQt6.QtGui import QPainter, QPen, QColor, QPainterPath, QFont
from collections import deque

from src.utils.logger import get_logger

logger = get_logger(__name__)


class PerformanceChart(QWidget):
    """
    性能图表组件 (v2.45.0)
    
    实时折线图，显示性能指标的变化趋势
    """
    
    def __init__(self, title: str = "性能趋势", max_points: int = 60, parent=None):
        """
        初始化性能图表
        
        Args:
            title: 图表标题
            max_points: 最大数据点数（默认60，即60秒）
            parent: 父组件
        """
        super().__init__(parent)
        self.title = title
        self.max_points = max_points
        
        # 数据存储（使用deque实现固定大小的滑动窗口）
        self._data_points: deque = deque(maxlen=max_points)
        
        # 图表配置
        self._min_value = 0.0
        self._max_value = 100.0
        self._auto_scale = True  # 自动缩放Y轴
        
        # 颜色配置（Material Design 3）
        self._line_color = QColor("#FF6B9D")  # 粉色
        self._grid_color = QColor(255, 255, 255, 30)  # 半透明白色
        self._text_color = QColor(255, 255, 255, 200)  # 白色
        self._bg_color = QColor(0, 0, 0, 50)  # 半透明黑色
        
        # 设置最小尺寸
        self.setMinimumSize(300, 150)
    
    def add_data_point(self, value: float):
        """
        添加数据点
        
        Args:
            value: 数据值
        """
        self._data_points.append(value)
        
        # 自动缩放Y轴
        if self._auto_scale and len(self._data_points) > 0:
            self._min_value = min(self._data_points)
            self._max_value = max(self._data_points)
            
            # 添加10%的边距
            value_range = self._max_value - self._min_value
            if value_range > 0:
                margin = value_range * 0.1
                self._min_value -= margin
                self._max_value += margin
            else:
                # 如果所有值相同，设置默认范围
                self._min_value = value - 10
                self._max_value = value + 10
        
        # 触发重绘
        self.update()
    
    def clear(self):
        """清除所有数据点"""
        self._data_points.clear()
        self.update()
    
    def paintEvent(self, event):
        """绘制图表"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # 绘制背景
        painter.fillRect(self.rect(), self._bg_color)
        
        # 计算绘图区域（留出边距）
        margin = 40
        chart_rect = QRectF(
            margin, margin,
            self.width() - 2 * margin,
            self.height() - 2 * margin
        )
        
        # 绘制标题
        painter.setPen(self._text_color)
        title_font = QFont()
        title_font.setPointSize(9)
        title_font.setBold(True)
        painter.setFont(title_font)
        painter.drawText(10, 20, self.title)
        
        # 如果没有数据，显示提示
        if len(self._data_points) == 0:
            painter.drawText(chart_rect, Qt.AlignmentFlag.AlignCenter, "暂无数据")
            return
        
        # 绘制网格线
        self._draw_grid(painter, chart_rect)
        
        # 绘制折线
        self._draw_line(painter, chart_rect)
        
        # 绘制Y轴标签
        self._draw_y_labels(painter, chart_rect)
    
    def _draw_grid(self, painter: QPainter, rect: QRectF):
        """绘制网格线"""
        painter.setPen(QPen(self._grid_color, 1, Qt.PenStyle.DashLine))
        
        # 绘制水平网格线（5条）
        for i in range(6):
            y = rect.top() + (rect.height() / 5) * i
            painter.drawLine(
                QPointF(rect.left(), y),
                QPointF(rect.right(), y)
            )
    
    def _draw_line(self, painter: QPainter, rect: QRectF):
        """绘制折线"""
        if len(self._data_points) < 2:
            return
        
        # 创建路径
        path = QPainterPath()
        
        # 计算点的位置
        points = []
        for i, value in enumerate(self._data_points):
            # X坐标：从左到右均匀分布
            x = rect.left() + (rect.width() / (self.max_points - 1)) * i
            
            # Y坐标：根据值映射到图表高度（注意Y轴是倒置的）
            if self._max_value > self._min_value:
                normalized = (value - self._min_value) / (self._max_value - self._min_value)
                y = rect.bottom() - normalized * rect.height()
            else:
                y = rect.center().y()
            
            points.append(QPointF(x, y))
        
        # 绘制路径
        if points:
            path.moveTo(points[0])
            for point in points[1:]:
                path.lineTo(point)
            
            painter.setPen(QPen(self._line_color, 2))
            painter.drawPath(path)

    def _draw_y_labels(self, painter: QPainter, rect: QRectF):
        """绘制Y轴标签"""
        painter.setPen(self._text_color)
        label_font = QFont()
        label_font.setPointSize(7)
        painter.setFont(label_font)

        # 绘制最大值和最小值标签
        painter.drawText(
            int(rect.left() - 35), int(rect.top() + 5),
            f"{self._max_value:.1f}"
        )
        painter.drawText(
            int(rect.left() - 35), int(rect.bottom() + 5),
            f"{self._min_value:.1f}"
        )
