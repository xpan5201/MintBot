#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
LLM 辅助提取测试脚本 v2.30.32

测试 LLM 辅助提取情感、主题和元数据的准确性
"""

import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.agent.core import MintChatAgent
from src.utils.logger import get_logger

logger = get_logger(__name__)


def test_llm_extraction():
    """测试 LLM 辅助提取功能"""
    logger.info("=" * 60)
    logger.info("【1】测试 LLM 辅助提取功能")
    logger.info("=" * 60)

    # 初始化 Agent
    agent = MintChatAgent(user_id=1)

    # 测试用例：(消息, 预期情感, 预期主题, 预期人物, 预期地点, 预期事件)
    test_cases = [
        (
            "明天要和同事一起去公司开项目会议，有点紧张但也很期待",
            "excited",  # 预期情感（转折词后为主）
            "work",  # 预期主题
            ["同事"],  # 预期人物
            "公司",  # 预期地点
            "项目会议",  # 预期事件
        ),
        (
            "昨天和朋友在餐厅吃饭，聊得很开心",
            "happy",  # 预期情感
            "relationship",  # 预期主题
            ["朋友"],  # 预期人物
            "餐厅",  # 预期地点
            None,  # 预期事件
        ),
        (
            "下周要考试了，需要好好复习，感觉压力很大",
            "anxious",  # 预期情感
            "study",  # 预期主题
            [],  # 预期人物
            None,  # 预期地点
            "考试",  # 预期事件
        ),
        (
            "今天去健身房锻炼身体，感觉很舒服",
            "happy",  # 预期情感
            "health",  # 预期主题
            [],  # 预期人物
            "健身房",  # 预期地点
            None,  # 预期事件
        ),
        (
            "和家人一起去旅游，玩得很开心",
            "happy",  # 预期情感
            "entertainment",  # 预期主题
            ["家人"],  # 预期人物
            None,  # 预期地点
            "旅游",  # 预期事件
        ),
    ]

    correct_emotion = 0
    correct_topic = 0
    correct_people = 0
    correct_location = 0
    correct_event = 0
    total = len(test_cases)

    for i, (message, expected_emotion, expected_topic, expected_people, expected_location, expected_event) in enumerate(test_cases, 1):
        logger.info(f"\n测试 {i}/{total}: \"{message}\"")

        # 提取元数据
        if agent.diary_memory.use_llm_extraction:
            result = agent.diary_memory._extract_with_llm(message)
            emotion = result.get("emotion", "neutral")
            topic = result.get("topic", "other")
            people = result.get("people", [])
            location = result.get("location")
            event = result.get("event")
        else:
            emotion = agent.diary_memory._extract_emotion(message)
            topic = agent.diary_memory._extract_topic(message)
            people = []
            location = None
            event = None

        # 检查情感
        if emotion == expected_emotion:
            logger.info(f"   ✅ 情感: {emotion} (正确)")
            correct_emotion += 1
        else:
            logger.info(f"   ❌ 情感: {emotion} (预期: {expected_emotion})")

        # 检查主题
        if topic == expected_topic:
            logger.info(f"   ✅ 主题: {topic} (正确)")
            correct_topic += 1
        else:
            logger.info(f"   ❌ 主题: {topic} (预期: {expected_topic})")

        # 检查人物
        if set(people) == set(expected_people):
            logger.info(f"   ✅ 人物: {people} (正确)")
            correct_people += 1
        else:
            logger.info(f"   ❌ 人物: {people} (预期: {expected_people})")

        # 检查地点
        if location == expected_location:
            logger.info(f"   ✅ 地点: {location} (正确)")
            correct_location += 1
        else:
            logger.info(f"   ❌ 地点: {location} (预期: {expected_location})")

        # 检查事件
        if event == expected_event:
            logger.info(f"   ✅ 事件: {event} (正确)")
            correct_event += 1
        else:
            logger.info(f"   ❌ 事件: {event} (预期: {expected_event})")

    # 输出统计结果
    logger.info("\n" + "=" * 60)
    logger.info("测试结果统计")
    logger.info("=" * 60)
    logger.info(f"情感识别准确率: {correct_emotion}/{total} = {correct_emotion/total*100:.1f}%")
    logger.info(f"主题识别准确率: {correct_topic}/{total} = {correct_topic/total*100:.1f}%")
    logger.info(f"人物提取准确率: {correct_people}/{total} = {correct_people/total*100:.1f}%")
    logger.info(f"地点提取准确率: {correct_location}/{total} = {correct_location/total*100:.1f}%")
    logger.info(f"事件提取准确率: {correct_event}/{total} = {correct_event/total*100:.1f}%")

    # 判断是否通过
    if correct_emotion >= total * 0.95 and correct_topic >= total * 0.95:
        logger.info("\n✅ 所有测试通过！准确率达到 95% 以上")
        return True
    else:
        logger.info("\n❌ 测试未通过，准确率未达到 95%")
        return False


if __name__ == "__main__":
    try:
        success = test_llm_extraction()
        sys.exit(0 if success else 1)
    except Exception as e:
        logger.error(f"测试失败: {e}", exc_info=True)
        sys.exit(1)

