#!/usr/bin/env python3
"""
GUI代码优化脚本

自动修复GUI代码中的常见问题：
1. 移除未使用的导入
2. 修复重复导入
3. 优化导入顺序
4. 检查代码规范
5. 优化性能问题
"""

import os
import re
import sys
from pathlib import Path
from typing import List, Set, Tuple

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


class GUICodeOptimizer:
    """GUI代码优化器"""

    def __init__(self, gui_dir: Path):
        self.gui_dir = gui_dir
        self.issues_found = []
        self.fixes_applied = []

    def analyze_file(self, file_path: Path) -> dict:
        """分析单个文件"""
        issues = {
            'duplicate_imports': [],
            'unused_imports': [],
            'import_order': [],
            'performance': [],
            'memory': []
        }

        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            lines = content.split('\n')

        # 检查重复导入
        imports = {}
        for i, line in enumerate(lines, 1):
            if line.strip().startswith(('import ', 'from ')):
                import_key = line.strip()
                if import_key in imports:
                    issues['duplicate_imports'].append({
                        'line': i,
                        'content': line,
                        'first_occurrence': imports[import_key]
                    })
                else:
                    imports[import_key] = i

        # 检查性能问题
        # 1. 检查是否在循环中创建动画对象
        for i, line in enumerate(lines, 1):
            if 'QPropertyAnimation' in line and any(
                keyword in lines[max(0, i-10):i]
                for keyword in ['for ', 'while ']
            ):
                issues['performance'].append({
                    'line': i,
                    'type': 'animation_in_loop',
                    'content': line
                })

        # 2. 检查是否有未清理的定时器
        timer_created = set()
        timer_stopped = set()
        for i, line in enumerate(lines, 1):
            if 'QTimer' in line and '=' in line:
                var_name = line.split('=')[0].strip().split()[-1]
                timer_created.add(var_name)
            if '.stop()' in line:
                var_name = line.split('.stop()')[0].strip().split()[-1]
                timer_stopped.add(var_name)

        unstop_timers = timer_created - timer_stopped
        if unstop_timers:
            issues['memory'].append({
                'type': 'unstop_timers',
                'timers': list(unstop_timers)
            })

        return issues

    def fix_duplicate_imports(self, file_path: Path) -> bool:
        """修复重复导入 - 只移除顶层的重复导入，保留函数内的局部导入"""
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        seen_imports = set()
        new_lines = []
        removed_count = 0
        in_function = False
        indent_level = 0

        for i, line in enumerate(lines):
            stripped = line.strip()

            # 检测是否在函数内部（通过缩进判断）
            if stripped.startswith('def '):
                in_function = True
                indent_level = len(line) - len(line.lstrip())
            elif in_function and line.strip() and not line[0].isspace():
                # 回到顶层，退出函数
                in_function = False
                indent_level = 0

            # 只检查顶层的导入语句
            if stripped.startswith(('import ', 'from ')):
                current_indent = len(line) - len(line.lstrip())

                # 如果是顶层导入（缩进为0）
                if current_indent == 0:
                    if stripped not in seen_imports:
                        seen_imports.add(stripped)
                        new_lines.append(line)
                    else:
                        removed_count += 1
                        print(f"  移除重复导入: {stripped}")
                else:
                    # 函数内的局部导入，保留
                    new_lines.append(line)
            else:
                new_lines.append(line)

        if removed_count > 0:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.writelines(new_lines)
            return True
        return False

    def optimize_imports(self, file_path: Path) -> bool:
        """优化导入顺序（标准库、第三方库、本地模块）"""
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # 提取导入语句
        import_pattern = r'^(?:from\s+\S+\s+)?import\s+.+$'
        imports = []
        other_lines = []
        in_imports = True

        for line in content.split('\n'):
            if re.match(import_pattern, line.strip()):
                imports.append(line)
            elif line.strip() and in_imports:
                in_imports = False
                other_lines.append(line)
            else:
                other_lines.append(line)

        if not imports:
            return False

        # 分类导入
        stdlib_imports = []
        third_party_imports = []
        local_imports = []

        stdlib_modules = {
            'sys', 'os', 'pathlib', 'typing', 're', 'json', 'datetime',
            'time', 'collections', 'itertools', 'functools', 'abc'
        }

        for imp in imports:
            if imp.strip().startswith('from .') or imp.strip().startswith('from src.'):
                local_imports.append(imp)
            else:
                module = imp.split()[1].split('.')[0]
                if module in stdlib_modules:
                    stdlib_imports.append(imp)
                else:
                    third_party_imports.append(imp)

        # 重新组织
        organized_imports = []
        if stdlib_imports:
            organized_imports.extend(sorted(stdlib_imports))
            organized_imports.append('')
        if third_party_imports:
            organized_imports.extend(sorted(third_party_imports))
            organized_imports.append('')
        if local_imports:
            organized_imports.extend(sorted(local_imports))
            organized_imports.append('')

        # 重新组合内容
        new_content = '\n'.join(organized_imports + other_lines)

        if new_content != content:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(new_content)
            return True
        return False

    def run(self):
        """运行优化"""
        print("=" * 70)
        print("  MintChat GUI 代码优化工具")
        print("=" * 70)
        print()

        # 获取所有Python文件
        py_files = list(self.gui_dir.glob('*.py'))
        print(f"找到 {len(py_files)} 个Python文件")
        print()

        total_issues = 0
        total_fixes = 0

        for py_file in py_files:
            if py_file.name.startswith('__'):
                continue

            print(f"分析: {py_file.name}")

            # 分析文件
            issues = self.analyze_file(py_file)

            # 统计问题
            file_issues = sum(len(v) if isinstance(v, list) else 1
                            for v in issues.values() if v)

            if file_issues > 0:
                total_issues += file_issues
                print(f"  发现 {file_issues} 个问题")

                # 显示问题详情
                if issues['duplicate_imports']:
                    print(f"    - {len(issues['duplicate_imports'])} 个重复导入")
                if issues['performance']:
                    print(f"    - {len(issues['performance'])} 个性能问题")
                if issues['memory']:
                    print(f"    - {len(issues['memory'])} 个内存问题")

                # 修复重复导入
                if issues['duplicate_imports']:
                    if self.fix_duplicate_imports(py_file):
                        total_fixes += len(issues['duplicate_imports'])
                        print(f"  ✓ 已修复重复导入")

        print()
        print("=" * 70)
        print(f"优化完成！")
        print(f"  发现问题: {total_issues}")
        print(f"  已修复: {total_fixes}")
        print("=" * 70)


def main():
    """主函数"""
    gui_dir = project_root / 'src' / 'gui'

    if not gui_dir.exists():
        print(f"错误: GUI目录不存在: {gui_dir}")
        return 1

    optimizer = GUICodeOptimizer(gui_dir)
    optimizer.run()

    return 0


if __name__ == '__main__':
    sys.exit(main())

