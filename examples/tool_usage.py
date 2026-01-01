"""
工具使用示例

演示智能体如何使用各种工具。
"""

import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.agent.core import MintChatAgent  # noqa: E402
from src.agent.tools import tool_registry  # noqa: E402
from src.utils.logger import get_logger  # noqa: E402

logger = get_logger(__name__)


def demo_tool_registry():
    """演示工具注册表功能"""
    print("=" * 60)
    print("工具注册表演示")
    print("=" * 60)
    print()

    # 显示所有工具
    print("已注册的工具:")
    tools = tool_registry.get_tools_description()
    for i, tool in enumerate(tools, 1):
        print(f"{i}. {tool['name']}")
        print(f"   描述: {tool['description'].strip()}")
        print()

    # 测试单个工具
    print("-" * 60)
    print("测试工具执行:")
    print()

    # 测试时间工具
    print("1. 获取当前时间:")
    result = tool_registry.execute_tool("get_current_time")
    print(f"   {result}")
    print()

    # 测试日期工具
    print("2. 获取当前日期:")
    result = tool_registry.execute_tool("get_current_date")
    print(f"   {result}")
    print()

    # 测试计算器
    print("3. 计算器:")
    result = tool_registry.execute_tool("calculator", expression="2 + 3 * 4")
    print(f"   {result}")
    print()

    # 测试天气查询
    print("4. 天气查询:")
    result = tool_registry.execute_tool("get_weather", city="北京")
    print(f"   {result}")
    print()


def demo_agent_with_tools():
    """演示智能体使用工具"""
    print("=" * 60)
    print("智能体工具使用演示")
    print("=" * 60)
    print()

    try:
        # 创建智能体
        agent = MintChatAgent()
        print("智能体已创建")
        print()

        # 测试问题列表
        test_questions = [
            "现在几点了？",
            "今天是几号？星期几？",
            "帮我算一下 15 * 23 等于多少",
            "北京今天天气怎么样？",
            "提醒我明天下午3点开会",
        ]

        print("测试问题:")
        for i, question in enumerate(test_questions, 1):
            print(f"\n{i}. 主人: {question}")
            try:
                response = agent.chat(question)
                print(f"   小喵: {response}")
            except Exception as e:
                print(f"   错误: {e}")
                logger.error(f"处理问题失败: {e}")

    except Exception as e:
        print(f"错误: {e}")
        logger.error(f"智能体工具使用演示失败: {e}")


def main():
    """主函数"""
    # 演示工具注册表
    demo_tool_registry()

    print("\n" + "=" * 60)
    print()

    # 演示智能体使用工具
    demo_agent_with_tools()


if __name__ == "__main__":
    main()
