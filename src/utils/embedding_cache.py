"""
Embedding 缓存模块 (v2.30.27)

提供 embedding 结果缓存，减少 API 调用，提升性能。

作者: MintChat Team
日期: 2025-11-16
"""

import hashlib
import json
import pickle
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta

from src.utils.logger import get_logger

logger = get_logger(__name__)


class EmbeddingCache:
    """Embedding 缓存管理器"""

    def __init__(
        self,
        cache_dir: str = "data/cache/embeddings",
        max_cache_size: int = 10000,
        cache_ttl_days: int = 30,
    ):
        """
        初始化缓存管理器

        Args:
            cache_dir: 缓存目录
            max_cache_size: 最大缓存数量
            cache_ttl_days: 缓存过期天数
        """
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        self.max_cache_size = max_cache_size
        self.cache_ttl = timedelta(days=cache_ttl_days)

        # 内存缓存（LRU）
        self.memory_cache: Dict[str, Tuple[List[float], datetime]] = {}
        self.cache_hits = 0
        self.cache_misses = 0

        # 加载持久化缓存索引
        self.index_file = self.cache_dir / "index.json"
        self.cache_index = self._load_index()

        logger.info(
            f"Embedding 缓存初始化完成 "
            f"(目录: {cache_dir}, 最大缓存: {max_cache_size}, TTL: {cache_ttl_days}天)"
        )

    def _load_index(self) -> Dict[str, Dict]:
        """加载缓存索引"""
        if self.index_file.exists():
            try:
                with open(self.index_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"加载缓存索引失败: {e}")
        return {}

    def _save_index(self):
        """保存缓存索引"""
        try:
            with open(self.index_file, "w", encoding="utf-8") as f:
                json.dump(self.cache_index, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存缓存索引失败: {e}")

    def _get_cache_key(self, text: str, model: str) -> str:
        """生成缓存键"""
        content = f"{model}:{text}"
        return hashlib.md5(content.encode("utf-8")).hexdigest()

    def get(self, text: str, model: str) -> Optional[List[float]]:
        """
        获取缓存的 embedding

        Args:
            text: 文本
            model: 模型名称

        Returns:
            Optional[List[float]]: embedding 向量，未找到返回 None
        """
        cache_key = self._get_cache_key(text, model)

        # 1. 检查内存缓存
        if cache_key in self.memory_cache:
            embedding, timestamp = self.memory_cache[cache_key]
            if datetime.now() - timestamp < self.cache_ttl:
                self.cache_hits += 1
                return embedding

        # 2. 检查持久化缓存
        if cache_key in self.cache_index:
            cache_file = self.cache_dir / f"{cache_key}.pkl"
            if cache_file.exists():
                try:
                    with open(cache_file, "rb") as f:
                        data = pickle.load(f)
                        embedding = data["embedding"]
                        timestamp = datetime.fromisoformat(data["timestamp"])

                        # 检查是否过期
                        if datetime.now() - timestamp < self.cache_ttl:
                            # 加载到内存缓存
                            self.memory_cache[cache_key] = (embedding, timestamp)
                            self.cache_hits += 1
                            return embedding
                        else:
                            # 删除过期缓存
                            cache_file.unlink()
                            del self.cache_index[cache_key]
                            self._save_index()
                except Exception as e:
                    logger.warning(f"加载缓存失败 ({cache_key}): {e}")

        self.cache_misses += 1
        return None

    def set(self, text: str, model: str, embedding: List[float]):
        """
        设置缓存

        Args:
            text: 文本
            model: 模型名称
            embedding: embedding 向量
        """
        cache_key = self._get_cache_key(text, model)
        timestamp = datetime.now()

        # 1. 保存到内存缓存
        self.memory_cache[cache_key] = (embedding, timestamp)

        # 2. 保存到持久化缓存
        try:
            cache_file = self.cache_dir / f"{cache_key}.pkl"
            with open(cache_file, "wb") as f:
                pickle.dump(
                    {
                        "embedding": embedding,
                        "timestamp": timestamp.isoformat(),
                        "text": text[:100],  # 保存前100个字符用于调试
                        "model": model,
                    },
                    f,
                )

            # 更新索引
            self.cache_index[cache_key] = {
                "timestamp": timestamp.isoformat(),
                "model": model,
            }
            self._save_index()

        except Exception as e:
            logger.error(f"保存缓存失败 ({cache_key}): {e}")

        # 3. 清理过大的内存缓存
        if len(self.memory_cache) > self.max_cache_size:
            self._cleanup_memory_cache()

    def _cleanup_memory_cache(self):
        """清理内存缓存（LRU）"""
        # 按时间戳排序，删除最旧的 20%
        sorted_items = sorted(
            self.memory_cache.items(),
            key=lambda x: x[1][1],
        )
        remove_count = len(sorted_items) // 5
        for key, _ in sorted_items[:remove_count]:
            del self.memory_cache[key]

        logger.debug(f"清理内存缓存: 删除 {remove_count} 条")

    def get_stats(self) -> Dict:
        """获取缓存统计"""
        total_requests = self.cache_hits + self.cache_misses
        hit_rate = (
            self.cache_hits / total_requests * 100 if total_requests > 0 else 0
        )

        return {
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "hit_rate": f"{hit_rate:.1f}%",
            "memory_cache_size": len(self.memory_cache),
            "disk_cache_size": len(self.cache_index),
        }

    def clear(self):
        """清空所有缓存"""
        self.memory_cache.clear()
        self.cache_index.clear()
        self._save_index()

        # 删除所有缓存文件
        for cache_file in self.cache_dir.glob("*.pkl"):
            cache_file.unlink()

        logger.info("已清空所有缓存")

