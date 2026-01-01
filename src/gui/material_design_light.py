"""
Material Design 3 浅色主题设计系统

基于 Google Material Design 3 规范（2024）
参考 QQ 现代化界面设计
使用可爱的渐变色和浅色配色方案
"""

# ============================================================================
# Material Design 3 浅色主题颜色系统
# ============================================================================

from functools import lru_cache

MD3_LIGHT_COLORS = {
    # Primary - 薄荷绿主题色（加深版）
    "primary": "#4ECDC4",  # 主薄荷绿（加深）
    "primary_light": "#7FE5D8",  # 浅薄荷绿
    "primary_lighter": "#A8E6CF",  # 更浅的薄荷绿
    "on_primary": "#FFFFFF",  # 主色上的文字
    "primary_container": "#C8F3E8",  # 主色容器（加深的薄荷绿）
    "primary_container_dark": "#A8E6CF",  # 主色容器深色版
    "on_primary_container": "#1B5E4A",  # 主色容器上的文字（深绿）
    # Secondary - 青绿色渐变（加深版）
    "secondary": "#3DBDB4",  # 主青绿色（加深）
    "secondary_light": "#7FD9CF",  # 浅青绿色
    "secondary_lighter": "#B3E8E0",  # 更浅的青绿色
    "on_secondary": "#FFFFFF",  # 次色上的文字
    "secondary_container": "#D5F4F1",  # 次色容器（加深）
    "on_secondary_container": "#1A5C56",  # 次色容器上的文字
    # Tertiary - 天蓝色渐变（加深版）
    "tertiary": "#5FCFED",  # 主天蓝色（加深）
    "tertiary_light": "#8FE0F5",  # 浅天蓝色
    "tertiary_lighter": "#B3ECFF",  # 更浅的天蓝色
    "on_tertiary": "#FFFFFF",  # 第三色上的文字
    "tertiary_container": "#D9F5FF",  # 第三色容器（加深）
    "on_tertiary_container": "#1A5A6B",  # 第三色容器上的文字
    # Success - 柔和的绿色
    "success": "#66BB6A",  # 成功绿
    "success_light": "#C8E6C9",  # 浅绿色
    "on_success": "#FFFFFF",  # 成功色上的文字
    "success_container": "#E8F5E9",  # 成功容器
    "on_success_container": "#2E7D32",  # 成功容器上的文字
    # Warning - 柔和的橙色
    "warning": "#FFA726",  # 警告橙
    "warning_light": "#FFE0B2",  # 浅橙色
    "on_warning": "#FFFFFF",  # 警告色上的文字
    "warning_container": "#FFF3E0",  # 警告容器
    "on_warning_container": "#E65100",  # 警告容器上的文字
    # Error - 柔和的红色
    "error": "#EF5350",  # 错误红
    "error_light": "#FFCDD2",  # 浅红色
    "on_error": "#FFFFFF",  # 错误色上的文字
    "error_container": "#FFEBEE",  # 错误容器
    "on_error_container": "#C62828",  # 错误容器上的文字
    # Surface - 浅色背景（薄荷绿调）
    "surface": "#F8FFFE",  # 主表面（极淡薄荷绿）
    "surface_dim": "#E8F8F5",  # 暗表面（淡薄荷绿）
    "surface_bright": "#FFFFFF",  # 亮表面
    "surface_container_lowest": "#FFFFFF",  # 最低容器
    "surface_container_low": "#F0FBF8",  # 低容器（极淡薄荷绿）
    "surface_container": "#E8F8F5",  # 容器（淡薄荷绿）
    "surface_container_high": "#D8F3ED",  # 高容器（薄荷绿）
    "surface_container_highest": "#C8F3E8",  # 最高容器（明显薄荷绿）
    "on_surface": "#1A1C1E",  # 表面上的文字
    "on_surface_variant": "#42474E",  # 表面变体上的文字
    # Background - 背景色（薄荷绿调）
    "background": "#F0FBF8",  # 背景（淡薄荷绿）
    "on_background": "#1A1C1E",  # 背景上的文字
    # Outline - 边框（薄荷绿调）
    "outline": "#C8F3E8",  # 边框（薄荷绿）
    "outline_variant": "#D8F3ED",  # 边框变体（淡薄荷绿）
    # Shadow - 阴影
    "shadow": "#000000",  # 阴影
    "scrim": "#000000",  # 遮罩
    # Inverse - 反色
    "inverse_surface": "#2D3132",  # 反色表面
    "inverse_on_surface": "#EFF1F1",  # 反色表面上的文字
    "inverse_primary": "#7FE5D8",  # 反色主色
    # 薄荷绿渐变色（加深版 - 更明显的薄荷绿效果）
    # 薄荷绿到青绿
    "gradient_mint_cyan": (
        "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #7FE5D8, stop:1 #7FD9CF)"
    ),
    # 青绿到天蓝
    "gradient_cyan_blue": (
        "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #7FD9CF, stop:1 #8FE0F5)"
    ),
    # 薄荷绿到天蓝
    "gradient_mint_blue": (
        "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #7FE5D8, stop:1 #8FE0F5)"
    ),
    # 淡薄荷绿到薄荷绿（加深）
    "gradient_light_mint": (
        "qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #F0FBF8, stop:1 #C8F3E8)"
    ),
    # 柔和薄荷渐变（加深）
    "gradient_soft_mint": (
        "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #D8F3ED, stop:1 #D5F4F1)"
    ),
    # 垂直薄荷渐变
    "gradient_mint_vertical": (
        "qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #C8F3E8, stop:1 #D8F3ED)"
    ),
    # 径向薄荷渐变
    "gradient_mint_radial": (
        "qlineargradient(x1:0.5, y1:0.5, x2:1, y2:1, stop:0 #C8F3E8, stop:1 #A8E6CF)"
    ),
    # 毛玻璃效果背景（薄荷绿调 - 加深版）
    "frosted_glass": "rgba(240, 251, 248, 0.90)",  # 半透明薄荷绿
    "frosted_glass_mint": "rgba(200, 243, 232, 0.92)",  # 半透明薄荷绿（加深）
    "frosted_glass_dark": "rgba(216, 243, 237, 0.94)",  # 半透明薄荷绿（更深）
}


