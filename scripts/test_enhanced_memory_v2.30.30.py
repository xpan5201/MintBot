#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
增强记忆系统测试脚本 v2.30.31

测试优化后的情感识别、主题识别和重要性评分准确性
包含混合情感识别和扩展关键词测试
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.agent.core import MintChatAgent
from src.utils.logger import logger


def test_emotion_recognition():
    """测试情感识别准确性"""
    logger.info("=" * 60)
    logger.info("【1】测试情感识别准确性")
    logger.info("=" * 60)
    
    agent = MintChatAgent(user_id=1)
    
    # 测试用例：(消息, 预期情感)
    test_cases = [
        # 测试否定词
        ("今天不开心", "sad"),  # 否定词 + happy -> sad
        ("我不难过", "happy"),  # 否定词 + sad -> happy

        # 测试程度副词
        ("超级开心！", "happy"),  # 程度副词 + happy
        ("非常难过", "sad"),  # 程度副词 + sad
        ("特别兴奋！", "excited"),  # 程度副词 + excited

        # 测试混合情感（v2.30.31: 新增）
        ("今天工作好累啊，但是完成了很开心", "happy"),  # 转折词，后面的happy为主
        ("虽然很紧张，但是很期待", "excited"),  # 转折词，后面的excited为主
        ("虽然累，可是很满足", "happy"),  # 转折词，后面的happy为主

        # 测试扩展关键词（v2.30.31: 新增）
        ("太期待明天的旅行了！", "excited"),  # 扩展excited关键词
        ("感觉很舒心", "happy"),  # 扩展happy关键词
        ("心里很忐忑", "anxious"),  # 扩展anxious关键词

        # 测试边界情况
        ("今天天气不错", "happy"),  # 弱情感
        ("嗯", "neutral"),  # 无情感
    ]
    
    correct = 0
    total = len(test_cases)
    
    for i, (message, expected) in enumerate(test_cases, 1):
        # 提取情感
        emotion = agent.diary_memory._extract_emotion(message)
        
        # 判断是否正确
        is_correct = emotion == expected
        if is_correct:
            correct += 1
            status = "✅"
        else:
            status = "❌"
        
        logger.info(f"{status} 测试 {i}/{total}: \"{message}\"")
        logger.info(f"   预期: {expected}, 实际: {emotion}")
    
    accuracy = correct / total * 100
    logger.info(f"\n情感识别准确率: {correct}/{total} = {accuracy:.1f}%")
    
    return accuracy >= 70  # 70%以上算通过


def test_topic_recognition():
    """测试主题识别准确性"""
    logger.info("\n" + "=" * 60)
    logger.info("【2】测试主题识别准确性")
    logger.info("=" * 60)
    
    agent = MintChatAgent(user_id=1)
    
    # 测试用例：(消息, 预期主题)
    test_cases = [
        # 测试优先级
        ("和朋友一起吃饭", "relationship"),  # relationship优先级高于life
        ("和家人去医院检查身体", "health"),  # health优先级高于relationship

        # 测试关键词权重
        ("今天工作加班到很晚", "work"),  # work关键词
        ("学习了新的编程技能", "study"),  # study关键词
        ("看了一部超级好看的电影", "entertainment"),  # entertainment关键词

        # 测试复杂主题
        ("下班后和同事一起玩游戏", "entertainment"),  # work + entertainment，entertainment权重更高
        ("在公司学习新技能", "study"),  # work + study，study权重更高

        # 测试扩展关键词（v2.30.31: 新增）
        ("和闺蜜一起逛街", "relationship"),  # 扩展relationship关键词
        ("去健身房锻炼身体", "health"),  # 扩展health关键词
        ("参加团队会议讨论项目", "work"),  # 扩展work关键词

        # 测试边界情况
        ("今天天气真好", "other"),  # 无明确主题
    ]
    
    correct = 0
    total = len(test_cases)
    
    for i, (message, expected) in enumerate(test_cases, 1):
        # 提取主题
        topic = agent.diary_memory._extract_topic(message)
        
        # 判断是否正确
        is_correct = topic == expected
        if is_correct:
            correct += 1
            status = "✅"
        else:
            status = "❌"
        
        logger.info(f"{status} 测试 {i}/{total}: \"{message}\"")
        logger.info(f"   预期: {expected}, 实际: {topic}")
    
    accuracy = correct / total * 100
    logger.info(f"\n主题识别准确率: {correct}/{total} = {accuracy:.1f}%")
    
    return accuracy >= 70  # 70%以上算通过


def test_importance_scoring():
    """测试重要性评分准确性"""
    logger.info("\n" + "=" * 60)
    logger.info("【3】测试重要性评分准确性")
    logger.info("=" * 60)
    
    agent = MintChatAgent(user_id=1)
    
    # 测试用例：(消息, 预期重要性范围)
    test_cases = [
        # 高重要性
        ("紧急！明天必须参加重要会议", (0.7, 1.0)),
        ("记住，下周一截止日期，千万别忘了", (0.6, 1.0)),
        
        # 中重要性
        ("明天要考试，需要复习一下", (0.4, 0.7)),
        ("下周有个项目要完成", (0.3, 0.6)),
        
        # 低重要性
        ("今天天气不错", (0.0, 0.3)),
        ("吃了个苹果", (0.0, 0.3)),
    ]
    
    correct = 0
    total = len(test_cases)
    
    for i, (message, (min_score, max_score)) in enumerate(test_cases, 1):
        # 计算重要性
        importance = agent.diary_memory._calculate_importance(message)
        
        # 判断是否在预期范围内
        is_correct = min_score <= importance <= max_score
        if is_correct:
            correct += 1
            status = "✅"
        else:
            status = "❌"
        
        logger.info(f"{status} 测试 {i}/{total}: \"{message}\"")
        logger.info(f"   预期: [{min_score:.1f}, {max_score:.1f}], 实际: {importance:.2f}")
    
    accuracy = correct / total * 100
    logger.info(f"\n重要性评分准确率: {correct}/{total} = {accuracy:.1f}%")
    
    return accuracy >= 70  # 70%以上算通过


if __name__ == "__main__":
    try:
        # 运行所有测试
        test1_passed = test_emotion_recognition()
        test2_passed = test_topic_recognition()
        test3_passed = test_importance_scoring()
        
        # 总结
        logger.info("\n" + "=" * 60)
        logger.info("测试总结")
        logger.info("=" * 60)
        logger.info(f"情感识别: {'✅ 通过' if test1_passed else '❌ 失败'}")
        logger.info(f"主题识别: {'✅ 通过' if test2_passed else '❌ 失败'}")
        logger.info(f"重要性评分: {'✅ 通过' if test3_passed else '❌ 失败'}")
        
        all_passed = test1_passed and test2_passed and test3_passed
        if all_passed:
            logger.info("\n✅ 所有测试通过！")
            sys.exit(0)
        else:
            logger.error("\n❌ 部分测试失败！")
            sys.exit(1)
            
    except Exception as e:
        logger.error(f"测试失败: {e}")
        import traceback
        logger.error(traceback.format_exc())
        sys.exit(1)

