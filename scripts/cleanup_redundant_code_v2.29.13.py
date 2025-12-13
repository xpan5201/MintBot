#!/usr/bin/env python3
"""
冗余代码清理脚本 v2.29.13
移除未使用的导入、注释掉的代码、调试语句
"""

import re
from pathlib import Path
from typing import List, Tuple

PROJECT_ROOT = Path(__file__).parent.parent


class CodeCleaner:
    """代码清理器"""
    
    def __init__(self):
        self.stats = {
            'debug_prints': 0,
            'commented_code': 0,
            'todo_comments': 0,
            'files_processed': 0,
        }
    
    def find_debug_prints(self, file_path: Path) -> List[Tuple[int, str]]:
        """查找调试print语句"""
        debug_prints = []
        
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            # 查找调试print（不在logger之后）
            if stripped.startswith('print(') and 'logger' not in line:
                # 排除文档字符串中的print
                if i > 1 and '"""' not in lines[i-2] and "'''" not in lines[i-2]:
                    debug_prints.append((i, stripped))
        
        return debug_prints
    
    def find_commented_code(self, file_path: Path) -> List[Tuple[int, str]]:
        """查找注释掉的代码"""
        commented_code = []
        
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            # 查找注释掉的代码（以#开头，包含=或def或class）
            if stripped.startswith('#') and any(keyword in stripped for keyword in ['=', 'def ', 'class ', 'import ', 'from ']):
                # 排除正常的注释
                if not any(marker in stripped for marker in ['TODO', 'FIXME', 'NOTE', 'XXX', '说明', '注意']):
                    commented_code.append((i, stripped[:80]))
        
        return commented_code
    
    def find_todo_comments(self, file_path: Path) -> List[Tuple[int, str]]:
        """查找TODO注释"""
        todos = []
        
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        for i, line in enumerate(lines, 1):
            if 'TODO' in line or 'FIXME' in line or 'XXX' in line:
                todos.append((i, line.strip()[:80]))
        
        return todos
    
    def analyze_file(self, file_path: Path) -> dict:
        """分析单个文件"""
        result = {
            'debug_prints': self.find_debug_prints(file_path),
            'commented_code': self.find_commented_code(file_path),
            'todo_comments': self.find_todo_comments(file_path),
        }
        
        return result
    
    def scan_project(self):
        """扫描整个项目"""
        print("=" * 60)
        print("  冗余代码清理分析 v2.29.13")
        print("=" * 60)
        print()
        
        src_dir = PROJECT_ROOT / "src"
        
        print(f"📂 扫描目录: {src_dir}\n")
        
        files_with_issues = []
        
        for py_file in src_dir.rglob("*.py"):
            # 跳过__pycache__
            if '__pycache__' in str(py_file):
                continue
            
            self.stats['files_processed'] += 1
            result = self.analyze_file(py_file)
            
            has_issues = any(result.values())
            
            if has_issues:
                files_with_issues.append((py_file, result))
                
                print(f"📄 {py_file.relative_to(PROJECT_ROOT)}")
                
                if result['debug_prints']:
                    print(f"  🐛 {len(result['debug_prints'])} 个调试print语句")
                    self.stats['debug_prints'] += len(result['debug_prints'])
                    for line_no, content in result['debug_prints'][:3]:
                        print(f"     L{line_no}: {content[:60]}")
                
                if result['commented_code']:
                    print(f"  💤 {len(result['commented_code'])} 处注释掉的代码")
                    self.stats['commented_code'] += len(result['commented_code'])
                    for line_no, content in result['commented_code'][:3]:
                        print(f"     L{line_no}: {content[:60]}")
                
                if result['todo_comments']:
                    print(f"  📝 {len(result['todo_comments'])} 个TODO注释")
                    self.stats['todo_comments'] += len(result['todo_comments'])
                    for line_no, content in result['todo_comments'][:3]:
                        print(f"     L{line_no}: {content[:60]}")
                
                print()
        
        print("=" * 60)
        print("  清理分析总结")
        print("=" * 60)
        print(f"  扫描文件: {self.stats['files_processed']} 个")
        print(f"  发现问题文件: {len(files_with_issues)} 个")
        print()
        print(f"  调试print语句: {self.stats['debug_prints']} 个")
        print(f"  注释掉的代码: {self.stats['commented_code']} 处")
        print(f"  TODO注释: {self.stats['todo_comments']} 个")
        print()
        
        if self.stats['debug_prints'] > 0:
            print("💡 建议:")
            print("  - 将调试print替换为logger.debug()")
            print("  - 或完全移除调试语句")
            print()
        
        if self.stats['commented_code'] > 0:
            print("💡 建议:")
            print("  - 移除注释掉的代码（使用版本控制系统）")
            print("  - 或将重要的注释改为文档说明")
            print()
        
        if self.stats['todo_comments'] > 0:
            print("💡 建议:")
            print("  - 完成TODO标记的任务")
            print("  - 或创建Issue跟踪")
            print()


def main():
    cleaner = CodeCleaner()
    cleaner.scan_project()


if __name__ == "__main__":
    main()

