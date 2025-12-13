"""
测试性能优化 v2.30.44

测试内容：
1. 多级缓存性能
2. 异步处理性能
3. ChromaDB 参数优化
4. 整体性能对比
"""

import sys
import os
import time
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


def test_cache_performance():
    """测试缓存性能"""
    print("\n" + "="*60)
    print("测试 1: 多级缓存性能")
    print("="*60)
    
    lore_book = LoreBook()
    
    # 添加测试知识
    print("\n添加测试知识...")
    test_lores = []
    for i in range(20):
        lore_id = lore_book.add_lore(
            title=f"测试知识 {i+1}",
            content=f"这是第 {i+1} 条测试知识，用于测试缓存性能。",
            category="test",
            keywords=[f"测试{i+1}", "缓存", "性能"],
            source="test",
            skip_quality_check=True,
        )
        if lore_id:
            test_lores.append(lore_id)
    
    print(f"✅ 添加成功: {len(test_lores)} 条")
    
    # 测试搜索性能（无缓存）
    print("\n测试搜索性能（无缓存）...")
    query = "测试知识"
    
    times_no_cache = []
    for i in range(5):
        start = time.time()
        results = lore_book.search_lore(query, k=5, use_cache=False)
        elapsed = (time.time() - start) * 1000
        times_no_cache.append(elapsed)
        print(f"  第 {i+1} 次: {elapsed:.2f}ms，找到 {len(results)} 条")
    
    avg_no_cache = sum(times_no_cache) / len(times_no_cache)
    print(f"  平均时间: {avg_no_cache:.2f}ms")
    
    # 测试搜索性能（有缓存）
    print("\n测试搜索性能（有缓存）...")
    
    times_with_cache = []
    for i in range(5):
        start = time.time()
        results = lore_book.search_lore(query, k=5, use_cache=True)
        elapsed = (time.time() - start) * 1000
        times_with_cache.append(elapsed)
        print(f"  第 {i+1} 次: {elapsed:.2f}ms，找到 {len(results)} 条")
    
    avg_with_cache = sum(times_with_cache) / len(times_with_cache)
    print(f"  平均时间: {avg_with_cache:.2f}ms")
    
    # 计算提升
    speedup = avg_no_cache / avg_with_cache if avg_with_cache > 0 else 0
    print(f"\n🚀 缓存提升: {speedup:.1f}x")
    
    # 获取缓存统计
    if lore_book.multi_cache:
        stats = lore_book.multi_cache.get_stats()
        print(f"\n缓存统计:")
        print(f"  L1 命中: {stats['l1_hits']}")
        print(f"  L2 命中: {stats['l2_hits']}")
        print(f"  未命中: {stats['misses']}")
        print(f"  命中率: {stats['hit_rate']:.1%}")
        print(f"  L1 大小: {stats['l1_size']}")
        print(f"  Redis 连接: {'是' if stats['redis_connected'] else '否'}")
    
    print("\n✅ 缓存性能测试完成")


def test_batch_performance():
    """测试批量操作性能"""
    print("\n" + "="*60)
    print("测试 2: 批量操作性能")
    print("="*60)
    
    lore_book = LoreBook()
    
    # 准备测试数据
    test_lores = []
    for i in range(50):
        test_lores.append({
            "title": f"批量测试知识 {i+1}",
            "content": f"这是第 {i+1} 条批量测试知识。",
            "category": "batch_test",
            "keywords": [f"批量{i+1}", "测试"],
            "source": "batch_test",
        })
    
    # 测试批量添加
    print(f"\n批量添加 {len(test_lores)} 条知识...")
    start = time.time()
    added_ids = lore_book.batch_add_lores(test_lores)
    time_batch = (time.time() - start) * 1000
    print(f"✅ 批量添加成功: {len(added_ids)} 条")
    print(f"⏱️ 批量添加时间: {time_batch:.2f}ms")
    print(f"⏱️ 平均每条: {time_batch / len(added_ids):.2f}ms")
    
    print("\n✅ 批量操作性能测试完成")


def test_overall_performance():
    """测试整体性能"""
    print("\n" + "="*60)
    print("测试 3: 整体性能对比")
    print("="*60)
    
    lore_book = LoreBook()
    
    # 获取所有知识
    print("\n获取所有知识...")
    start = time.time()
    all_lores = lore_book.get_all_lores(use_cache=True)
    time_get_all = (time.time() - start) * 1000
    print(f"✅ 获取成功: {len(all_lores)} 条")
    print(f"⏱️ 获取时间: {time_get_all:.2f}ms")
    
    # 获取统计信息
    print("\n获取统计信息...")
    start = time.time()
    stats = lore_book.get_statistics()
    time_stats = (time.time() - start) * 1000
    print(f"✅ 统计信息:")
    print(f"  总数: {stats['total']}")
    print(f"  类别: {stats['by_category']}")
    print(f"⏱️ 统计时间: {time_stats:.2f}ms")
    
    # 搜索性能
    print("\n搜索性能...")
    queries = ["测试", "知识", "批量", "性能", "缓存"]
    total_time = 0
    total_results = 0
    
    for query in queries:
        start = time.time()
        results = lore_book.search_lore(query, k=5, use_cache=True)
        elapsed = (time.time() - start) * 1000
        total_time += elapsed
        total_results += len(results)
        print(f"  查询 '{query}': {elapsed:.2f}ms，找到 {len(results)} 条")
    
    avg_search_time = total_time / len(queries)
    print(f"  平均搜索时间: {avg_search_time:.2f}ms")
    
    print("\n✅ 整体性能测试完成")


if __name__ == "__main__":
    print("="*60)
    print("性能优化测试 v2.30.44")
    print("="*60)
    
    try:
        test_cache_performance()
        test_batch_performance()
        test_overall_performance()
        
        print("\n" + "="*60)
        print("✅ 所有测试完成！")
        print("="*60)
    
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()

