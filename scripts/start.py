#!/usr/bin/env python3
"""
MintChat 命令行启动脚本 (跨平台)

版本: v2.8.0
日期: 2025-11-06

这是一个跨平台的命令行启动脚本，可以在 Windows、Linux、Mac 上运行。
推荐使用 uv + .venv（无需手动激活环境）。
提供多个示例程序的交互式菜单。
"""

import os
import sys
import subprocess
from pathlib import Path
from shutil import which

PROJECT_ROOT = Path(__file__).resolve().parent.parent
os.chdir(PROJECT_ROOT)


def print_banner():
    """打印欢迎横幅"""
    print()
    print("=" * 60)
    print("  MintChat v2.8.0 - 多模态猫娘女仆智能体")
    print("=" * 60)
    print()


def check_env():
    """检查是否在虚拟环境中，并给出启动建议"""
    venv = os.environ.get("VIRTUAL_ENV")
    if venv:
        print(f"[信息] 当前虚拟环境: {venv}")
        return

    print("[提示] 未检测到虚拟环境 (VIRTUAL_ENV)")
    print()

    uv_path = which("uv")
    if uv_path:
        print(f"[信息] 已检测到 uv: {uv_path}")
        print("建议使用 uv 启动（会自动使用/创建 .venv）:")
        if sys.platform == "win32":
            print("  uv sync --locked --no-install-project")
            print("  .\\.venv\\Scripts\\python.exe scripts/start.py")
        else:
            print("  uv sync --locked --no-install-project")
            print("  ./.venv/bin/python scripts/start.py")
    else:
        print("[警告] 未检测到 uv")
        print("请先安装 uv，然后使用 uv 启动。")
        print("Windows: pipx install uv")
        print("Linux/macOS: curl -LsSf https://astral.sh/uv/install.sh | sh")
    print()


def check_python_version():
    """检查 Python 版本"""
    version = (
        f"{sys.version_info.major}."
        f"{sys.version_info.minor}."
        f"{sys.version_info.micro}"
    )
    print(f"[信息] Python 版本: {version}")

    if sys.version_info < (3, 13):
        print("[错误] Python 版本过低")
        print(
            f"当前版本: "
            f"{sys.version_info.major}.{sys.version_info.minor}"
        )
        print("需要版本: 3.13+")
        print()
        return False

    print("[成功] Python 版本检查通过")
    return True


def check_config():
    """检查配置文件"""
    config_file = Path("config.yaml")
    example_file = Path("config.yaml.example")

    if not config_file.exists():
        print("[警告] config.yaml 文件不存在")
        print()

        if example_file.exists():
            print("[信息] 正在从示例创建配置文件...")
            import shutil
            shutil.copy(example_file, config_file)
            print("[成功] 配置文件已创建")
            print()
            print("=" * 60)
            print("  重要提示")
            print("=" * 60)
            print()
            print("请编辑 config.yaml 文件并填入您的 API Key")
            print()
            print(f"配置文件位置: {config_file.absolute()}")
            print()
            print("需要配置的项目:")
            print("  1. LLM.key - 您的 API Key")
            print("  2. LLM.api - API 地址（如使用 SiliconFlow）")
            print("  3. LLM.model - 模型名称")
            print()
            print("编辑完成后，请重新运行此脚本")
            print()
            return False
        else:
            print("[错误] 找不到 config.yaml.example 文件")
            print()
            print("请确保在 MintChat 项目根目录下运行此脚本")
            print()
            return False

    print("[成功] 配置文件检查通过")
    return True


def check_dependencies():
    """检查依赖"""
    print("[检查] 正在检查依赖...")

    try:
        import langchain  # noqa: F401
        import langchain_core  # noqa: F401
        import pydantic  # noqa: F401
        import yaml  # noqa: F401
        print("[成功] 依赖检查通过")
        return True
    except ImportError as e:
        print(f"[警告] 依赖未安装或不完整: {e}")
        print()
        print("请使用 uv 同步依赖后重试:")
        print("  uv sync --locked --no-install-project")
        print()
        print("然后使用 .venv 运行:")
        if sys.platform == "win32":
            print("  .\\.venv\\Scripts\\python.exe scripts/start.py")
        else:
            print("  ./.venv/bin/python scripts/start.py")
        print()
        return False


def show_menu():
    """显示菜单"""
    print()
    print("请选择要运行的示例:")
    print()
    print("  [1] 基础对话 (basic_chat.py)")
    print("  [2] 流式对话 (streaming_chat.py)")
    print("  [3] 情感演示 (emotion_demo.py)")
    print("  [4] 多模态演示 (multimodal_demo.py)")
    print("  [5] v2.5 新功能演示 (v25_features_demo.py)")
    print("  [6] 性能演示 (performance_demo.py)")
    print("  [7] 工具使用演示 (tool_usage.py)")
    print("  [8] 高级功能演示 (advanced_features_demo.py)")
    print()
    print("  [0] 退出")
    print()


def run_example(choice):
    """运行示例"""
    examples = {
        "1": "basic_chat.py",
        "2": "streaming_chat.py",
        "3": "emotion_demo.py",
        "4": "multimodal_demo.py",
        "5": "v25_features_demo.py",
        "6": "performance_demo.py",
        "7": "tool_usage.py",
        "8": "advanced_features_demo.py",
    }

    if choice not in examples:
        print("[错误] 无效的选择")
        return False

    example_file = Path("examples") / examples[choice]

    if not example_file.exists():
        print(f"[错误] 找不到示例文件: {example_file}")
        return False

    print()
    print("[启动] 正在启动示例...")
    print("=" * 60)
    print()

    try:
        # 运行示例
        subprocess.run([sys.executable, str(example_file)], check=True)
        return True
    except subprocess.CalledProcessError as e:
        print()
        print(f"[错误] 示例运行失败: {e}")
        return False
    except KeyboardInterrupt:
        print()
        print("[信息] 用户中断")
        return True


def main():
    """主函数"""
    # 打印横幅
    print_banner()

    # 检查环境
    check_env()
    print()

    # 检查 Python 版本
    if not check_python_version():
        print()
        input("按 Enter 键退出...")
        return 1

    print()

    # 检查配置文件
    if not check_config():
        print()
        input("按 Enter 键退出...")
        return 1

    print()

    # 检查依赖
    if not check_dependencies():
        print()
        input("按 Enter 键退出...")
        return 1

    print()

    # 交互式菜单
    while True:
        show_menu()

        try:
            choice = input("请输入选择 [0-8]: ").strip()
        except (KeyboardInterrupt, EOFError):
            print()
            print()
            print("=" * 60)
            print("  MintChat 已退出")
            print("=" * 60)
            print()
            return 0

        if choice == "0":
            print()
            print("=" * 60)
            print("  MintChat 已退出")
            print("=" * 60)
            print()
            return 0

        # 运行示例
        run_example(choice)

        print()
        print("=" * 60)
        print()

        # 询问是否继续
        try:
            continue_choice = input("是否继续运行其他示例? [y/N]: ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            print()
            print()
            print("=" * 60)
            print("  MintChat 已退出")
            print("=" * 60)
            print()
            return 0

        if continue_choice not in ["y", "yes", "是"]:
            print()
            print("=" * 60)
            print("  MintChat 已退出")
            print("=" * 60)
            print()
            return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print()
        print()
        print("=" * 60)
        print("  MintChat 已退出")
        print("=" * 60)
        print()
        sys.exit(0)
