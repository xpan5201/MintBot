"""
MintChat 记忆检索优化模块

v2.30.27 新增：并发记忆检索，提升性能到毫秒级
- 并发检索多个记忆源（长期记忆、核心记忆）
- 智能缓存和预热
- 性能监控和优化

v2.32.0 性能优化：
- 集成智能缓存管理器
- 优化检索参数
- 添加缓存预热机制
"""

import asyncio
import hashlib
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Dict, List, Optional, TypedDict
from concurrent.futures import ThreadPoolExecutor

from src.utils.logger import get_logger
from src.utils.cache_manager import cache_manager


logger = get_logger(__name__)


class _RetrieverStats(TypedDict):
    total_retrievals: int
    avg_time_ms: float
    cache_hits: int
    last_latency_ms: float
    last_source_latency_ms: Dict[str, float]


@dataclass(slots=True)
class _CircuitBreaker:
    """简易熔断器，用于在记忆源持续失败时暂时跳过相应检索。"""

    threshold: int
    cooldown: float
    failures: int = 0
    opened_until: float = 0.0

    def should_skip(self) -> bool:
        return time.perf_counter() < self.opened_until

    def record_failure(self) -> bool:
        self.failures += 1
        if self.failures >= self.threshold:
            self.failures = 0
            self.opened_until = time.perf_counter() + self.cooldown
            return True
        return False

    def record_success(self) -> None:
        self.failures = 0
        self.opened_until = 0.0


@dataclass(slots=True)
class _SourceStats:
    """记录单个记忆源的动态性能表现。"""

    avg_latency_ms: float = 0.0
    samples: int = 0
    failure_streak: int = 0

    def record_success(self, latency_ms: float) -> None:
        self.samples += 1
        alpha = 0.3
        if self.samples == 1:
            self.avg_latency_ms = latency_ms
        else:
            self.avg_latency_ms = self.avg_latency_ms * (1 - alpha) + latency_ms * alpha
        self.failure_streak = 0

    def record_failure(self) -> None:
        self.failure_streak += 1


