"""
MCP 集成测试脚本 - v2.30.15

测试 MCP (Model Context Protocol) 系统集成是否正常工作。
"""

import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.agent.mcp_manager import mcp_manager
from src.agent.tools import tool_registry
from src.utils.logger import logger


def test_mcp_manager():
    """测试 MCP 管理器"""
    print("\n" + "=" * 60)
    print("测试 1: MCP 管理器初始化")
    print("=" * 60)

    try:
        # MCP 管理器应该已经在 tool_registry 初始化时被初始化
        print(f"✅ MCP 管理器已初始化: {mcp_manager._initialized}")
        print(f"✅ MCP 会话数量: {len(mcp_manager.sessions)}")
        print(f"✅ MCP 工具数量: {len(mcp_manager.tools)}")

        # 列出所有 MCP 工具
        if mcp_manager.tools:
            print("\n已注册的 MCP 工具:")
            for tool in mcp_manager.tools:
                tool_name = getattr(tool, "name", "未知")
                tool_desc = getattr(tool, "description", "无描述")
                print(f"  - {tool_name}: {tool_desc}")
        else:
            print("\n⚠️  未找到 MCP 工具（可能 MCP 服务器未启用或连接失败）")

        return True

    except Exception as e:
        print(f"❌ MCP 管理器测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_tool_registry():
    """测试工具注册表"""
    print("\n" + "=" * 60)
    print("测试 2: 工具注册表集成")
    print("=" * 60)

    try:
        # 获取所有工具
        all_tools = tool_registry.get_all_tools()
        print(f"✅ 工具注册表总工具数: {len(all_tools)}")

        # 获取工具名称
        tool_names = tool_registry.get_tool_names()
        print(f"✅ 默认工具数量: {len(tool_names)}")
        print(f"✅ MCP 工具数量: {len(tool_registry._mcp_tools)}")

        # 列出所有工具
        print("\n所有工具:")
        print("  默认工具:")
        for name in tool_names:
            print(f"    - {name}")

        if tool_registry._mcp_tools:
            print("  MCP 工具:")
            for tool in tool_registry._mcp_tools:
                tool_name = getattr(tool, "name", "未知")
                print(f"    - {tool_name}")

        return True

    except Exception as e:
        print(f"❌ 工具注册表测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_mcp_tool_execution():
    """测试 MCP 工具执行"""
    print("\n" + "=" * 60)
    print("测试 3: MCP 工具执行")
    print("=" * 60)

    if not mcp_manager.tools:
        print("⚠️  跳过工具执行测试（无可用 MCP 工具）")
        return True

    try:
        # 尝试执行时间 MCP 工具
        time_tool = None
        for tool in mcp_manager.tools:
            tool_name = getattr(tool, "name", "")
            if "time" in tool_name.lower() and "get_current_time" in tool_name.lower():
                time_tool = tool
                break

        if time_tool:
            print(f"找到时间工具: {time_tool.name}")
            print("正在执行工具...")

            # 执行工具（传入时区参数）
            result = time_tool.invoke({"timezone": "Asia/Shanghai"})
            print(f"✅ 工具执行成功!")
            print(f"结果: {result}")
            return True
        else:
            print("⚠️  未找到时间工具，跳过执行测试")
            return True

    except Exception as e:
        print(f"❌ MCP 工具执行失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """主测试函数"""
    print("\n" + "=" * 60)
    print("MCP 集成测试 - v2.30.15")
    print("=" * 60)

    results = []

    # 测试 1: MCP 管理器
    results.append(("MCP 管理器", test_mcp_manager()))

    # 测试 2: 工具注册表
    results.append(("工具注册表", test_tool_registry()))

    # 测试 3: MCP 工具执行
    results.append(("MCP 工具执行", test_mcp_tool_execution()))

    # 总结
    print("\n" + "=" * 60)
    print("测试总结")
    print("=" * 60)

    for test_name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{test_name}: {status}")

    all_passed = all(result for _, result in results)
    print("\n" + "=" * 60)
    if all_passed:
        print("✅ 所有测试通过!")
    else:
        print("❌ 部分测试失败")
    print("=" * 60)

    return all_passed


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

