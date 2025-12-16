"""
统一HTTP连接池管理器 (v2.48.13)

提供全局HTTP连接池，优化网络请求性能。
支持连接复用、DNS缓存、自动重试。

作者: MintChat Team
日期: 2025-11-18
"""

import asyncio
import sys
import aiohttp
from typing import Optional, Dict, Any
from src.utils.logger import get_logger

logger = get_logger(__name__)


class HTTPConnectionPool:
    """统一HTTP连接池管理器（单例模式）"""
    
    _instance: Optional['HTTPConnectionPool'] = None
    _lock = asyncio.Lock()
    
    def __init__(self):
        """初始化HTTP连接池"""
        self._session: Optional[aiohttp.ClientSession] = None
        self._connector: Optional[aiohttp.TCPConnector] = None
        self._stats = {
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "total_bytes_sent": 0,
            "total_bytes_received": 0,
        }
    
    @classmethod
    async def get_instance(cls) -> 'HTTPConnectionPool':
        """获取单例实例"""
        if cls._instance is None:
            async with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
                    await cls._instance._init_session()
        return cls._instance
    
    async def _init_session(self):
        """初始化HTTP会话"""
        if self._session is not None and not self._session.closed:
            return
        
        connector_kwargs: dict[str, Any] = {
            "limit": 100,  # 全局最大连接数
            "limit_per_host": 30,  # 单主机最大连接数
            "ttl_dns_cache": 600,  # DNS缓存10分钟
            "keepalive_timeout": 60,  # Keep-Alive超时60秒
            "force_close": False,  # 启用连接复用
            "use_dns_cache": True,  # 启用DNS缓存
            "family": 0,  # 自动选择IPv4/IPv6
        }
        # Python 3.13.5+ 已修复底层问题，aiohttp 会忽略并给出弃用警告
        if sys.version_info < (3, 13, 5):
            connector_kwargs["enable_cleanup_closed"] = True

        # 优化的TCP连接器
        self._connector = aiohttp.TCPConnector(**connector_kwargs)
        
        # 创建HTTP会话
        self._session = aiohttp.ClientSession(
            connector=self._connector,
            timeout=aiohttp.ClientTimeout(
                total=30,  # 总超时30秒
                connect=5,  # 连接超时5秒
                sock_read=25,  # 读取超时25秒
            ),
            connector_owner=True,
            headers={
                'Accept-Encoding': 'gzip, deflate',
                'Connection': 'keep-alive',
                'User-Agent': 'MintChat/2.48.13',
            },
            auto_decompress=True,  # 自动解压缩
        )
        
        logger.info("统一HTTP连接池已初始化")
    
    async def get_session(self) -> aiohttp.ClientSession:
        """
        获取HTTP会话
        
        Returns:
            aiohttp.ClientSession
        """
        if self._session is None or self._session.closed:
            await self._init_session()
        
        return self._session
    
    async def request(
        self,
        method: str,
        url: str,
        **kwargs
    ) -> aiohttp.ClientResponse:
        """
        发送HTTP请求（带统计）
        
        Args:
            method: HTTP方法（GET/POST等）
            url: 请求URL
            **kwargs: 其他参数
            
        Returns:
            aiohttp.ClientResponse
        """
        session = await self.get_session()
        self._stats["total_requests"] += 1
        
        try:
            response = await session.request(method, url, **kwargs)
            self._stats["successful_requests"] += 1
            return response
        except Exception as e:
            self._stats["failed_requests"] += 1
            logger.error(f"HTTP请求失败: {method} {url}, 错误: {e}")
            raise
    
    async def get(self, url: str, **kwargs) -> aiohttp.ClientResponse:
        """GET请求"""
        return await self.request("GET", url, **kwargs)
    
    async def post(self, url: str, **kwargs) -> aiohttp.ClientResponse:
        """POST请求"""
        return await self.request("POST", url, **kwargs)
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return self._stats.copy()
    
    async def close(self):
        """关闭连接池"""
        if self._session and not self._session.closed:
            await self._session.close()
            logger.info("统一HTTP连接池已关闭")


# 全局HTTP连接池实例
async def get_http_pool() -> HTTPConnectionPool:
    """获取全局HTTP连接池"""
    return await HTTPConnectionPool.get_instance()
