#!/usr/bin/env python3
"""
移除版本注释脚本 v2.48.7

移除light_chat_window.py中的冗余版本注释（v2.x.x格式）
保留重要的功能说明，只移除版本号标记
"""

import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
TARGET_FILE = PROJECT_ROOT / "src" / "gui" / "light_chat_window.py"


def remove_version_comments(file_path: Path) -> tuple[int, int]:
    """
    移除文件中的版本注释
    
    Returns:
        (移除的注释数量, 减少的行数)
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    new_lines = []
    removed_count = 0
    removed_lines = 0
    
    # 正则表达式匹配版本注释
    # 匹配: # v2.30.13: 说明
    # 匹配: # v2.30.13 说明
    # 匹配: (v2.30.13)
    # 匹配: - v2.30.13 说明
    version_pattern = re.compile(r'#\s*v2\.\d+\.\d+[:\s]|v2\.\d+\.\d+[:\s]|\(v2\.\d+\.\d+\)|[-–]\s*v2\.\d+\.\d+')
    
    for line in lines:
        original_line = line
        
        # 检查是否包含版本注释
        if version_pattern.search(line):
            # 移除版本标记，保留功能说明
            # 例如: "# v2.30.13: 用于强制处理事件" -> "# 用于强制处理事件"
            new_line = version_pattern.sub('', line)
            
            # 清理多余的空格和冒号
            new_line = re.sub(r'#\s*:\s*', '# ', new_line)
            new_line = re.sub(r'#\s+', '# ', new_line)
            
            # 如果移除版本号后只剩下空注释，则完全移除该行
            if re.match(r'^\s*#\s*$', new_line):
                removed_lines += 1
                removed_count += 1
                continue
            
            # 如果移除版本号后注释变得很短（<5个字符），也移除
            comment_content = re.sub(r'^\s*#\s*', '', new_line).strip()
            if len(comment_content) < 5:
                removed_lines += 1
                removed_count += 1
                continue
            
            new_lines.append(new_line)
            removed_count += 1
        else:
            new_lines.append(original_line)
    
    # 写回文件
    with open(file_path, 'w', encoding='utf-8') as f:
        f.writelines(new_lines)
    
    return removed_count, removed_lines


def main():
    print("=" * 60)
    print("  移除版本注释脚本 v2.48.7")
    print("=" * 60)
    print()
    
    if not TARGET_FILE.exists():
        print(f"❌ 文件不存在: {TARGET_FILE}")
        return
    
    print(f"📝 处理文件: {TARGET_FILE.relative_to(PROJECT_ROOT)}")
    print()
    
    # 备份原文件
    backup_file = TARGET_FILE.with_suffix('.py.bak')
    import shutil
    shutil.copy2(TARGET_FILE, backup_file)
    print(f"✅ 已备份到: {backup_file.name}")
    print()
    
    # 移除版本注释
    removed_count, removed_lines = remove_version_comments(TARGET_FILE)
    
    print("=" * 60)
    print("  优化结果")
    print("=" * 60)
    print(f"  移除版本注释: {removed_count} 处")
    print(f"  减少代码行数: {removed_lines} 行")
    print()
    print("✅ 优化完成！")
    print()
    print(f"💡 如需恢复，请运行:")
    print(f"   copy {backup_file.name} {TARGET_FILE.name}")


if __name__ == "__main__":
    main()

