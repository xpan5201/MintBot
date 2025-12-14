"""
Embedding 缓存模块 (v2.30.27)

提供 embedding 结果缓存，减少 API 调用，提升性能。

作者: MintChat Team
日期: 2025-11-16
"""

from __future__ import annotations

import hashlib
import json
import pickle
import time
from collections import OrderedDict
from threading import Lock
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
        self.memory_cache: "OrderedDict[str, Tuple[List[float], datetime]]" = OrderedDict()
        self.cache_hits = 0
        self.cache_misses = 0
        self._lock = Lock()

        # 索引写入节流：避免每次 set 都重写 index.json
        self._index_dirty = False
        self._dirty_count = 0
        self._last_index_save = time.monotonic()

        # 加载持久化缓存索引
        self.index_file = self.cache_dir / "index.json"
        self.cache_index = self._load_index()

        logger.info(
            "Embedding 缓存初始化完成 (目录: %s, 最大缓存: %d, TTL: %d天)",
            cache_dir,
            max_cache_size,
            cache_ttl_days,
        )

    def _load_index(self) -> Dict[str, Dict]:
        """加载缓存索引"""
        if self.index_file.exists():
            try:
                with open(self.index_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return data if isinstance(data, dict) else {}
            except Exception as e:
                logger.warning("加载缓存索引失败: %s", e)
        return {}

    def _write_index_file(self, snapshot: Dict[str, Dict]) -> None:
        """原子写入索引文件，避免中途崩溃导致 index.json 损坏。"""
        try:
            tmp_file = self.index_file.with_suffix(self.index_file.suffix + ".tmp")
            with open(tmp_file, "w", encoding="utf-8") as f:
                json.dump(snapshot, f, ensure_ascii=False, separators=(",", ":"))
            tmp_file.replace(self.index_file)
        except Exception as e:
            logger.error("保存缓存索引失败: %s", e)

    def _maybe_save_index(self, *, force: bool = False) -> None:
        """
        节流保存 index.json：
        - 默认累计一定次数或超过一定时间才落盘
        - `force=True` 用于 clear() 等关键路径确保一致性
        """
        snapshot: Optional[Dict[str, Dict]] = None
        with self._lock:
            if not force and not self._index_dirty:
                return

            now = time.monotonic()
            if not force:
                if self._dirty_count < 50 and (now - self._last_index_save) < 2.0:
                    return

            snapshot = dict(self.cache_index)
            self._index_dirty = False
            self._dirty_count = 0
            self._last_index_save = now

        if snapshot is not None:
            self._write_index_file(snapshot)

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
        now = datetime.now()

        # 1. 检查内存缓存
        with self._lock:
            cached = self.memory_cache.get(cache_key)
            if cached is not None:
                embedding, timestamp = cached
                if now - timestamp < self.cache_ttl:
                    self.cache_hits += 1
                    self.memory_cache.move_to_end(cache_key)
                    return embedding
                # 过期：移除
                self.memory_cache.pop(cache_key, None)

        # 2. 检查持久化缓存
        cache_file = self.cache_dir / f"{cache_key}.pkl"
        if cache_file.exists():
            try:
                with open(cache_file, "rb") as f:
                    data = pickle.load(f)

                embedding = data.get("embedding")
                timestamp_str = data.get("timestamp")
                if not isinstance(embedding, list) or not timestamp_str:
                    raise ValueError("缓存文件格式不正确")

                timestamp = datetime.fromisoformat(timestamp_str)
                # 检查是否过期
                if now - timestamp < self.cache_ttl:
                    with self._lock:
                        self.memory_cache[cache_key] = (embedding, timestamp)
                        self.memory_cache.move_to_end(cache_key)
                        self.cache_index.setdefault(cache_key, {"timestamp": timestamp_str, "model": model})
                        self.cache_hits += 1
                    return embedding

                # 过期：删除文件 + 索引（索引为 best-effort）
                try:
                    cache_file.unlink()
                except Exception:
                    pass
                with self._lock:
                    if cache_key in self.cache_index:
                        del self.cache_index[cache_key]
                        self._index_dirty = True
                        self._dirty_count += 1
                self._maybe_save_index()
            except Exception as e:
                logger.warning("加载缓存失败 (%s): %s", cache_key, e)

        with self._lock:
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
        with self._lock:
            self.memory_cache[cache_key] = (embedding, timestamp)
            self.memory_cache.move_to_end(cache_key)

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
            with self._lock:
                self.cache_index[cache_key] = {
                    "timestamp": timestamp.isoformat(),
                    "model": model,
                }
                self._index_dirty = True
                self._dirty_count += 1

        except Exception as e:
            logger.error("保存缓存失败 (%s): %s", cache_key, e)

        # 3. 清理过大的内存缓存
        with self._lock:
            if self.max_cache_size > 0:
                while len(self.memory_cache) > self.max_cache_size:
                    self.memory_cache.popitem(last=False)

        self._maybe_save_index()

    def get_stats(self) -> Dict:
        """获取缓存统计"""
        with self._lock:
            hits = self.cache_hits
            misses = self.cache_misses
            memory_size = len(self.memory_cache)
            disk_size = len(self.cache_index)

        total_requests = hits + misses
        hit_rate = hits / total_requests * 100 if total_requests > 0 else 0

        return {
            "cache_hits": hits,
            "cache_misses": misses,
            "hit_rate": f"{hit_rate:.1f}%",
            "memory_cache_size": memory_size,
            "disk_cache_size": disk_size,
        }

    def clear(self):
        """清空所有缓存"""
        with self._lock:
            self.memory_cache.clear()
            self.cache_index.clear()
            self._index_dirty = True
            self._dirty_count += 1
        self._maybe_save_index(force=True)

        # 删除所有缓存文件
        for cache_file in self.cache_dir.glob("*.pkl"):
            cache_file.unlink()

        logger.info("已清空所有缓存")
