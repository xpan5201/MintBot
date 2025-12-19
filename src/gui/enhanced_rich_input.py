"""
MintChat - 增强富文本输入框

支持内联显示表情包和文件预览的输入框组件

v2.30.7 新增
"""

from PyQt6.QtWidgets import (
    QWidget,
    QTextEdit,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QAbstractScrollArea,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
)
from PyQt6.QtCore import (
    Qt,
    pyqtSignal,
    QSize,
    QTimer,
    QUrl,
    QEvent,
    QRectF,
    QPointF,
    pyqtProperty,
    QPropertyAnimation,
    QEasingCurve,
)
from PyQt6.QtGui import (
    QTextCursor,
    QTextDocument,
    QTextImageFormat,
    QImage,
    QPixmap,
    QPainter,
    QTextCharFormat,
    QImageReader,
    QColor,
    QFont,
    QPen,
)
from pathlib import Path
from functools import lru_cache
from datetime import datetime
import uuid
from src.utils.logger import get_logger

from src.gui.material_design_light import MD3_LIGHT_COLORS
from src.gui.material_design_enhanced import MD3_ENHANCED_COLORS, MD3_ENHANCED_RADIUS
from src.gui.qss_utils import qss_rgba

logger = get_logger(__name__)


_INLINE_STICKER_SIZE = 80
_ATTACHMENT_THUMBNAIL_SIZE = (72, 52)
_SUPPORTED_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}


@lru_cache(maxsize=128)
def _load_inline_sticker_image(path: str, size: int, mtime_ns: int) -> QImage:
    """加载并缩放用于输入框内联显示的表情包（缓存）。"""
    _ = mtime_ns  # 仅用于缓存键，文件变更时自动失效
    image = QImage(path)
    if image.isNull():
        return QImage()
    return image.scaled(
        size,
        size,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )


@lru_cache(maxsize=256)
def _load_attachment_thumbnail_pixmap(
    path: str,
    max_width: int,
    max_height: int,
    mtime_ns: int,
) -> QPixmap:
    """加载并缩放附件缩略图（缓存，避免反复解码大图）。"""
    _ = mtime_ns  # 仅用于缓存键，文件变更时自动失效
    try:
        reader = QImageReader(path)
        reader.setAutoTransform(True)
        size = reader.size()
        if size.isValid():
            target = QSize(max_width, max_height)
            reader.setScaledSize(size.scaled(target, Qt.AspectRatioMode.KeepAspectRatio))
        image = reader.read()
        if image.isNull():
            return QPixmap()
        return QPixmap.fromImage(image)
    except Exception:
        return QPixmap()


