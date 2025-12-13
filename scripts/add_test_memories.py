"""
添加测试记忆数据

为性能测试准备数据
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.agent.memory import MemoryManager
from src.agent.advanced_memory import CoreMemory, DiaryMemory, LoreBook
from src.utils.logger import logger


def add_test_memories():
    """添加测试记忆"""
    logger.info("添加测试记忆数据...")

    # 初始化记忆系统
    memory = MemoryManager()
    core_memory = CoreMemory()
    diary_memory = DiaryMemory()
    lore_book = LoreBook()

    # 添加长期记忆
    test_conversations = [
        ("今天天气真好", "是的主人，阳光明媚，适合出门散步喵~"),
        ("你喜欢什么颜色", "我喜欢粉色和白色，很可爱的颜色喵~"),
        ("帮我查一下北京的天气", "好的主人，北京今天晴天，温度15-25度喵~"),
        ("你会做什么", "我会聊天、查天气、搜索信息等等喵~"),
        ("你叫什么名字", "我叫MintChat，是您的猫娘女仆喵~"),
    ]

    for user_msg, assistant_msg in test_conversations:
        memory.add_interaction(user_msg, assistant_msg, save_to_long_term=True)

    logger.info(f"添加了 {len(test_conversations)} 条对话记忆")

    # 添加核心记忆
    core_memories_data = [
        "主人喜欢晴天",
        "主人经常问天气",
        "主人喜欢猫娘",
    ]

    for core_mem in core_memories_data:
        core_memory.add_core_memory(core_mem, importance=0.9)

    logger.info(f"添加了 {len(core_memories_data)} 条核心记忆")

    # 添加日记
    diary_entries_data = [
        "今天和主人聊了天气，主人很开心",
        "主人问了我的名字，我告诉他我叫MintChat",
        "今天帮主人查了北京的天气",
    ]

    for entry in diary_entries_data:
        diary_memory.add_diary_entry(entry)

    logger.info(f"添加了 {len(diary_entries_data)} 条日记")

    # 添加知识库
    lore_data = [
        ("天气知识", "晴天适合出门，雨天要带伞"),
        ("猫娘知识", "猫娘喜欢说'喵'，很可爱"),
        ("服务知识", "作为女仆要礼貌、体贴、细心"),
    ]

    for title, content in lore_data:
        lore_book.add_lore(title, content, category="常识")

    logger.info(f"添加了 {len(lore_data)} 条知识")

    logger.info("测试记忆数据添加完成！")


if __name__ == "__main__":
    add_test_memories()

