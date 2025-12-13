"""
测试知识库系统优化 v2.30.40-v2.30.41

测试内容：
1. 混合检索系统
2. 重排序机制
3. 知识质量管理
4. 用户反馈功能
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

def test_hybrid_retrieval():
    """测试混合检索"""
    print("\n" + "="*60)
    print("测试 1: 混合检索系统")
    print("="*60)
    
    # 初始化知识库
    lore_book = LoreBook()
    
    # 添加测试知识
    test_knowledge = [
        {
            "title": "小薄荷的生日",
            "content": "小薄荷的生日是 2024年1月1日，她是一只可爱的猫娘女仆。",
            "category": "character",
            "keywords": ["小薄荷", "生日", "猫娘"],
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
    ]
    
    print("\n添加测试知识...")
    for knowledge in test_knowledge:
        lore_id = lore_book.add_lore(
            title=knowledge["title"],
            content=knowledge["content"],
            category=knowledge["category"],
            keywords=knowledge["keywords"],
            source="test",
            skip_quality_check=True,  # 跳过质量检查以加快测试
        )
        if lore_id:
            print(f"✅ 添加成功: {knowledge['title']}")
        else:
            print(f"❌ 添加失败: {knowledge['title']}")
    
    # 测试混合检索
    print("\n测试混合检索...")
    queries = [
        "小薄荷什么时候生日？",
        "主人喜欢什么饮料？",
        "家在哪里？",
    ]
    
    for query in queries:
        print(f"\n查询: {query}")
        
        # 传统检索
        start_time = time.time()
        traditional_results = lore_book.search_lore(query, k=3, use_hybrid=False)
        traditional_time = time.time() - start_time
        
        # 混合检索
        start_time = time.time()
        hybrid_results = lore_book.search_lore(query, k=3, use_hybrid=True)
        hybrid_time = time.time() - start_time
        
        print(f"  传统检索: {len(traditional_results)} 条结果, 耗时 {traditional_time*1000:.2f}ms")
        print(f"  混合检索: {len(hybrid_results)} 条结果, 耗时 {hybrid_time*1000:.2f}ms")
        
        if hybrid_results:
            print(f"  最佳匹配: {hybrid_results[0]['metadata']['title']}")
            print(f"  相似度: {hybrid_results[0]['similarity']:.3f}")
    
    print("\n✅ 混合检索测试完成")


def test_quality_management():
    """测试知识质量管理"""
    print("\n" + "="*60)
    print("测试 2: 知识质量管理")
    print("="*60)
    
    lore_book = LoreBook()
    
    # 添加不同质量的知识
    test_cases = [
        {
            "title": "高质量知识",
            "content": "这是一条详细的、结构良好的知识条目。它包含了丰富的信息，有清晰的标点符号，内容长度适中。",
            "category": "general",
            "keywords": ["测试", "高质量"],
            "expected_quality": "高",
        },
        {
            "title": "低质量知识",
            "content": "短",
            "category": "general",
            "keywords": [],
            "expected_quality": "低",
        },
        {
            "title": "中等质量知识",
            "content": "这是一条中等质量的知识",
            "category": "general",
            "keywords": ["测试"],
            "expected_quality": "中",
        },
    ]
    
    print("\n添加测试知识并评估质量...")
    for case in test_cases:
        lore_id = lore_book.add_lore(
            title=case["title"],
            content=case["content"],
            category=case["category"],
            keywords=case["keywords"],
            source="test",
            skip_quality_check=False,  # 启用质量检查
        )
        
        if lore_id:
            # 评估质量
            assessment = lore_book.assess_knowledge_quality(lore_id)
            if assessment:
                print(f"\n知识: {case['title']}")
                print(f"  预期质量: {case['expected_quality']}")
                print(f"  质量分数: {assessment['quality_score']:.3f}")
                print(f"  是否有效: {assessment['is_valid']}")
                if assessment['issues']:
                    print(f"  问题: {', '.join(assessment['issues'])}")
                if assessment['suggestions']:
                    print(f"  建议: {', '.join(assessment['suggestions'])}")
    
    # 获取低质量知识
    print("\n获取低质量知识...")
    low_quality = lore_book.get_low_quality_knowledge(threshold=0.5)
    print(f"找到 {len(low_quality)} 条低质量知识")
    for lore in low_quality:
        print(f"  - {lore['title']}: {lore['quality_score']:.3f}")
    
    print("\n✅ 知识质量管理测试完成")


def test_user_feedback():
    """测试用户反馈"""
    print("\n" + "="*60)
    print("测试 3: 用户反馈功能")
    print("="*60)
    
    lore_book = LoreBook()
    
    # 添加测试知识
    lore_id = lore_book.add_lore(
        title="测试反馈",
        content="这是一条用于测试反馈功能的知识。",
        category="general",
        keywords=["测试", "反馈"],
        source="test",
        skip_quality_check=True,
    )
    
    if lore_id:
        print(f"\n添加测试知识: {lore_id}")
        
        # 提供正面反馈
        print("\n提供正面反馈...")
        success = lore_book.provide_feedback(lore_id, is_positive=True)
        print(f"  {'✅ 成功' if success else '❌ 失败'}")
        
        # 提供负面反馈
        print("\n提供负面反馈...")
        success = lore_book.provide_feedback(lore_id, is_positive=False)
        print(f"  {'✅ 成功' if success else '❌ 失败'}")
        
        # 查看反馈统计
        all_lores = lore_book.get_all_lores()
        for lore in all_lores:
            if lore.get("id") == lore_id:
                print(f"\n反馈统计:")
                print(f"  正面反馈: {lore.get('positive_feedback', 0)}")
                print(f"  负面反馈: {lore.get('negative_feedback', 0)}")
                break
    
    print("\n✅ 用户反馈测试完成")


if __name__ == "__main__":
    print("="*60)
    print("知识库系统优化测试 v2.30.40-v2.30.41")
    print("="*60)
    
    try:
        test_hybrid_retrieval()
        test_quality_management()
        test_user_feedback()
        
        print("\n" + "="*60)
        print("✅ 所有测试完成！")
        print("="*60)
    
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()

