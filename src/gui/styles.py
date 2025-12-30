"""
MintChat GUI 样式表

提供现代化的深色主题样式，参考 QQ 设计
"""

# 主题色
THEME_COLORS = {
    # 主色调
    "primary": "#1890ff",  # 蓝色
    "primary_hover": "#40a9ff",
    "primary_active": "#096dd9",
    # 背景色
    "bg_dark": "#1e1e1e",  # 深色背景
    "bg_darker": "#141414",  # 更深的背景
    "bg_light": "#2d2d2d",  # 浅色背景
    "bg_hover": "#3d3d3d",  # 悬停背景
    # 文字色
    "text_primary": "#ffffff",
    "text_secondary": "#b0b0b0",
    "text_disabled": "#666666",
    # 边框色
    "border": "#3d3d3d",
    "border_light": "#4d4d4d",
    # 消息气泡
    "bubble_user": "#1890ff",  # 用户消息（蓝色）
    "bubble_ai": "#2d2d2d",  # AI消息（深灰色）
    # 状态色
    "success": "#52c41a",
    "warning": "#faad14",
    "error": "#f5222d",
    "info": "#1890ff",
}


# 主窗口样式
MAIN_WINDOW_STYLE = f"""
QMainWindow {{
    background-color: {THEME_COLORS['bg_dark']};
}}

/* 标题栏 */
QWidget#titleBar {{
    background-color: {THEME_COLORS['bg_darker']};
    border-bottom: 1px solid {THEME_COLORS['border']};
}}

/* 侧边栏 */
QWidget#sidebar {{
    background-color: {THEME_COLORS['bg_darker']};
    border-right: 1px solid {THEME_COLORS['border']};
}}

/* 聊天区域 */
QWidget#chatArea {{
    background-color: {THEME_COLORS['bg_dark']};
}}

/* 输入区域 */
QWidget#inputArea {{
    background-color: {THEME_COLORS['bg_light']};
    border-top: 1px solid {THEME_COLORS['border']};
}}
"""


# 按钮样式
BUTTON_STYLE = f"""
QPushButton {{
    background-color: {THEME_COLORS['primary']};
    color: {THEME_COLORS['text_primary']};
    border: none;
    border-radius: 4px;
    padding: 8px 16px;
    font-size: 14px;
    font-weight: 500;
}}

QPushButton:hover {{
    background-color: {THEME_COLORS['primary_hover']};
}}

QPushButton:pressed {{
    background-color: {THEME_COLORS['primary_active']};
}}

QPushButton:disabled {{
    background-color: {THEME_COLORS['bg_light']};
    color: {THEME_COLORS['text_disabled']};
}}

/* 次要按钮 */
QPushButton#secondaryButton {{
    background-color: {THEME_COLORS['bg_light']};
    color: {THEME_COLORS['text_primary']};
}}

QPushButton#secondaryButton:hover {{
    background-color: {THEME_COLORS['bg_hover']};
}}

/* 图标按钮 */
QPushButton#iconButton {{
    background-color: transparent;
    border: none;
    padding: 8px;
    border-radius: 4px;
}}

QPushButton#iconButton:hover {{
    background-color: {THEME_COLORS['bg_hover']};
}}
"""


# 输入框样式
INPUT_STYLE = f"""
QTextEdit {{
    background-color: {THEME_COLORS['bg_light']};
    color: {THEME_COLORS['text_primary']};
    border: 1px solid {THEME_COLORS['border']};
    border-radius: 4px;
    padding: 8px;
    font-size: 14px;
    selection-background-color: {THEME_COLORS['primary']};
}}

QTextEdit:focus {{
    border: 1px solid {THEME_COLORS['primary']};
}}

QLineEdit {{
    background-color: {THEME_COLORS['bg_light']};
    color: {THEME_COLORS['text_primary']};
    border: 1px solid {THEME_COLORS['border']};
    border-radius: 4px;
    padding: 8px 12px;
    font-size: 14px;
    selection-background-color: {THEME_COLORS['primary']};
}}

QLineEdit:focus {{
    border: 1px solid {THEME_COLORS['primary']};
}}
"""


# 滚动条样式
SCROLLBAR_STYLE = f"""
QScrollBar:vertical {{
    background-color: {THEME_COLORS['bg_dark']};
    width: 8px;
    border: none;
}}

QScrollBar::handle:vertical {{
    background-color: {THEME_COLORS['bg_hover']};
    border-radius: 4px;
    min-height: 20px;
}}

QScrollBar::handle:vertical:hover {{
    background-color: {THEME_COLORS['border_light']};
}}

QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical {{
    height: 0px;
}}

QScrollBar::add-page:vertical,
QScrollBar::sub-page:vertical {{
    background: none;
}}

QScrollBar:horizontal {{
    background-color: {THEME_COLORS['bg_dark']};
    height: 8px;
    border: none;
}}

QScrollBar::handle:horizontal {{
    background-color: {THEME_COLORS['bg_hover']};
    border-radius: 4px;
    min-width: 20px;
}}

QScrollBar::handle:horizontal:hover {{
    background-color: {THEME_COLORS['border_light']};
}}

QScrollBar::add-line:horizontal,
QScrollBar::sub-line:horizontal {{
    width: 0px;
}}

QScrollBar::add-page:horizontal,
QScrollBar::sub-page:horizontal {{
    background: none;
}}
"""


# 标签样式
LABEL_STYLE = f"""
QLabel {{
    color: {THEME_COLORS['text_primary']};
    font-size: 14px;
}}

QLabel#titleLabel {{
    font-size: 16px;
    font-weight: bold;
}}

QLabel#subtitleLabel {{
    color: {THEME_COLORS['text_secondary']};
    font-size: 12px;
}}
"""


# 列表样式
LIST_STYLE = f"""
QListWidget {{
    background-color: {THEME_COLORS['bg_darker']};
    color: {THEME_COLORS['text_primary']};
    border: none;
    outline: none;
}}

QListWidget::item {{
    padding: 12px;
    border-bottom: 1px solid {THEME_COLORS['border']};
}}

QListWidget::item:hover {{
    background-color: {THEME_COLORS['bg_hover']};
}}

QListWidget::item:selected {{
    background-color: {THEME_COLORS['primary']};
    color: {THEME_COLORS['text_primary']};
}}
"""


# 组合所有样式
COMPLETE_STYLE = (
    MAIN_WINDOW_STYLE + BUTTON_STYLE + INPUT_STYLE + SCROLLBAR_STYLE + LABEL_STYLE + LIST_STYLE
)


def get_message_bubble_style(is_user: bool) -> str:
    """
    获取消息气泡样式

    Args:
        is_user: 是否为用户消息

    Returns:
        str: CSS 样式字符串
    """
    bg_color = THEME_COLORS["bubble_user"] if is_user else THEME_COLORS["bubble_ai"]

    return f"""
        background-color: {bg_color};
        color: {THEME_COLORS['text_primary']};
        border-radius: 8px;
        padding: 10px 14px;
        max-width: 60%;
        word-wrap: break-word;
    """
