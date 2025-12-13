"""
TTS状态面板组件 - v2.36.0

显示TTS队列状态和播放进度
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QProgressBar, QPushButton, QFrame
)
from PyQt6.QtCore import Qt, pyqtSlot
from PyQt6.QtGui import QFont

from src.utils.logger import get_logger

logger = get_logger(__name__)


class TTSStatusPanel(QWidget):
    """TTS状态显示面板 (v2.36.0)"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
        
    def setup_ui(self):
        """设置UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)
        
        # 标题
        title_label = QLabel("🎤 TTS状态")
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
        
        # 播放进度区域
        progress_layout = QVBoxLayout()
        progress_layout.setSpacing(4)
        
        # 进度标签
        self.progress_label = QLabel("播放进度: 0s / 0s")
        self.progress_label.setStyleSheet("color: rgba(255, 255, 255, 0.7); font-size: 9pt;")
        progress_layout.addWidget(self.progress_label)
        
        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("%p%")
        self.progress_bar.setFixedHeight(20)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid rgba(255, 255, 255, 0.2);
                border-radius: 10px;
                background: rgba(0, 0, 0, 0.3);
                text-align: center;
                color: white;
                font-size: 9pt;
            }
            QProgressBar::chunk {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 #FF6B9D, stop:1 #C06C84
                );
                border-radius: 9px;
            }
        """)
        progress_layout.addWidget(self.progress_bar)
        
        layout.addLayout(progress_layout)
        
        # 队列信息区域
        queue_layout = QHBoxLayout()
        queue_layout.setSpacing(8)
        
        # 队列大小标签
        self.queue_label = QLabel("队列: 0/10")
        self.queue_label.setStyleSheet("color: rgba(255, 255, 255, 0.7); font-size: 9pt;")
        queue_layout.addWidget(self.queue_label)
        
        queue_layout.addStretch()
        
        # 跳过按钮
        self.skip_btn = QPushButton("⏭ 跳过")
        self.skip_btn.setFixedSize(60, 24)
        self.skip_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.skip_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 107, 157, 0.2);
                border: 1px solid rgba(255, 107, 157, 0.3);
                border-radius: 12px;
                color: white;
                font-size: 9pt;
                padding: 2px 8px;
            }
            QPushButton:hover {
                background: rgba(255, 107, 157, 0.3);
                border: 1px solid rgba(255, 107, 157, 0.5);
            }
            QPushButton:pressed {
                background: rgba(255, 107, 157, 0.4);
            }
            QPushButton:disabled {
                background: rgba(128, 128, 128, 0.2);
                border: 1px solid rgba(128, 128, 128, 0.3);
                color: rgba(255, 255, 255, 0.3);
            }
        """)
        queue_layout.addWidget(self.skip_btn)
        
        layout.addLayout(queue_layout)
        
        # 设置面板样式
        self.setStyleSheet("""
            TTSStatusPanel {
                background: rgba(0, 0, 0, 0.3);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 12px;
            }
        """)
        
        # 初始状态：禁用跳过按钮
        self.skip_btn.setEnabled(False)
    
    @pyqtSlot(int, int)
    def update_progress(self, position: int, duration: int):
        """
        更新播放进度
        
        Args:
            position: 当前位置(ms)
            duration: 总时长(ms)
        """
        if duration > 0:
            progress = int((position / duration) * 100)
            self.progress_bar.setValue(progress)
            
            # 更新时间标签
            pos_sec = position // 1000
            dur_sec = duration // 1000
            self.progress_label.setText(f"播放进度: {pos_sec}s / {dur_sec}s")
            
            # 启用跳过按钮
            self.skip_btn.setEnabled(True)
        else:
            self.progress_bar.setValue(0)
            self.progress_label.setText("播放进度: 0s / 0s")
            self.skip_btn.setEnabled(False)
    
    @pyqtSlot(int, int)
    def update_queue_size(self, size: int, max_size: int):
        """
        更新队列大小
        
        Args:
            size: 当前队列大小
            max_size: 最大队列大小
        """
        self.queue_label.setText(f"队列: {size}/{max_size}")
        
        # 如果队列为空且没有播放，禁用跳过按钮
        if size == 0 and self.progress_bar.value() == 0:
            self.skip_btn.setEnabled(False)

