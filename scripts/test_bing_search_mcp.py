"""
测试必应搜索 MCP 服务器
"""

import asyncio
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def test_bing_search_mcp():
    """测试必应搜索 MCP 服务器"""
    print("正在连接必应搜索 MCP 服务器...")

    # 创建服务器参数
    server_params = StdioServerParameters(
        command="cmd",
        args=["/c", "npx", "bing-cn-mcp"],
    )

    print(f"命令: {server_params.command}")
    print(f"参数: {server_params.args}")

    try:
        # 连接到服务器
        print("正在启动 stdio_client...")
        async with stdio_client(server_params) as (read, write):
            print("stdio_client 已启动")

            # 创建会话
            print("正在创建 ClientSession...")
            async with ClientSession(read, write) as session:
                print("ClientSession 已创建")

                # 初始化会话
                print("正在初始化会话...")
                await session.initialize()
                print("会话初始化完成")

                # 列出工具
                print("正在列出工具...")
                tools = await session.list_tools()
                print(f"找到 {len(tools.tools)} 个工具:")
                for tool in tools.tools:
                    print(f"  - {tool.name}: {tool.description}")

                # 调用搜索工具
                if tools.tools:
                    print(f"\n正在调用工具: bing_search")
                    result = await session.call_tool(
                        "bing_search", 
                        arguments={"query": "Python编程", "num_results": 3}
                    )
                    print(f"搜索结果: {result}")

        print("\n✅ 测试成功!")
        return True

    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(test_bing_search_mcp())
    sys.exit(0 if success else 1)

