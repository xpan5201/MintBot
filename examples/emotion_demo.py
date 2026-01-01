"""
情感系统演示

展示 MintChat 的情感引擎功能，让猫娘更接近人类。
"""

import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.agent.core import MintChatAgent  # noqa: E402
from src.agent.emotion import EmotionEngine, EmotionType  # noqa: E402
from src.utils.logger import get_logger  # noqa: E402

logger = get_logger(__name__)


def print_emotion_state(agent: MintChatAgent) -> None:
    """
    打印当前情感状态

    Args:
        agent: 智能体实例
    """
    emotion = agent.emotion_engine.current_emotion
    profile = agent.emotion_engine.user_profile

    print("\n" + "=" * 60)
    print("【情感状态】")
    print("=" * 60)
    print(f"当前情感: {emotion.emotion_type.value}")
    print(f"情感强度: {emotion.intensity:.2f}")
    if emotion.trigger:
        print(f"触发原因: {emotion.trigger}")
    print(f"\n关系描述: {agent.emotion_engine.get_relationship_description()}")
    print(f"亲密度: {profile.relationship_level:.2f}")
    print(f"正面互动: {profile.positive_interactions} 次")
    print(f"负面互动: {profile.negative_interactions} 次")
    print(f"情感修饰符: {agent.emotion_engine.get_emotion_modifier()}")
    print("=" * 60 + "\n")


def test_emotion_analysis():
    """测试情感分析功能"""
    print("=" * 60)
    print("情感分析测试")
    print("=" * 60)
    print()

    engine = EmotionEngine()

    test_messages = [
        ("我今天好开心啊！", EmotionType.HAPPY),
        ("有点难过...", EmotionType.SAD),
        ("太棒了！这真是太好了！", EmotionType.EXCITED),
        ("我有点担心明天的考试", EmotionType.WORRIED),
        ("这是什么意思？我不太懂", EmotionType.CONFUSED),
        ("我们一起玩游戏吧！", EmotionType.PLAYFUL),
        ("我很喜欢你", EmotionType.AFFECTIONATE),
        ("为什么会这样呢？", EmotionType.CURIOUS),
    ]

    for message, expected_emotion in test_messages:
        detected = engine.analyze_message(message)
        match = "✓" if detected == expected_emotion else "✗"
        print(
            f"{match} 消息: '{message}' -> "
            f"检测到: {detected.value} "
            f"(期望: {expected_emotion.value})"
        )

    print()


def test_emotion_conversation():
    """测试情感对话"""
    print("=" * 60)
    print("情感对话测试")
    print("=" * 60)
    print()

    # 创建智能体
    agent = MintChatAgent()

    # 不同情感的对话场景
    scenarios = [
        {
            "title": "开心场景",
            "messages": [
                "我今天考试得了满分！",
                "真的很开心！",
            ],
        },
        {
            "title": "难过场景",
            "messages": [
                "我今天心情不太好...",
                "感觉有点失落",
            ],
        },
        {
            "title": "好奇场景",
            "messages": [
                "你是怎么工作的呢？",
                "为什么你能理解我说的话？",
            ],
        },
        {
            "title": "俏皮场景",
            "messages": [
                "我们来玩个游戏吧！",
                "猜猜我在想什么？",
            ],
        },
    ]

    for scenario in scenarios:
        print(f"\n--- {scenario['title']} ---")
        for message in scenario["messages"]:
            print(f"\n主人: {message}")

            # 发送消息
            reply = agent.chat(message)
            print(f"{agent.character.name}: {reply}")

            # 显示情感变化
            emotion = agent.emotion_engine.current_emotion
            print(f"[情感变化] {emotion.emotion_type.value} " f"(强度: {emotion.intensity:.2f})")

        # 显示场景结束后的情感状态
        print_emotion_state(agent)


def test_relationship_building():
    """测试关系建立"""
    print("=" * 60)
    print("关系建立测试")
    print("=" * 60)
    print()

    agent = MintChatAgent()

    print("初始状态:")
    print_emotion_state(agent)

    # 模拟多次正面互动
    print("进行 10 次正面互动...")
    for i in range(10):
        agent.emotion_engine.update_user_profile(
            interaction_positive=True,
            memorable_moment=f"美好时刻 {i + 1}" if i % 3 == 0 else None,
        )

    print("10 次正面互动后:")
    print_emotion_state(agent)

    # 模拟一些负面互动
    print("进行 3 次负面互动...")
    for i in range(3):
        agent.emotion_engine.update_user_profile(interaction_positive=False)

    print("3 次负面互动后:")
    print_emotion_state(agent)

    # 显示难忘时刻
    moments = agent.emotion_engine.user_profile.memorable_moments
    if moments:
        print("\n难忘时刻:")
        for i, moment in enumerate(moments, 1):
            print(f"  {i}. {moment}")
        print()


def test_emotion_decay():
    """测试情感衰减"""
    print("=" * 60)
    print("情感衰减测试")
    print("=" * 60)
    print()

    engine = EmotionEngine()

    # 设置一个强烈的情感
    engine.update_emotion(EmotionType.EXCITED, intensity=1.0, trigger="测试")
    print(f"初始情感: {engine.current_emotion}")

    # 模拟多次衰减
    print("\n情感衰减过程:")
    for i in range(10):
        engine.decay_emotion()
        print(
            f"  第 {i + 1} 次衰减: {engine.current_emotion.emotion_type.value} "
            f"(强度: {engine.current_emotion.intensity:.2f})"
        )

    print()


def main():
    """主函数"""
    print("\n" + "=" * 60)
    print("MintChat 情感系统演示")
    print("=" * 60)
    print()

    # 运行各项测试
    test_emotion_analysis()
    input("按 Enter 继续...")

    test_emotion_conversation()
    input("按 Enter 继续...")

    test_relationship_building()
    input("按 Enter 继续...")

    test_emotion_decay()

    print("\n演示完成！")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n程序被用户中断")
    except Exception as e:
        logger.error(f"程序运行出错: {e}", exc_info=True)
        print(f"\n错误: {e}")