def _apply_color_overrides(
    base: dict[str, str],
    overrides: dict[str, str],
) -> dict[str, str]:
    merged = dict(base)
    merged.update(overrides)
    return merged


_ANIME_LIGHT_COLOR_OVERRIDES: dict[str, str] = {
    # Anime / Kawaii: Sakura Pink + Lavender + Sky Blue
    "primary": "#FF6FAE",
    "primary_light": "#FF9FCB",
    "primary_lighter": "#FFD2E6",
    "on_primary": "#FFFFFF",
    "primary_container": "#FFE3F1",
    "primary_container_dark": "#FFD2E6",
    "on_primary_container": "#5A1235",
    "secondary": "#8B7DFF",
    "secondary_light": "#B1A8FF",
    "secondary_lighter": "#DAD6FF",
    "on_secondary": "#FFFFFF",
    "secondary_container": "#ECEAFF",
    "on_secondary_container": "#2A1A5C",
    "tertiary": "#5AB6FF",
    "tertiary_light": "#8FD1FF",
    "tertiary_lighter": "#C7E8FF",
    "on_tertiary": "#FFFFFF",
    "tertiary_container": "#DDF3FF",
    "on_tertiary_container": "#0B375C",
    "surface": "#FFFCFE",
    "surface_dim": "#FFF2FA",
    "surface_container_low": "#FFF7FB",
    "surface_container": "#FFF2FA",
    "surface_container_high": "#FFE3F1",
    "surface_container_highest": "#FFD2E6",
    "on_surface_variant": "#4A3E49",
    "background": "#FFF7FB",
    "outline": "#F1C3DA",
    "outline_variant": "#F6D8E7",
    # Keep key names for compatibility; update stops for anime feel.
    "gradient_mint_cyan": "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #FF9FCB, stop:1 #B1A8FF)",
    "gradient_cyan_blue": "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #B1A8FF, stop:1 #8FD1FF)",
    "gradient_mint_blue": "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #FF9FCB, stop:1 #8FD1FF)",
    "gradient_light_mint": (
        "qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #FFF7FB, stop:1 #FFE3F1)"
    ),
    "gradient_soft_mint": "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #FFF2FA, stop:1 #ECEAFF)",
    "gradient_mint_vertical": (
        "qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #FFD2E6, stop:1 #FFE3F1)"
    ),
    "gradient_mint_radial": (
        "qlineargradient(x1:0.5, y1:0.5, x2:1, y2:1, stop:0 #FFD2E6, stop:1 #B1A8FF)"
    ),
    "frosted_glass": "rgba(255, 247, 251, 0.90)",
    "frosted_glass_mint": "rgba(255, 227, 241, 0.92)",
    "frosted_glass_dark": "rgba(255, 210, 230, 0.94)",
}

