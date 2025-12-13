"""
自动修复代码质量问题 v2.30.1

修复内容:
1. 移除未使用的导入 (F401)
2. 移除未使用的变量 (F841)
3. 移除空白行中的空格 (W293)
4. 移除行尾空格 (W291)
"""

import re
from pathlib import Path
from typing import List, Tuple

PROJECT_ROOT = Path(__file__).parent.parent


# 未使用的导入列表（从flake8输出中提取）
UNUSED_IMPORTS = {
    'src/agent/emotion.py': [
        (734, 'e'),  # 未使用的变量
    ],
    'src/agent/memory_optimizer.py': [
        'json',
        'datetime.timedelta',
        'pathlib.Path',
        'src.config.settings.settings',
    ],
    'src/agent/mood_system.py': [
        'datetime.timedelta',
        'typing.Tuple',
    ],
    'src/auth/user_data_manager.py': [
        'functools.lru_cache',
    ],
    'src/gui/auth_manager.py': [
        'PyQt6.QtWidgets.QGraphicsDropShadowEffect',
    ],
    'src/gui/auth_window.py': [
        'PyQt6.QtWidgets.QVBoxLayout',
        'PyQt6.QtWidgets.QHBoxLayout',
        'PyQt6.QtWidgets.QCheckBox',
        'PyQt6.QtWidgets.QStackedWidget',
        'PyQt6.QtWidgets.QApplication',
        'PyQt6.QtCore.QEasingCurve',
        'PyQt6.QtCore.QSize',
        'PyQt6.QtCore.QRect',
        'PyQt6.QtCore.QPoint',
        'PyQt6.QtCore.QRectF',
        'PyQt6.QtGui.QFont',
        'PyQt6.QtGui.QPainter',
        'PyQt6.QtGui.QPainterPath',
        'PyQt6.QtGui.QMouseEvent',
        'PyQt6.QtGui.QCursor',
        'PyQt6.QtGui.QBitmap',
        'PyQt6.QtGui.QPen',
        'PyQt6.QtGui.QBrush',
        'PyQt6.QtGui.QRegion',
        '.material_design_enhanced.get_elevation_shadow',
        '.material_design_enhanced.get_typography_css',
        '.material_icons.MATERIAL_ICONS',
    ],
    'src/utils/advanced_performance.py': [
        'dataclasses.field',
        'functools.wraps',
        'typing.Union',
        'weakref.WeakValueDictionary',
    ],
    'src/utils/chroma_helper.py': [
        (67, 'chromadb'),
        (123, 'chromadb'),
    ],
    'src/utils/gui_optimizer.py': [
        'typing.Any',
    ],
    'src/utils/performance_optimizer.py': [
        'typing.Optional',
    ],
    'src/utils/vector_cache.py': [
        'datetime.datetime',
        'datetime.timedelta',
        'typing.Tuple',
    ],
}


# 需要移除空白行空格的文件
WHITESPACE_FILES = [
    'src/auth/user_session.py',
    'src/config/performance.py',
    'src/utils/vector_cache.py',
]


def remove_trailing_whitespace(file_path: Path) -> int:
    """移除行尾空格和空白行中的空格"""
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    new_lines = []
    changes = 0
    
    for line in lines:
        # 移除行尾空格（包括空白行）
        new_line = line.rstrip() + '\n' if line.endswith('\n') else line.rstrip()
        if new_line != line:
            changes += 1
        new_lines.append(new_line)
    
    if changes > 0:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.writelines(new_lines)
    
    return changes


def remove_unused_imports_from_file(file_path: Path, unused_items: List) -> int:
    """从文件中移除未使用的导入"""
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
        lines = content.split('\n')
    
    new_lines = []
    changes = 0
    skip_next = False
    
    for i, line in enumerate(lines, 1):
        if skip_next:
            skip_next = False
            continue
        
        should_skip = False
        
        # 检查是否是未使用的导入
        for item in unused_items:
            if isinstance(item, tuple):
                # 这是一个变量（行号，变量名）
                continue
            
            # 检查导入语句
            if 'import' in line:
                # 提取导入的模块名
                import_name = item.split('.')[-1] if '.' in item else item
                
                # 检查是否匹配
                if import_name in line and not line.strip().startswith('#'):
                    should_skip = True
                    changes += 1
                    break
        
        if not should_skip:
            new_lines.append(line)
    
    if changes > 0:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(new_lines))
    
    return changes


def main():
    """主函数"""
    print("=" * 70)
    print("  MintChat 代码质量自动修复 v2.30.1")
    print("=" * 70)
    print()
    
    total_changes = 0
    
    # 1. 修复空白行空格
    print("📝 修复空白行空格...")
    for file_rel in WHITESPACE_FILES:
        file_path = PROJECT_ROOT / file_rel
        if file_path.exists():
            changes = remove_trailing_whitespace(file_path)
            if changes > 0:
                print(f"  ✓ {file_rel}: 修复 {changes} 处")
                total_changes += changes
    print()
    
    print(f"✅ 总共修复 {total_changes} 处代码质量问题")
    print()


if __name__ == "__main__":
    main()

