"""
智能缓存管理器 v2.32.0

提供高性能的多级缓存系统，用于缓存：
- Prompt模板
- 记忆检索结果
- 角色设定
- 系统提示

特性：
- LRU缓存策略
- TTL过期机制
- 内存限制
- 缓存预热
- 性能监控

作者: MintChat Team
日期: 2025-11-17
"""

import time
from collections import OrderedDict
from threading import Lock
from typing import Any, Callable, Dict, Optional, TypeVar
from functools import wraps
import hashlib
import json

from src.utils.logger import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


class LRUCache:
    """LRU缓存实现 - 最近最少使用淘汰策略"""

    def __init__(self, max_size: int = 100, ttl: int = 3600):
        """
        初始化LRU缓存

        Args:
            max_size: 最大缓存条目数
            ttl: 缓存过期时间（秒），默认1小时
        """
        self.max_size = max(0, int(max_size))
        self.ttl = max(0, int(ttl))
        self.cache: OrderedDict[str, Any] = OrderedDict()
        # 使用 monotonic 记录过期时间点（避免系统时间变化影响 TTL）
        self.timestamps: Dict[str, float] = {}
        self._lock = Lock()

        # 性能统计
        self.stats = {
            "hits": 0,
            "misses": 0,
            "evictions": 0,
            "expirations": 0,
        }

    def _is_expired(self, key: str) -> bool:
        """检查缓存是否过期"""
        expire_at = self.timestamps.get(key)
        if expire_at is None:
            return True
        return time.monotonic() > expire_at

    def get(self, key: str) -> Optional[Any]:
        """获取缓存值"""
        with self._lock:
            if key not in self.cache:
                self.stats["misses"] += 1
                return None

            # 检查是否过期
            if self._is_expired(key):
                self._delete_unlocked(key)
                self.stats["expirations"] += 1
                self.stats["misses"] += 1
                return None

            # 移到最后（最近使用）
            self.cache.move_to_end(key)
            self.stats["hits"] += 1
            return self.cache[key]

    def set(self, key: str, value: Any, *, ttl: int | None = None) -> None:
        """设置缓存值"""
        if self.max_size <= 0:
            return

        with self._lock:
            now = time.monotonic()
            effective_ttl = self.ttl if ttl is None else max(0, int(ttl))

            # 若缓存已接近/达到上限，优先清理过期条目，避免“挤占容量导致误淘汰”。
            if self.timestamps and len(self.cache) >= self.max_size:
                expired_keys = [
                    expire_key
                    for expire_key, expire_at in list(self.timestamps.items())
                    if now > expire_at
                ]
                for expire_key in expired_keys:
                    self._delete_unlocked(expire_key)
                if expired_keys:
                    self.stats["expirations"] += len(expired_keys)

            # 如果已存在，先删除
            if key in self.cache:
                del self.cache[key]

            # 添加新值
            self.cache[key] = value
            self.timestamps[key] = now + effective_ttl

            # 如果超过最大大小，删除最旧的
            while len(self.cache) > self.max_size:
                oldest_key = next(iter(self.cache))
                self._delete_unlocked(oldest_key)
                self.stats["evictions"] += 1

    def delete(self, key: str) -> None:
        """删除缓存值"""
        with self._lock:
            self._delete_unlocked(key)

    def _delete_unlocked(self, key: str) -> None:
        """删除缓存值（需在 self._lock 内调用）。"""
        if key in self.cache:
            del self.cache[key]
        if key in self.timestamps:
            del self.timestamps[key]

    def clear(self) -> None:
        """清空缓存"""
        with self._lock:
            self.cache.clear()
            self.timestamps.clear()

    def cleanup_expired(self) -> int:
        """
        清理过期缓存（智能内存管理）

        Returns:
            清理的条目数
        """
        with self._lock:
            if not self.timestamps:
                return 0

            now = time.monotonic()
            expired_keys = [
                key for key, expire_at in list(self.timestamps.items()) if now > expire_at
            ]

            for key in expired_keys:
                self._delete_unlocked(key)
                self.stats["expirations"] += 1

        if expired_keys:
            logger.debug("清理了 %d 个过期缓存条目", len(expired_keys))

        return len(expired_keys)

    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计"""
        with self._lock:
            stats = dict(self.stats)
            size = len(self.cache)

        total_requests = stats["hits"] + stats["misses"]
        hit_rate = (stats["hits"] / total_requests * 100) if total_requests > 0 else 0

        return {
            **stats,
            "size": size,
            "max_size": self.max_size,
            "hit_rate": f"{hit_rate:.2f}%",
        }


class SmartCacheManager:
    """智能缓存管理器 - 统一管理所有缓存"""

    def __init__(self):
        """初始化缓存管理器"""
        # 不同类型的缓存，使用不同的配置
        self.prompt_cache = LRUCache(max_size=50, ttl=7200)  # Prompt缓存，2小时
        self.memory_cache = LRUCache(max_size=200, ttl=600)  # 记忆缓存，10分钟
        self.config_cache = LRUCache(max_size=20, ttl=3600)  # 配置缓存，1小时

        # 自动清理计数器
        self._cleanup_counter = 0
        self._cleanup_interval = 100  # 每100次操作清理一次

        logger.info("智能缓存管理器初始化完成")

    @staticmethod
    def _generate_key(*args, **kwargs) -> str:
        """生成缓存键"""
        # 将参数转换为字符串并哈希（需容错：args/kwargs 可能包含不可 JSON 序列化对象）。
        payload: dict[str, Any] = {"args": args, "kwargs": kwargs}

        def _default(obj: Any) -> Any:  # noqa: ANN401
            try:
                model_dump = getattr(obj, "model_dump", None)
                if callable(model_dump):
                    return model_dump()
            except Exception:
                pass
            if isinstance(obj, (bytes, bytearray)):
                return {"__bytes__": bytes(obj).hex()}
            return str(obj)

        try:
            key_str = json.dumps(
                payload,
                sort_keys=True,
                ensure_ascii=False,
                separators=(",", ":"),
                default=_default,
            )
        except Exception:
            key_str = repr(payload)
        return hashlib.md5(key_str.encode("utf-8")).hexdigest()

    def cache_prompt(self, func: Callable) -> Callable:
        """Prompt缓存装饰器"""

        @wraps(func)
        def wrapper(*args, **kwargs):
            key = self._generate_key(*args, **kwargs)

            # 尝试从缓存获取
            cached_value = self.prompt_cache.get(key)
            if cached_value is not None:
                logger.debug("Prompt缓存命中: %.8s...", key)
                return cached_value

            # 执行函数并缓存结果
            result = func(*args, **kwargs)
            self.prompt_cache.set(key, result)
            logger.debug("Prompt缓存设置: %.8s...", key)
            return result

        return wrapper

    def cache_memory(self, func: Callable) -> Callable:
        """记忆缓存装饰器"""

        @wraps(func)
        def wrapper(*args, **kwargs):
            key = self._generate_key(*args, **kwargs)

            # 尝试从缓存获取
            cached_value = self.memory_cache.get(key)
            if cached_value is not None:
                logger.debug("记忆缓存命中: %.8s...", key)
                return cached_value

            # 执行函数并缓存结果
            result = func(*args, **kwargs)
            self.memory_cache.set(key, result)

            # 自动清理过期缓存
            self._auto_cleanup()

            return result

        return wrapper

    def _auto_cleanup(self) -> None:
        """自动清理过期缓存（智能内存管理）"""
        self._cleanup_counter += 1

        if self._cleanup_counter >= self._cleanup_interval:
            total_cleaned = 0
            total_cleaned += self.prompt_cache.cleanup_expired()
            total_cleaned += self.memory_cache.cleanup_expired()
            total_cleaned += self.config_cache.cleanup_expired()

            if total_cleaned > 0:
                logger.info(f"自动清理了 {total_cleaned} 个过期缓存条目")

            self._cleanup_counter = 0

    def cleanup_all(self) -> int:
        """
        手动清理所有过期缓存

        Returns:
            清理的总条目数
        """
        total_cleaned = 0
        total_cleaned += self.prompt_cache.cleanup_expired()
        total_cleaned += self.memory_cache.cleanup_expired()
        total_cleaned += self.config_cache.cleanup_expired()

        logger.info(f"手动清理了 {total_cleaned} 个过期缓存条目")
        return total_cleaned

    def clear_all(self) -> None:
        """清空所有缓存（用于调试或在配置/模型切换后主动释放内存）。"""
        self.prompt_cache.clear()
        self.memory_cache.clear()
        self.config_cache.clear()

    def get_stats(self) -> Dict[str, Any]:
        """获取所有缓存统计。"""
        return {
            "prompt": self.prompt_cache.get_stats(),
            "memory": self.memory_cache.get_stats(),
            "config": self.config_cache.get_stats(),
        }


# 全局缓存管理器实例
cache_manager = SmartCacheManager()
