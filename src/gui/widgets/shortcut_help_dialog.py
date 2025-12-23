"""
快捷键帮助对话框 - v2.41.0

显示所有可用的快捷键及其说明
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView
)
from PyQt6.QtCore import Qt, pyqtSignal

from src.utils.logger import get_logger

logger = get_logger(__name__)


class ShortcutHelpDialog(QDialog):
    """快捷键帮助对话框 (v2.42.0: 增加设置按钮)"""

    # 信号
    settings_requested = pyqtSignal()  # v2.42.0: 请求打开设置

    def __init__(self, parent=None):
        """
        初始化快捷键帮助对话框

        Args:
            parent: 父窗口
        """
        super().__init__(parent)

        self.setWindowTitle("快捷键帮助")
        self.setMinimumSize(600, 400)

        self._init_ui()
        logger.info("快捷键帮助对话框已初始化")
    
    def _init_ui(self):
        """初始化UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        # 标题
        title_label = QLabel("⌨️ 快捷键帮助")
        title_label.setStyleSheet("""
            QLabel {
                font-size: 18px;
                font-weight: bold;
                color: #FF6B9D;
            }
        """)
        layout.addWidget(title_label)
        
        # 快捷键表格
        self.shortcut_table = QTableWidget()
        self.shortcut_table.setColumnCount(3)
        self.shortcut_table.setHorizontalHeaderLabels([
            "功能", "快捷键", "说明"
        ])
        
        # 设置表格样式
        self.shortcut_table.setStyleSheet("""
            QTableWidget {
                border: 2px solid rgba(255, 107, 157, 0.3);
                border-radius: 12px;
                background: rgba(255, 255, 255, 0.95);
                gridline-color: rgba(255, 107, 157, 0.2);
            }
            QTableWidget::item {
                padding: 8px;
                border-bottom: 1px solid rgba(255, 107, 157, 0.1);
            }
            QHeaderView::section {
                background: qlineargradient(
                    x1:0, y1:0, x2:0, y2:1,
                    stop:0 #FF6B9D, stop:1 #C06C84
                );
                color: white;
                padding: 8px;
                border: none;
                font-weight: bold;
                font-size: 13px;
            }
        """)
        
        # 设置列宽
        header = self.shortcut_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        
        # 设置行高
        self.shortcut_table.verticalHeader().setDefaultSectionSize(40)
        self.shortcut_table.verticalHeader().setVisible(False)
        
        # 禁用编辑
        self.shortcut_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        
        # 添加快捷键数据
        self._load_shortcuts()
        
        layout.addWidget(self.shortcut_table)
        
        # 按钮布局
        button_layout = QHBoxLayout()

        # v2.42.0: 设置按钮
        settings_btn = QPushButton("⚙️ 自定义快捷键")
        settings_btn.setFixedSize(140, 36)
        settings_btn.setStyleSheet("""
            QPushButton {
                background: #f0f0f0;
                color: #333;
                border: 1px solid #ddd;
                border-radius: 8px;
                font-size: 14px;
            }
            QPushButton:hover {
                background: #e0e0e0;
            }
            QPushButton:pressed {
                background: #d0d0d0;
            }
        """)
        settings_btn.clicked.connect(self._on_settings_clicked)
        button_layout.addWidget(settings_btn)

        button_layout.addStretch()

        close_btn = QPushButton("关闭")
        close_btn.setFixedSize(100, 36)
        close_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(
                    x1:0, y1:0, x2:0, y2:1,
                    stop:0 #FF6B9D, stop:1 #C06C84
                );
                color: white;
                border: none;
                border-radius: 8px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: qlineargradient(
                    x1:0, y1:0, x2:0, y2:1,
                    stop:0 #C06C84, stop:1 #FF6B9D
                );
            }
            QPushButton:pressed {
                background: #A05A6C;
            }
        """)
        close_btn.clicked.connect(self.accept)
        button_layout.addWidget(close_btn)

        layout.addLayout(button_layout)

    def _on_settings_clicked(self):
        """设置按钮点击 (v2.42.0)"""
        self.settings_requested.emit()
        self.accept()  # 关闭帮助对话框
    
    def _load_shortcuts(self):
        """加载快捷键数据"""
        shortcuts = [
            ("TTS开关", "Ctrl+T", "快速启用/禁用TTS语音播报"),
            ("跳过播放", "Ctrl+Shift+S", "跳过当前正在播放的音频"),
            ("清空队列", "Ctrl+Shift+C", "清空TTS播放队列"),
            ("发送消息", "Enter", "发送当前输入的消息"),
            ("换行", "Shift+Enter", "在输入框中插入换行符"),
            ("清空输入", "Ctrl+L", "清空输入框内容"),
        ]
        
        self.shortcut_table.setRowCount(len(shortcuts))
        
        for row, (function, shortcut, description) in enumerate(shortcuts):
            # 功能
            function_item = QTableWidgetItem(function)
            function_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            self.shortcut_table.setItem(row, 0, function_item)
            
            # 快捷键
            shortcut_item = QTableWidgetItem(shortcut)
            shortcut_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            shortcut_item.setForeground(Qt.GlobalColor.darkBlue)
            self.shortcut_table.setItem(row, 1, shortcut_item)
            
            # 说明
            description_item = QTableWidgetItem(description)
            description_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            self.shortcut_table.setItem(row, 2, description_item)
