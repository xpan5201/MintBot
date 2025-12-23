"""
快捷键设置对话框 - v2.42.0

支持用户自定义快捷键绑定
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QMessageBox, QKeySequenceEdit
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QKeySequence
from typing import Dict, Optional

from src.utils.logger import get_logger

logger = get_logger(__name__)


class ShortcutSettingsDialog(QDialog):
    """快捷键设置对话框 (v2.42.0)"""

    # 信号
    shortcuts_changed = pyqtSignal(dict)  # 快捷键变更信号

    # 默认快捷键
    DEFAULT_SHORTCUTS = {
        "tts_toggle": "Ctrl+T",
        "tts_skip": "Ctrl+Shift+S",
        "tts_clear": "Ctrl+Shift+C",
    }

    # 快捷键描述
    SHORTCUT_DESCRIPTIONS = {
        "tts_toggle": "TTS开关",
        "tts_skip": "跳过当前播放",
        "tts_clear": "清空播放队列",
    }

    def __init__(self, current_shortcuts: Optional[Dict[str, str]] = None, parent=None):
        """
        初始化快捷键设置对话框

        Args:
            current_shortcuts: 当前快捷键配置
            parent: 父窗口
        """
        super().__init__(parent)

        self.current_shortcuts = current_shortcuts or self.DEFAULT_SHORTCUTS.copy()
        self.shortcut_editors: Dict[str, QKeySequenceEdit] = {}

        self.setWindowTitle("快捷键设置")
        self.setMinimumSize(600, 400)

        self._init_ui()
        logger.info("快捷键设置对话框已初始化")

    def _init_ui(self):
        """初始化UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # 标题
        title_label = QLabel("⌨️ 快捷键设置")
        title_label.setStyleSheet("""
            QLabel {
                font-size: 18px;
                font-weight: bold;
                color: #FF6B9D;
            }
        """)
        layout.addWidget(title_label)

        # 说明
        info_label = QLabel("点击快捷键输入框，然后按下您想要设置的快捷键组合")
        info_label.setStyleSheet("color: #666; font-size: 12px;")
        layout.addWidget(info_label)

        # 快捷键表格
        self.shortcut_table = QTableWidget()
        self.shortcut_table.setColumnCount(3)
        self.shortcut_table.setHorizontalHeaderLabels([
            "功能", "快捷键", "操作"
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
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)

        # 设置行高
        self.shortcut_table.verticalHeader().setDefaultSectionSize(50)
        self.shortcut_table.verticalHeader().setVisible(False)

        # 加载快捷键
        self._load_shortcuts()

        layout.addWidget(self.shortcut_table)

        # 按钮布局
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        # 重置按钮
        reset_btn = QPushButton("🔄 重置为默认")
        reset_btn.setFixedSize(120, 36)
        reset_btn.setStyleSheet(self._get_button_style("#888"))
        reset_btn.clicked.connect(self._reset_shortcuts)
        button_layout.addWidget(reset_btn)

        # 取消按钮
        cancel_btn = QPushButton("取消")
        cancel_btn.setFixedSize(100, 36)
        cancel_btn.setStyleSheet(self._get_button_style("#888"))
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)

        # 保存按钮
        save_btn = QPushButton("保存")
        save_btn.setFixedSize(100, 36)
        save_btn.setStyleSheet(self._get_button_style("#FF6B9D"))
        save_btn.clicked.connect(self._save_shortcuts)
        button_layout.addWidget(save_btn)

        layout.addLayout(button_layout)

    def _load_shortcuts(self):
        """加载快捷键到表格"""
        self.shortcut_table.setRowCount(len(self.current_shortcuts))

        row = 0
        for key, shortcut in self.current_shortcuts.items():
            # 功能名称
            function_item = QTableWidgetItem(self.SHORTCUT_DESCRIPTIONS.get(key, key))
            function_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            self.shortcut_table.setItem(row, 0, function_item)

            # 快捷键编辑器
            editor = QKeySequenceEdit(QKeySequence(shortcut))
            editor.setStyleSheet("""
                QKeySequenceEdit {
                    padding: 5px;
                    border: 1px solid rgba(255, 107, 157, 0.3);
                    border-radius: 4px;
                    background: white;
                }
                QKeySequenceEdit:focus {
                    border: 2px solid #FF6B9D;
                }
            """)
            self.shortcut_editors[key] = editor
            self.shortcut_table.setCellWidget(row, 1, editor)

            # 重置按钮
            reset_btn = QPushButton("重置")
            reset_btn.setFixedSize(60, 28)
            reset_btn.setStyleSheet("""
                QPushButton {
                    background: #f0f0f0;
                    border: 1px solid #ddd;
                    border-radius: 4px;
                    font-size: 12px;
                }
                QPushButton:hover {
                    background: #e0e0e0;
                }
            """)
            reset_btn.clicked.connect(lambda checked, k=key: self._reset_single_shortcut(k))
            self.shortcut_table.setCellWidget(row, 2, reset_btn)

            row += 1

    def _reset_single_shortcut(self, key: str):
        """重置单个快捷键"""
        if key in self.DEFAULT_SHORTCUTS:
            default_shortcut = self.DEFAULT_SHORTCUTS[key]
            self.shortcut_editors[key].setKeySequence(QKeySequence(default_shortcut))
            logger.info(f"重置快捷键: {key} -> {default_shortcut}")

    def _reset_shortcuts(self):
        """重置所有快捷键为默认值"""
        reply = QMessageBox.question(
            self,
            "确认重置",
            "确定要将所有快捷键重置为默认值吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            for key, default_shortcut in self.DEFAULT_SHORTCUTS.items():
                if key in self.shortcut_editors:
                    self.shortcut_editors[key].setKeySequence(QKeySequence(default_shortcut))
            logger.info("所有快捷键已重置为默认值")

    def _check_conflicts(self) -> Optional[str]:
        """
        检查快捷键冲突

        Returns:
            str: 冲突信息，如果没有冲突则返回None
        """
        shortcuts_map = {}

        for key, editor in self.shortcut_editors.items():
            sequence = editor.keySequence().toString()
            if not sequence:
                continue

            if sequence in shortcuts_map:
                conflict_key = shortcuts_map[sequence]
                return f"快捷键冲突: '{self.SHORTCUT_DESCRIPTIONS[key]}' 和 '{self.SHORTCUT_DESCRIPTIONS[conflict_key]}' 都使用了 '{sequence}'"

            shortcuts_map[sequence] = key

        return None

    def _save_shortcuts(self):
        """保存快捷键设置"""
        # 检查冲突
        conflict = self._check_conflicts()
        if conflict:
            QMessageBox.warning(self, "快捷键冲突", conflict)
            return

        # 收集新的快捷键
        new_shortcuts = {}
        for key, editor in self.shortcut_editors.items():
            sequence = editor.keySequence().toString()
            if sequence:
                new_shortcuts[key] = sequence
            else:
                # 如果为空，使用默认值
                new_shortcuts[key] = self.DEFAULT_SHORTCUTS.get(key, "")

        # 发送信号
        self.shortcuts_changed.emit(new_shortcuts)

        logger.info(f"快捷键设置已保存: {new_shortcuts}")
        self.accept()

    def _get_button_style(self, color: str) -> str:
        """获取按钮样式"""
        if color == "#FF6B9D":
            return """
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
            """
        else:
            return """
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
            """
