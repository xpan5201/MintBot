"""
测试知识图谱系统 v2.30.43

测试内容：
1. 知识关系建模
2. 关系查询
3. 知识推理
4. 图谱统计
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


def test_build_knowledge_graph():
    """测试构建知识图谱"""
    print("\n" + "="*60)
    print("测试 1: 构建知识图谱")
    print("="*60)
    
    # 初始化知识库
    lore_book = LoreBook()
    
    # 添加测试知识
    test_knowledge = [
        {
            "title": "小薄荷",
            "content": "小薄荷是一只可爱的猫娘女仆，她的生日是3月15日。",
            "category": "character",
            "keywords": ["小薄荷", "猫娘", "女仆"],
        },
        {
            "title": "小薄荷的生日",
            "content": "小薄荷的生日是3月15日，她是一只可爱的猫娘女仆。",
            "category": "character",
            "keywords": ["小薄荷", "生日", "3月15日"],
        },
        {
            "title": "小薄荷的喜好",
            "content": "小薄荷喜欢吃鱼，尤其是三文鱼，还喜欢晒太阳。",
            "category": "character",
            "keywords": ["小薄荷", "喜好", "鱼", "三文鱼"],
        },
        {
            "title": "主人",
            "content": "主人是小薄荷的主人，他们住在一起。",
            "category": "character",
            "keywords": ["主人", "小薄荷"],
        },
        {
            "title": "家",
            "content": "家是小薄荷和主人住的地方，位于北京市朝阳区。",
            "category": "location",
            "keywords": ["家", "北京", "朝阳区"],
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
    
    # 构建知识图谱
    print("\n构建知识图谱...")
    lore_book.build_knowledge_graph(use_llm=False)
    
    # 获取图谱统计
    stats = lore_book.get_graph_statistics()
    print(f"\n图谱统计:")
    print(f"  节点数: {stats.get('node_count')}")
    print(f"  边数: {stats.get('edge_count')}")
    print(f"  平均度: {stats.get('avg_degree', 0):.2f}")
    print(f"  密度: {stats.get('density', 0):.4f}")
    print(f"  关系类型: {stats.get('relation_types')}")
    
    print("\n✅ 构建知识图谱测试完成")


def test_find_related_knowledge():
    """测试查找相关知识"""
    print("\n" + "="*60)
    print("测试 2: 查找相关知识")
    print("="*60)
    
    lore_book = LoreBook()
    
    # 获取所有知识
    all_lores = lore_book.get_all_lores()
    if not all_lores:
        print("  没有知识可供测试")
        return
    
    # 选择第一个知识
    first_lore = all_lores[0]
    print(f"\n查找与 '{first_lore['title']}' 相关的知识...")
    
    # 查找相关知识
    related = lore_book.find_related_knowledge_by_graph(
        knowledge_id=first_lore['id'],
        max_depth=2,
        min_confidence=0.3,
    )
    
    print(f"  找到 {len(related)} 个相关知识:")
    for i, lore in enumerate(related[:5], 1):
        graph_rel = lore.get('graph_relation', {})
        print(f"  {i}. {lore['title']}")
        print(f"     关系类型: {graph_rel.get('relation_type')}")
        print(f"     置信度: {graph_rel.get('confidence', 0):.2f}")
        print(f"     深度: {graph_rel.get('depth')}")
        if graph_rel.get('description'):
            print(f"     描述: {graph_rel.get('description')}")
    
    print("\n✅ 查找相关知识测试完成")


def test_find_knowledge_path():
    """测试查找知识路径"""
    print("\n" + "="*60)
    print("测试 3: 查找知识路径")
    print("="*60)
    
    lore_book = LoreBook()
    
    # 获取所有知识
    all_lores = lore_book.get_all_lores()
    if len(all_lores) < 2:
        print("  知识数量不足，无法测试")
        return
    
    # 选择两个知识
    source_lore = all_lores[0]
    target_lore = all_lores[min(2, len(all_lores)-1)]
    
    print(f"\n查找从 '{source_lore['title']}' 到 '{target_lore['title']}' 的路径...")
    
    # 查找路径
    path = lore_book.find_knowledge_path(
        source_id=source_lore['id'],
        target_id=target_lore['id'],
    )
    
    if path:
        print(f"  找到路径 ({len(path)} 个节点):")
        for i, lore in enumerate(path, 1):
            print(f"  {i}. {lore['title']}")
    else:
        print("  未找到路径")
    
    print("\n✅ 查找知识路径测试完成")


def test_infer_relations():
    """测试知识推理"""
    print("\n" + "="*60)
    print("测试 4: 知识推理")
    print("="*60)
    
    lore_book = LoreBook()
    
    # 获取所有知识
    all_lores = lore_book.get_all_lores()
    if not all_lores:
        print("  没有知识可供测试")
        return
    
    # 选择第一个知识
    first_lore = all_lores[0]
    print(f"\n对 '{first_lore['title']}' 进行推理...")
    
    # 推理新关系
    inferences = lore_book.infer_new_relations(first_lore['id'])
    
    print(f"  推理出 {len(inferences)} 条新关系:")
    for i, inf in enumerate(inferences[:5], 1):
        print(f"  {i}. {inf.get('source_id')[:8]}... -> {inf.get('target_id')[:8]}...")
        print(f"     关系类型: {inf.get('relation_type')}")
        print(f"     置信度: {inf.get('confidence', 0):.2f}")
        print(f"     推理类型: {inf.get('inference_type')}")
        if inf.get('description'):
            print(f"     描述: {inf.get('description')}")
    
    print("\n✅ 知识推理测试完成")


if __name__ == "__main__":
    print("="*60)
    print("知识图谱系统测试 v2.30.43")
    print("="*60)
    
    try:
        test_build_knowledge_graph()
        test_find_related_knowledge()
        test_find_knowledge_path()
        test_infer_relations()
        
        print("\n" + "="*60)
        print("✅ 所有测试完成！")
        print("="*60)
    
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()

