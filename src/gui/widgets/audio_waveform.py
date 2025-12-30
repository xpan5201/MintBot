"""
音频波形可视化组件 - v2.39.0

实时显示音频播放的波形和音量。

核心功能:
- 实时波形显示
- 音量可视化
- 播放进度指示
- Material Design 3样式
- 真实音频数据处理 (v2.39.0 新增)
"""

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QFrame
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPainter, QColor, QLinearGradient, QFont
import io
import wave
from typing import List

from src.utils.logger import get_logger

logger = get_logger(__name__)


class AudioWaveform(QWidget):
    """音频波形可视化 (v2.38.0)"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(120)

        # 波形数据
        self.waveform_data: List[float] = [0.0] * 50  # 50个采样点
        self.current_volume = 0.0
        self.is_playing = False

        # 更新定时器
        self.update_timer = QTimer(self)
        self.update_timer.timeout.connect(self._update_waveform)
        self.update_timer.setInterval(50)  # 20fps

        self.setup_ui()

    def setup_ui(self):
        """设置UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)

        # 标题
        title_label = QLabel("🎵 音频波形")
        title_font = QFont()
        title_font.setPointSize(10)
        title_font.setBold(True)
        title_label.setFont(title_font)
        layout.addWidget(title_label)

        # 分隔线
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        separator.setStyleSheet("background: rgba(255, 255, 255, 0.1);")
        layout.addWidget(separator)

        # 波形画布
        self.canvas = QWidget()
        self.canvas.setMinimumHeight(60)
        layout.addWidget(self.canvas)

        # 音量标签
        self.volume_label = QLabel("音量: 0%")
        self.volume_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.volume_label.setStyleSheet("color: white; font-size: 9pt;")
        layout.addWidget(self.volume_label)

        # 设置面板样式
        self.setStyleSheet(
            """
            AudioWaveform {
                background: rgba(0, 0, 0, 0.3);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 12px;
            }
        """
        )

    def start(self):
        """开始显示波形 (v2.38.0)"""
        self.is_playing = True
        self.update_timer.start()
        logger.debug("波形显示已启动")

    def stop(self):
        """停止显示波形 (v2.38.0)"""
        self.is_playing = False
        self.update_timer.stop()
        self.waveform_data = [0.0] * 50
        self.current_volume = 0.0
        self.update()
        logger.debug("波形显示已停止")

    def update_audio_data(self, audio_data: bytes):
        """
        更新音频数据 (v2.39.0)

        从WAV格式音频数据中提取振幅信息用于波形显示

        Args:
            audio_data: WAV格式音频数据
        """
        try:
            # 解析WAV数据
            with wave.open(io.BytesIO(audio_data), "rb") as wav_file:
                # 获取参数
                n_channels = wav_file.getnchannels()
                sample_width = wav_file.getsampwidth()
                framerate = wav_file.getframerate()
                n_frames = wav_file.getnframes()

                # 读取音频帧
                frames = wav_file.readframes(n_frames)

                # 转换为整数数组
                import struct

                if sample_width == 2:  # 16-bit
                    # 每个样本2字节
                    sample_count = len(frames) // 2
                    audio_array = struct.unpack(f"{sample_count}h", frames)
                elif sample_width == 1:  # 8-bit
                    audio_array = struct.unpack(f"{len(frames)}B", frames)
                else:
                    logger.warning(f"不支持的样本宽度: {sample_width}")
                    return

                # 如果是立体声，转换为单声道（取平均值）
                if n_channels == 2:
                    mono_array = []
                    for i in range(0, len(audio_array), 2):
                        if i + 1 < len(audio_array):
                            mono_array.append((audio_array[i] + audio_array[i + 1]) / 2)
                    audio_array = mono_array

                # 计算振幅（归一化到0-1）
                max_amplitude = 32768.0 if sample_width == 2 else 128.0
                amplitude = [abs(sample) / max_amplitude for sample in audio_array]

                # 下采样到50个点
                if len(amplitude) > 50:
                    step = len(amplitude) // 50
                    self.waveform_data = [amplitude[i * step] for i in range(50)]
                else:
                    # 如果样本数少于50，填充0
                    self.waveform_data = amplitude + [0.0] * (50 - len(amplitude))

                # 计算平均音量
                if amplitude:
                    self.current_volume = sum(amplitude) / len(amplitude)
                    self.volume_label.setText(f"音量: {int(self.current_volume * 100)}%")

                logger.debug(
                    f"音频数据已更新: {len(audio_array)} samples, {n_channels} channels, {framerate} Hz"
                )

        except Exception as e:
            logger.error(f"音频数据处理失败: {e}")

    def set_volume(self, volume: float):
        """
        设置音量 (v2.38.0)

        Args:
            volume: 音量 (0.0-1.0)
        """
        self.current_volume = max(0.0, min(1.0, volume))
        self.volume_label.setText(f"音量: {int(self.current_volume * 100)}%")

    def _update_waveform(self):
        """
        更新波形数据 (v2.39.0)

        v2.39.0: 不再使用模拟数据，由update_audio_data提供真实数据
        这里只负责刷新显示
        """
        if not self.is_playing:
            return

        # 更新显示
        self.update()

    def paintEvent(self, event):
        """绘制波形 (v2.38.0)"""
        super().paintEvent(event)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 获取画布区域
        canvas_rect = self.canvas.geometry()
        x = canvas_rect.x()
        y = canvas_rect.y()
        width = canvas_rect.width()
        height = canvas_rect.height()

        # 绘制背景
        painter.fillRect(x, y, width, height, QColor(0, 0, 0, 50))

        # 绘制波形
        if len(self.waveform_data) > 0:
            bar_width = width / len(self.waveform_data)

            for i, value in enumerate(self.waveform_data):
                bar_height = value * height * 0.8
                bar_x = x + i * bar_width
                bar_y = y + (height - bar_height) / 2

                # 渐变色
                gradient = QLinearGradient(bar_x, bar_y, bar_x, bar_y + bar_height)
                gradient.setColorAt(0, QColor(255, 107, 157, 200))
                gradient.setColorAt(1, QColor(192, 108, 132, 200))

                painter.fillRect(
                    int(bar_x + 1), int(bar_y), int(bar_width - 2), int(bar_height), gradient
                )
