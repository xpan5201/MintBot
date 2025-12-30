"""
知识库性能优化器 v2.30.44

提供知识库系统的性能优化功能：
1. ChromaDB 参数调优
2. 多级缓存（内存 + Redis）
3. 异步处理
4. 批量操作优化

作者: MintChat Team
日期: 2025-11-16
"""

import asyncio
import hashlib
import json
import time
from collections import OrderedDict
from concurrent.futures import Future, ThreadPoolExecutor, wait
from threading import Lock
from typing import Any, Dict, List, Optional, Callable
from functools import wraps

from src.utils.logger import get_logger
from src.utils.async_loop_thread import AsyncLoopThread

logger = get_logger(__name__)

# 尝试导入 Redis
try:
    import redis
    from redis import Redis

    HAS_REDIS = True
except ImportError:
    HAS_REDIS = False
    logger.debug("Redis 未安装，将只使用内存缓存")


class MultiLevelCache:
    """
    多级缓存系统 - 内存 + Redis

    功能：
    1. L1 缓存：内存缓存（快速访问）
    2. L2 缓存：Redis 缓存（持久化）
    3. 自动过期管理
    4. 缓存预热
    """

    def __init__(
        self,
        redis_host: str = "localhost",
        redis_port: int = 6379,
        redis_db: int = 0,
        redis_password: Optional[str] = None,
        default_ttl: int = 3600,  # 默认过期时间（秒）
        max_memory_items: int = 1000,  # 内存缓存最大条目数
        enable_redis: bool = True,
        connect_timeout: float = 2.0,
        socket_timeout: float = 2.0,
        validate_connection: bool = True,
    ):
        """
        初始化多级缓存

        Args:
            redis_host: Redis 主机地址
            redis_port: Redis 端口
            redis_db: Redis 数据库编号
            redis_password: Redis 密码
            default_ttl: 默认过期时间（秒）
            max_memory_items: 内存缓存最大条目数
            enable_redis: 是否启用 Redis 作为 L2 缓存
            connect_timeout: Redis 连接超时时间（秒）
            socket_timeout: Redis 读写超时时间（秒）
            validate_connection: 是否在初始化时 ping Redis
        """
        self.default_ttl = max(0, int(default_ttl))
        self.max_memory_items = max(0, int(max_memory_items))
        self.redis_enabled = enable_redis and HAS_REDIS
        self._state_lock = Lock()

        # L1 缓存：内存缓存
        self._memory_cache: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()

        # L2 缓存：Redis 缓存
        self.redis_client: Optional[Redis] = None
        self._redis_disabled_reason: Optional[str] = None
        self._redis_error_logged: bool = False

        if self.redis_enabled:
            try:
                self.redis_client = redis.Redis(
                    host=redis_host,
                    port=redis_port,
                    db=redis_db,
                    password=redis_password,
                    decode_responses=True,
                    socket_connect_timeout=max(0.1, float(connect_timeout)),
                    socket_timeout=max(0.1, float(socket_timeout)),
                )
                if validate_connection:
                    # 测试连接：可能造成启动延迟，允许通过 validate_connection 关闭
                    self.redis_client.ping()
                    logger.info("Redis 缓存已连接: %s:%s", redis_host, redis_port)
                else:
                    logger.info("Redis 客户端已配置: %s:%s", redis_host, redis_port)
            except Exception as e:
                self.redis_client = None
                self.redis_enabled = False
                self._redis_disabled_reason = f"{type(e).__name__}: {e}"
                logger.warning(
                    "Redis 连接失败，将只使用内存缓存。"
                    " 请确认 Redis 已启动并可访问，或在 config.user.yaml 的 Agent.redis_enabled 设为 false。"
                    f" 原因: {self._redis_disabled_reason}"
                )
        elif not HAS_REDIS:
            self._redis_disabled_reason = "redis 库未安装"
            logger.debug("Redis 未安装，将仅使用内存缓存")
        else:
            self._redis_disabled_reason = "配置禁用"
            logger.debug("配置禁用了 Redis，将仅使用内存缓存")

        # 统计信息
        self.stats = {
            "l1_hits": 0,
            "l2_hits": 0,
            "misses": 0,
            "sets": 0,
        }

    def _disable_redis(self, reason: str, *, action: str) -> None:
        """运行时禁用 Redis，避免每次访问都报错/超时。"""
        should_log = False
        client_to_close = None
        with self._state_lock:
            if self.redis_client is None:
                self.redis_enabled = False
                self._redis_disabled_reason = self._redis_disabled_reason or reason
                return

            client_to_close = self.redis_client
            self.redis_client = None
            self.redis_enabled = False
            self._redis_disabled_reason = reason
            if not self._redis_error_logged:
                self._redis_error_logged = True
                should_log = True

        if client_to_close is not None:
            try:
                close_fn = getattr(client_to_close, "close", None)
                if callable(close_fn):
                    close_fn()
            except Exception:
                pass

        if should_log:
            logger.warning("Redis %s 失败，已自动禁用 Redis 缓存: %s", action, reason)

    def _make_key(self, key: str, prefix: str = "mintchat") -> str:
        """生成缓存键"""
        return f"{prefix}:{key}"

    def get(self, key: str, prefix: str = "mintchat") -> Optional[Any]:
        """
        获取缓存值

        Args:
            key: 缓存键
            prefix: 键前缀

        Returns:
            Optional[Any]: 缓存值，不存在返回 None
        """
        cache_key = self._make_key(key, prefix)

        # L1 缓存：内存缓存
        if self.max_memory_items > 0:
            with self._state_lock:
                entry = self._memory_cache.get(cache_key)
                if entry is not None:
                    now = time.monotonic()
                    if float(entry["expire_at"]) > now:
                        self._memory_cache.move_to_end(cache_key)
                        self.stats["l1_hits"] += 1
                        value = entry["value"]
                        logger.debug("L1 缓存命中: %s", cache_key)
                        return value
                    # 过期，删除
                    self._memory_cache.pop(cache_key, None)

        # L2 缓存：Redis 缓存
        with self._state_lock:
            redis_client = self.redis_client
        if redis_client:
            try:
                value_json = redis_client.get(cache_key)
                if value_json:
                    value: Optional[Any] = None
                    try:
                        value = json.loads(value_json)
                    except Exception as decode_exc:
                        # 单条缓存值损坏/格式不兼容：删除该 key，不应导致禁用 Redis
                        logger.warning(
                            "Redis 缓存值解析失败，已删除 key=%s: %s", cache_key, decode_exc
                        )
                        try:
                            redis_client.delete(cache_key)
                        except Exception:
                            pass
                    if value is not None:
                        with self._state_lock:
                            self.stats["l2_hits"] += 1
                        logger.debug("L2 缓存命中: %s", cache_key)

                        # 回填到 L1 缓存
                        self._set_memory_cache(cache_key, value, self.default_ttl)

                        return value
            except Exception as e:
                self._disable_redis(f"{type(e).__name__}: {e}", action="读取")

        # 缓存未命中
        with self._state_lock:
            self.stats["misses"] += 1
        return None

    def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
        prefix: str = "mintchat",
    ) -> bool:
        """
        设置缓存值

        Args:
            key: 缓存键
            value: 缓存值
            ttl: 过期时间（秒），None 使用默认值
            prefix: 键前缀

        Returns:
            bool: 是否成功
        """
        cache_key = self._make_key(key, prefix)
        ttl_seconds = self.default_ttl if ttl is None else max(0, int(ttl))

        # L1 缓存：内存缓存
        if self.max_memory_items > 0:
            self._set_memory_cache(cache_key, value, ttl_seconds)

        # L2 缓存：Redis 缓存
        with self._state_lock:
            redis_client = self.redis_client
        if redis_client:
            try:
                value_json: Optional[str]
                try:
                    value_json = json.dumps(value, ensure_ascii=False)
                except TypeError:
                    # value 不可 JSON 序列化：仅跳过 Redis 写入，不要禁用 Redis
                    value_json = None

                if value_json is None:
                    logger.debug("跳过 Redis 缓存写入（不可序列化）: %s", cache_key)
                elif ttl_seconds <= 0:
                    logger.debug("跳过 Redis 缓存写入（ttl<=0）: %s", cache_key)
                else:
                    redis_client.setex(cache_key, ttl_seconds, value_json)
            except Exception as e:
                self._disable_redis(f"{type(e).__name__}: {e}", action="写入")

        with self._state_lock:
            self.stats["sets"] += 1
        return True

    def _set_memory_cache(self, key: str, value: Any, ttl: int):
        """设置内存缓存"""
        if self.max_memory_items <= 0:
            return

        ttl = max(0, int(ttl))
        expire_at = time.monotonic() + ttl

        with self._state_lock:
            # 覆盖写入时保持 LRU 顺序
            if key in self._memory_cache:
                self._memory_cache[key] = {"value": value, "expire_at": expire_at}
                self._memory_cache.move_to_end(key)
                return

            # 检查内存缓存大小（LRU：从最旧开始淘汰）
            now = time.monotonic()
            while len(self._memory_cache) >= self.max_memory_items and self._memory_cache:
                oldest_key, oldest_entry = next(iter(self._memory_cache.items()))
                if float(oldest_entry.get("expire_at", 0.0)) <= now:
                    self._memory_cache.popitem(last=False)
                    continue
                self._memory_cache.popitem(last=False)
                break

            # 设置缓存
            self._memory_cache[key] = {
                "value": value,
                "expire_at": expire_at,
            }

    def delete(self, key: str, prefix: str = "mintchat") -> bool:
        """
        删除缓存值

        Args:
            key: 缓存键
            prefix: 键前缀

        Returns:
            bool: 是否成功
        """
        cache_key = self._make_key(key, prefix)

        # L1 缓存
        with self._state_lock:
            self._memory_cache.pop(cache_key, None)

        # L2 缓存
        with self._state_lock:
            redis_client = self.redis_client
        if redis_client:
            try:
                redis_client.delete(cache_key)
            except Exception as e:
                self._disable_redis(f"{type(e).__name__}: {e}", action="删除")

        return True

    def clear(self, prefix: str = "mintchat"):
        """
        清除所有缓存

        Args:
            prefix: 键前缀
        """
        # L1 缓存
        with self._state_lock:
            keys_to_delete = [k for k in self._memory_cache.keys() if k.startswith(f"{prefix}:")]
            for key in keys_to_delete:
                self._memory_cache.pop(key, None)

        # L2 缓存
        with self._state_lock:
            redis_client = self.redis_client
        if redis_client:
            try:
                pattern = f"{prefix}:*"
                # keys() 在大 keyspace 下可能阻塞；优先使用 scan_iter
                if hasattr(redis_client, "scan_iter"):
                    batch: List[str] = []
                    for k in redis_client.scan_iter(match=pattern, count=500):
                        batch.append(k)
                        if len(batch) >= 500:
                            redis_client.delete(*batch)
                            batch.clear()
                    if batch:
                        redis_client.delete(*batch)
                else:
                    keys = redis_client.keys(pattern)
                    if keys:
                        redis_client.delete(*keys)
            except Exception as e:
                self._disable_redis(f"{type(e).__name__}: {e}", action="清除")

        logger.info("缓存已清除: %s", prefix)

    def close(self) -> None:
        """关闭缓存并释放底层资源（幂等）。"""
        client_to_close = None
        with self._state_lock:
            client_to_close = self.redis_client
            self.redis_client = None
            self.redis_enabled = False
            self._memory_cache.clear()

        if client_to_close is not None:
            try:
                close_fn = getattr(client_to_close, "close", None)
                if callable(close_fn):
                    close_fn()
            except Exception:
                pass

    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        with self._state_lock:
            stats = dict(self.stats)
            l1_size = len(self._memory_cache)
            redis_connected = self.redis_client is not None

        total_requests = stats["l1_hits"] + stats["l2_hits"] + stats["misses"]
        hit_rate = (
            (stats["l1_hits"] + stats["l2_hits"]) / total_requests if total_requests > 0 else 0
        )

        return {
            "l1_hits": stats["l1_hits"],
            "l2_hits": stats["l2_hits"],
            "misses": stats["misses"],
            "sets": stats["sets"],
            "total_requests": total_requests,
            "hit_rate": hit_rate,
            "l1_size": l1_size,
            "redis_connected": redis_connected,
        }


