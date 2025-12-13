#!/usr/bin/env python3
"""
内存泄漏检测脚本 (v2.29.1)

定期检查GUI对象的生命周期，检测潜在的内存泄漏。
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer
from src.utils.gui_optimizer import check_memory_leaks
from src.utils.logger import get_logger

logger = get_logger(__name__)


def main():
    """主函数"""
    print("=" * 60)
    print("MintChat 内存泄漏检测工具 (v2.29.1)")
    print("=" * 60)
    print()

    # 创建QApplication（如果需要）
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)

    print("✅ 应用程序已初始化")
    print("⏳ 开始检测内存泄漏...")
    print()

    # 检查内存泄漏
    leaks = check_memory_leaks()

    if leaks:
        print(f"❌ 检测到 {len(leaks)} 个潜在内存泄漏:")
        print()
        for i, leak in enumerate(leaks, 1):
            print(f"{i}. {leak['name']} ({leak['type']})")
            print(f"   生命周期: {leak['lifetime']:.2f}秒")
            print()

        print("💡 建议:")
        print("  1. 检查这些对象是否正确释放")
        print("  2. 确保在不需要时调用 deleteLater()")
        print("  3. 检查信号连接是否正确断开")
        print()
        return 1
    else:
        print("✅ 未检测到内存泄漏")
        print()
        return 0


if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except Exception as e:
        print(f"❌ 检测失败: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
