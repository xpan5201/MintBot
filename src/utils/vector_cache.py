"""
向量检索缓存优化模块 (v2.29.0)

提供智能缓存机制，优化ChromaDB向量检索性能。

特性:
- 🚀 查询结果缓存 - 避免重复检索
- 🧠 嵌入向量缓存 - 避免重复计算
- 🔄 LRU淘汰策略 - 自动管理缓存大小
- ⏰ TTL过期机制 - 自动清理过期缓存
- 📊 性能统计 - 监控缓存命中率
"""

import hashlib
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class CacheEntry:
    """缓存条目"""
    value: Any
    timestamp: float = field(default_factory=time.time)
    access_count: int = 0
    last_access: float = field(default_factory=time.time)


class VectorSearchCache:
    """
    向量检索缓存

    使用LRU策略和TTL机制管理缓存，优化向量检索性能。
    """

    def __init__(
        self,
        max_size: int = 1000,
        ttl_seconds: int = 3600,
        enable_stats: bool = True,
    ):
        """
        初始化向量检索缓存

        Args:
            max_size: 最大缓存条目数
            ttl_seconds: 缓存过期时间（秒）
            enable_stats: 是否启用统计
        """
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self.enable_stats = enable_stats

        # 使用OrderedDict实现LRU
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()

        # 统计信息
        self._stats = {
            "hits": 0,
            "misses": 0,
            "evictions": 0,
            "expirations": 0,
            "total_queries": 0,
        }

        logger.info(f"向量检索缓存初始化: max_size={max_size}, ttl={ttl_seconds}s")

    def _generate_key(self, query: str, k: int, filter_dict: Optional[Dict] = None) -> str:
        """
        生成缓存键

        Args:
            query: 查询文本
            k: 返回数量
            filter_dict: 过滤条件

        Returns:
            缓存键
        """
        # 标准化查询（去除多余空格、转小写）
        import re
        normalized_query = re.sub(r'\s+', ' ', query.strip().lower())

        # 生成唯一键
        key_parts = [normalized_query, str(k)]
        if filter_dict:
            key_parts.append(str(sorted(filter_dict.items())))

        key_string = "|".join(key_parts)

        # 使用MD5生成短键（避免键过长）
        return hashlib.md5(key_string.encode()).hexdigest()

    def get(
        self,
        query: str,
        k: int,
        filter_dict: Optional[Dict] = None,
    ) -> Optional[List[Dict[str, Any]]]:
        """
        从缓存获取检索结果

        Args:
            query: 查询文本
            k: 返回数量
            filter_dict: 过滤条件

        Returns:
            缓存的检索结果，如果不存在或过期则返回None
        """
        if self.enable_stats:
            self._stats["total_queries"] += 1

        key = self._generate_key(query, k, filter_dict)

        if key not in self._cache:
            if self.enable_stats:
                self._stats["misses"] += 1
            return None

        entry = self._cache[key]

        # 检查是否过期
        if time.time() - entry.timestamp > self.ttl_seconds:
            del self._cache[key]
            if self.enable_stats:
                self._stats["expirations"] += 1
                self._stats["misses"] += 1
            logger.debug(f"缓存过期: {query[:30]}...")
            return None

        # 更新访问信息
        entry.access_count += 1
        entry.last_access = time.time()

        # 移到末尾（LRU）
        self._cache.move_to_end(key)

        if self.enable_stats:
            self._stats["hits"] += 1

        logger.debug(f"缓存命中: {query[:30]}... (访问次数: {entry.access_count})")
        return entry.value

    def put(
        self,
        query: str,
        k: int,
        results: List[Dict[str, Any]],
        filter_dict: Optional[Dict] = None,
    ) -> None:
        """
        将检索结果放入缓存

        Args:
            query: 查询文本
            k: 返回数量
            results: 检索结果
            filter_dict: 过滤条件
        """
        key = self._generate_key(query, k, filter_dict)

        # 检查缓存大小，必要时淘汰最旧的条目
        if len(self._cache) >= self.max_size:
            # 移除最旧的条目（FIFO）
            oldest_key = next(iter(self._cache))
            del self._cache[oldest_key]
            if self.enable_stats:
                self._stats["evictions"] += 1
            logger.debug(f"缓存淘汰: 达到最大大小 {self.max_size}")

        # 添加新条目
        self._cache[key] = CacheEntry(value=results)
        logger.debug(f"缓存添加: {query[:30]}... (当前大小: {len(self._cache)})")

    def clear(self) -> None:
        """清空缓存"""
        self._cache.clear()
        logger.info("向量检索缓存已清空")

    def cleanup_expired(self) -> int:
        """
        清理过期缓存

        Returns:
            清理的条目数
        """
        current_time = time.time()
        expired_keys = [
            key for key, entry in self._cache.items()
            if current_time - entry.timestamp > self.ttl_seconds
        ]

        for key in expired_keys:
            del self._cache[key]

        if expired_keys:
            if self.enable_stats:
                self._stats["expirations"] += len(expired_keys)
            logger.info(f"清理了 {len(expired_keys)} 个过期缓存条目")

        return len(expired_keys)

    def get_stats(self) -> Dict[str, Any]:
        """
        获取缓存统计信息

        Returns:
            统计信息字典
        """
        if not self.enable_stats:
            return {}

        total_queries = self._stats["total_queries"]
        hits = self._stats["hits"]

        hit_rate = (hits / total_queries) if total_queries > 0 else 0

        return {
            "cache_size": len(self._cache),
            "max_size": self.max_size,
            "hit_rate": hit_rate,
            "total_queries": total_queries,
            "hits": hits,
            "misses": self._stats["misses"],
            "evictions": self._stats["evictions"],
            "expirations": self._stats["expirations"],
        }

    def print_stats(self) -> None:
        """打印缓存统计信息"""
        stats = self.get_stats()
        if not stats:
            logger.info("缓存统计未启用")
            return

        logger.info("=" * 50)
        logger.info("向量检索缓存统计")
        logger.info("=" * 50)
        for key, value in stats.items():
            logger.info(f"{key}: {value}")
        logger.info("=" * 50)


