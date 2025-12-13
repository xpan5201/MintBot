"""
测试智能日记系统 v2.30.36

测试内容：
1. 智能过滤 - 只保存重要对话
2. 每日总结 - 自动生成今天的对话总结
3. 对话缓存 - 临时缓存不重要的对话
"""

import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.agent.advanced_memory import DiaryMemory
from src.utils.logger import logger
from datetime import datetime
import json


def test_smart_diary():
    """测试智能日记系统"""
    logger.info("=" * 80)
    logger.info("开始测试智能日记系统 v2.30.36")
    logger.info("=" * 80)

    # 创建测试用的日记系统
    test_dir = project_root / "data" / "test_smart_diary"
    diary = DiaryMemory(persist_directory=str(test_dir))

    # 清空之前的测试数据
    diary_file = test_dir / "diary.json"
    if diary_file.exists():
        diary_file.write_text("[]", encoding="utf-8")
    diary.daily_conversations = []
    diary.last_summary_date = None

    logger.info("\n" + "=" * 80)
    logger.info("测试 1: 智能过滤 - 只保存重要对话")
    logger.info("=" * 80)

    # 测试对话（包含重要和不重要的）
    test_conversations = [
        # 不重要的对话（应该被过滤）
        ("主人: 你好\n小雪糕: 你好主人喵~", 0.3, "neutral", [], None, None),
        ("主人: 今天天气怎么样\n小雪糕: 今天天气很好喵~", 0.4, "neutral", [], None, None),
        ("主人: 嗯\n小雪糕: 主人还有什么需要吗喵~", 0.2, "neutral", [], None, None),
        
        # 重要对话（应该被保存）
        ("主人: 明天要去公司开项目会议，有点紧张\n小雪糕: 主人不要紧张喵~ 您一定可以的！", 0.75, "anxious", ["同事"], "公司", "项目会议"),
        
        # 美好瞬间（应该被保存）
        ("主人: 今天项目成功了！太开心了！\n小雪糕: 恭喜主人喵~ 我就知道您一定可以的！", 0.85, "excited", [], None, "项目成功"),
        
        # 不重要的对话（应该被过滤）
        ("主人: 好的\n小雪糕: 好的主人喵~", 0.3, "neutral", [], None, None),
        ("主人: 谢谢\n小雪糕: 不客气主人喵~", 0.4, "happy", [], None, None),
        
        # 特殊情感（应该被保存）
        ("主人: 今天工作出错了，好难过\n小雪糕: 主人不要难过喵~ 我会一直陪着您的", 0.5, "sad", [], None, None),
        
        # 不重要的对话（应该被过滤）
        ("主人: 嗯嗯\n小雪糕: 主人还有什么需要吗喵~", 0.2, "neutral", [], None, None),
        ("主人: 没有了\n小雪糕: 好的主人喵~", 0.3, "neutral", [], None, None),
    ]

    saved_count = 0
    filtered_count = 0

    for content, importance, emotion, people, location, event in test_conversations:
        logger.info(f"\n添加对话: {content[:30]}... (重要性:{importance}, 情感:{emotion})")
        
        # 记录添加前的日记数量
        before_count = len(json.loads(diary_file.read_text(encoding="utf-8")))
        
        # 添加日记
        diary.add_diary_entry(
            content=content,
            importance=importance,
            emotion=emotion,
            people=people,
            location=location,
            event=event,
        )
        
        # 记录添加后的日记数量
        after_count = len(json.loads(diary_file.read_text(encoding="utf-8")))
        
        if after_count > before_count:
            saved_count += 1
            logger.info(f"✅ 已保存为日记")
        else:
            filtered_count += 1
            logger.info(f"⏭️ 已过滤（缓存到 daily_conversations）")

    logger.info(f"\n总结:")
    logger.info(f"- 总对话数: {len(test_conversations)}")
    logger.info(f"- 保存为日记: {saved_count} 条")
    logger.info(f"- 过滤掉: {filtered_count} 条")
    logger.info(f"- 缓存对话数: {len(diary.daily_conversations)}")

    logger.info("\n" + "=" * 80)
    logger.info("测试 2: 每日总结 - 自动生成今天的对话总结")
    logger.info("=" * 80)

    # 生成每日总结
    summary = diary.generate_daily_summary(force=True)
    
    if summary:
        logger.info(f"\n✅ 每日总结生成成功:")
        logger.info(summary)
    else:
        logger.error("❌ 每日总结生成失败")

    # 检查总结是否保存为日记
    diaries = json.loads(diary_file.read_text(encoding="utf-8"))
    summary_entries = [d for d in diaries if "每日总结" in d["content"]]
    
    if summary_entries:
        logger.info(f"\n✅ 每日总结已保存为日记")
        logger.info(f"总结内容: {summary_entries[-1]['content'][:100]}...")
    else:
        logger.error("❌ 每日总结未保存为日记")

    logger.info("\n" + "=" * 80)
    logger.info("测试 3: 验证日记内容")
    logger.info("=" * 80)

    # 读取所有日记
    diaries = json.loads(diary_file.read_text(encoding="utf-8"))
    
    logger.info(f"\n总日记数: {len(diaries)}")
    logger.info(f"\n日记列表:")
    for i, diary_entry in enumerate(diaries, 1):
        logger.info(f"\n{i}. {diary_entry['timestamp']}")
        logger.info(f"   情感: {diary_entry['emotion']}")
        logger.info(f"   主题: {diary_entry['topic']}")
        logger.info(f"   重要性: {diary_entry['importance']:.2f}")
        if diary_entry.get('people'):
            logger.info(f"   人物: {', '.join(diary_entry['people'])}")
        if diary_entry.get('location'):
            logger.info(f"   地点: {diary_entry['location']}")
        if diary_entry.get('event'):
            logger.info(f"   事件: {diary_entry['event']}")
        logger.info(f"   内容: {diary_entry['content'][:80]}...")

    logger.info("\n" + "=" * 80)
    logger.info("✅ 智能日记系统测试完成！")
    logger.info("=" * 80)


if __name__ == "__main__":
    test_smart_diary()