try:
    from .theme_manager import is_anime_theme

    if is_anime_theme():
        MD3_LIGHT_COLORS = _apply_color_overrides(MD3_LIGHT_COLORS, _ANIME_LIGHT_COLOR_OVERRIDES)
except Exception:
    # Theme is an optional layer; fall back to default colors on any import/config error.
    pass

# ============================================================================
# Material Design 3 阴影系统（浅色主题）
# ============================================================================

MD3_LIGHT_ELEVATION = {
    0: {"offset_x": 0, "offset_y": 0, "blur": 0, "spread": 0, "opacity": 0.0},
    1: {"offset_x": 0, "offset_y": 1, "blur": 2, "spread": 0, "opacity": 0.12},
    2: {"offset_x": 0, "offset_y": 2, "blur": 4, "spread": 0, "opacity": 0.14},
    3: {"offset_x": 0, "offset_y": 4, "blur": 8, "spread": 0, "opacity": 0.16},
    4: {"offset_x": 0, "offset_y": 6, "blur": 12, "spread": 0, "opacity": 0.18},
    5: {"offset_x": 0, "offset_y": 8, "blur": 16, "spread": 0, "opacity": 0.20},
}


@lru_cache(maxsize=16)
def _get_light_elevation_shadow_cached(level: int) -> str:
    shadow = MD3_LIGHT_ELEVATION[level]
    return (
        f"{shadow['offset_x']}px {shadow['offset_y']}px "
        f"{shadow['blur']}px {shadow['spread']}px rgba(0,0,0,{shadow['opacity']})"
    )


def get_light_elevation_shadow(level: int) -> str:
    """获取浅色主题阴影样式（带缓存）。"""
    if level not in MD3_LIGHT_ELEVATION:
        level = 0
    return _get_light_elevation_shadow_cached(level)


# ============================================================================
# Material Design 3 圆角半径系统（与深色主题相同）
# ============================================================================

MD3_RADIUS = {
    "extra_small": "4px",
    "small": "8px",
    "medium": "12px",
    "large": "16px",
    "extra_large": "28px",
    "full": "9999px",  # 完全圆形
}

try:
    from .theme_manager import is_anime_theme

    if is_anime_theme():
        # Anime / Kawaii: slightly rounder corners for a softer look.
        MD3_RADIUS = {
            "extra_small": "6px",
            "small": "10px",
            "medium": "14px",
            "large": "18px",
            "extra_large": "32px",
            "full": "9999px",
        }
except Exception:
    pass

# ============================================================================
# Material Design 3 动画时长系统（与深色主题相同）
# ============================================================================

MD3_DURATION = {
    # Short durations (50-200ms) - 快速微交互
    "short1": 50,  # 涟漪开始
    "short2": 100,  # 悬停状态
    "short3": 150,  # 按压反馈
    "short4": 200,  # 快速过渡
    # Medium durations (250-400ms) - 标准过渡
    "medium1": 250,  # 淡入淡出
    "medium2": 300,  # 消息气泡出现
    "medium3": 350,  # 侧边栏展开
    "medium4": 400,  # 页面切换
    # Long durations (450-600ms) - 复杂动画
    "long1": 450,  # 打字指示器
    "long2": 500,  # 滚动动画
    "long3": 550,  # 加载动画
    "long4": 600,  # 完整过渡
    # Extra long durations (700-1000ms) - 特殊效果
    "extra_long1": 700,  # 强调动画
    "extra_long2": 800,  # 欢迎动画
    "extra_long3": 900,  # 启动动画
    "extra_long4": 1000,  # 完整循环
    # Material Design 3 专用动画时长
    "ripple": 400,  # 涟漪效果
    "scale": 300,  # 缩放动画
    "slide": 350,  # 滑动动画
    "fade": 250,  # 淡入淡出
    "bounce": 500,  # 弹跳动画
    "morph": 450,  # 形变动画
    "reveal": 400,  # 揭示动画
    "collapse": 300,  # 折叠动画
    "expand": 350,  # 展开动画
}

# ============================================================================
# Material Design 3 缓动函数（Expressive Motion System）
# ============================================================================

