"""
测试内置工具系统 - v2.30.25
测试性能监控增强、智能缓存预热、批量操作扩展等新功能

作者: MintChat Team
日期: 2025-11-16
"""

import sys
from pathlib import Path
import asyncio
import json

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from loguru import logger
from src.agent.builtin_tools import (
    bing_web_search,
    amap_batch_weather,
    amap_batch_poi_search,
    get_tool_statistics,
    ConnectionPool,
    warmup_cache,
    generate_performance_report,
    _bing_cache,
    _amap_cache,
)


def test_batch_weather():
    """测试批量天气查询 (v2.30.25 新增)"""
    print("\n" + "=" * 60)
    print("测试批量天气查询 (v2.30.25 新增)")
    print("=" * 60)
    
    result = amap_batch_weather.invoke({"cities": "北京;上海;广州", "extensions": "base"})
    print(f"✅ 批量天气查询结果:\n{result[:500]}...\n")


def test_batch_poi_search():
    """测试批量 POI 搜索 (v2.30.25 新增)"""
    print("\n" + "=" * 60)
    print("测试批量 POI 搜索 (v2.30.25 新增)")
    print("=" * 60)
    
    result = amap_batch_poi_search.invoke({"keywords_list": "咖啡馆;餐厅", "city": "北京", "limit": 3})
    print(f"✅ 批量 POI 搜索结果:\n{result[:500]}...\n")


async def test_cache_warmup():
    """测试智能缓存预热 (v2.30.25 新增)"""
    print("\n" + "=" * 60)
    print("测试智能缓存预热 (v2.30.25 新增)")
    print("=" * 60)
    
    await warmup_cache()
    print(f"✅ 缓存预热完成")
    print(f"✅ 高德缓存大小: {len(_amap_cache.cache)}\n")


def test_performance_stats_enhanced():
    """测试性能统计增强 (v2.30.25 新增)"""
    print("\n" + "=" * 60)
    print("测试性能统计增强 (v2.30.25 新增)")
    print("=" * 60)
    
    stats = get_tool_statistics()
    stats_dict = json.loads(stats)
    
    print("✅ 性能统计（包含 P50/P95/P99 延迟和缓存命中率）:")
    for tool_name, tool_stats in stats_dict.items():
        if tool_stats.get("call_count", 0) > 0:
            print(f"\n  {tool_name}:")
            print(f"    调用次数: {tool_stats.get('call_count')}")
            print(f"    平均耗时: {tool_stats.get('avg_time')}")
            print(f"    P50 延迟: {tool_stats.get('p50_latency')}")
            print(f"    P95 延迟: {tool_stats.get('p95_latency')}")
            print(f"    P99 延迟: {tool_stats.get('p99_latency')}")
            print(f"    缓存命中: {tool_stats.get('cache_hits')}")
            print(f"    缓存命中率: {tool_stats.get('cache_hit_rate')}")
            print(f"    成功率: {tool_stats.get('success_rate')}")


async def test_connection_pool_stats():
    """测试连接池统计 (v2.30.25 新增)"""
    print("\n" + "=" * 60)
    print("测试连接池统计 (v2.30.25 新增)")
    print("=" * 60)
    
    stats = ConnectionPool.get_pool_stats()
    print(f"✅ 连接池状态: {stats.get('status')}")
    print(f"✅ 总连接数限制: {stats.get('total_connections')}")
    print(f"✅ 每主机连接数限制: {stats.get('limit_per_host')}")
    print(f"✅ 活跃连接数: {stats.get('active_connections')}\n")


def test_performance_report():
    """测试性能监控报告生成 (v2.30.26 新增)"""
    print("\n" + "=" * 60)
    print("测试性能监控报告生成 (v2.30.26 新增)")
    print("=" * 60)

    report_path = generate_performance_report()
    print(f"✅ 性能监控报告已生成: {report_path}\n")


def main():
    """主测试函数"""
    print("\n" + "=" * 60)
    print("内置工具系统 v2.30.26 测试")
    print("=" * 60)

    try:
        # 测试智能缓存预热 (v2.30.25 新增)
        asyncio.run(test_cache_warmup())

        # 测试批量天气查询 (v2.30.25 新增)
        test_batch_weather()

        # 测试批量 POI 搜索 (v2.30.25 新增)
        test_batch_poi_search()

        # 测试连接池统计 (v2.30.25 新增)
        asyncio.run(test_connection_pool_stats())

        # 测试性能统计增强 (v2.30.25 新增)
        test_performance_stats_enhanced()

        # 测试性能监控报告生成 (v2.30.26 新增)
        test_performance_report()

        print("\n" + "=" * 60)
        print("✅ 所有测试完成！")
        print("=" * 60)

    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()

