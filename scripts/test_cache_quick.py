"""
快速测试多级缓存功能 v2.30.44
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

from src.agent.performance_optimizer import MultiLevelCache


def test_multi_level_cache():
    """测试多级缓存"""
    print("="*60)
    print("测试多级缓存功能 v2.30.44")
    print("="*60)
    
    # 初始化缓存
    print("\n1. 初始化多级缓存...")
    cache = MultiLevelCache(
        redis_host="localhost",
        redis_port=6379,
        default_ttl=3600,
        max_memory_items=100,
    )
    print("✅ 初始化成功")
    
    # 获取初始统计
    stats = cache.get_stats()
    print(f"\n初始统计:")
    print(f"  Redis 连接: {'是' if stats['redis_connected'] else '否'}")
    print(f"  L1 大小: {stats['l1_size']}")
    
    # 测试设置和获取
    print("\n2. 测试设置和获取...")
    test_data = {
        "title": "测试知识",
        "content": "这是测试内容",
        "category": "test",
    }
    
    # 设置缓存
    cache.set("test_key", test_data, ttl=60, prefix="lorebook")
    print("✅ 设置缓存成功")
    
    # 获取缓存
    cached_data = cache.get("test_key", prefix="lorebook")
    if cached_data:
        print("✅ 获取缓存成功")
        print(f"  数据: {cached_data}")
    else:
        print("❌ 获取缓存失败")
    
    # 测试缓存命中
    print("\n3. 测试缓存命中...")
    for i in range(5):
        result = cache.get("test_key", prefix="lorebook")
        if result:
            print(f"  第 {i+1} 次: ✅ 命中")
        else:
            print(f"  第 {i+1} 次: ❌ 未命中")
    
    # 获取统计
    stats = cache.get_stats()
    print(f"\n缓存统计:")
    print(f"  L1 命中: {stats['l1_hits']}")
    print(f"  L2 命中: {stats['l2_hits']}")
    print(f"  未命中: {stats['misses']}")
    print(f"  设置次数: {stats['sets']}")
    print(f"  命中率: {stats['hit_rate']:.1%}")
    print(f"  L1 大小: {stats['l1_size']}")
    
    # 测试删除
    print("\n4. 测试删除...")
    cache.delete("test_key", prefix="lorebook")
    print("✅ 删除成功")
    
    # 验证删除
    result = cache.get("test_key", prefix="lorebook")
    if result is None:
        print("✅ 验证删除成功")
    else:
        print("❌ 验证删除失败")
    
    # 测试清除
    print("\n5. 测试清除...")
    cache.set("key1", "value1", prefix="lorebook")
    cache.set("key2", "value2", prefix="lorebook")
    cache.set("key3", "value3", prefix="lorebook")
    print("✅ 设置 3 个缓存")
    
    cache.clear(prefix="lorebook")
    print("✅ 清除缓存成功")
    
    # 验证清除
    result1 = cache.get("key1", prefix="lorebook")
    result2 = cache.get("key2", prefix="lorebook")
    result3 = cache.get("key3", prefix="lorebook")
    
    if result1 is None and result2 is None and result3 is None:
        print("✅ 验证清除成功")
    else:
        print("❌ 验证清除失败")
    
    # 最终统计
    stats = cache.get_stats()
    print(f"\n最终统计:")
    print(f"  L1 命中: {stats['l1_hits']}")
    print(f"  L2 命中: {stats['l2_hits']}")
    print(f"  未命中: {stats['misses']}")
    print(f"  设置次数: {stats['sets']}")
    print(f"  命中率: {stats['hit_rate']:.1%}")
    print(f"  L1 大小: {stats['l1_size']}")
    
    print("\n" + "="*60)
    print("✅ 所有测试完成！")
    print("="*60)


if __name__ == "__main__":
    try:
        test_multi_level_cache()
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()

