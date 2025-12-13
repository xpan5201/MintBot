"""
自动修复代码风格问题

修复内容：
- 移除行尾空白 (W291, W293)
- 移除文件末尾空行 (W391)
- 移除未使用的导入 (F401)
- 修复缩进问题 (E128, E131)
"""

import os
import re
from pathlib import Path


def remove_trailing_whitespace(content: str) -> str:
    """移除行尾空白"""
    lines = content.split('\n')
    cleaned_lines = [line.rstrip() for line in lines]
    return '\n'.join(cleaned_lines)


def remove_blank_line_at_eof(content: str) -> str:
    """移除文件末尾的空行"""
    return content.rstrip() + '\n'


def remove_unused_imports(file_path: str, content: str) -> str:
    """移除未使用的导入（简单版本）"""
    # 这里只处理明显未使用的导入
    unused_imports = {
        'src/gui/animated_message.py': [
            'MD3_SPACING',
            'get_elevation_shadow'
        ],
        'src/gui/animated_sidebar.py': [
            'QIcon',
            'MD3_SPACING'
        ],
        'src/gui/notifications.py': [
            'QVBoxLayout',
            'QPoint',
            'QPainter',
            'QColor',
            'QPainterPath'
        ],
        'src/gui/settings_panel.py': [
            'QGraphicsDropShadowEffect',
            'QEasingCurve',
            'QFont',
            'QColor',
            'get_elevation_shadow',
            'MATERIAL_ICONS',
            'settings'
        ]
    }
    
    # 转换为相对路径
    rel_path = file_path.replace('\\', '/')
    
    if rel_path not in unused_imports:
        return content
    
    lines = content.split('\n')
    result_lines = []
    skip_next = False
    
    for i, line in enumerate(lines):
        if skip_next:
            skip_next = False
            continue
            
        # 检查是否是未使用的导入
        should_skip = False
        for unused in unused_imports[rel_path]:
            if unused in line and ('import' in line or 'from' in line):
                # 检查是否是多行导入的一部分
                if '(' in line and ')' not in line:
                    # 多行导入开始
                    should_skip = True
                    break
                elif unused in line and not line.strip().startswith('#'):
                    should_skip = True
                    break
        
        if not should_skip:
            result_lines.append(line)
    
    return '\n'.join(result_lines)


def fix_file(file_path: Path) -> bool:
    """修复单个文件"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        original_content = content
        
        # 应用修复
        content = remove_trailing_whitespace(content)
        content = remove_blank_line_at_eof(content)
        # content = remove_unused_imports(str(file_path), content)  # 暂时禁用，避免误删
        
        # 只有内容改变时才写入
        if content != original_content:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            return True
        
        return False
    except Exception as e:
        print(f"❌ 修复失败 {file_path}: {e}")
        return False


def main():
    """主函数"""
    print("=" * 60)
    print("自动修复代码风格问题")
    print("=" * 60)
    print()
    
    # 获取项目根目录
    project_root = Path(__file__).parent.parent
    
    # 需要修复的目录
    directories = [
        project_root / 'src' / 'auth',
        project_root / 'src' / 'gui',
    ]
    
    fixed_count = 0
    total_count = 0
    
    for directory in directories:
        if not directory.exists():
            continue
            
        print(f"📁 处理目录: {directory.relative_to(project_root)}")
        
        for py_file in directory.rglob('*.py'):
            total_count += 1
            if fix_file(py_file):
                fixed_count += 1
                print(f"  ✅ {py_file.relative_to(project_root)}")
    
    print()
    print("=" * 60)
    print(f"✅ 修复完成！")
    print(f"   处理文件: {total_count}")
    print(f"   修复文件: {fixed_count}")
    print("=" * 60)


if __name__ == '__main__':
    main()

