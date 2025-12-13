"""
异步数据库包装器 - v2.32.0

提供异步数据库操作接口，避免阻塞主线程，提升性能。

核心功能:
- 异步SQLite操作
- 连接池管理
- 事务支持
- 性能监控

依赖: aiosqlite (需要安装: pip install aiosqlite)
"""

import asyncio
import aiosqlite
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from contextlib import asynccontextmanager
import time

from src.utils.logger import get_logger

logger = get_logger(__name__)


class AsyncDatabasePool:
    """异步数据库连接池"""
    
    def __init__(
        self,
        database_path: Path,
        max_connections: int = 5,
        timeout: float = 30.0,
    ):
        """
        初始化异步数据库连接池
        
        Args:
            database_path: 数据库文件路径
            max_connections: 最大连接数
            timeout: 连接超时时间（秒）
        """
        self.database_path = database_path
        self.max_connections = max_connections
        self.timeout = timeout
        
        # 连接池
        self._pool: List[aiosqlite.Connection] = []
        self._available: asyncio.Queue = asyncio.Queue(maxsize=max_connections)
        self._lock = asyncio.Lock()
        
        # 统计信息
        self._stats = {
            "total_connections": 0,
            "active_connections": 0,
            "total_queries": 0,
            "total_time": 0.0,
        }
        
        logger.info(f"异步数据库连接池初始化: {database_path}, 最大连接数: {max_connections}")
    
    async def _create_connection(self) -> aiosqlite.Connection:
        """创建新的数据库连接"""
        try:
            conn = await aiosqlite.connect(
                str(self.database_path),
                timeout=self.timeout,
            )
            
            # 启用外键约束
            await conn.execute("PRAGMA foreign_keys = ON")
            # 设置WAL模式以提高并发性能
            await conn.execute("PRAGMA journal_mode = WAL")
            # 优化性能
            await conn.execute("PRAGMA synchronous = NORMAL")
            await conn.execute("PRAGMA cache_size = -64000")  # 64MB缓存
            await conn.execute("PRAGMA temp_store = MEMORY")
            
            async with self._lock:
                self._pool.append(conn)
                self._stats["total_connections"] += 1
            
            logger.debug(f"创建新的异步数据库连接 (总数: {self._stats['total_connections']})")
            return conn
            
        except Exception as e:
            logger.error(f"创建异步数据库连接失败: {e}")
            raise
    
    @asynccontextmanager
    async def get_connection(self):
        """获取数据库连接（上下文管理器）"""
        conn = None
        try:
            # 尝试从队列获取可用连接
            try:
                conn = await asyncio.wait_for(
                    self._available.get(),
                    timeout=1.0
                )
            except asyncio.TimeoutError:
                # 队列为空，创建新连接
                if len(self._pool) < self.max_connections:
                    conn = await self._create_connection()
                else:
                    # 等待可用连接
                    conn = await self._available.get()
            
            async with self._lock:
                self._stats["active_connections"] += 1
            
            yield conn
            
        finally:
            if conn:
                # 归还连接到池
                await self._available.put(conn)
                async with self._lock:
                    self._stats["active_connections"] -= 1
    
    async def execute(
        self,
        query: str,
        parameters: Optional[Tuple] = None,
        fetch_one: bool = False,
        fetch_all: bool = False,
        commit: bool = False,
    ) -> Any:
        """
        执行SQL查询（异步）
        
        Args:
            query: SQL查询语句
            parameters: 查询参数
            fetch_one: 是否返回单行结果
            fetch_all: 是否返回所有结果
            commit: 是否提交事务
        
        Returns:
            查询结果或None
        """
        start_time = time.perf_counter()
        
        async with self.get_connection() as conn:
            try:
                if parameters:
                    cursor = await conn.execute(query, parameters)
                else:
                    cursor = await conn.execute(query)
                
                if commit:
                    await conn.commit()
                
                result = None
                if fetch_one:
                    result = await cursor.fetchone()
                elif fetch_all:
                    result = await cursor.fetchall()
                else:
                    result = cursor.lastrowid
                
                await cursor.close()
                
                # 更新统计
                elapsed = time.perf_counter() - start_time
                async with self._lock:
                    self._stats["total_queries"] += 1
                    self._stats["total_time"] += elapsed
                
                return result
                
            except Exception as e:
                await conn.rollback()
                logger.error(f"异步SQL执行失败: {e}")
                raise

    async def execute_many(
        self,
        query: str,
        parameters_list: List[Tuple],
        commit: bool = True,
    ) -> int:
        """
        批量执行SQL查询（异步）

        Args:
            query: SQL查询语句
            parameters_list: 参数列表
            commit: 是否提交事务

        Returns:
            影响的行数
        """
        start_time = time.perf_counter()

        async with self.get_connection() as conn:
            try:
                cursor = await conn.executemany(query, parameters_list)

                if commit:
                    await conn.commit()

                row_count = cursor.rowcount
                await cursor.close()

                # 更新统计
                elapsed = time.perf_counter() - start_time
                async with self._lock:
                    self._stats["total_queries"] += len(parameters_list)
                    self._stats["total_time"] += elapsed

                logger.debug(f"批量执行 {len(parameters_list)} 条SQL，耗时: {elapsed*1000:.1f}ms")
                return row_count

            except Exception as e:
                await conn.rollback()
                logger.error(f"异步批量SQL执行失败: {e}")
                raise

    async def close_all(self):
        """关闭所有连接"""
        async with self._lock:
            for conn in self._pool:
                await conn.close()
            self._pool.clear()
            logger.info("所有异步数据库连接已关闭")

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        stats = self._stats.copy()
        if stats["total_queries"] > 0:
            stats["avg_query_time"] = stats["total_time"] / stats["total_queries"]
        else:
            stats["avg_query_time"] = 0.0
        return stats


