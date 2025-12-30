"""
记忆管理界面 (v2.30.32)

提供记忆查看、筛选、编辑和删除功能
支持按情感、主题、重要性、人物、地点、事件筛选
"""

from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QComboBox,
    QLineEdit,
    QTextEdit,
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QMessageBox,
    QDoubleSpinBox,
    QGroupBox,
    QFormLayout,
    QScrollArea,
    QSplitter,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from datetime import datetime
from typing import Dict, Any
import json

from src.utils.logger import get_logger
from .material_design_light import MD3_LIGHT_COLORS

logger = get_logger(__name__)


class MemoryDetailDialog(QDialog):
    """记忆详情对话框"""

    def __init__(self, memory: Dict[str, Any], parent=None):
        super().__init__(parent)
        self.memory = memory
        self.setWindowTitle("记忆详情")
        self.setMinimumSize(600, 500)
        self.setup_ui()

    def setup_ui(self):
        """设置 UI"""
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 24, 24, 24)

        # 标题
        title = QLabel("📝 记忆详情")
        title.setFont(QFont("Microsoft YaHei UI", 16, QFont.Weight.Bold))
        layout.addWidget(title)

        # 滚动区域
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(
            """
            QScrollArea {{
                border: none;
                background: transparent;
            }}
        """
        )

        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setSpacing(12)

        # 基本信息
        info_group = QGroupBox("基本信息")
        info_layout = QFormLayout()
        info_layout.setSpacing(8)

        # 时间
        timestamp = self.memory.get("timestamp", "")
        if timestamp:
            dt = datetime.fromisoformat(timestamp)
            time_label = QLabel(dt.strftime("%Y-%m-%d %H:%M:%S"))
            info_layout.addRow("时间:", time_label)

        # 情感
        emotion = self.memory.get("emotion", "neutral")
        emotion_map = {
            "happy": "😊 开心",
            "sad": "😢 难过",
            "angry": "😠 生气",
            "anxious": "😰 焦虑",
            "excited": "🤩 兴奋",
            "neutral": "😐 中性",
        }
        emotion_label = QLabel(emotion_map.get(emotion, emotion))
        info_layout.addRow("情感:", emotion_label)

        # 主题
        topic = self.memory.get("topic", "other")
        topic_map = {
            "work": "💼 工作",
            "life": "🏠 生活",
            "study": "📖 学习",
            "entertainment": "🎮 娱乐",
            "health": "💪 健康",
            "relationship": "👥 人际关系",
            "other": "📝 其他",
        }
        topic_label = QLabel(topic_map.get(topic, topic))
        info_layout.addRow("主题:", topic_label)

        # 重要性
        importance = self.memory.get("importance", 0.0)
        importance_label = QLabel(f"{importance:.2f}")
        info_layout.addRow("重要性:", importance_label)

        info_group.setLayout(info_layout)
        content_layout.addWidget(info_group)

        # 元数据（v2.30.32 新增）
        metadata_group = QGroupBox("元数据")
        metadata_layout = QFormLayout()
        metadata_layout.setSpacing(8)

        # 人物
        people = self.memory.get("people", [])
        if people:
            people_label = QLabel(", ".join(people))
            metadata_layout.addRow("人物:", people_label)

        # 地点
        location = self.memory.get("location")
        if location:
            location_label = QLabel(location)
            metadata_layout.addRow("地点:", location_label)

        # 时间信息
        time_info = self.memory.get("time_info")
        if time_info:
            time_info_label = QLabel(time_info)
            metadata_layout.addRow("时间信息:", time_info_label)

        # 事件
        event = self.memory.get("event")
        if event:
            event_label = QLabel(event)
            metadata_layout.addRow("事件:", event_label)

        metadata_group.setLayout(metadata_layout)
        content_layout.addWidget(metadata_group)

        # 内容
        content_group = QGroupBox("内容")
        content_text = QTextEdit()
        content_text.setPlainText(self.memory.get("content", ""))
        content_text.setReadOnly(True)
        content_text.setMinimumHeight(200)
        content_text.setStyleSheet(
            f"""
            QTextEdit {{
                border: 1px solid {MD3_LIGHT_COLORS['outline']};
                border-radius: 8px;
                padding: 12px;
                background: {MD3_LIGHT_COLORS['surface']};
                color: {MD3_LIGHT_COLORS['on_surface']};
                font-size: 14px;
                line-height: 1.6;
            }}
        """
        )
        content_group_layout = QVBoxLayout()
        content_group_layout.addWidget(content_text)
        content_group.setLayout(content_group_layout)
        content_layout.addWidget(content_group)

        scroll.setWidget(content_widget)
        layout.addWidget(scroll)

        # 按钮
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        button_box.accepted.connect(self.accept)
        layout.addWidget(button_box)


