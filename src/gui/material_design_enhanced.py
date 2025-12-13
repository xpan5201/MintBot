"""
Material Design 3 增强设计系统 (v2.15.0)

基于 Google Material Design 3 最新规范（2024）
全方位优化：颜色、排版、间距、阴影、动画、微交互
专为 MintChat 薄荷绿主题优化
"""

from PyQt6.QtCore import QEasingCurve

# ============================================================================
# Material Design 3 增强颜色系统 - 薄荷绿主题
# ============================================================================

MD3_ENHANCED_COLORS = {
    # ========== 主色调 (Primary) - 薄荷绿系 ==========
    # 完整的色阶系统，用于不同状态和层次
    "primary_10": "#E0F2F1",  # 最浅 - 背景
    "primary_20": "#B2DFDB",  # 很浅 - 容器
    "primary_30": "#80CBC4",  # 浅 - 悬停
    "primary_40": "#4DB6AC",  # 中浅 - 激活
    "primary_50": "#26A69A",  # 标准 - 主色
    "primary_60": "#00897B",  # 中深 - 按压
    "primary_70": "#00796B",  # 深 - 强调
    "primary_80": "#00695C",  # 很深 - 文字
    "primary_90": "#004D40",  # 最深 - 高对比度

    # 主色调语义化
    "primary": "#26A69A",  # 主色
    "on_primary": "#FFFFFF",  # 主色上的文字
    "primary_container": "#B2DFDB",  # 主色容器
    "on_primary_container": "#00201C",  # 容器上的文字
    "primary_fixed": "#B2DFDB",  # 固定主色
    "primary_fixed_dim": "#80CBC4",  # 固定主色暗版
    "on_primary_fixed": "#00201C",  # 固定主色上的文字
    "on_primary_fixed_variant": "#00695C",  # 固定主色变体上的文字

    # ========== 次要色 (Secondary) - 青绿色系 ==========
    "secondary_10": "#E0F7FA",
    "secondary_20": "#B2EBF2",
    "secondary_30": "#80DEEA",
    "secondary_40": "#4DD0E1",
    "secondary_50": "#26C6DA",
    "secondary_60": "#00BCD4",
    "secondary_70": "#00ACC1",
    "secondary_80": "#0097A7",
    "secondary_90": "#00838F",

    "secondary": "#26C6DA",
    "on_secondary": "#FFFFFF",
    "secondary_container": "#B2EBF2",
    "on_secondary_container": "#001F24",

    # ========== 第三色 (Tertiary) - 天蓝色系 ==========
    "tertiary_10": "#E1F5FE",
    "tertiary_20": "#B3E5FC",
    "tertiary_30": "#81D4FA",
    "tertiary_40": "#4FC3F7",
    "tertiary_50": "#29B6F6",
    "tertiary_60": "#03A9F4",
    "tertiary_70": "#039BE5",
    "tertiary_80": "#0288D1",
    "tertiary_90": "#0277BD",

    "tertiary": "#03A9F4",
    "on_tertiary": "#FFFFFF",
    "tertiary_container": "#B3E5FC",
    "on_tertiary_container": "#001E2F",

    # ========== 错误色 (Error) ==========
    "error_10": "#FFEBEE",
    "error_20": "#FFCDD2",
    "error_30": "#EF9A9A",
    "error_40": "#E57373",
    "error_50": "#EF5350",
    "error_60": "#F44336",
    "error_70": "#E53935",
    "error_80": "#D32F2F",
    "error_90": "#C62828",

    "error": "#EF5350",
    "on_error": "#FFFFFF",
    "error_container": "#FFCDD2",
    "on_error_container": "#C62828",

    # ========== 中性色 (Neutral) - 薄荷绿调 ==========
    "neutral_10": "#F8FFFE",  # 极淡薄荷绿
    "neutral_20": "#F0FBF8",  # 很淡薄荷绿
    "neutral_30": "#E8F8F5",  # 淡薄荷绿
    "neutral_40": "#D8F3ED",  # 薄荷绿
    "neutral_50": "#C8F3E8",  # 明显薄荷绿
    "neutral_60": "#A8E6CF",  # 中薄荷绿
    "neutral_70": "#80CBC4",  # 深薄荷绿
    "neutral_80": "#4DB6AC",  # 很深薄荷绿
    "neutral_90": "#26A69A",  # 最深薄荷绿

    # ========== 表面色 (Surface) ==========
    "surface_dim": "#E8F8F5",  # 暗表面
    "surface": "#F8FFFE",  # 标准表面
    "surface_bright": "#FFFFFF",  # 亮表面
    "surface_container_lowest": "#FFFFFF",  # 最低容器
    "surface_container_low": "#F0FBF8",  # 低容器
    "surface_container": "#E8F8F5",  # 标准容器
    "surface_container_high": "#D8F3ED",  # 高容器
    "surface_container_highest": "#C8F3E8",  # 最高容器
    "surface_variant": "#D8F3ED",  # 表面变体

    "on_surface": "#1A1C1E",  # 表面上的文字
    "on_surface_variant": "#42474E",  # 表面变体上的文字

    # ========== 背景色 (Background) ==========
    "background": "#F0FBF8",  # 背景
    "on_background": "#1A1C1E",  # 背景上的文字

    # ========== 轮廓色 (Outline) ==========
    "outline": "#C8F3E8",  # 轮廓
    "outline_variant": "#D8F3ED",  # 轮廓变体

    # ========== 阴影和遮罩 ==========
    "shadow": "#000000",  # 阴影
    "scrim": "#000000",  # 遮罩

    # ========== 反色 (Inverse) ==========
    "inverse_surface": "#2D3132",  # 反色表面
    "inverse_on_surface": "#EFF1F1",  # 反色表面上的文字
    "inverse_primary": "#80CBC4",  # 反色主色

    # ========== 状态色 (State) ==========
    "success": "#66BB6A",  # 成功
    "on_success": "#FFFFFF",
    "success_container": "#C8E6C9",
    "on_success_container": "#1B5E20",

    "warning": "#FFA726",  # 警告
    "on_warning": "#FFFFFF",
    "warning_container": "#FFE0B2",
    "on_warning_container": "#E65100",

    "info": "#29B6F6",  # 信息
    "on_info": "#FFFFFF",
    "info_container": "#B3E5FC",
    "on_info_container": "#01579B",

    # ========== 渐变色 (Gradients) ==========
    "gradient_primary": "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #80CBC4, stop:1 #26A69A)",
    "gradient_primary_vertical": "qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #80CBC4, stop:1 #26A69A)",
    "gradient_secondary": "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #80DEEA, stop:1 #26C6DA)",
    "gradient_tertiary": "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #81D4FA, stop:1 #03A9F4)",
    "gradient_surface": "qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #F0FBF8, stop:1 #C8F3E8)",
    "gradient_mint_soft": "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #E0F2F1, stop:1 #B2DFDB)",
    "gradient_mint_radial": "qradialgradient(cx:0.5, cy:0.5, radius:1, fx:0.5, fy:0.5, stop:0 #B2DFDB, stop:1 #80CBC4)",

    # ========== 毛玻璃效果 (Frosted Glass) ==========
    "frosted_glass_light": "rgba(248, 255, 254, 0.85)",
    "frosted_glass": "rgba(240, 251, 248, 0.90)",
    "frosted_glass_medium": "rgba(232, 248, 245, 0.92)",
    "frosted_glass_strong": "rgba(200, 243, 232, 0.95)",
}

