"""
MintChat - 增强缓存管理器

提供智能缓存管理，支持：
- 自适应TTL（根据访问频率调整）
- 智能LRU（考虑访问频率和重要性）
- 缓存预热和持久化
- 内存监控和自动清理

v2.30.6 新增
"""

import time
import threading
import pickle
import hashlib
from pathlib import Path
from collections import OrderedDict
from typing import Dict, Any, Optional, Callable, TypeVar, Generic
from dataclasses import dataclass, field
from datetime import datetime
from src.utils.logger import get_logger

logger = get_logger(__name__)

T = TypeVar('T')


@dataclass
class CacheEntry(Generic[T]):
    """缓存条目"""
    key: str
    value: T
    created_at: float = field(default_factory=time.time)
    last_access: float = field(default_factory=time.time)
    access_count: int = 0
    ttl: float = 3600.0  # 默认1小时
    importance: float = 1.0  # 重要性权重（0-1）
    size_bytes: int = 0  # 估算大小（字节）
    
    def is_expired(self) -> bool:
        """检查是否过期"""
        return time.time() - self.created_at > self.ttl
    
    def update_access(self):
        """更新访问信息"""
        self.last_access = time.time()
        self.access_count += 1
    
    def get_score(self) -> float:
        """
        计算缓存条目的分数（用于LRU淘汰）
        分数越高，越不应该被淘汰
        
        考虑因素：
        - 访问频率
        - 最近访问时间
        - 重要性权重
        """
        # 访问频率分数（0-1）
        freq_score = min(self.access_count / 100.0, 1.0)
        
        # 时间衰减分数（0-1）
        time_since_access = time.time() - self.last_access
        time_score = max(0, 1.0 - time_since_access / self.ttl)
        
        # 综合分数
        return (freq_score * 0.4 + time_score * 0.4 + self.importance * 0.2)


@dataclass
class CacheStats:
    """缓存统计信息"""
    hits: int = 0
    misses: int = 0
    evictions: int = 0
    expirations: int = 0
    total_size_bytes: int = 0
    entry_count: int = 0
    
    @property
    def hit_rate(self) -> float:
        """命中率"""
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0


