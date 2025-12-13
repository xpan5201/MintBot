#!/usr/bin/env python3
"""
MintChat 快速启动脚本

版本: v2.8.0
日期: 2025-11-06

这是一个简化的启动脚本，直接启动基础对话，无需交互式菜单。
"""

import sys
from pathlib import Path


def main():
    """主函数"""
    print()
    print("=" * 60)
    print("  MintChat v2.8.0 - 多模态猫娘女仆智能体 (快速启动)")
    print("=" * 60)
    print()
    
    # 检查 Python 版本
    if sys.version_info < (3, 12):
        print("[错误] Python 版本过低")
        print(f"当前版本: {sys.version_info.major}.{sys.version_info.minor}")
        print("需要版本: 3.12+")
        print()
        return 1
    
    # 检查配置文件
    config_file = Path("config.yaml")
    if not config_file.exists():
        print("[错误] config.yaml 文件不存在")
        print()
        print("请先运行以下命令创建配置文件:")
        print("  python start.py")
        print()
        print("或手动复制:")
        print("  cp config.yaml.example config.yaml")
        print()
        return 1
    
    # 检查依赖
    try:
        import langchain
    except ImportError:
        print("[错误] 依赖未安装")
        print()
        print("请运行以下命令安装依赖:")
        print("  pip install -r requirements.txt")
        print()
        return 1
    
    # 启动基础对话
    print("[启动] 正在启动 MintChat...")
    print()
    print("=" * 60)
    print()
    
    try:
        # 导入并运行
        sys.path.insert(0, str(Path(__file__).parent))
        from examples.basic_chat import main as chat_main
        chat_main()
        return 0
    except Exception as e:
        print()
        print(f"[错误] 启动失败: {e}")
        # 使用统一异常处理
        try:
            from src.utils.exceptions import handle_exception
            from src.utils.logger import get_logger
            logger = get_logger(__name__)
            handle_exception(e, logger, "启动失败")
        except:
            # 如果导入失败，使用基本错误输出
            import traceback
            traceback.print_exc()
        return 1


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

