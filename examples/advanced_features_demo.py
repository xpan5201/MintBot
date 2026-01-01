"""
高级功能演示

演示 v2.3 新增的高级功能：
- 核心记忆
- 高级情绪系统
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.agent.core import MintChatAgent  # noqa: E402
from src.utils.logger import get_logger  # noqa: E402

logger = get_logger(__name__)


def demo_core_memory():
    """演示核心记忆功能"""
    print("\n" + "=" * 60)
    print("【核心记忆演示】")
    print("=" * 60)

    agent = MintChatAgent()

    # 添加核心记忆
    print("\n1. 添加核心记忆...")
    agent.add_core_memory("主人最喜欢吃草莓蛋糕", category="preferences", importance=0.9)
    agent.add_core_memory("主人的生日是3月15日", category="personal_info", importance=1.0)
    agent.add_core_memory("主人每天晚上10点睡觉", category="habits", importance=0.7)

    # 测试核心记忆检索
    print("\n2. 测试核心记忆检索...")
    response = agent.chat("我喜欢吃什么？")
    print("\n主人: 我喜欢吃什么？")
    print(f"{agent.character.name}: {response}")

    response = agent.chat("我的生日是什么时候？")
    print("\n主人: 我的生日是什么时候？")
    print(f"{agent.character.name}: {response}")


def demo_mood_system():
    """演示高级情绪系统"""
    print("\n" + "=" * 60)
    print("【高级情绪系统演示】")
    print("=" * 60)

    agent = MintChatAgent()

    # 检查情绪系统状态
    print(f"\n初始情绪状态: {agent.get_mood_status()}")

    # 正面互动
    print("\n1. 正面互动...")
    positive_messages = [
        "你今天真可爱！",
        "谢谢你一直陪伴我",
        "你是最好的女仆！",
    ]

    for msg in positive_messages:
        print(f"\n主人: {msg}")
        response = agent.chat(msg)
        print(f"{agent.character.name}: {response}")
        print(f"情绪状态: {agent.get_mood_status()}")

    # 负面互动
    print("\n2. 负面互动...")
    negative_messages = [
        "我今天心情不好",
        "工作太累了",
    ]

    for msg in negative_messages:
        print(f"\n主人: {msg}")
        response = agent.chat(msg)
        print(f"{agent.character.name}: {response}")
        print(f"情绪状态: {agent.get_mood_status()}")


def demo_integrated_features():
    """演示综合功能"""
    print("\n" + "=" * 60)
    print("【综合功能演示】")
    print("=" * 60)

    agent = MintChatAgent()

    # 设置背景记忆
    print("\n1. 设置背景记忆...")
    agent.add_core_memory(
        "主人是一名程序员，喜欢编程和阅读", category="personal_info", importance=0.9
    )

    # 进行对话
    print("\n2. 进行对话...")
    conversations = [
        "今天写了一整天的Python代码",
        "终于解决了那个bug，好开心！",
        "你知道Python吗？",
        "我昨天做了什么？",
    ]

    for msg in conversations:
        print(f"\n主人: {msg}")
        response = agent.chat(msg)
        print(f"{agent.character.name}: {response}")

    # 显示统计信息
    print("\n3. 统计信息...")
    stats = agent.get_stats()
    print(f"\n角色名称: {stats['character_name']}")
    print(f"模型: {stats['model_name']}")
    print(f"情感状态: {agent.get_emotion_status()}")
    print(f"情绪状态: {agent.get_mood_status()}")
    print("\n高级记忆系统:")
    print(
        f"  - 核心记忆: {'启用' if stats['advanced_memory']['core_memory_enabled'] else '未启用'}"
    )


def main():
    """主函数"""
    print("\n" + "=" * 60)
    print("MintChat v2.3 高级功能演示")
    print("=" * 60)

    demos = {
        "1": ("核心记忆", demo_core_memory),
        "2": ("高级情绪系统", demo_mood_system),
        "3": ("综合功能", demo_integrated_features),
        "0": ("全部演示", None),
    }

    print("\n请选择要演示的功能：")
    for key, (name, _) in demos.items():
        print(f"  {key}. {name}")

    choice = input("\n请输入选项 (默认: 0): ").strip() or "0"

    if choice == "0":
        # 运行所有演示
        for key, (name, func) in demos.items():
            if key != "0" and func:
                try:
                    func()
                except Exception as e:
                    logger.error(f"{name}演示失败: {e}")
                    print(f"\n❌ {name}演示失败: {e}")
    elif choice in demos and demos[choice][1]:
        # 运行选定的演示
        try:
            demos[choice][1]()
        except Exception as e:
            logger.error(f"演示失败: {e}")
            print(f"\n❌ 演示失败: {e}")
    else:
        print("无效的选项")

    print("\n" + "=" * 60)
    print("演示完成！")
    print("=" * 60)


if __name__ == "__main__":
    main()
