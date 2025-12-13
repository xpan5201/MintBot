"""
自动修复代码质量问题 v2.30.12

修复内容:
1. 将调试print语句替换为logger
2. 移除注释掉的代码（保留重要的分隔注释）
3. 优化异常处理
4. 提升代码规范性
"""

import re
from pathlib import Path
from typing import List, Tuple, Dict

PROJECT_ROOT = Path(__file__).parent.parent


def fix_print_statements(file_path: Path) -> int:
    """将print语句替换为logger"""
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
        lines = content.split('\n')
    
    changes = 0
    new_lines = []
    has_logger_import = 'from src.utils.logger import' in content or 'from loguru import logger' in content
    needs_logger_import = False
    
    for i, line in enumerate(lines):
        stripped = line.strip()
        
        # 跳过文档字符串中的print
        if '"""' in line or "'''" in line:
            new_lines.append(line)
            continue
        
        # 检测调试print语句
        if stripped.startswith('print(') and 'logger' not in line:
            # 提取print内容
            match = re.match(r'(\s*)print\((.*)\)', line)
            if match:
                indent = match.group(1)
                content_str = match.group(2)
                
                # 判断日志级别
                if '警告' in content_str or 'Warning' in content_str or '⚠' in content_str:
                    new_line = f'{indent}logger.warning({content_str})'
                elif '错误' in content_str or 'Error' in content_str or '❌' in content_str:
                    new_line = f'{indent}logger.error({content_str})'
                elif '成功' in content_str or 'Success' in content_str or '✅' in content_str:
                    new_line = f'{indent}logger.success({content_str})'
                else:
                    new_line = f'{indent}logger.info({content_str})'
                
                new_lines.append(new_line)
                changes += 1
                needs_logger_import = True
                continue
        
        new_lines.append(line)
    
    # 添加logger导入（如果需要且不存在）
    if needs_logger_import and not has_logger_import:
        # 找到导入区域的末尾
        import_end = 0
        for i, line in enumerate(new_lines):
            if line.strip().startswith(('import ', 'from ')):
                import_end = i
        
        # 在导入区域末尾添加logger导入
        if import_end > 0:
            new_lines.insert(import_end + 1, 'from src.utils.logger import logger')
            changes += 1
    
    if changes > 0:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(new_lines))
    
    return changes


def remove_commented_code(file_path: Path) -> int:
    """移除注释掉的代码（保留重要的分隔注释）"""
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    changes = 0
    new_lines = []
    
    # 保留的注释模式（分隔线、重要说明等）
    keep_patterns = [
        r'^\s*#\s*=+',  # 分隔线
        r'^\s*#\s*-+',  # 分隔线
        r'^\s*#\s*\d+\.',  # 编号列表
        r'^\s*#\s*(TODO|FIXME|NOTE|XXX|HACK|WARNING)',  # 重要标记
        r'^\s*#\s*[一二三四五六七八九十\d]+[、.]',  # 中文编号
        r'^\s*#\s*v\d+\.\d+',  # 版本标记
    ]
    
    for line in lines:
        stripped = line.strip()
        
        # 检查是否是需要保留的注释
        should_keep = False
        for pattern in keep_patterns:
            if re.match(pattern, stripped):
                should_keep = True
                break
        
        # 如果是需要保留的注释，直接添加
        if should_keep:
            new_lines.append(line)
            continue
        
        # 检查是否是注释掉的代码
        if stripped.startswith('#') and any(keyword in stripped for keyword in ['=', 'def ', 'class ', 'import ', 'from ']):
            # 跳过这行（移除注释掉的代码）
            changes += 1
            continue
        
        new_lines.append(line)
    
    if changes > 0:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.writelines(new_lines)
    
    return changes


def main():
    """主函数"""
    print("=" * 70)
    print("  MintChat 代码质量自动修复 v2.30.12")
    print("=" * 70)
    print()
    
    # 需要修复的文件列表
    files_to_fix = [
        'src/config/settings.py',
        'src/config/performance.py',
        'src/character/config_loader.py',
        'src/gui/material_icons.py',
        'src/gui/auth_manager.py',
        'src/gui/light_chat_window.py',
        'src/gui/settings_panel.py',
        'src/gui/modern_chat_window.py',
        'src/utils/memory_monitor.py',
        'src/utils/performance.py',
        'src/utils/performance_optimizer.py',
    ]
    
    total_print_fixes = 0
    total_comment_fixes = 0
    
    for file_rel in files_to_fix:
        file_path = PROJECT_ROOT / file_rel
        if not file_path.exists():
            continue
        
        print(f"📝 处理: {file_rel}")
        
        # 修复print语句
        print_fixes = fix_print_statements(file_path)
        if print_fixes > 0:
            print(f"  ✓ 修复 {print_fixes} 个print语句")
            total_print_fixes += print_fixes
        
        # 移除注释掉的代码
        comment_fixes = remove_commented_code(file_path)
        if comment_fixes > 0:
            print(f"  ✓ 移除 {comment_fixes} 处注释代码")
            total_comment_fixes += comment_fixes
    
    print()
    print(f"✅ 总共修复:")
    print(f"  - Print语句: {total_print_fixes} 个")
    print(f"  - 注释代码: {total_comment_fixes} 处")
    print()


if __name__ == "__main__":
    main()

