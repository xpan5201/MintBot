"""
TTS历史记录面板 - v2.40.0

显示TTS合成历史记录，支持：
- 历史记录列表
- 重新播放
- 导出音频
- 搜索和过滤
- 删除记录
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QLineEdit, QHeaderView,
    QMessageBox, QFileDialog, QComboBox, QDateEdit
)
from PyQt6.QtCore import Qt, pyqtSignal, QDate
from PyQt6.QtGui import QIcon
from typing import Optional, List, Dict, Any
from datetime import datetime

from src.utils.logger import get_logger

logger = get_logger(__name__)


class TTSHistoryPanel(QWidget):
    """TTS历史记录面板 (v2.40.0)"""
    
    # 信号
    replay_requested = pyqtSignal(int)  # 重新播放请求 (record_id)
    export_requested = pyqtSignal(list)  # 导出请求 (record_ids)
    filter_changed = pyqtSignal()  # 筛选条件变化 (v2.41.0)
    
    def __init__(self, parent=None):
        """
        初始化TTS历史记录面板
        
        Args:
            parent: 父窗口
        """
        super().__init__(parent)
        
        self._init_ui()
        logger.info("TTS历史记录面板已初始化")
    
    def _init_ui(self):
        """初始化UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)
        
        # 标题和搜索栏
        header_layout = QHBoxLayout()
        
        title_label = QLabel("📜 TTS历史记录")
        title_label.setStyleSheet("""
            QLabel {
                font-size: 16px;
                font-weight: bold;
                color: #FF6B9D;
            }
        """)
        header_layout.addWidget(title_label)
        
        header_layout.addStretch()
        
        # 搜索框
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍 搜索文本...")
        self.search_input.setFixedWidth(200)
        self.search_input.setStyleSheet("""
            QLineEdit {
                padding: 6px 12px;
                border: 2px solid rgba(255, 107, 157, 0.3);
                border-radius: 8px;
                background: rgba(255, 255, 255, 0.9);
                font-size: 13px;
            }
            QLineEdit:focus {
                border-color: #FF6B9D;
                background: white;
            }
        """)
        self.search_input.textChanged.connect(self._on_search)
        header_layout.addWidget(self.search_input)

        layout.addLayout(header_layout)

        # v2.41.0: 筛选控件
        filter_layout = QHBoxLayout()
        filter_layout.setSpacing(10)

        # 日期范围筛选
        date_label = QLabel("📅 日期范围:")
        date_label.setStyleSheet("font-size: 13px; color: #666;")
        filter_layout.addWidget(date_label)

        self.start_date_edit = QDateEdit()
        self.start_date_edit.setCalendarPopup(True)
        self.start_date_edit.setDate(QDate.currentDate().addDays(-30))  # 默认最近30天
        self.start_date_edit.setDisplayFormat("yyyy-MM-dd")
        self.start_date_edit.setFixedWidth(120)
        self.start_date_edit.setStyleSheet("""
            QDateEdit {
                padding: 4px 8px;
                border: 2px solid rgba(255, 107, 157, 0.3);
                border-radius: 6px;
                background: rgba(255, 255, 255, 0.9);
                font-size: 12px;
            }
            QDateEdit:focus {
                border-color: #FF6B9D;
            }
        """)
        self.start_date_edit.dateChanged.connect(self._on_filter_changed)
        filter_layout.addWidget(self.start_date_edit)

        filter_layout.addWidget(QLabel("至"))

        self.end_date_edit = QDateEdit()
        self.end_date_edit.setCalendarPopup(True)
        self.end_date_edit.setDate(QDate.currentDate())
        self.end_date_edit.setDisplayFormat("yyyy-MM-dd")
        self.end_date_edit.setFixedWidth(120)
        self.end_date_edit.setStyleSheet("""
            QDateEdit {
                padding: 4px 8px;
                border: 2px solid rgba(255, 107, 157, 0.3);
                border-radius: 6px;
                background: rgba(255, 255, 255, 0.9);
                font-size: 12px;
            }
            QDateEdit:focus {
                border-color: #FF6B9D;
            }
        """)
        self.end_date_edit.dateChanged.connect(self._on_filter_changed)
        filter_layout.addWidget(self.end_date_edit)

        filter_layout.addSpacing(20)

        # 参考音频筛选
        ref_audio_label = QLabel("🎤 参考音频:")
        ref_audio_label.setStyleSheet("font-size: 13px; color: #666;")
        filter_layout.addWidget(ref_audio_label)

        self.ref_audio_combo = QComboBox()
        self.ref_audio_combo.addItem("全部", None)
        self.ref_audio_combo.setFixedWidth(150)
        self.ref_audio_combo.setStyleSheet("""
            QComboBox {
                padding: 4px 8px;
                border: 2px solid rgba(255, 107, 157, 0.3);
                border-radius: 6px;
                background: rgba(255, 255, 255, 0.9);
                font-size: 12px;
            }
            QComboBox:focus {
                border-color: #FF6B9D;
            }
            QComboBox::drop-down {
                border: none;
            }
            QComboBox::down-arrow {
                image: url(none);
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 6px solid #FF6B9D;
                margin-right: 8px;
            }
        """)
        self.ref_audio_combo.currentIndexChanged.connect(self._on_filter_changed)
        filter_layout.addWidget(self.ref_audio_combo)

        filter_layout.addSpacing(20)

        # 情感筛选
        emotion_label = QLabel("😊 情感:")
        emotion_label.setStyleSheet("font-size: 13px; color: #666;")
        filter_layout.addWidget(emotion_label)

        self.emotion_combo = QComboBox()
        self.emotion_combo.addItem("全部", None)
        self.emotion_combo.setFixedWidth(120)
        self.emotion_combo.setStyleSheet("""
            QComboBox {
                padding: 4px 8px;
                border: 2px solid rgba(255, 107, 157, 0.3);
                border-radius: 6px;
                background: rgba(255, 255, 255, 0.9);
                font-size: 12px;
            }
            QComboBox:focus {
                border-color: #FF6B9D;
            }
            QComboBox::drop-down {
                border: none;
            }
            QComboBox::down-arrow {
                image: url(none);
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 6px solid #FF6B9D;
                margin-right: 8px;
            }
        """)
        self.emotion_combo.currentIndexChanged.connect(self._on_filter_changed)
        filter_layout.addWidget(self.emotion_combo)

        filter_layout.addStretch()

        # 重置筛选按钮
        reset_filter_btn = QPushButton("🔄 重置筛选")
        reset_filter_btn.setFixedSize(100, 30)
        reset_filter_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(
                    x1:0, y1:0, x2:0, y2:1,
                    stop:0 #FFA07A, stop:1 #FF8C69
                );
                color: white;
                border: none;
                border-radius: 6px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: qlineargradient(
                    x1:0, y1:0, x2:0, y2:1,
                    stop:0 #FF8C69, stop:1 #FFA07A
                );
            }
            QPushButton:pressed {
                background: #FF7F50;
            }
        """)
        reset_filter_btn.clicked.connect(self._on_reset_filter)
        filter_layout.addWidget(reset_filter_btn)

        layout.addLayout(filter_layout)

        # 历史记录表格
        self.history_table = QTableWidget()
        self.history_table.setColumnCount(6)
        self.history_table.setHorizontalHeaderLabels([
            "时间", "文本", "参考音频", "情感", "时长", "操作"
        ])
        
        # 设置表格样式
        self.history_table.setStyleSheet("""
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
            QTableWidget::item:selected {
                background: rgba(255, 107, 157, 0.2);
                color: #333;
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
        header = self.history_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)  # 时间
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)  # 文本
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)  # 参考音频
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)  # 情感
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)  # 时长
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)  # 操作
        self.history_table.setColumnWidth(5, 150)
        
        # 设置行高
        self.history_table.verticalHeader().setDefaultSectionSize(50)
        self.history_table.verticalHeader().setVisible(False)
        
        # 设置选择模式
        self.history_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.history_table.setSelectionMode(QTableWidget.SelectionMode.MultiSelection)
        
        layout.addWidget(self.history_table)
        
        # 底部按钮栏
        button_layout = QHBoxLayout()

        # 刷新按钮
        self.refresh_btn = QPushButton("🔄 刷新")
        self.refresh_btn.setFixedSize(100, 36)
        self.refresh_btn.clicked.connect(self.refresh)
        self._style_button(self.refresh_btn, "#4CAF50")
        button_layout.addWidget(self.refresh_btn)

        # 导出选中按钮
        self.export_selected_btn = QPushButton("📤 导出选中")
        self.export_selected_btn.setFixedSize(120, 36)
        self.export_selected_btn.clicked.connect(self._on_export_selected)
        self._style_button(self.export_selected_btn, "#2196F3")
        button_layout.addWidget(self.export_selected_btn)

        # 删除选中按钮
        self.delete_selected_btn = QPushButton("🗑 删除选中")
        self.delete_selected_btn.setFixedSize(120, 36)
        self.delete_selected_btn.clicked.connect(self._on_delete_selected)
        self._style_button(self.delete_selected_btn, "#F44336")
        button_layout.addWidget(self.delete_selected_btn)

        button_layout.addStretch()

        # 清空全部按钮
        self.clear_all_btn = QPushButton("🗑 清空全部")
        self.clear_all_btn.setFixedSize(120, 36)
        self.clear_all_btn.clicked.connect(self._on_clear_all)
        self._style_button(self.clear_all_btn, "#9E9E9E")
        button_layout.addWidget(self.clear_all_btn)

        layout.addLayout(button_layout)

        # 统计信息
        self.stats_label = QLabel()
        self.stats_label.setStyleSheet("""
            QLabel {
                color: #666;
                font-size: 12px;
                padding: 5px;
            }
        """)
        layout.addWidget(self.stats_label)

    def _style_button(self, button: QPushButton, color: str):
        """
        设置按钮样式

        Args:
            button: 按钮
            color: 主题颜色
        """
        button.setStyleSheet(f"""
            QPushButton {{
                background: {color};
                color: white;
                border: none;
                border-radius: 8px;
                font-size: 13px;
                font-weight: bold;
                padding: 8px 16px;
            }}
            QPushButton:hover {{
                background: qlineargradient(
                    x1:0, y1:0, x2:0, y2:1,
                    stop:0 {color}, stop:1 rgba(0, 0, 0, 0.1)
                );
            }}
            QPushButton:pressed {{
                background: rgba(0, 0, 0, 0.2);
            }}
            QPushButton:disabled {{
                background: #CCCCCC;
                color: #999999;
            }}
        """)

    def load_history(self, records: List[Dict[str, Any]]):
        """
        加载历史记录

        Args:
            records: 历史记录列表
        """
        self.history_table.setRowCount(0)

        for record in records:
            row = self.history_table.rowCount()
            self.history_table.insertRow(row)

            # 时间
            created_at = record.get('created_at', '')
            if created_at:
                try:
                    dt = datetime.fromisoformat(created_at)
                    time_str = dt.strftime('%m-%d %H:%M')
                except:
                    time_str = created_at[:16]
            else:
                time_str = ''

            time_item = QTableWidgetItem(time_str)
            time_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.history_table.setItem(row, 0, time_item)

            # 文本（截断显示）
            text = record.get('text', '')
            text_preview = text[:50] + '...' if len(text) > 50 else text
            text_item = QTableWidgetItem(text_preview)
            text_item.setToolTip(text)  # 完整文本作为提示
            self.history_table.setItem(row, 1, text_item)

            # 参考音频
            ref_audio = record.get('ref_audio_name', '')
            ref_item = QTableWidgetItem(ref_audio)
            ref_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.history_table.setItem(row, 2, ref_item)

            # 情感
            emotion = record.get('ref_audio_emotion', '')
            emotion_item = QTableWidgetItem(emotion)
            emotion_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.history_table.setItem(row, 3, emotion_item)

            # 时长
            duration = record.get('duration', 0.0)
            duration_str = f"{duration:.1f}s" if duration else ''
            duration_item = QTableWidgetItem(duration_str)
            duration_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.history_table.setItem(row, 4, duration_item)

            # 操作按钮
            action_widget = QWidget()
            action_layout = QHBoxLayout(action_widget)
            action_layout.setContentsMargins(5, 5, 5, 5)
            action_layout.setSpacing(5)

            # 播放按钮
            replay_btn = QPushButton("▶️")
            replay_btn.setFixedSize(30, 30)
            replay_btn.setToolTip("重新播放")
            replay_btn.clicked.connect(lambda checked, r=record: self._on_replay(r))
            self._style_button(replay_btn, "#4CAF50")
            action_layout.addWidget(replay_btn)

            # 导出按钮
            export_btn = QPushButton("📤")
            export_btn.setFixedSize(30, 30)
            export_btn.setToolTip("导出音频")
            export_btn.clicked.connect(lambda checked, r=record: self._on_export_single(r))
            self._style_button(export_btn, "#2196F3")
            action_layout.addWidget(export_btn)

            # 删除按钮
            delete_btn = QPushButton("🗑")
            delete_btn.setFixedSize(30, 30)
            delete_btn.setToolTip("删除记录")
            delete_btn.clicked.connect(lambda checked, r=record: self._on_delete_single(r))
            self._style_button(delete_btn, "#F44336")
            action_layout.addWidget(delete_btn)

            self.history_table.setCellWidget(row, 5, action_widget)

            # 存储record_id到item的data中
            time_item.setData(Qt.ItemDataRole.UserRole, record.get('id'))

        logger.debug(f"加载历史记录: {len(records)}条")

    def update_statistics(self, stats: Dict[str, Any]):
        """
        更新统计信息

        Args:
            stats: 统计信息
        """
        total_count = stats.get('total_count', 0)
        total_duration = stats.get('total_duration', 0.0)
        today_count = stats.get('today_count', 0)

        # 格式化时长
        hours = int(total_duration // 3600)
        minutes = int((total_duration % 3600) // 60)
        seconds = int(total_duration % 60)

        if hours > 0:
            duration_str = f"{hours}小时{minutes}分钟"
        elif minutes > 0:
            duration_str = f"{minutes}分钟{seconds}秒"
        else:
            duration_str = f"{seconds}秒"

        self.stats_label.setText(
            f"总记录: {total_count}条 | 总时长: {duration_str} | 今日: {today_count}条"
        )

    def refresh(self):
        """刷新历史记录"""
        # 由父窗口处理刷新逻辑
        logger.debug("刷新历史记录")

    def _on_search(self, text: str):
        """
        搜索文本变化

        Args:
            text: 搜索文本
        """
        # 由父窗口处理搜索逻辑
        logger.debug(f"搜索: {text}")

    def _on_replay(self, record: Dict[str, Any]):
        """
        重新播放

        Args:
            record: 历史记录
        """
        record_id = record.get('id')
        if record_id:
            self.replay_requested.emit(record_id)
            logger.debug(f"请求重新播放: ID={record_id}")

    def _on_export_single(self, record: Dict[str, Any]):
        """
        导出单个音频

        Args:
            record: 历史记录
        """
        record_id = record.get('id')
        if record_id:
            self.export_requested.emit([record_id])
            logger.debug(f"请求导出: ID={record_id}")

    def _on_delete_single(self, record: Dict[str, Any]):
        """
        删除单个记录

        Args:
            record: 历史记录
        """
        record_id = record.get('id')
        if record_id:
            reply = QMessageBox.question(
                self,
                "确认删除",
                "确定要删除这条历史记录吗？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )

            if reply == QMessageBox.StandardButton.Yes:
                # 由父窗口处理删除逻辑
                logger.debug(f"删除记录: ID={record_id}")

    def _on_export_selected(self):
        """导出选中的记录"""
        selected_rows = self.history_table.selectionModel().selectedRows()
        if not selected_rows:
            QMessageBox.warning(self, "提示", "请先选择要导出的记录")
            return

        record_ids = []
        for index in selected_rows:
            row = index.row()
            item = self.history_table.item(row, 0)
            if item:
                record_id = item.data(Qt.ItemDataRole.UserRole)
                if record_id:
                    record_ids.append(record_id)

        if record_ids:
            self.export_requested.emit(record_ids)
            logger.debug(f"请求导出选中: {len(record_ids)}条")

    def _on_delete_selected(self):
        """删除选中的记录"""
        selected_rows = self.history_table.selectionModel().selectedRows()
        if not selected_rows:
            QMessageBox.warning(self, "提示", "请先选择要删除的记录")
            return

        reply = QMessageBox.question(
            self,
            "确认删除",
            f"确定要删除选中的 {len(selected_rows)} 条记录吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            # 由父窗口处理删除逻辑
            logger.debug(f"删除选中: {len(selected_rows)}条")

    def _on_clear_all(self):
        """清空全部记录"""
        reply = QMessageBox.question(
            self,
            "确认清空",
            "确定要清空所有历史记录吗？此操作不可恢复！",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            # 由父窗口处理清空逻辑
            logger.debug("清空全部历史记录")

    def _on_filter_changed(self):
        """筛选条件变化 (v2.41.0)"""
        logger.debug("筛选条件已变化")
        self.filter_changed.emit()

    def _on_reset_filter(self):
        """重置筛选条件 (v2.41.0)"""
        self.start_date_edit.setDate(QDate.currentDate().addDays(-30))
        self.end_date_edit.setDate(QDate.currentDate())
        self.ref_audio_combo.setCurrentIndex(0)
        self.emotion_combo.setCurrentIndex(0)
        logger.debug("筛选条件已重置")

    def update_filter_options(self, ref_audio_names: List[str], emotions: List[str]):
        """
        更新筛选选项 (v2.41.0, v2.45.2: 修复递归问题)

        Args:
            ref_audio_names: 参考音频名称列表
            emotions: 情感标签列表
        """
        # v2.45.2: 临时阻塞信号，防止触发递归
        self.ref_audio_combo.blockSignals(True)
        self.emotion_combo.blockSignals(True)

        try:
            # 更新参考音频下拉框
            current_ref = self.ref_audio_combo.currentData()
            self.ref_audio_combo.clear()
            self.ref_audio_combo.addItem("全部", None)
            for name in ref_audio_names:
                self.ref_audio_combo.addItem(name, name)

            # 恢复之前的选择
            if current_ref:
                index = self.ref_audio_combo.findData(current_ref)
                if index >= 0:
                    self.ref_audio_combo.setCurrentIndex(index)

            # 更新情感下拉框
            current_emotion = self.emotion_combo.currentData()
            self.emotion_combo.clear()
            self.emotion_combo.addItem("全部", None)
            for emotion in emotions:
                self.emotion_combo.addItem(emotion, emotion)

            # 恢复之前的选择
            if current_emotion:
                index = self.emotion_combo.findData(current_emotion)
                if index >= 0:
                    self.emotion_combo.setCurrentIndex(index)

            logger.debug(f"更新筛选选项: {len(ref_audio_names)}个音频, {len(emotions)}个情感")

        finally:
            # v2.45.2: 恢复信号
            self.ref_audio_combo.blockSignals(False)
            self.emotion_combo.blockSignals(False)

    def get_filter_params(self) -> Dict[str, Any]:
        """
        获取当前筛选参数 (v2.41.0)

        Returns:
            Dict: 筛选参数
        """
        start_date = self.start_date_edit.date().toPyDate()
        end_date = self.end_date_edit.date().toPyDate()
        ref_audio = self.ref_audio_combo.currentData()
        emotion = self.emotion_combo.currentData()

        return {
            'start_date': datetime.combine(start_date, datetime.min.time()),
            'end_date': datetime.combine(end_date, datetime.max.time()),
            'ref_audio_name': ref_audio,
            'ref_audio_emotion': emotion
        }


