"""
智能冗余代码清理脚本 v2.30.12

安全清理策略:
1. 保留重要的分隔注释（====、----、v2.x版本标记）
2. 保留编号列表注释
3. 移除注释掉的代码块
4. 创建备份文件
5. 生成详细的清理报告
"""

from pathlib import Path
from typing import List, Tuple
import re
import shutil

PROJECT_ROOT = Path(__file__).parent.parent


def is_important_comment(line: str) -> bool:
    """判断是否是重要注释（需要保留）"""
    stripped = line.strip()
    
    # 保留分隔注释
    if re.match(r'^#\s*[=\-]{10,}', stripped):
        return True
    
    # 保留版本标记
    if re.search(r'v\d+\.\d+', stripped, re.IGNORECASE):
        return True
    
    # 保留编号列表
    if re.match(r'^#\s*\d+[\.\)、]', stripped):
        return True
    
    # 保留TODO/FIXME/NOTE等标记
    if re.search(r'(TODO|FIXME|NOTE|WARNING|IMPORTANT):', stripped, re.IGNORECASE):
        return True
    
    # 保留文档字符串标记
    if '"""' in stripped or "'''" in stripped:
        return True
    
    return False


def is_commented_code(line: str) -> bool:
    """判断是否是注释掉的代码"""
    stripped = line.strip()
    
    if not stripped.startswith('#'):
        return False
    
    # 移除注释符号
    code = stripped[1:].strip()
    
    if not code:
        return False
    
    # 检查是否是代码特征
    code_patterns = [
        r'^(import|from)\s+\w+',  # import语句
        r'^\w+\s*=\s*.+',  # 赋值语句
        r'^(def|class|if|for|while|try|with|return)\s+',  # 关键字
        r'^\w+\(.*\)',  # 函数调用
        r'^self\.\w+',  # self.属性
        r'^\w+\.\w+',  # 对象.方法
    ]
    
    for pattern in code_patterns:
        if re.match(pattern, code):
            return True
    
    return False


def clean_file(file_path: Path, dry_run: bool = False) -> Tuple[int, List[str]]:
    """清理单个文件的冗余代码"""
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    cleaned_lines = []
    removed_lines = []
    removed_count = 0
    
    i = 0
    while i < len(lines):
        line = lines[i]
        
        # 检查是否是重要注释
        if is_important_comment(line):
            cleaned_lines.append(line)
            i += 1
            continue
        
        # 检查是否是注释掉的代码
        if is_commented_code(line):
            removed_lines.append(f"L{i+1}: {line.rstrip()}")
            removed_count += 1
            i += 1
            continue
        
        cleaned_lines.append(line)
        i += 1
    
    # 如果不是演练模式，写入文件
    if not dry_run and removed_count > 0:
        # 创建备份
        backup_path = file_path.with_suffix(file_path.suffix + '.backup')
        shutil.copy2(file_path, backup_path)
        
        # 写入清理后的内容
        with open(file_path, 'w', encoding='utf-8') as f:
            f.writelines(cleaned_lines)
    
    return removed_count, removed_lines


def main():
    """主函数"""
    print("=" * 70)
    print("  MintChat 智能冗余代码清理 v2.30.12")
    print("=" * 70)
    print()
    
    # 需要清理的文件（根据之前的扫描结果）
    files_to_clean = [
        'src/agent/core.py',
        'src/agent/memory.py',
        'src/agent/memory_scorer.py',
        'src/agent/mood_system.py',
        'src/agent/tools.py',
        'src/auth/database.py',
        'src/auth/user_data_manager.py',
        'src/auth/user_session.py',
        'src/character/prompts.py',
        'src/config/settings.py',
        'src/gui/auth_manager.py',
        'src/gui/auth_window.py',
        'src/gui/contacts_panel.py',
        'src/gui/light_chat_window.py',
        'src/gui/material_design_enhanced.py',
        'src/gui/material_design_light.py',
    ]
    
    total_removed = 0
    cleaned_files = []
    
    print("🔍 扫描并清理冗余代码...")
    print()
    
    for file_rel in files_to_clean:
        file_path = PROJECT_ROOT / file_rel
        if not file_path.exists():
            continue
        
        removed_count, removed_lines = clean_file(file_path, dry_run=False)
        
        if removed_count > 0:
            print(f"📄 {file_rel}")
            print(f"  ✓ 移除 {removed_count} 行注释代码")
            print(f"  ✓ 备份: {file_rel}.backup")
            total_removed += removed_count
            cleaned_files.append(file_rel)
            
            # 显示前3行被移除的内容
            for line in removed_lines[:3]:
                print(f"    - {line}")
            if len(removed_lines) > 3:
                print(f"    ... 还有 {len(removed_lines) - 3} 行")
            print()
    
    print("=" * 70)
    print(f"✅ 清理完成:")
    print(f"  - 处理文件: {len(cleaned_files)} 个")
    print(f"  - 移除代码: {total_removed} 行")
    print(f"  - 备份文件: {len(cleaned_files)} 个")
    print()
    print("💡 提示:")
    print("  - 备份文件已创建（.backup后缀）")
    print("  - 请测试项目功能是否正常")
    print("  - 确认无误后可删除备份文件")
    print("=" * 70)


if __name__ == "__main__":
    main()

