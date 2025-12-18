"""设置面板组件（Material Design 3、卡片式布局、性能优化、流畅动画、实时预览、输入验证）"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTabWidget, QStackedWidget,
    QLabel, QLineEdit, QTextEdit, QPushButton, QCheckBox,
    QSpinBox, QDoubleSpinBox, QComboBox, QScrollArea,
    QGroupBox, QFormLayout, QMessageBox, QFileDialog, QGraphicsDropShadowEffect
)
from PyQt6.QtCore import Qt, pyqtSignal, QPropertyAnimation, pyqtProperty, QTimer, QEasingCurve
from PyQt6.QtGui import QPixmap, QPainter, QPainterPath, QColor

from src.gui.material_design_light import MD3_LIGHT_COLORS, MD3_RADIUS
from src.gui.material_design_enhanced import (
    MD3_ENHANCED_COLORS, MD3_ENHANCED_SPACING, MD3_ENHANCED_RADIUS,
    MD3_ENHANCED_DURATION, MD3_ENHANCED_EASING,
    get_typography_css
)
from src.gui.material_icons import MaterialIconButton, MATERIAL_ICONS
from src.auth.user_session import user_session
import yaml
from pathlib import Path
from src.utils.logger import get_logger

logger = get_logger(__name__)


class SettingsPanel(QWidget):
    """设置面板（个人资料、LLM配置、Agent配置、记忆系统、系统配置）"""

    settings_saved = pyqtSignal()
    back_clicked = pyqtSignal()

    def __init__(self, agent=None, parent=None):
        super().__init__(parent)

        self.agent = agent
        self.config_data = {}
        self._opacity = 1.0
        self.user_avatar_preview = None
        self.ai_avatar_preview = None
        self._is_saving = False
        self._has_unsaved_changes = False
        self._suppress_unsaved_changes = False
        self.memory_manager_window = None
        self._pending_page_builds: set[int] = set()
        self._page_titles = ["个人资料", "模型服务", "角色配置", "记忆系统", "系统配置"]
        self._page_builders = [
            self._create_profile_page,
            self._create_llm_page,
            self._create_agent_page,
            self._create_memory_page,
            self._create_system_page,
        ]
        self._page_built = [False for _ in self._page_builders]

        self.setup_ui()
        self._reload_config_data()
        self._ensure_page_built(0)
        self._apply_config_to_widgets()
        self.setup_animations()

    @staticmethod
    def _load_config():
        """加载配置文件"""
        config_file = Path("config.yaml")
        if config_file.exists():
            with open(config_file, "r", encoding="utf-8") as f:
                return yaml.safe_load(f)
        return {}

    def setup_animations(self):
        """设置动画"""
        # 淡入淡出动画
        self.fade_animation = QPropertyAnimation(self, b"opacity")
        self.fade_animation.setDuration(MD3_ENHANCED_DURATION["medium1"])
        self.fade_animation.setEasingCurve(MD3_ENHANCED_EASING["emphasized_decelerate"])

    @pyqtProperty(float)
    def opacity(self):
        return self._opacity

    @opacity.setter
    def opacity(self, value):
        self._opacity = value
        self.setWindowOpacity(value)

    def setup_ui(self):
        """设置 UI - v2.31.0 全新布局：左侧导航+右侧内容"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 标题栏
        header = self._create_header()
        layout.addWidget(header)

        # 主内容区：左侧导航 + 右侧内容
        main_content = QWidget()
        main_layout = QHBoxLayout(main_content)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 左侧导航栏
        self.sidebar = self._create_sidebar()
        main_layout.addWidget(self.sidebar)

        # 右侧内容区（使用 QStackedWidget 切换不同页面）
        self.content_stack = QStackedWidget()
        self.content_stack.setStyleSheet(f"""
            QStackedWidget {{
                background: qlineargradient(
                    x1:0, y1:0, x2:0, y2:1,
                    stop:0 {MD3_ENHANCED_COLORS['surface']},
                    stop:1 {MD3_ENHANCED_COLORS['surface_bright']}
                );
            }}
        """)

        # v2.50.x: 页面懒加载 - 初始仅创建占位页，切换时再构建真实页面，降低打开设置面板卡顿
        self.profile_page = None
        self.llm_page = None
        self.agent_page = None
        self.memory_page = None
        self.system_page = None

        for title in list(getattr(self, "_page_titles", [])) or ["设置"]:
            self.content_stack.addWidget(self._create_page_placeholder(title))

        main_layout.addWidget(self.content_stack, 1)  # 右侧内容区占据剩余空间

        layout.addWidget(main_content, 1)

        # 底部按钮栏
        footer = self._create_footer()
        layout.addWidget(footer)

        # 设置面板样式
        self.setStyleSheet(f"""
            QWidget {{
                background: {MD3_ENHANCED_COLORS['background']};
            }}
        """)

    def _create_sidebar(self):
        """创建左侧导航栏 - v2.31.0 新增"""
        sidebar = QWidget()
        sidebar.setFixedWidth(240)
        sidebar.setStyleSheet(f"""
            QWidget {{
                background: qlineargradient(
                    x1:0, y1:0, x2:0, y2:1,
                    stop:0 {MD3_ENHANCED_COLORS['surface_container']},
                    stop:1 {MD3_ENHANCED_COLORS['surface_container_low']}
                );
                border-right: 1px solid {MD3_ENHANCED_COLORS['outline_variant']};
            }}
        """)

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(8, 16, 8, 16)
        layout.setSpacing(4)

        # 导航项列表 - v2.31.0: 使用MD3图标
        nav_items = [
            ("person", "个人资料", 0),
            ("smart_toy", "模型服务", 1),
            ("pets", "角色配置", 2),
            ("psychology", "记忆系统", 3),
            ("settings", "系统配置", 4),
        ]

        self.nav_buttons = []
        for icon_name, text, index in nav_items:
            btn = self._create_nav_button(icon_name, text, index)
            layout.addWidget(btn)
            self.nav_buttons.append(btn)

        layout.addStretch()

        # 默认选中第一项
        if self.nav_buttons:
            self.nav_buttons[0].setChecked(True)

        return sidebar

    def _create_nav_button(self, icon_name: str, text: str, index: int):
        """创建导航按钮 - v2.31.0 优化版: 使用MD3图标"""
        from PyQt6.QtGui import QFont

        # 创建按钮容器
        btn = QPushButton()
        btn.setCheckable(True)
        btn.setFixedHeight(52)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(lambda: self._switch_page(index))

        # 设置Material Symbols字体和图标
        icon_text = MATERIAL_ICONS.get(icon_name, icon_name)
        btn.setText(f"{icon_text}  {text}")

        # 设置字体(图标部分使用Material Symbols)
        font = QFont()
        font.setFamilies(["Material Symbols Outlined", "Microsoft YaHei UI"])
        font.setPixelSize(16)
        btn.setFont(font)

        btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {MD3_ENHANCED_COLORS['on_surface']};
                border: none;
                border-radius: {MD3_ENHANCED_RADIUS['md']};
                padding: 12px 16px;
                text-align: left;
                font-weight: 500;
                margin: 4px 8px;
            }}
            QPushButton:hover {{
                background: {MD3_ENHANCED_COLORS['surface_container_highest']};
            }}
            QPushButton:checked {{
                background: {MD3_ENHANCED_COLORS['secondary_container']};
                color: {MD3_ENHANCED_COLORS['on_secondary_container']};
                font-weight: 600;
            }}
            QPushButton:pressed {{
                background: {MD3_ENHANCED_COLORS['secondary_container']};
            }}
        """)

        return btn

    def _switch_page(self, index: int):
        """切换页面"""
        # 更新按钮状态
        for i, btn in enumerate(self.nav_buttons):
            btn.setChecked(i == index)

        # 切换内容页面
        self.content_stack.setCurrentIndex(index)
        if index < 0 or index >= len(getattr(self, "_page_builders", [])):
            return
        if not self._page_built[index]:
            self._schedule_page_build(index)

    def _create_page_placeholder(self, title: str) -> QWidget:
        """创建懒加载占位页（轻量，避免动画造成额外开销）。"""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(8)

        label = QLabel(f"正在加载 {title}…")
        label.setStyleSheet(
            f"""
            QLabel {{
                color: {MD3_ENHANCED_COLORS['on_surface']};
                {get_typography_css('title_medium')}
                background: transparent;
                font-weight: 600;
            }}
            """
        )
        hint = QLabel("首次打开该页面会稍慢，之后会更快。")
        hint.setStyleSheet(
            f"""
            QLabel {{
                color: {MD3_ENHANCED_COLORS['on_surface_variant']};
                {get_typography_css('body_medium')}
                background: transparent;
            }}
            """
        )
        hint.setWordWrap(True)

        layout.addWidget(label, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(hint, alignment=Qt.AlignmentFlag.AlignHCenter)
        return page

    def _schedule_page_build(self, index: int) -> None:
        """延迟构建页面，让 UI 先完成一次绘制（更顺滑）。"""
        pending = getattr(self, "_pending_page_builds", None)
        if pending is None:
            self._pending_page_builds = set()
            pending = self._pending_page_builds

        if index in pending:
            return
        pending.add(index)
        QTimer.singleShot(0, lambda idx=index: self._build_page_deferred(idx))

    def _build_page_deferred(self, index: int) -> None:
        try:
            self._pending_page_builds.discard(index)
        except Exception:
            pass

        if self._ensure_page_built(index):
            # 页面刚构建完成，按当前 config_data 填充控件
            try:
                self._apply_config_to_widgets()
            except Exception:
                pass

    def _ensure_page_built(self, index: int) -> bool:
        """确保指定页面已构建并替换占位页。"""
        builders = getattr(self, "_page_builders", [])
        if index < 0 or index >= len(builders):
            return False
        if self._page_built[index]:
            return True

        builder = builders[index]
        title = (getattr(self, "_page_titles", []) or ["设置"])[min(index, len(self._page_titles) - 1)]

        current_widget = self.content_stack.currentWidget()
        placeholder = self.content_stack.widget(index)
        try:
            page = builder()
        except Exception as exc:
            logger.error("构建设置页面失败: %s", exc, exc_info=True)
            page = QWidget()
            layout = QVBoxLayout(page)
            layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.setContentsMargins(24, 24, 24, 24)
            layout.setSpacing(8)
            title_label = QLabel(f"{title} 加载失败")
            title_label.setStyleSheet(
                f"""
                QLabel {{
                    color: {MD3_ENHANCED_COLORS['error']};
                    {get_typography_css('title_medium')}
                    background: transparent;
                    font-weight: 700;
                }}
                """
            )
            detail = QLabel(str(exc))
            detail.setStyleSheet(
                f"""
                QLabel {{
                    color: {MD3_ENHANCED_COLORS['on_surface_variant']};
                    {get_typography_css('body_small')}
                    background: transparent;
                }}
                """
            )
            detail.setWordWrap(True)
            layout.addWidget(title_label, alignment=Qt.AlignmentFlag.AlignHCenter)
            layout.addWidget(detail, alignment=Qt.AlignmentFlag.AlignHCenter)

        # 用 insert+remove 的方式替换，保持 index 稳定
        self.content_stack.insertWidget(index, page)
        self.content_stack.removeWidget(placeholder)
        try:
            placeholder.deleteLater()
        except Exception:
            pass

        self._page_built[index] = True
        if current_widget is placeholder:
            try:
                self.content_stack.setCurrentWidget(page)
            except Exception:
                pass

        # v2.51.x: 自动绑定“未保存”提示（对所有输入控件统一追踪）
        try:
            self._wire_unsaved_tracking(page)
        except Exception:
            pass

        # 兼容旧属性名（便于外部引用/调试）
        if index == 0:
            self.profile_page = page
        elif index == 1:
            self.llm_page = page
        elif index == 2:
            self.agent_page = page
        elif index == 3:
            self.memory_page = page
        elif index == 4:
            self.system_page = page

        return True

    def _create_icon_label(self, icon_name: str, text: str, font_size: int = 16) -> QLabel:
        """创建带MD3图标的标签 - v2.31.0 新增辅助方法"""
        from PyQt6.QtGui import QFont
        icon_text = MATERIAL_ICONS.get(icon_name, icon_name)
        label = QLabel(f"{icon_text}  {text}")
        font = QFont()
        font.setFamilies(["Material Symbols Outlined", "Microsoft YaHei UI"])
        font.setPixelSize(font_size)
        label.setFont(font)
        return label

    def _create_icon_button(self, icon_name: str, text: str, font_size: int = 16, font_weight=None) -> QPushButton:
        """创建带MD3图标的按钮 - v2.31.0 新增辅助方法"""
        from PyQt6.QtGui import QFont
        icon_text = MATERIAL_ICONS.get(icon_name, icon_name)
        btn = QPushButton(f"{icon_text}  {text}")
        font = QFont()
        font.setFamilies(["Material Symbols Outlined", "Microsoft YaHei UI"])
        font.setPixelSize(font_size)
        if font_weight:
            font.setWeight(font_weight)
        btn.setFont(font)
        return btn

    def _create_header(self):
        """创建标题栏 - v2.31.0 简化版"""
        header = QWidget()
        header.setFixedHeight(64)
        header.setStyleSheet(f"""
            QWidget {{
                background: {MD3_ENHANCED_COLORS['surface_container']};
                border-bottom: 1px solid {MD3_ENHANCED_COLORS['outline_variant']};
            }}
        """)

        layout = QHBoxLayout(header)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(16)

        # 返回按钮
        back_btn = MaterialIconButton("arrow_back", "返回", size=40, icon_size=20)
        back_btn.setCheckable(False)
        back_btn.clicked.connect(self.back_clicked.emit)
        layout.addWidget(back_btn)

        # 标题 - v2.31.0: 使用MD3图标
        from PyQt6.QtGui import QFont
        title = QLabel(f"{MATERIAL_ICONS['settings']}  设置")
        title_font = QFont()
        title_font.setFamilies(["Material Symbols Outlined", "Microsoft YaHei UI"])
        title_font.setPixelSize(24)
        title_font.setWeight(QFont.Weight.DemiBold)
        title.setFont(title_font)
        title.setStyleSheet(f"""
            QLabel {{
                color: {MD3_ENHANCED_COLORS['on_surface']};
                background: transparent;
            }}
        """)
        layout.addWidget(title)

        layout.addStretch()

        # v2.24.0 新增：未保存更改提示
        self.unsaved_indicator = QLabel("● 有未保存的更改")
        self.unsaved_indicator.setStyleSheet(f"""
            QLabel {{
                {get_typography_css('label_medium')}
                color: {MD3_ENHANCED_COLORS['error']};
                background: transparent;
                padding: 8px 16px;
                border-radius: {MD3_ENHANCED_RADIUS['full']};
            }}
        """)
        self.unsaved_indicator.hide()  # 默认隐藏
        layout.addWidget(self.unsaved_indicator)

        return header

    def _create_footer(self):
        """创建底部按钮 - v2.24.0 优化版：更现代的按钮设计"""
        footer = QWidget()
        footer.setFixedHeight(88)
        footer.setStyleSheet(f"""
            QWidget {{
                background: qlineargradient(
                    x1:0, y1:0, x2:0, y2:1,
                    stop:0 {MD3_ENHANCED_COLORS['surface']},
                    stop:1 {MD3_ENHANCED_COLORS['surface_bright']}
                );
                border-top: 2px solid {MD3_ENHANCED_COLORS['outline_variant']};
            }}
        """)

        # v2.24.0 添加阴影效果
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(12)
        shadow.setXOffset(0)
        shadow.setYOffset(-2)
        shadow.setColor(QColor(0, 0, 0, 15))
        footer.setGraphicsEffect(shadow)

        layout = QHBoxLayout(footer)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        # v2.31.0: 快捷操作提示 - 使用MD3图标
        from PyQt6.QtGui import QFont
        hint_label = QLabel(f"{MATERIAL_ICONS['lightbulb']}  提示：Ctrl+S 快速保存")
        hint_font = QFont()
        hint_font.setFamilies(["Material Symbols Outlined", "Microsoft YaHei UI"])
        hint_font.setPixelSize(14)
        hint_label.setFont(hint_font)
        hint_label.setStyleSheet(f"""
            QLabel {{
                color: {MD3_ENHANCED_COLORS['on_surface_variant']};
                background: transparent;
            }}
        """)
        layout.addWidget(hint_label)

        layout.addStretch()

        # 重置按钮 - v2.31.0: 使用MD3图标
        from PyQt6.QtGui import QFont
        reset_btn = QPushButton(f"{MATERIAL_ICONS['refresh']}  重置")
        reset_btn.setFixedSize(140, 52)
        reset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        reset_font = QFont()
        reset_font.setFamilies(["Material Symbols Outlined", "Microsoft YaHei UI"])
        reset_font.setPixelSize(16)
        reset_font.setWeight(QFont.Weight.Medium)
        reset_btn.setFont(reset_font)
        reset_btn.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 {MD3_ENHANCED_COLORS['surface_container_high']},
                    stop:1 {MD3_ENHANCED_COLORS['surface_container_highest']}
                );
                color: {MD3_ENHANCED_COLORS['on_surface']};
                border: 2px solid {MD3_ENHANCED_COLORS['outline']};
                border-radius: {MD3_ENHANCED_RADIUS['full']};
            }}
            QPushButton:hover {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 {MD3_ENHANCED_COLORS['surface_container_highest']},
                    stop:1 {MD3_ENHANCED_COLORS['surface_bright']}
                );
                border-color: {MD3_ENHANCED_COLORS['primary']};
            }}
            QPushButton:pressed {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 {MD3_ENHANCED_COLORS['primary_container']},
                    stop:1 {MD3_ENHANCED_COLORS['secondary_container']}
                );
            }}
        """)
        reset_btn.clicked.connect(self.on_reset_clicked)
        layout.addWidget(reset_btn)

        # 保存按钮 - v2.31.0: 使用MD3图标
        self.save_btn = QPushButton(f"{MATERIAL_ICONS['save']}  保存设置")
        self.save_btn.setFixedSize(160, 52)
        self.save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_font = QFont()
        save_font.setFamilies(["Material Symbols Outlined", "Microsoft YaHei UI"])
        save_font.setPixelSize(16)
        save_font.setWeight(QFont.Weight.DemiBold)
        self.save_btn.setFont(save_font)
        self.save_btn.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 {MD3_ENHANCED_COLORS['primary']},
                    stop:1 {MD3_ENHANCED_COLORS['primary_60']}
                );
                color: {MD3_ENHANCED_COLORS['on_primary']};
                border: none;
                border-radius: {MD3_ENHANCED_RADIUS['full']};
                {get_typography_css('label_large')}
                font-weight: 600;
            }}
            QPushButton:hover {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 {MD3_ENHANCED_COLORS['primary_60']},
                    stop:1 {MD3_ENHANCED_COLORS['primary_70']}
                );
            }}
            QPushButton:pressed {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 {MD3_ENHANCED_COLORS['primary_70']},
                    stop:1 {MD3_ENHANCED_COLORS['primary_80']}
                );
            }}
        """)

        # v2.24.0 添加按钮阴影
        save_shadow = QGraphicsDropShadowEffect()
        save_shadow.setBlurRadius(16)
        save_shadow.setXOffset(0)
        save_shadow.setYOffset(4)
        shadow_color = QColor(MD3_ENHANCED_COLORS["primary"])
        shadow_color.setAlpha(100)
        save_shadow.setColor(shadow_color)
        self.save_btn.setGraphicsEffect(save_shadow)

        self.save_btn.clicked.connect(self.save_settings)
        layout.addWidget(self.save_btn)

        return footer

    def on_reset_clicked(self):
        """重置按钮点击事件 - v2.24.0 新增：带确认对话框"""
        reply = QMessageBox.question(
            self,
            "确认重置",
            "确定要重置所有设置吗？\n\n这将丢弃所有未保存的更改。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.load_settings()
            self._mark_as_saved()
            QMessageBox.information(self, "重置成功", "设置已重置为上次保存的状态。")

    def _create_profile_page(self):
        """创建个人资料页面 - v2.31.0 重构"""
        page = QWidget()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"""
            QScrollArea {{
                border: none;
                background: transparent;
            }}
            QScrollBar:vertical {{
                background: {MD3_ENHANCED_COLORS['surface_container']};
                width: 12px;
                border-radius: 6px;
                margin: 0px;
            }}
            QScrollBar::handle:vertical {{
                background: {MD3_ENHANCED_COLORS['primary_40']};
                border-radius: 6px;
                min-height: 30px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {MD3_ENHANCED_COLORS['primary_50']};
            }}
            QScrollBar::handle:vertical:pressed {{
                background: {MD3_ENHANCED_COLORS['primary_60']};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background: none;
            }}
        """)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(32, 24, 32, 24)
        layout.setSpacing(20)

        # 页面标题和说明
        title_label = QLabel("个人资料")
        title_label.setStyleSheet(f"""
            QLabel {{
                {get_typography_css('headline_small')}
                color: {MD3_ENHANCED_COLORS['on_surface']};
                font-weight: 600;
                padding-bottom: 4px;
            }}
        """)
        layout.addWidget(title_label)

        desc_label = QLabel("自定义您的头像和个人信息")
        desc_label.setStyleSheet(f"""
            QLabel {{
                {get_typography_css('body_medium')}
                color: {MD3_ENHANCED_COLORS['on_surface_variant']};
                padding-bottom: 16px;
            }}
        """)
        layout.addWidget(desc_label)

        # 用户头像组 - v2.31.0: 使用MD3图标
        user_avatar_group = self._create_group(f"{MATERIAL_ICONS['person']}  用户头像")
        user_avatar_layout = QVBoxLayout()
        user_avatar_layout.setSpacing(12)

        # 头像预览和选择
        avatar_preview_layout = QHBoxLayout()
        avatar_preview_layout.setSpacing(16)

        # v2.24.0 用户头像预览 - 圆形设计
        self.user_avatar_preview = QLabel("👤")
        self.user_avatar_preview.setFixedSize(96, 96)
        self.user_avatar_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.user_avatar_preview.setStyleSheet(f"""
            QLabel {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 {MD3_ENHANCED_COLORS['primary_30']},
                    stop:1 {MD3_ENHANCED_COLORS['tertiary_30']}
                );
                border-radius: 48px;
                font-size: 48px;
                border: 4px solid {MD3_ENHANCED_COLORS['surface_bright']};
            }}
        """)

        # v2.24.0 添加头像阴影
        avatar_shadow = QGraphicsDropShadowEffect()
        avatar_shadow.setBlurRadius(20)
        avatar_shadow.setXOffset(0)
        avatar_shadow.setYOffset(4)
        avatar_shadow.setColor(QColor(0, 0, 0, 40))
        self.user_avatar_preview.setGraphicsEffect(avatar_shadow)

        avatar_preview_layout.addWidget(self.user_avatar_preview)

        # 头像输入和按钮
        avatar_input_layout = QVBoxLayout()
        avatar_input_layout.setSpacing(12)

        self.user_avatar_input = QLineEdit()
        self.user_avatar_input.setPlaceholderText("输入 emoji 或图片路径")
        self._style_input(self.user_avatar_input)
        self.user_avatar_input.textChanged.connect(lambda: self._update_avatar_preview('user'))
        avatar_input_layout.addWidget(self.user_avatar_input)

        # v2.24.0 按钮组
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        # 选择图片按钮 - v2.31.0: 使用MD3图标
        choose_user_avatar_btn = self._create_icon_button("folder_open", "选择图片", 15)
        choose_user_avatar_btn.setFixedHeight(44)
        choose_user_avatar_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        choose_user_avatar_btn.setStyleSheet(f"""
            QPushButton {{
                background: {MD3_ENHANCED_COLORS['primary_container']};
                color: {MD3_ENHANCED_COLORS['on_primary_container']};
                border: none;
                border-radius: {MD3_ENHANCED_RADIUS['md']};
                padding: 8px 16px;
                {get_typography_css('label_large')}
                font-weight: 500;
            }}
            QPushButton:hover {{
                background: {MD3_ENHANCED_COLORS['primary_40']};
            }}
            QPushButton:pressed {{
                background: {MD3_ENHANCED_COLORS['primary_50']};
            }}
        """)
        choose_user_avatar_btn.clicked.connect(lambda: self._choose_avatar('user'))
        btn_layout.addWidget(choose_user_avatar_btn)

        # v2.24.0 清除按钮
        clear_user_avatar_btn = self._create_icon_button("delete", "清除", 15)
        clear_user_avatar_btn.setFixedHeight(44)
        clear_user_avatar_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        clear_user_avatar_btn.setStyleSheet(f"""
            QPushButton {{
                background: {MD3_ENHANCED_COLORS['surface_container_high']};
                color: {MD3_ENHANCED_COLORS['on_surface']};
                border: 1px solid {MD3_ENHANCED_COLORS['outline']};
                border-radius: {MD3_ENHANCED_RADIUS['md']};
                padding: 8px 16px;
                {get_typography_css('label_large')}
            }}
            QPushButton:hover {{
                background: {MD3_ENHANCED_COLORS['error_container']};
                color: {MD3_ENHANCED_COLORS['on_error_container']};
                border-color: {MD3_ENHANCED_COLORS['error']};
            }}
        """)
        clear_user_avatar_btn.clicked.connect(lambda: self._clear_avatar('user'))
        btn_layout.addWidget(clear_user_avatar_btn)

        avatar_input_layout.addLayout(btn_layout)

        avatar_preview_layout.addLayout(avatar_input_layout)
        avatar_preview_layout.addStretch()

        user_avatar_layout.addLayout(avatar_preview_layout)
        user_avatar_group.setLayout(user_avatar_layout)
        layout.addWidget(user_avatar_group)

        # AI助手头像组
        ai_avatar_group = self._create_group(f"{MATERIAL_ICONS['smart_toy']}  AI助手头像")
        ai_avatar_layout = QVBoxLayout()
        ai_avatar_layout.setSpacing(12)

        # AI头像预览和选择
        ai_avatar_preview_layout = QHBoxLayout()
        ai_avatar_preview_layout.setSpacing(16)

        # v2.24.0 AI头像预览 - 圆形设计
        self.ai_avatar_preview = QLabel("🐱")
        self.ai_avatar_preview.setFixedSize(96, 96)
        self.ai_avatar_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.ai_avatar_preview.setStyleSheet(f"""
            QLabel {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 {MD3_ENHANCED_COLORS['tertiary_30']},
                    stop:1 {MD3_ENHANCED_COLORS['secondary_30']}
                );
                border-radius: 48px;
                font-size: 48px;
                border: 4px solid {MD3_ENHANCED_COLORS['surface_bright']};
            }}
        """)

        # v2.24.0 添加头像阴影
        ai_avatar_shadow = QGraphicsDropShadowEffect()
        ai_avatar_shadow.setBlurRadius(20)
        ai_avatar_shadow.setXOffset(0)
        ai_avatar_shadow.setYOffset(4)
        ai_avatar_shadow.setColor(QColor(0, 0, 0, 40))
        self.ai_avatar_preview.setGraphicsEffect(ai_avatar_shadow)

        ai_avatar_preview_layout.addWidget(self.ai_avatar_preview)

        # AI头像输入和按钮
        ai_avatar_input_layout = QVBoxLayout()
        ai_avatar_input_layout.setSpacing(12)

        self.ai_avatar_input = QLineEdit()
        self.ai_avatar_input.setPlaceholderText("输入 emoji 或图片路径")
        self._style_input(self.ai_avatar_input)
        self.ai_avatar_input.textChanged.connect(lambda: self._update_avatar_preview('ai'))
        ai_avatar_input_layout.addWidget(self.ai_avatar_input)

        # v2.24.0 按钮组
        ai_btn_layout = QHBoxLayout()
        ai_btn_layout.setSpacing(8)

        # 选择图片按钮
        choose_ai_avatar_btn = self._create_icon_button("folder_open", "选择图片", 15)
        choose_ai_avatar_btn.setFixedHeight(44)
        choose_ai_avatar_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        choose_ai_avatar_btn.setStyleSheet(f"""
            QPushButton {{
                background: {MD3_ENHANCED_COLORS['tertiary_container']};
                color: {MD3_ENHANCED_COLORS['on_tertiary_container']};
                border: none;
                border-radius: {MD3_ENHANCED_RADIUS['md']};
                padding: 8px 16px;
                {get_typography_css('label_large')}
                font-weight: 500;
            }}
            QPushButton:hover {{
                background: {MD3_ENHANCED_COLORS['tertiary_40']};
            }}
            QPushButton:pressed {{
                background: {MD3_ENHANCED_COLORS['tertiary_50']};
            }}
        """)
        choose_ai_avatar_btn.clicked.connect(lambda: self._choose_avatar('ai'))
        ai_btn_layout.addWidget(choose_ai_avatar_btn)

        # v2.24.0 清除按钮
        clear_ai_avatar_btn = self._create_icon_button("delete", "清除", 15)
        clear_ai_avatar_btn.setFixedHeight(44)
        clear_ai_avatar_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        clear_ai_avatar_btn.setStyleSheet(f"""
            QPushButton {{
                background: {MD3_ENHANCED_COLORS['surface_container_high']};
                color: {MD3_ENHANCED_COLORS['on_surface']};
                border: 1px solid {MD3_ENHANCED_COLORS['outline']};
                border-radius: {MD3_ENHANCED_RADIUS['md']};
                padding: 8px 16px;
                {get_typography_css('label_large')}
            }}
            QPushButton:hover {{
                background: {MD3_ENHANCED_COLORS['error_container']};
                color: {MD3_ENHANCED_COLORS['on_error_container']};
                border-color: {MD3_ENHANCED_COLORS['error']};
            }}
        """)
        clear_ai_avatar_btn.clicked.connect(lambda: self._clear_avatar('ai'))
        ai_btn_layout.addWidget(clear_ai_avatar_btn)

        ai_avatar_input_layout.addLayout(ai_btn_layout)

        ai_avatar_preview_layout.addLayout(ai_avatar_input_layout)
        ai_avatar_preview_layout.addStretch()

        ai_avatar_layout.addLayout(ai_avatar_preview_layout)
        ai_avatar_group.setLayout(ai_avatar_layout)
        layout.addWidget(ai_avatar_group)

        layout.addStretch()

        scroll.setWidget(content)

        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.addWidget(scroll)

        return page

    def _choose_avatar(self, avatar_type: str):
        """选择头像图片

        Args:
            avatar_type: 'user' 或 'ai'
        """
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择头像图片",
            "",
            "图片文件 (*.png *.jpg *.jpeg *.gif *.webp *.bmp)"
        )

        if file_path:
            if avatar_type == 'user':
                self.user_avatar_input.setText(file_path)
            else:
                self.ai_avatar_input.setText(file_path)

    def _create_llm_page(self):
        """创建 LLM 配置页面 - v2.31.0 重构"""
        page = QWidget()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"""
            QScrollArea {{
                border: none;
                background: transparent;
            }}
            QScrollBar:vertical {{
                background: {MD3_ENHANCED_COLORS['surface_container']};
                width: 12px;
                border-radius: 6px;
                margin: 0px;
            }}
            QScrollBar::handle:vertical {{
                background: {MD3_ENHANCED_COLORS['primary_40']};
                border-radius: 6px;
                min-height: 30px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {MD3_ENHANCED_COLORS['primary_50']};
            }}
            QScrollBar::handle:vertical:pressed {{
                background: {MD3_ENHANCED_COLORS['primary_60']};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background: none;
            }}
        """)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(32, 24, 32, 24)
        layout.setSpacing(20)

        # 页面标题和说明
        title_label = QLabel("模型服务")
        title_label.setStyleSheet(f"""
            QLabel {{
                {get_typography_css('headline_small')}
                color: {MD3_ENHANCED_COLORS['on_surface']};
                font-weight: 600;
                padding-bottom: 4px;
            }}
        """)
        layout.addWidget(title_label)

        desc_label = QLabel("配置大语言模型API和参数")
        desc_label.setStyleSheet(f"""
            QLabel {{
                {get_typography_css('body_medium')}
                color: {MD3_ENHANCED_COLORS['on_surface_variant']};
                padding-bottom: 16px;
            }}
        """)
        layout.addWidget(desc_label)

        # API 配置组
        api_group = self._create_group(f"{MATERIAL_ICONS['tune']}  API 配置")
        api_layout = QFormLayout()
        api_layout.setSpacing(12)
        api_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        # API 地址
        self.api_input = QLineEdit()
        self.api_input.setPlaceholderText("https://api.openai.com/v1")
        self._style_input(self.api_input)
        api_layout.addRow("API 地址:", self.api_input)

        # API Key
        self.key_input = QLineEdit()
        self.key_input.setPlaceholderText("sk-...")
        self.key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._style_input(self.key_input)
        api_layout.addRow("API Key:", self.key_input)

        # 模型名称
        self.model_input = QLineEdit()
        self.model_input.setPlaceholderText("gpt-4o")
        self._style_input(self.model_input)
        api_layout.addRow("模型名称:", self.model_input)

        api_group.setLayout(api_layout)
        layout.addWidget(api_group)

        # 模型参数组
        params_group = self._create_group(f"{MATERIAL_ICONS['settings']}  模型参数")
        params_layout = QFormLayout()
        params_layout.setSpacing(12)
        params_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        # Temperature
        self.temperature_input = QDoubleSpinBox()
        self.temperature_input.setRange(0.0, 2.0)
        self.temperature_input.setSingleStep(0.1)
        self.temperature_input.setValue(0.7)
        self._style_spinbox(self.temperature_input)
        params_layout.addRow("Temperature:", self.temperature_input)

        params_group.setLayout(params_layout)
        layout.addWidget(params_group)

        layout.addStretch()

        scroll.setWidget(content)

        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.addWidget(scroll)

        return page

    def _create_agent_page(self):
        """创建 Agent 配置页面 - v2.31.0 重构"""
        page = QWidget()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"""
            QScrollArea {{
                border: none;
                background: transparent;
            }}
            QScrollBar:vertical {{
                background: {MD3_ENHANCED_COLORS['surface_container']};
                width: 12px;
                border-radius: 6px;
                margin: 0px;
            }}
            QScrollBar::handle:vertical {{
                background: {MD3_ENHANCED_COLORS['primary_40']};
                border-radius: 6px;
                min-height: 30px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {MD3_ENHANCED_COLORS['primary_50']};
            }}
            QScrollBar::handle:vertical:pressed {{
                background: {MD3_ENHANCED_COLORS['primary_60']};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background: none;
            }}
        """)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(32, 24, 32, 24)
        layout.setSpacing(20)

        # 页面标题和说明
        title_label = QLabel("角色配置")
        title_label.setStyleSheet(f"""
            QLabel {{
                {get_typography_css('headline_small')}
                color: {MD3_ENHANCED_COLORS['on_surface']};
                font-weight: 600;
                padding-bottom: 4px;
            }}
        """)
        layout.addWidget(title_label)

        desc_label = QLabel("自定义AI助手的角色和性格")
        desc_label.setStyleSheet(f"""
            QLabel {{
                {get_typography_css('body_medium')}
                color: {MD3_ENHANCED_COLORS['on_surface_variant']};
                padding-bottom: 16px;
            }}
        """)
        layout.addWidget(desc_label)

        # 基础配置组
        basic_group = self._create_group(f"{MATERIAL_ICONS['note']}  基础配置")
        basic_layout = QFormLayout()
        basic_layout.setSpacing(12)
        basic_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        # 启用角色模板
        self.is_up_checkbox = QCheckBox("启用角色模板功能")
        self._style_checkbox(self.is_up_checkbox)
        basic_layout.addRow("", self.is_up_checkbox)

        # 角色名称
        self.char_input = QLineEdit()
        self.char_input.setPlaceholderText("小雪糕")
        self._style_input(self.char_input)
        basic_layout.addRow("角色名称:", self.char_input)

        # 用户名称
        self.user_input = QLineEdit()
        self.user_input.setPlaceholderText("主人")
        self._style_input(self.user_input)
        basic_layout.addRow("用户名称:", self.user_input)

        # 上下文长度
        self.context_length_input = QSpinBox()
        self.context_length_input.setRange(0, 1000)
        self.context_length_input.setValue(40)
        self.context_length_input.setSpecialValueText("无限制")
        self._style_spinbox(self.context_length_input)
        basic_layout.addRow("上下文长度:", self.context_length_input)

        basic_group.setLayout(basic_layout)
        layout.addWidget(basic_group)

        # 角色设定组
        char_group = self._create_group(f"{MATERIAL_ICONS['masks']}  角色设定")
        char_layout = QVBoxLayout()
        char_layout.setSpacing(12)

        # 角色基本设定
        char_settings_label = QLabel("角色基本设定:")
        self._style_label(char_settings_label)
        char_layout.addWidget(char_settings_label)

        self.char_settings_input = QTextEdit()
        self.char_settings_input.setPlaceholderText("描述角色的基本设定...")
        self.char_settings_input.setMaximumHeight(100)
        self._style_textedit(self.char_settings_input)
        char_layout.addWidget(self.char_settings_input)

        # 角色性格设定
        char_personalities_label = QLabel("角色性格设定:")
        self._style_label(char_personalities_label)
        char_layout.addWidget(char_personalities_label)

        self.char_personalities_input = QTextEdit()
        self.char_personalities_input.setPlaceholderText("描述角色的性格...")
        self.char_personalities_input.setMaximumHeight(100)
        self._style_textedit(self.char_personalities_input)
        char_layout.addWidget(self.char_personalities_input)

        char_group.setLayout(char_layout)
        layout.addWidget(char_group)

        layout.addStretch()

        scroll.setWidget(content)

        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.addWidget(scroll)

        return page

    def _create_memory_page(self):
        """创建记忆系统页面 - v2.31.0 重构"""
        page = QWidget()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"""
            QScrollArea {{
                border: none;
                background: transparent;
            }}
            QScrollBar:vertical {{
                background: {MD3_ENHANCED_COLORS['surface_container']};
                width: 12px;
                border-radius: 6px;
                margin: 0px;
            }}
            QScrollBar::handle:vertical {{
                background: {MD3_ENHANCED_COLORS['primary_40']};
                border-radius: 6px;
                min-height: 30px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {MD3_ENHANCED_COLORS['primary_50']};
            }}
            QScrollBar::handle:vertical:pressed {{
                background: {MD3_ENHANCED_COLORS['primary_60']};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background: none;
            }}
        """)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(32, 24, 32, 24)
        layout.setSpacing(20)

        # 页面标题和说明
        title_label = QLabel("记忆系统")
        title_label.setStyleSheet(f"""
            QLabel {{
                {get_typography_css('headline_small')}
                color: {MD3_ENHANCED_COLORS['on_surface']};
                font-weight: 600;
                padding-bottom: 4px;
            }}
        """)
        layout.addWidget(title_label)

        desc_label = QLabel("配置AI助手的记忆管理系统")
        desc_label.setStyleSheet(f"""
            QLabel {{
                {get_typography_css('body_medium')}
                color: {MD3_ENHANCED_COLORS['on_surface_variant']};
                padding-bottom: 16px;
            }}
        """)
        layout.addWidget(desc_label)

        # 记忆功能组
        memory_group = self._create_group(f"{MATERIAL_ICONS['psychology']}  记忆功能")
        memory_layout = QVBoxLayout()
        memory_layout.setSpacing(12)

        # 长期记忆
        self.long_memory_checkbox = QCheckBox("启用日记功能（长期记忆）")
        self._style_checkbox(self.long_memory_checkbox)
        memory_layout.addWidget(self.long_memory_checkbox)

        # 日记检索加强
        self.is_check_memorys_checkbox = QCheckBox("启用日记检索加强")
        self._style_checkbox(self.is_check_memorys_checkbox)
        memory_layout.addWidget(self.is_check_memorys_checkbox)

        # 核心记忆
        self.is_core_mem_checkbox = QCheckBox("启用核心记忆功能")
        self._style_checkbox(self.is_core_mem_checkbox)
        memory_layout.addWidget(self.is_core_mem_checkbox)

        # v2.30.36: 智能日记系统
        self.smart_diary_checkbox = QCheckBox("启用智能日记系统（只记录重要对话）")
        self._style_checkbox(self.smart_diary_checkbox)
        memory_layout.addWidget(self.smart_diary_checkbox)

        # v2.30.36: 每日总结
        self.daily_summary_checkbox = QCheckBox("启用每日总结（自动生成今天的对话总结）")
        self._style_checkbox(self.daily_summary_checkbox)
        memory_layout.addWidget(self.daily_summary_checkbox)

        memory_group.setLayout(memory_layout)
        layout.addWidget(memory_group)

        # 记忆参数组
        mem_params_group = self._create_group(f"{MATERIAL_ICONS['settings']}  记忆参数")
        mem_params_layout = QFormLayout()
        mem_params_layout.setSpacing(12)
        mem_params_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        # 日记搜索阈值
        self.mem_thresholds_input = QDoubleSpinBox()
        self.mem_thresholds_input.setRange(0.0, 1.0)
        self.mem_thresholds_input.setSingleStep(0.01)
        self.mem_thresholds_input.setValue(0.385)
        self._style_spinbox(self.mem_thresholds_input)
        mem_params_layout.addRow("日记搜索阈值:", self.mem_thresholds_input)

        # v2.30.36: 日记重要性阈值
        self.diary_importance_threshold_input = QDoubleSpinBox()
        self.diary_importance_threshold_input.setRange(0.0, 1.0)
        self.diary_importance_threshold_input.setSingleStep(0.05)
        self.diary_importance_threshold_input.setValue(0.6)
        self._style_spinbox(self.diary_importance_threshold_input)
        mem_params_layout.addRow("日记重要性阈值:", self.diary_importance_threshold_input)

        mem_params_group.setLayout(mem_params_layout)
        layout.addWidget(mem_params_group)

        # 知识库配置组
        books_group = self._create_group(f"{MATERIAL_ICONS['library_books']}  知识库配置")
        books_layout = QVBoxLayout()
        books_layout.setSpacing(12)

        # 启用知识库
        self.lore_books_checkbox = QCheckBox("启用世界书（知识库）")
        self._style_checkbox(self.lore_books_checkbox)
        books_layout.addWidget(self.lore_books_checkbox)

        # 知识库参数
        books_params_layout = QFormLayout()
        books_params_layout.setSpacing(12)
        books_params_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        # 知识库检索阈值
        self.books_thresholds_input = QDoubleSpinBox()
        self.books_thresholds_input.setRange(0.0, 1.0)
        self.books_thresholds_input.setSingleStep(0.01)
        self.books_thresholds_input.setValue(0.5)
        self._style_spinbox(self.books_thresholds_input)
        books_params_layout.addRow("检索阈值:", self.books_thresholds_input)

        # 搜索深度
        self.scan_depth_input = QSpinBox()
        self.scan_depth_input.setRange(1, 20)
        self.scan_depth_input.setValue(4)
        self._style_spinbox(self.scan_depth_input)
        books_params_layout.addRow("搜索深度:", self.scan_depth_input)

        books_layout.addLayout(books_params_layout)
        books_group.setLayout(books_layout)
        layout.addWidget(books_group)

        # v2.30.32: 记忆管理组
        memory_mgmt_group = self._create_group("记忆管理")
        memory_mgmt_layout = QVBoxLayout()
        memory_mgmt_layout.setSpacing(12)

        # 说明文本 - v2.31.0: 优化圆角和渐变
        desc_label = QLabel("查看、筛选、编辑和删除记忆。支持按情感、主题、重要性、人物、地点、事件筛选。")
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet(f"""
            QLabel {{
                color: {MD3_ENHANCED_COLORS['on_surface_variant']};
                font-size: 13px;
                padding: 12px 16px;
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 {MD3_ENHANCED_COLORS['secondary_container']},
                    stop:1 {MD3_ENHANCED_COLORS['tertiary_container']}
                );
                border-radius: {MD3_ENHANCED_RADIUS['lg']};
                border: 1px solid {MD3_ENHANCED_COLORS['outline_variant']};
            }}
        """)
        memory_mgmt_layout.addWidget(desc_label)

        # 按钮布局
        mgmt_buttons_layout = QHBoxLayout()

        # 打开记忆管理按钮 - v2.31.0: 优化渐变效果
        open_memory_mgmt_btn = self._create_icon_button("psychology", "打开记忆管理", 15)
        open_memory_mgmt_btn.clicked.connect(self._open_memory_manager)
        open_memory_mgmt_btn.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 {MD3_ENHANCED_COLORS['primary_container']},
                    stop:1 {MD3_ENHANCED_COLORS['secondary_container']}
                );
                color: {MD3_ENHANCED_COLORS['on_primary_container']};
                border: none;
                border-radius: {MD3_ENHANCED_RADIUS['xl']};
                padding: 12px 24px;
                font-size: 14px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 {MD3_ENHANCED_COLORS['primary_40']},
                    stop:1 {MD3_ENHANCED_COLORS['secondary_40']}
                );
            }}
            QPushButton:pressed {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 {MD3_ENHANCED_COLORS['primary_50']},
                    stop:1 {MD3_ENHANCED_COLORS['secondary_50']}
                );
            }}
        """)
        mgmt_buttons_layout.addWidget(open_memory_mgmt_btn)

        # v2.30.38: 打开知识库管理按钮 - v2.31.0: 优化渐变效果
        open_lorebook_mgmt_btn = self._create_icon_button("library_books", "打开知识库管理", 15)
        open_lorebook_mgmt_btn.clicked.connect(self._open_lorebook_manager)
        open_lorebook_mgmt_btn.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 {MD3_ENHANCED_COLORS['tertiary_container']},
                    stop:1 {MD3_ENHANCED_COLORS['primary_container']}
                );
                color: {MD3_ENHANCED_COLORS['on_tertiary_container']};
                border: none;
                border-radius: {MD3_ENHANCED_RADIUS['xl']};
                padding: 12px 24px;
                font-size: 14px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 {MD3_ENHANCED_COLORS['tertiary_40']},
                    stop:1 {MD3_ENHANCED_COLORS['primary_40']}
                );
            }}
            QPushButton:pressed {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 {MD3_ENHANCED_COLORS['tertiary_50']},
                    stop:1 {MD3_ENHANCED_COLORS['primary_50']}
                );
            }}
        """)
        mgmt_buttons_layout.addWidget(open_lorebook_mgmt_btn)

        memory_mgmt_layout.addLayout(mgmt_buttons_layout)

        memory_mgmt_group.setLayout(memory_mgmt_layout)
        layout.addWidget(memory_mgmt_group)

        layout.addStretch()

        scroll.setWidget(content)

        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.addWidget(scroll)

        return page

    def _create_system_page(self):
        """创建系统配置页面 - v2.31.0 重构"""
        page = QWidget()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"""
            QScrollArea {{
                border: none;
                background: transparent;
            }}
            QScrollBar:vertical {{
                background: {MD3_ENHANCED_COLORS['surface_container']};
                width: 12px;
                border-radius: 6px;
                margin: 0px;
            }}
            QScrollBar::handle:vertical {{
                background: {MD3_ENHANCED_COLORS['primary_40']};
                border-radius: 6px;
                min-height: 30px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {MD3_ENHANCED_COLORS['primary_50']};
            }}
            QScrollBar::handle:vertical:pressed {{
                background: {MD3_ENHANCED_COLORS['primary_60']};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background: none;
            }}
        """)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(32, 24, 32, 24)
        layout.setSpacing(20)

        # 页面标题和说明
        title_label = QLabel("系统配置")
        title_label.setStyleSheet(f"""
            QLabel {{
                {get_typography_css('headline_small')}
                color: {MD3_ENHANCED_COLORS['on_surface']};
                font-weight: 600;
                padding-bottom: 4px;
            }}
        """)
        layout.addWidget(title_label)

        desc_label = QLabel("配置界面主题、系统日志和数据路径")
        desc_label.setStyleSheet(f"""
            QLabel {{
                {get_typography_css('body_medium')}
                color: {MD3_ENHANCED_COLORS['on_surface_variant']};
                padding-bottom: 16px;
            }}
        """)
        layout.addWidget(desc_label)

        # 日志配置组
        log_group = self._create_group(f"{MATERIAL_ICONS['assignment']}  日志配置")
        log_layout = QFormLayout()
        log_layout.setSpacing(12)
        log_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        # 日志级别
        self.log_level_combo = QComboBox()
        self.log_level_combo.addItems(["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"])
        self._style_combobox(self.log_level_combo)
        log_layout.addRow("日志级别:", self.log_level_combo)

        log_group.setLayout(log_layout)
        layout.addWidget(log_group)

        # 界面主题组
        theme_group = self._create_group(f"{MATERIAL_ICONS['masks']}  界面主题")
        theme_container_layout = QVBoxLayout()
        theme_container_layout.setSpacing(10)

        theme_layout = QFormLayout()
        theme_layout.setSpacing(12)
        theme_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        self.gui_theme_combo = QComboBox()
        self.gui_theme_combo.addItem("薄荷清新（默认）", "mint")
        self.gui_theme_combo.addItem("二次元（动漫）", "anime")
        self._style_combobox(self.gui_theme_combo)
        theme_layout.addRow("主题风格:", self.gui_theme_combo)
        theme_container_layout.addLayout(theme_layout)

        theme_hint = QLabel("提示：切换主题需重启应用后生效")
        theme_hint.setStyleSheet(
            f"""
            QLabel {{
                {get_typography_css('body_small')}
                color: {MD3_ENHANCED_COLORS['on_surface_variant']};
                background: transparent;
                padding-left: 8px;
            }}
            """
        )
        theme_container_layout.addWidget(theme_hint)

        theme_group.setLayout(theme_container_layout)
        layout.addWidget(theme_group)

        # 数据路径配置组
        path_group = self._create_group(f"{MATERIAL_ICONS['folder_open']}  数据路径")
        path_layout = QFormLayout()
        path_layout.setSpacing(12)
        path_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        # 数据根目录
        self.data_dir_input = QLineEdit()
        self.data_dir_input.setPlaceholderText("./data")
        self._style_input(self.data_dir_input)
        path_layout.addRow("数据根目录:", self.data_dir_input)

        path_group.setLayout(path_layout)
        layout.addWidget(path_group)

        # 嵌入模型配置组
        embedding_group = self._create_group("嵌入模型")
        embedding_layout = QFormLayout()
        embedding_layout.setSpacing(12)
        embedding_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        # 嵌入模型名称
        self.embedding_model_input = QLineEdit()
        self.embedding_model_input.setPlaceholderText("BAAI/bge-large-zh-v1.5")
        self._style_input(self.embedding_model_input)
        embedding_layout.addRow("模型名称:", self.embedding_model_input)

        embedding_group.setLayout(embedding_layout)
        layout.addWidget(embedding_group)

        layout.addStretch()

        scroll.setWidget(content)

        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.addWidget(scroll)

        return page

    @staticmethod
    def _create_group(title):
        """创建分组框 - v2.31.0 优化版：更现代的卡片设计，渐变背景"""
        group = QGroupBox(title)
        group.setStyleSheet(f"""
            QGroupBox {{
                background: qlineargradient(
                    x1:0, y1:0, x2:0, y2:1,
                    stop:0 {MD3_ENHANCED_COLORS['surface_container']},
                    stop:1 {MD3_ENHANCED_COLORS['surface_container_low']}
                );
                border: 1px solid {MD3_ENHANCED_COLORS['outline_variant']};
                border-radius: {MD3_ENHANCED_RADIUS['xl']};
                padding: 28px;
                margin-top: 12px;
                margin-bottom: 12px;
                {get_typography_css('title_small')}
                color: {MD3_ENHANCED_COLORS['on_surface']};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 8px 20px;
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 {MD3_ENHANCED_COLORS['secondary_container']},
                    stop:1 {MD3_ENHANCED_COLORS['tertiary_container']}
                );
                color: {MD3_ENHANCED_COLORS['on_secondary_container']};
                border-radius: {MD3_ENHANCED_RADIUS['full']};
                font-weight: 600;
                left: 12px;
            }}
        """)

        # v2.31.0 优化阴影效果
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(12)
        shadow.setXOffset(0)
        shadow.setYOffset(3)
        shadow.setColor(QColor(0, 0, 0, 15))
        group.setGraphicsEffect(shadow)

        return group

    @staticmethod
    def _style_input(widget):
        """设置输入框样式 - v2.31.0 优化版：更简洁现代"""
        widget.setStyleSheet(f"""
            QLineEdit {{
                background: {MD3_ENHANCED_COLORS['surface_container_high']};
                color: {MD3_ENHANCED_COLORS['on_surface']};
                border: 1px solid {MD3_ENHANCED_COLORS['outline_variant']};
                border-radius: {MD3_ENHANCED_RADIUS['md']};
                padding: 12px 16px;
                {get_typography_css('body_medium')}
                min-width: 280px;
                min-height: 48px;
                selection-background-color: {MD3_ENHANCED_COLORS['primary_container']};
                selection-color: {MD3_ENHANCED_COLORS['on_primary_container']};
            }}
            QLineEdit:focus {{
                border: 2px solid {MD3_ENHANCED_COLORS['primary']};
                background: {MD3_ENHANCED_COLORS['surface_bright']};
                padding: 11px 15px;
            }}
            QLineEdit:hover {{
                background: {MD3_ENHANCED_COLORS['surface_container_highest']};
                border: 1px solid {MD3_ENHANCED_COLORS['outline']};
            }}
            QLineEdit:disabled {{
                background: {MD3_ENHANCED_COLORS['surface_container']};
                color: {MD3_ENHANCED_COLORS['on_surface_variant']};
                border-color: {MD3_ENHANCED_COLORS['outline_variant']};
            }}
        """)

    @staticmethod
    def _style_textedit(widget):
        """设置文本编辑框样式 - v2.31.0 优化版"""
        widget.setStyleSheet(f"""
            QTextEdit {{
                background: {MD3_ENHANCED_COLORS['surface_container_high']};
                color: {MD3_ENHANCED_COLORS['on_surface']};
                border: 1px solid {MD3_ENHANCED_COLORS['outline_variant']};
                border-radius: {MD3_ENHANCED_RADIUS['md']};
                padding: 12px 16px;
                {get_typography_css('body_medium')}
                selection-background-color: {MD3_ENHANCED_COLORS['primary_container']};
                selection-color: {MD3_ENHANCED_COLORS['on_primary_container']};
            }}
            QTextEdit:focus {{
                border: 2px solid {MD3_ENHANCED_COLORS['primary']};
                background: {MD3_ENHANCED_COLORS['surface_bright']};
                padding: 11px 15px;
            }}
            QTextEdit:hover {{
                background: {MD3_ENHANCED_COLORS['surface_container_highest']};
                border: 1px solid {MD3_ENHANCED_COLORS['outline']};
            }}
            QTextEdit:disabled {{
                background: {MD3_ENHANCED_COLORS['surface_container']};
                color: {MD3_ENHANCED_COLORS['on_surface_variant']};
                border-color: {MD3_ENHANCED_COLORS['outline_variant']};
            }}
            QScrollBar:vertical {{
                background: {MD3_ENHANCED_COLORS['surface_container']};
                width: 8px;
                border-radius: 4px;
                margin: 0px;
            }}
            QScrollBar::handle:vertical {{
                background: {MD3_ENHANCED_COLORS['primary_40']};
                border-radius: 4px;
                min-height: 20px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {MD3_ENHANCED_COLORS['primary_50']};
            }}
            QScrollBar::handle:vertical:pressed {{
                background: {MD3_ENHANCED_COLORS['primary_60']};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background: none;
            }}
        """)

    @staticmethod
    def _style_checkbox(widget):
        """设置复选框样式 - v2.31.0 优化版"""
        widget.setStyleSheet(f"""
            QCheckBox {{
                color: {MD3_ENHANCED_COLORS['on_surface']};
                {get_typography_css('body_medium')}
                spacing: 12px;
                background: transparent;
                min-height: 44px;
                padding: 4px 0;
            }}
            QCheckBox::indicator {{
                width: 20px;
                height: 20px;
                border: 2px solid {MD3_ENHANCED_COLORS['outline']};
                border-radius: {MD3_ENHANCED_RADIUS['xs']};
                background: {MD3_ENHANCED_COLORS['surface_container_high']};
            }}
            QCheckBox::indicator:hover {{
                background: {MD3_ENHANCED_COLORS['surface_container_highest']};
                border-color: {MD3_ENHANCED_COLORS['primary']};
            }}
            QCheckBox::indicator:checked {{
                background: {MD3_ENHANCED_COLORS['primary']};
                border-color: {MD3_ENHANCED_COLORS['primary']};
                image: url(data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMTYiIGhlaWdodD0iMTYiIHZpZXdCb3g9IjAgMCAxNiAxNiIgZmlsbD0ibm9uZSIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj48cGF0aCBkPSJNMTMuMzMzMyA0TDYgMTEuMzMzM0wyLjY2NjY3IDgiIHN0cm9rZT0id2hpdGUiIHN0cm9rZS13aWR0aD0iMiIgc3Ryb2tlLWxpbmVjYXA9InJvdW5kIiBzdHJva2UtbGluZWpvaW49InJvdW5kIi8+PC9zdmc+);
            }}
            QCheckBox::indicator:checked:hover {{
                background: {MD3_ENHANCED_COLORS['primary_60']};
            }}
        """)

    @staticmethod
    def _style_spinbox(widget):
        """设置数字输入框样式 - v2.31.0 优化版"""
        widget.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        widget.setStyleSheet(f"""
            QSpinBox, QDoubleSpinBox {{
                background: {MD3_ENHANCED_COLORS['surface_container_high']};
                color: {MD3_ENHANCED_COLORS['on_surface']};
                border: 1px solid {MD3_ENHANCED_COLORS['outline_variant']};
                border-radius: {MD3_ENHANCED_RADIUS['md']};
                padding: 12px 16px;
                {get_typography_css('body_medium')}
                min-width: 140px;
                min-height: 48px;
            }}
            QSpinBox:focus, QDoubleSpinBox:focus {{
                border: 2px solid {MD3_ENHANCED_COLORS['primary']};
                background: {MD3_ENHANCED_COLORS['surface_bright']};
                padding: 11px 15px;
            }}
            QSpinBox:hover, QDoubleSpinBox:hover {{
                background: {MD3_ENHANCED_COLORS['surface_container_highest']};
                border: 1px solid {MD3_ENHANCED_COLORS['outline']};
            }}
        """)

    @staticmethod
    def _style_combobox(widget):
        """设置下拉框样式 - v2.31.0 优化版"""
        widget.setStyleSheet(f"""
            QComboBox {{
                background: {MD3_ENHANCED_COLORS['surface_container_high']};
                color: {MD3_ENHANCED_COLORS['on_surface']};
                border: 1px solid {MD3_ENHANCED_COLORS['outline_variant']};
                border-radius: {MD3_ENHANCED_RADIUS['md']};
                padding: 12px 16px;
                {get_typography_css('body_medium')}
                min-width: 140px;
                min-height: 48px;
            }}
            QComboBox:focus {{
                border: 2px solid {MD3_ENHANCED_COLORS['primary']};
                background: {MD3_ENHANCED_COLORS['surface_bright']};
                padding: 11px 15px;
            }}
            QComboBox:hover {{
                background: {MD3_ENHANCED_COLORS['surface_container_highest']};
                border: 1px solid {MD3_ENHANCED_COLORS['outline']};
            }}
            QComboBox::drop-down {{
                border: none;
                width: 32px;
            }}
            QComboBox::down-arrow {{
                image: none;
                border: none;
            }}
            QComboBox QAbstractItemView {{
                background: {MD3_ENHANCED_COLORS['surface_container_high']};
                color: {MD3_ENHANCED_COLORS['on_surface']};
                border: 1px solid {MD3_ENHANCED_COLORS['outline_variant']};
                border-radius: {MD3_ENHANCED_RADIUS['md']};
                padding: 4px;
                selection-background-color: {MD3_ENHANCED_COLORS['primary_container']};
                selection-color: {MD3_ENHANCED_COLORS['on_primary_container']};
            }}
        """)

    @staticmethod
    def _style_label(widget):
        """设置标签样式"""
        widget.setStyleSheet(f"""
            QLabel {{
                color: {MD3_LIGHT_COLORS['on_surface']};
                font-size: 14px;
                font-weight: 500;
                background: transparent;
            }}
        """)

    def _merge_settings(self, user_settings: dict):
        """合并用户设置到配置数据

        Args:
            user_settings: 用户特定设置
        """
        def deep_merge(base: dict, override: dict):
            """深度合并字典"""
            for key, value in override.items():
                if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                    deep_merge(base[key], value)
                else:
                    base[key] = value

        deep_merge(self.config_data, user_settings)

    def _reload_config_data(self) -> None:
        """重新加载配置（全局配置 + 用户覆盖）。"""
        # 加载全局配置作为默认值
        self.config_data = self._load_config() or {}

        # 如果用户已登录，加载用户特定设置并覆盖
        if user_session.is_logged_in():
            try:
                user_settings = user_session.get_settings()
                if user_settings:
                    self._merge_settings(user_settings)
            except Exception as e:
                logger.info("加载用户设置失败: %s", e)

    def _apply_config_to_widgets(self) -> None:
        """将当前 config_data 应用到已创建的控件（懒加载页面可能尚未构建）。"""
        self._suppress_unsaved_changes = True
        try:
            llm_config = self.config_data.get("LLM", {})
            if hasattr(self, "api_input"):
                self.api_input.setText(llm_config.get("api", ""))
            if hasattr(self, "key_input"):
                self.key_input.setText(llm_config.get("key", ""))
            if hasattr(self, "model_input"):
                self.model_input.setText(llm_config.get("model", ""))

            extra_config = llm_config.get("extra_config", {})
            if extra_config and hasattr(self, "temperature_input"):
                self.temperature_input.setValue(extra_config.get("temperature", 0.7))

            agent_config = self.config_data.get("Agent", {})
            if hasattr(self, "is_up_checkbox"):
                self.is_up_checkbox.setChecked(agent_config.get("is_up", True))
            if hasattr(self, "char_input"):
                self.char_input.setText(agent_config.get("char", ""))
            if hasattr(self, "user_input"):
                self.user_input.setText(agent_config.get("user", ""))
            if hasattr(self, "char_settings_input"):
                self.char_settings_input.setPlainText(agent_config.get("char_settings", ""))
            if hasattr(self, "char_personalities_input"):
                self.char_personalities_input.setPlainText(agent_config.get("char_personalities", ""))
            if hasattr(self, "context_length_input"):
                self.context_length_input.setValue(agent_config.get("context_length", 40))

            # 记忆系统配置
            if hasattr(self, "long_memory_checkbox"):
                self.long_memory_checkbox.setChecked(agent_config.get("long_memory", True))
            if hasattr(self, "is_check_memorys_checkbox"):
                self.is_check_memorys_checkbox.setChecked(agent_config.get("is_check_memorys", True))
            if hasattr(self, "is_core_mem_checkbox"):
                self.is_core_mem_checkbox.setChecked(agent_config.get("is_core_mem", True))
            if hasattr(self, "mem_thresholds_input"):
                self.mem_thresholds_input.setValue(agent_config.get("mem_thresholds", 0.385))

            # v2.30.36: 智能日记系统配置
            if hasattr(self, "smart_diary_checkbox"):
                self.smart_diary_checkbox.setChecked(agent_config.get("smart_diary_enabled", True))
            if hasattr(self, "daily_summary_checkbox"):
                self.daily_summary_checkbox.setChecked(agent_config.get("daily_summary_enabled", True))
            if hasattr(self, "diary_importance_threshold_input"):
                self.diary_importance_threshold_input.setValue(
                    agent_config.get("diary_importance_threshold", 0.6)
                )

            # 知识库配置
            if hasattr(self, "lore_books_checkbox"):
                self.lore_books_checkbox.setChecked(agent_config.get("lore_books", True))
            if hasattr(self, "books_thresholds_input"):
                self.books_thresholds_input.setValue(agent_config.get("books_thresholds", 0.5))
            if hasattr(self, "scan_depth_input"):
                self.scan_depth_input.setValue(agent_config.get("scan_depth", 4))

            # 系统配置
            if hasattr(self, "log_level_combo"):
                self.log_level_combo.setCurrentText(self.config_data.get("log_level", "INFO"))
            if hasattr(self, "data_dir_input"):
                self.data_dir_input.setText(self.config_data.get("data_dir", "./data"))
            if hasattr(self, "embedding_model_input"):
                self.embedding_model_input.setText(
                    self.config_data.get("embedding_model", "BAAI/bge-large-zh-v1.5")
                )

            gui_config = self.config_data.get("GUI") or self.config_data.get("gui") or {}
            if hasattr(self, "gui_theme_combo") and isinstance(gui_config, dict):
                theme = gui_config.get("theme", "mint")
                for idx in range(self.gui_theme_combo.count()):
                    if self.gui_theme_combo.itemData(idx) == theme:
                        self.gui_theme_combo.setCurrentIndex(idx)
                        break

            # 头像（仅登录用户）
            if user_session.is_logged_in():
                if hasattr(self, "user_avatar_input"):
                    self.user_avatar_input.setText(user_session.get_user_avatar())
                if hasattr(self, "ai_avatar_input"):
                    self.ai_avatar_input.setText(user_session.get_ai_avatar())
        finally:
            self._suppress_unsaved_changes = False

    def load_settings(self):
        """加载设置到界面"""
        self._reload_config_data()
        self._apply_config_to_widgets()

    def save_settings(self):
        """保存设置"""
        self._is_saving = True
        try:
            # 更新配置数据（懒加载页面可能未构建：仅覆盖“已创建控件”的字段）
            if "LLM" not in self.config_data:
                self.config_data["LLM"] = {}
            if "Agent" not in self.config_data:
                self.config_data["Agent"] = {}

            # LLM 配置
            if hasattr(self, "api_input"):
                self.config_data["LLM"]["api"] = self.api_input.text()
            if hasattr(self, "key_input"):
                self.config_data["LLM"]["key"] = self.key_input.text()
            if hasattr(self, "model_input"):
                self.config_data["LLM"]["model"] = self.model_input.text()

            if "extra_config" not in self.config_data["LLM"]:
                self.config_data["LLM"]["extra_config"] = {}
            if hasattr(self, "temperature_input"):
                self.config_data["LLM"]["extra_config"]["temperature"] = self.temperature_input.value()

            # Agent 配置
            if hasattr(self, "is_up_checkbox"):
                self.config_data["Agent"]["is_up"] = self.is_up_checkbox.isChecked()
            if hasattr(self, "char_input"):
                self.config_data["Agent"]["char"] = self.char_input.text()
            if hasattr(self, "user_input"):
                self.config_data["Agent"]["user"] = self.user_input.text()
            if hasattr(self, "char_settings_input"):
                self.config_data["Agent"]["char_settings"] = self.char_settings_input.toPlainText()
            if hasattr(self, "char_personalities_input"):
                self.config_data["Agent"]["char_personalities"] = self.char_personalities_input.toPlainText()
            if hasattr(self, "context_length_input"):
                self.config_data["Agent"]["context_length"] = self.context_length_input.value()

            # 记忆系统配置
            if hasattr(self, "long_memory_checkbox"):
                self.config_data["Agent"]["long_memory"] = self.long_memory_checkbox.isChecked()
            if hasattr(self, "is_check_memorys_checkbox"):
                self.config_data["Agent"]["is_check_memorys"] = self.is_check_memorys_checkbox.isChecked()
            if hasattr(self, "is_core_mem_checkbox"):
                self.config_data["Agent"]["is_core_mem"] = self.is_core_mem_checkbox.isChecked()
            if hasattr(self, "mem_thresholds_input"):
                self.config_data["Agent"]["mem_thresholds"] = self.mem_thresholds_input.value()

            # v2.30.36: 智能日记系统配置
            if hasattr(self, "smart_diary_checkbox"):
                self.config_data["Agent"]["smart_diary_enabled"] = self.smart_diary_checkbox.isChecked()
            if hasattr(self, "daily_summary_checkbox"):
                self.config_data["Agent"]["daily_summary_enabled"] = self.daily_summary_checkbox.isChecked()
            if hasattr(self, "diary_importance_threshold_input"):
                self.config_data["Agent"]["diary_importance_threshold"] = (
                    self.diary_importance_threshold_input.value()
                )

            # 知识库配置
            if hasattr(self, "lore_books_checkbox"):
                self.config_data["Agent"]["lore_books"] = self.lore_books_checkbox.isChecked()
            if hasattr(self, "books_thresholds_input"):
                self.config_data["Agent"]["books_thresholds"] = self.books_thresholds_input.value()
            if hasattr(self, "scan_depth_input"):
                self.config_data["Agent"]["scan_depth"] = self.scan_depth_input.value()

            # 系统配置
            if hasattr(self, "log_level_combo"):
                self.config_data["log_level"] = self.log_level_combo.currentText()
            if hasattr(self, "data_dir_input"):
                self.config_data["data_dir"] = self.data_dir_input.text()
            if hasattr(self, "embedding_model_input"):
                self.config_data["embedding_model"] = self.embedding_model_input.text()
            if hasattr(self, "gui_theme_combo"):
                if "GUI" not in self.config_data or not isinstance(self.config_data.get("GUI"), dict):
                    self.config_data["GUI"] = {}
                theme_value = self.gui_theme_combo.currentData() or "mint"
                self.config_data["GUI"]["theme"] = str(theme_value)

            # v2.22.0 保存头像设置
            if user_session.is_logged_in():
                try:
                    # 保存用户头像
                    user_avatar = self.user_avatar_input.text() if hasattr(self, "user_avatar_input") else ""
                    if user_avatar and hasattr(user_session, "update_user_avatar"):
                        user_session.update_user_avatar(user_avatar)
                        logger.info("用户头像已更新: %s", user_avatar)

                    # 保存AI助手头像
                    ai_avatar = self.ai_avatar_input.text() if hasattr(self, "ai_avatar_input") else ""
                    if ai_avatar and hasattr(user_session, "update_ai_avatar"):
                        user_session.update_ai_avatar(ai_avatar)
                        logger.info("AI助手头像已更新: %s", ai_avatar)

                    # 保存其他设置到数据库
                    user_session.save_settings(self.config_data)
                    logger.info("用户设置已保存到数据库")
                except Exception as e:
                    logger.info("保存用户设置到数据库失败: %s", e)

            # 同时保存到全局配置文件（作为默认值）
            config_file = Path("config.yaml")
            tmp_file = config_file.with_name(config_file.name + ".tmp")
            try:
                with open(tmp_file, "w", encoding="utf-8") as f:
                    yaml.safe_dump(self.config_data, f, allow_unicode=True, sort_keys=False)
                tmp_file.replace(config_file)
            finally:
                try:
                    if tmp_file.exists():
                        tmp_file.unlink()
                except Exception:
                    pass

            # v2.24.0 显示成功消息 - 更友好的提示
            QMessageBox.information(
                self,
                "✅ 保存成功",
                "设置已成功保存！"
            )

            # v2.24.0 标记为已保存
            self._mark_as_saved()

            # 发送信号
            self.settings_saved.emit()

        except Exception as e:
            QMessageBox.critical(
                self,
                "❌ 保存失败",
                f"保存设置时出错：\n\n{str(e)}\n\n请检查配置文件权限或联系管理员。"
            )
        finally:
            self._is_saving = False

    def _mark_as_saved(self):
        """标记为已保存 - v2.24.0 新增"""
        self._has_unsaved_changes = False
        self.unsaved_indicator.hide()

    def _mark_as_unsaved(self):
        """标记为未保存 - v2.24.0 新增"""
        if self._is_saving or self._suppress_unsaved_changes:
            return
        if not self._has_unsaved_changes:
            self._has_unsaved_changes = True
            self.unsaved_indicator.show()
            # 添加淡入动画
            fade_in = QPropertyAnimation(self.unsaved_indicator, b"windowOpacity")
            fade_in.setDuration(200)
            fade_in.setStartValue(0.0)
            fade_in.setEndValue(1.0)
            fade_in.start()

    def _wire_unsaved_tracking(self, root: QWidget) -> None:
        """为页面内的输入控件绑定“未保存”状态追踪。"""
        if root is None:
            return

        def _on_change(*_args) -> None:
            self._mark_as_unsaved()

        for widget in root.findChildren(QLineEdit):
            try:
                widget.textChanged.connect(_on_change)
            except Exception:
                pass

        for widget in root.findChildren(QTextEdit):
            try:
                widget.textChanged.connect(_on_change)
            except Exception:
                pass

        for widget in root.findChildren(QComboBox):
            try:
                widget.currentIndexChanged.connect(_on_change)
            except Exception:
                pass

        for widget in root.findChildren(QSpinBox):
            try:
                widget.valueChanged.connect(_on_change)
            except Exception:
                pass

        for widget in root.findChildren(QDoubleSpinBox):
            try:
                widget.valueChanged.connect(_on_change)
            except Exception:
                pass

        for widget in root.findChildren(QCheckBox):
            try:
                widget.stateChanged.connect(_on_change)
            except Exception:
                pass

    def _update_avatar_preview(self, avatar_type: str):
        """更新头像预览 - v2.24.0 新增

        Args:
            avatar_type: 'user' 或 'ai'
        """
        if avatar_type == 'user':
            avatar_text = self.user_avatar_input.text()
            preview_label = self.user_avatar_preview
            default_emoji = "👤"
        else:
            avatar_text = self.ai_avatar_input.text()
            preview_label = self.ai_avatar_preview
            default_emoji = "🐱"

        # 检查是否为图片路径
        if avatar_text and Path(avatar_text).exists() and Path(avatar_text).is_file():
            # 加载图片并创建圆形预览
            pixmap = QPixmap(avatar_text)
            if not pixmap.isNull():
                # 缩放图片
                size = 96
                scaled_pixmap = pixmap.scaled(
                    size, size,
                    Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                    Qt.TransformationMode.SmoothTransformation
                )

                # 裁剪为正方形
                if scaled_pixmap.width() > size or scaled_pixmap.height() > size:
                    x = (scaled_pixmap.width() - size) // 2
                    y = (scaled_pixmap.height() - size) // 2
                    scaled_pixmap = scaled_pixmap.copy(x, y, size, size)

                # 创建圆形遮罩
                rounded_pixmap = QPixmap(size, size)
                rounded_pixmap.fill(Qt.GlobalColor.transparent)

                painter = QPainter(rounded_pixmap)
                painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

                # 创建圆形路径
                path = QPainterPath()
                path.addEllipse(0, 0, size, size)

                # 裁剪并绘制
                painter.setClipPath(path)
                painter.drawPixmap(0, 0, scaled_pixmap)
                painter.end()

                preview_label.setPixmap(rounded_pixmap)
                preview_label.setScaledContents(False)
                preview_label.setText("")  # 清除文本
            else:
                # 图片加载失败，使用默认emoji
                preview_label.setPixmap(QPixmap())
                preview_label.setText(default_emoji)
        else:
            # emoji 或无效路径：直接显示文本
            preview_label.setPixmap(QPixmap())
            preview_label.setText(avatar_text if avatar_text else default_emoji)

        # 标记为未保存
        self._mark_as_unsaved()

    def _choose_avatar(self, avatar_type: str):
        """选择头像图片 - v2.24.0 优化

        Args:
            avatar_type: 'user' 或 'ai'
        """
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择头像图片",
            "",
            "图片文件 (*.png *.jpg *.jpeg *.gif *.bmp *.webp);;所有文件 (*.*)"
        )

        if file_path:
            if avatar_type == 'user':
                self.user_avatar_input.setText(file_path)
            else:
                self.ai_avatar_input.setText(file_path)

            # 预览会通过textChanged信号自动更新

    def _open_memory_manager(self):
        """打开记忆管理器 - v2.30.32 新增"""
        if not self.agent:
            QMessageBox.warning(
                self,
                "提示",
                "Agent 未初始化，无法打开记忆管理器"
            )
            return

        if not hasattr(self.agent, 'diary_memory') or not self.agent.diary_memory:
            QMessageBox.warning(
                self,
                "提示",
                "日记功能未启用，无法打开记忆管理器"
            )
            return

        # 导入记忆管理器
        from src.gui.memory_manager import MemoryManagerWidget
        from PyQt6.QtWidgets import QDialog

        # 创建对话框
        dialog = QDialog(self)
        dialog.setWindowTitle("记忆管理")
        dialog.setMinimumSize(1200, 800)

        # 创建记忆管理器
        memory_manager = MemoryManagerWidget(self.agent, dialog)

        # 设置布局
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(memory_manager)

        # 显示对话框
        dialog.exec()

    def _open_lorebook_manager(self):
        """打开知识库管理器 - v2.30.38 新增"""
        if not self.agent:
            QMessageBox.warning(
                self,
                "提示",
                "Agent 未初始化，无法打开知识库管理器"
            )
            return

        if not hasattr(self.agent, 'lore_book') or not self.agent.lore_book:
            QMessageBox.warning(
                self,
                "提示",
                "知识库功能未启用，无法打开知识库管理器"
            )
            return

        # 导入知识库管理器
        from src.gui.lore_book_manager import LoreBookManagerWidget
        from PyQt6.QtWidgets import QDialog

        # 创建对话框
        dialog = QDialog(self)
        dialog.setWindowTitle("知识库管理")
        dialog.setMinimumSize(1200, 800)

        # 创建知识库管理器
        lorebook_manager = LoreBookManagerWidget(self.agent, dialog)

        # 设置布局
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(lorebook_manager)

        # 显示对话框
        dialog.exec()

    def _clear_avatar(self, avatar_type: str):
        """清除头像 - v2.24.0 新增

        Args:
            avatar_type: 'user' 或 'ai'
        """
        if avatar_type == 'user':
            self.user_avatar_input.clear()
        else:
            self.ai_avatar_input.clear()