class AsyncProcessor:
    """
    异步处理器 - 提升响应速度

    功能：
    1. 异步执行非关键操作
    2. 任务队列管理
    3. 并发控制
    4. 错误处理
    """

    def __init__(
        self,
        max_workers: int = 4,
        *,
        use_async_loop_thread: bool = True,
        loop_start_timeout_s: float = 5.0,
    ):
        """
        初始化异步处理器（线程池版，适配同步 GUI/CLI 场景）。

        旧实现依赖 event loop 持续运行，否则 create_task 只是挂起不执行；
        这里改为 ThreadPoolExecutor，保证 submit 后立即开始执行。
        """
        self.max_workers = max(1, int(max_workers))
        self._use_async_loop_thread = bool(use_async_loop_thread)
        self._loop_start_timeout_s = max(0.1, float(loop_start_timeout_s))
        self._executor = ThreadPoolExecutor(
            max_workers=self.max_workers,
            thread_name_prefix="mintchat-async",
        )
        self._lock = Lock()
        self._futures: set[Future] = set()
        self._loop_thread: Optional[AsyncLoopThread] = None

        logger.info("异步处理器初始化完成，最大并发数: %d", self.max_workers)

    def _get_or_create_loop_thread(self) -> AsyncLoopThread:
        loop_thread = self._loop_thread
        if loop_thread is not None:
            return loop_thread
        with self._lock:
            loop_thread = self._loop_thread
            if loop_thread is None:
                loop_thread = AsyncLoopThread(
                    thread_name="mintchat-async-processor",
                    start_timeout_s=self._loop_start_timeout_s,
                )
                self._loop_thread = loop_thread
        return loop_thread

    def _track_future(self, future: Future) -> Future:
        with self._lock:
            self._futures.add(future)

        def _cleanup(_f: Future) -> None:
            with self._lock:
                self._futures.discard(_f)

        future.add_done_callback(_cleanup)
        return future

    def submit(self, func: Callable, *args, **kwargs) -> Future:
        """
        提交异步任务（后台线程执行）。

        Returns:
            Future: 可用于取消/等待的 future。
        """

        if self._use_async_loop_thread and asyncio.iscoroutinefunction(func):
            try:
                coro = func(*args, **kwargs)
                return self._track_future(self._get_or_create_loop_thread().submit(coro))
            except Exception as exc:
                logger.debug("AsyncLoopThread 提交失败，回退线程池执行: %s", exc)

        def _runner() -> Any:
            try:
                if asyncio.iscoroutinefunction(func):
                    coro = func(*args, **kwargs)
                    if self._use_async_loop_thread:
                        return self._get_or_create_loop_thread().run(coro)
                    return asyncio.run(coro)
                result = func(*args, **kwargs)
                if asyncio.iscoroutine(result):
                    if self._use_async_loop_thread:
                        return self._get_or_create_loop_thread().run(result)
                    return asyncio.run(result)
                return result
            except Exception:
                logger.exception("异步任务执行失败")
                raise

        return self._track_future(self._executor.submit(_runner))

    def wait_all(self, timeout: Optional[float] = None) -> List[Any]:
        """
        等待当前已提交的任务完成。

        Returns:
            List[Any]: 任务结果列表（含异常对象，语义与 gather(return_exceptions=True) 接近）。
        """
        with self._lock:
            futures = list(self._futures)

        if not futures:
            return []

        done, not_done = wait(futures, timeout=timeout)
        results: List[Any] = []
        for fut in done:
            try:
                results.append(fut.result())
            except Exception as exc:
                results.append(exc)

        if not_done:
            for fut in not_done:
                fut.cancel()
            logger.warning(
                "异步任务超时: %.2fs（取消 %d 个任务）", float(timeout or 0.0), len(not_done)
            )

        return results

    def close(self) -> None:
        """清理资源：取消任务并关闭线程池。"""
        with self._lock:
            futures = list(self._futures)
            self._futures.clear()
            loop_thread = self._loop_thread
            self._loop_thread = None

        for fut in futures:
            if not fut.done():
                fut.cancel()

        try:
            self._executor.shutdown(wait=False, cancel_futures=True)
        except TypeError:
            self._executor.shutdown(wait=False)
        finally:
            if loop_thread is not None:
                try:
                    loop_thread.close(timeout=2.0)
                except Exception:
                    pass

    def __enter__(self) -> "AsyncProcessor":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # noqa: ANN001 - context manager protocol
        self.close()

    def __del__(self) -> None:
        # 析构阶段尽量避免留下非守护线程（忽略所有异常）
        try:
            self.close()
        except Exception:
            pass


