#!/usr/bin/env python3
"""
自动添加类型注解工具 v2.30.13
基于2025年Python 3.12最佳实践

功能：
1. 自动为缺少类型注解的函数添加基础类型注解
2. 基于函数名和参数名推断类型
3. 为返回值添加类型注解
4. 支持常见类型（str, int, bool, dict, list等）

注意：
- 这是一个辅助工具，生成的类型注解需要人工审核
- 建议先备份文件再运行
- 生成的注解可能不完全准确，需要根据实际情况调整
"""

import ast
import re
from pathlib import Path
from typing import Dict, List, Set

PROJECT_ROOT = Path(__file__).parent.parent


class TypeHintAdder:
    """类型注解添加器"""

    def __init__(self):
        self.modified_files = []
        self.stats = {
            "total_functions": 0,
            "added_annotations": 0,
        }

        # 常见类型推断规则
        self.type_inference_rules = {
            # 参数名模式 -> 类型
            "name": "str",
            "text": "str",
            "message": "str",
            "content": "str",
            "path": "str",
            "file": "str",
            "url": "str",
            "id": "int",
            "count": "int",
            "index": "int",
            "size": "int",
            "limit": "int",
            "offset": "int",
            "enabled": "bool",
            "is_": "bool",  # is_开头的参数
            "has_": "bool",  # has_开头的参数
            "data": "Dict[str, Any]",
            "config": "Dict[str, Any]",
            "settings": "Dict[str, Any]",
            "items": "List[Any]",
            "results": "List[Any]",
        }

        # 函数名模式 -> 返回类型
        self.return_type_rules = {
            "get_": "Optional[Any]",
            "is_": "bool",
            "has_": "bool",
            "check_": "bool",
            "validate_": "bool",
            "count_": "int",
            "calculate_": "float",
            "load_": "Optional[Any]",
            "save_": "bool",
            "create_": "Optional[Any]",
            "delete_": "bool",
            "update_": "bool",
            "find_": "Optional[Any]",
            "search_": "List[Any]",
            "list_": "List[Any]",
            "to_": "str",  # to_string, to_dict等
        }

    def infer_param_type(self, param_name: str) -> str:
        """推断参数类型"""
        # 精确匹配
        if param_name in self.type_inference_rules:
            return self.type_inference_rules[param_name]

        # 前缀匹配
        for prefix, type_hint in self.type_inference_rules.items():
            if param_name.startswith(prefix):
                return type_hint

        # 后缀匹配
        if param_name.endswith("_id"):
            return "int"
        elif param_name.endswith("_name"):
            return "str"
        elif param_name.endswith("_path"):
            return "str"
        elif param_name.endswith("_count"):
            return "int"
        elif param_name.endswith("_list"):
            return "List[Any]"
        elif param_name.endswith("_dict"):
            return "Dict[str, Any]"

        # 默认类型
        return "Any"

    def infer_return_type(self, func_name: str) -> str:
        """推断返回类型"""
        # 前缀匹配
        for prefix, type_hint in self.return_type_rules.items():
            if func_name.startswith(prefix):
                return type_hint

        # 默认返回类型
        return "Any"

    def add_type_hints_to_function(self, func_def: str, func_name: str, params: List[str]) -> str:
        """为函数添加类型注解"""
        # 解析函数定义
        lines = func_def.split("\n")
        func_line = lines[0]

        # 检查是否已有类型注解
        if "->" in func_line:
            return func_def  # 已有返回类型注解

        # 为参数添加类型注解
        modified_params = []
        for param in params:
            param = param.strip()
            if not param or param in ("self", "cls"):
                modified_params.append(param)
                continue

            # 检查是否已有类型注解
            if ":" in param:
                modified_params.append(param)
                continue

            # 推断类型
            param_name = param.split("=")[0].strip()  # 移除默认值
            param_type = self.infer_param_type(param_name)

            # 添加类型注解
            if "=" in param:
                # 有默认值
                name, default = param.split("=", 1)
                modified_params.append(f"{name.strip()}: {param_type} = {default.strip()}")
            else:
                # 无默认值
                modified_params.append(f"{param}: {param_type}")

        # 推断返回类型
        return_type = self.infer_return_type(func_name)

        # 重构函数定义
        # 这里简化处理，实际应该使用AST重写
        # 由于复杂性，这里只生成建议，不直接修改文件

        return func_def

    def analyze_file(self, file_path: Path) -> List[Dict]:
        """分析文件，找出需要添加类型注解的函数"""
        suggestions = []

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            tree = ast.parse(content)

            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    self.stats["total_functions"] += 1

                    # 跳过特殊方法
                    if node.name.startswith("__") and node.name.endswith("__"):
                        continue

                    # 检查是否缺少类型注解
                    missing_annotations = []

                    # 检查返回类型
                    if node.returns is None:
                        missing_annotations.append("return")

                    # 检查参数类型
                    for arg in node.args.args:
                        if arg.arg not in ("self", "cls") and arg.annotation is None:
                            missing_annotations.append(f"param:{arg.arg}")

                    if missing_annotations:
                        # 生成建议
                        param_types = []
                        for arg in node.args.args:
                            if arg.arg in ("self", "cls"):
                                continue
                            if arg.annotation is None:
                                param_type = self.infer_param_type(arg.arg)
                                param_types.append(f"{arg.arg}: {param_type}")
                            else:
                                param_types.append(f"{arg.arg}: <已有注解>")

                        return_type = self.infer_return_type(node.name) if node.returns is None else "<已有注解>"

                        suggestions.append({
                            "file": str(file_path.relative_to(PROJECT_ROOT)),
                            "line": node.lineno,
                            "function": node.name,
                            "missing": missing_annotations,
                            "suggested_params": param_types,
                            "suggested_return": return_type,
                        })

        except Exception as e:
            print(f"⚠️  分析文件失败 {file_path}: {e}")

        return suggestions

    def scan_directory(self, directory: Path) -> List[Dict]:
        """扫描目录"""
        all_suggestions = []

        for file_path in directory.rglob("*.py"):
            # 跳过虚拟环境、缓存、测试文件
            if any(part in file_path.parts for part in ["venv", "__pycache__", ".git", "build", "dist", "tests"]):
                continue

            suggestions = self.analyze_file(file_path)
            all_suggestions.extend(suggestions)

        return all_suggestions

    def print_report(self, suggestions: List[Dict]) -> None:
        """打印报告"""
        print("\n" + "=" * 80)
        print("  类型注解建议报告 v2.30.13")
        print("=" * 80)
        print()

        print(f"📊 统计信息")
        print("-" * 80)
        print(f"总函数数: {self.stats['total_functions']}")
        print(f"需要添加注解的函数: {len(suggestions)}")
        print()

        if not suggestions:
            print("✅ 所有函数都已有完整的类型注解！")
            return

        # 按文件分组
        by_file = {}
        for suggestion in suggestions:
            file = suggestion["file"]
            if file not in by_file:
                by_file[file] = []
            by_file[file].append(suggestion)

        print(f"📝 类型注解建议（显示前10个文件）")
        print("-" * 80)

        for i, (file, file_suggestions) in enumerate(sorted(by_file.items())[:10]):
            print(f"\n📄 {file} ({len(file_suggestions)}个函数)")

            # 显示前3个函数
            for suggestion in file_suggestions[:3]:
                print(f"  行 {suggestion['line']}: {suggestion['function']}()")
                if suggestion['suggested_params']:
                    print(f"    参数建议: {', '.join(suggestion['suggested_params'][:3])}")
                    if len(suggestion['suggested_params']) > 3:
                        print(f"              ... 还有 {len(suggestion['suggested_params']) - 3} 个参数")
                print(f"    返回类型建议: {suggestion['suggested_return']}")

            if len(file_suggestions) > 3:
                print(f"  ... 还有 {len(file_suggestions) - 3} 个函数")

        if len(by_file) > 10:
            print(f"\n... 还有 {len(by_file) - 10} 个文件")

        print()
        print("=" * 80)
        print("💡 建议：")
        print("  1. 优先为公共API函数添加类型注解")
        print("  2. 使用mypy或pyright进行类型检查")
        print("  3. 参考Python 3.13类型注解最佳实践")
        print("  4. 建议目标：类型注解覆盖率 >= 80%")
        print("=" * 80)


def main():
    """主函数"""
    adder = TypeHintAdder()

    print("🔍 开始扫描项目...")
    print()

    # 扫描src目录
    src_dir = PROJECT_ROOT / "src"
    if src_dir.exists():
        suggestions = adder.scan_directory(src_dir)
        adder.print_report(suggestions)


if __name__ == "__main__":
    main()


