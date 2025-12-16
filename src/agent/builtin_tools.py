"""
内置工具系统 - v2.30.26
完全自定义实现，无需外部 MCP 依赖

功能:
- Bing 搜索（HTML 解析，返回结构化数据）
- 高德地图（POI 搜索、地理编码、逆地理编码、路线规划、天气查询）
- 批量操作（批量地理编码、批量路线规划、批量天气查询、批量 POI 搜索）
- 时间转换（时区转换、格式化）
- 性能监控（P50/P95/P99 延迟统计，缓存命中率，性能报告生成）

优化 (v2.30.26):
- ✅ 全局连接池（复用 aiohttp ClientSession，自动检测 event loop 变化）
- ✅ 指数退避重试机制（智能重试，最多3次）
- ✅ TTL 缓存（Bing 5分钟，高德 10分钟）
- ✅ 错误分类处理（5种错误类型，精准错误消息）
- ✅ 参数验证（所有工具完整验证）
- ✅ 批量 API 调用（4种批量操作，并发调用）
- ✅ 性能监控增强（P50/P95/P99 延迟统计，缓存命中率）
- ✅ 智能缓存预热（预加载常用查询）
- ✅ 连接池监控（实时监控连接池状态）
- ✅ 性能报告生成（matplotlib 可视化图表）
- ✅ Event Loop 修复（修复 event loop closed 错误）
- ✅ BeautifulSoup HTML 解析

工具列表 (12个):
1. bing_web_search - Bing 网络搜索
2. amap_poi_search - 高德 POI 搜索
3. amap_geocode - 地理编码（地址→经纬度）
4. amap_regeo - 逆地理编码（经纬度→地址）
5. amap_route_plan - 路线规划（驾车）
6. amap_weather - 天气查询
7. amap_batch_geocode - 批量地理编码
8. amap_batch_route_plan - 批量路线规划
9. amap_batch_weather - 批量天气查询
10. amap_batch_poi_search - 批量 POI 搜索
11. get_time_in_timezone - 时区查询
12. convert_timezone - 时区转换

作者: MintChat Team
日期: 2025-11-16
版本: v2.30.26
"""

import asyncio
import json
import sys
import time
import threading
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List, Tuple
from zoneinfo import ZoneInfo
from pathlib import Path
from functools import wraps
from collections import OrderedDict
from enum import Enum

import aiohttp

try:
    from langchain_core.tools import tool  # type: ignore
except Exception:  # pragma: no cover - 兼容不同 LangChain 版本/最小依赖环境
    try:
        from langchain.tools import tool  # type: ignore
    except Exception:  # pragma: no cover
        def tool(func):  # type: ignore[misc]
            return func

from src.utils.logger import get_logger
from src.utils.async_loop_thread import AsyncLoopThread
from src.utils.tool_context import get_current_tool_timeout_s

logger = get_logger(__name__)


# ==================== 配置和工具函数 ====================
def load_config() -> Dict[str, Any]:
    """加载 config.yaml 配置文件"""
    try:
        import yaml  # 延迟导入：避免模块导入阶段引入额外依赖/解析开销
    except Exception:
        return {}

    config_path = Path(__file__).parent.parent.parent / "config.yaml"
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    return {}


_config: Optional[Dict[str, Any]] = None


def _get_config() -> Dict[str, Any]:
    """惰性加载配置，避免模块导入阶段读取/解析 config.yaml。"""
    global _config
    if _config is None:
        _config = load_config()
    return _config

# 性能统计 (v2.30.25 增强：添加延迟百分位统计)
_tool_stats = {
    "call_count": {},
    "total_time": {},
    "error_count": {},
    "retry_count": {},  # v2.30.23: 新增重试统计
    "latencies": {},    # v2.30.25: 新增延迟列表（用于计算 P50/P95/P99）
    "cache_hits": {},   # v2.30.25: 新增缓存命中统计
}
_tool_stats_lock = threading.Lock()


# ==================== 错误分类 (v2.30.23) ====================
class ErrorType(Enum):
    """错误类型枚举"""
    NETWORK_ERROR = "网络错误"
    API_ERROR = "API错误"
    PARAM_ERROR = "参数错误"
    TIMEOUT_ERROR = "超时错误"
    UNKNOWN_ERROR = "未知错误"


class ToolError(Exception):
    """工具错误基类"""
    def __init__(self, error_type: ErrorType, message: str):
        self.error_type = error_type
        self.message = message
        super().__init__(message)


# ==================== 全局连接池 (v2.30.23) ====================
class ConnectionPool:
    """全局 aiohttp ClientSession 连接池"""
    _session: Optional[aiohttp.ClientSession] = None
    _lock: Optional[asyncio.Lock] = None
    _lock_loop: Optional[asyncio.AbstractEventLoop] = None

    @classmethod
    def _get_lock(cls) -> asyncio.Lock:
        # asyncio.Lock 绑定 event loop；避免在 import 时创建导致跨 loop 使用报错
        loop = asyncio.get_running_loop()
        if cls._lock is None or cls._lock_loop is not loop:
            cls._lock = asyncio.Lock()
            cls._lock_loop = loop
        return cls._lock

    @classmethod
    async def get_session(cls) -> aiohttp.ClientSession:
        """
        获取或创建全局 ClientSession

        v2.30.26 修复:
        - 检查 session 是否绑定到当前 event loop
        - 如果 event loop 不匹配，重新创建 session
        """
        try:
            # 检查 session 是否存在且未关闭
            if cls._session is not None and not cls._session.closed:
                # 检查 session 是否绑定到当前 event loop
                try:
                    loop = asyncio.get_running_loop()
                    # 如果 session 的 loop 与当前 loop 不同，需要重新创建
                    if hasattr(cls._session, '_loop') and cls._session._loop != loop:
                        logger.warning("检测到 event loop 变化，重新创建 HTTP 连接池")
                        await cls._session.close()
                        cls._session = None
                except RuntimeError:
                    pass

            if cls._session is None or cls._session.closed:
                async with cls._get_lock():
                    if cls._session is None or cls._session.closed:
                        def _make_connector() -> aiohttp.TCPConnector:
                            connector_kwargs: dict[str, Any] = {
                                "limit": 100,  # 最大连接数
                                "limit_per_host": 30,  # 每个主机最大连接数
                                "ttl_dns_cache": 300,  # DNS 缓存时间（秒）
                            }
                            # Python 3.13.5+ 已修复底层问题，aiohttp 会忽略并给出弃用警告
                            if sys.version_info < (3, 13, 5):
                                connector_kwargs["enable_cleanup_closed"] = True
                            return aiohttp.TCPConnector(**connector_kwargs)

                        # 配置连接池参数
                        connector = _make_connector()
                        timeout = aiohttp.ClientTimeout(total=30, connect=10)
                        cls._session = aiohttp.ClientSession(
                            connector=connector,
                            timeout=timeout,
                            headers={
                                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                            }
                        )
                        logger.info("全局 HTTP 连接池已创建")
            return cls._session
        except Exception as e:
            logger.error(f"获取 HTTP 连接池失败: {e}")
            # 如果出错，创建新的 session
            connector_kwargs: dict[str, Any] = {
                "limit": 100,
                "limit_per_host": 30,
                "ttl_dns_cache": 300,
            }
            if sys.version_info < (3, 13, 5):
                connector_kwargs["enable_cleanup_closed"] = True
            connector = aiohttp.TCPConnector(**connector_kwargs)
            timeout = aiohttp.ClientTimeout(total=30, connect=10)
            cls._session = aiohttp.ClientSession(
                connector=connector,
                timeout=timeout,
                headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }
            )
            logger.info("全局 HTTP 连接池已重新创建")
            return cls._session

    @classmethod
    async def close(cls):
        """关闭全局 ClientSession"""
        if cls._session and not cls._session.closed:
            await cls._session.close()
            logger.info("全局 HTTP 连接池已关闭")

    @classmethod
    def get_pool_stats(cls) -> Dict[str, Any]:
        """获取连接池统计信息（v2.30.25 新增）"""
        if cls._session is None or cls._session.closed:
            return {
                "status": "未创建",
                "total_connections": 0,
                "active_connections": 0
            }

        connector = cls._session.connector
        return {
            "status": "已创建",
            "total_connections": connector.limit if connector else 0,
            "limit_per_host": connector.limit_per_host if connector else 0,
            "active_connections": len(connector._conns) if connector and hasattr(connector, '_conns') else 0
        }