# ============================================================================
# Material Design 3 增强排版系统
# ============================================================================

MD3_ENHANCED_TYPOGRAPHY = {
    # Display - 大标题
    "display_large": {
        "size": 57, "weight": 400, "line_height": 64,
        "letter_spacing": -0.25, "font": "Segoe UI"
    },
    "display_medium": {
        "size": 45, "weight": 400, "line_height": 52,
        "letter_spacing": 0, "font": "Segoe UI"
    },
    "display_small": {
        "size": 36, "weight": 400, "line_height": 44,
        "letter_spacing": 0, "font": "Segoe UI"
    },

    # Headline - 标题
    "headline_large": {
        "size": 32, "weight": 400, "line_height": 40,
        "letter_spacing": 0, "font": "Segoe UI"
    },
    "headline_medium": {
        "size": 28, "weight": 400, "line_height": 36,
        "letter_spacing": 0, "font": "Segoe UI"
    },
    "headline_small": {
        "size": 24, "weight": 400, "line_height": 32,
        "letter_spacing": 0, "font": "Segoe UI"
    },

    # Title - 小标题
    "title_large": {
        "size": 22, "weight": 500, "line_height": 28,
        "letter_spacing": 0, "font": "Segoe UI"
    },
    "title_medium": {
        "size": 16, "weight": 500, "line_height": 24,
        "letter_spacing": 0.15, "font": "Segoe UI"
    },
    "title_small": {
        "size": 14, "weight": 500, "line_height": 20,
        "letter_spacing": 0.1, "font": "Segoe UI"
    },

    # Body - 正文
    "body_large": {
        "size": 16, "weight": 400, "line_height": 24,
        "letter_spacing": 0.5, "font": "Segoe UI"
    },
    "body_medium": {
        "size": 14, "weight": 400, "line_height": 20,
        "letter_spacing": 0.25, "font": "Segoe UI"
    },
    "body_small": {
        "size": 12, "weight": 400, "line_height": 16,
        "letter_spacing": 0.4, "font": "Segoe UI"
    },

    # Label - 标签
    "label_large": {
        "size": 14, "weight": 500, "line_height": 20,
        "letter_spacing": 0.1, "font": "Segoe UI"
    },
    "label_medium": {
        "size": 12, "weight": 500, "line_height": 16,
        "letter_spacing": 0.5, "font": "Segoe UI"
    },
    "label_small": {
        "size": 11, "weight": 500, "line_height": 16,
        "letter_spacing": 0.5, "font": "Segoe UI"
    },
}


