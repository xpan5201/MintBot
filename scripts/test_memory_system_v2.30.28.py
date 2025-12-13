#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
记忆系统测试脚本 v2.30.28

测试长期记忆、核心记忆和日记系统是否正常工作
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.agent.core import MintChatAgent
from src.utils.logger import logger


def test_memory_system():
    """测试记忆系统"""
    logger.info("=" * 60)
    logger.info("开始测试记忆系统 v2.30.28")
    logger.info("=" * 60)
    
    # 创建 Agent
    agent = MintChatAgent(user_id=1)
    
    # 1. 测试初始状态
    logger.info("\n【1】测试初始记忆状态")
    initial_stats = agent.get_memory_stats()
    logger.info(f"初始记忆统计: {initial_stats}")
    
    # 2. 测试日记保存
    logger.info("\n【2】测试日记保存")
    test_messages = [
        "你好，小喵！",
        "今天天气真好",
        "我喜欢吃苹果",
        "记住，我的生日是3月15日",
        "我叫张三，今年25岁"
    ]
    
    for i, msg in enumerate(test_messages, 1):
        logger.info(f"\n测试消息 {i}/{len(test_messages)}: {msg}")
        
        # 使用流式对话（这是GUI主要使用的方法）
        reply = ""
        for chunk in agent.chat_stream(msg, save_to_long_term=True):
            reply += chunk
        
        logger.info(f"回复: {reply[:100]}...")
    
    # 3. 检查记忆统计
    logger.info("\n【3】检查记忆统计")
    final_stats = agent.get_memory_stats()
    logger.info(f"最终记忆统计: {final_stats}")
    
    # 4. 对比变化
    logger.info("\n【4】记忆变化对比")
    logger.info(f"短期记忆: {initial_stats['short_term_messages']} → {final_stats['short_term_messages']}")
    logger.info(f"长期记忆: {initial_stats['long_term_memories']} → {final_stats['long_term_memories']}")
    logger.info(f"核心记忆: {initial_stats['core_memories']} → {final_stats['core_memories']}")
    logger.info(f"日记条目: {initial_stats['diary_entries']} → {final_stats['diary_entries']}")
    logger.info(f"知识库: {initial_stats['lore_entries']} → {final_stats['lore_entries']}")
    
    # 5. 验证结果
    logger.info("\n【5】验证结果")
    success = True
    
    if final_stats['diary_entries'] <= initial_stats['diary_entries']:
        logger.error(f"❌ 日记未增加！当前: {final_stats['diary_entries']}")
        success = False
    else:
        logger.info(f"✅ 日记增加了 {final_stats['diary_entries'] - initial_stats['diary_entries']} 条")
    
    if final_stats['core_memories'] <= initial_stats['core_memories']:
        logger.warning(f"⚠️ 核心记忆未增加！当前: {final_stats['core_memories']}")
        logger.info("提示: 核心记忆需要包含特定关键词才会自动提取")
    else:
        logger.info(f"✅ 核心记忆增加了 {final_stats['core_memories'] - initial_stats['core_memories']} 条")
    
    if final_stats['long_term_memories'] <= initial_stats['long_term_memories']:
        logger.error(f"❌ 长期记忆未增加！当前: {final_stats['long_term_memories']}")
        success = False
    else:
        logger.info(f"✅ 长期记忆增加了 {final_stats['long_term_memories'] - initial_stats['long_term_memories']} 条")
    
    # 6. 测试记忆检索
    logger.info("\n【6】测试记忆检索")
    
    # 测试日记检索
    logger.info("\n测试日记检索（内容搜索）:")
    diary_results = agent.diary_memory.search_by_content("苹果", k=3)
    logger.info(f"找到 {len(diary_results)} 条相关日记")
    for i, entry in enumerate(diary_results, 1):
        logger.info(f"  {i}. {entry.get('content', '')[:100]}...")
    
    # 测试核心记忆检索
    logger.info("\n测试核心记忆检索:")
    core_results = agent.core_memory.search_core_memories("生日", k=3)
    logger.info(f"找到 {len(core_results)} 条相关核心记忆")
    for i, entry in enumerate(core_results, 1):
        logger.info(f"  {i}. {entry.get('content', '')[:100]}...")
    
    # 7. 总结
    logger.info("\n" + "=" * 60)
    if success:
        logger.info("✅ 记忆系统测试通过！")
    else:
        logger.error("❌ 记忆系统测试失败！")
    logger.info("=" * 60)
    
    return success


if __name__ == "__main__":
    try:
        success = test_memory_system()
        sys.exit(0 if success else 1)
    except Exception as e:
        logger.error(f"测试失败: {e}")
        import traceback
        logger.error(traceback.format_exc())
        sys.exit(1)

