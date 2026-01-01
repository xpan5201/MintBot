"""
语音控制面板组件 - v2.37.0

支持语速和音色调整
"""

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSlider
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont

from src.utils.logger import get_logger

logger = get_logger(__name__)


class VoiceControlPanel(QWidget):
    """语音控制面板"""

    # 信号
    speed_changed = pyqtSignal(float)  # 语速变化
    temperature_changed = pyqtSignal(float)  # 温度变化
    top_p_changed = pyqtSignal(float)  # Top-p变化
    top_k_changed = pyqtSignal(int)  # Top-k变化

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()

    def setup_ui(self):
        """设置UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(12)

        # 标题
        title_label = QLabel("语音控制")
        title_font = QFont()
        title_font.setPointSize(10)
        title_font.setBold(True)
        title_label.setFont(title_font)
        layout.addWidget(title_label)

        # 语速控制
        speed_layout = self._create_slider_control(
            "语速",
            min_val=50,  # 0.5x
            max_val=200,  # 2.0x
            default_val=100,  # 1.0x
            suffix="x",
            divisor=100.0,
            callback=self._on_speed_changed,
        )
        layout.addLayout(speed_layout)
        self.speed_slider = speed_layout.itemAt(1).widget()
        self.speed_label = speed_layout.itemAt(2).widget()

        # 音色控制 - 温度
        temp_layout = self._create_slider_control(
            "音色变化",
            min_val=10,  # 0.1
            max_val=200,  # 2.0
            default_val=100,  # 1.0
            suffix="",
            divisor=100.0,
            callback=self._on_temperature_changed,
        )
        layout.addLayout(temp_layout)
        self.temp_slider = temp_layout.itemAt(1).widget()
        self.temp_label = temp_layout.itemAt(2).widget()

        # 音色控制 - Top-p
        top_p_layout = self._create_slider_control(
            "音色稳定性",
            min_val=10,  # 0.1
            max_val=100,  # 1.0
            default_val=100,  # 1.0
            suffix="",
            divisor=100.0,
            callback=self._on_top_p_changed,
        )
        layout.addLayout(top_p_layout)
        self.top_p_slider = top_p_layout.itemAt(1).widget()
        self.top_p_label = top_p_layout.itemAt(2).widget()

        # 音色控制 - Top-k
        top_k_layout = self._create_slider_control(
            "音色多样性",
            min_val=1,
            max_val=20,
            default_val=5,
            suffix="",
            divisor=1.0,
            callback=self._on_top_k_changed,
        )
        layout.addLayout(top_k_layout)
        self.top_k_slider = top_k_layout.itemAt(1).widget()
        self.top_k_label = top_k_layout.itemAt(2).widget()

        # 设置样式
        self.setStyleSheet(
            """
            QWidget {
                background: rgba(0, 0, 0, 0.3);
                border-radius: 12px;
                border: 1px solid rgba(255, 255, 255, 0.1);
            }
            QLabel {
                color: white;
                background: transparent;
                border: none;
            }
            QSlider::groove:horizontal {
                background: rgba(255, 255, 255, 0.1);
                height: 6px;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #FF6B9D, stop:1 #C06C84);
                width: 16px;
                height: 16px;
                margin: -5px 0;
                border-radius: 8px;
            }
            QSlider::handle:horizontal:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #FF8CB4, stop:1 #D07C94);
            }
            QSlider::sub-page:horizontal {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #FF6B9D, stop:1 #C06C84);
                border-radius: 3px;
            }
        """
        )

    def _create_slider_control(
        self, label_text, min_val, max_val, default_val, suffix, divisor, callback
    ):
        """创建滑块控制"""
        layout = QHBoxLayout()
        layout.setSpacing(8)

        # 标签
        label = QLabel(label_text)
        label.setFixedWidth(80)
        layout.addWidget(label)

        # 滑块
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setMinimum(min_val)
        slider.setMaximum(max_val)
        slider.setValue(default_val)
        slider.valueChanged.connect(callback)
        layout.addWidget(slider)

        # 值标签
        value_label = QLabel(f"{default_val / divisor:.1f}{suffix}")
        value_label.setFixedWidth(50)
        value_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(value_label)

        return layout

    def _on_speed_changed(self, value):
        """语速变化"""
        speed = value / 100.0
        self.speed_label.setText(f"{speed:.1f}x")
        self.speed_changed.emit(speed)

    def _on_temperature_changed(self, value):
        """温度变化"""
        temp = value / 100.0
        self.temp_label.setText(f"{temp:.1f}")
        self.temperature_changed.emit(temp)

    def _on_top_p_changed(self, value):
        """Top-p变化"""
        top_p = value / 100.0
        self.top_p_label.setText(f"{top_p:.1f}")
        self.top_p_changed.emit(top_p)

    def _on_top_k_changed(self, value):
        """Top-k变化"""
        self.top_k_label.setText(f"{value}")
        self.top_k_changed.emit(value)

    def set_speed(self, speed: float):
        """设置语速"""
        self.speed_slider.setValue(int(speed * 100))

    def set_temperature(self, temp: float):
        """设置温度"""
        self.temp_slider.setValue(int(temp * 100))

    def set_top_p(self, top_p: float):
        """设置Top-p"""
        self.top_p_slider.setValue(int(top_p * 100))

    def set_top_k(self, top_k: int):
        """设置Top-k"""
        self.top_k_slider.setValue(top_k)
