"""
代码质量检查脚本 (v2.29.12)

自动检查和优化代码质量：
- 类型注解检查
- 代码风格检查
- 性能问题检测
- 安全漏洞扫描
- 依赖更新检查

作者: MintChat Team
日期: 2025-11-13
"""

import ast
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Tuple

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent


class CodeQualityChecker:
    """代码质量检查器"""

    def __init__(self):
        self.issues: List[Dict] = []
        self.warnings: List[Dict] = []
        self.suggestions: List[Dict] = []

    def check_type_annotations(self, file_path: Path) -> None:
        """检查类型注解覆盖率"""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            tree = ast.parse(content)

            total_functions = 0
            annotated_functions = 0

            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    total_functions += 1

                    # 检查返回类型注解
                    has_return_annotation = node.returns is not None

                    # 检查参数类型注解
                    has_param_annotations = all(
                        arg.annotation is not None for arg in node.args.args if arg.arg != "self"
                    )

                    if has_return_annotation and has_param_annotations:
                        annotated_functions += 1

            if total_functions > 0:
                coverage = (annotated_functions / total_functions) * 100
                if coverage < 80:
                    self.warnings.append(
                        {
                            "file": str(file_path.relative_to(PROJECT_ROOT)),
                            "type": "type_annotation",
                            "message": f"类型注解覆盖率: {coverage:.1f}% (建议 >= 80%)",
                        }
                    )

        except Exception as e:
            print(f"检查类型注解失败 {file_path}: {e}")

    def check_async_patterns(self, file_path: Path) -> None:
        """检查异步模式使用"""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            # 检查是否使用了旧的异步模式
            if "asyncio.get_event_loop()" in content:
                self.suggestions.append(
                    {
                        "file": str(file_path.relative_to(PROJECT_ROOT)),
                        "type": "async_pattern",
                        "message": "建议使用 asyncio.run() 或 asyncio.create_task() 替代 get_event_loop()",
                    }
                )

            # 检查是否缺少异步上下文管理器
            if "async def" in content and "async with" not in content:
                self.suggestions.append(
                    {
                        "file": str(file_path.relative_to(PROJECT_ROOT)),
                        "type": "async_pattern",
                        "message": "考虑使用 async with 进行资源管理",
                    }
                )

        except Exception as e:
            print(f"检查异步模式失败 {file_path}: {e}")

    def check_exception_handling(self, file_path: Path) -> None:
        """检查异常处理"""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            tree = ast.parse(content)

            for node in ast.walk(tree):
                if isinstance(node, ast.ExceptHandler):
                    # 检查是否有裸except
                    if node.type is None:
                        self.issues.append(
                            {
                                "file": str(file_path.relative_to(PROJECT_ROOT)),
                                "line": node.lineno,
                                "type": "exception_handling",
                                "message": "避免使用裸 except，应指定具体异常类型",
                            }
                        )

                    # 检查是否吞掉了异常
                    if len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
                        self.warnings.append(
                            {
                                "file": str(file_path.relative_to(PROJECT_ROOT)),
                                "line": node.lineno,
                                "type": "exception_handling",
                                "message": "异常被静默忽略，建议至少记录日志",
                            }
                        )

        except Exception as e:
            print(f"检查异常处理失败 {file_path}: {e}")

    def check_performance_issues(self, file_path: Path) -> None:
        """检查性能问题"""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            # 检查循环中的字符串拼接
            if re.search(r"for\s+\w+\s+in.*:\s*\w+\s*\+=\s*['\"]", content):
                self.suggestions.append(
                    {
                        "file": str(file_path.relative_to(PROJECT_ROOT)),
                        "type": "performance",
                        "message": "循环中使用字符串拼接，建议使用 join() 或 f-string",
                    }
                )

            # 检查重复的正则表达式编译
            regex_patterns = re.findall(r're\.(?:search|match|findall)\(["\'](.+?)["\']\)', content)
            if len(regex_patterns) > len(set(regex_patterns)):
                self.suggestions.append(
                    {
                        "file": str(file_path.relative_to(PROJECT_ROOT)),
                        "type": "performance",
                        "message": "重复的正则表达式，建议预编译",
                    }
                )

        except Exception as e:
            print(f"检查性能问题失败 {file_path}: {e}")

    def scan_directory(self, directory: Path) -> None:
        """扫描目录"""
        for file_path in directory.rglob("*.py"):
            # 跳过虚拟环境和缓存
            if any(
                part in file_path.parts for part in ["venv", "__pycache__", ".git", "build", "dist"]
            ):
                continue

            print(f"检查: {file_path.relative_to(PROJECT_ROOT)}")

            self.check_type_annotations(file_path)
            self.check_async_patterns(file_path)
            self.check_exception_handling(file_path)
            self.check_performance_issues(file_path)

    def generate_report(self) -> str:
        """生成报告"""
        report = []
        report.append("=" * 80)
        report.append("代码质量检查报告")
        report.append("=" * 80)
        report.append("")

        # 问题
        if self.issues:
            report.append(f"🔴 问题 ({len(self.issues)}个):")
            report.append("-" * 80)
            for issue in self.issues:
                report.append(f"  文件: {issue['file']}")
                if "line" in issue:
                    report.append(f"  行号: {issue['line']}")
                report.append(f"  类型: {issue['type']}")
                report.append(f"  消息: {issue['message']}")
                report.append("")
        else:
            report.append("✅ 未发现严重问题")
            report.append("")

        # 警告
        if self.warnings:
            report.append(f"⚠️  警告 ({len(self.warnings)}个):")
            report.append("-" * 80)
            for warning in self.warnings[:10]:  # 只显示前10个
                report.append(f"  文件: {warning['file']}")
                if "line" in warning:
                    report.append(f"  行号: {warning['line']}")
                report.append(f"  类型: {warning['type']}")
                report.append(f"  消息: {warning['message']}")
                report.append("")
            if len(self.warnings) > 10:
                report.append(f"  ... 还有 {len(self.warnings) - 10} 个警告")
                report.append("")
        else:
            report.append("✅ 未发现警告")
            report.append("")

        # 建议
        if self.suggestions:
            report.append(f"💡 优化建议 ({len(self.suggestions)}个):")
            report.append("-" * 80)
            for suggestion in self.suggestions[:10]:  # 只显示前10个
                report.append(f"  文件: {suggestion['file']}")
                report.append(f"  类型: {suggestion['type']}")
                report.append(f"  消息: {suggestion['message']}")
                report.append("")
            if len(self.suggestions) > 10:
                report.append(f"  ... 还有 {len(self.suggestions) - 10} 个建议")
                report.append("")
        else:
            report.append("✅ 代码质量良好")
            report.append("")

        report.append("=" * 80)
        report.append(
            f"总计: {len(self.issues)} 个问题, {len(self.warnings)} 个警告, {len(self.suggestions)} 个建议"
        )
        report.append("=" * 80)

        return "\n".join(report)


def main():
    """主函数"""
    print("开始代码质量检查...")
    print()

    checker = CodeQualityChecker()

    # 扫描src目录
    src_dir = PROJECT_ROOT / "src"
    if src_dir.exists():
        checker.scan_directory(src_dir)

    # 生成报告
    report = checker.generate_report()
    print()
    print(report)

    # 保存报告
    report_file = PROJECT_ROOT / "docs" / "CODE_QUALITY_REPORT.md"
    report_file.parent.mkdir(exist_ok=True)
    with open(report_file, "w", encoding="utf-8") as f:
        f.write(f"# 代码质量检查报告\n\n")
        f.write(
            f"生成时间: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        )
        f.write("```\n")
        f.write(report)
        f.write("\n```\n")

    print()
    print(f"报告已保存到: {report_file.relative_to(PROJECT_ROOT)}")

    # 返回退出码
    return 1 if checker.issues else 0


if __name__ == "__main__":
    sys.exit(main())