# ==================== TTL 缓存 (v2.30.23) ====================
class TTLCache:
    """基于时间的缓存（Time-To-Live Cache）"""
    def __init__(self, ttl_seconds: int = 300, maxsize: int = 100):
        self.ttl_seconds = ttl_seconds
        self.maxsize = maxsize
        self.cache: OrderedDict[str, Tuple[Any, datetime]] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[Any]:
        """获取缓存值"""
        with self._lock:
            if key in self.cache:
                value, expire_time = self.cache[key]
                if datetime.now() < expire_time:
                    # 移到末尾（LRU）
                    self.cache.move_to_end(key)
                    return value
                else:
                    # 过期，删除
                    del self.cache[key]
        return None

    def set(self, key: str, value: Any) -> None:
        """设置缓存值"""
        with self._lock:
            expire_time = datetime.now() + timedelta(seconds=self.ttl_seconds)
            self.cache[key] = (value, expire_time)
            self.cache.move_to_end(key)

            # 超过最大容量，删除最旧的
            if len(self.cache) > self.maxsize:
                self.cache.popitem(last=False)

    def clear(self) -> None:
        """清空缓存"""
        with self._lock:
            self.cache.clear()


# 全局缓存实例
_bing_cache = TTLCache(ttl_seconds=300, maxsize=100)  # Bing 搜索缓存 5 分钟
_amap_cache = TTLCache(ttl_seconds=600, maxsize=200)  # 高德 API 缓存 10 分钟


# ==================== 智能缓存预热 (v2.30.25 新增) ====================
async def warmup_cache():
    """
    智能缓存预热 - 预加载常用查询

    v2.30.25 新增:
    - 预加载常用城市天气
    - 预加载常用地点信息
    - 减少首次查询延迟
    """
    logger.info("开始缓存预热...")

    # 常用城市列表
    common_cities = ["北京", "上海", "广州", "深圳", "杭州"]

    try:
        # 预热天气缓存
        from src.agent.builtin_tools import _amap_api_call
        tasks = []
        for city in common_cities:
            params = {"city": city, "extensions": "base"}
            tasks.append(_amap_api_call("weather/weatherInfo", params, _tool_name="cache_warmup"))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        success_count = sum(1 for r in results if not isinstance(r, Exception))
        logger.info(f"缓存预热完成: {success_count}/{len(common_cities)} 个城市天气已缓存")

    except Exception as e:
        logger.warning(f"缓存预热失败: {e}")


# ==================== 指数退避重试 (v2.30.23) ====================
def retry_with_backoff(max_retries: int = 3, base_delay: float = 1.0, max_delay: float = 10.0):
    """
    指数退避重试装饰器

    Args:
        max_retries: 最大重试次数
        base_delay: 基础延迟（秒）
        max_delay: 最大延迟（秒）
    """
    def decorator(func):
        func_name = getattr(func, "name", None) or getattr(func, "__name__", None) or func.__class__.__name__

        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_error = None
            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                    last_error = e
                    if attempt < max_retries:
                        # 指数退避：delay = base_delay * (2 ^ attempt)
                        delay = min(base_delay * (2 ** attempt), max_delay)
                        logger.warning(
                            f"{func_name} 第 {attempt + 1} 次失败，{delay:.1f}秒后重试: {e}"
                        )
                        await asyncio.sleep(delay)

                        # 更新重试统计
                        tool_name = kwargs.get('_tool_name', func_name)
                        with _tool_stats_lock:
                            _tool_stats["retry_count"][tool_name] = _tool_stats["retry_count"].get(tool_name, 0) + 1
                    else:
                        logger.error(f"{func_name} 已达最大重试次数 ({max_retries}): {e}")
                        raise ToolError(ErrorType.NETWORK_ERROR, f"网络请求失败: {str(e)}")
                except Exception as e:
                    # 非网络错误，不重试
                    logger.error(f"{func_name} 执行失败: {e}")
                    raise

            # 理论上不会到这里
            raise last_error
        return wrapper
    return decorator


_async_runtime: Optional[AsyncLoopThread] = None
_async_runtime_lock = threading.Lock()


def _get_async_runtime() -> AsyncLoopThread:
    global _async_runtime
    if _async_runtime is not None:
        return _async_runtime
    with _async_runtime_lock:
        if _async_runtime is None:
            _async_runtime = AsyncLoopThread(thread_name="mintchat-builtin-tools")
    return _async_runtime


def async_to_sync(async_func):
    """
    异步函数转同步装饰器（兼容 LangChain 同步调用）

    v2.30.26 修复:
    - 修复 event loop closed 错误
    - 使用全局 event loop 避免重复创建
    - 支持 nest_asyncio 嵌套调用
    
    v3.3.3 修复:
    - 添加线程安全保护
    - 改进异常处理
    """
    @wraps(async_func)
    def wrapper(*args, **kwargs):
        timeout_s = get_current_tool_timeout_s()
        runtime_timeout: Optional[float] = None
        if timeout_s is not None:
            try:
                timeout_value = float(timeout_s)
                if timeout_value > 0:
                    # 给线程池外层 timeout 留一点余量，优先在协程侧触发取消，避免线程泄露
                    runtime_timeout = max(0.01, timeout_value - 0.05)
            except Exception:
                runtime_timeout = None

        try:
            # 当前线程存在运行中的 event loop（例如在 Jupyter/异步上下文中被同步调用）
            loop = asyncio.get_running_loop()
            try:
                import nest_asyncio

                nest_asyncio.apply()
                coro = async_func(*args, **kwargs)
                if runtime_timeout is not None:
                    coro = asyncio.wait_for(coro, timeout=runtime_timeout)
                return loop.run_until_complete(coro)
            except Exception:
                # fallback：避免 re-entrancy/版本差异导致的异常
                return _get_async_runtime().run(async_func(*args, **kwargs), timeout=runtime_timeout)
        except RuntimeError:
            # 常见路径：同步/线程池环境下，统一在后台 event loop 执行，保证线程安全与 aiohttp 会话复用
            return _get_async_runtime().run(async_func(*args, **kwargs), timeout=runtime_timeout)
    return wrapper


