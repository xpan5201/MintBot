"""
异步流式对话示例

展示 MintChat 的异步流式输出功能，提供更高性能的用户体验。
"""

import asyncio
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.agent.core import MintChatAgent
from src.utils.logger import get_logger

logger = get_logger(__name__)


async def async_print_with_delay(text: str, delay: float = 0.03) -> None:
    """
    异步打字机效果

    Args:
        text: 要打印的文本
        delay: 每个字符的延迟时间（秒）
    """
    for char in text:
        print(char, end="", flush=True)
        await asyncio.sleep(delay)
    print()


async def chat_async(agent: MintChatAgent, message: str) -> None:
    """
    异步对话

    Args:
        agent: 智能体实例
        message: 用户消息
    """
    print(f"主人: {message}")
    print(f"{agent.character.name}: ", end="", flush=True)

    # 使用异步流式输出
    async for chunk in agent.chat_stream_async(message):
        print(chunk, end="", flush=True)
        await asyncio.sleep(0.02)  # 模拟打字效果
    print()  # 换行


async def main():
    """主函数"""
    print("=" * 60)
    print("MintChat 异步流式对话示例")
    print("=" * 60)
    print()

    # 创建智能体
    print("正在初始化智能体...")
    agent = MintChatAgent(enable_streaming=True)
    print("✓ 智能体初始化完成！\n")

    # 显示问候语
    greeting = agent.get_greeting()
    print(f"{agent.character.name}: ", end="")
    await async_print_with_delay(greeting)
    print()

    # 并发处理多个对话（展示异步优势）
    print("--- 演示异步并发处理 ---\n")

    messages = [
        "你好呀！",
        "今天天气怎么样？",
        "能帮我算一下 100 + 200 吗？",
    ]

    # 顺序处理
    print("【顺序处理】")
    import time

    start_time = time.time()
    for msg in messages:
        await chat_async(agent, msg)
        print()
    sequential_time = time.time() - start_time

    print(f"顺序处理耗时: {sequential_time:.2f} 秒\n")

    # 显示情感状态
    print("=" * 60)
    print("当前状态")
    print("=" * 60)
    emotion_status = agent.get_emotion_status()
    print(emotion_status)
    print()

    # 显示统计信息
    stats = agent.get_stats()
    print(f"对话轮数: {stats['recent_messages_count'] // 2}")
    print(f"亲密度: {stats['emotion_stats']['relationship_level']:.2f}")

    # 告别
    print()
    farewell = agent.get_farewell()
    print(f"{agent.character.name}: ", end="")
    await async_print_with_delay(farewell)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n程序被用户中断")
    except Exception as e:
        logger.error(f"程序运行出错: {e}", exc_info=True)
        print(f"\n错误: {e}")
