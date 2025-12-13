"""
自动修复未使用的导入 v2.30.4

基于flake8 F401错误自动移除未使用的导入
"""

import re
from pathlib import Path
from typing import Dict, List, Set

PROJECT_ROOT = Path(__file__).parent.parent

# 从flake8输出中提取的未使用导入（按文件分组）
UNUSED_IMPORTS = {
    'src/gui/auth_manager.py': [
        'QGraphicsDropShadowEffect',
    ],
    'src/gui/auth_window.py': [
        'QVBoxLayout', 'QHBoxLayout', 'QCheckBox', 'QStackedWidget', 'QApplication',
        'QEasingCurve', 'QSize', 'QRect', 'QPoint', 'QRectF',
        'QFont', 'QPainter', 'QPainterPath', 'QMouseEvent', 'QCursor', 'QBitmap', 'QPen', 'QBrush', 'QRegion',
        'get_elevation_shadow', 'get_typography_css', 'MATERIAL_ICONS',
    ],
    'src/gui/chat_window.py': [
        'QFrame', 'QSizePolicy', 'QApplication', 'QIcon', 'QFont', 'QTextCursor', 'Path', 'sys',
    ],
    'src/gui/contacts_panel.py': [
        'QTextEdit', 'QScrollArea', 'QGraphicsDropShadowEffect', 'MD3_ENHANCED_STATE_LAYERS',
    ],
    'src/gui/emoji_picker.py': [
        'QGraphicsOpacityEffect', 'QEasingCurve', 'QTimer', 'QParallelAnimationGroup', 'QSequentialAnimationGroup',
        'QFont', 'List', 'json',
        'MD3_LIGHT_COLORS', 'MD3_RADIUS', 'MD3_DURATION', 'get_elevation_shadow',
    ],
    'src/gui/enhanced_animations.py': [
        'QGraphicsDropShadowEffect', 'QSequentialAnimationGroup', 'QTimer', 'QColor',
        'MD3_EASING', 'MD3_STATE_LAYERS', 'pi', 'cos', 'sin',
    ],
    'src/gui/enhanced_input.py': [
        'QGraphicsOpacityEffect', 'QGraphicsDropShadowEffect', 'QTimer', 'QColor', 'QTextCursor',
        'get_light_elevation_shadow',
    ],
    'src/gui/frameless_window.py': [
        'QPropertyAnimation', 'QEasingCurve', 'QCursor', 'MD3_DURATION', 'get_elevation_shadow',
    ],
    'src/gui/interactive_widgets.py': [
        'QGraphicsOpacityEffect', 'QPen', 'MD3_LIGHT_COLORS', 'MD3_RADIUS',
    ],
    'src/gui/light_chat_window.py': [
        'QSizePolicy', 'QRunnable', 'pyqtSlot', 'QFont',
        'MD3_LIGHT_COLORS', 'MD3_RADIUS',
        'MD3_ENHANCED_SPACING', 'MD3_ENHANCED_RADIUS', 'MD3_ENHANCED_DURATION', 'MD3_ENHANCED_EASING', 'MD3_ENHANCED_ELEVATION', 'get_elevation_shadow',
        'EnhancedInputArea', 'EmptyState',
        'debounce', 'batch_updates', 'gui_monitor_performance',
        'QBrush', 'QRegion', 'AuthService',
    ],
    'src/gui/light_frameless_window.py': [
        'QPainter', 'QPainterPath', 'get_light_elevation_shadow',
    ],
    'src/gui/light_message_bubble.py': [
        'QSequentialAnimationGroup', 'QFont',
        'MD3_LIGHT_COLORS', 'MD3_RADIUS', 'MD3_DURATION', 'get_light_elevation_shadow',
        'MD3_ENHANCED_TYPOGRAPHY', 'MD3_ENHANCED_RADIUS', 'get_elevation_shadow',
        'AnimationMixin',
    ],
    'src/gui/light_sidebar.py': [
        'QScrollArea', 'QGraphicsDropShadowEffect', 'QSize', 'QParallelAnimationGroup',
        'QIcon', 'QPixmap', 'QPen', 'get_light_elevation_shadow',
        'MD3_ENHANCED_SPACING', 'get_elevation_shadow',
    ],
    'src/gui/loading_states.py': [
        'QRect', 'MD3_RADIUS',
        'MD3_ENHANCED_COLORS', 'MD3_ENHANCED_SPACING', 'MD3_ENHANCED_RADIUS', 'get_typography_css',
    ],
    'src/gui/message_bubble.py': [
        'QSize', 'QFont',
    ],
    'src/gui/modern_chat_window.py': [
        'QFont', 'MD3_SPACING', 'MD3_DURATION',
    ],
    'src/gui/notifications.py': [
        'QVBoxLayout', 'QPoint', 'QPainter', 'QColor', 'QPainterPath',
    ],
    'src/gui/settings_panel.py': [
        'QTimer', 'QEasingCurve', 'MD3_RADIUS',
    ],
}


def remove_unused_import(file_path: Path, unused_names: List[str]) -> int:
    """
    从文件中移除未使用的导入
    
    Returns:
        移除的导入数量
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    removed_count = 0
    new_lines = []
    skip_next = False
    
    for i, line in enumerate(lines):
        if skip_next:
            skip_next = False
            continue
            
        # 检查是否是导入行
        if line.strip().startswith(('import ', 'from ')):
            # 检查是否包含未使用的导入
            should_remove = False
            for unused_name in unused_names:
                # 匹配导入语句中的名称
                if re.search(rf'\b{re.escape(unused_name)}\b', line):
                    should_remove = True
                    removed_count += 1
                    break
            
            if should_remove:
                # 如果是多行导入的一部分，需要特殊处理
                if '(' in line and ')' not in line:
                    # 多行导入的开始，跳过直到找到结束
                    while i < len(lines) and ')' not in lines[i]:
                        i += 1
                    continue
                else:
                    continue
        
        new_lines.append(line)
    
    # 写回文件
    with open(file_path, 'w', encoding='utf-8') as f:
        f.writelines(new_lines)
    
    return removed_count


def main():
    """主函数"""
    print("=" * 70)
    print("  自动修复未使用的导入 v2.30.4")
    print("=" * 70)
    print()
    
    total_removed = 0
    files_fixed = 0
    
    for file_rel_path, unused_names in UNUSED_IMPORTS.items():
        file_path = PROJECT_ROOT / file_rel_path
        
        if not file_path.exists():
            print(f"⚠️  文件不存在: {file_rel_path}")
            continue
        
        print(f"📝 处理: {file_rel_path}")
        print(f"   未使用导入: {len(unused_names)} 个")
        
        removed = remove_unused_import(file_path, unused_names)
        
        if removed > 0:
            total_removed += removed
            files_fixed += 1
            print(f"   ✅ 已移除: {removed} 个导入")
        else:
            print(f"   ℹ️  无需修改")
        print()
    
    print("=" * 70)
    print(f"✅ 完成！")
    print(f"   修复文件: {files_fixed} 个")
    print(f"   移除导入: {total_removed} 个")
    print("=" * 70)


if __name__ == '__main__':
    main()