def shutdown_builtin_tools_runtime(timeout_s: float = 2.0) -> None:
    """
    显式关闭 builtin_tools 的后台事件循环与 HTTP 连接池。

    说明：
    - ToolRegistry.close()/Agent.close() 可调用此函数，避免 aiohttp session 残留与线程泄露。
    """
    global _async_runtime
    runtime = _async_runtime
    if runtime is None:
        return

    try:
        # aiohttp ClientSession 必须在创建它的 loop 中关闭
        runtime.run(ConnectionPool.close(), timeout=max(0.1, float(timeout_s)))
    except Exception as exc:
        logger.debug("关闭 builtin_tools 连接池失败（可忽略）: %s", exc)
    finally:
        try:
            runtime.close(timeout=max(0.1, float(timeout_s)))
        except Exception:
            pass
        _async_runtime = None


def track_performance(tool_name: str):
    """性能监控装饰器（v2.30.25 增强：添加延迟百分位统计）"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                execution_time = time.time() - start_time

                # 更新统计
                with _tool_stats_lock:
                    _tool_stats["call_count"][tool_name] = _tool_stats["call_count"].get(tool_name, 0) + 1
                    _tool_stats["total_time"][tool_name] = _tool_stats["total_time"].get(tool_name, 0) + execution_time

                    # v2.30.25: 记录延迟（用于计算 P50/P95/P99）
                    if tool_name not in _tool_stats["latencies"]:
                        _tool_stats["latencies"][tool_name] = []
                    _tool_stats["latencies"][tool_name].append(execution_time)

                    # 限制延迟列表大小（最多保留最近 1000 次）
                    if len(_tool_stats["latencies"][tool_name]) > 1000:
                        _tool_stats["latencies"][tool_name] = _tool_stats["latencies"][tool_name][-1000:]

                logger.debug(f"工具 {tool_name} 执行成功，耗时: {execution_time:.3f}秒")
                return result
            except Exception as e:
                with _tool_stats_lock:
                    _tool_stats["error_count"][tool_name] = _tool_stats["error_count"].get(tool_name, 0) + 1
                logger.error(f"工具 {tool_name} 执行失败: {e}")
                raise
        return wrapper
    return decorator


def get_tool_stats() -> Dict[str, Any]:
    """获取工具性能统计（v2.30.25 增强：添加延迟百分位统计）"""
    import numpy as np

    with _tool_stats_lock:
        snapshot = {key: dict(value) if isinstance(value, dict) else value for key, value in _tool_stats.items()}

    stats = {}
    for tool_name in snapshot["call_count"]:
        call_count = snapshot["call_count"].get(tool_name, 0)
        total_time = snapshot["total_time"].get(tool_name, 0)
        error_count = snapshot["error_count"].get(tool_name, 0)
        retry_count = snapshot["retry_count"].get(tool_name, 0)
        cache_hits = snapshot["cache_hits"].get(tool_name, 0)
        latencies = snapshot["latencies"].get(tool_name, [])

        # 计算延迟百分位（P50/P95/P99）
        p50 = p95 = p99 = 0.0
        if latencies:
            p50 = float(np.percentile(latencies, 50))
            p95 = float(np.percentile(latencies, 95))
            p99 = float(np.percentile(latencies, 99))

        stats[tool_name] = {
            "call_count": call_count,
            "total_time": f"{total_time:.3f}s",
            "avg_time": f"{total_time / call_count:.3f}s" if call_count > 0 else "0s",
            "p50_latency": f"{p50:.3f}s",  # v2.30.25: 新增
            "p95_latency": f"{p95:.3f}s",  # v2.30.25: 新增
            "p99_latency": f"{p99:.3f}s",  # v2.30.25: 新增
            "error_count": error_count,
            "retry_count": retry_count,
            "cache_hits": cache_hits,  # v2.30.25: 新增
            "cache_hit_rate": f"{cache_hits / call_count * 100:.1f}%" if call_count > 0 else "0%",  # v2.30.25: 新增
            "success_rate": f"{(call_count - error_count) / call_count * 100:.1f}%" if call_count > 0 else "0%"
        }
    return stats


# ==================== Bing 搜索工具 (v2.30.23 优化) ====================
@retry_with_backoff(max_retries=3, base_delay=1.0)
async def _bing_search_async(query: str, count: int = 5, _tool_name: str = "bing_web_search") -> List[Dict[str, str]]:
    """
    异步 Bing 搜索（内部实现）

    v2.30.23 优化:
    - 使用全局连接池
    - TTL 缓存（5分钟）
    - 指数退避重试
    """
    # 检查缓存
    cache_key = f"bing_{query}_{count}"
    cached_result = _bing_cache.get(cache_key)
    if cached_result is not None:
        logger.debug(f"Bing 搜索命中缓存: {query}")
        # v2.30.25: 更新缓存命中统计
        with _tool_stats_lock:
            _tool_stats["cache_hits"][_tool_name] = _tool_stats["cache_hits"].get(_tool_name, 0) + 1
        return cached_result

    headers = {
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    }

    url = f"https://cn.bing.com/search?q={query}&count={count}"

    # 使用全局连接池
    session = await ConnectionPool.get_session()
    async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as response:
        if response.status != 200:
            raise ToolError(ErrorType.API_ERROR, f"Bing 搜索返回状态码 {response.status}")

        html = await response.text()

        # 使用 BeautifulSoup 解析 HTML（延迟导入避免启动时额外开销）
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        results = []

        # 查找搜索结果（Bing 的结果在 li.b_algo 中）
        for item in soup.select('li.b_algo')[:count]:
            try:
                # 提取标题
                title_elem = item.select_one('h2 a')
                title = title_elem.get_text(strip=True) if title_elem else "无标题"

                # 提取链接
                link = title_elem.get('href', '') if title_elem else ''

                # 提取描述
                desc_elem = item.select_one('.b_caption p, .b_caption .b_algoSlug')
                description = desc_elem.get_text(strip=True) if desc_elem else "无描述"

                results.append({
                    "title": title,
                    "link": link,
                    "description": description[:200]  # 限制描述长度
                })
            except Exception as e:
                logger.debug(f"解析搜索结果项失败: {e}")
                continue

        # 缓存结果
        _bing_cache.set(cache_key, results)

        return results


@tool
@track_performance("bing_web_search")
@async_to_sync
async def bing_web_search(query: str, count: int = 5) -> str:
    """
    Bing 网络搜索（无需 API Key，HTML 解析）

    v2.30.23 优化:
    - 全局连接池
    - TTL 缓存（5分钟）
    - 指数退避重试
    - 错误分类处理

    Args:
        query: 搜索关键词
        count: 返回结果数量（默认5条）

    Returns:
        str: 搜索结果的 JSON 字符串，包含标题、链接、描述

    示例:
        >>> bing_web_search("Python 编程", 3)
        [{"title": "...", "link": "...", "description": "..."}]
    """
    # 参数验证
    if not query or not query.strip():
        return "抱歉主人，搜索关键词不能为空喵~"
    if count < 1 or count > 50:
        return "抱歉主人，搜索结果数量应在 1-50 之间喵~"

    try:
        results = await _bing_search_async(query, count)

        if results:
            logger.info(f"Bing 搜索成功: {query}，找到 {len(results)} 条结果")
            return json.dumps(results, ensure_ascii=False, indent=2)
        else:
            return f"抱歉主人，没有找到关于'{query}'的搜索结果喵~"

    except ToolError as e:
        # 分类错误处理
        if e.error_type == ErrorType.NETWORK_ERROR:
            return f"抱歉主人，网络连接失败了喵~ 请检查网络连接"
        elif e.error_type == ErrorType.API_ERROR:
            return f"抱歉主人，搜索服务暂时不可用喵~ ({e.message})"
        else:
            return f"抱歉主人，搜索出错了: {e.message} 喵~"
    except asyncio.TimeoutError:
        logger.error(f"Bing 搜索超时: {query}")
        return f"抱歉主人，搜索'{query}'超时了喵~"
    except Exception as e:
        logger.error(f"Bing 搜索失败: {e}")
        return f"抱歉主人，搜索出错了: {str(e)} 喵~"


# ==================== 高德地图工具 (v2.30.23 优化) ====================
@retry_with_backoff(max_retries=3, base_delay=0.5)
async def _amap_api_call(endpoint: str, params: Dict[str, Any], _tool_name: str = "amap_api") -> Dict[str, Any]:
    """
    高德 API 异步调用（内部函数）

    v2.30.23 优化:
    - 使用全局连接池
    - TTL 缓存（10分钟）
    - 指数退避重试
    - 错误分类处理
    """
    api_key = _get_config().get("AMAP", {}).get("api_key", "")
    if not api_key:
        raise ToolError(ErrorType.PARAM_ERROR, "高德地图 API Key 未配置")

    params["key"] = api_key
    params["output"] = "json"

    # 生成缓存键
    cache_key = f"amap_{endpoint}_{json.dumps(params, sort_keys=True)}"
    cached_result = _amap_cache.get(cache_key)
    if cached_result is not None:
        logger.debug(f"高德 API 命中缓存: {endpoint}")
        # v2.30.25: 更新缓存命中统计
        with _tool_stats_lock:
            _tool_stats["cache_hits"][_tool_name] = _tool_stats["cache_hits"].get(_tool_name, 0) + 1
        return cached_result

    url = f"https://restapi.amap.com/v3/{endpoint}"

    # 使用全局连接池
    session = await ConnectionPool.get_session()
    async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as response:
        if response.status != 200:
            raise ToolError(ErrorType.API_ERROR, f"高德 API 返回状态码 {response.status}")

        result = await response.json()

        # 检查 API 返回状态
        if result.get("status") != "1":
            error_msg = result.get("info", "未知错误")
            raise ToolError(ErrorType.API_ERROR, f"高德 API 错误: {error_msg}")

        # 缓存结果
        _amap_cache.set(cache_key, result)

        return result


@tool
@track_performance("amap_poi_search")
@async_to_sync
async def amap_poi_search(keywords: str, city: str = "全国", limit: int = 5) -> str:
    """
    高德地图 POI（地点）搜索

    v2.30.24 优化:
    - 参数验证
    - 错误分类处理
    - TTL 缓存（10分钟）

    Args:
        keywords: 搜索关键词（如"餐厅"、"酒店"、"医院"）
        city: 城市名称（默认"全国"）
        limit: 返回结果数量（默认5条）

    Returns:
        str: POI 搜索结果的 JSON 字符串

    示例:
        >>> amap_poi_search("火锅", "北京", 3)
        [{"name": "海底捞", "address": "...", "location": "...", "type": "餐饮"}]
    """
    # 参数验证
    if not keywords or not keywords.strip():
        return "抱歉主人，搜索关键词不能为空喵~"
    if limit < 1 or limit > 50:
        return "抱歉主人，搜索结果数量应在 1-50 之间喵~"

    try:
        data = await _amap_api_call("place/text", {
            "keywords": keywords,
            "city": city
        }, _tool_name="amap_poi_search")

        if data.get("pois"):
            pois = data["pois"][:limit]
            results = []
            for poi in pois:
                results.append({
                    "name": poi.get("name"),
                    "address": poi.get("address"),
                    "location": poi.get("location"),
                    "type": poi.get("type"),
                    "tel": poi.get("tel", ""),
                    "distance": poi.get("distance", "")
                })

            logger.info(f"高德 POI 搜索成功: {keywords} in {city}，找到 {len(results)} 条结果")
            return json.dumps(results, ensure_ascii=False, indent=2)
        else:
            return f"未找到'{keywords}'的相关地点喵~"

    except ToolError as e:
        if e.error_type == ErrorType.NETWORK_ERROR:
            return "抱歉主人，网络连接失败了喵~ 请检查网络连接"
        elif e.error_type == ErrorType.API_ERROR:
            return f"抱歉主人，高德地图服务暂时不可用喵~ ({e.message})"
        elif e.error_type == ErrorType.PARAM_ERROR:
            return f"抱歉主人，{e.message}喵~"
        else:
            return f"抱歉主人，搜索出错了: {e.message} 喵~"
    except Exception as e:
        logger.error(f"高德 POI 搜索失败: {e}")
        return f"抱歉主人，搜索出错了: {str(e)} 喵~"


@tool
@track_performance("amap_geocode")
@async_to_sync
async def amap_geocode(address: str, city: str = "") -> str:
    """
    高德地图地理编码（地址 → 经纬度）

    v2.30.24 优化:
    - 参数验证
    - 错误分类处理
    - TTL 缓存（10分钟）

    Args:
        address: 地址（如"北京市朝阳区阜通东大街6号"）
        city: 城市名称（可选，用于提高准确性）

    Returns:
        str: 地理编码结果的 JSON 字符串

    示例:
        >>> amap_geocode("天安门", "北京")
        {"address": "天安门", "location": "116.397128,39.916527", "level": "兴趣点"}
    """
    # 参数验证
    if not address or not address.strip():
        return "抱歉主人，地址不能为空喵~"

    try:
        params = {"address": address}
        if city:
            params["city"] = city

        data = await _amap_api_call("geocode/geo", params, _tool_name="amap_geocode")

        if data.get("geocodes"):
            geocode = data["geocodes"][0]
            result = {
                "address": geocode.get("formatted_address"),
                "location": geocode.get("location"),
                "level": geocode.get("level"),
                "province": geocode.get("province"),
                "city": geocode.get("city"),
                "district": geocode.get("district")
            }

            logger.info(f"高德地理编码成功: {address}")
            return json.dumps(result, ensure_ascii=False, indent=2)
        else:
            return f"未找到地址'{address}'的地理编码喵~"

    except ToolError as e:
        if e.error_type == ErrorType.NETWORK_ERROR:
            return "抱歉主人，网络连接失败了喵~ 请检查网络连接"
        elif e.error_type == ErrorType.API_ERROR:
            return f"抱歉主人，高德地图服务暂时不可用喵~ ({e.message})"
        elif e.error_type == ErrorType.PARAM_ERROR:
            return f"抱歉主人，{e.message}喵~"
        else:
            return f"抱歉主人，地理编码出错了: {e.message} 喵~"
    except Exception as e:
        logger.error(f"高德地理编码失败: {e}")
        return f"抱歉主人，地理编码出错了: {str(e)} 喵~"


@tool
@track_performance("amap_regeo")
@async_to_sync
async def amap_regeo(location: str, radius: int = 1000) -> str:
    """
    高德地图逆地理编码（经纬度 → 地址）

    v2.30.24 优化:
    - 参数验证
    - 错误分类处理
    - TTL 缓存（10分钟）

    Args:
        location: 经纬度（格式："经度,纬度"，如"116.481488,39.990464"）
        radius: 搜索半径（米，默认1000米）

    Returns:
        str: 逆地理编码结果的 JSON 字符串

    示例:
        >>> amap_regeo("116.481488,39.990464")
        {"address": "北京市朝阳区...", "province": "北京市", "city": "北京市"}
    """
    # 参数验证
    if not location or not location.strip():
        return "抱歉主人，经纬度不能为空喵~"
    if "," not in location:
        return "抱歉主人，经纬度格式应为'经度,纬度'喵~"
    if radius < 0 or radius > 3000:
        return "抱歉主人，搜索半径应在 0-3000 米之间喵~"

    try:
        data = await _amap_api_call("geocode/regeo", {
            "location": location,
            "radius": radius
        }, _tool_name="amap_regeo")

        if data.get("regeocode"):
            regeocode = data["regeocode"]
            addressComponent = regeocode.get("addressComponent", {})

            result = {
                "address": regeocode.get("formatted_address"),
                "province": addressComponent.get("province"),
                "city": addressComponent.get("city"),
                "district": addressComponent.get("district"),
                "township": addressComponent.get("township"),
                "street": addressComponent.get("streetNumber", {}).get("street"),
                "number": addressComponent.get("streetNumber", {}).get("number")
            }

            logger.info(f"高德逆地理编码成功: {location}")
            return json.dumps(result, ensure_ascii=False, indent=2)
        else:
            return f"未找到位置'{location}'的地址信息喵~"

    except ToolError as e:
        if e.error_type == ErrorType.NETWORK_ERROR:
            return "抱歉主人，网络连接失败了喵~ 请检查网络连接"
        elif e.error_type == ErrorType.API_ERROR:
            return f"抱歉主人，高德地图服务暂时不可用喵~ ({e.message})"
        elif e.error_type == ErrorType.PARAM_ERROR:
            return f"抱歉主人，{e.message}喵~"
        else:
            return f"抱歉主人，逆地理编码出错了: {e.message} 喵~"
    except Exception as e:
        logger.error(f"高德逆地理编码失败: {e}")
        return f"抱歉主人，逆地理编码出错了: {str(e)} 喵~"


@tool
@track_performance("amap_route_plan")
@async_to_sync
async def amap_route_plan(origin: str, destination: str, strategy: int = 0, waypoints: str = "") -> str:
    """
    高德地图路线规划（驾车）

    v2.30.24 优化:
    - 参数验证
    - 错误分类处理
    - TTL 缓存（10分钟）

    Args:
        origin: 起点（经纬度，格式："经度,纬度"）
        destination: 终点（经纬度，格式："经度,纬度"）
        strategy: 路线策略（0-速度优先，1-费用优先，2-距离优先，3-不走高速）
        waypoints: 途经点（可选，多个途经点用分号分隔）

    Returns:
        str: 路线规划结果的 JSON 字符串

    示例:
        >>> amap_route_plan("116.481028,39.989643", "116.434446,39.90816")
        {"distance": "10.5km", "duration": "25分钟", "tolls": "5元", "steps": [...]}
    """
    # 参数验证
    if not origin or not origin.strip():
        return "抱歉主人，起点不能为空喵~"
    if not destination or not destination.strip():
        return "抱歉主人，终点不能为空喵~"
    if "," not in origin or "," not in destination:
        return "抱歉主人，经纬度格式应为'经度,纬度'喵~"
    if strategy < 0 or strategy > 10:
        return "抱歉主人，路线策略应在 0-10 之间喵~"

    try:
        params = {
            "origin": origin,
            "destination": destination,
            "strategy": strategy
        }
        if waypoints:
            params["waypoints"] = waypoints

        data = await _amap_api_call("direction/driving", params, _tool_name="amap_route_plan")

        if data.get("route"):
            route = data["route"]
            paths = route.get("paths", [])

            if paths:
                path = paths[0]  # 取第一条路线

                # 提取关键步骤
                steps = []
                for step in path.get("steps", [])[:10]:  # 最多10步
                    steps.append({
                        "instruction": step.get("instruction"),
                        "road": step.get("road"),
                        "distance": f"{int(step.get('distance', 0))}米",
                        "duration": f"{int(step.get('duration', 0)) // 60}分钟"
                    })

                result = {
                    "distance": f"{float(path.get('distance', 0)) / 1000:.1f}公里",
                    "duration": f"{int(path.get('duration', 0)) // 60}分钟",
                    "tolls": f"{path.get('tolls', 0)}元",
                    "traffic_lights": f"{path.get('traffic_lights', 0)}个红绿灯",
                    "steps": steps
                }

                logger.info(f"高德路线规划成功: {origin} -> {destination}")
                return json.dumps(result, ensure_ascii=False, indent=2)
            else:
                return f"未找到从'{origin}'到'{destination}'的路线喵~"
        else:
            return f"路线规划失败喵~"

    except ToolError as e:
        if e.error_type == ErrorType.NETWORK_ERROR:
            return "抱歉主人，网络连接失败了喵~ 请检查网络连接"
        elif e.error_type == ErrorType.API_ERROR:
            return f"抱歉主人，高德地图服务暂时不可用喵~ ({e.message})"
        elif e.error_type == ErrorType.PARAM_ERROR:
            return f"抱歉主人，{e.message}喵~"
        else:
            return f"抱歉主人，路线规划出错了: {e.message} 喵~"
    except Exception as e:
        logger.error(f"高德路线规划失败: {e}")
        return f"抱歉主人，路线规划出错了: {str(e)} 喵~"


@tool
@track_performance("amap_weather")
@async_to_sync
async def amap_weather(city: str, extensions: str = "base") -> str:
    """
    高德天气查询

    v2.30.24 优化:
    - 参数验证
    - 错误分类处理
    - TTL 缓存（10分钟）

    Args:
        city: 城市名称或城市编码（如"北京"或"110000"）
        extensions: 查询类型（"base"-实况天气，"all"-预报天气）

    Returns:
        str: 天气信息的 JSON 字符串

    示例:
        >>> amap_weather("北京")
        {"city": "北京市", "weather": "晴", "temperature": "5°C", ...}
    """
    # 参数验证
    if not city or not city.strip():
        return "抱歉主人，城市名称不能为空喵~"
    if extensions not in ["base", "all"]:
        return "抱歉主人，查询类型应为 'base' 或 'all' 喵~"

    try:
        data = await _amap_api_call("weather/weatherInfo", {
            "city": city,
            "extensions": extensions
        }, _tool_name="amap_weather")

        if extensions == "base" and data.get("lives"):
            # 实况天气
            live = data["lives"][0]
            result = {
                "city": live.get("city"),
                "weather": live.get("weather"),
                "temperature": f"{live.get('temperature')}°C",
                "humidity": f"{live.get('humidity')}%",
                "wind_direction": live.get("winddirection"),
                "wind_power": f"{live.get('windpower')}级",
                "report_time": live.get("reporttime")
            }
        elif extensions == "all" and data.get("forecasts"):
            # 预报天气
            forecast = data["forecasts"][0]
            casts = forecast.get("casts", [])[:3]  # 未来3天

            result = {
                "city": forecast.get("city"),
                "forecasts": [
                    {
                        "date": cast.get("date"),
                        "week": cast.get("week"),
                        "dayweather": cast.get("dayweather"),
                        "nightweather": cast.get("nightweather"),
                        "daytemp": f"{cast.get('daytemp')}°C",
                        "nighttemp": f"{cast.get('nighttemp')}°C"
                    }
                    for cast in casts
                ]
            }
        else:
            return f"未找到城市'{city}'的天气信息喵~"

        logger.info(f"高德天气查询成功: {city}")
        return json.dumps(result, ensure_ascii=False, indent=2)

    except ToolError as e:
        if e.error_type == ErrorType.NETWORK_ERROR:
            return "抱歉主人，网络连接失败了喵~ 请检查网络连接"
        elif e.error_type == ErrorType.API_ERROR:
            return f"抱歉主人，高德地图服务暂时不可用喵~ ({e.message})"
        elif e.error_type == ErrorType.PARAM_ERROR:
            return f"抱歉主人，{e.message}喵~"
        else:
            return f"抱歉主人，天气查询出错了: {e.message} 喵~"
    except Exception as e:
        logger.error(f"高德天气查询失败: {e}")
        return f"抱歉主人，天气查询出错了: {str(e)} 喵~"


# ==================== 时间工具（增强版）====================
@tool
@track_performance("get_time_in_timezone")
def get_time_in_timezone(timezone_name: str = "Asia/Shanghai") -> str:
    """
    获取指定时区的当前时间

    Args:
        timezone_name: 时区名称（如 "Asia/Shanghai", "America/New_York"）

    Returns:
        str: 时间信息的 JSON 字符串
    """
    try:
        tz = ZoneInfo(timezone_name)
        now = datetime.now(tz)

        result = {
            "timezone": timezone_name,
            "datetime": now.isoformat(),
            "date": now.strftime("%Y-%m-%d"),
            "time": now.strftime("%H:%M:%S"),
            "day_of_week": now.strftime("%A"),
            "is_dst": bool(now.dst())
        }

        logger.info(f"获取时区时间成功: {timezone_name}")
        return json.dumps(result, ensure_ascii=False, indent=2)

    except Exception as e:
        logger.error(f"获取时区时间失败: {e}")
        return f"抱歉主人，时区'{timezone_name}'不存在或查询失败喵~"


@tool
@track_performance("convert_timezone")
def convert_timezone(time_str: str, from_tz: str, to_tz: str) -> str:
    """
    时区转换

    Args:
        time_str: 时间字符串（ISO 格式，如 "2025-11-16T10:00:00"）
        from_tz: 源时区（如 "Asia/Shanghai"）
        to_tz: 目标时区（如 "America/New_York"）

    Returns:
        str: 转换后的时间信息
    """
    try:
        # 解析时间
        dt = datetime.fromisoformat(time_str)

        # 设置源时区
        from_timezone = ZoneInfo(from_tz)
        dt_with_tz = dt.replace(tzinfo=from_timezone)

        # 转换到目标时区
        to_timezone = ZoneInfo(to_tz)
        converted_dt = dt_with_tz.astimezone(to_timezone)

        result = {
            "original_time": dt_with_tz.isoformat(),
            "original_timezone": from_tz,
            "converted_time": converted_dt.isoformat(),
            "converted_timezone": to_tz,
            "time_difference": str(converted_dt.utcoffset() - dt_with_tz.utcoffset())
        }

        logger.info(f"时区转换成功: {from_tz} -> {to_tz}")
        return json.dumps(result, ensure_ascii=False, indent=2)

    except Exception as e:
        logger.error(f"时区转换失败: {e}")
        return f"抱歉主人，时区转换失败: {str(e)} 喵~"


# ==================== 批量操作工具 (v2.30.24 新增) ====================
@tool
@track_performance("amap_batch_geocode")
@async_to_sync
async def amap_batch_geocode(addresses: str, city: str = "") -> str:
    """
    批量地理编码（地址 → 经纬度）

    v2.30.24 新增:
    - 批量处理多个地址
    - 并发 API 调用
    - 统一错误处理

    Args:
        addresses: 地址列表（用分号分隔，如"天安门;故宫;鸟巢"）
        city: 城市名称（可选，用于提高准确性）

    Returns:
        str: 批量地理编码结果的 JSON 字符串

    示例:
        >>> amap_batch_geocode("天安门;故宫", "北京")
        [{"address": "天安门", "location": "..."}, {"address": "故宫", "location": "..."}]
    """
    # 参数验证
    if not addresses or not addresses.strip():
        return "抱歉主人，地址列表不能为空喵~"

    address_list = [addr.strip() for addr in addresses.split(";") if addr.strip()]
    if not address_list:
        return "抱歉主人，没有有效的地址喵~"
    if len(address_list) > 20:
        return "抱歉主人，批量地理编码最多支持 20 个地址喵~"

    try:
        # 并发调用地理编码 API
        tasks = []
        for address in address_list:
            params = {"address": address}
            if city:
                params["city"] = city
            tasks.append(_amap_api_call("geocode/geo", params, _tool_name="amap_batch_geocode"))

        # 等待所有任务完成
        results_data = await asyncio.gather(*tasks, return_exceptions=True)

        # 处理结果
        results = []
        for i, data in enumerate(results_data):
            if isinstance(data, Exception):
                results.append({
                    "address": address_list[i],
                    "status": "error",
                    "message": str(data)
                })
            elif data.get("geocodes"):
                geocode = data["geocodes"][0]
                results.append({
                    "address": address_list[i],
                    "status": "success",
                    "location": geocode.get("location"),
                    "formatted_address": geocode.get("formatted_address"),
                    "level": geocode.get("level")
                })
            else:
                results.append({
                    "address": address_list[i],
                    "status": "not_found",
                    "message": "未找到地理编码"
                })

        success_count = sum(1 for r in results if r.get("status") == "success")
        logger.info(f"批量地理编码完成: {success_count}/{len(address_list)} 成功")
        return json.dumps(results, ensure_ascii=False, indent=2)

    except Exception as e:
        logger.error(f"批量地理编码失败: {e}")
        return f"抱歉主人，批量地理编码出错了: {str(e)} 喵~"


@tool
@track_performance("amap_batch_route_plan")
@async_to_sync
async def amap_batch_route_plan(routes: str, strategy: int = 0) -> str:
    """
    批量路线规划（驾车）

    v2.30.24 新增:
    - 批量处理多条路线
    - 并发 API 调用
    - 统一错误处理

    Args:
        routes: 路线列表（格式："起点1,终点1;起点2,终点2"，经纬度格式）
        strategy: 路线策略（0-速度优先，1-费用优先，2-距离优先，3-不走高速）

    Returns:
        str: 批量路线规划结果的 JSON 字符串

    示例:
        >>> amap_batch_route_plan("116.481028,39.989643,116.434446,39.90816;...")
        [{"origin": "...", "destination": "...", "distance": "...", "duration": "..."}]
    """
    # 参数验证
    if not routes or not routes.strip():
        return "抱歉主人，路线列表不能为空喵~"

    route_list = []
    for route in routes.split(";"):
        route = route.strip()
        if not route:
            continue
        parts = route.split(",")
        if len(parts) != 4:
            return f"抱歉主人，路线格式应为'起点经度,起点纬度,终点经度,终点纬度'喵~"
        route_list.append({
            "origin": f"{parts[0]},{parts[1]}",
            "destination": f"{parts[2]},{parts[3]}"
        })

    if not route_list:
        return "抱歉主人，没有有效的路线喵~"
    if len(route_list) > 10:
        return "抱歉主人，批量路线规划最多支持 10 条路线喵~"

    try:
        # 并发调用路线规划 API
        tasks = []
        for route in route_list:
            params = {
                "origin": route["origin"],
                "destination": route["destination"],
                "strategy": strategy
            }
            tasks.append(_amap_api_call("direction/driving", params, _tool_name="amap_batch_route_plan"))

        # 等待所有任务完成
        results_data = await asyncio.gather(*tasks, return_exceptions=True)

        # 处理结果
        results = []
        for i, data in enumerate(results_data):
            route_info = route_list[i]
            if isinstance(data, Exception):
                results.append({
                    "origin": route_info["origin"],
                    "destination": route_info["destination"],
                    "status": "error",
                    "message": str(data)
                })
            elif data.get("route") and data["route"].get("paths"):
                path = data["route"]["paths"][0]
                results.append({
                    "origin": route_info["origin"],
                    "destination": route_info["destination"],
                    "status": "success",
                    "distance": f"{float(path.get('distance', 0)) / 1000:.1f}公里",
                    "duration": f"{int(path.get('duration', 0)) // 60}分钟",
                    "tolls": f"{path.get('tolls', 0)}元"
                })
            else:
                results.append({
                    "origin": route_info["origin"],
                    "destination": route_info["destination"],
                    "status": "not_found",
                    "message": "未找到路线"
                })

        success_count = sum(1 for r in results if r.get("status") == "success")
        logger.info(f"批量路线规划完成: {success_count}/{len(route_list)} 成功")
        return json.dumps(results, ensure_ascii=False, indent=2)

    except Exception as e:
        logger.error(f"批量路线规划失败: {e}")
        return f"抱歉主人，批量路线规划出错了: {str(e)} 喵~"


@tool
@track_performance("amap_batch_weather")
@async_to_sync
async def amap_batch_weather(cities: str, extensions: str = "base") -> str:
    """
    批量天气查询

    v2.30.25 新增:
    - 批量处理多个城市
    - 并发 API 调用
    - 统一错误处理

    Args:
        cities: 城市列表（用分号分隔，如"北京;上海;广州"）
        extensions: 查询类型（base-实况天气，all-预报天气）

    Returns:
        str: 批量天气查询结果的 JSON 字符串

    示例:
        >>> amap_batch_weather("北京;上海;广州", "base")
        [{"city": "北京", "weather": "晴", "temperature": "25℃"}, ...]
    """
    # 参数验证
    if not cities or not cities.strip():
        return "抱歉主人，城市列表不能为空喵~"
    if extensions not in ["base", "all"]:
        return "抱歉主人，查询类型应为 'base' 或 'all' 喵~"

    city_list = [city.strip() for city in cities.split(";") if city.strip()]
    if not city_list:
        return "抱歉主人，没有有效的城市喵~"
    if len(city_list) > 20:
        return "抱歉主人，批量天气查询最多支持 20 个城市喵~"

    try:
        # 并发调用天气查询 API
        tasks = []
        for city in city_list:
            params = {"city": city, "extensions": extensions}
            tasks.append(_amap_api_call("weather/weatherInfo", params, _tool_name="amap_batch_weather"))

        # 等待所有任务完成
        results_data = await asyncio.gather(*tasks, return_exceptions=True)

        # 处理结果
        results = []
        for i, data in enumerate(results_data):
            city = city_list[i]
            if isinstance(data, Exception):
                results.append({
                    "city": city,
                    "status": "error",
                    "message": str(data)
                })
            elif data.get("lives"):
                # 实况天气
                live = data["lives"][0]
                results.append({
                    "city": city,
                    "status": "success",
                    "weather": live.get("weather"),
                    "temperature": f"{live.get('temperature')}℃",
                    "humidity": f"{live.get('humidity')}%",
                    "wind_direction": live.get("winddirection"),
                    "wind_power": f"{live.get('windpower')}级"
                })
            elif data.get("forecasts"):
                # 预报天气
                forecast = data["forecasts"][0]
                results.append({
                    "city": city,
                    "status": "success",
                    "forecast": forecast.get("casts", [])[:3]  # 只返回前3天
                })
            else:
                results.append({
                    "city": city,
                    "status": "not_found",
                    "message": "未找到天气信息"
                })

        success_count = sum(1 for r in results if r.get("status") == "success")
        logger.info(f"批量天气查询完成: {success_count}/{len(city_list)} 成功")
        return json.dumps(results, ensure_ascii=False, indent=2)

    except Exception as e:
        logger.error(f"批量天气查询失败: {e}")
        return f"抱歉主人，批量天气查询出错了: {str(e)} 喵~"


@tool
@track_performance("amap_batch_poi_search")
@async_to_sync
async def amap_batch_poi_search(keywords_list: str, city: str = "全国", limit: int = 3) -> str:
    """
    批量 POI 搜索

    v2.30.25 新增:
    - 批量处理多个关键词
    - 并发 API 调用
    - 统一错误处理

    Args:
        keywords_list: 关键词列表（用分号分隔，如"咖啡馆;餐厅;酒店"）
        city: 城市名称（默认"全国"）
        limit: 每个关键词返回的结果数量（默认3）

    Returns:
        str: 批量 POI 搜索结果的 JSON 字符串

    示例:
        >>> amap_batch_poi_search("咖啡馆;餐厅", "北京", 3)
        [{"keyword": "咖啡馆", "results": [...]}, {"keyword": "餐厅", "results": [...]}]
    """
    # 参数验证
    if not keywords_list or not keywords_list.strip():
        return "抱歉主人，关键词列表不能为空喵~"
    if limit < 1 or limit > 10:
        return "抱歉主人，每个关键词的结果数量应在 1-10 之间喵~"

    keywords = [kw.strip() for kw in keywords_list.split(";") if kw.strip()]
    if not keywords:
        return "抱歉主人，没有有效的关键词喵~"
    if len(keywords) > 10:
        return "抱歉主人，批量 POI 搜索最多支持 10 个关键词喵~"

    try:
        # 并发调用 POI 搜索 API
        tasks = []
        for keyword in keywords:
            params = {"keywords": keyword, "city": city}
            tasks.append(_amap_api_call("place/text", params, _tool_name="amap_batch_poi_search"))

        # 等待所有任务完成
        results_data = await asyncio.gather(*tasks, return_exceptions=True)

        # 处理结果
        results = []
        for i, data in enumerate(results_data):
            keyword = keywords[i]
            if isinstance(data, Exception):
                results.append({
                    "keyword": keyword,
                    "status": "error",
                    "message": str(data)
                })
            elif data.get("pois"):
                pois = data["pois"][:limit]
                poi_list = []
                for poi in pois:
                    poi_list.append({
                        "name": poi.get("name"),
                        "address": poi.get("address"),
                        "location": poi.get("location"),
                        "type": poi.get("type")
                    })
                results.append({
                    "keyword": keyword,
                    "status": "success",
                    "count": len(poi_list),
                    "results": poi_list
                })
            else:
                results.append({
                    "keyword": keyword,
                    "status": "not_found",
                    "message": "未找到 POI"
                })

        success_count = sum(1 for r in results if r.get("status") == "success")
        logger.info(f"批量 POI 搜索完成: {success_count}/{len(keywords)} 成功")
        return json.dumps(results, ensure_ascii=False, indent=2)

    except Exception as e:
        logger.error(f"批量 POI 搜索失败: {e}")
        return f"抱歉主人，批量 POI 搜索出错了: {str(e)} 喵~"


# ==================== 工具列表 (v2.30.25 更新) ====================
BUILTIN_TOOLS = [
    # 搜索工具
    bing_web_search,

    # 高德地图工具
    amap_poi_search,
    amap_geocode,
    amap_regeo,
    amap_route_plan,
    amap_weather,

    # 批量操作工具 (v2.30.24-v2.30.25)
    amap_batch_geocode,
    amap_batch_route_plan,
    amap_batch_weather,      # v2.30.25 新增
    amap_batch_poi_search,   # v2.30.25 新增

    # 时间工具
    get_time_in_timezone,
    convert_timezone,
]


def get_builtin_tools() -> List:
    """
    获取所有内置工具

    Returns:
        List: 工具列表
    """
    return BUILTIN_TOOLS


def get_tool_statistics() -> str:
    """
    获取工具性能统计（JSON 格式）

    Returns:
        str: 性能统计的 JSON 字符串
    """
    stats = get_tool_stats()
    return json.dumps(stats, ensure_ascii=False, indent=2)


def generate_performance_report(output_path: Optional[str] = None) -> str:
    """
    生成性能监控报告（v2.30.26 新增）

    生成包含以下内容的性能报告：
    - 工具调用统计表格
    - P50/P95/P99 延迟趋势图
    - 缓存命中率图表
    - 错误率统计

    Args:
        output_path: 报告输出路径（默认为 logs/performance_report_YYYYMMDD_HHMMSS.png）

    Returns:
        str: 报告文件路径或错误消息
    """
    try:
        import matplotlib
        matplotlib.use('Agg')  # 使用非交互式后端
        import matplotlib.pyplot as plt
        import numpy as np
        from datetime import datetime

        # 获取统计数据
        stats = get_tool_stats()

        if not stats:
            return "暂无性能数据"

        # 设置中文字体
        plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'Arial Unicode MS']
        plt.rcParams['axes.unicode_minus'] = False

        # 创建图表
        fig, axes = plt.subplots(2, 2, figsize=(16, 12))
        fig.suptitle('内置工具系统性能监控报告', fontsize=16, fontweight='bold')

        # 准备数据
        tool_names = []
        call_counts = []
        p50_latencies = []
        p95_latencies = []
        p99_latencies = []
        cache_hit_rates = []
        error_rates = []

        for tool_name, tool_stats in stats.items():
            tool_names.append(tool_name)
            call_counts.append(tool_stats.get('call_count', 0))

            # 解析时间字符串（去掉 's' 后缀）
            p50_str = tool_stats.get('p50_latency', '0s').replace('s', '')
            p50_latencies.append(float(p50_str))

            p95_str = tool_stats.get('p95_latency', '0s').replace('s', '')
            p95_latencies.append(float(p95_str))

            p99_str = tool_stats.get('p99_latency', '0s').replace('s', '')
            p99_latencies.append(float(p99_str))

            # 解析缓存命中率（去掉 '%' 后缀）
            cache_hit_rate_str = tool_stats.get('cache_hit_rate', '0%').replace('%', '')
            cache_hit_rates.append(float(cache_hit_rate_str))

            # 计算错误率
            call_count = tool_stats.get('call_count', 0)
            error_count = tool_stats.get('error_count', 0)
            error_rate = (error_count / call_count * 100) if call_count > 0 else 0
            error_rates.append(error_rate)

        # 图表1: 调用次数柱状图
        ax1 = axes[0, 0]
        bars1 = ax1.bar(range(len(tool_names)), call_counts, color='skyblue', edgecolor='navy')
        ax1.set_xlabel('工具名称', fontsize=12)
        ax1.set_ylabel('调用次数', fontsize=12)
        ax1.set_title('工具调用次数统计', fontsize=14, fontweight='bold')
        ax1.set_xticks(range(len(tool_names)))
        ax1.set_xticklabels(tool_names, rotation=45, ha='right', fontsize=9)
        ax1.grid(axis='y', alpha=0.3)

        # 在柱状图上显示数值
        for i, bar in enumerate(bars1):
            height = bar.get_height()
            ax1.text(bar.get_x() + bar.get_width()/2., height,
                    f'{int(height)}',
                    ha='center', va='bottom', fontsize=8)

        # 图表2: P50/P95/P99 延迟对比
        ax2 = axes[0, 1]
        x = np.arange(len(tool_names))
        width = 0.25

        bars2_1 = ax2.bar(x - width, p50_latencies, width, label='P50', color='lightgreen', edgecolor='green')
        bars2_2 = ax2.bar(x, p95_latencies, width, label='P95', color='orange', edgecolor='darkorange')
        bars2_3 = ax2.bar(x + width, p99_latencies, width, label='P99', color='salmon', edgecolor='red')

        ax2.set_xlabel('工具名称', fontsize=12)
        ax2.set_ylabel('延迟 (秒)', fontsize=12)
        ax2.set_title('延迟百分位统计 (P50/P95/P99)', fontsize=14, fontweight='bold')
        ax2.set_xticks(x)
        ax2.set_xticklabels(tool_names, rotation=45, ha='right', fontsize=9)
        ax2.legend(fontsize=10)
        ax2.grid(axis='y', alpha=0.3)

        # 图表3: 缓存命中率
        ax3 = axes[1, 0]
        colors = ['green' if rate >= 50 else 'orange' if rate >= 20 else 'red' for rate in cache_hit_rates]
        bars3 = ax3.bar(range(len(tool_names)), cache_hit_rates, color=colors, edgecolor='black', alpha=0.7)
        ax3.set_xlabel('工具名称', fontsize=12)
        ax3.set_ylabel('缓存命中率 (%)', fontsize=12)
        ax3.set_title('缓存命中率统计', fontsize=14, fontweight='bold')
        ax3.set_xticks(range(len(tool_names)))
        ax3.set_xticklabels(tool_names, rotation=45, ha='right', fontsize=9)
        ax3.axhline(y=50, color='green', linestyle='--', alpha=0.5, label='良好 (≥50%)')
        ax3.axhline(y=20, color='orange', linestyle='--', alpha=0.5, label='一般 (≥20%)')
        ax3.legend(fontsize=10)
        ax3.grid(axis='y', alpha=0.3)

        # 在柱状图上显示数值
        for i, bar in enumerate(bars3):
            height = bar.get_height()
            ax3.text(bar.get_x() + bar.get_width()/2., height,
                    f'{height:.1f}%',
                    ha='center', va='bottom', fontsize=8)

        # 图表4: 错误率统计
        ax4 = axes[1, 1]
        colors4 = ['green' if rate == 0 else 'orange' if rate < 5 else 'red' for rate in error_rates]
        bars4 = ax4.bar(range(len(tool_names)), error_rates, color=colors4, edgecolor='black', alpha=0.7)
        ax4.set_xlabel('工具名称', fontsize=12)
        ax4.set_ylabel('错误率 (%)', fontsize=12)
        ax4.set_title('错误率统计', fontsize=14, fontweight='bold')
        ax4.set_xticks(range(len(tool_names)))
        ax4.set_xticklabels(tool_names, rotation=45, ha='right', fontsize=9)
        ax4.axhline(y=5, color='orange', linestyle='--', alpha=0.5, label='警告 (≥5%)')
        ax4.legend(fontsize=10)
        ax4.grid(axis='y', alpha=0.3)

        # 在柱状图上显示数值
        for i, bar in enumerate(bars4):
            height = bar.get_height()
            if height > 0:
                ax4.text(bar.get_x() + bar.get_width()/2., height,
                        f'{height:.1f}%',
                        ha='center', va='bottom', fontsize=8)

        # 调整布局
        plt.tight_layout()

        # 保存图表
        if output_path is None:
            output_path = Path("logs") / f"performance_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        else:
            output_path = Path(output_path)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        plt.savefig(output_path, dpi=150, bbox_inches='tight')
        plt.close()

        logger.info(f"性能监控报告已生成: {output_path}")
        return str(output_path)

    except ImportError as e:
        logger.warning(f"生成性能报告需要 matplotlib: {e}")
        return "需要安装 matplotlib 才能生成性能报告"
    except Exception as e:
        logger.error(f"生成性能报告失败: {e}")
        return f"生成性能报告失败: {str(e)}"
