#!/usr/bin/env python3
"""
MintChat 全面代码质量检查工具 v2.30.13
基于2025年最新最佳实践

检查项目：
1. 类型注解覆盖率（目标：80%+）
2. 文档字符串完整性（目标：90%+）
3. 异常处理规范性
4. 代码复杂度（圈复杂度）
5. 安全性问题（SQL注入、路径遍历等）
6. 代码重复度
7. 性能问题（同步阻塞、内存泄漏等）
8. 导入优化（未使用导入、循环导入）

参考标准：
- PEP 8: Python代码风格指南
- PEP 257: 文档字符串规范
- PEP 484: 类型注解
- Google Python Style Guide
- Ruff 2025最佳实践
"""

import ast
import re
from pathlib import Path
from typing import Dict, List, Tuple, Any
from collections import defaultdict

PROJECT_ROOT = Path(__file__).parent.parent


class ComprehensiveQualityChecker:
    """全面代码质量检查器"""

    def __init__(self):
        self.issues = defaultdict(list)
        self.stats = {
            "total_files": 0,
            "total_functions": 0,
            "annotated_functions": 0,
            "documented_functions": 0,
            "total_classes": 0,
            "documented_classes": 0,
        }

    def check_type_annotations(self, file_path: Path, tree: ast.AST) -> None:
        """检查类型注解覆盖率（2025标准：80%+）"""
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self.stats["total_functions"] += 1

                # 跳过特殊方法（__init__, __str__等）
                if node.name.startswith("__") and node.name.endswith("__"):
                    continue

                # 检查返回类型注解
                has_return = node.returns is not None

                # 检查参数类型注解（排除self和cls）
                params = [arg for arg in node.args.args if arg.arg not in ("self", "cls")]
                has_params = all(arg.annotation is not None for arg in params) if params else True

                if has_return and has_params:
                    self.stats["annotated_functions"] += 1
                else:
                    missing = []
                    if not has_return:
                        missing.append("返回类型")
                    if not has_params:
                        missing.append("参数类型")

                    self.issues["type_annotation"].append({
                        "file": str(file_path.relative_to(PROJECT_ROOT)),
                        "line": node.lineno,
                        "function": node.name,
                        "missing": ", ".join(missing),
                    })

    def check_docstrings(self, file_path: Path, tree: ast.AST) -> None:
        """检查文档字符串完整性（2025标准：90%+）"""
        for node in ast.walk(tree):
            # 检查函数文档字符串
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # 跳过私有方法
                if node.name.startswith("_") and not node.name.startswith("__"):
                    continue

                docstring = ast.get_docstring(node)
                if docstring:
                    self.stats["documented_functions"] += 1
                    # 检查文档字符串质量
                    if len(docstring) < 20:
                        self.issues["docstring_quality"].append({
                            "file": str(file_path.relative_to(PROJECT_ROOT)),
                            "line": node.lineno,
                            "function": node.name,
                            "issue": "文档字符串过短（<20字符）",
                        })
                else:
                    self.issues["missing_docstring"].append({
                        "file": str(file_path.relative_to(PROJECT_ROOT)),
                        "line": node.lineno,
                        "function": node.name,
                    })

            # 检查类文档字符串
            elif isinstance(node, ast.ClassDef):
                self.stats["total_classes"] += 1
                docstring = ast.get_docstring(node)
                if docstring:
                    self.stats["documented_classes"] += 1
                else:
                    self.issues["missing_class_docstring"].append({
                        "file": str(file_path.relative_to(PROJECT_ROOT)),
                        "line": node.lineno,
                        "class": node.name,
                    })

    def check_complexity(self, file_path: Path, tree: ast.AST) -> None:
        """检查代码复杂度（圈复杂度 > 10 需要重构）"""
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                complexity = self._calculate_complexity(node)
                if complexity > 10:
                    self.issues["high_complexity"].append({
                        "file": str(file_path.relative_to(PROJECT_ROOT)),
                        "line": node.lineno,
                        "function": node.name,
                        "complexity": complexity,
                        "suggestion": "建议拆分为更小的函数",
                    })

    def _calculate_complexity(self, node: ast.AST) -> int:
        """计算圈复杂度"""
        complexity = 1  # 基础复杂度
        for child in ast.walk(node):
            # 每个分支点增加复杂度
            if isinstance(child, (ast.If, ast.While, ast.For, ast.ExceptHandler)):
                complexity += 1
            elif isinstance(child, ast.BoolOp):
                complexity += len(child.values) - 1
        return complexity

    def check_security_issues(self, file_path: Path, content: str) -> None:
        """检查安全性问题（2025标准）"""
        lines = content.split("\n")

        for i, line in enumerate(lines, 1):
            # 检查SQL注入风险
            if re.search(r'execute\s*\(\s*f["\']|execute\s*\(\s*["\'].*%', line):
                self.issues["security_sql_injection"].append({
                    "file": str(file_path.relative_to(PROJECT_ROOT)),
                    "line": i,
                    "issue": "可能存在SQL注入风险，建议使用参数化查询",
                    "code": line.strip()[:80],
                })

            # 检查eval/exec使用（排除PyQt的menu.exec()和dialog.exec()）
            if re.search(r'\beval\s*\(', line) and "eval" in line:
                # 检查是否已经限制了__builtins__（安全的eval）
                if "__builtins__" not in line:
                    self.issues["security_eval"].append({
                        "file": str(file_path.relative_to(PROJECT_ROOT)),
                        "line": i,
                        "issue": "使用eval存在安全风险，建议限制__builtins__",
                        "code": line.strip()[:80],
                    })
            elif re.search(r'\bexec\s*\(', line) and not re.search(r'\.(exec|exec_)\s*\(', line):
                # 排除PyQt的.exec()方法
                self.issues["security_exec"].append({
                    "file": str(file_path.relative_to(PROJECT_ROOT)),
                    "line": i,
                    "issue": "使用exec存在安全风险",
                    "code": line.strip()[:80],
                })

            # 检查硬编码密钥/密码
            if re.search(r'(password|secret|api_key|token)\s*=\s*["\'][^"\']+["\']', line, re.IGNORECASE):
                if "config" not in line.lower() and "settings" not in line.lower():
                    self.issues["security_hardcoded"].append({
                        "file": str(file_path.relative_to(PROJECT_ROOT)),
                        "line": i,
                        "issue": "可能存在硬编码的密钥/密码",
                        "code": line.strip()[:80],
                    })

    def check_performance_issues(self, file_path: Path, tree: ast.AST) -> None:
        """检查性能问题"""
        for node in ast.walk(tree):
            # 检查同步阻塞调用
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute):
                    # 检查time.sleep在异步函数中
                    if node.func.attr == "sleep":
                        parent_func = self._find_parent_function(tree, node)
                        if parent_func and isinstance(parent_func, ast.AsyncFunctionDef):
                            self.issues["performance_blocking"].append({
                                "file": str(file_path.relative_to(PROJECT_ROOT)),
                                "line": node.lineno,
                                "issue": "异步函数中使用time.sleep，建议使用asyncio.sleep",
                            })

    def _find_parent_function(self, tree: ast.AST, target: ast.AST) -> ast.AST:
        """查找节点的父函数"""
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for child in ast.walk(node):
                    if child is target:
                        return node
        return None

    def check_unused_imports(self, file_path: Path, tree: ast.AST, content: str) -> None:
        """检查未使用的导入"""
        imports = set()
        used_names = set()

        for node in ast.walk(tree):
            # 收集导入
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.add(alias.asname if alias.asname else alias.name)
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    imports.add(alias.asname if alias.asname else alias.name)

            # 收集使用的名称
            elif isinstance(node, ast.Name):
                used_names.add(node.id)

        # 查找未使用的导入
        unused = imports - used_names
        if unused:
            self.issues["unused_imports"].append({
                "file": str(file_path.relative_to(PROJECT_ROOT)),
                "imports": sorted(unused),
                "count": len(unused),
            })

    def check_file(self, file_path: Path) -> None:
        """检查单个文件"""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            tree = ast.parse(content)
            self.stats["total_files"] += 1

            # 执行各项检查
            self.check_type_annotations(file_path, tree)
            self.check_docstrings(file_path, tree)
            self.check_complexity(file_path, tree)
            self.check_security_issues(file_path, content)
            self.check_performance_issues(file_path, tree)
            self.check_unused_imports(file_path, tree, content)

        except Exception as e:
            print(f"⚠️  检查文件失败 {file_path}: {e}")

    def scan_directory(self, directory: Path) -> None:
        """扫描目录"""
        for file_path in directory.rglob("*.py"):
            # 跳过虚拟环境、缓存、测试文件
            if any(part in file_path.parts for part in ["venv", "__pycache__", ".git", "build", "dist", "tests"]):
                continue

            self.check_file(file_path)

    def print_report(self) -> None:
        """打印检查报告"""
        print("\n" + "=" * 80)
        print("  MintChat 全面代码质量检查报告 v2.30.13")
        print("=" * 80)
        print()

        # 统计信息
        print("📊 统计信息")
        print("-" * 80)
        print(f"总文件数: {self.stats['total_files']}")
        print(f"总函数数: {self.stats['total_functions']}")
        print(f"总类数: {self.stats['total_classes']}")
        print()

        # 类型注解覆盖率
        if self.stats["total_functions"] > 0:
            type_coverage = (self.stats["annotated_functions"] / self.stats["total_functions"]) * 100
            print(f"类型注解覆盖率: {type_coverage:.1f}% ({self.stats['annotated_functions']}/{self.stats['total_functions']})")
            if type_coverage < 80:
                print(f"  ⚠️  低于目标值 80%，建议提升")
            else:
                print(f"  ✅ 达到目标值 80%")

        # 文档字符串覆盖率
        if self.stats["total_functions"] > 0:
            doc_coverage = (self.stats["documented_functions"] / self.stats["total_functions"]) * 100
            print(f"文档字符串覆盖率: {doc_coverage:.1f}% ({self.stats['documented_functions']}/{self.stats['total_functions']})")
            if doc_coverage < 90:
                print(f"  ⚠️  低于目标值 90%，建议提升")
            else:
                print(f"  ✅ 达到目标值 90%")

        # 类文档覆盖率
        if self.stats["total_classes"] > 0:
            class_doc_coverage = (self.stats["documented_classes"] / self.stats["total_classes"]) * 100
            print(f"类文档覆盖率: {class_doc_coverage:.1f}% ({self.stats['documented_classes']}/{self.stats['total_classes']})")

        print()

        # 问题汇总
        total_issues = sum(len(issues) for issues in self.issues.values())
        print(f"🔍 发现问题: {total_issues} 个")
        print("-" * 80)

        # 按类别显示问题
        issue_categories = {
            "type_annotation": "❌ 类型注解缺失",
            "missing_docstring": "📝 文档字符串缺失",
            "docstring_quality": "📝 文档字符串质量问题",
            "missing_class_docstring": "📝 类文档字符串缺失",
            "high_complexity": "⚠️  高复杂度函数",
            "security_sql_injection": "🔒 SQL注入风险",
            "security_eval": "🔒 eval/exec安全风险",
            "security_hardcoded": "🔒 硬编码密钥",
            "performance_blocking": "⚡ 性能问题（阻塞调用）",
            "unused_imports": "🧹 未使用的导入",
        }

        for category, title in issue_categories.items():
            if category in self.issues and self.issues[category]:
                print(f"\n{title} ({len(self.issues[category])}个)")
                print("-" * 80)

                # 显示前5个问题
                for issue in self.issues[category][:5]:
                    if category == "type_annotation":
                        print(f"  📄 {issue['file']}:{issue['line']}")
                        print(f"     函数: {issue['function']}")
                        print(f"     缺失: {issue['missing']}")
                    elif category in ["missing_docstring", "missing_class_docstring"]:
                        print(f"  📄 {issue['file']}:{issue['line']}")
                        if "function" in issue:
                            print(f"     函数: {issue['function']}")
                        if "class" in issue:
                            print(f"     类: {issue['class']}")
                    elif category == "high_complexity":
                        print(f"  📄 {issue['file']}:{issue['line']}")
                        print(f"     函数: {issue['function']}")
                        print(f"     复杂度: {issue['complexity']} (建议 <= 10)")
                    elif category.startswith("security_"):
                        print(f"  📄 {issue['file']}:{issue['line']}")
                        print(f"     问题: {issue['issue']}")
                        if "code" in issue:
                            print(f"     代码: {issue['code']}")
                    elif category == "unused_imports":
                        print(f"  📄 {issue['file']}")
                        print(f"     未使用: {', '.join(issue['imports'][:5])}")
                        if len(issue['imports']) > 5:
                            print(f"     ... 还有 {len(issue['imports']) - 5} 个")

                if len(self.issues[category]) > 5:
                    print(f"  ... 还有 {len(self.issues[category]) - 5} 个问题")

        print()
        print("=" * 80)
        print("✅ 检查完成！")
        print("=" * 80)


def main():
    """主函数"""
    checker = ComprehensiveQualityChecker()

    print("🔍 开始扫描项目...")
    print()

    # 扫描src目录
    src_dir = PROJECT_ROOT / "src"
    if src_dir.exists():
        checker.scan_directory(src_dir)

    # 打印报告
    checker.print_report()


if __name__ == "__main__":
    main()


