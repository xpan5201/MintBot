"""
知识库（世界书）管理界面 - v2.30.38

提供知识库查看、编辑、管理功能
支持添加、更新、删除、导入、导出知识
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTableWidget, QTableWidgetItem, QComboBox, QLineEdit,
    QTextEdit, QDialog, QDialogButtonBox, QHeaderView,
    QMessageBox, QFileDialog, QGroupBox, QFormLayout,
    QScrollArea, QSplitter, QTabWidget, QProgressDialog
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QThread
from PyQt6.QtGui import QFont, QColor
from datetime import datetime
from typing import Optional, List, Dict, Any
from pathlib import Path
import json

from src.utils.logger import get_logger
from .material_design_light import MD3_LIGHT_COLORS

logger = get_logger(__name__)


class LearnFileThread(QThread):
    """后台从文件学习知识，避免阻塞 UI。"""

    learned = pyqtSignal(list)  # learned_ids
    error = pyqtSignal(str)

    def __init__(self, lore_book, filepath: str):
        super().__init__()
        self.lore_book = lore_book
        self.filepath = filepath

    def run(self) -> None:
        try:
            if self.lore_book is None:
                raise RuntimeError("知识库未初始化")
            learned_ids = self.lore_book.learn_from_file(self.filepath)
            self.learned.emit(learned_ids or [])
        except Exception as exc:
            self.error.emit(str(exc))


class LoreDetailDialog(QDialog):
    """知识详情对话框"""

    def __init__(self, lore: Dict[str, Any], parent=None):
        super().__init__(parent)
        self.lore = lore
        self.setWindowTitle("知识详情")
        self.setMinimumSize(600, 500)
        self.setup_ui()

    def setup_ui(self):
        """设置 UI"""
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 24, 24, 24)

        # 标题
        title = QLabel("📚 知识详情")
        title.setFont(QFont("Microsoft YaHei UI", 16, QFont.Weight.Bold))
        layout.addWidget(title)

        # 滚动区域
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"""
            QScrollArea {{
                border: none;
                background: transparent;
            }}
        """)

        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setSpacing(12)

        # 显示知识信息
        info_items = [
            ("📝 标题", self.lore.get("title", "未知")),
            ("📂 类别", self.lore.get("category", "general")),
            ("🔖 关键词", ", ".join(self.lore.get("keywords", []))),
            ("📍 来源", self.lore.get("source", "manual")),
            ("⏰ 创建时间", self.lore.get("timestamp", "未知")),
            ("🔄 更新次数", str(self.lore.get("update_count", 0))),
        ]

        for label_text, value_text in info_items:
            item_layout = QVBoxLayout()
            item_layout.setSpacing(4)

            label = QLabel(label_text)
            label.setFont(QFont("Microsoft YaHei UI", 10, QFont.Weight.Bold))
            label.setStyleSheet(f"color: {MD3_LIGHT_COLORS['on_surface_variant']};")

            value = QLabel(str(value_text))
            value.setWordWrap(True)
            value.setStyleSheet(f"""
                QLabel {{
                    background: {MD3_LIGHT_COLORS['surface_container']};
                    border-radius: 8px;
                    padding: 8px;
                    color: {MD3_LIGHT_COLORS['on_surface']};
                }}
            """)

            item_layout.addWidget(label)
            item_layout.addWidget(value)
            content_layout.addLayout(item_layout)

        # 内容
        content_label = QLabel("📄 内容")
        content_label.setFont(QFont("Microsoft YaHei UI", 10, QFont.Weight.Bold))
        content_label.setStyleSheet(f"color: {MD3_LIGHT_COLORS['on_surface_variant']};")
        content_layout.addWidget(content_label)

        content_text = QTextEdit()
        content_text.setPlainText(self.lore.get("content", ""))
        content_text.setReadOnly(True)
        content_text.setMinimumHeight(200)
        content_text.setStyleSheet(f"""
            QTextEdit {{
                background: {MD3_LIGHT_COLORS['surface_container']};
                border-radius: 8px;
                padding: 12px;
                color: {MD3_LIGHT_COLORS['on_surface']};
                font-size: 13px;
                line-height: 1.6;
            }}
        """)
        content_layout.addWidget(content_text)

        scroll.setWidget(content_widget)
        layout.addWidget(scroll)

        # 按钮
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        button_box.accepted.connect(self.accept)
        button_box.setStyleSheet(f"""
            QPushButton {{
                background: {MD3_LIGHT_COLORS['primary']};
                color: {MD3_LIGHT_COLORS['on_primary']};
                border: none;
                border-radius: 8px;
                padding: 8px 24px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background: {MD3_LIGHT_COLORS['primary_light']};
            }}
        """)
        layout.addWidget(button_box)


class LoreEditDialog(QDialog):
    """知识编辑对话框 - v2.30.39 新增"""

    def __init__(self, lore: Optional[Dict[str, Any]] = None, parent=None):
        super().__init__(parent)
        self.lore = lore  # None 表示添加新知识
        self.is_add_mode = lore is None

        self.setWindowTitle("添加知识" if self.is_add_mode else "编辑知识")
        self.setMinimumSize(700, 600)
        self.setup_ui()

    def setup_ui(self):
        """设置 UI"""
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 24, 24, 24)

        # 标题
        title_text = "➕ 添加知识" if self.is_add_mode else "✏️ 编辑知识"
        title = QLabel(title_text)
        title.setFont(QFont("Microsoft YaHei UI", 16, QFont.Weight.Bold))
        layout.addWidget(title)

        # 表单
        form_layout = QFormLayout()
        form_layout.setSpacing(12)
        form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        # 标题输入
        self.title_input = QLineEdit()
        self.title_input.setPlaceholderText("请输入知识标题...")
        if not self.is_add_mode:
            self.title_input.setText(self.lore.get("title", ""))
        self.title_input.setStyleSheet(self._get_input_style())
        form_layout.addRow("📝 标题:", self.title_input)

        # 类别选择
        self.category_combo = QComboBox()
        self.category_combo.addItems([
            "general (通用)",
            "character (角色)",
            "location (地点)",
            "item (物品)",
            "event (事件)",
        ])
        if not self.is_add_mode:
            category = self.lore.get("category", "general")
            index = ["general", "character", "location", "item", "event"].index(category)
            self.category_combo.setCurrentIndex(index)
        self.category_combo.setStyleSheet(self._get_input_style())
        form_layout.addRow("📂 类别:", self.category_combo)

        # 关键词输入
        self.keywords_input = QLineEdit()
        self.keywords_input.setPlaceholderText("请输入关键词，用逗号分隔...")
        if not self.is_add_mode:
            keywords = self.lore.get("keywords", [])
            self.keywords_input.setText(", ".join(keywords))
        self.keywords_input.setStyleSheet(self._get_input_style())
        form_layout.addRow("🔖 关键词:", self.keywords_input)

        # 来源（仅显示，不可编辑）
        if not self.is_add_mode:
            source_label = QLabel(self.lore.get("source", "manual"))
            source_label.setStyleSheet(f"""
                QLabel {{
                    background: {MD3_LIGHT_COLORS['surface_container']};
                    border-radius: 8px;
                    padding: 8px;
                    color: {MD3_LIGHT_COLORS['on_surface_variant']};
                }}
            """)
            form_layout.addRow("📍 来源:", source_label)

        layout.addLayout(form_layout)

        # 内容输入
        content_label = QLabel("📄 内容:")
        content_label.setFont(QFont("Microsoft YaHei UI", 10, QFont.Weight.Bold))
        layout.addWidget(content_label)

        self.content_input = QTextEdit()
        self.content_input.setPlaceholderText("请输入知识内容...")
        if not self.is_add_mode:
            self.content_input.setPlainText(self.lore.get("content", ""))
        self.content_input.setMinimumHeight(250)
        self.content_input.setStyleSheet(f"""
            QTextEdit {{
                background: {MD3_LIGHT_COLORS['surface_container']};
                border: 2px solid {MD3_LIGHT_COLORS['outline']};
                border-radius: 8px;
                padding: 12px;
                color: {MD3_LIGHT_COLORS['on_surface']};
                font-size: 13px;
                line-height: 1.6;
            }}
            QTextEdit:focus {{
                border-color: {MD3_LIGHT_COLORS['primary']};
            }}
        """)
        layout.addWidget(self.content_input)

        # 按钮
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        cancel_btn.setStyleSheet(f"""
            QPushButton {{
                background: {MD3_LIGHT_COLORS['surface_container']};
                color: {MD3_LIGHT_COLORS['on_surface']};
                border: none;
                border-radius: 8px;
                padding: 10px 24px;
                font-weight: bold;
                min-width: 80px;
            }}
            QPushButton:hover {{
                background: {MD3_LIGHT_COLORS['surface_container_high']};
            }}
        """)
        button_layout.addWidget(cancel_btn)

        save_btn = QPushButton("保存")
        save_btn.clicked.connect(self.accept)
        save_btn.setStyleSheet(f"""
            QPushButton {{
                background: {MD3_LIGHT_COLORS['primary']};
                color: {MD3_LIGHT_COLORS['on_primary']};
                border: none;
                border-radius: 8px;
                padding: 10px 24px;
                font-weight: bold;
                min-width: 80px;
            }}
            QPushButton:hover {{
                background: {MD3_LIGHT_COLORS['primary_light']};
            }}
        """)
        button_layout.addWidget(save_btn)

        layout.addLayout(button_layout)

    def _get_input_style(self) -> str:
        """获取输入框样式"""
        return f"""
            QLineEdit, QComboBox {{
                background: {MD3_LIGHT_COLORS['surface_container']};
                border: 2px solid {MD3_LIGHT_COLORS['outline']};
                border-radius: 8px;
                padding: 8px 12px;
                color: {MD3_LIGHT_COLORS['on_surface']};
                font-size: 13px;
            }}
            QLineEdit:focus, QComboBox:focus {{
                border-color: {MD3_LIGHT_COLORS['primary']};
            }}
            QComboBox::drop-down {{
                border: none;
                padding-right: 8px;
            }}
            QComboBox::down-arrow {{
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 5px solid {MD3_LIGHT_COLORS['on_surface']};
                margin-right: 8px;
            }}
        """

    def get_data(self) -> Dict[str, Any]:
        """获取表单数据"""
        category_text = self.category_combo.currentText()
        category = category_text.split(" ")[0]  # 提取类别代码

        keywords_text = self.keywords_input.text().strip()
        keywords = [k.strip() for k in keywords_text.split(",") if k.strip()]

        return {
            "title": self.title_input.text().strip(),
            "content": self.content_input.toPlainText().strip(),
            "category": category,
            "keywords": keywords,
        }

    def validate(self) -> bool:
        """验证表单数据"""
        data = self.get_data()

        if not data["title"]:
            QMessageBox.warning(self, "验证失败", "请输入知识标题")
            return False

        if not data["content"]:
            QMessageBox.warning(self, "验证失败", "请输入知识内容")
            return False

        return True

    def accept(self):
        """确认按钮"""
        if self.validate():
            super().accept()


class LoreBookManagerWidget(QWidget):
    """知识库管理器主界面"""

    # 信号
    lore_added = pyqtSignal(str)  # 知识ID
    lore_updated = pyqtSignal(str)  # 知识ID
    lore_deleted = pyqtSignal(str)  # 知识ID

    def __init__(self, agent, parent=None):
        super().__init__(parent)
        self.agent = agent
        self.lore_book = agent.lore_book if agent else None
        self.current_lores = []
        self._learn_file_thread: Optional[LearnFileThread] = None
        self._learn_progress: Optional[QProgressDialog] = None
        self.setup_ui()
        self.load_lores()

    def setup_ui(self):
        """设置 UI"""
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(16, 16, 16, 16)

        # 标题栏
        header_layout = QHBoxLayout()

        title = QLabel("📚 知识库管理")
        title.setFont(QFont("Microsoft YaHei UI", 18, QFont.Weight.Bold))
        header_layout.addWidget(title)

        header_layout.addStretch()

        # 统计信息
        self.stats_label = QLabel("加载中...")
        self.stats_label.setStyleSheet(f"color: {MD3_LIGHT_COLORS['on_surface_variant']};")
        header_layout.addWidget(self.stats_label)

        layout.addLayout(header_layout)

        # 工具栏
        toolbar_layout = QHBoxLayout()

        # 添加按钮
        add_btn = QPushButton("➕ 添加知识")
        add_btn.clicked.connect(self._on_add_clicked)
        self._style_button(add_btn, "primary")
        toolbar_layout.addWidget(add_btn)

        # 导入按钮
        import_btn = QPushButton("📥 导入")
        import_btn.clicked.connect(self._on_import_clicked)
        self._style_button(import_btn, "secondary")
        toolbar_layout.addWidget(import_btn)

        # 导出按钮
        export_btn = QPushButton("📤 导出")
        export_btn.clicked.connect(self._on_export_clicked)
        self._style_button(export_btn, "secondary")
        toolbar_layout.addWidget(export_btn)

        # 学习文件按钮
        self.learn_file_btn = QPushButton("📖 学习文件")
        self.learn_file_btn.clicked.connect(self._on_learn_file_clicked)
        self._style_button(self.learn_file_btn, "tertiary")
        toolbar_layout.addWidget(self.learn_file_btn)

        toolbar_layout.addStretch()

        # 刷新按钮
        refresh_btn = QPushButton("🔄 刷新")
        refresh_btn.clicked.connect(self.load_lores)
        self._style_button(refresh_btn, "secondary")
        toolbar_layout.addWidget(refresh_btn)

        layout.addLayout(toolbar_layout)

        # 筛选栏
        filter_layout = QHBoxLayout()

        # 类别筛选
        filter_layout.addWidget(QLabel("类别:"))
        self.category_filter = QComboBox()
        self.category_filter.addItems([
            "全部", "character", "location", "item", "event", "general"
        ])
        self.category_filter.currentTextChanged.connect(self._on_filter_changed)
        self._style_combobox(self.category_filter)
        filter_layout.addWidget(self.category_filter)

        # 来源筛选
        filter_layout.addWidget(QLabel("来源:"))
        self.source_filter = QComboBox()
        self.source_filter.addItems([
            "全部", "manual", "conversation", "file", "mcp", "import"
        ])
        self.source_filter.currentTextChanged.connect(self._on_filter_changed)
        self._style_combobox(self.source_filter)
        filter_layout.addWidget(self.source_filter)

        # 搜索框
        filter_layout.addWidget(QLabel("搜索:"))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("搜索标题、内容、关键词...")
        self.search_input.textChanged.connect(self._on_filter_changed)
        self._style_lineedit(self.search_input)
        filter_layout.addWidget(self.search_input)

        layout.addLayout(filter_layout)

        # 知识列表表格
        self.lore_table = self._create_lore_table()
        layout.addWidget(self.lore_table)

        # 底部按钮栏
        bottom_layout = QHBoxLayout()

        # 删除按钮
        delete_btn = QPushButton("🗑️ 删除选中")
        delete_btn.clicked.connect(self._on_delete_clicked)
        self._style_button(delete_btn, "error")
        bottom_layout.addWidget(delete_btn)

        # 清空按钮
        clear_btn = QPushButton("🧹 清空全部")
        clear_btn.clicked.connect(self._on_clear_all_clicked)
        self._style_button(clear_btn, "error")
        bottom_layout.addWidget(clear_btn)

        bottom_layout.addStretch()

        layout.addLayout(bottom_layout)

    def _create_lore_table(self) -> QTableWidget:
        """创建知识列表表格"""
        table = QTableWidget()
        table.setColumnCount(7)
        table.setHorizontalHeaderLabels([
            "标题", "类别", "关键词", "来源", "创建时间", "更新次数", "操作"
        ])

        # 设置列宽
        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)  # 标题
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)  # 类别
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)  # 关键词
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)  # 来源
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)  # 时间
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)  # 更新次数
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)  # 操作

        # 样式
        table.setStyleSheet(f"""
            QTableWidget {{
                background: {MD3_LIGHT_COLORS['surface']};
                border: 1px solid {MD3_LIGHT_COLORS['outline']};
                border-radius: 12px;
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
        """)

        # 双击查看详情
        table.cellDoubleClicked.connect(self.show_lore_detail)

        return table

    def load_lores(self):
        """加载知识列表"""
        if not self.lore_book:
            return

        try:
            # 获取所有知识
            self.current_lores = self.lore_book.get_all_lores()

            # 应用筛选
            self._apply_filters()

            # 更新统计信息
            self._update_statistics()

            logger.info(f"加载知识库: {len(self.current_lores)} 条")

        except Exception as e:
            logger.error(f"加载知识库失败: {e}")
            QMessageBox.critical(self, "错误", f"加载知识库失败: {e}")

    def _apply_filters(self):
        """应用筛选条件"""
        filtered_lores = self.current_lores

        # 类别筛选
        category = self.category_filter.currentText()
        if category != "全部":
            filtered_lores = [
                lore for lore in filtered_lores
                if lore.get("category") == category
            ]

        # 来源筛选
        source = self.source_filter.currentText()
        if source != "全部":
            filtered_lores = [
                lore for lore in filtered_lores
                if lore.get("source", "manual").startswith(source)
            ]

        # 搜索筛选
        search_text = self.search_input.text().lower()
        if search_text:
            filtered_lores = [
                lore for lore in filtered_lores
                if search_text in lore.get("title", "").lower()
                or search_text in lore.get("content", "").lower()
                or search_text in " ".join(lore.get("keywords", [])).lower()
            ]

        # 更新表格
        self._update_table(filtered_lores)

    def _update_table(self, lores: List[Dict[str, Any]]):
        """更新表格显示"""
        self.lore_table.setRowCount(len(lores))

        for row, lore in enumerate(lores):
            # 标题
            title_item = QTableWidgetItem(lore.get("title", ""))
            self.lore_table.setItem(row, 0, title_item)

            # 类别
            category_item = QTableWidgetItem(lore.get("category", "general"))
            self.lore_table.setItem(row, 1, category_item)

            # 关键词
            keywords = ", ".join(lore.get("keywords", [])[:3])  # 只显示前3个
            if len(lore.get("keywords", [])) > 3:
                keywords += "..."
            keywords_item = QTableWidgetItem(keywords)
            self.lore_table.setItem(row, 2, keywords_item)

            # 来源
            source_item = QTableWidgetItem(lore.get("source", "manual"))
            self.lore_table.setItem(row, 3, source_item)

            # 创建时间
            timestamp = lore.get("timestamp", "")
            if timestamp:
                try:
                    dt = datetime.fromisoformat(timestamp)
                    time_str = dt.strftime("%Y-%m-%d %H:%M")
                except:
                    time_str = timestamp
            else:
                time_str = "未知"
            time_item = QTableWidgetItem(time_str)
            self.lore_table.setItem(row, 4, time_item)

            # 更新次数
            update_count = str(lore.get("update_count", 0))
            update_item = QTableWidgetItem(update_count)
            self.lore_table.setItem(row, 5, update_item)

            # 操作按钮
            action_widget = QWidget()
            action_layout = QHBoxLayout(action_widget)
            action_layout.setContentsMargins(4, 4, 4, 4)
            action_layout.setSpacing(4)

            # 查看按钮
            view_btn = QPushButton("👁️")
            view_btn.setToolTip("查看详情")
            view_btn.setMaximumWidth(40)
            view_btn.clicked.connect(lambda checked, r=row: self.show_lore_detail(r, 0))
            action_layout.addWidget(view_btn)

            # 编辑按钮
            edit_btn = QPushButton("✏️")
            edit_btn.setToolTip("编辑")
            edit_btn.setMaximumWidth(40)
            edit_btn.clicked.connect(lambda checked, l=lore: self._on_edit_clicked(l))
            action_layout.addWidget(edit_btn)

            self.lore_table.setCellWidget(row, 6, action_widget)

    def _update_statistics(self):
        """更新统计信息"""
        if not self.lore_book:
            return

        try:
            stats = self.lore_book.get_statistics()
            total = stats.get("total", 0)
            recent = stats.get("recent_count", 0)

            self.stats_label.setText(f"总计: {total} 条 | 最近7天: {recent} 条")

        except Exception as e:
            logger.error(f"更新统计信息失败: {e}")

    def show_lore_detail(self, row: int, column: int):
        """显示知识详情"""
        if row < 0 or row >= self.lore_table.rowCount():
            return

        # 获取标题
        title_item = self.lore_table.item(row, 0)
        if not title_item:
            return

        title = title_item.text()

        # 查找知识
        lore = None
        for l in self.current_lores:
            if l.get("title") == title:
                lore = l
                break

        if not lore:
            return

        # 显示详情对话框
        dialog = LoreDetailDialog(lore, self)
        dialog.exec()

    def _on_filter_changed(self):
        """筛选条件改变"""
        self._apply_filters()

    def _on_add_clicked(self):
        """添加知识 - v2.30.39 实现"""
        dialog = LoreEditDialog(parent=self)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            try:
                data = dialog.get_data()

                # 添加知识
                lore_id = self.lore_book.add_lore(
                    title=data["title"],
                    content=data["content"],
                    category=data["category"],
                    keywords=data["keywords"],
                    source="manual",
                )

                if lore_id:
                    self.load_lores()
                    self.lore_added.emit(lore_id)
                    QMessageBox.information(self, "成功", f"知识添加成功！\nID: {lore_id}")
                else:
                    QMessageBox.critical(self, "错误", "添加知识失败")

            except Exception as e:
                logger.error(f"添加知识失败: {e}")
                QMessageBox.critical(self, "错误", f"添加知识失败: {e}")

    def _on_edit_clicked(self, lore: Dict[str, Any]):
        """编辑知识 - v2.30.39 实现"""
        dialog = LoreEditDialog(lore=lore, parent=self)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            try:
                data = dialog.get_data()
                lore_id = lore.get("id")

                if not lore_id:
                    QMessageBox.critical(self, "错误", "知识ID不存在")
                    return

                # 更新知识
                success = self.lore_book.update_lore(
                    lore_id=lore_id,
                    title=data["title"],
                    content=data["content"],
                    category=data["category"],
                    keywords=data["keywords"],
                )

                if success:
                    self.load_lores()
                    self.lore_updated.emit(lore_id)
                    QMessageBox.information(self, "成功", "知识更新成功！")
                else:
                    QMessageBox.critical(self, "错误", "更新知识失败")

            except Exception as e:
                logger.error(f"更新知识失败: {e}")
                QMessageBox.critical(self, "错误", f"更新知识失败: {e}")

    def _on_delete_clicked(self):
        """删除选中的知识"""
        selected_rows = set(item.row() for item in self.lore_table.selectedItems())
        if not selected_rows:
            QMessageBox.warning(self, "提示", "请先选择要删除的知识")
            return

        # 确认删除
        reply = QMessageBox.question(
            self,
            "确认删除",
            f"确定要删除选中的 {len(selected_rows)} 条知识吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        # 删除知识
        deleted_count = 0
        for row in sorted(selected_rows, reverse=True):
            title_item = self.lore_table.item(row, 0)
            if not title_item:
                continue

            title = title_item.text()

            # 查找知识ID
            for lore in self.current_lores:
                if lore.get("title") == title:
                    lore_id = lore.get("id")
                    if lore_id and self.lore_book.delete_lore(lore_id):
                        deleted_count += 1
                        self.lore_deleted.emit(lore_id)
                    break

        # 刷新列表
        self.load_lores()

        QMessageBox.information(self, "成功", f"已删除 {deleted_count} 条知识")

    def _on_clear_all_clicked(self):
        """清空所有知识"""
        reply = QMessageBox.question(
            self,
            "确认清空",
            "⚠️ 确定要清空所有知识吗？此操作不可恢复！",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        if self.lore_book and self.lore_book.clear_all():
            self.load_lores()
            QMessageBox.information(self, "成功", "已清空所有知识")
        else:
            QMessageBox.critical(self, "错误", "清空失败")

    def _on_import_clicked(self):
        """导入知识库"""
        filepath, _ = QFileDialog.getOpenFileName(
            self,
            "选择导入文件",
            "",
            "JSON Files (*.json)"
        )

        if not filepath:
            return

        try:
            count = self.lore_book.import_from_json(filepath, overwrite=False)
            self.load_lores()
            QMessageBox.information(self, "成功", f"成功导入 {count} 条知识")
        except Exception as e:
            logger.error(f"导入失败: {e}")
            QMessageBox.critical(self, "错误", f"导入失败: {e}")

    def _on_export_clicked(self):
        """导出知识库"""
        filepath, _ = QFileDialog.getSaveFileName(
            self,
            "选择导出文件",
            f"lore_book_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
            "JSON Files (*.json)"
        )

        if not filepath:
            return

        try:
            if self.lore_book.export_to_json(filepath):
                QMessageBox.information(self, "成功", f"成功导出到: {filepath}")
            else:
                QMessageBox.critical(self, "错误", "导出失败")
        except Exception as e:
            logger.error(f"导出失败: {e}")
            QMessageBox.critical(self, "错误", f"导出失败: {e}")

    def _on_learn_file_clicked(self):
        """从文件学习知识"""
        if self._learn_file_thread is not None and self._learn_file_thread.isRunning():
            QMessageBox.information(self, "提示", "正在学习文件中，请稍候…")
            return

        filepath, _ = QFileDialog.getOpenFileName(
            self,
            "选择学习文件",
            "",
            "Text Files (*.txt *.md);;PDF Files (*.pdf);;Word Files (*.docx);;All Files (*.*)"
        )

        if not filepath:
            return

        if self.lore_book is None:
            QMessageBox.critical(self, "错误", "知识库未初始化")
            return

        self._learn_progress = QProgressDialog("正在学习文件，请稍候…", None, 0, 0, self)
        self._learn_progress.setWindowTitle("学习中")
        self._learn_progress.setWindowModality(Qt.WindowModality.WindowModal)
        self._learn_progress.setCancelButton(None)
        self._learn_progress.setMinimumDuration(0)
        self._learn_progress.show()

        try:
            if hasattr(self, "learn_file_btn") and self.learn_file_btn is not None:
                self.learn_file_btn.setEnabled(False)
        except Exception:
            pass

        self._learn_file_thread = LearnFileThread(self.lore_book, filepath)
        self._learn_file_thread.learned.connect(self._on_learn_file_finished)
        self._learn_file_thread.error.connect(self._on_learn_file_error)
        self._learn_file_thread.start()

    def _on_learn_file_finished(self, learned_ids: list) -> None:
        try:
            self.load_lores()
            QMessageBox.information(self, "成功", f"从文件中学习到 {len(learned_ids)} 条知识")
        finally:
            self._cleanup_learn_file_thread()

    def _on_learn_file_error(self, error: str) -> None:
        logger.error("学习失败: %s", error)
        try:
            QMessageBox.critical(self, "错误", f"学习失败: {error}")
        finally:
            self._cleanup_learn_file_thread()

    def _cleanup_learn_file_thread(self) -> None:
        try:
            if self._learn_progress is not None:
                self._learn_progress.close()
        except Exception:
            pass
        self._learn_progress = None

        try:
            if hasattr(self, "learn_file_btn") and self.learn_file_btn is not None:
                self.learn_file_btn.setEnabled(True)
        except Exception:
            pass

        try:
            if self._learn_file_thread is not None:
                self._learn_file_thread.deleteLater()
        except Exception:
            pass
        self._learn_file_thread = None

    # ==================== 样式方法 ====================

    def _style_button(self, button: QPushButton, style_type: str = "primary"):
        """设置按钮样式"""
        if style_type == "primary":
            bg_color = MD3_LIGHT_COLORS['primary']
            text_color = MD3_LIGHT_COLORS['on_primary']
            hover_color = MD3_LIGHT_COLORS['primary_light']
        elif style_type == "secondary":
            bg_color = MD3_LIGHT_COLORS['secondary']
            text_color = MD3_LIGHT_COLORS['on_secondary']
            hover_color = MD3_LIGHT_COLORS['secondary_light']
        elif style_type == "tertiary":
            bg_color = MD3_LIGHT_COLORS['tertiary']
            text_color = MD3_LIGHT_COLORS['on_tertiary']
            hover_color = MD3_LIGHT_COLORS['tertiary_light']
        elif style_type == "error":
            bg_color = MD3_LIGHT_COLORS['error']
            text_color = MD3_LIGHT_COLORS['on_error']
            hover_color = MD3_LIGHT_COLORS['error_light']
        else:
            bg_color = MD3_LIGHT_COLORS['surface_container']
            text_color = MD3_LIGHT_COLORS['on_surface']
            hover_color = MD3_LIGHT_COLORS['surface_container_high']

        button.setStyleSheet(f"""
            QPushButton {{
                background: {bg_color};
                color: {text_color};
                border: none;
                border-radius: 8px;
                padding: 8px 16px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background: {hover_color};
            }}
            QPushButton:pressed {{
                background: {bg_color};
            }}
        """)

    def _style_combobox(self, combobox: QComboBox):
        """设置下拉框样式"""
        combobox.setStyleSheet(f"""
            QComboBox {{
                background: {MD3_LIGHT_COLORS['surface_container']};
                border: 1px solid {MD3_LIGHT_COLORS['outline']};
                border-radius: 8px;
                padding: 6px 12px;
                min-width: 100px;
            }}
            QComboBox:hover {{
                border-color: {MD3_LIGHT_COLORS['primary']};
            }}
            QComboBox::drop-down {{
                border: none;
            }}
        """)

    def _style_lineedit(self, lineedit: QLineEdit):
        """设置输入框样式"""
        lineedit.setStyleSheet(f"""
            QLineEdit {{
                background: {MD3_LIGHT_COLORS['surface_container']};
                border: 1px solid {MD3_LIGHT_COLORS['outline']};
                border-radius: 8px;
                padding: 6px 12px;
                min-width: 200px;
            }}
            QLineEdit:focus {{
                border-color: {MD3_LIGHT_COLORS['primary']};
            }}
        """)