MD3_EASING = {
    # Material Design 3 标准缓动 - 用于大多数过渡
    "standard": "cubic-bezier(0.2, 0.0, 0, 1.0)",
    # Material Design 3 强调缓动 - 用于重要元素
    "emphasized": "cubic-bezier(0.2, 0.0, 0, 1.0)",
    "emphasized_accelerate": "cubic-bezier(0.3, 0.0, 0.8, 0.15)",  # 加速离开
    "emphasized_decelerate": "cubic-bezier(0.05, 0.7, 0.1, 1.0)",  # 减速进入
    # 线性 - 用于持续动画
    "linear": "linear",
    # Material Design 3 弹性缓动 - 用于有趣的交互
    "bounce": "cubic-bezier(0.68, -0.55, 0.265, 1.55)",
    "elastic": "cubic-bezier(0.68, -0.6, 0.32, 1.6)",  # 更强的弹性
    "spring": "cubic-bezier(0.5, -0.5, 0.1, 1.5)",  # 弹簧效果
    # Material Design 3 平滑缓动 - 用于流畅过渡
    "smooth": "cubic-bezier(0.4, 0.0, 0.2, 1.0)",
    "smooth_in": "cubic-bezier(0.4, 0.0, 1.0, 1.0)",  # 平滑进入
    "smooth_out": "cubic-bezier(0.0, 0.0, 0.2, 1.0)",  # 平滑离开
    # Material Design 3 标准缓动变体
    "ease_in_out": "cubic-bezier(0.42, 0.0, 0.58, 1.0)",  # 缓入缓出
    "ease_in": "cubic-bezier(0.42, 0.0, 1.0, 1.0)",  # 缓入
    "ease_out": "cubic-bezier(0.0, 0.0, 0.58, 1.0)",  # 缓出
    # Material Design 3 特殊缓动
    "overshoot": "cubic-bezier(0.34, 1.56, 0.64, 1)",  # 超调效果
    "anticipate": "cubic-bezier(0.36, 0, 0.66, -0.56)",  # 预期效果
}

# ============================================================================
# Material Design 3 状态层透明度（State Layers）
# ============================================================================

MD3_STATE_LAYERS = {
    # 悬停状态
    "hover": 0.08,
    # 聚焦状态
    "focus": 0.12,
    # 按压状态
    "pressed": 0.12,
    # 拖拽状态
    "dragged": 0.16,
}

# ============================================================================
# Material Design 3 字体系统（与深色主题相同）
# ============================================================================

MD3_TYPOGRAPHY = {
    # Display
    "display_large": {"size": 57, "weight": 400, "line_height": 64},
    "display_medium": {"size": 45, "weight": 400, "line_height": 52},
    "display_small": {"size": 36, "weight": 400, "line_height": 44},
    # Headline
    "headline_large": {"size": 32, "weight": 400, "line_height": 40},
    "headline_medium": {"size": 28, "weight": 400, "line_height": 36},
    "headline_small": {"size": 24, "weight": 400, "line_height": 32},
    # Title
    "title_large": {"size": 22, "weight": 400, "line_height": 28},
    "title_medium": {"size": 16, "weight": 500, "line_height": 24},
    "title_small": {"size": 14, "weight": 500, "line_height": 20},
    # Body
    "body_large": {"size": 16, "weight": 400, "line_height": 24},
    "body_medium": {"size": 14, "weight": 400, "line_height": 20},
    "body_small": {"size": 12, "weight": 400, "line_height": 16},
    # Label
    "label_large": {"size": 14, "weight": 500, "line_height": 20},
    "label_medium": {"size": 12, "weight": 500, "line_height": 16},
    "label_small": {"size": 11, "weight": 500, "line_height": 16},
}


def get_typography_style(style: str) -> str:
    """获取字体样式"""
    if style not in MD3_TYPOGRAPHY:
        style = "body_medium"

    typo = MD3_TYPOGRAPHY[style]
    return (
        f"font-size: {typo['size']}px; "
        f"font-weight: {typo['weight']}; "
        f"line-height: {typo['line_height']}px;"
    )


# ============================================================================
# Material Design 3 间距系统（与深色主题相同）
# ============================================================================

MD3_SPACING = {
    "xs": "4px",
    "sm": "8px",
    "md": "12px",
    "lg": "16px",
    "xl": "24px",
    "2xl": "32px",
    "3xl": "48px",
    "4xl": "64px",
}

# ============================================================================
# 向后兼容层
# ============================================================================

# 为了兼容旧代码，提供一个主题颜色字典
LIGHT_THEME_COLORS = MD3_LIGHT_COLORS.copy()