class EnhancedCache(Generic[T]):
    """增强缓存管理器"""
    
    def __init__(
        self,
        name: str,
        max_size: int = 1000,
        default_ttl: float = 3600.0,
        max_memory_mb: float = 100.0,
        enable_persistence: bool = False,
        persistence_path: Optional[Path] = None,
    ):
        """
        初始化增强缓存
        
        Args:
            name: 缓存名称
            max_size: 最大条目数
            default_ttl: 默认TTL（秒）
            max_memory_mb: 最大内存占用（MB）
            enable_persistence: 是否启用持久化
            persistence_path: 持久化文件路径
        """
        self.name = name
        self.max_size = max_size
        self.default_ttl = default_ttl
        self.max_memory_bytes = int(max_memory_mb * 1024 * 1024)
        self.enable_persistence = enable_persistence
        self.persistence_path = persistence_path or Path(f"data/cache/{name}.pkl")
        
        self._cache: OrderedDict[str, CacheEntry[T]] = OrderedDict()
        self._lock = threading.RLock()
        self._stats = CacheStats()
        
        # 加载持久化缓存
        if self.enable_persistence:
            self._load_from_disk()
        
        logger.info(
            f"增强缓存 '{name}' 初始化完成 "
            f"(max_size={max_size}, ttl={default_ttl}s, max_memory={max_memory_mb}MB)"
        )
    
    def _generate_key(self, key: Any) -> str:
        """生成缓存键"""
        if isinstance(key, str):
            return hashlib.md5(key.encode()).hexdigest()
        else:
            return hashlib.md5(str(key).encode()).hexdigest()
    
    def _estimate_size(self, value: T) -> int:
        """估算对象大小（字节）"""
        try:
            return len(pickle.dumps(value))
        except Exception:
            # 如果无法序列化，返回估算值
            return 1024  # 默认1KB
    
    def get(
        self,
        key: Any,
        default: Optional[T] = None,
    ) -> Optional[T]:
        """
        获取缓存值
        
        Args:
            key: 缓存键
            default: 默认值
            
        Returns:
            缓存值或默认值
        """
        cache_key = self._generate_key(key)
        
        with self._lock:
            if cache_key not in self._cache:
                self._stats.misses += 1
                return default
            
            entry = self._cache[cache_key]
            
            # 检查是否过期
            if entry.is_expired():
                del self._cache[cache_key]
                self._stats.expirations += 1
                self._stats.misses += 1
                self._update_total_size()
                return default
            
            # 更新访问信息
            entry.update_access()
            
            # 移到末尾（LRU）
            self._cache.move_to_end(cache_key)
            
            self._stats.hits += 1
            return entry.value

    def put(
        self,
        key: Any,
        value: T,
        ttl: Optional[float] = None,
        importance: float = 1.0,
    ) -> None:
        """
        存储缓存值

        Args:
            key: 缓存键
            value: 缓存值
            ttl: TTL（秒），None使用默认值
            importance: 重要性权重（0-1）
        """
        cache_key = self._generate_key(key)
        size_bytes = self._estimate_size(value)

        with self._lock:
            # 检查内存限制
            while (
                self._stats.total_size_bytes + size_bytes > self.max_memory_bytes
                and len(self._cache) > 0
            ):
                self._evict_one()

            # 检查条目数限制
            while len(self._cache) >= self.max_size:
                self._evict_one()

            # 创建缓存条目
            entry = CacheEntry(
                key=cache_key,
                value=value,
                ttl=ttl or self.default_ttl,
                importance=importance,
                size_bytes=size_bytes,
            )

            self._cache[cache_key] = entry
            self._cache.move_to_end(cache_key)

            self._update_total_size()

    def _evict_one(self) -> None:
        """淘汰一个缓存条目（智能LRU）"""
        if not self._cache:
            return

        # 计算所有条目的分数
        scored_entries = [
            (key, entry.get_score())
            for key, entry in self._cache.items()
        ]

        # 淘汰分数最低的
        if scored_entries:
            key_to_evict = min(scored_entries, key=lambda x: x[1])[0]
            del self._cache[key_to_evict]
            self._stats.evictions += 1

    def _update_total_size(self) -> None:
        """更新总大小统计"""
        self._stats.total_size_bytes = sum(
            entry.size_bytes for entry in self._cache.values()
        )
        self._stats.entry_count = len(self._cache)

    def cleanup_expired(self) -> int:
        """
        清理过期缓存

        Returns:
            清理的条目数
        """
        with self._lock:
            expired_keys = [
                key for key, entry in self._cache.items()
                if entry.is_expired()
            ]

            for key in expired_keys:
                del self._cache[key]

            if expired_keys:
                self._stats.expirations += len(expired_keys)
                self._update_total_size()
                logger.info(f"缓存 '{self.name}' 清理了 {len(expired_keys)} 个过期条目")

            return len(expired_keys)

    def clear(self) -> None:
        """清空缓存"""
        with self._lock:
            self._cache.clear()
            self._stats = CacheStats()
            logger.info(f"缓存 '{self.name}' 已清空")

    def get_stats(self) -> CacheStats:
        """获取统计信息"""
        with self._lock:
            self._update_total_size()
            return CacheStats(
                hits=self._stats.hits,
                misses=self._stats.misses,
                evictions=self._stats.evictions,
                expirations=self._stats.expirations,
                total_size_bytes=self._stats.total_size_bytes,
                entry_count=self._stats.entry_count,
            )

    def _save_to_disk(self) -> None:
        """保存缓存到磁盘"""
        if not self.enable_persistence:
            return

        try:
            self.persistence_path.parent.mkdir(parents=True, exist_ok=True)

            with self._lock:
                # 只保存未过期的条目
                valid_entries = {
                    key: entry
                    for key, entry in self._cache.items()
                    if not entry.is_expired()
                }

                with open(self.persistence_path, 'wb') as f:
                    pickle.dump(valid_entries, f)

                logger.info(
                    f"缓存 '{self.name}' 已保存到磁盘 "
                    f"({len(valid_entries)} 个条目)"
                )
        except Exception as e:
            logger.error(f"保存缓存到磁盘失败: {e}")

    def _load_from_disk(self) -> None:
        """从磁盘加载缓存"""
        if not self.enable_persistence or not self.persistence_path.exists():
            return

        try:
            with open(self.persistence_path, 'rb') as f:
                loaded_entries = pickle.load(f)

            with self._lock:
                # 只加载未过期的条目
                for key, entry in loaded_entries.items():
                    if not entry.is_expired():
                        self._cache[key] = entry

                self._update_total_size()

                logger.info(
                    f"缓存 '{self.name}' 从磁盘加载 "
                    f"({len(self._cache)} 个条目)"
                )
        except Exception as e:
            logger.error(f"从磁盘加载缓存失败: {e}")

    def __del__(self):
        """析构时保存缓存"""
        if self.enable_persistence:
            try:
                self._save_to_disk()
            except Exception:
                pass