class EmbeddingCache:
    """
    嵌入向量缓存

    缓存文本的嵌入向量，避免重复计算。
    """

    def __init__(
        self,
        max_size: int = 500,
        ttl_seconds: int = 7200,
    ):
        """
        初始化嵌入向量缓存

        Args:
            max_size: 最大缓存条目数
            ttl_seconds: 缓存过期时间（秒）
        """
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds

        # 使用OrderedDict实现LRU
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()

        logger.info(f"嵌入向量缓存初始化: max_size={max_size}, ttl={ttl_seconds}s")

    def _generate_key(self, text: str) -> str:
        """生成缓存键"""
        # 标准化文本（去除多余空格、转小写）
        import re
        normalized_text = re.sub(r'\s+', ' ', text.strip().lower())
        # 使用MD5生成短键
        return hashlib.md5(normalized_text.encode()).hexdigest()

    def get(self, text: str) -> Optional[List[float]]:
        """获取嵌入向量"""
        key = self._generate_key(text)

        if key not in self._cache:
            return None

        entry = self._cache[key]

        # 检查是否过期
        if time.time() - entry.timestamp > self.ttl_seconds:
            del self._cache[key]
            return None

        # 更新访问信息
        entry.access_count += 1
        entry.last_access = time.time()

        # 移到末尾（LRU）
        self._cache.move_to_end(key)

        return entry.value

    def put(self, text: str, embedding: List[float]) -> None:
        """存储嵌入向量"""
        key = self._generate_key(text)

        # 检查缓存大小
        if len(self._cache) >= self.max_size:
            # 移除最旧的条目
            oldest_key = next(iter(self._cache))
            del self._cache[oldest_key]

        # 添加新条目
        self._cache[key] = CacheEntry(value=embedding)

    def clear(self) -> None:
        """清空缓存"""
        self._cache.clear()
        logger.info("嵌入向量缓存已清空")

    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        total_accesses = sum(entry.access_count for entry in self._cache.values())

        return {
            "cache_size": len(self._cache),
            "max_size": self.max_size,
            "total_accesses": total_accesses,
            "hit_rate": 0.0,  # EmbeddingCache没有命中率统计
        }


# 全局缓存实例
_vector_search_cache: Optional[VectorSearchCache] = None
_embedding_cache: Optional[EmbeddingCache] = None


def get_vector_search_cache() -> VectorSearchCache:
    """获取全局向量检索缓存实例"""
    global _vector_search_cache
    if _vector_search_cache is None:
        _vector_search_cache = VectorSearchCache()
    return _vector_search_cache


def get_embedding_cache() -> EmbeddingCache:
    """获取全局嵌入向量缓存实例"""
    global _embedding_cache
    if _embedding_cache is None:
        _embedding_cache = EmbeddingCache()
    return _embedding_cache

