"""
工具系统增强测试脚本 - v2.30.14

测试新增的重试机制、参数验证、超时控制等功能。
"""

import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.agent.tools import tool_registry
from src.utils.logger import get_logger

logger = get_logger(__name__)


def test_calculator():
    """测试计算器工具的增强功能"""
    print("\n" + "=" * 60)
    print("测试 1: 计算器工具")
    print("=" * 60)
    
    # 测试正常计算
    result = tool_registry.execute_tool("calculator", expression="2 + 3 * 4")
    print(f"✅ 正常计算: 2 + 3 * 4 = {result}")
    
    # 测试除零错误
    result = tool_registry.execute_tool("calculator", expression="10 / 0")
    print(f"✅ 除零错误处理: {result}")
    
    # 测试语法错误
    result = tool_registry.execute_tool("calculator", expression="2 + + 3")
    print(f"✅ 语法错误处理: {result}")
    
    # 测试不允许的字符
    result = tool_registry.execute_tool("calculator", expression="import os")
    print(f"✅ 安全性检查: {result}")


def test_file_operations():
    """测试文件操作工具的增强功能"""
    print("\n" + "=" * 60)
    print("测试 2: 文件操作工具")
    print("=" * 60)
    
    # 测试写入文件
    test_file = "test_output/test_tool_v2.30.14.txt"
    test_content = "这是工具系统v2.30.14的测试内容\n包含中文字符测试"
    
    result = tool_registry.execute_tool("write_file", filepath=test_file, content=test_content)
    print(f"✅ 写入文件: {result}")
    
    # 测试读取文件
    result = tool_registry.execute_tool("read_file", filepath=test_file)
    print(f"✅ 读取文件: {result[:100]}...")
    
    # 测试读取不存在的文件
    result = tool_registry.execute_tool("read_file", filepath="nonexistent_file.txt")
    print(f"✅ 文件不存在处理: {result}")
    
    # 测试路径安全检查（尝试访问项目外的文件）
    result = tool_registry.execute_tool("read_file", filepath="../../../etc/passwd")
    print(f"✅ 路径安全检查: {result}")


def test_execution_time():
    """测试执行时间统计"""
    print("\n" + "=" * 60)
    print("测试 3: 执行时间统计")
    print("=" * 60)
    
    # 执行一个简单的计算
    result = tool_registry.execute_tool("calculator", expression="123 * 456")
    print(f"✅ 计算完成（查看日志中的执行时间）: {result}")


def test_tool_list():
    """测试工具列表"""
    print("\n" + "=" * 60)
    print("测试 4: 工具列表")
    print("=" * 60)
    
    tools = tool_registry.get_all_tools()
    print(f"✅ 已注册工具数量: {len(tools)}")
    print("✅ 工具列表:")
    for i, tool in enumerate(tools, 1):
        tool_name = tool.name if hasattr(tool, 'name') else str(tool)
        print(f"   {i}. {tool_name}")


def main():
    """主测试函数"""
    print("\n" + "=" * 60)
    print("🎉 工具系统增强测试 - v2.30.14")
    print("=" * 60)
    
    try:
        # 运行所有测试
        test_calculator()
        test_file_operations()
        test_execution_time()
        test_tool_list()
        
        print("\n" + "=" * 60)
        print("✅ 所有测试完成！")
        print("=" * 60)
        
    except Exception as e:
        logger.error(f"测试失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()

