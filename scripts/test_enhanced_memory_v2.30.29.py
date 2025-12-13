#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
增强记忆系统测试脚本 v2.30.29

测试日记系统的元数据提取（情感、主题、重要性）和检索功能
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.agent.core import MintChatAgent
from src.utils.logger import logger


def test_enhanced_memory():
    """测试增强记忆系统"""
    logger.info("=" * 60)
    logger.info("开始测试增强记忆系统 v2.30.29")
    logger.info("=" * 60)
    
    # 创建 Agent
    agent = MintChatAgent(user_id=1)
    
    # 1. 测试初始状态
    logger.info("\n【1】测试初始记忆状态")
    initial_stats = agent.get_memory_stats()
    logger.info(f"初始记忆统计: {initial_stats}")
    
    # 2. 测试不同情感和主题的消息
    logger.info("\n【2】测试不同情感和主题的消息")
    test_messages = [
        "今天工作好累啊，加班到很晚",  # sad + work
        "哈哈，刚才看了个超级搞笑的视频！",  # happy + entertainment
        "明天要考试了，好紧张啊",  # anxious + study
        "记住，下周一要参加重要会议",  # neutral + work + important
        "和朋友一起吃饭，聊得很开心~",  # happy + relationship
        "最近身体不太舒服，要多休息",  # sad + health
        "学习了新的编程技能，超级兴奋！",  # excited + study
        "今天天气真好，出去散步了",  # happy + life
    ]
    
    for i, msg in enumerate(test_messages, 1):
        logger.info(f"\n测试消息 {i}/{len(test_messages)}: {msg}")
        
        # 使用流式对话
        reply = ""
        for chunk in agent.chat_stream(msg, save_to_long_term=True):
            reply += chunk
        
        logger.info(f"回复: {reply[:100]}...")
    
    # 3. 检查记忆统计
    logger.info("\n【3】检查记忆统计（含情感和主题）")
    final_stats = agent.get_memory_stats()
    logger.info(f"最终记忆统计: {final_stats}")
    
    # 4. 对比变化
    logger.info("\n【4】记忆变化对比")
    logger.info(f"短期记忆: {initial_stats['short_term_messages']} → {final_stats['short_term_messages']}")
    logger.info(f"长期记忆: {initial_stats['long_term_memories']} → {final_stats['long_term_memories']}")
    logger.info(f"核心记忆: {initial_stats['core_memories']} → {final_stats['core_memories']}")
    logger.info(f"日记条目: {initial_stats['diary_entries']} → {final_stats['diary_entries']}")
    
    # 5. 情感和主题统计
    logger.info("\n【5】情感和主题统计")
    logger.info(f"情感统计: {final_stats.get('emotion_stats', {})}")
    logger.info(f"主题统计: {final_stats.get('topic_stats', {})}")
    
    # 6. 测试按情感检索
    logger.info("\n【6】测试按情感检索")
    for emotion in ["happy", "sad", "anxious", "excited"]:
        results = agent.diary_memory.search_by_emotion(emotion, k=3)
        logger.info(f"\n情感 [{emotion}]: 找到 {len(results)} 条日记")
        for i, entry in enumerate(results, 1):
            logger.info(f"  {i}. {entry.get('content', '')[:80]}...")
            logger.info(f"     重要性: {entry.get('importance', 0):.2f}")
    
    # 7. 测试按主题检索
    logger.info("\n【7】测试按主题检索")
    for topic in ["work", "study", "entertainment", "relationship", "health", "life"]:
        results = agent.diary_memory.search_by_topic(topic, k=3)
        logger.info(f"\n主题 [{topic}]: 找到 {len(results)} 条日记")
        for i, entry in enumerate(results, 1):
            logger.info(f"  {i}. {entry.get('content', '')[:80]}...")
            logger.info(f"     情感: {entry.get('emotion', 'unknown')}, 重要性: {entry.get('importance', 0):.2f}")
    
    # 8. 测试内容检索（带元数据过滤）
    logger.info("\n【8】测试内容检索（带元数据过滤）")
    
    # 搜索开心的工作相关日记
    logger.info("\n搜索：开心的工作相关日记")
    results = agent.diary_memory.search_by_content("工作", k=3, emotion="happy")
    logger.info(f"找到 {len(results)} 条相关日记")
    for i, entry in enumerate(results, 1):
        logger.info(f"  {i}. {entry.get('content', '')[:80]}...")
        logger.info(f"     相似度: {entry.get('similarity', 0):.2f}")
    
    # 搜索重要的学习相关日记
    logger.info("\n搜索：重要的学习相关日记（重要性 >= 0.5）")
    results = agent.diary_memory.search_by_content("学习", k=3, min_importance=0.5)
    logger.info(f"找到 {len(results)} 条相关日记")
    for i, entry in enumerate(results, 1):
        logger.info(f"  {i}. {entry.get('content', '')[:80]}...")
        logger.info(f"     重要性: {entry.get('metadata', {}).get('importance', 0):.2f}")
    
    # 9. 验证结果
    logger.info("\n【9】验证结果")
    success = True
    
    if final_stats['diary_entries'] <= initial_stats['diary_entries']:
        logger.error(f"❌ 日记未增加！当前: {final_stats['diary_entries']}")
        success = False
    else:
        logger.info(f"✅ 日记增加了 {final_stats['diary_entries'] - initial_stats['diary_entries']} 条")
    
    if not final_stats.get('emotion_stats'):
        logger.error("❌ 情感统计为空！")
        success = False
    else:
        logger.info(f"✅ 情感统计正常: {len(final_stats['emotion_stats'])} 种情感")
    
    if not final_stats.get('topic_stats'):
        logger.error("❌ 主题统计为空！")
        success = False
    else:
        logger.info(f"✅ 主题统计正常: {len(final_stats['topic_stats'])} 个主题")
    
    # 10. 总结
    logger.info("\n" + "=" * 60)
    if success:
        logger.info("✅ 增强记忆系统测试通过！")
    else:
        logger.error("❌ 增强记忆系统测试失败！")
    logger.info("=" * 60)
    
    return success


if __name__ == "__main__":
    try:
        success = test_enhanced_memory()
        sys.exit(0 if success else 1)
    except Exception as e:
        logger.error(f"测试失败: {e}")
        import traceback
        logger.error(traceback.format_exc())
        sys.exit(1)

