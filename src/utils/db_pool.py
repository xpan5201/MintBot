"""
数据库连接池管理器

提供高效的数据库连接管理，支持连接复用和自动清理。
"""

import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from queue import Queue, Empty
from typing import Optional, Generator
import time

from src.utils.logger import get_logger

logger = get_logger(__name__)


class DatabaseConnectionPool:
    """SQLite数据库连接池"""

    def __init__(
        self,
        database_path: str,
        max_connections: int = 5,
        timeout: float = 30.0,
        check_same_thread: bool = False,
        warmup: bool = True,
    ):
        """
        初始化数据库连接池

        Args:
            database_path: 数据库文件路径
            max_connections: 最大连接数
            timeout: 获取连接的超时时间（秒）
            check_same_thread: 是否检查线程（SQLite特有）
            warmup: 是否预热连接池（默认True）
        """
        self.database_path = Path(database_path)
        self.max_connections = max_connections
        self.timeout = timeout
        self.check_same_thread = check_same_thread

        # 确保数据库目录存在
        self.database_path.parent.mkdir(parents=True, exist_ok=True)

        # 连接池
        self._pool: Queue = Queue(maxsize=max_connections)
        self._all_connections: list = []
        self._lock = threading.Lock()
        self._closed = False

        # 统计信息
        self._stats = {
            "total_connections": 0,
            "active_connections": 0,
            "total_requests": 0,
            "total_timeouts": 0,
            "warmup_connections": 0,
        }

        logger.info(
            f"数据库连接池初始化: {database_path} (最大连接数: {max_connections})"
        )

        # 连接池预热
        if warmup:
            self._warmup_pool()

    def _create_connection(self) -> sqlite3.Connection:
        """创建新的数据库连接"""
        try:
            conn = sqlite3.connect(
                str(self.database_path),
                timeout=self.timeout,
                check_same_thread=self.check_same_thread,
            )
            # 启用外键约束
            conn.execute("PRAGMA foreign_keys = ON")
            # 设置WAL模式以提高并发性能
            conn.execute("PRAGMA journal_mode = WAL")
            # 优化性能
            conn.execute("PRAGMA synchronous = NORMAL")
            conn.execute("PRAGMA cache_size = -64000")  # 64MB缓存
            conn.execute("PRAGMA temp_store = MEMORY")

            with self._lock:
                self._all_connections.append(conn)
                self._stats["total_connections"] += 1

            logger.debug(f"创建新数据库连接 (总数: {self._stats['total_connections']})")
            return conn

        except sqlite3.Error as e:
            error_msg = f"创建数据库连接失败: {e}"
            logger.error(error_msg)
            raise sqlite3.Error(error_msg)

    def _warmup_pool(self):
        """
        预热连接池（创建初始连接）

        预先创建min(2, max_connections)个连接，减少首次请求延迟
        """
        warmup_count = min(2, self.max_connections)

        try:
            for _ in range(warmup_count):
                conn = self._create_connection()
                self._pool.put(conn)
                self._stats["warmup_connections"] += 1

            logger.info(f"连接池预热完成: 创建了 {warmup_count} 个连接")
        except Exception as e:
            logger.warning(f"连接池预热失败: {e}")

    @contextmanager
    def get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """
        获取数据库连接（上下文管理器）

        Yields:
            sqlite3.Connection: 数据库连接

        Raises:
            RuntimeError: 获取连接失败
        """
        if self._closed:
            raise RuntimeError("连接池已关闭")

        conn = None
        start_time = time.time()

        with self._lock:
            self._stats["total_requests"] += 1

        try:
            # 尝试从池中获取连接
            try:
                conn = self._pool.get(block=False)
                logger.debug("从连接池获取连接")
            except Empty:
                # 池中没有可用连接，创建新连接
                with self._lock:
                    if self._stats["total_connections"] < self.max_connections:
                        conn = self._create_connection()
                    else:
                        # 达到最大连接数，等待可用连接
                        logger.debug("等待可用连接...")
                        try:
                            conn = self._pool.get(timeout=self.timeout)
                        except Empty:
                            with self._lock:
                                self._stats["total_timeouts"] += 1
                            error_msg = f"获取数据库连接超时 ({self.timeout}秒)"
                            logger.error(error_msg)
                            raise TimeoutError(error_msg)

            with self._lock:
                self._stats["active_connections"] += 1

            # 返回连接
            yield conn

        except Exception as e:
            logger.error(f"数据库操作失败: {e}")
            raise

        finally:
            # 归还连接到池中
            if conn is not None:
                try:
                    # 回滚未提交的事务
                    conn.rollback()
                    # 归还到池中
                    self._pool.put(conn, block=False)
                    logger.debug("连接已归还到池中")
                except Exception as e:
                    logger.error(f"归还连接失败: {e}")
                    # 连接可能已损坏，关闭它
                    try:
                        conn.close()
                    except Exception as close_error:
                        logger.debug(f"关闭损坏连接失败: {close_error}")
                        pass

                with self._lock:
                    self._stats["active_connections"] -= 1

            elapsed = time.time() - start_time
            if elapsed > 1.0:
                logger.warning(f"数据库操作耗时较长: {elapsed:.2f}秒")

    def execute(
        self,
        query: str,
        parameters: Optional[tuple] = None,
        fetch_one: bool = False,
        fetch_all: bool = False,
        commit: bool = False,
    ):
        """
        执行SQL查询

        Args:
            query: SQL查询语句
            parameters: 查询参数
            fetch_one: 是否返回单行结果
            fetch_all: 是否返回所有结果
            commit: 是否提交事务

        Returns:
            查询结果或None
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                if parameters:
                    cursor.execute(query, parameters)
                else:
                    cursor.execute(query)

                if commit:
                    conn.commit()

                if fetch_one:
                    return cursor.fetchone()
                elif fetch_all:
                    return cursor.fetchall()
                else:
                    return cursor.lastrowid

            except sqlite3.Error as e:
                conn.rollback()
                error_msg = f"SQL执行失败: {e}"
                logger.error(error_msg)
                raise sqlite3.Error(error_msg)
            finally:
                cursor.close()

    def executemany(
        self, query: str, parameters_list: list, commit: bool = True
    ) -> None:
        """
        批量执行SQL查询

        Args:
            query: SQL查询语句
            parameters_list: 参数列表
            commit: 是否提交事务
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.executemany(query, parameters_list)
                if commit:
                    conn.commit()
                logger.debug(f"批量执行 {len(parameters_list)} 条SQL")
            except sqlite3.Error as e:
                conn.rollback()
                error_msg = f"批量SQL执行失败: {e}"
                logger.error(error_msg)
                raise sqlite3.Error(error_msg)
            finally:
                cursor.close()

    def get_stats(self) -> dict:
        """获取连接池统计信息"""
        with self._lock:
            return {
                **self._stats,
                "pool_size": self._pool.qsize(),
                "max_connections": self.max_connections,
            }

    def close(self) -> None:
        """关闭连接池，释放所有连接"""
        if self._closed:
            return

        self._closed = True
        logger.info("正在关闭数据库连接池...")

        with self._lock:
            # 关闭所有连接
            for conn in self._all_connections:
                try:
                    conn.close()
                except Exception as e:
                    logger.error(f"关闭连接失败: {e}")

            self._all_connections.clear()
            self._stats["total_connections"] = 0
            self._stats["active_connections"] = 0

        logger.info("数据库连接池已关闭")

    def __enter__(self):
        """支持上下文管理器"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """退出上下文时关闭连接池"""
        self.close()

    def __del__(self):
        """析构时确保关闭连接池"""
        if not self._closed:
            self.close()
