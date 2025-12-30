"""
异步向量检索优化 (v2.29.12)

提供异步向量检索功能，提升性能和响应速度。
- v2.29.12: 集成新的异步优化器，支持批量执行和智能缓存
"""

import asyncio
from typing import List, Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor
import time

from src.utils.logger import get_logger
from src.utils.vector_cache import get_vector_search_cache, get_embedding_cache
from src.utils.async_optimizer import AsyncBatchExecutor, async_timed

logger = get_logger(__name__)


class AsyncVectorSearch:
    """异步向量检索器"""

    def __init__(self, vectorstore, max_workers: int = 4):
        """
        初始化异步向量检索器

        Args:
            vectorstore: 向量数据库实例
            max_workers: 最大工作线程数
        """
        self.vectorstore = vectorstore
        self.executor = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="AsyncVectorSearch"
        )
        self.vector_cache = get_vector_search_cache()
        self.embedding_cache = get_embedding_cache()
        self.batch_executor = AsyncBatchExecutor(max_concurrent=max_workers)

        logger.info(f"异步向量检索器初始化 (工作线程数: {max_workers})")

    @async_timed
    async def search_async(
        self, query: str, k: int = 5, filter_dict: Optional[Dict] = None
    ) -> List[Dict[str, Any]]:
        """
        异步向量检索 (v2.29.12: 添加性能监控)

        Args:
            query: 查询文本
            k: 返回数量
            filter_dict: 过滤条件

        Returns:
            检索结果列表
        """
        # 1. 检查缓存
        cached_results = self.vector_cache.get(query, k, filter_dict)
        if cached_results is not None:
            logger.debug("向量检索缓存命中")
            return cached_results

        # 2. 异步执行检索
        loop = asyncio.get_running_loop()  # Python 3.7+ 推荐方式
        results = await loop.run_in_executor(
            self.executor, self._search_sync, query, k, filter_dict
        )

        # 3. 存入缓存
        self.vector_cache.put(query, k, results, filter_dict)

        return results

    def _search_sync(self, query: str, k: int, filter_dict: Optional[Dict]) -> List[Dict[str, Any]]:
        """
        同步向量检索（在线程池中执行）

        Args:
            query: 查询文本
            k: 返回数量
            filter_dict: 过滤条件

        Returns:
            检索结果列表
        """
        try:
            if filter_dict:
                results = self.vectorstore.similarity_search_with_score(
                    query, k=k, filter=filter_dict
                )
            else:
                results = self.vectorstore.similarity_search_with_score(query, k=k)

            # 转换为字典格式
            formatted_results = []
            for doc, score in results:
                formatted_results.append(
                    {
                        "content": doc.page_content,
                        "metadata": doc.metadata,
                        "score": float(score),
                    }
                )

            return formatted_results

        except Exception as e:
            logger.error(f"向量检索失败: {e}")
            return []

    @async_timed
    async def batch_search_async(
        self, queries: List[str], k: int = 5, filter_dict: Optional[Dict] = None
    ) -> List[List[Dict[str, Any]]]:
        """
        批量异步向量检索 (v2.29.12: 使用批量执行器优化)

        Args:
            queries: 查询文本列表
            k: 每个查询返回数量
            filter_dict: 过滤条件

        Returns:
            检索结果列表的列表
        """

        # 使用批量执行器并发执行所有查询
        async def create_task(query: str):
            return await self.search_async(query, k, filter_dict)

        tasks = [lambda q=query: create_task(q) for query in queries]
        results = await self.batch_executor.execute_batch(tasks, timeout=30.0)

        logger.info(f"批量向量检索完成 ({len(queries)}个查询)")
        return results

    async def get_embedding_async(self, text: str) -> List[float]:
        """
        异步获取文本嵌入向量

        Args:
            text: 文本

        Returns:
            嵌入向量
        """
        # 1. 检查缓存
        cached_embedding = self.embedding_cache.get(text)
        if cached_embedding is not None:
            logger.debug("嵌入向量缓存命中")
            return cached_embedding

        # 2. 异步计算嵌入
        loop = asyncio.get_running_loop()  # Python 3.7+ 推荐方式
        embedding = await loop.run_in_executor(self.executor, self._get_embedding_sync, text)

        # 3. 存入缓存
        if embedding:
            self.embedding_cache.put(text, embedding)

        return embedding

    def _get_embedding_sync(self, text: str) -> List[float]:
        """
        同步获取嵌入向量（在线程池中执行）

        Args:
            text: 文本

        Returns:
            嵌入向量
        """
        try:
            # 使用vectorstore的embedding函数
            if hasattr(self.vectorstore, "_embedding_function"):
                embedding = self.vectorstore._embedding_function.embed_query(text)
                return embedding
            else:
                logger.warning("向量数据库没有embedding函数")
                return []
        except Exception as e:
            logger.error(f"获取嵌入向量失败: {e}")
            return []

    async def batch_get_embeddings_async(self, texts: List[str]) -> List[List[float]]:
        """
        批量异步获取嵌入向量

        Args:
            texts: 文本列表

        Returns:
            嵌入向量列表
        """
        start_time = time.time()

        # 并发执行所有嵌入计算
        tasks = [self.get_embedding_async(text) for text in texts]

        embeddings = await asyncio.gather(*tasks)

        elapsed = (time.time() - start_time) * 1000
        logger.info(f"批量嵌入计算完成 ({len(texts)}个文本)，耗时: {elapsed:.2f}ms")

        return list(embeddings)

    def close(self):
        """关闭线程池"""
        self.executor.shutdown(wait=True)
        logger.info("异步向量检索器已关闭")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


# 全局异步向量检索器实例
_async_vector_search_instance: Optional[AsyncVectorSearch] = None


def get_async_vector_search(vectorstore, max_workers: int = 4) -> AsyncVectorSearch:
    """
    获取全局异步向量检索器实例

    Args:
        vectorstore: 向量数据库实例
        max_workers: 最大工作线程数

    Returns:
        AsyncVectorSearch实例
    """
    global _async_vector_search_instance

    if _async_vector_search_instance is None:
        _async_vector_search_instance = AsyncVectorSearch(vectorstore, max_workers)

    return _async_vector_search_instance


def close_async_vector_search():
    """关闭全局异步向量检索器"""
    global _async_vector_search_instance

    if _async_vector_search_instance is not None:
        _async_vector_search_instance.close()
        _async_vector_search_instance = None
