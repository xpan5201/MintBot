"""
MintChat 性能测试脚本 v2.30.27

测试并发记忆检索的性能提升
"""

import sys
import time
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.agent.memory import MemoryManager
from src.agent.advanced_memory import CoreMemory, DiaryMemory, LoreBook
from src.agent.memory_retriever import ConcurrentMemoryRetriever
from src.utils.logger import logger


def test_serial_retrieval():
    """测试串行记忆检索（旧方法）"""
    logger.info("=" * 70)
    logger.info("测试串行记忆检索（旧方法）")
    logger.info("=" * 70)

    # 初始化记忆系统
    memory = MemoryManager()
    core_memory = CoreMemory()
    diary_memory = DiaryMemory()
    lore_book = LoreBook()

    test_query = "今天天气怎么样？"

    # 串行检索
    start_time = time.perf_counter()

    relevant_memories = memory.search_relevant_memories(test_query, k=5)
    core_memories = (
        core_memory.search_core_memories(test_query, k=2)
        if core_memory.vectorstore
        else []
    )
    diary_entries = (
        diary_memory.search_by_content(test_query, k=2)
        if diary_memory.vectorstore
        else []
    )
    lore_entries = (
        lore_book.search_lore(test_query, k=3)
        if lore_book.vectorstore
        else []
    )

    elapsed_ms = (time.perf_counter() - start_time) * 1000

    logger.info(f"串行检索完成: {elapsed_ms:.2f}ms")
    logger.info(f"  - 长期记忆: {len(relevant_memories)}条")
    logger.info(f"  - 核心记忆: {len(core_memories)}条")
    logger.info(f"  - 日记: {len(diary_entries)}条")
    logger.info(f"  - 知识库: {len(lore_entries)}条")

    return elapsed_ms


def test_concurrent_retrieval():
    """测试并发记忆检索（新方法）"""
    logger.info("=" * 70)
    logger.info("测试并发记忆检索（新方法）")
    logger.info("=" * 70)

    # 初始化记忆系统
    memory = MemoryManager()
    core_memory = CoreMemory()
    diary_memory = DiaryMemory()
    lore_book = LoreBook()

    # 初始化并发检索器
    retriever = ConcurrentMemoryRetriever(
        long_term_memory=memory,
        core_memory=core_memory,
        diary_memory=diary_memory,
        lore_book=lore_book,
        max_workers=4,
    )

    test_query = "今天天气怎么样？"

    # 并发检索
    start_time = time.perf_counter()

    memories = retriever.retrieve_all_memories_sync(
        query=test_query,
        long_term_k=5,
        core_k=2,
        diary_k=2,
        lore_k=3,
    )

    elapsed_ms = (time.perf_counter() - start_time) * 1000

    logger.info(f"并发检索完成: {elapsed_ms:.2f}ms")
    logger.info(f"  - 长期记忆: {len(memories['long_term'])}条")
    logger.info(f"  - 核心记忆: {len(memories['core'])}条")
    logger.info(f"  - 日记: {len(memories['diary'])}条")
    logger.info(f"  - 知识库: {len(memories['lore'])}条")

    # 性能统计
    stats = retriever.get_stats()
    logger.info(f"性能统计: {stats}")

    return elapsed_ms


def main():
    """主函数"""
    logger.info("=" * 70)
    logger.info("MintChat 性能测试 v2.30.27")
    logger.info("=" * 70)

    # 测试串行检索
    serial_time = test_serial_retrieval()

    logger.info("")

    # 测试并发检索
    concurrent_time = test_concurrent_retrieval()

    # 性能对比
    logger.info("")
    logger.info("=" * 70)
    logger.info("性能对比")
    logger.info("=" * 70)
    logger.info(f"串行检索: {serial_time:.2f}ms")
    logger.info(f"并发检索: {concurrent_time:.2f}ms")

    if serial_time > 0:
        speedup = serial_time / concurrent_time
        improvement = ((serial_time - concurrent_time) / serial_time) * 100
        logger.info(f"性能提升: {speedup:.2f}x ({improvement:.1f}%)")

        if concurrent_time < 50:
            logger.info("✅ 达到目标：<50ms")
        else:
            logger.warning(f"⚠️ 未达到目标：{concurrent_time:.2f}ms > 50ms")
    else:
        logger.warning("串行检索时间为0，无法计算性能提升")

    logger.info("=" * 70)


if __name__ == "__main__":
    main()

