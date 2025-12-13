"""
MintChat GUI - Material Design 3 系统

遵循 Google Material Design 3 规范的设计系统
包含颜色、阴影、动画等核心设计元素
"""

# Material Design 3 颜色系统 (Dark Theme)
MD3_COLORS = {
    # 主色调 (Primary) - 紫色系
    "primary": "#D0BCFF",
    "on_primary": "#381E72",
    "primary_container": "#4F378B",
    "on_primary_container": "#EADDFF",

    # 次要色 (Secondary) - 淡紫色系
    "secondary": "#CCC2DC",
    "on_secondary": "#332D41",
    "secondary_container": "#4A4458",
    "on_secondary_container": "#E8DEF8",

    # 第三色 (Tertiary) - 粉色系
    "tertiary": "#EFB8C8",
    "on_tertiary": "#492532",
    "tertiary_container": "#633B48",
    "on_tertiary_container": "#FFD8E4",

    # 背景色 (Surface)
    "surface": "#1C1B1F",
    "on_surface": "#E6E1E5",
    "surface_variant": "#49454F",
    "on_surface_variant": "#CAC4D0",

    # 容器色 (Surface Containers)
    "surface_container_lowest": "#0F0D13",
    "surface_container_low": "#1D1B20",
    "surface_container": "#211F26",
    "surface_container_high": "#2B2930",
    "surface_container_highest": "#36343B",

    # 轮廓色 (Outline)
    "outline": "#938F99",
    "outline_variant": "#49454F",

    # 错误色 (Error)
    "error": "#F2B8B5",
    "on_error": "#601410",
    "error_container": "#8C1D18",
    "on_error_container": "#F9DEDC",

    # 背景和阴影
    "background": "#1C1B1F",
    "on_background": "#E6E1E5",
    "shadow": "#000000",
    "scrim": "#000000",

    # 反色 (Inverse)
    "inverse_surface": "#E6E1E5",
    "inverse_on_surface": "#313033",
    "inverse_primary": "#6750A4",
}


# Material Design 3 阴影层级
# 参考: https://m3.material.io/styles/elevation/overview
MD3_ELEVATION = {
    # Level 0: 无阴影
    0: {
        "offset_y": 0,
        "blur_radius": 0,
        "spread_radius": 0,
        "opacity": 0.0,
    },
    # Level 1: 1dp elevation
    1: {
        "offset_y": 1,
        "blur_radius": 3,
        "spread_radius": 1,
        "opacity": 0.15,
    },
    # Level 2: 3dp elevation
    2: {
        "offset_y": 2,
        "blur_radius": 6,
        "spread_radius": 2,
        "opacity": 0.18,
    },
    # Level 3: 6dp elevation
    3: {
        "offset_y": 4,
        "blur_radius": 12,
        "spread_radius": 3,
        "opacity": 0.20,
    },
    # Level 4: 8dp elevation
    4: {
        "offset_y": 6,
        "blur_radius": 16,
        "spread_radius": 4,
        "opacity": 0.22,
    },
    # Level 5: 12dp elevation
    5: {
        "offset_y": 8,
        "blur_radius": 24,
        "spread_radius": 5,
        "opacity": 0.24,
    },
}


def get_elevation_shadow(level: int = 1) -> str:
    """
    获取指定层级的阴影样式

    Args:
        level: 阴影层级 (0-5)

    Returns:
        CSS box-shadow 字符串
    """
    if level not in MD3_ELEVATION:
        level = 1

    shadow = MD3_ELEVATION[level]
    if level == 0:
        return "none"

    # 计算阴影颜色（带透明度）
    opacity_hex = hex(int(shadow["opacity"] * 255))[2:].zfill(2)
    shadow_color = f"{MD3_COLORS['shadow']}{opacity_hex}"

    return (
        f"{shadow['offset_y']}px "
        f"{shadow['blur_radius']}px "
        f"{shadow['spread_radius']}px "
        f"{shadow_color}"
    )


# Material Design 3 圆角半径
MD3_RADIUS = {
    "none": "0px",
    "extra_small": "4px",
    "small": "8px",
    "medium": "12px",
    "large": "16px",
    "extra_large": "28px",
    "full": "9999px",
}