# 全局异步数据库池实例
_async_db_pools: Dict[str, AsyncDatabasePool] = {}


def get_async_db_pool(database_path: Path, max_connections: int = 5) -> AsyncDatabasePool:
    """
    获取异步数据库连接池（单例模式）

    Args:
        database_path: 数据库文件路径
        max_connections: 最大连接数

    Returns:
        AsyncDatabasePool: 异步数据库连接池
    """
    db_key = str(database_path)

    if db_key not in _async_db_pools:
        _async_db_pools[db_key] = AsyncDatabasePool(
            database_path=database_path,
            max_connections=max_connections,
        )

    return _async_db_pools[db_key]


async def close_all_pools():
    """关闭所有数据库连接池"""
    for pool in _async_db_pools.values():
        await pool.close_all()
    _async_db_pools.clear()
    logger.info("所有异步数据库连接池已关闭")


# 示例用法
if __name__ == "__main__":
    async def test():
        """测试异步数据库操作"""
        # 创建测试数据库
        test_db = Path("test_async.db")

        # 获取连接池
        pool = get_async_db_pool(test_db, max_connections=3)

        # 创建表
        await pool.execute(
            "CREATE TABLE IF NOT EXISTS test (id INTEGER PRIMARY KEY, name TEXT)",
            commit=True
        )

        # 插入数据
        await pool.execute(
            "INSERT INTO test (name) VALUES (?)",
            ("Alice",),
            commit=True
        )

        # 批量插入
        await pool.execute_many(
            "INSERT INTO test (name) VALUES (?)",
            [("Bob",), ("Charlie",), ("David",)],
            commit=True
        )

        # 查询数据
        results = await pool.execute(
            "SELECT * FROM test",
            fetch_all=True
        )
        print(f"查询结果: {results}")

        # 获取统计
        stats = pool.get_stats()
        print(f"统计信息: {stats}")

        # 关闭连接池
        await pool.close_all()

        # 删除测试数据库
        test_db.unlink(missing_ok=True)

    # 运行测试
    asyncio.run(test())


