"""
测试 Embedding 缓存性能 (v2.30.27)

测试缓存对性能的提升效果。
"""

import sys
from pathlib import Path
import time

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.agent.memory import MemoryManager
from src.utils.logger import logger


def test_embedding_cache():
    """测试 embedding 缓存性能"""
    logger.info("=" * 70)
    logger.info("测试 Embedding 缓存性能 v2.30.27")
    logger.info("=" * 70)

    # 初始化记忆系统
    logger.info("\n初始化记忆系统...")
    memory = MemoryManager()

    # 测试查询
    test_queries = [
        "今天天气怎么样",
        "你喜欢什么颜色",
        "帮我查一下北京的天气",
        "你会做什么",
        "你叫什么名字",
    ]

    # 第一轮：无缓存（冷启动）
    logger.info("\n" + "=" * 70)
    logger.info("第一轮：冷启动（无缓存）")
    logger.info("=" * 70)

    first_round_times = []
    for query in test_queries:
        start_time = time.perf_counter()
        results = memory.search_relevant_memories(query, k=3)
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        first_round_times.append(elapsed_ms)
        logger.info(f"查询: '{query}' - {elapsed_ms:.2f}ms ({len(results)} 条结果)")

    avg_first = sum(first_round_times) / len(first_round_times)
    logger.info(f"\n平均时间: {avg_first:.2f}ms")

    # 第二轮：有缓存（热启动）
    logger.info("\n" + "=" * 70)
    logger.info("第二轮：热启动（有缓存）")
    logger.info("=" * 70)

    second_round_times = []
    for query in test_queries:
        start_time = time.perf_counter()
        results = memory.search_relevant_memories(query, k=3)
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        second_round_times.append(elapsed_ms)
        logger.info(f"查询: '{query}' - {elapsed_ms:.2f}ms ({len(results)} 条结果)")

    avg_second = sum(second_round_times) / len(second_round_times)
    logger.info(f"\n平均时间: {avg_second:.2f}ms")

    # 性能对比
    logger.info("\n" + "=" * 70)
    logger.info("性能对比")
    logger.info("=" * 70)
    logger.info(f"冷启动平均时间: {avg_first:.2f}ms")
    logger.info(f"热启动平均时间: {avg_second:.2f}ms")

    if avg_second > 0:
        speedup = avg_first / avg_second
        improvement = (1 - avg_second / avg_first) * 100
        logger.info(f"性能提升: {speedup:.2f}x ({improvement:.1f}%)")

        if improvement >= 50:
            logger.info("✅ 缓存效果显著！")
        elif improvement >= 20:
            logger.info("✅ 缓存效果良好")
        else:
            logger.warning("⚠️ 缓存效果不明显")
    else:
        logger.info("⚠️ 无法计算性能提升")

    # 缓存统计
    if hasattr(memory, "vectorstore") and hasattr(memory.vectorstore, "_embedding_function"):
        embedding_func = memory.vectorstore._embedding_function
        if hasattr(embedding_func, "get_stats"):
            logger.info("\n" + "=" * 70)
            logger.info("缓存统计")
            logger.info("=" * 70)
            stats = embedding_func.get_stats()
            for key, value in stats.items():
                logger.info(f"{key}: {value}")
    else:
        logger.info("\n⚠️ 当前使用的是 API embedding，缓存统计不可用")

    logger.info("\n" + "=" * 70)


if __name__ == "__main__":
    test_embedding_cache()

