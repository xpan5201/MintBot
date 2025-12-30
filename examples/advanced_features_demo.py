"""
高级功能演示

演示 v2.3 新增的高级功能：
- 核心记忆
- 日记功能
- 知识库
- 高级情绪系统
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.agent.core import MintChatAgent
from src.utils.logger import get_logger

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


def demo_diary():
    """演示日记功能"""
    print("\n" + "=" * 60)
    print("【日记功能演示】")
    print("=" * 60)

    agent = MintChatAgent()

    # 模拟几天的对话
    print("\n1. 模拟对话并自动记录日记...")
    conversations = [
        "今天天气真好，我们去公园散步了",
        "中午吃了美味的拉面",
        "下午看了一部有趣的电影",
    ]

    for msg in conversations:
        print(f"\n主人: {msg}")
        response = agent.chat(msg)
        print(f"{agent.character.name}: {response}")

    # 测试时间检索
    print("\n2. 测试时间检索...")
    response = agent.chat("今天做了什么？")
    print("\n主人: 今天做了什么？")
    print(f"{agent.character.name}: {response}")


def demo_lore_book():
    """演示知识库功能"""
    print("\n" + "=" * 60)
    print("【知识库演示】")
    print("=" * 60)

    agent = MintChatAgent()

    # 添加知识库条目
    print("\n1. 添加知识库条目...")
    agent.add_lore(
        title="小雪糕的猫耳",
        content="小雪糕的猫耳是粉白相间的，非常可爱。当她开心时，猫耳会竖起来；害羞时会微微垂下。",
        category="character",
        keywords=["猫耳", "外观", "表情"],
    )

    agent.add_lore(
        title="温馨小屋",
        content="主人和小雪糕居住的温馨小屋，有暖黄色的吊灯，铺着绒垫的猫窝，靠窗的书桌。",
        category="location",
        keywords=["小屋", "家", "环境"],
    )

    agent.add_lore(
        title="小铃铛",
        content="小雪糕女仆装袖口上别着的小铃铛，走动时会发出清脆的响声。",
        category="item",
        keywords=["铃铛", "装饰", "声音"],
    )

    # 测试知识库检索
    print("\n2. 测试知识库检索...")
    response = agent.chat("你的猫耳是什么样的？")
    print("\n主人: 你的猫耳是什么样的？")
    print(f"{agent.character.name}: {response}")

    response = agent.chat("我们的家是什么样的？")
    print("\n主人: 我们的家是什么样的？")
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

    # 设置背景知识
    print("\n1. 设置背景知识...")
    agent.add_core_memory(
        "主人是一名程序员，喜欢编程和阅读", category="personal_info", importance=0.9
    )

    agent.add_lore(
        title="编程语言Python",
        content="Python是主人最喜欢的编程语言，简洁优雅，功能强大。",
        category="knowledge",
        keywords=["编程", "Python", "技术"],
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
    print(f"  - 日记功能: {'启用' if stats['advanced_memory']['diary_enabled'] else '未启用'}")
    print(f"  - 知识库: {'启用' if stats['advanced_memory']['lore_books_enabled'] else '未启用'}")


def main():
    """主函数"""
    print("\n" + "=" * 60)
    print("MintChat v2.3 高级功能演示")
    print("=" * 60)

    demos = {
        "1": ("核心记忆", demo_core_memory),
        "2": ("日记功能", demo_diary),
        "3": ("知识库", demo_lore_book),
        "4": ("高级情绪系统", demo_mood_system),
        "5": ("综合功能", demo_integrated_features),
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
