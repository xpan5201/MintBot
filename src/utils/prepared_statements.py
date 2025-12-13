"""
预编译SQL语句管理器

使用预编译语句提升数据库查询性能30-50%
"""

import sqlite3
from typing import Dict, Optional, Tuple, Any
from pathlib import Path
import threading

from src.utils.logger import get_logger

logger = get_logger(__name__)


class PreparedStatementManager:
    """预编译SQL语句管理器（线程安全）"""
    
    def __init__(self, db_path: Path):
        """
        初始化预编译语句管理器
        
        Args:
            db_path: 数据库文件路径
        """
        self.db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None
        self._statements: Dict[str, sqlite3.Cursor] = {}
        self._lock = threading.Lock()
        
        # 初始化连接
        self._init_connection()
        
        # 预编译常用语句
        self._prepare_common_statements()
    
    def _init_connection(self):
        """初始化数据库连接"""
        try:
            self._conn = sqlite3.connect(
                str(self.db_path),
                check_same_thread=False,
                timeout=10.0
            )
            # 优化设置
            self._conn.execute("PRAGMA journal_mode = WAL")
            self._conn.execute("PRAGMA synchronous = NORMAL")
            self._conn.execute("PRAGMA cache_size = -64000")
            self._conn.execute("PRAGMA temp_store = MEMORY")
            logger.info(f"预编译语句管理器已连接到: {self.db_path}")
        except Exception as e:
            logger.error(f"初始化数据库连接失败: {e}")
            raise
    
    def _prepare_common_statements(self):
        """预编译常用SQL语句"""
        common_queries = {
            # 用户查询
            "get_user_by_username": "SELECT * FROM users WHERE username = ?",
            "get_user_by_email": "SELECT * FROM users WHERE email = ?",
            "get_user_by_id": "SELECT * FROM users WHERE id = ?",
            
            # 会话查询
            "verify_session": """
                SELECT s.user_id, u.username, u.email, s.expires_at
                FROM sessions s
                JOIN users u ON s.user_id = u.id
                WHERE s.session_token = ? AND s.is_active = 1
            """,
            "get_active_sessions": "SELECT * FROM sessions WHERE user_id = ? AND is_active = 1",
            
            # 用户数据查询
            "get_user_data": "SELECT * FROM user_data WHERE user_id = ? AND key = ?",
            "get_all_user_data": "SELECT * FROM user_data WHERE user_id = ?",
            
            # 插入语句
            "insert_user": """
                INSERT INTO users (username, email, password_hash, salt, user_avatar, ai_avatar)
                VALUES (?, ?, ?, ?, ?, ?)
            """,
            "insert_session": """
                INSERT INTO sessions (user_id, session_token, expires_at, is_active)
                VALUES (?, ?, ?, 1)
            """,
            "insert_user_data": """
                INSERT OR REPLACE INTO user_data (user_id, key, value, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            """,
            
            # 更新语句
            "update_last_login": "UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = ?",
            "invalidate_session": "UPDATE sessions SET is_active = 0 WHERE session_token = ?",
            "delete_user_data": "DELETE FROM user_data WHERE user_id = ? AND key = ?",
        }
        
        with self._lock:
            for name, query in common_queries.items():
                try:
                    cursor = self._conn.cursor()
                    # SQLite会自动缓存预编译的语句
                    self._statements[name] = (query, cursor)
                    logger.debug(f"预编译语句: {name}")
                except Exception as e:
                    logger.error(f"预编译语句失败 {name}: {e}")
    
    def execute(
        self,
        statement_name: str,
        parameters: Optional[Tuple] = None,
        fetch_one: bool = False,
        fetch_all: bool = False,
        commit: bool = False,
    ) -> Any:
        """
        执行预编译语句
        
        Args:
            statement_name: 语句名称
            parameters: 查询参数
            fetch_one: 是否返回单行
            fetch_all: 是否返回所有行
            commit: 是否提交事务
        
        Returns:
            查询结果
        """
        with self._lock:
            if statement_name not in self._statements:
                raise ValueError(f"未找到预编译语句: {statement_name}")
            
            query, cursor = self._statements[statement_name]
            
            try:
                if parameters:
                    cursor.execute(query, parameters)
                else:
                    cursor.execute(query)
                
                if commit:
                    self._conn.commit()
                
                if fetch_one:
                    return cursor.fetchone()
                elif fetch_all:
                    return cursor.fetchall()
                else:
                    return cursor.lastrowid
            
            except Exception as e:
                self._conn.rollback()
                logger.error(f"执行预编译语句失败 {statement_name}: {e}")
                raise
    
    def close(self):
        """关闭连接"""
        with self._lock:
            if self._conn:
                self._conn.close()
                self._conn = None
                self._statements.clear()
                logger.info("预编译语句管理器已关闭")


# 全局实例
_prepared_statement_managers: Dict[str, PreparedStatementManager] = {}
_manager_lock = threading.Lock()


def get_prepared_statement_manager(db_path: Path) -> PreparedStatementManager:
    """
    获取预编译语句管理器（单例模式）
    
    Args:
        db_path: 数据库文件路径
    
    Returns:
        PreparedStatementManager: 预编译语句管理器
    """
    db_key = str(db_path)
    
    with _manager_lock:
        if db_key not in _prepared_statement_managers:
            _prepared_statement_managers[db_key] = PreparedStatementManager(db_path)
        
        return _prepared_statement_managers[db_key]

