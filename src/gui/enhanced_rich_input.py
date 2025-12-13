"""
MintChat - 增强富文本输入框

支持内联显示表情包和文件预览的输入框组件

v2.30.7 新增
"""

from PyQt6.QtWidgets import (
    QWidget, QTextEdit, QVBoxLayout, QHBoxLayout, 
    QLabel, QPushButton, QScrollArea
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize, QTimer
from PyQt6.QtGui import (
    QTextCursor, QTextDocument, QTextImageFormat,
    QImage, QPixmap, QPainter, QTextCharFormat
)
from pathlib import Path
from src.utils.logger import get_logger

from src.gui.material_design_light import MD3_LIGHT_COLORS
from src.gui.material_design_enhanced import MD3_ENHANCED_COLORS

logger = get_logger(__name__)


class RichTextInput(QTextEdit):
    """支持富文本的输入框 - 可内联显示图片"""
    
    # 信号
    send_requested = pyqtSignal()  # 请求发送
    content_changed = pyqtSignal()  # 内容改变
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # 配置
        self.setAcceptRichText(True)  # 支持富文本
        self.setPlaceholderText("💬 输入消息... (Enter 发送, Shift+Enter 换行)")
        self.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        # 高度设置
        self._single_line_height = 56
        self._max_lines = 4
        self.setFixedHeight(self._single_line_height)
        
        # 样式 - v2.31.0: 优化渐变背景和焦点效果
        self.setStyleSheet(f"""
            QTextEdit {{
                background: qlineargradient(
                    x1:0, y1:0, x2:0, y2:1,
                    stop:0 {MD3_LIGHT_COLORS['surface_container']},
                    stop:1 {MD3_LIGHT_COLORS['surface_container_low']}
                );
                border: 1px solid {MD3_LIGHT_COLORS['outline_variant']};
                border-radius: 28px;
                padding: 14px 20px;
                font-size: 15px;
                color: {MD3_LIGHT_COLORS['on_surface']};
                line-height: 1.5;
            }}
            QTextEdit:focus {{
                background: qlineargradient(
                    x1:0, y1:0, x2:0, y2:1,
                    stop:0 {MD3_ENHANCED_COLORS['surface_bright']},
                    stop:1 {MD3_LIGHT_COLORS['surface_container']}
                );
                border: 2px solid {MD3_ENHANCED_COLORS['primary']};
                padding: 13px 19px;
            }}

            /* MD3 风格滚动条 */
            QScrollBar:vertical {{
                background: transparent;
                width: 8px;
                margin: 4px 4px 4px 0px;
                border-radius: 4px;
            }}
            QScrollBar::handle:vertical {{
                background: {MD3_LIGHT_COLORS['outline_variant']};
                border-radius: 4px;
                min-height: 30px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {MD3_LIGHT_COLORS['outline']};
            }}
            QScrollBar::handle:vertical:pressed {{
                background: {MD3_ENHANCED_COLORS['primary']};
            }}
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
            QScrollBar::add-page:vertical,
            QScrollBar::sub-page:vertical {{
                background: none;
            }}
        """)
        
        # 防抖定时器
        self._height_adjust_timer = QTimer()
        self._height_adjust_timer.setSingleShot(True)
        self._height_adjust_timer.setInterval(50)
        self._height_adjust_timer.timeout.connect(self._adjust_height)
        
        # 连接信号
        self.textChanged.connect(lambda: self._height_adjust_timer.start())
        self.textChanged.connect(self.content_changed.emit)
    
    def keyPressEvent(self, event):
        """处理按键事件"""
        # Enter发送，Shift+Enter换行
        if event.key() == Qt.Key.Key_Return or event.key() == Qt.Key.Key_Enter:
            if event.modifiers() == Qt.KeyboardModifier.ShiftModifier:
                # Shift+Enter: 插入换行
                super().keyPressEvent(event)
            else:
                # Enter: 发送消息
                if self.toPlainText().strip() or self.has_images():
                    self.send_requested.emit()
                return
        
        super().keyPressEvent(event)
    
    def _adjust_height(self):
        """自动调整高度"""
        doc_height = self.document().size().height()
        line_height = 24  # 每行约24px
        
        # 计算行数
        lines = max(1, int(doc_height / line_height))
        lines = min(lines, self._max_lines)
        
        # 计算新高度
        if lines == 1:
            new_height = self._single_line_height
        else:
            new_height = self._single_line_height + (lines - 1) * line_height
        
        self.setFixedHeight(new_height)
    
    def insert_emoji(self, emoji: str):
        """插入emoji表情"""
        cursor = self.textCursor()
        cursor.insertText(emoji)
        self.setFocus()
    
    def insert_sticker(self, sticker_path: str):
        """插入表情包图片（内联显示）
        
        Args:
            sticker_path: 表情包文件路径
        """
        try:
            path = Path(sticker_path)
            if not path.exists():
                logger.error(f"表情包文件不存在: {sticker_path}")
                return
            
            # 加载图片
            image = QImage(str(path))
            if image.isNull():
                logger.error(f"无法加载表情包: {sticker_path}")
                return
            
            # 缩放到合适大小（表情包显示为80x80）
            scaled_image = image.scaled(
                80, 80,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            
            # 添加到文档资源
            doc = self.document()
            image_name = f"sticker_{id(sticker_path)}"
            doc.addResource(QTextDocument.ResourceType.ImageResource, image_name, scaled_image)
            
            # 插入图片
            cursor = self.textCursor()
            image_format = QTextImageFormat()
            image_format.setName(image_name)
            image_format.setWidth(80)
            image_format.setHeight(80)
            image_format.setProperty(1000, sticker_path)  # 保存原始路径

            cursor.insertImage(image_format)
            cursor.insertText(" ")  # 添加空格，方便继续输入

            self.setFocus()
            logger.info(f"表情包已插入: {sticker_path}")

        except Exception as e:
            logger.error(f"插入表情包失败: {e}", exc_info=True)

    def has_images(self) -> bool:
        """检查是否包含图片"""
        doc = self.document()
        cursor = QTextCursor(doc)
        cursor.movePosition(QTextCursor.MoveOperation.Start)

        while not cursor.atEnd():
            char_format = cursor.charFormat()
            if char_format.isImageFormat():
                return True
            cursor.movePosition(QTextCursor.MoveOperation.NextCharacter)

        return False

    def get_sticker_paths(self) -> list:
        """获取所有表情包路径"""
        paths = []
        doc = self.document()
        cursor = QTextCursor(doc)
        cursor.movePosition(QTextCursor.MoveOperation.Start)

        while not cursor.atEnd():
            char_format = cursor.charFormat()
            if char_format.isImageFormat():
                image_format = char_format.toImageFormat()
                path = image_format.property(1000)
                if path:
                    paths.append(path)
            cursor.movePosition(QTextCursor.MoveOperation.NextCharacter)

        return paths

    def get_plain_text_without_images(self) -> str:
        """获取纯文本（不包含图片）"""
        text = self.toPlainText()
        # 移除图片占位符（通常是特殊字符）
        text = text.replace('\ufffc', '').strip()
        return text

    def clear_content(self):
        """清空内容"""
        self.clear()
        self.setFixedHeight(self._single_line_height)


class EnhancedInputWidget(QWidget):
    """增强输入框组件 - 包含输入框和文件预览区域

    v2.30.7 新增：
    - 支持内联显示表情包
    - 集成文件预览区域
    - 优化的高度调整
    """

    # 信号
    send_requested = pyqtSignal(str, list, list)  # (文本, 表情包路径列表, 文件路径列表)

    def __init__(self, parent=None):
        super().__init__(parent)

        # 待发送文件列表
        self.pending_files = []

        # 布局
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # 文件预览区域（默认隐藏）
        self.file_preview_container = QWidget()
        self.file_preview_container.setVisible(False)
        self.file_preview_container.setStyleSheet(f"""
            QWidget {{
                background: {MD3_LIGHT_COLORS['surface_container_low']};
                border-radius: 12px;
                padding: 8px;
            }}
        """)

        file_preview_layout = QVBoxLayout(self.file_preview_container)
        file_preview_layout.setContentsMargins(8, 8, 8, 8)
        file_preview_layout.setSpacing(4)

        # 预览标题
        preview_title = QLabel("📎 待发送文件")
        preview_title.setStyleSheet(f"""
            QLabel {{
                color: {MD3_LIGHT_COLORS['on_surface_variant']};
                font-size: 12px;
                font-weight: 500;
            }}
        """)
        file_preview_layout.addWidget(preview_title)

        # 文件预览滚动区域
        self.file_preview_scroll = QScrollArea()
        self.file_preview_scroll.setWidgetResizable(True)
        self.file_preview_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.file_preview_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.file_preview_scroll.setMaximumHeight(120)
        self.file_preview_scroll.setStyleSheet("""
            QScrollArea {
                border: none;
                background: transparent;
            }
        """)

        # 文件预览内容
        file_preview_content = QWidget()
        self.file_preview_content_layout = QHBoxLayout(file_preview_content)
        self.file_preview_content_layout.setContentsMargins(0, 0, 0, 0)
        self.file_preview_content_layout.setSpacing(8)
        self.file_preview_content_layout.addStretch()

        self.file_preview_scroll.setWidget(file_preview_content)
        file_preview_layout.addWidget(self.file_preview_scroll)

        layout.addWidget(self.file_preview_container)

        # 富文本输入框
        self.input_text = RichTextInput()
        self.input_text.send_requested.connect(self._on_send_requested)
        layout.addWidget(self.input_text)

    def insert_emoji(self, emoji: str):
        """插入emoji"""
        self.input_text.insert_emoji(emoji)

    def insert_sticker(self, sticker_path: str):
        """插入表情包"""
        self.input_text.insert_sticker(sticker_path)

    def add_file(self, file_path: str):
        """添加文件到预览区域

        Args:
            file_path: 文件路径
        """
        if file_path in self.pending_files:
            logger.debug(f"文件已在待发送列表中: {file_path}")
            return

        self.pending_files.append(file_path)

        # 创建文件预览项
        preview_item = self._create_file_preview_item(file_path)

        # 添加到预览区域
        self.file_preview_content_layout.insertWidget(
            self.file_preview_content_layout.count() - 1,
            preview_item
        )

        # 显示预览区域
        self.file_preview_container.setVisible(True)

        logger.info(f"添加文件: {file_path}, 当前共 {len(self.pending_files)} 个")

    def _create_file_preview_item(self, file_path: str) -> QWidget:
        """创建文件预览项

        Args:
            file_path: 文件路径

        Returns:
            预览项widget
        """
        preview_item = QWidget()
        preview_item.setFixedSize(90, 90)
        preview_item.setProperty("file_path", file_path)

        item_layout = QVBoxLayout(preview_item)
        item_layout.setContentsMargins(0, 0, 0, 0)
        item_layout.setSpacing(0)

        # 文件容器
        file_container = QWidget()
        file_container.setFixedSize(90, 70)
        file_container_layout = QVBoxLayout(file_container)
        file_container_layout.setContentsMargins(0, 0, 0, 0)

        # 加载并显示缩略图
        file_label = QLabel()
        pixmap = QPixmap(file_path)
        if not pixmap.isNull():
            scaled_pixmap = pixmap.scaled(
                90, 70,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            file_label.setPixmap(scaled_pixmap)
            file_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        else:
            # 非图片文件，显示文件名
            file_name = Path(file_path).name
            file_label.setText(file_name[:10] + "..." if len(file_name) > 10 else file_name)
            file_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            file_label.setWordWrap(True)

        file_label.setStyleSheet(f"""
            QLabel {{
                background: {MD3_LIGHT_COLORS['surface_container']};
                border: 2px solid {MD3_LIGHT_COLORS['outline_variant']};
                border-radius: 8px;
                color: {MD3_LIGHT_COLORS['on_surface']};
                font-size: 11px;
                padding: 4px;
            }}
        """)
        file_container_layout.addWidget(file_label)
        item_layout.addWidget(file_container)

        # 删除按钮
        remove_btn = QPushButton("×")
        remove_btn.setFixedSize(90, 20)
        remove_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        remove_btn.setStyleSheet(f"""
            QPushButton {{
                background: {MD3_LIGHT_COLORS['error']};
                color: {MD3_LIGHT_COLORS['on_error']};
                border: none;
                border-radius: 4px;
                font-size: 16px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background: {MD3_LIGHT_COLORS['error_light']};
            }}
        """)
        remove_btn.clicked.connect(lambda: self._remove_file(file_path, preview_item))
        item_layout.addWidget(remove_btn)

        return preview_item

    def _remove_file(self, file_path: str, preview_item: QWidget):
        """移除文件

        Args:
            file_path: 文件路径
            preview_item: 预览项widget
        """
        if file_path in self.pending_files:
            self.pending_files.remove(file_path)

        # 移除预览项
        self.file_preview_content_layout.removeWidget(preview_item)
        preview_item.deleteLater()

        # 如果没有文件了，隐藏预览区域
        if not self.pending_files:
            self.file_preview_container.setVisible(False)

        logger.info(f"移除文件: {file_path}, 剩余 {len(self.pending_files)} 个")

    def _on_send_requested(self):
        """发送请求"""
        # 获取纯文本
        text = self.input_text.get_plain_text_without_images()

        # 获取表情包路径
        sticker_paths = self.input_text.get_sticker_paths()

        # 获取文件路径
        file_paths = self.pending_files.copy()

        # 发送信号
        self.send_requested.emit(text, sticker_paths, file_paths)

        # 清空内容
        self.clear_all()

    def clear_all(self):
        """清空所有内容"""
        # 清空输入框
        self.input_text.clear_content()

        # 清空文件列表
        for file_path in self.pending_files.copy():
            # 查找并移除预览项
            for i in range(self.file_preview_content_layout.count()):
                item = self.file_preview_content_layout.itemAt(i)
                if item and item.widget():
                    widget = item.widget()
                    if widget.property("file_path") == file_path:
                        self.file_preview_content_layout.removeWidget(widget)
                        widget.deleteLater()
                        break

        self.pending_files.clear()
        self.file_preview_container.setVisible(False)

    def get_text(self) -> str:
        """获取纯文本"""
        return self.input_text.get_plain_text_without_images()

    def has_content(self) -> bool:
        """检查是否有内容"""
        return bool(self.get_text().strip() or
                   self.input_text.has_images() or
                   self.pending_files)

