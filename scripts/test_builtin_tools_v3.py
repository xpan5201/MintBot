"""
测试内置工具系统 - v2.30.24
测试连接池、重试机制、TTL 缓存、批量操作等新功能

作者: MintChat Team
日期: 2025-11-16
"""

import sys
from pathlib import Path
import asyncio

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from loguru import logger
from src.agent.builtin_tools import (
    bing_web_search,
    amap_poi_search,
    amap_geocode,
    amap_batch_geocode,
    amap_batch_route_plan,
    get_tool_statistics,
    ConnectionPool,
    _bing_cache,
    _amap_cache,
)


def test_bing_search_with_cache():
    """测试 Bing 搜索（带缓存）"""
    print("\n" + "=" * 60)
    print("测试 Bing 搜索（带缓存）")
    print("=" * 60)
    
    # 第一次调用（无缓存）
    print("\n第一次调用（无缓存）:")
    result1 = bing_web_search.invoke({"query": "Python 3.13 新特性", "count": 3})
    print(f"✅ 搜索结果:\n{result1[:200]}...\n")
    
    # 第二次调用（应该命中缓存）
    print("第二次调用（应该命中缓存）:")
    result2 = bing_web_search.invoke({"query": "Python 3.13 新特性", "count": 3})
    print(f"✅ 搜索结果:\n{result2[:200]}...\n")
    
    # 验证结果一致
    if result1 == result2:
        print("✅ 缓存验证成功：两次结果一致")
    else:
        print("❌ 缓存验证失败：两次结果不一致")


def test_amap_poi_search():
    """测试高德 POI 搜索"""
    print("\n" + "=" * 60)
    print("测试高德 POI 搜索")
    print("=" * 60)
    
    result = amap_poi_search.invoke({"keywords": "咖啡馆", "city": "北京", "limit": 3})
    print(f"✅ 搜索结果:\n{result[:300]}...\n")


def test_parameter_validation():
    """测试参数验证"""
    print("\n" + "=" * 60)
    print("测试参数验证")
    print("=" * 60)
    
    # 测试空查询
    print("\n测试空查询:")
    result = bing_web_search.invoke({"query": "", "count": 3})
    print(f"✅ 结果: {result}\n")
    
    # 测试无效数量
    print("测试无效数量:")
    result = bing_web_search.invoke({"query": "Python", "count": 100})
    print(f"✅ 结果: {result}\n")


def test_performance_stats():
    """测试性能统计"""
    print("\n" + "=" * 60)
    print("测试性能统计")
    print("=" * 60)
    
    stats = get_tool_statistics()
    print(f"✅ 性能统计:\n{stats}\n")


async def test_connection_pool():
    """测试连接池"""
    print("\n" + "=" * 60)
    print("测试连接池")
    print("=" * 60)
    
    session = await ConnectionPool.get_session()
    print(f"✅ 连接池状态: {'已创建' if session and not session.closed else '未创建'}")
    print(f"✅ 连接数限制: {session.connector.limit if session else 'N/A'}")
    print(f"✅ 每主机连接数限制: {session.connector.limit_per_host if session else 'N/A'}\n")


async def test_cache_stats():
    """测试缓存统计"""
    print("\n" + "=" * 60)
    print("测试缓存统计")
    print("=" * 60)

    print(f"✅ Bing 缓存大小: {len(_bing_cache.cache)}")
    print(f"✅ 高德缓存大小: {len(_amap_cache.cache)}\n")


def test_batch_geocode():
    """测试批量地理编码"""
    print("\n" + "=" * 60)
    print("测试批量地理编码 (v2.30.24 新增)")
    print("=" * 60)

    result = amap_batch_geocode.invoke({"addresses": "天安门;故宫;鸟巢", "city": "北京"})
    print(f"✅ 批量地理编码结果:\n{result[:500]}...\n")


def test_batch_route_plan():
    """测试批量路线规划"""
    print("\n" + "=" * 60)
    print("测试批量路线规划 (v2.30.24 新增)")
    print("=" * 60)

    # 天安门→故宫; 故宫→鸟巢
    routes = "116.397128,39.916527,116.397477,39.918058;116.397477,39.918058,116.402544,39.992831"
    result = amap_batch_route_plan.invoke({"routes": routes, "strategy": 0})
    print(f"✅ 批量路线规划结果:\n{result[:500]}...\n")


def main():
    """主测试函数"""
    print("\n" + "=" * 60)
    print("内置工具系统 v2.30.24 测试")
    print("=" * 60)

    try:
        # 测试 Bing 搜索（带缓存）
        test_bing_search_with_cache()

        # 测试高德 POI 搜索
        test_amap_poi_search()

        # 测试参数验证
        test_parameter_validation()

        # 测试批量地理编码 (v2.30.24 新增)
        test_batch_geocode()

        # 测试批量路线规划 (v2.30.24 新增)
        test_batch_route_plan()

        # 测试连接池
        asyncio.run(test_connection_pool())

        # 测试缓存统计
        asyncio.run(test_cache_stats())

        # 测试性能统计
        test_performance_stats()

        print("\n" + "=" * 60)
        print("✅ 所有测试完成！")
        print("=" * 60)

    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()

