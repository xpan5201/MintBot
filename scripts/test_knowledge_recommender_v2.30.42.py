"""
测试知识推荐系统 v2.30.42

测试内容：
1. 上下文感知推荐
2. 主动知识推送
3. 知识使用统计
4. 用户偏好学习
"""

import sys
import os
from pathlib import Path

# 设置编码
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.agent.advanced_memory import LoreBook
from src.config.settings import settings
import time


def test_context_aware_recommendation():
    """测试上下文感知推荐"""
    print("\n" + "="*60)
    print("测试 1: 上下文感知推荐")
    print("="*60)
    
    # 初始化知识库
    lore_book = LoreBook()
    
    # 添加测试知识
    test_knowledge = [
        {
            "title": "小薄荷的生日",
            "content": "小薄荷的生日是3月15日，她是一只可爱的猫娘女仆。",
            "category": "character",
            "keywords": ["小薄荷", "生日", "猫娘"],
        },
        {
            "title": "小薄荷的喜好",
            "content": "小薄荷喜欢吃鱼，尤其是三文鱼，还喜欢晒太阳。",
            "category": "character",
            "keywords": ["小薄荷", "喜好", "鱼"],
        },
        {
            "title": "主人的喜好",
            "content": "主人喜欢喝咖啡，尤其是拿铁咖啡，不喜欢太苦的咖啡。",
            "category": "character",
            "keywords": ["主人", "咖啡", "喜好"],
        },
        {
            "title": "家里的地址",
            "content": "家里的地址是北京市朝阳区某某街道123号。",
            "category": "location",
            "keywords": ["地址", "北京", "家"],
        },
        {
            "title": "天气情况",
            "content": "今天天气晴朗，温度适宜，适合外出活动。",
            "category": "general",
            "keywords": ["天气", "晴朗"],
        },
    ]
    
    print("\n添加测试知识...")
    for knowledge in test_knowledge:
        lore_id = lore_book.add_lore(
            title=knowledge["title"],
            content=knowledge["content"],
            category=knowledge["category"],
            keywords=knowledge["keywords"],
            source="test",
            skip_quality_check=True,
        )
        if lore_id:
            print(f"✅ 添加成功: {knowledge['title']}")
    
    # 测试推荐
    print("\n测试上下文感知推荐...")
    
    contexts = [
        {
            "query": "小薄荷喜欢什么？",
            "topic": "character",
            "keywords": ["小薄荷", "喜好"],
            "recent_topics": ["character"],
            "user_id": "test_user",
        },
        {
            "query": "主人喜欢喝什么？",
            "topic": "character",
            "keywords": ["主人", "喝"],
            "recent_topics": ["character"],
            "user_id": "test_user",
        },
        {
            "query": "家在哪里？",
            "topic": "location",
            "keywords": ["家", "地址"],
            "recent_topics": ["location"],
            "user_id": "test_user",
        },
    ]
    
    for context in contexts:
        print(f"\n查询: {context['query']}")
        
        recommendations = lore_book.recommend_knowledge(
            context=context,
            k=3,
            min_score=0.1,
        )
        
        print(f"  推荐数量: {len(recommendations)}")
        for i, rec in enumerate(recommendations, 1):
            print(f"  {i}. {rec['title']}")
            print(f"     推荐分数: {rec['recommendation_score']:.3f}")
            print(f"     推荐理由: {', '.join(rec['recommendation_reasons'])}")
    
    print("\n✅ 上下文感知推荐测试完成")


def test_proactive_push():
    """测试主动知识推送"""
    print("\n" + "="*60)
    print("测试 2: 主动知识推送")
    print("="*60)
    
    lore_book = LoreBook()
    
    # 测试推送
    print("\n测试主动推送...")
    
    contexts = [
        {
            "topic": "character",
            "keywords": ["小薄荷"],
            "recent_topics": [],
            "user_message": "小薄荷是谁？",
        },
        {
            "topic": "character",
            "keywords": ["主人"],
            "recent_topics": ["character"],
            "user_message": "主人喜欢什么？",
        },
    ]
    
    for context in contexts:
        print(f"\n用户消息: {context['user_message']}")
        
        pushed = lore_book.push_knowledge(
            user_id="test_user",
            context=context,
            k=2,
        )
        
        if pushed:
            print(f"  推送数量: {len(pushed)}")
            for i, knowledge in enumerate(pushed, 1):
                print(f"  {i}. {knowledge['title']}")
                print(f"     相关性: {knowledge.get('push_relevance', 0):.3f}")
        else:
            print("  未推送（冷却中或无合适知识）")
        
        # 等待冷却时间
        time.sleep(1)
    
    print("\n✅ 主动知识推送测试完成")


def test_usage_statistics():
    """测试知识使用统计"""
    print("\n" + "="*60)
    print("测试 3: 知识使用统计")
    print("="*60)
    
    lore_book = LoreBook()
    
    # 获取最常用的知识
    print("\n最常用的知识:")
    top_used = lore_book.get_top_used_knowledge(k=5)
    for i, item in enumerate(top_used, 1):
        print(f"  {i}. 知识ID: {item['knowledge_id'][:8]}..., 使用次数: {item['usage_count']}")
    
    # 获取未使用的知识
    print("\n未使用的知识 (30天内):")
    unused = lore_book.get_unused_knowledge(days=30)
    print(f"  未使用知识数量: {len(unused)}")
    
    # 生成统计报告
    print("\n统计报告:")
    report = lore_book.generate_usage_report()
    print(report)
    
    print("\n✅ 知识使用统计测试完成")


def test_user_preference():
    """测试用户偏好学习"""
    print("\n" + "="*60)
    print("测试 4: 用户偏好学习")
    print("="*60)
    
    lore_book = LoreBook()
    
    # 获取一些知识
    all_lores = lore_book.get_all_lores()
    if not all_lores:
        print("  没有知识可供测试")
        return
    
    # 模拟用户反馈
    print("\n模拟用户反馈...")
    for i, lore in enumerate(all_lores[:3]):
        is_positive = i % 2 == 0  # 交替正面和负面
        lore_book.update_recommendation_preference(
            user_id="test_user",
            knowledge=lore,
            is_positive=is_positive,
        )
        print(f"  {lore['title']}: {'正面' if is_positive else '负面'}反馈")
    
    # 再次推荐，查看偏好影响
    print("\n基于偏好的推荐:")
    context = {
        "query": "推荐一些知识",
        "topic": "character",
        "keywords": [],
        "recent_topics": [],
        "user_id": "test_user",
    }
    
    recommendations = lore_book.recommend_knowledge(context, k=3, min_score=0.1)
    for i, rec in enumerate(recommendations, 1):
        print(f"  {i}. {rec['title']}")
        print(f"     推荐分数: {rec['recommendation_score']:.3f}")
    
    print("\n✅ 用户偏好学习测试完成")


if __name__ == "__main__":
    print("="*60)
    print("知识推荐系统测试 v2.30.42")
    print("="*60)
    
    try:
        test_context_aware_recommendation()
        test_proactive_push()
        test_usage_statistics()
        test_user_preference()
        
        print("\n" + "="*60)
        print("✅ 所有测试完成！")
        print("="*60)
    
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()