class MemoryManagerWidget(QWidget):
    """记忆管理主界面"""

    memory_deleted = pyqtSignal(str)  # 记忆被删除信号（传递时间戳）
    memory_updated = pyqtSignal(dict)  # 记忆被更新信号

    def __init__(self, agent=None, parent=None):
        super().__init__(parent)
        self.agent = agent
        self.current_memories = []  # 当前显示的记忆列表
        self.setup_ui()
        self.load_memories()

    def setup_ui(self):
        """设置 UI"""
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 24, 24, 24)

        # 标题
        title = QLabel("🧠 记忆管理")
        title.setFont(QFont("Microsoft YaHei UI", 18, QFont.Weight.Bold))
        layout.addWidget(title)

        # 筛选区域
        filter_group = self._create_filter_group()
        layout.addWidget(filter_group)

        # 分隔器
        splitter = QSplitter(Qt.Orientation.Vertical)

        # 记忆列表
        self.memory_table = self._create_memory_table()
        splitter.addWidget(self.memory_table)

        # 统计信息
        stats_widget = self._create_stats_widget()
        splitter.addWidget(stats_widget)

        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter)

        # 操作按钮
        button_layout = self._create_button_layout()
        layout.addLayout(button_layout)

    def _create_filter_group(self) -> QGroupBox:
        """创建筛选区域"""
        group = QGroupBox("筛选条件")
        layout = QHBoxLayout()
        layout.setSpacing(12)

        # 情感筛选
        emotion_label = QLabel("情感:")
        self.emotion_filter = QComboBox()
        self.emotion_filter.addItems(
            ["全部", "😊 开心", "😢 难过", "😠 生气", "😰 焦虑", "🤩 兴奋", "😐 中性"]
        )
        self.emotion_filter.currentTextChanged.connect(self.apply_filters)
        layout.addWidget(emotion_label)
        layout.addWidget(self.emotion_filter)

        # 主题筛选
        topic_label = QLabel("主题:")
        self.topic_filter = QComboBox()
        self.topic_filter.addItems(
            [
                "全部",
                "💼 工作",
                "🏠 生活",
                "📖 学习",
                "🎮 娱乐",
                "💪 健康",
                "👥 人际关系",
                "📝 其他",
            ]
        )
        self.topic_filter.currentTextChanged.connect(self.apply_filters)
        layout.addWidget(topic_label)
        layout.addWidget(self.topic_filter)

        # 重要性筛选
        importance_label = QLabel("最小重要性:")
        self.importance_filter = QDoubleSpinBox()
        self.importance_filter.setRange(0.0, 1.0)
        self.importance_filter.setSingleStep(0.1)
        self.importance_filter.setValue(0.0)
        self.importance_filter.valueChanged.connect(self.apply_filters)
        layout.addWidget(importance_label)
        layout.addWidget(self.importance_filter)

        # 搜索框
        search_label = QLabel("搜索:")
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("搜索内容、人物、地点、事件...")
        self.search_input.textChanged.connect(self.apply_filters)
        layout.addWidget(search_label)
        layout.addWidget(self.search_input)

        # 重置按钮
        reset_btn = QPushButton("重置")
        reset_btn.clicked.connect(self.reset_filters)
        layout.addWidget(reset_btn)

        layout.addStretch()
        group.setLayout(layout)
        return group

    def _create_memory_table(self) -> QTableWidget:
        """创建记忆表格"""
        table = QTableWidget()
        table.setColumnCount(7)
        table.setHorizontalHeaderLabels(
            ["时间", "情感", "主题", "重要性", "内容预览", "元数据", "操作"]
        )

        # 设置列宽
        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)

        # 设置样式
        table.setStyleSheet(
            f"""
            QTableWidget {{
                border: 1px solid {MD3_LIGHT_COLORS['outline']};
                border-radius: 8px;
                background: {MD3_LIGHT_COLORS['surface']};
                gridline-color: {MD3_LIGHT_COLORS['outline_variant']};
            }}
            QTableWidget::item {{
                padding: 8px;
            }}
            QTableWidget::item:selected {{
                background: {MD3_LIGHT_COLORS['primary_container']};
                color: {MD3_LIGHT_COLORS['on_primary_container']};
            }}
            QHeaderView::section {{
                background: {MD3_LIGHT_COLORS['surface_container']};
                color: {MD3_LIGHT_COLORS['on_surface_variant']};
                padding: 8px;
                border: none;
                font-weight: bold;
            }}
        """
        )

        # 双击查看详情
        table.cellDoubleClicked.connect(self.show_memory_detail)

        return table

    def _create_stats_widget(self) -> QWidget:
        """创建统计信息区域"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        # 标题
        title = QLabel("📊 统计信息")
        title.setFont(QFont("Microsoft YaHei UI", 14, QFont.Weight.Bold))
        layout.addWidget(title)

        # 统计标签
        self.stats_label = QLabel("加载中...")
        self.stats_label.setWordWrap(True)
        self.stats_label.setStyleSheet(
            f"""
            QLabel {{
                background: {MD3_LIGHT_COLORS['surface_container']};
                border-radius: 8px;
                padding: 16px;
                color: {MD3_LIGHT_COLORS['on_surface_variant']};
                font-size: 13px;
                line-height: 1.6;
            }}
        """
        )
        layout.addWidget(self.stats_label)

        return widget

    def _create_button_layout(self) -> QHBoxLayout:
        """创建操作按钮布局"""
        layout = QHBoxLayout()
        layout.setSpacing(12)

        # 刷新按钮
        refresh_btn = QPushButton("🔄 刷新")
        refresh_btn.clicked.connect(self.load_memories)
        layout.addWidget(refresh_btn)

        # 删除选中按钮
        delete_btn = QPushButton("🗑️ 删除选中")
        delete_btn.clicked.connect(self.delete_selected)
        layout.addWidget(delete_btn)

        # 清空全部按钮
        clear_btn = QPushButton("⚠️ 清空全部")
        clear_btn.clicked.connect(self.clear_all_memories)
        layout.addWidget(clear_btn)

        layout.addStretch()

        return layout

    def load_memories(self):
        """加载记忆"""
        if not self.agent or not hasattr(self.agent, "diary_memory"):
            logger.warning("Agent 或 diary_memory 未初始化")
            return

        try:
            # 从 JSON 文件加载所有日记
            diary_file = self.agent.diary_memory.diary_file
            if not diary_file or not diary_file.exists():
                logger.warning("日记文件不存在")
                self.current_memories = []
                self.update_table()
                self.update_stats()
                return

            with open(diary_file, "r", encoding="utf-8") as f:
                self.current_memories = json.load(f)

            # 按时间倒序排序
            self.current_memories.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

            logger.info(f"加载了 {len(self.current_memories)} 条记忆")
            self.update_table()
            self.update_stats()

        except Exception as e:
            logger.error(f"加载记忆失败: {e}")
            QMessageBox.critical(self, "错误", f"加载记忆失败: {e}")

    def apply_filters(self):
        """应用筛选条件"""
        if not self.agent or not hasattr(self.agent, "diary_memory"):
            return

        try:
            # 从 JSON 文件加载所有日记
            diary_file = self.agent.diary_memory.diary_file
            if not diary_file or not diary_file.exists():
                self.current_memories = []
                self.update_table()
                return

            with open(diary_file, "r", encoding="utf-8") as f:
                all_memories = json.load(f)

            # 应用筛选
            filtered = all_memories

            # 情感筛选
            emotion_text = self.emotion_filter.currentText()
            if emotion_text != "全部":
                emotion_map = {
                    "😊 开心": "happy",
                    "😢 难过": "sad",
                    "😠 生气": "angry",
                    "😰 焦虑": "anxious",
                    "🤩 兴奋": "excited",
                    "😐 中性": "neutral",
                }
                emotion = emotion_map.get(emotion_text)
                if emotion:
                    filtered = [m for m in filtered if m.get("emotion") == emotion]

            # 主题筛选
            topic_text = self.topic_filter.currentText()
            if topic_text != "全部":
                topic_map = {
                    "💼 工作": "work",
                    "🏠 生活": "life",
                    "📖 学习": "study",
                    "🎮 娱乐": "entertainment",
                    "💪 健康": "health",
                    "👥 人际关系": "relationship",
                    "📝 其他": "other",
                }
                topic = topic_map.get(topic_text)
                if topic:
                    filtered = [m for m in filtered if m.get("topic") == topic]

            # 重要性筛选
            min_importance = self.importance_filter.value()
            if min_importance > 0.0:
                filtered = [m for m in filtered if m.get("importance", 0.0) >= min_importance]

            # 搜索筛选
            search_text = self.search_input.text().strip().lower()
            if search_text:
                filtered = [
                    m
                    for m in filtered
                    if (
                        search_text in m.get("content", "").lower()
                        or search_text in str(m.get("people", [])).lower()
                        or search_text in str(m.get("location", "")).lower()
                        or search_text in str(m.get("event", "")).lower()
                    )
                ]

            # 按时间倒序排序
            filtered.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

            self.current_memories = filtered
            self.update_table()
            self.update_stats()

        except Exception as e:
            logger.error(f"应用筛选失败: {e}")

    def reset_filters(self):
        """重置筛选条件"""
        self.emotion_filter.setCurrentIndex(0)
        self.topic_filter.setCurrentIndex(0)
        self.importance_filter.setValue(0.0)
        self.search_input.clear()
        self.load_memories()

    def update_table(self):
        """更新表格显示"""
        self.memory_table.setRowCount(0)

        emotion_map = {
            "happy": "😊",
            "sad": "😢",
            "angry": "😠",
            "anxious": "😰",
            "excited": "🤩",
            "neutral": "😐",
        }

        topic_map = {
            "work": "💼",
            "life": "🏠",
            "study": "📖",
            "entertainment": "🎮",
            "health": "💪",
            "relationship": "👥",
            "other": "📝",
        }

        for memory in self.current_memories:
            row = self.memory_table.rowCount()
            self.memory_table.insertRow(row)

            # 时间
            timestamp = memory.get("timestamp", "")
            if timestamp:
                dt = datetime.fromisoformat(timestamp)
                time_str = dt.strftime("%m-%d %H:%M")
            else:
                time_str = "未知"
            self.memory_table.setItem(row, 0, QTableWidgetItem(time_str))

            # 情感
            emotion = memory.get("emotion", "neutral")
            emotion_icon = emotion_map.get(emotion, "😐")
            self.memory_table.setItem(row, 1, QTableWidgetItem(emotion_icon))

            # 主题
            topic = memory.get("topic", "other")
            topic_icon = topic_map.get(topic, "📝")
            self.memory_table.setItem(row, 2, QTableWidgetItem(topic_icon))

            # 重要性
            importance = memory.get("importance", 0.0)
            self.memory_table.setItem(row, 3, QTableWidgetItem(f"{importance:.2f}"))

            # 内容预览
            content = memory.get("content", "")
            preview = content[:50] + "..." if len(content) > 50 else content
            self.memory_table.setItem(row, 4, QTableWidgetItem(preview))

            # 元数据
            metadata_parts = []
            people = memory.get("people", [])
            if people:
                metadata_parts.append(f"👤{','.join(people)}")
            location = memory.get("location")
            if location:
                metadata_parts.append(f"📍{location}")
            event = memory.get("event")
            if event:
                metadata_parts.append(f"📅{event}")
            metadata_str = " ".join(metadata_parts) if metadata_parts else "-"
            self.memory_table.setItem(row, 5, QTableWidgetItem(metadata_str))

            # 操作按钮
            btn_widget = QWidget()
            btn_layout = QHBoxLayout(btn_widget)
            btn_layout.setContentsMargins(4, 4, 4, 4)
            btn_layout.setSpacing(4)

            # 查看按钮
            view_btn = QPushButton("👁️")
            view_btn.setToolTip("查看详情")
            view_btn.setMaximumWidth(40)
            view_btn.clicked.connect(lambda checked, r=row: self.show_memory_detail(r, 0))
            btn_layout.addWidget(view_btn)

            # 删除按钮
            delete_btn = QPushButton("🗑️")
            delete_btn.setToolTip("删除")
            delete_btn.setMaximumWidth(40)
            delete_btn.clicked.connect(lambda checked, r=row: self.delete_memory(r))
            btn_layout.addWidget(delete_btn)

            self.memory_table.setCellWidget(row, 6, btn_widget)

    def update_stats(self):
        """更新统计信息"""
        if not self.current_memories:
            self.stats_label.setText("暂无记忆数据")
            return

        # 统计情感分布
        emotion_counts = {}
        for memory in self.current_memories:
            emotion = memory.get("emotion", "neutral")
            emotion_counts[emotion] = emotion_counts.get(emotion, 0) + 1

        # 统计主题分布
        topic_counts = {}
        for memory in self.current_memories:
            topic = memory.get("topic", "other")
            topic_counts[topic] = topic_counts.get(topic, 0) + 1

        # 计算平均重要性
        importances = [m.get("importance", 0.0) for m in self.current_memories]
        avg_importance = sum(importances) / len(importances) if importances else 0.0

        # 统计元数据
        people_count = sum(1 for m in self.current_memories if m.get("people"))
        location_count = sum(1 for m in self.current_memories if m.get("location"))
        event_count = sum(1 for m in self.current_memories if m.get("event"))

        # 构建统计文本
        emotion_map = {
            "happy": "😊 开心",
            "sad": "😢 难过",
            "angry": "😠 生气",
            "anxious": "😰 焦虑",
            "excited": "🤩 兴奋",
            "neutral": "😐 中性",
        }

        topic_map = {
            "work": "💼 工作",
            "life": "🏠 生活",
            "study": "📖 学习",
            "entertainment": "🎮 娱乐",
            "health": "💪 健康",
            "relationship": "👥 人际关系",
            "other": "📝 其他",
        }

        stats_text = f"<b>总记忆数:</b> {len(self.current_memories)}<br><br>"

        stats_text += "<b>情感分布:</b><br>"
        for emotion, count in sorted(emotion_counts.items(), key=lambda x: x[1], reverse=True):
            emotion_name = emotion_map.get(emotion, emotion)
            percentage = count / len(self.current_memories) * 100
            stats_text += f"  {emotion_name}: {count} ({percentage:.1f}%)<br>"

        stats_text += "<br><b>主题分布:</b><br>"
        for topic, count in sorted(topic_counts.items(), key=lambda x: x[1], reverse=True):
            topic_name = topic_map.get(topic, topic)
            percentage = count / len(self.current_memories) * 100
            stats_text += f"  {topic_name}: {count} ({percentage:.1f}%)<br>"

        stats_text += f"<br><b>平均重要性:</b> {avg_importance:.2f}<br>"
        stats_text += "<br><b>元数据统计:</b><br>"
        stats_text += f"  包含人物: {people_count}<br>"
        stats_text += f"  包含地点: {location_count}<br>"
        stats_text += f"  包含事件: {event_count}<br>"

        self.stats_label.setText(stats_text)

    def show_memory_detail(self, row: int, column: int):
        """显示记忆详情"""
        if row < 0 or row >= len(self.current_memories):
            return

        memory = self.current_memories[row]
        dialog = MemoryDetailDialog(memory, self)
        dialog.exec()

    def delete_memory(self, row: int):
        """删除单条记忆"""
        if row < 0 or row >= len(self.current_memories):
            return

        memory = self.current_memories[row]
        content_preview = memory.get("content", "")[:50]

        reply = QMessageBox.question(
            self,
            "确认删除",
            f"确定要删除这条记忆吗？\n\n{content_preview}...",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            try:
                # 从文件中删除
                diary_file = self.agent.diary_memory.diary_file
                with open(diary_file, "r", encoding="utf-8") as f:
                    all_memories = json.load(f)

                # 根据时间戳查找并删除
                timestamp = memory.get("timestamp")
                all_memories = [m for m in all_memories if m.get("timestamp") != timestamp]

                # 保存回文件
                with open(diary_file, "w", encoding="utf-8") as f:
                    json.dump(all_memories, f, ensure_ascii=False, indent=2)

                # 发送删除信号
                self.memory_deleted.emit(timestamp)

                # 重新加载
                self.load_memories()

                QMessageBox.information(self, "成功", "记忆已删除")

            except Exception as e:
                logger.error(f"删除记忆失败: {e}")
                QMessageBox.critical(self, "错误", f"删除记忆失败: {e}")

    def delete_selected(self):
        """删除选中的记忆"""
        selected_rows = set()
        for item in self.memory_table.selectedItems():
            selected_rows.add(item.row())

        if not selected_rows:
            QMessageBox.warning(self, "提示", "请先选择要删除的记忆")
            return

        reply = QMessageBox.question(
            self,
            "确认删除",
            f"确定要删除选中的 {len(selected_rows)} 条记忆吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            try:
                # 获取要删除的时间戳
                timestamps_to_delete = set()
                for row in selected_rows:
                    if row < len(self.current_memories):
                        memory = self.current_memories[row]
                        timestamps_to_delete.add(memory.get("timestamp"))

                # 从文件中删除
                diary_file = self.agent.diary_memory.diary_file
                with open(diary_file, "r", encoding="utf-8") as f:
                    all_memories = json.load(f)

                all_memories = [
                    m for m in all_memories if m.get("timestamp") not in timestamps_to_delete
                ]

                # 保存回文件
                with open(diary_file, "w", encoding="utf-8") as f:
                    json.dump(all_memories, f, ensure_ascii=False, indent=2)

                # 重新加载
                self.load_memories()

                QMessageBox.information(self, "成功", f"已删除 {len(timestamps_to_delete)} 条记忆")

            except Exception as e:
                logger.error(f"批量删除记忆失败: {e}")
                QMessageBox.critical(self, "错误", f"批量删除记忆失败: {e}")

    def clear_all_memories(self):
        """清空所有记忆"""
        reply = QMessageBox.warning(
            self,
            "⚠️ 危险操作",
            "确定要清空所有记忆吗？此操作不可恢复！",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            # 二次确认
            reply2 = QMessageBox.warning(
                self,
                "⚠️ 最后确认",
                "真的要清空所有记忆吗？这将永久删除所有数据！",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )

            if reply2 == QMessageBox.StandardButton.Yes:
                try:
                    # 清空文件
                    diary_file = self.agent.diary_memory.diary_file
                    with open(diary_file, "w", encoding="utf-8") as f:
                        json.dump([], f)

                    # 重新加载
                    self.load_memories()

                    QMessageBox.information(self, "成功", "所有记忆已清空")

                except Exception as e:
                    logger.error(f"清空记忆失败: {e}")
                    QMessageBox.critical(self, "错误", f"清空记忆失败: {e}")
