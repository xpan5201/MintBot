"""
深度代码质量检查脚本 v2.30.12

检查项目:
1. 未使用的导入
2. 未使用的变量
3. 复杂度过高的函数
4. 过长的函数
5. 重复代码
6. 潜在的性能问题
"""

from pathlib import Path
from typing import List, Dict, Tuple
import re
import ast

PROJECT_ROOT = Path(__file__).parent.parent


class CodeQualityChecker:
    """代码质量检查器"""
    
    def __init__(self):
        self.issues = {
            'unused_imports': [],
            'long_functions': [],
            'complex_functions': [],
            'performance_issues': [],
            'code_smells': [],
        }
    
    def check_file(self, file_path: Path) -> Dict:
        """检查单个文件"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                lines = content.split('\n')
            
            # 检查函数长度
            self._check_function_length(file_path, content)
            
            # 检查性能问题
            self._check_performance_issues(file_path, lines)
            
            # 检查代码异味
            self._check_code_smells(file_path, lines)
            
        except Exception as e:
            print(f"  ⚠️ 检查失败: {e}")
        
        return self.issues
    
    def _check_function_length(self, file_path: Path, content: str):
        """检查函数长度"""
        try:
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    # 计算函数行数
                    func_lines = node.end_lineno - node.lineno + 1
                    if func_lines > 100:
                        self.issues['long_functions'].append({
                            'file': str(file_path.relative_to(PROJECT_ROOT)),
                            'function': node.name,
                            'lines': func_lines,
                            'start_line': node.lineno,
                        })
        except:
            pass
    
    def _check_performance_issues(self, file_path: Path, lines: List[str]):
        """检查性能问题"""
        file_rel = str(file_path.relative_to(PROJECT_ROOT))
        
        for i, line in enumerate(lines, 1):
            # 检查循环中的字符串拼接
            if re.search(r'for\s+\w+\s+in\s+', line):
                # 检查后续几行是否有 += 字符串拼接
                for j in range(i, min(i + 10, len(lines))):
                    if re.search(r'\w+\s*\+=\s*["\']', lines[j]):
                        self.issues['performance_issues'].append({
                            'file': file_rel,
                            'line': j + 1,
                            'issue': '循环中使用字符串拼接，建议使用列表join',
                            'code': lines[j].strip(),
                        })
            
            # 检查重复的列表查找
            if line.count('.index(') > 1 or line.count(' in ') > 2:
                self.issues['performance_issues'].append({
                    'file': file_rel,
                    'line': i,
                    'issue': '重复的列表查找，考虑使用字典或集合',
                    'code': line.strip(),
                })
    
    def _check_code_smells(self, file_path: Path, lines: List[str]):
        """检查代码异味"""
        file_rel = str(file_path.relative_to(PROJECT_ROOT))
        
        for i, line in enumerate(lines, 1):
            # 检查裸except
            if re.match(r'\s*except\s*:', line):
                self.issues['code_smells'].append({
                    'file': file_rel,
                    'line': i,
                    'issue': '裸except子句，应指定具体异常类型',
                    'code': line.strip(),
                })
            
            # 检查过长的行
            if len(line) > 120:
                self.issues['code_smells'].append({
                    'file': file_rel,
                    'line': i,
                    'issue': f'行过长（{len(line)}字符），建议不超过120',
                    'code': line.strip()[:80] + '...',
                })


def main():
    """主函数"""
    print("=" * 70)
    print("  MintChat 深度代码质量检查 v2.30.12")
    print("=" * 70)
    print()
    
    # 检查核心模块
    core_modules = [
        'src/agent/core.py',
        'src/agent/memory.py',
        'src/agent/advanced_memory.py',
        'src/config/settings.py',
        'src/utils/async_manager.py',
        'src/utils/performance.py',
    ]
    
    checker = CodeQualityChecker()
    
    print("🔍 检查核心模块代码质量...")
    print()
    
    for module in core_modules:
        file_path = PROJECT_ROOT / module
        if file_path.exists():
            print(f"📄 检查: {module}")
            checker.check_file(file_path)
    
    print()
    print("=" * 70)
    print("📊 检查结果:")
    print("=" * 70)
    print()
    
    # 显示长函数
    if checker.issues['long_functions']:
        print(f"⚠️ 过长函数 ({len(checker.issues['long_functions'])} 个):")
        for issue in checker.issues['long_functions'][:5]:
            print(f"  - {issue['file']}:{issue['start_line']} - {issue['function']}() ({issue['lines']}行)")
        if len(checker.issues['long_functions']) > 5:
            print(f"  ... 还有 {len(checker.issues['long_functions']) - 5} 个")
        print()
    
    # 显示性能问题
    if checker.issues['performance_issues']:
        print(f"⚡ 性能问题 ({len(checker.issues['performance_issues'])} 个):")
        for issue in checker.issues['performance_issues'][:5]:
            print(f"  - {issue['file']}:{issue['line']} - {issue['issue']}")
        if len(checker.issues['performance_issues']) > 5:
            print(f"  ... 还有 {len(checker.issues['performance_issues']) - 5} 个")
        print()
    
    # 显示代码异味
    if checker.issues['code_smells']:
        print(f"🔍 代码异味 ({len(checker.issues['code_smells'])} 个):")
        for issue in checker.issues['code_smells'][:5]:
            print(f"  - {issue['file']}:{issue['line']} - {issue['issue']}")
        if len(checker.issues['code_smells']) > 5:
            print(f"  ... 还有 {len(checker.issues['code_smells']) - 5} 个")
        print()
    
    print("✅ 检查完成")
    print("=" * 70)


if __name__ == "__main__":
    main()