class ConcurrentMemoryRetriever:
    """
    并发记忆检索器

    v2.30.27 性能优化: 并发检索多个记忆源
    v2.48.5 性能优化: 熔断与动态超时
    """

    SOURCE_LABELS = {
        "long_term": "长期记忆",
        "core": "核心记忆",
    }

    def __init__(
        self,
        long_term_memory,
        core_memory,
        max_workers: int = 4,
        source_timeout_s: float = 0.0,
        breaker_threshold: int = 3,
        breaker_cooldown_s: float = 3.0,
    ):
        """
        初始化并发记忆检索器

        Args:
            long_term_memory: 长期记忆管理器
            core_memory: 核心记忆管理器
            max_workers: 最大并发工作线程数
            breaker_threshold: 熔断器阈值（连续失败次数）
            breaker_cooldown_s: 熔断器冷却时间（秒）
        """
        self.long_term_memory = long_term_memory
        self.core_memory = core_memory
        self.executor: Optional[ThreadPoolExecutor] = ThreadPoolExecutor(
            max_workers=max(1, int(max_workers)),
            thread_name_prefix="mintchat-mem",
        )
        self._source_timeout_s = max(0.0, float(source_timeout_s or 0.0))
        self._breaker_threshold = max(1, int(breaker_threshold or 1))
        self._breaker_cooldown_s = max(0.5, float(breaker_cooldown_s or 0.5))
        self._breakers = {
            "long_term": _CircuitBreaker(self._breaker_threshold, self._breaker_cooldown_s),
            "core": _CircuitBreaker(self._breaker_threshold, self._breaker_cooldown_s),
        }
        self._source_stats = {
            "long_term": _SourceStats(),
            "core": _SourceStats(),
        }

        # 性能统计
        self.stats: _RetrieverStats = {
            "total_retrievals": 0,
            "avg_time_ms": 0.0,
            "cache_hits": 0,
            "last_latency_ms": 0.0,
            "last_source_latency_ms": {
                "long_term": 0.0,
                "core": 0.0,
            },
        }

    async def retrieve_all_memories_async(
        self,
        query: str,
        long_term_k: int = 5,
        core_k: int = 2,
        use_cache: bool = True,
    ) -> Dict[str, List[str]]:
        """
        并发检索所有记忆源（异步版本）

        v2.30.27 性能优化：
        - 使用 asyncio.gather 并发执行所有检索
        - 目标延迟：<50ms（相比串行的200ms+）

        v2.32.0 性能优化：
        - 集成智能缓存，缓存命中时延迟 <5ms
        - 优化检索参数，减少不必要的检索

        Args:
            query: 查询文本
            long_term_k: 长期记忆返回数量
            core_k: 核心记忆返回数量
            use_cache: 是否使用缓存

        Returns:
            Dict[str, List[str]]: 各类记忆的检索结果
        """
        start_time = time.perf_counter()

        # 优化缓存键生成，使用hash减少内存占用
        cache_key = None
        if use_cache:
            # 注意：cache_manager.memory_cache 是全局缓存，必须纳入 user_id 等维度，避免跨用户污染
            user_id = getattr(self.long_term_memory, "user_id", None)
            long_term_obj = getattr(self.long_term_memory, "long_term", None)
            lt_version = getattr(long_term_obj, "write_version", 0)
            try:
                core_version = int(getattr(self.core_memory, "write_version", 0) or 0)
            except Exception:
                core_version = 0
            cache_key_data = (
                f"u={user_id}"
                f"|ltv={lt_version}"
                f"|cv={core_version}"
                f"|{query}_{long_term_k}_{core_k}"
            )
            cache_key = hashlib.md5(cache_key_data.encode()).hexdigest()
            cached_result = cache_manager.memory_cache.get(cache_key)
            if cached_result is not None:
                self.stats["cache_hits"] += 1
                return cached_result

        # 并发执行所有检索任务
        tasks = [
            self._retrieve_long_term_async(query, long_term_k),
            self._retrieve_core_async(query, core_k),
        ]

        # 等待所有任务完成（各 source 内部已做异常兜底，这里不需要 return_exceptions=True）
        long_term_memories, core_memories = await asyncio.gather(*tasks)

        # 性能统计
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        self.stats["total_retrievals"] += 1
        self.stats["last_latency_ms"] = round(elapsed_ms, 2)
        self.stats["avg_time_ms"] = (
            self.stats["avg_time_ms"] * (self.stats["total_retrievals"] - 1) + elapsed_ms
        ) / self.stats["total_retrievals"]

        # 记录详细日志
        logger.debug(
            "并发记忆检索完成: %.1fms (长期:%d, 核心:%d)",
            elapsed_ms,
            len(long_term_memories),
            len(core_memories),
        )

        result = {
            "long_term": long_term_memories,
            "core": core_memories,
        }

        # v2.32.0: 缓存结果（复用已生成的缓存键）
        if use_cache and cache_key:
            cache_manager.memory_cache.set(cache_key, result)

        return result

    async def _retrieve_long_term_async(self, query: str, k: int) -> List[str]:
        """异步检索长期记忆"""
        if self._should_skip_source("long_term"):
            return []

        executor = self.executor
        if executor is None:
            return []

        loop = asyncio.get_running_loop()
        future = loop.run_in_executor(
            executor,
            self.long_term_memory.search_relevant_memories,
            query,
            k,
        )
        return await self._await_with_metrics("long_term", future)

    async def _retrieve_core_async(self, query: str, k: int) -> List[str]:
        """异步检索核心记忆"""
        if not self.core_memory.vectorstore:
            return []

        if self._should_skip_source("core"):
            return []

        executor = self.executor
        if executor is None:
            return []

        loop = asyncio.get_running_loop()
        future = loop.run_in_executor(
            executor,
            self.core_memory.search_core_memories,
            query,
            k,
        )
        results = await self._await_with_metrics("core", future)
        if not results:
            return []
        return [entry.get("content", "") for entry in results if entry.get("content")]

    def get_stats(self) -> Dict[str, Any]:
        """获取性能统计"""
        return {
            **self.stats,
            "avg_time_ms": round(self.stats["avg_time_ms"], 2),
        }

    def close(self) -> None:
        """显式清理资源（推荐使用此方法而不是依赖 __del__）。"""
        executor = self.executor
        if executor is None:
            return
        try:
            executor.shutdown(wait=False, cancel_futures=True)
        except TypeError:
            # Python < 3.9 不支持 cancel_futures
            try:
                executor.shutdown(wait=False)
            except Exception:
                pass
        except Exception as e:
            logger.warning("关闭记忆检索器线程池时出错: %s", e)
        finally:
            self.executor = None

    def __del__(self):
        """清理资源（备用方法，不推荐依赖）"""
        executor = getattr(self, "executor", None)
        if executor is not None:
            try:
                executor.shutdown(wait=False)
            except Exception:
                pass

    # ----------------------------- 内部方法 -----------------------------

    def _should_skip_source(self, name: str) -> bool:
        breaker = self._breakers[name]
        if breaker.should_skip():
            remaining = max(0.0, breaker.opened_until - time.perf_counter())
            logger.debug("跳过%s记忆检索：熔断冷却中 %.0fms", name, remaining * 1000)
            return True
        return False

    def _mark_source_failure(self, name: str) -> None:
        breaker = self._breakers[name]
        if breaker.record_failure():
            logger.warning("%s记忆检索连续失败，熔断 %.1fs", name, self._breaker_cooldown_s)

    def _mark_source_success(self, name: str) -> None:
        self._breakers[name].record_success()

    async def _await_with_metrics(
        self,
        name: str,
        awaitable: Awaitable,
    ) -> List[Any]:
        """
        带指标记录的异步等待，增强错误处理

        改进：
        - 改进错误信息处理（避免空错误信息）
        - 记录性能指标
        """
        stats = self._source_stats[name]
        label = self.SOURCE_LABELS.get(name, name)
        started = time.perf_counter()
        try:
            timeout_s = self._source_timeout_s
            if timeout_s > 0.0:
                result = await asyncio.wait_for(awaitable, timeout=timeout_s)
            else:
                result = await awaitable
        except asyncio.TimeoutError as exc:
            stats.record_failure()
            self._mark_source_failure(name)

            # 尝试取消尚未开始的线程池任务，避免占用队列；已开始的任务无法安全中止
            try:
                cancel = getattr(awaitable, "cancel", None)
                if callable(cancel):
                    cancel()
            except Exception:
                pass

            # 避免 executor future 在超时后抛出异常时出现 “Future exception was never retrieved” 警告
            try:
                add_done_callback = getattr(awaitable, "add_done_callback", None)
                exception_fn = getattr(awaitable, "exception", None)
                if callable(add_done_callback) and callable(exception_fn):
                    add_done_callback(lambda f: f.exception())  # noqa: B023
            except Exception:
                pass

            timeout_ms = max(0.0, float(self._source_timeout_s)) * 1000
            error_msg = str(exc) or repr(exc) or f"{type(exc).__name__}: {label}检索超时"
            logger.warning("%s检索超时(%.0fms): %s", label, timeout_ms, error_msg)
            return []
        except Exception as exc:
            stats.record_failure()
            self._mark_source_failure(name)
            # 改进错误信息处理，避免空错误信息
            error_msg = str(exc) or repr(exc) or f"{type(exc).__name__}: {label}检索失败"
            logger.error(f"{label}检索失败: {error_msg}")
            return []

        latency_ms = (time.perf_counter() - started) * 1000
        stats.record_success(latency_ms)
        self._mark_source_success(name)
        self.stats["last_source_latency_ms"][name] = round(latency_ms, 2)
        return result if result else []