def get_typography_css(variant: str) -> str:
    """获取排版CSS样式"""
    if variant not in MD3_ENHANCED_TYPOGRAPHY:
        variant = "body_medium"

    typo = MD3_ENHANCED_TYPOGRAPHY[variant]
    return f"""
        font-family: '{typo['font']}', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        font-size: {typo['size']}px;
        font-weight: {typo['weight']};
        line-height: {typo['line_height']}px;
        letter-spacing: {typo['letter_spacing']}px;
    """


# ============================================================================
# Material Design 3 增强间距系统
# ============================================================================

MD3_ENHANCED_SPACING = {
    # 基础间距 (4px 基准)
    "0": "0px",
    "1": "4px",   # 0.25rem
    "2": "8px",   # 0.5rem
    "3": "12px",  # 0.75rem
    "4": "16px",  # 1rem
    "5": "20px",  # 1.25rem
    "6": "24px",  # 1.5rem
    "8": "32px",  # 2rem
    "10": "40px", # 2.5rem
    "12": "48px", # 3rem
    "16": "64px", # 4rem
    "20": "80px", # 5rem
    "24": "96px", # 6rem

    # 语义化间距
    "xs": "4px",
    "sm": "8px",
    "md": "16px",
    "lg": "24px",
    "xl": "32px",
    "2xl": "48px",
    "3xl": "64px",
    "4xl": "96px",
}


# ============================================================================
# Material Design 3 增强圆角系统
# ============================================================================

MD3_ENHANCED_RADIUS = {
    "none": "0px",
    "xs": "2px",
    "sm": "4px",
    "md": "8px",
    "lg": "12px",
    "xl": "16px",
    "2xl": "20px",
    "3xl": "28px",
    "full": "9999px",

    # 语义化圆角
    "extra_small": "4px",
    "small": "8px",
    "medium": "12px",
    "large": "16px",
    "extra_large": "28px",
    "circle": "9999px",
}


# ============================================================================
# Material Design 3 增强阴影系统
# ============================================================================

MD3_ENHANCED_ELEVATION = {
    # Level 0: 无阴影
    0: {
        "offset_x": 0, "offset_y": 0,
        "blur": 0, "spread": 0,
        "color": "rgba(0, 0, 0, 0)",
        "opacity": 0.0
    },
    # Level 1: 1dp elevation - 卡片、按钮
    1: {
        "offset_x": 0, "offset_y": 1,
        "blur": 3, "spread": 0,
        "color": "rgba(0, 0, 0, 0.12)",
        "opacity": 0.12
    },
    # Level 2: 3dp elevation - 悬停卡片
    2: {
        "offset_x": 0, "offset_y": 2,
        "blur": 6, "spread": 0,
        "color": "rgba(0, 0, 0, 0.14)",
        "opacity": 0.14
    },
    # Level 3: 6dp elevation - 对话框
    3: {
        "offset_x": 0, "offset_y": 4,
        "blur": 12, "spread": 0,
        "color": "rgba(0, 0, 0, 0.16)",
        "opacity": 0.16
    },
    # Level 4: 8dp elevation - 导航抽屉
    4: {
        "offset_x": 0, "offset_y": 6,
        "blur": 16, "spread": 0,
        "color": "rgba(0, 0, 0, 0.18)",
        "opacity": 0.18
    },
    # Level 5: 12dp elevation - 模态对话框
    5: {
        "offset_x": 0, "offset_y": 8,
        "blur": 24, "spread": 0,
        "color": "rgba(0, 0, 0, 0.20)",
        "opacity": 0.20
    },
}