class RichTextInput(QTextEdit):
    """支持富文本的输入框 - 可内联显示图片"""
    
    # 信号
    send_requested = pyqtSignal()  # 请求发送
    content_changed = pyqtSignal()  # 内容改变
    files_pasted = pyqtSignal(list)  # 粘贴的文件路径列表（用于“粘贴图片即附件”）
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # 配置
        self.setAcceptRichText(True)  # 支持富文本
        # ChatGPT 风格：更短的占位文案（快捷键提示放到 tooltip）
        self.setPlaceholderText("询问任何问题")
        self.setToolTip("Enter 发送 · Shift+Enter 换行")
        self.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # 性能：减少输入/高度变化时的无效重绘
        try:
            if hasattr(self, "setViewportUpdateMode"):
                self.setViewportUpdateMode(QAbstractScrollArea.ViewportUpdateMode.MinimalViewportUpdate)
        except Exception:
            pass
        
        # 高度设置
        self._single_line_height = 56
        self._max_lines = 4
        self.setFixedHeight(self._single_line_height)
        
        # ChatGPT 风格：输入框本身透明/无边框，由外层 Card 负责边框与圆角
        self.setStyleSheet(f"""
            QTextEdit {{
                background: transparent;
                border: none;
                padding: 10px 3px;
                font-size: 15px;
                color: {MD3_ENHANCED_COLORS['on_surface']};
                line-height: 1.5;
            }}
            QTextEdit:focus {{
                background: transparent;
                border: none;
            }}

            /* 轻量滚动条（仅在超过最大行数时出现） */
            QScrollBar:vertical {{
                background: transparent;
                width: 6px;
                margin: 4px 2px 4px 0px;
                border-radius: 3px;
            }}
            QScrollBar::handle:vertical {{
                background: {MD3_ENHANCED_COLORS['outline_variant']};
                border-radius: 3px;
                min-height: 30px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {MD3_ENHANCED_COLORS['outline']};
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
        self._height_adjust_timer = QTimer(self)
        self._height_adjust_timer.setSingleShot(True)
        self._height_adjust_timer.setInterval(50)
        self._height_adjust_timer.timeout.connect(self._adjust_height)
        
        # 连接信号
        self.textChanged.connect(lambda: self._height_adjust_timer.start())
        self.textChanged.connect(self.content_changed.emit)

        # 资源跟踪：QTextDocument 会缓存 addResource() 的图片；长时间使用可能导致内存增长。
        # 这里记录插入过的资源 key，便于在 clear_content() 时显式释放图片数据。
        self._image_resource_keys: set[str] = set()
    
    def keyPressEvent(self, event):
        """处理按键事件"""
        # Enter发送，Shift+Enter换行
        if event.key() == Qt.Key.Key_Return or event.key() == Qt.Key.Key_Enter:
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                # Shift+Enter: 插入换行
                super().keyPressEvent(event)
            else:
                # Enter: 发送消息（是否允许发送由上层根据文本/表情包/附件决定）
                self.send_requested.emit()
                return
        
        super().keyPressEvent(event)

    def _persist_pasted_image(self, image: QImage) -> str:
        try:
            from src.config.settings import settings as runtime_settings

            base = Path(getattr(runtime_settings, "data_dir", "./data") or "./data")
        except Exception:
            base = Path("./data")

        target_dir = base / "images" / "pasted"
        target_dir.mkdir(parents=True, exist_ok=True)

        max_dim = 2048
        try:
            if max(image.width(), image.height()) > max_dim:
                image = image.scaled(
                    max_dim,
                    max_dim,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
        except Exception:
            pass

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        name = f"paste_{stamp}_{uuid.uuid4().hex[:10]}.png"
        path = target_dir / name
        ok = image.save(str(path), "PNG")
        return str(path) if ok else ""

    def insertFromMimeData(self, source):  # noqa: N802 - Qt API naming
        try:
            if source is None:
                return super().insertFromMimeData(source)

            file_paths: list[str] = []
            url_paths: list[str] = []
            try:
                if source.hasUrls():
                    for url in source.urls():
                        try:
                            local = url.toLocalFile()
                        except Exception:
                            local = ""
                        if local and Path(local).suffix.lower() in _SUPPORTED_IMAGE_EXTS:
                            url_paths.append(local)
            except Exception:
                pass

            try:
                if source.hasImage():
                    raw = source.imageData()
                    if isinstance(raw, QImage):
                        image = raw
                    elif isinstance(raw, QPixmap):
                        image = raw.toImage()
                    else:
                        image = QImage(raw)
                    if not image.isNull():
                        path = self._persist_pasted_image(image)
                        if path:
                            file_paths = [path]
            except Exception:
                pass

            if not file_paths and url_paths:
                file_paths = url_paths

            if file_paths:
                dedup: list[str] = []
                seen: set[str] = set()
                for p in file_paths:
                    key = str(p or "").strip()
                    if not key or key in seen:
                        continue
                    seen.add(key)
                    dedup.append(key)
                if dedup:
                    self.files_pasted.emit(dedup)
                self.setFocus()
                return
        except Exception:
            pass

        super().insertFromMimeData(source)
    
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

            try:
                mtime_ns = path.stat().st_mtime_ns
            except OSError:
                mtime_ns = 0
             
            # 加载图片
            scaled_image = _load_inline_sticker_image(str(path), _INLINE_STICKER_SIZE, mtime_ns)
            if scaled_image.isNull():
                logger.error(f"无法加载表情包: {sticker_path}")
                return
             
            # 添加到文档资源
            doc = self.document()
            resource_url = QUrl.fromLocalFile(str(path))
            resource_url.setQuery(f"inline=1&size={_INLINE_STICKER_SIZE}&mtime={mtime_ns}")
            resource_key = resource_url.toString()
            if resource_key not in self._image_resource_keys:
                doc.addResource(QTextDocument.ResourceType.ImageResource, resource_url, scaled_image)
                self._image_resource_keys.add(resource_key)
             
            # 插入图片
            cursor = self.textCursor()
            image_format = QTextImageFormat()
            image_format.setName(resource_url.toString())
            image_format.setWidth(_INLINE_STICKER_SIZE)
            image_format.setHeight(_INLINE_STICKER_SIZE)
            image_format.setProperty(1000, sticker_path)  # 保存原始路径
 
            cursor.insertImage(image_format)
            # v2.46.x: 确保后续文本不继承图片格式，避免 get_sticker_paths() 误判为重复表情包
            cursor.insertText(" ", QTextCharFormat())  # 添加空格，方便继续输入

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
        paths: list[str] = []
        doc = self.document()
        cursor = QTextCursor(doc)
        cursor.movePosition(QTextCursor.MoveOperation.Start)

        # v2.46.x: 防止图片格式“泄漏”到后续字符导致同一表情包被重复读取。
        # 仅在“连续的 imageFormat 且 path 相同”时去重，仍保留用户主动插入两次同一表情包的语义。
        prev_was_image = False
        prev_path = None

        while not cursor.atEnd():
            char_format = cursor.charFormat()
            if char_format.isImageFormat():
                image_format = char_format.toImageFormat()
                path = image_format.property(1000)
                if path:
                    try:
                        path = str(path)
                    except Exception:
                        path = None
                if path and not (prev_was_image and prev_path == path):
                    paths.append(path)
                    prev_path = path
                prev_was_image = True if path else False
            else:
                prev_was_image = False
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
        # 释放已插入过的图片资源（避免 QTextDocument 资源缓存无限增长）
        try:
            doc = self.document()
            for resource_key in list(self._image_resource_keys):
                try:
                    doc.addResource(
                        QTextDocument.ResourceType.ImageResource,
                        QUrl(resource_key),
                        QImage(),
                    )
                except Exception:
                    pass
            self._image_resource_keys.clear()
        except Exception:
            pass

        self.clear()
        self.setFixedHeight(self._single_line_height)


class ChatComposerIconButton(QPushButton):
    """ChatGPT 风格圆形动作按钮（轻量 hover/press 动画，自绘以保证圆角稳定）。"""

    VARIANT_GHOST = "ghost"
    VARIANT_FILLED = "filled"

    def __init__(
        self,
        icon: str,
        tooltip: str,
        *,
        size: int = 44,
        icon_size: int = 20,
        variant: str = VARIANT_GHOST,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._icon = str(icon or "")
        self._size = int(size)
        self._icon_size = int(icon_size)
        self._variant = str(variant or self.VARIANT_GHOST)

        self._hover_t = 0.0
        self._press_t = 0.0
        self._active = False

        self.setToolTip(tooltip)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setFixedSize(self._size, self._size)
        self.setFlat(True)

        self._icon_font = QFont("Material Symbols Outlined")
        self._icon_font.setPixelSize(self._icon_size)

        self._hover_anim = QPropertyAnimation(self, b"hover_t", self)
        self._hover_anim.setDuration(120)
        self._hover_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._press_anim = QPropertyAnimation(self, b"press_t", self)
        self._press_anim.setDuration(90)
        self._press_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    def set_icon(self, icon: str) -> None:
        """Update the Material Symbols icon name (repaint-only)."""
        self._icon = str(icon or "")
        self.update()

    def set_active(self, active: bool) -> None:
        self._active = bool(active)
        self.update()

    @pyqtProperty(float)
    def hover_t(self) -> float:
        return float(self._hover_t)

    @hover_t.setter
    def hover_t(self, value: float) -> None:
        self._hover_t = max(0.0, min(1.0, float(value)))
        self.update()

    @pyqtProperty(float)
    def press_t(self) -> float:
        return float(self._press_t)

    @press_t.setter
    def press_t(self, value: float) -> None:
        self._press_t = max(0.0, min(1.0, float(value)))
        self.update()

    def _start_anim(self, anim: QPropertyAnimation, end_value: float) -> None:
        anim.stop()
        if anim is self._hover_anim:
            anim.setStartValue(float(self._hover_t))
        else:
            anim.setStartValue(float(self._press_t))
        anim.setEndValue(float(end_value))
        anim.start()

    def enterEvent(self, event):  # noqa: N802 - Qt API naming
        super().enterEvent(event)
        self._start_anim(self._hover_anim, 1.0)

    def leaveEvent(self, event):  # noqa: N802 - Qt API naming
        super().leaveEvent(event)
        self._start_anim(self._hover_anim, 0.0)

    def mousePressEvent(self, event):  # noqa: N802 - Qt API naming
        if event.button() == Qt.MouseButton.LeftButton:
            self._start_anim(self._press_anim, 1.0)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):  # noqa: N802 - Qt API naming
        if event.button() == Qt.MouseButton.LeftButton:
            self._start_anim(self._press_anim, 0.0)
        super().mouseReleaseEvent(event)

    def paintEvent(self, _event):  # noqa: N802 - Qt API naming
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        rect = QRectF(0.5, 0.5, self.width() - 1.0, self.height() - 1.0)
        inset = 1.2 * self._press_t
        circle = rect.adjusted(inset, inset, -inset, -inset)

        enabled = self.isEnabled()

        if self._variant == self.VARIANT_FILLED:
            if enabled:
                bg = QColor(MD3_ENHANCED_COLORS["on_surface"])
            else:
                bg = QColor(MD3_ENHANCED_COLORS["outline_variant"])
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(bg)
            painter.drawEllipse(circle)

            icon_color = (
                QColor(MD3_ENHANCED_COLORS["surface_bright"])
                if enabled
                else QColor(MD3_ENHANCED_COLORS["on_surface_variant"])
            )
        else:
            # Ghost: only draw subtle background on hover/press
            hover_alpha = int(22 * self._hover_t)
            press_alpha = int(30 * self._press_t)
            alpha = max(hover_alpha, press_alpha)
            if alpha > 0:
                bg = QColor(MD3_ENHANCED_COLORS["on_surface"])
                bg.setAlpha(alpha)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(bg)
                painter.drawEllipse(circle)

            # Subtle outline so the button keeps its circular shape even at rest
            outline = QColor(MD3_ENHANCED_COLORS["outline_variant"])
            outline.setAlpha(190 if enabled else 120)
            painter.setPen(QPen(outline, 1.0))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(circle)

            icon_color = QColor(
                MD3_ENHANCED_COLORS["on_surface_variant"] if enabled else MD3_ENHANCED_COLORS["outline"]
            )
            if self._hover_t > 0.5 and enabled:
                icon_color = QColor(MD3_ENHANCED_COLORS["on_surface"])

            # Active (toggled) state: slightly stronger outline + subtle tint.
            if self._active and enabled:
                try:
                    tint = QColor(MD3_ENHANCED_COLORS.get("primary", MD3_ENHANCED_COLORS["on_surface"]))
                    tint.setAlpha(26)
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.setBrush(tint)
                    painter.drawEllipse(circle)

                    outline2 = QColor(MD3_ENHANCED_COLORS.get("primary", MD3_ENHANCED_COLORS["on_surface"]))
                    outline2.setAlpha(210)
                    painter.setPen(QPen(outline2, 1.2))
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    painter.drawEllipse(circle)
                    icon_color = QColor(MD3_ENHANCED_COLORS.get("primary", MD3_ENHANCED_COLORS["on_surface"]))
                except Exception:
                    pass

        painter.setPen(QPen(icon_color, 1.0))
        painter.setFont(self._icon_font)
        painter.drawText(circle, Qt.AlignmentFlag.AlignCenter, self._icon)


class EnhancedInputWidget(QWidget):
    """增强输入框组件 - 包含输入框和文件预览区域

    v2.30.7 新增：
    - 支持内联显示表情包
    - 集成文件预览区域
    - 优化的高度调整
    """

    # 信号
    send_requested = pyqtSignal(str, list, list)  # (文本, 表情包路径列表, 文件路径列表)
    content_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self.pending_files: list[str] = []
        self._card_hovered = False
        self._card_focused = False
        self._card_dragging = False
        self._card_style_cache: dict[tuple[bool, bool, bool], str] = {}
        self._card_style_key: tuple[bool, bool, bool] | None = None

        self.setAcceptDrops(True)

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # ChatGPT 风格输入卡片：圆角 + 细边框 + 内边距（避免 DropShadowEffect，降低键入时离屏渲染开销）
        self.card = QWidget()
        self.card.setObjectName("composerCard")
        try:
            self.card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        except Exception:
            pass
        self.card.installEventFilter(self)

        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(8, 8, 8, 8)
        card_layout.setSpacing(4)

        # 文件预览区域（默认隐藏，位于输入框内部顶部，类似 ChatGPT Web）
        self.file_preview_container = QWidget()
        self.file_preview_container.setVisible(False)
        self.file_preview_container.setStyleSheet("background: transparent;")
        try:
            self.file_preview_container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            self.file_preview_container.setFixedHeight(64)
        except Exception:
            pass

        file_preview_layout = QVBoxLayout(self.file_preview_container)
        file_preview_layout.setContentsMargins(0, 0, 0, 0)
        file_preview_layout.setSpacing(0)

        self.file_preview_scroll = QScrollArea()
        self.file_preview_scroll.setWidgetResizable(True)
        # 性能：附件预览区域的滚动/更新尽量做最小重绘
        try:
            if hasattr(self.file_preview_scroll, "setViewportUpdateMode"):
                self.file_preview_scroll.setViewportUpdateMode(
                    QAbstractScrollArea.ViewportUpdateMode.MinimalViewportUpdate
                )
        except Exception:
            pass
        self.file_preview_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.file_preview_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.file_preview_scroll.setFixedHeight(64)
        self.file_preview_scroll.setStyleSheet(
            """
            QScrollArea {
                border: none;
                background: transparent;
            }
            QScrollBar:horizontal {
                height: 0px;
            }
            """
        )

        file_preview_content = QWidget()
        self.file_preview_content_layout = QHBoxLayout(file_preview_content)
        self.file_preview_content_layout.setContentsMargins(0, 0, 0, 0)
        self.file_preview_content_layout.setSpacing(10)
        self.file_preview_content_layout.addStretch()
        self.file_preview_scroll.setWidget(file_preview_content)
        file_preview_layout.addWidget(self.file_preview_scroll)
        card_layout.addWidget(self.file_preview_container)

        # 附件区与输入区分隔线（仅在有附件时显示）
        self._attachments_divider = QWidget()
        self._attachments_divider.setFixedHeight(1)
        self._attachments_divider.setVisible(False)
        self._attachments_divider.setStyleSheet(
            f"background: {qss_rgba(MD3_ENHANCED_COLORS['outline_variant'], 0.9)};"
        )
        card_layout.addWidget(self._attachments_divider)

        # 底部输入行：+ | 输入框 | mic | send
        input_row = QHBoxLayout()
        input_row.setContentsMargins(0, 0, 0, 0)
        input_row.setSpacing(6)

        self.plus_btn = ChatComposerIconButton(
            "add",
            "更多",
            size=38,
            icon_size=19,
            variant=ChatComposerIconButton.VARIANT_GHOST,
        )
        input_row.addWidget(self.plus_btn, 0, Qt.AlignmentFlag.AlignBottom)

        self.input_text = RichTextInput()
        self.input_text.send_requested.connect(self._on_send_requested)
        self.input_text.content_changed.connect(self._emit_content_changed_debounced)
        self.input_text.files_pasted.connect(self._on_files_pasted)
        self.input_text.installEventFilter(self)
        self.input_text.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        input_row.addWidget(self.input_text, 1)

        self.mic_btn = ChatComposerIconButton(
            "mic",
            "语音输入（开发中）",
            size=38,
            icon_size=19,
            variant=ChatComposerIconButton.VARIANT_GHOST,
        )
        input_row.addWidget(self.mic_btn, 0, Qt.AlignmentFlag.AlignBottom)

        self.send_btn = ChatComposerIconButton(
            "send",
            "发送",
            size=38,
            icon_size=19,
            variant=ChatComposerIconButton.VARIANT_FILLED,
        )
        self.send_btn.clicked.connect(self.input_text.send_requested.emit)
        input_row.addWidget(self.send_btn, 0, Qt.AlignmentFlag.AlignBottom)

        card_layout.addLayout(input_row)
        root_layout.addWidget(self.card)

        try:
            self.card.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
            self.card.setFocusProxy(self.input_text)
            self.setFocusProxy(self.input_text)
        except Exception:
            pass

        try:
            self.file_preview_scroll.viewport().installEventFilter(self)
        except Exception:
            pass

        # 初始状态同步
        self._update_card_style()
        self._emit_content_changed_debounced()

    def _build_card_stylesheet(self, *, focused: bool, hovered: bool, dragging: bool) -> str:
        radius = MD3_ENHANCED_RADIUS["extra_large"]
        outline_soft = qss_rgba(MD3_ENHANCED_COLORS["outline_variant"], 0.9)
        outline_hover = qss_rgba(MD3_ENHANCED_COLORS["outline"], 0.95)
        primary_soft = qss_rgba(MD3_ENHANCED_COLORS["primary"], 0.85)
        if dragging:
            border = primary_soft
            border_style = "dashed"
            bg = MD3_ENHANCED_COLORS["frosted_glass_medium"]
        elif focused:
            border = primary_soft
            border_style = "solid"
            bg = MD3_ENHANCED_COLORS["surface_bright"]
        else:
            border = outline_hover if hovered else outline_soft
            border_style = "solid"
            bg = (
                MD3_ENHANCED_COLORS["frosted_glass_medium"]
                if hovered
                else MD3_ENHANCED_COLORS["frosted_glass_light"]
            )
        return f"""
            QWidget#composerCard {{
                background: {bg};
                border: 1px {border_style} {border};
                border-radius: {radius};
            }}
        """

    def _update_card_style(self) -> None:
        try:
            key = (bool(self._card_focused), bool(self._card_hovered), bool(self._card_dragging))
            if key == self._card_style_key:
                return
            style = self._card_style_cache.get(key)
            if style is None:
                style = self._build_card_stylesheet(focused=key[0], hovered=key[1], dragging=key[2])
                self._card_style_cache[key] = style
            self.card.setStyleSheet(style)
            self._card_style_key = key
        except Exception:
            pass

    def _emit_content_changed_debounced(self, *_args) -> None:
        try:
            timer = getattr(self, "_content_changed_timer", None)
            if timer is None:
                timer = QTimer(self)
                timer.setSingleShot(True)
                # 性能：键入时合并多次变化，避免每个字符都触发上层 enable/disable 与布局检查
                timer.setInterval(40)
                timer.timeout.connect(self.content_changed.emit)
                self._content_changed_timer = timer
            timer.start()
        except Exception:
            self.content_changed.emit()

    def eventFilter(self, obj, event):  # noqa: N802 - Qt API naming
        try:
            if obj is self.input_text:
                if event.type() == QEvent.Type.FocusIn:
                    self._card_focused = True
                    self._update_card_style()
                elif event.type() == QEvent.Type.FocusOut:
                    self._card_focused = False
                    self._update_card_style()
            elif obj is self.card:
                if event.type() == QEvent.Type.Enter:
                    self._card_hovered = True
                    self._update_card_style()
                elif event.type() == QEvent.Type.Leave:
                    self._card_hovered = False
                    self._update_card_style()
                elif event.type() == QEvent.Type.MouseButtonPress:
                    try:
                        self.input_text.setFocus()
                    except Exception:
                        pass
            elif (
                hasattr(self, "file_preview_scroll")
                and self.file_preview_scroll is not None
                and obj is self.file_preview_scroll.viewport()
                and event.type() == QEvent.Type.Wheel
            ):
                delta = 0
                try:
                    pixel = event.pixelDelta()
                    delta = int(pixel.x() or pixel.y() or 0)
                except Exception:
                    delta = 0
                if not delta:
                    try:
                        delta = int(event.angleDelta().y() / 2)
                    except Exception:
                        delta = 0
                try:
                    hbar = self.file_preview_scroll.horizontalScrollBar()
                    hbar.setValue(hbar.value() - int(delta))
                except Exception:
                    pass
                return True
        except Exception:
            pass
        return super().eventFilter(obj, event)

    def dragEnterEvent(self, event):  # noqa: N802 - Qt API naming
        try:
            mime = event.mimeData()
            if mime and mime.hasUrls():
                for url in mime.urls():
                    try:
                        path = url.toLocalFile()
                    except Exception:
                        path = ""
                    if path and Path(path).suffix.lower() in _SUPPORTED_IMAGE_EXTS:
                        self._card_dragging = True
                        self._update_card_style()
                        event.acceptProposedAction()
                        return
        except Exception:
            pass
        super().dragEnterEvent(event)

    def dragLeaveEvent(self, event):  # noqa: N802 - Qt API naming
        try:
            self._card_dragging = False
            self._update_card_style()
        except Exception:
            pass
        super().dragLeaveEvent(event)

    def dropEvent(self, event):  # noqa: N802 - Qt API naming
        try:
            mime = event.mimeData()
            if not (mime and mime.hasUrls()):
                super().dropEvent(event)
                return
            for url in mime.urls():
                try:
                    path = url.toLocalFile()
                except Exception:
                    continue
                if not path:
                    continue
                if Path(path).suffix.lower() in _SUPPORTED_IMAGE_EXTS:
                    self.add_file(path)
            self._card_dragging = False
            self._update_card_style()
            event.acceptProposedAction()
            return
        except Exception:
            try:
                self._card_dragging = False
                self._update_card_style()
            except Exception:
                pass
            super().dropEvent(event)

    def _on_files_pasted(self, file_paths: list[str]) -> None:
        try:
            for file_path in file_paths or []:
                if file_path and Path(file_path).suffix.lower() in _SUPPORTED_IMAGE_EXTS:
                    self.add_file(file_path)
        except Exception:
            pass

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
        try:
            self._attachments_divider.setVisible(True)
        except Exception:
            pass
        self._emit_content_changed_debounced()

        logger.info(f"添加文件: {file_path}, 当前共 {len(self.pending_files)} 个")

    def remove_file(self, file_path: str) -> None:
        """按路径移除一个已添加的文件预览。"""
        file_path = str(file_path or "").strip()
        if not file_path:
            return
        if file_path not in self.pending_files:
            return

        preview_item: QWidget | None = None
        try:
            for i in range(self.file_preview_content_layout.count()):
                item = self.file_preview_content_layout.itemAt(i)
                widget = item.widget() if item else None
                if widget is not None and widget.property("file_path") == file_path:
                    preview_item = widget
                    break
        except Exception:
            preview_item = None

        if preview_item is not None:
            self._remove_file(file_path, preview_item)
            return

        try:
            self.pending_files.remove(file_path)
        except ValueError:
            return
        if not self.pending_files:
            self.file_preview_container.setVisible(False)
            try:
                self._attachments_divider.setVisible(False)
            except Exception:
                pass
        self._emit_content_changed_debounced()

    def _create_file_preview_item(self, file_path: str) -> QWidget:
        """创建文件预览项

        Args:
            file_path: 文件路径

        Returns:
            预览项widget
        """
        preview_item = QWidget()
        preview_item.setFixedSize(84, 64)
        preview_item.setProperty("file_path", file_path)

        item_layout = QGridLayout(preview_item)
        item_layout.setContentsMargins(0, 0, 0, 0)
        item_layout.setHorizontalSpacing(0)
        item_layout.setVerticalSpacing(0)

        file_container = QWidget()
        file_container.setObjectName("composerAttachmentCard")
        file_container.setFixedSize(84, 64)
        file_container.setStyleSheet(
            f"""
            QWidget#composerAttachmentCard {{
                background: {MD3_ENHANCED_COLORS['surface_container_low']};
                border: 1px solid {MD3_ENHANCED_COLORS['outline_variant']};
                border-radius: {MD3_ENHANCED_RADIUS['large']};
            }}
            """
        )
        file_container_layout = QVBoxLayout(file_container)
        file_container_layout.setContentsMargins(6, 6, 6, 6)

        file_label = QLabel()
        suffix = Path(file_path).suffix.lower()
        if suffix in _SUPPORTED_IMAGE_EXTS:
            try:
                mtime_ns = Path(file_path).stat().st_mtime_ns
            except OSError:
                mtime_ns = 0
            w, h = _ATTACHMENT_THUMBNAIL_SIZE
            pixmap = _load_attachment_thumbnail_pixmap(file_path, w, h, mtime_ns)
            if not pixmap.isNull():
                file_label.setPixmap(pixmap)
                file_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            else:
                file_name = Path(file_path).name
                file_label.setText(file_name[:10] + "..." if len(file_name) > 10 else file_name)
                file_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                file_label.setWordWrap(True)
        else:
            file_name = Path(file_path).name
            file_label.setText(file_name[:10] + "..." if len(file_name) > 10 else file_name)
            file_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            file_label.setWordWrap(True)

        file_label.setStyleSheet(
            f"""
            QLabel {{
                background: transparent;
                border: none;
                color: {MD3_ENHANCED_COLORS['on_surface']};
                font-size: 11px;
            }}
            """
        )
        file_container_layout.addWidget(file_label)
        item_layout.addWidget(file_container, 0, 0)

        remove_btn = QPushButton("×", preview_item)
        remove_btn.setFixedSize(18, 18)
        remove_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        remove_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        remove_btn.setStyleSheet(
            f"""
            QPushButton {{
                background: rgba(0, 0, 0, 100);
                color: {MD3_ENHANCED_COLORS['surface_bright']};
                border: none;
                border-radius: {MD3_ENHANCED_RADIUS['circle']};
                font-size: 12px;
                font-weight: 700;
            }}
            QPushButton:hover {{
                background: rgba(0, 0, 0, 140);
            }}
            QPushButton:pressed {{
                background: rgba(0, 0, 0, 170);
            }}
            """
        )
        remove_btn.clicked.connect(lambda: self._remove_file(file_path, preview_item))
        item_layout.addWidget(remove_btn, 0, 0, Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight)

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
            try:
                self._attachments_divider.setVisible(False)
            except Exception:
                pass
        self._emit_content_changed_debounced()

        logger.info(f"移除文件: {file_path}, 剩余 {len(self.pending_files)} 个")

    def _on_send_requested(self):
        """发送请求"""
        # 获取纯文本
        text = self.input_text.get_plain_text_without_images()

        # 获取表情包路径
        sticker_paths = self.input_text.get_sticker_paths()

        # 获取文件路径
        file_paths = self.pending_files.copy()

        # 没有任何内容时不发送（避免空触发）
        if not (text.strip() or sticker_paths or file_paths):
            return

        # 发送信号
        self.send_requested.emit(text, sticker_paths, file_paths)

        # 清空由上层决定（例如 Agent 未就绪时应保留输入内容）

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
        try:
            self._attachments_divider.setVisible(False)
        except Exception:
            pass
        self._emit_content_changed_debounced()

    def get_text(self) -> str:
        """获取纯文本"""
        return self.input_text.get_plain_text_without_images()

    def has_content(self) -> bool:
        """检查是否有内容"""
        return bool(self.get_text().strip() or
                   self.input_text.has_images() or
                   self.pending_files)
