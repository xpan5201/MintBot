"""
流式对话示例

展示 MintChat 的流式输出功能，提供更好的用户体验。
"""

import sys
import time
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.agent.core import MintChatAgent  # noqa: E402
from src.utils.logger import get_logger  # noqa: E402

logger = get_logger(__name__)


def print_typing_effect(text: str, delay: float = 0.03) -> None:
    """
    打字机效果打印

    Args:
        text: 要打印的文本
        delay: 每个字符的延迟时间（秒）
    """
    for char in text:
        print(char, end="", flush=True)
        time.sleep(delay)
    print()  # 换行


def main():
    """主函数"""
    print("=" * 60)
    print("MintChat 流式对话示例")
    print("=" * 60)
    print()

    # 创建智能体（启用流式输出）
    print("正在初始化智能体...")
    agent = MintChatAgent(enable_streaming=True)
    print("✓ 智能体初始化完成！\n")

    # 显示问候语
    greeting = agent.get_greeting()
    print(f"{agent.character.name}: ", end="")
    print_typing_effect(greeting)
    print()

    # 对话示例
    test_messages = [
        "你好呀，小喵！",
        "今天天气真好！",
        "能帮我计算一下 123 + 456 吗？",
        "你现在心情怎么样？",
    ]

    for i, message in enumerate(test_messages, 1):
        print(f"\n--- 对话 {i} ---")
        print(f"主人: {message}")
        print(f"{agent.character.name}: ", end="", flush=True)

        # 使用流式输出
        for chunk in agent.chat_stream(message):
            print(chunk, end="", flush=True)
            time.sleep(0.03)  # 模拟打字效果
        print()  # 换行

        # 显示当前情感状态
        emotion_status = agent.get_emotion_status()
        print(f"\n[情感状态] {emotion_status}")

    # 显示统计信息
    print("\n" + "=" * 60)
    print("对话统计")
    print("=" * 60)
    stats = agent.get_stats()
    print(f"角色名称: {stats['character_name']}")
    print(f"模型: {stats['model_name']}")
    print(f"流式输出: {'启用' if stats['streaming_enabled'] else '禁用'}")
    print(f"工具数量: {stats['tools_count']}")
    print(f"对话轮数: {stats['recent_messages_count'] // 2}")

    emotion_stats = stats["emotion_stats"]
    print("\n情感统计:")
    print(f"  当前情感: {emotion_stats['current_emotion']}")
    print(f"  亲密度: {emotion_stats['relationship_level']:.2f}")
    print(f"  正面互动: {emotion_stats['positive_interactions']}")
    print(f"  情感历史记录: {emotion_stats['emotion_history_count']}")

    # 告别
    print()
    farewell = agent.get_farewell()
    print(f"{agent.character.name}: ", end="")
    print_typing_effect(farewell)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n程序被用户中断")
    except Exception as e:
        logger.error(f"程序运行出错: {e}", exc_info=True)
        print(f"\n错误: {e}")