def get_elevation_shadow(level: int) -> str:
    """获取阴影CSS样式"""
    if level not in MD3_ENHANCED_ELEVATION:
        level = 0

    shadow = MD3_ENHANCED_ELEVATION[level]
    if level == 0:
        return "none"

    return f"{shadow['offset_x']}px {shadow['offset_y']}px {shadow['blur']}px {shadow['spread']}px {shadow['color']}"


# ============================================================================
# Material Design 3 增强动画时长系统
# ============================================================================

MD3_ENHANCED_DURATION = {
    # Short durations (50-200ms) - 快速微交互
    "short1": 50,   # 涟漪开始
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
    "extra_long1": 700,   # 强调动画
    "extra_long2": 800,   # 欢迎动画
    "extra_long3": 900,   # 启动动画
    "extra_long4": 1000,  # 完整循环

    # 语义化动画时长
    "instant": 0,
    "fast": 100,
    "normal": 300,
    "slow": 500,
    "slower": 700,
    "slowest": 1000,
}


# ============================================================================
# Material Design 3 增强缓动函数系统
# ============================================================================

MD3_ENHANCED_EASING = {
    # Material Design 3 标准缓动
    "standard": QEasingCurve.Type.InOutCubic,
    "standard_accelerate": QEasingCurve.Type.InCubic,
    "standard_decelerate": QEasingCurve.Type.OutCubic,

    # Material Design 3 强调缓动
    "emphasized": QEasingCurve.Type.OutCubic,
    "emphasized_accelerate": QEasingCurve.Type.InQuart,
    "emphasized_decelerate": QEasingCurve.Type.OutQuart,

    # 弹性缓动
    "bounce": QEasingCurve.Type.OutBounce,
    "elastic": QEasingCurve.Type.OutElastic,
    "spring": QEasingCurve.Type.OutBack,

    # 平滑缓动
    "smooth": QEasingCurve.Type.InOutQuad,
    "smooth_in": QEasingCurve.Type.InQuad,
    "smooth_out": QEasingCurve.Type.OutQuad,

    # 线性
    "linear": QEasingCurve.Type.Linear,

    # 特殊缓动
    "overshoot": QEasingCurve.Type.OutBack,
    "anticipate": QEasingCurve.Type.InBack,
}


# CSS 缓动函数字符串
MD3_ENHANCED_EASING_CSS = {
    "standard": "cubic-bezier(0.2, 0.0, 0, 1.0)",
    "standard_accelerate": "cubic-bezier(0.3, 0.0, 1, 1)",
    "standard_decelerate": "cubic-bezier(0, 0.0, 0, 1)",
    "emphasized": "cubic-bezier(0.2, 0.0, 0, 1.0)",
    "emphasized_accelerate": "cubic-bezier(0.3, 0.0, 0.8, 0.15)",
    "emphasized_decelerate": "cubic-bezier(0.05, 0.7, 0.1, 1.0)",
    "bounce": "cubic-bezier(0.68, -0.55, 0.265, 1.55)",
    "elastic": "cubic-bezier(0.68, -0.6, 0.32, 1.6)",
    "spring": "cubic-bezier(0.5, -0.5, 0.1, 1.5)",
    "smooth": "cubic-bezier(0.4, 0.0, 0.2, 1.0)",
    "smooth_in": "cubic-bezier(0.4, 0.0, 1.0, 1.0)",
    "smooth_out": "cubic-bezier(0.0, 0.0, 0.2, 1.0)",
    "linear": "linear",
    "overshoot": "cubic-bezier(0.34, 1.56, 0.64, 1)",
    "anticipate": "cubic-bezier(0.36, 0, 0.66, -0.56)",
}


# ============================================================================
# Material Design 3 状态层透明度
# ============================================================================

MD3_ENHANCED_STATE_LAYERS = {
    "hover": 0.08,      # 悬停
    "focus": 0.12,      # 聚焦
    "pressed": 0.12,    # 按压
    "dragged": 0.16,    # 拖拽
    "selected": 0.12,   # 选中
    "activated": 0.12,  # 激活
    "disabled": 0.38,   # 禁用
}


# ============================================================================
# Material Design 3 图标尺寸
# ============================================================================

MD3_ENHANCED_ICON_SIZES = {
    "xs": 16,
    "sm": 20,
    "md": 24,
    "lg": 32,
    "xl": 48,
    "2xl": 64,
}


# ============================================================================
# Material Design 3 Z-Index 层级
# ============================================================================

MD3_ENHANCED_Z_INDEX = {
    "base": 0,
    "dropdown": 1000,
    "sticky": 1020,
    "fixed": 1030,
    "modal_backdrop": 1040,
    "modal": 1050,
    "popover": 1060,
    "tooltip": 1070,
    "notification": 1080,
}