# Material Design 3 动画时长
MD3_DURATION = {
    "short1": 50,   # 50ms
    "short2": 100,  # 100ms
    "short3": 150,  # 150ms
    "short4": 200,  # 200ms
    "medium1": 250, # 250ms
    "medium2": 300, # 300ms
    "medium3": 350, # 350ms
    "medium4": 400, # 400ms
    "long1": 450,   # 450ms
    "long2": 500,   # 500ms
    "long3": 550,   # 550ms
    "long4": 600,   # 600ms
    "extra_long1": 700,  # 700ms
    "extra_long2": 800,  # 800ms
    "extra_long3": 900,  # 900ms
    "extra_long4": 1000, # 1000ms
}


# Material Design 3 缓动函数
MD3_EASING = {
    # 标准缓动
    "standard": "cubic-bezier(0.2, 0.0, 0, 1.0)",
    "standard_accelerate": "cubic-bezier(0.3, 0.0, 1, 1)",
    "standard_decelerate": "cubic-bezier(0, 0.0, 0, 1)",

    # 强调缓动
    "emphasized": "cubic-bezier(0.2, 0.0, 0, 1.0)",
    "emphasized_accelerate": "cubic-bezier(0.3, 0.0, 0.8, 0.15)",
    "emphasized_decelerate": "cubic-bezier(0.05, 0.7, 0.1, 1.0)",

    # 线性
    "linear": "linear",
}


# Material Design 3 字体
MD3_TYPOGRAPHY = {
    # Display
    "display_large": {"size": "57px", "weight": "400", "line_height": "64px"},
    "display_medium": {"size": "45px", "weight": "400", "line_height": "52px"},
    "display_small": {"size": "36px", "weight": "400", "line_height": "44px"},

    # Headline
    "headline_large": {"size": "32px", "weight": "400", "line_height": "40px"},
    "headline_medium": {"size": "28px", "weight": "400", "line_height": "36px"},
    "headline_small": {"size": "24px", "weight": "400", "line_height": "32px"},

    # Title
    "title_large": {"size": "22px", "weight": "400", "line_height": "28px"},
    "title_medium": {"size": "16px", "weight": "500", "line_height": "24px"},
    "title_small": {"size": "14px", "weight": "500", "line_height": "20px"},

    # Body
    "body_large": {"size": "16px", "weight": "400", "line_height": "24px"},
    "body_medium": {"size": "14px", "weight": "400", "line_height": "20px"},
    "body_small": {"size": "12px", "weight": "400", "line_height": "16px"},

    # Label
    "label_large": {"size": "14px", "weight": "500", "line_height": "20px"},
    "label_medium": {"size": "12px", "weight": "500", "line_height": "16px"},
    "label_small": {"size": "11px", "weight": "500", "line_height": "16px"},
}


def get_typography_style(variant: str) -> str:
    """
    获取指定字体样式的 CSS

    Args:
        variant: 字体变体名称

    Returns:
        CSS 字体样式字符串
    """
    if variant not in MD3_TYPOGRAPHY:
        variant = "body_medium"

    typo = MD3_TYPOGRAPHY[variant]
    return (
        f"font-size: {typo['size']}; "
        f"font-weight: {typo['weight']}; "
        f"line-height: {typo['line_height']};"
    )


# Material Design 3 间距系统
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


# 导出常用颜色（兼容旧代码）
THEME_COLORS = {
    "primary": MD3_COLORS["primary"],
    "primary_container": MD3_COLORS["primary_container"],
    "secondary": MD3_COLORS["secondary"],
    "surface": MD3_COLORS["surface"],
    "surface_variant": MD3_COLORS["surface_variant"],
    "surface_container": MD3_COLORS["surface_container"],
    "surface_container_high": MD3_COLORS["surface_container_high"],
    "surface_container_highest": MD3_COLORS["surface_container_highest"],
    "on_surface": MD3_COLORS["on_surface"],
    "on_surface_variant": MD3_COLORS["on_surface_variant"],
    "outline": MD3_COLORS["outline"],
    "outline_variant": MD3_COLORS["outline_variant"],
    "error": MD3_COLORS["error"],
    "background": MD3_COLORS["background"],
    "on_background": MD3_COLORS["on_background"],

    # 兼容旧代码
    "bg_dark": MD3_COLORS["surface"],
    "bg_darker": MD3_COLORS["surface_container_lowest"],
    "bg_light": MD3_COLORS["surface_container_high"],
    "text_primary": MD3_COLORS["on_surface"],
    "text_secondary": MD3_COLORS["on_surface_variant"],
    "border": MD3_COLORS["outline_variant"],
    "bubble_user": MD3_COLORS["primary_container"],
    "bubble_ai": MD3_COLORS["surface_container_high"],
}