class ChromaDBOptimizer:
    """
    ChromaDB 参数优化器

    功能：
    1. HNSW 参数调优
    2. 批量操作优化
    3. 查询优化
    """

    @staticmethod
    def get_optimized_hnsw_params(
        collection_size: int = 10000,
        query_speed_priority: bool = True,
    ) -> Dict[str, Any]:
        """
        获取优化的 HNSW 参数

        Args:
            collection_size: 集合大小（预估）
            query_speed_priority: 是否优先查询速度（否则优先准确率）

        Returns:
            Dict: HNSW 参数
        """
        if query_speed_priority:
            # 优先查询速度
            if collection_size < 1000:
                return {
                    "hnsw:space": "cosine",
                    "hnsw:construction_ef": 100,
                    "hnsw:search_ef": 50,
                    "hnsw:M": 16,
                }
            elif collection_size < 10000:
                return {
                    "hnsw:space": "cosine",
                    "hnsw:construction_ef": 200,
                    "hnsw:search_ef": 100,
                    "hnsw:M": 32,
                }
            else:
                return {
                    "hnsw:space": "cosine",
                    "hnsw:construction_ef": 400,
                    "hnsw:search_ef": 200,
                    "hnsw:M": 48,
                }
        else:
            # 优先准确率
            if collection_size < 1000:
                return {
                    "hnsw:space": "cosine",
                    "hnsw:construction_ef": 200,
                    "hnsw:search_ef": 100,
                    "hnsw:M": 32,
                }
            elif collection_size < 10000:
                return {
                    "hnsw:space": "cosine",
                    "hnsw:construction_ef": 400,
                    "hnsw:search_ef": 200,
                    "hnsw:M": 48,
                }
            else:
                return {
                    "hnsw:space": "cosine",
                    "hnsw:construction_ef": 800,
                    "hnsw:search_ef": 400,
                    "hnsw:M": 64,
                }

    @staticmethod
    def optimize_batch_size(
        total_items: int,
        item_size_bytes: int = 1024,
        max_memory_mb: int = 100,
    ) -> int:
        """
        优化批量操作的批次大小

        Args:
            total_items: 总条目数
            item_size_bytes: 单个条目大小（字节）
            max_memory_mb: 最大内存使用（MB）

        Returns:
            int: 优化的批次大小
        """
        max_memory_bytes = max_memory_mb * 1024 * 1024
        max_batch_size = max_memory_bytes // item_size_bytes

        # 限制批次大小在合理范围内
        batch_size = min(max_batch_size, 1000)
        batch_size = max(batch_size, 10)

        return batch_size


def cache_result(
    ttl: int = 3600,
    key_func: Optional[Callable] = None,
    cache_instance: Optional[MultiLevelCache] = None,
):
    """
    缓存装饰器 - 自动缓存函数结果

    Args:
        ttl: 缓存过期时间（秒）
        key_func: 生成缓存键的函数
        cache_instance: 缓存实例
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            # 生成缓存键
            if key_func:
                cache_key = key_func(*args, **kwargs)
            else:
                # 默认使用函数名和参数生成键
                key_parts = [func.__name__]
                key_parts.extend(str(arg) for arg in args)
                key_parts.extend(f"{k}={v}" for k, v in sorted(kwargs.items()))
                cache_key = hashlib.md5(":".join(key_parts).encode()).hexdigest()

            # 尝试从缓存获取
            if cache_instance:
                cached_value = cache_instance.get(cache_key)
                if cached_value is not None:
                    return cached_value

            # 执行函数
            result = func(*args, **kwargs)

            # 缓存结果
            if cache_instance and result is not None:
                cache_instance.set(cache_key, result, ttl)

            return result

        return wrapper

    return decorator