class CacheManager:
    """全局缓存管理器 - 单例模式"""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, '_initialized'):
            return

        self._initialized = True
        self._caches: Dict[str, EnhancedCache] = {}
        self._global_lock = threading.Lock()
        self._warmup_callbacks: Dict[str, Callable] = {}  # v2.30.6: 预热回调

        logger.info("全局缓存管理器初始化完成")

    def register_cache(
        self,
        name: str,
        max_size: int = 1000,
        default_ttl: float = 3600.0,
        max_memory_mb: float = 100.0,
        enable_persistence: bool = False,
    ) -> EnhancedCache:
        """注册新的缓存"""
        with self._global_lock:
            if name in self._caches:
                return self._caches[name]

            cache = EnhancedCache(
                name=name,
                max_size=max_size,
                default_ttl=default_ttl,
                max_memory_mb=max_memory_mb,
                enable_persistence=enable_persistence,
            )
            self._caches[name] = cache

            return cache

    def get_cache(self, name: str) -> Optional[EnhancedCache]:
        """获取缓存"""
        with self._global_lock:
            return self._caches.get(name)

    def cleanup_all(self) -> Dict[str, int]:
        """清理所有缓存的过期条目"""
        results = {}
        with self._global_lock:
            for name, cache in self._caches.items():
                count = cache.cleanup_expired()
                if count > 0:
                    results[name] = count
        return results

    def get_all_stats(self) -> Dict[str, CacheStats]:
        """获取所有缓存的统计信息"""
        with self._global_lock:
            return {
                name: cache.get_stats()
                for name, cache in self._caches.items()
            }

    def register_warmup_callback(self, cache_name: str, callback: Callable[[EnhancedCache], None]) -> None:
        """
        注册缓存预热回调

        Args:
            cache_name: 缓存名称
            callback: 预热回调函数，接收缓存对象作为参数
        """
        with self._global_lock:
            self._warmup_callbacks[cache_name] = callback
            logger.info(f"已注册缓存 '{cache_name}' 的预热回调")

    def warmup_cache(self, cache_name: str) -> bool:
        """
        预热指定缓存

        Args:
            cache_name: 缓存名称

        Returns:
            是否成功预热
        """
        with self._global_lock:
            if cache_name not in self._caches:
                logger.warning(f"缓存 '{cache_name}' 不存在，无法预热")
                return False

            if cache_name not in self._warmup_callbacks:
                logger.warning(f"缓存 '{cache_name}' 没有注册预热回调")
                return False

            cache = self._caches[cache_name]
            callback = self._warmup_callbacks[cache_name]

        try:
            logger.info(f"开始预热缓存 '{cache_name}'...")
            start_time = time.time()

            callback(cache)

            elapsed = time.time() - start_time
            stats = cache.get_stats()
            logger.info(
                f"缓存 '{cache_name}' 预热完成，"
                f"耗时 {elapsed:.2f}秒，"
                f"加载 {stats.entry_count} 个条目"
            )
            return True
        except Exception as e:
            logger.error(f"预热缓存 '{cache_name}' 失败: {e}")
            return False

    def warmup_all(self, background: bool = True) -> Dict[str, bool]:
        """
        预热所有已注册回调的缓存

        Args:
            background: 是否在后台线程中预热

        Returns:
            每个缓存的预热结果
        """
        if background:
            # 在后台线程中预热
            from src.utils.thread_pool_manager import submit_background_task

            def warmup_task():
                return self._warmup_all_sync()

            future = submit_background_task(warmup_task)
            logger.info("已在后台线程中启动缓存预热")
            return {}
        else:
            return self._warmup_all_sync()

    def _warmup_all_sync(self) -> Dict[str, bool]:
        """同步预热所有缓存"""
        results = {}

        with self._global_lock:
            cache_names = list(self._warmup_callbacks.keys())

        for cache_name in cache_names:
            results[cache_name] = self.warmup_cache(cache_name)

        success_count = sum(1 for v in results.values() if v)
        logger.info(
            f"缓存预热完成，成功 {success_count}/{len(results)} 个"
        )

        return results


# 全局实例
_cache_manager = None


def get_cache_manager() -> CacheManager:
    """获取全局缓存管理器"""
    global _cache_manager
    if _cache_manager is None:
        _cache_manager = CacheManager()
    return _cache_manager

