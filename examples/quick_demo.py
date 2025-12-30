"""
快速演示 - MintChat v2.0 新功能

展示情感系统、流式输出、上下文感知等核心功能。
"""

import sys
import time
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.agent.core import MintChatAgent
from src.utils.logger import get_logger

logger = get_logger(__name__)


def print_section(title: str) -> None:
    """打印章节标题"""
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60 + "\n")


def print_typing(text: str, delay: float = 0.03) -> None:
    """打字机效果"""
    for char in text:
        print(char, end="", flush=True)
        time.sleep(delay)
    print()


def demo_emotion_system():
    """演示情感系统"""
    print_section("1. 情感系统演示 💖")

    agent = MintChatAgent()

    scenarios = [
        ("开心场景", "我今天考试得了满分！太开心了！"),
        ("难过场景", "我今天心情不太好..."),
        ("好奇场景", "你是怎么工作的呢？"),
        ("俏皮场景", "我们来玩个游戏吧！"),
    ]

    for title, message in scenarios:
        print(f"\n【{title}】")
        print(f"主人: {message}")

        # 发送消息
        response = agent.chat(message)
        print(f"{agent.character.name}: ", end="")
        print_typing(response, delay=0.02)

        # 显示情感状态
        emotion = agent.emotion_engine.current_emotion
        print(f"\n💭 情感变化: {emotion.emotion_type.value} " f"(强度: {emotion.intensity:.2f})")
        time.sleep(1)


def demo_streaming_output():
    """演示流式输出"""
    print_section("2. 流式输出演示 ⚡")

    agent = MintChatAgent(enable_streaming=True)

    messages = [
        "你好呀，小喵！",
        "能给我讲个故事吗？",
    ]

    for message in messages:
        print(f"\n主人: {message}")
        print(f"{agent.character.name}: ", end="", flush=True)

        # 流式输出
        for chunk in agent.chat_stream(message):
            print(chunk, end="", flush=True)
            time.sleep(0.03)  # 模拟打字效果
        print()
        time.sleep(1)


def demo_relationship_building():
    """演示关系建立"""
    print_section("3. 关系建立演示 🤝")

    agent = MintChatAgent()

    print("初始状态:")
    print(agent.get_emotion_status())
    print()

    # 进行多次互动
    interactions = [
        "你好呀！",
        "你真可爱！",
        "我很喜欢和你聊天",
        "你是最好的猫娘女仆！",
        "谢谢你一直陪伴我",
    ]

    print("进行 5 次正面互动...\n")
    for i, message in enumerate(interactions, 1):
        print(f"互动 {i}: {message}")
        response = agent.chat(message)
        print(f"回复: {response[:50]}...")

        # 显示亲密度变化
        level = agent.emotion_engine.user_profile.relationship_level
        print(f"亲密度: {level:.2f}\n")
        time.sleep(0.5)

    print("\n最终状态:")
    print(agent.get_emotion_status())


def demo_context_awareness():
    """演示上下文感知"""
    print_section("4. 上下文感知演示 🎯")

    agent = MintChatAgent()

    print("进行一段连续对话，观察上下文理解...\n")

    conversation = [
        "我今天去了公园",
        "那里的花开得很漂亮",
        "我拍了很多照片",
        "你想看吗？",
    ]

    for message in conversation:
        print(f"主人: {message}")
        response = agent.chat(message, save_to_long_term=True)
        print(f"{agent.character.name}: {response}\n")
        time.sleep(1)

    # 测试记忆检索
    print("--- 测试记忆检索 ---")
    print("主人: 我刚才说去了哪里？")
    response = agent.chat("我刚才说去了哪里？")
    print(f"{agent.character.name}: {response}")


def demo_statistics():
    """演示统计信息"""
    print_section("5. 统计信息展示 📊")

    agent = MintChatAgent()

    # 进行一些对话
    for msg in ["你好", "今天天气不错", "我很开心"]:
        agent.chat(msg)

    stats = agent.get_stats()

    print("智能体统计:")
    print(f"  角色名称: {stats['character_name']}")
    print(f"  使用模型: {stats['model_name']}")
    print(f"  流式输出: {'启用' if stats['streaming_enabled'] else '禁用'}")
    print(f"  工具数量: {stats['tools_count']}")
    print(f"  对话轮数: {stats['recent_messages_count'] // 2}")

    emotion_stats = stats["emotion_stats"]
    print("\n情感统计:")
    print(f"  当前情感: {emotion_stats['current_emotion']}")
    print(f"  亲密度: {emotion_stats['relationship_level']:.2f}")
    print(f"  正面互动: {emotion_stats['positive_interactions']}")
    print(f"  情感历史: {emotion_stats['emotion_history_count']} 条记录")


def main():
    """主函数"""
    print("\n" + "=" * 60)
    print("  MintChat v2.0 快速演示")
    print("  展示情感系统、流式输出、上下文感知等新功能")
    print("=" * 60)

    try:
        # 1. 情感系统
        demo_emotion_system()
        input("\n按 Enter 继续下一个演示...")

        # 2. 流式输出
        demo_streaming_output()
        input("\n按 Enter 继续下一个演示...")

        # 3. 关系建立
        demo_relationship_building()
        input("\n按 Enter 继续下一个演示...")

        # 4. 上下文感知
        demo_context_awareness()
        input("\n按 Enter 继续下一个演示...")

        # 5. 统计信息
        demo_statistics()

        print("\n" + "=" * 60)
        print("  演示完成！")
        print("=" * 60)
        print("\n✨ MintChat v2.0 核心特性:")
        print("  1. 💖 情感系统 - 12 种情感类型，真实的情感反应")
        print("  2. ⚡ 流式输出 - 打字机效果，降低 60%+ 首字延迟")
        print("  3. 🤝 关系系统 - 亲密度追踪，记录难忘时刻")
        print("  4. 🎯 上下文感知 - 情感 + 记忆 + 关系多维度融合")
        print("  5. 📊 完整统计 - 实时监控各项指标")
        print("\n🎉 致力于打造最接近人类的多模态猫娘女仆智能体！")
        print()

    except KeyboardInterrupt:
        print("\n\n演示被用户中断")
    except Exception as e:
        logger.error(f"演示运行出错: {e}", exc_info=True)
        print(f"\n错误: {e}")


if __name__ == "__main__":
    main()
