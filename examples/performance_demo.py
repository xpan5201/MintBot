"""
性能监控和角色配置演示

展示 v2.4 新增的性能监控系统和角色配置整合功能。
"""

import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.agent.core import MintChatAgent  # noqa: E402
from src.character.config_loader import CharacterConfigLoader  # noqa: E402
from src.utils.performance import BatchProcessor, monitor_performance  # noqa: E402


def demo_character_config():
    """演示角色配置加载"""
    print("\n" + "=" * 60)
    print("角色配置演示")
    print("=" * 60)

    # 打印配置摘要
    CharacterConfigLoader.print_config_summary()

    # 获取角色配置
    config = CharacterConfigLoader.load_character_settings()
    print(f"\n角色名称: {config['name']}")
    print(f"主人名称: {config['user_name']}")

    # 生成系统提示词
    prompt = CharacterConfigLoader.generate_system_prompt()
    print("\n生成的系统提示词 (前 200 字符):")
    print(prompt[:200] + "...")

    # 获取问候语
    greeting = CharacterConfigLoader.get_greeting()
    print(f"\n问候语: {greeting}")

    # 验证配置
    validation = CharacterConfigLoader.validate_config()
    print(f"\n配置验证: {'✓ 通过' if validation['is_valid'] else '✗ 失败'}")


def demo_performance_monitoring():
    """演示性能监控"""
    print("\n" + "=" * 60)
    print("性能监控演示")
    print("=" * 60)

    # 创建 Agent
    print("\n创建 Agent...")
    agent = MintChatAgent()

    # 进行一些对话
    print("\n进行对话测试...")
    messages = [
        "你好！",
        "今天天气怎么样？",
        "帮我设置一个提醒",
        "你最喜欢什么？",
        "谢谢你！",
    ]

    for i, msg in enumerate(messages, 1):
        print(f"\n[{i}/{len(messages)}] 用户: {msg}")
        response = agent.chat(msg)
        print(f"猫娘: {response[:100]}...")

    # 查看性能统计
    print("\n" + "-" * 60)
    print("性能统计")
    print("-" * 60)

    stats = agent.get_performance_stats()

    # 打印总体统计
    summary = stats.get("_summary", {})
    print(f"\n运行时间: {summary.get('uptime_seconds', 0):.2f} 秒")
    print(f"总操作数: {summary.get('total_operations', 0)}")
    print(f"总错误数: {summary.get('total_errors', 0)}")
    print(f"错误率: {summary.get('error_rate', 0):.2%}")

    # 打印 chat 操作统计
    if "chat" in stats:
        chat_stats = stats["chat"]
        print("\nchat 操作统计:")
        print(f"  调用次数: {chat_stats['count']}")
        print(f"  平均耗时: {chat_stats['avg']:.4f} 秒")
        print(f"  最小耗时: {chat_stats['min']:.4f} 秒")
        print(f"  最大耗时: {chat_stats['max']:.4f} 秒")
        print(f"  总耗时: {chat_stats['total']:.4f} 秒")

    # 打印完整的性能报告
    print("\n" + "=" * 60)
    print("完整性能报告")
    print("=" * 60)
    agent.print_performance_stats()


@monitor_performance("custom_function")
def custom_function(n: int) -> int:
    """自定义函数，演示性能监控装饰器"""
    import time

    time.sleep(0.1)  # 模拟耗时操作
    return n * 2


def demo_performance_decorator():
    """演示性能监控装饰器"""
    print("\n" + "=" * 60)
    print("性能监控装饰器演示")
    print("=" * 60)

    from src.utils.performance import performance_monitor

    # 重置统计
    performance_monitor.reset()

    # 调用自定义函数
    print("\n调用自定义函数 10 次...")
    for i in range(10):
        result = custom_function(i)
        print(f"  custom_function({i}) = {result}")

    # 查看统计
    stats = performance_monitor.get_stats("custom_function")
    print("\ncustom_function 统计:")
    print(f"  调用次数: {stats['count']}")
    print(f"  平均耗时: {stats['avg']:.4f} 秒")
    print(f"  最小耗时: {stats['min']:.4f} 秒")
    print(f"  最大耗时: {stats['max']:.4f} 秒")


def demo_batch_processing():
    """演示批处理"""
    print("\n" + "=" * 60)
    print("批处理演示")
    print("=" * 60)

    # 准备数据
    items = list(range(1, 21))  # 1-20

    def process_item(item: int) -> int:
        """处理单个数据项"""
        import time

        time.sleep(0.05)  # 模拟耗时操作
        return item * 2

    # 批量处理
    print(f"\n批量处理 {len(items)} 个数据项...")
    results = BatchProcessor.batch_process(
        items=items, process_func=process_item, batch_size=5, show_progress=True
    )

    print(f"\n处理结果 (前 10 个): {results[:10]}")
    print(f"总共处理: {len(results)} 个数据项")


def demo_integrated_features():
    """演示集成功能"""
    print("\n" + "=" * 60)
    print("集成功能演示")
    print("=" * 60)

    # 创建 Agent（使用配置文件中的角色设定）
    print("\n创建 Agent（使用配置文件中的角色设定）...")
    agent = MintChatAgent()

    # 查看角色信息
    stats = agent.get_stats()
    print(f"\n角色名称: {stats['character_name']}")
    print(f"使用模型: {stats['model_name']}")
    print(f"可用工具: {', '.join(stats['tool_names'])}")

    # 进行对话
    print("\n进行对话...")
    response = agent.chat("你好，介绍一下你自己吧！")
    print(f"\n猫娘: {response}")

    # 查看情绪状态
    print(f"\n{agent.get_mood_status()}")

    # 查看性能统计
    print("\n性能统计:")
    stats = agent.get_performance_stats()
    if "chat" in stats:
        print(f"  chat 平均耗时: {stats['chat']['avg']:.4f} 秒")


def main():
    """主函数"""
    print("\n" + "=" * 60)
    print("MintChat v2.4 性能监控和角色配置演示")
    print("=" * 60)

    try:
        # 1. 角色配置演示
        demo_character_config()

        # 2. 性能监控演示
        demo_performance_monitoring()

        # 3. 性能监控装饰器演示
        demo_performance_decorator()

        # 4. 批处理演示
        demo_batch_processing()

        # 5. 集成功能演示
        demo_integrated_features()

        print("\n" + "=" * 60)
        print("演示完成！")
        print("=" * 60)

    except Exception as e:
        print(f"\n错误: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
