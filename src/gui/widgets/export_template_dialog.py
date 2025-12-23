"""
导出模板管理对话框 - v2.42.0

管理文件名导出模板
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QListWidget, QListWidgetItem,
    QMessageBox, QInputDialog
)
from PyQt6.QtCore import Qt, pyqtSignal
from typing import List, Dict
import json
from pathlib import Path

from src.utils.logger import get_logger

logger = get_logger(__name__)


class ExportTemplateDialog(QDialog):
    """导出模板管理对话框 (v2.42.0)"""

    # 信号
    template_selected = pyqtSignal(str)  # 模板选择信号

    # 默认模板
    DEFAULT_TEMPLATES = [
        "tts_{timestamp}_{text_preview}",
        "tts_{timestamp}_{ref_audio}_{emotion}",
        "{text_preview}_{timestamp}",
        "{ref_audio}_{emotion}_{index}",
    ]

    def __init__(self, parent=None):
        """初始化导出模板管理对话框"""
        super().__init__(parent)

        self.templates = self._load_templates()
        self.current_template = self.templates[0] if self.templates else self.DEFAULT_TEMPLATES[0]

        self.setWindowTitle("导出模板管理")
        self.setMinimumSize(500, 400)

        self._init_ui()
        logger.info("导出模板管理对话框已初始化")

    def _get_config_file(self) -> Path:
        """获取导出模板配置文件路径（跟随 settings.data_dir）。"""
        try:
            from src.config.settings import settings

            return Path(settings.data_dir) / "export_templates.json"
        except Exception:
            return Path("data/export_templates.json")

    def _init_ui(self):
        """初始化UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # 标题
        title_label = QLabel("📋 导出模板管理")
        title_label.setStyleSheet("font-size: 18px; font-weight: bold; color: #FF6B9D;")
        layout.addWidget(title_label)

        # 说明
        info_label = QLabel("可用占位符: {timestamp}, {text_preview}, {ref_audio}, {emotion}, {index}")
        info_label.setStyleSheet("color: #666; font-size: 12px;")
        layout.addWidget(info_label)

        # 模板列表
        self.template_list = QListWidget()
        self.template_list.setStyleSheet("""
            QListWidget {
                border: 2px solid rgba(255, 107, 157, 0.3);
                border-radius: 8px;
                background: white;
                padding: 5px;
            }
            QListWidget::item {
                padding: 8px;
                border-radius: 4px;
            }
            QListWidget::item:selected {
                background: qlineargradient(
                    x1:0, y1:0, x2:0, y2:1,
                    stop:0 #FF6B9D, stop:1 #C06C84
                );
                color: white;
            }
            QListWidget::item:hover {
                background: rgba(255, 107, 157, 0.1);
            }
        """)
        self._load_template_list()
        layout.addWidget(self.template_list)

        # 按钮布局
        button_layout = QHBoxLayout()

        # 添加按钮
        add_btn = QPushButton("➕ 添加")
        add_btn.setFixedSize(80, 32)
        add_btn.clicked.connect(self._add_template)
        button_layout.addWidget(add_btn)

        # 删除按钮
        delete_btn = QPushButton("🗑️ 删除")
        delete_btn.setFixedSize(80, 32)
        delete_btn.clicked.connect(self._delete_template)
        button_layout.addWidget(delete_btn)

        # 设为默认按钮
        default_btn = QPushButton("⭐ 设为默认")
        default_btn.setFixedSize(100, 32)
        default_btn.clicked.connect(self._set_default)
        button_layout.addWidget(default_btn)

        button_layout.addStretch()

        # 取消按钮
        cancel_btn = QPushButton("取消")
        cancel_btn.setFixedSize(80, 32)
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)

        # 确定按钮
        ok_btn = QPushButton("确定")
        ok_btn.setFixedSize(80, 32)
        ok_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #FF6B9D, stop:1 #C06C84);
                color: white;
                border: none;
                border-radius: 6px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #C06C84, stop:1 #FF6B9D);
            }
        """)
        ok_btn.clicked.connect(self._on_ok)
        button_layout.addWidget(ok_btn)

        layout.addLayout(button_layout)

    def _load_templates(self) -> List[str]:
        """加载模板列表"""
        config_file = self._get_config_file()
        try:
            if config_file.exists():
                with open(config_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                templates = data.get("templates", None) if isinstance(data, dict) else None
                if isinstance(templates, list):
                    filtered = [str(item) for item in templates if str(item).strip()]
                    if filtered:
                        return filtered
        except Exception as e:
            logger.error(f"加载模板失败: {e}")
        return self.DEFAULT_TEMPLATES.copy()

    def _save_templates(self) -> None:
        """保存模板列表到配置文件。"""
        config_file = self._get_config_file()
        try:
            config_file.parent.mkdir(parents=True, exist_ok=True)
            payload: Dict[str, List[str]] = {"templates": [str(t) for t in self.templates if str(t).strip()]}
            with open(config_file, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存模板失败: {e}")

    def _load_template_list(self):
        """加载模板到列表"""
        self.template_list.clear()
        for template in self.templates:
            item = QListWidgetItem(template)
            if template == self.current_template:
                item.setBackground(Qt.GlobalColor.lightGray)
            self.template_list.addItem(item)

    def _add_template(self):
        """添加新模板"""
        template, ok = QInputDialog.getText(
            self,
            "添加模板",
            "请输入模板（可用占位符: {timestamp}, {text_preview}, {ref_audio}, {emotion}, {index}）:",
            text="tts_{timestamp}_{text_preview}"
        )

        if ok and template:
            if template not in self.templates:
                self.templates.append(template)
                self._load_template_list()
                self._save_templates()
                logger.info(f"添加模板: {template}")
            else:
                QMessageBox.warning(self, "重复模板", "该模板已存在")

    def _delete_template(self):
        """删除选中的模板"""
        current_item = self.template_list.currentItem()
        if not current_item:
            QMessageBox.warning(self, "未选择", "请先选择要删除的模板")
            return

        template = current_item.text()

        if len(self.templates) <= 1:
            QMessageBox.warning(self, "无法删除", "至少需要保留一个模板")
            return

        reply = QMessageBox.question(
            self,
            "确认删除",
            f"确定要删除模板 '{template}' 吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.templates.remove(template)
            if template == self.current_template:
                self.current_template = self.templates[0]
            self._load_template_list()
            self._save_templates()
            logger.info(f"删除模板: {template}")

    def _set_default(self):
        """设置默认模板"""
        current_item = self.template_list.currentItem()
        if not current_item:
            QMessageBox.warning(self, "未选择", "请先选择要设为默认的模板")
            return

        self.current_template = current_item.text()
        self._load_template_list()
        logger.info(f"设置默认模板: {self.current_template}")

    def _on_ok(self):
        """确定按钮点击"""
        current_item = self.template_list.currentItem()
        if current_item:
            self.template_selected.emit(current_item.text())
        else:
            self.template_selected.emit(self.current_template)
        self.accept()
