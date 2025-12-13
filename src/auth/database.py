"""
用户数据库模型

使用 SQLite 存储用户信息和会话数据
"""

import sqlite3
import hashlib
import secrets
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any

from src.utils.logger import get_logger
logger = get_logger(__name__)

try:
    from src.utils.prepared_statements import get_prepared_statement_manager
    HAS_PREPARED_STATEMENTS = True
except ImportError as e:
    HAS_PREPARED_STATEMENTS = False
    logger.warning(f"预编译语句不可用: {e}")


class UserDatabase:
    """用户数据库管理类（优化版）"""

    def __init__(self, db_path: str = "data/users.db", use_prepared: bool = True):
        """初始化数据库

        Args:
            db_path: 数据库文件路径
            use_prepared: 是否使用预编译语句（提升30-50%性能）
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.timeout = 10.0

        # 使用预编译语句管理器
        self.use_prepared = use_prepared and HAS_PREPARED_STATEMENTS
        if self.use_prepared:
            try:
                self._prepared_mgr = get_prepared_statement_manager(self.db_path)
                logger.info(f"用户数据库使用预编译语句模式: {db_path}")
            except Exception as e:
                logger.error(f"预编译语句初始化失败，切换到传统模式: {e}")
                self.use_prepared = False
                self._prepared_mgr = None
        else:
            self._prepared_mgr = None
            logger.info(f"用户数据库使用传统模式: {db_path}")

        self._init_database()

    def _get_connection(self):
        """获取数据库连接"""
        return sqlite3.connect(str(self.db_path), timeout=self.timeout)

    def _init_database(self):
        """初始化数据库表 (v2.25.0: 修复连接管理)"""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()

            # 启用 WAL 模式以提高并发性能
            cursor.execute("PRAGMA journal_mode=WAL")

            # 用户表 - v2.22.0 新增：用户头像和AI助手头像字段
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    email TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    salt TEXT NOT NULL,
                    user_avatar TEXT DEFAULT '👤',
                    ai_avatar TEXT DEFAULT '🐱',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_login TIMESTAMP,
                    is_active INTEGER DEFAULT 1
                )
            """)

            # 会话表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    session_token TEXT UNIQUE NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP NOT NULL,
                    is_active INTEGER DEFAULT 1,
                    FOREIGN KEY (user_id) REFERENCES users (id)
                )
            """)

            # 创建索引
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_username ON users(username)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_email ON users(email)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_session_token ON sessions(session_token)
            """)

            # v2.22.0 数据库迁移：添加头像字段（如果不存在）
            try:
                cursor.execute("SELECT user_avatar FROM users LIMIT 1")
            except sqlite3.OperationalError:
                # 字段不存在，添加字段
                cursor.execute("ALTER TABLE users ADD COLUMN user_avatar TEXT DEFAULT '👤'")
                cursor.execute("ALTER TABLE users ADD COLUMN ai_avatar TEXT DEFAULT '🐱'")
                logger.info("数据库迁移：已添加用户头像和AI助手头像字段")

            conn.commit()
        finally:
            conn.close()

    def _hash_password(self, password: str, salt: str) -> str:
        """哈希密码

        Args:
            password: 明文密码
            salt: 盐值

        Returns:
            哈希后的密码
        """
        return hashlib.pbkdf2_hmac(
            'sha256',
            password.encode('utf-8'),
            salt.encode('utf-8'),
            100000
        ).hex()

    def create_user(self, username: str, email: str, password: str) -> Optional[int]:
        """创建新用户 (v2.24.0: 优化连接管理)

        Args:
            username: 用户名
            email: 邮箱
            password: 密码

        Returns:
            用户 ID，如果创建失败返回 None
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                # 生成盐值
                salt = secrets.token_hex(32)

                # 哈希密码
                password_hash = self._hash_password(password, salt)

                # 插入用户
                cursor.execute("""
                    INSERT INTO users (username, email, password_hash, salt)
                    VALUES (?, ?, ?, ?)
                """, (username, email, password_hash, salt))

                user_id = cursor.lastrowid
                conn.commit()

                return user_id
        except sqlite3.IntegrityError:
            # 用户名或邮箱已存在
            return None

    def verify_user(self, username: str, password: str) -> Optional[Dict[str, Any]]:
        """验证用户登录 (v2.24.0: 优化连接管理)

        Args:
            username: 用户名
            password: 密码

        Returns:
            用户信息字典，如果验证失败返回 None
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                SELECT id, username, email, password_hash, salt, is_active
                FROM users
                WHERE username = ?
            """, (username,))

            row = cursor.fetchone()

            if not row:
                return None

            user_id, username, email, password_hash, salt, is_active = row

            # 检查用户是否激活
            if not is_active:
                return None

            # 验证密码
            if self._hash_password(password, salt) != password_hash:
                return None

            # 更新最后登录时间（在同一个连接中）
            cursor.execute("""
                UPDATE users
                SET last_login = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (user_id,))

            conn.commit()

            return {
                'id': user_id,
                'username': username,
                'email': email
            }

    def _update_last_login(self, user_id: int):
        """更新最后登录时间 (v2.24.0: 优化连接管理)"""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                UPDATE users
                SET last_login = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (user_id,))

            conn.commit()

    def change_password(self, user_id: int, old_password: str, new_password: str) -> bool:
        """修改密码 (v2.24.0: 优化连接管理)

        Args:
            user_id: 用户 ID
            old_password: 旧密码
            new_password: 新密码

        Returns:
            是否修改成功
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # 获取用户信息
            cursor.execute("""
                SELECT password_hash, salt
                FROM users
                WHERE id = ?
            """, (user_id,))

            row = cursor.fetchone()
            if not row:
                return False

            password_hash, salt = row

            # 验证旧密码
            if self._hash_password(old_password, salt) != password_hash:
                return False

            # 生成新盐值
            new_salt = secrets.token_hex(32)

            # 哈希新密码
            new_password_hash = self._hash_password(new_password, new_salt)

            # 更新密码
            cursor.execute("""
                UPDATE users
                SET password_hash = ?, salt = ?
                WHERE id = ?
            """, (new_password_hash, new_salt, user_id))

            conn.commit()

            return True

    def reset_password(self, username: str, new_password: str) -> bool:
        """重置密码（通过用户名，不需要旧密码）

        Args:
            username: 用户名
            new_password: 新密码

        Returns:
            是否重置成功
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()

            # 获取用户信息
            cursor.execute("""
                SELECT id
                FROM users
                WHERE username = ?
            """, (username,))

            row = cursor.fetchone()
            if not row:
                return False

            user_id = row[0]

            # 生成新盐值
            new_salt = secrets.token_hex(32)

            # 哈希新密码
            new_password_hash = self._hash_password(new_password, new_salt)

            # 更新密码
            cursor.execute("""
                UPDATE users
                SET password_hash = ?, salt = ?
                WHERE id = ?
            """, (new_password_hash, new_salt, user_id))

            conn.commit()
            return True
        finally:
            if not self.use_prepared:
                conn.close()

    def create_session(self, user_id: int, expires_in_days: int = 30) -> str:
        """创建会话

        Args:
            user_id: 用户 ID
            expires_in_days: 会话有效期（天）

        Returns:
            会话令牌
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()

            # 生成会话令牌
            session_token = secrets.token_urlsafe(64)

            # 计算过期时间
            expires_at = datetime.now() + timedelta(days=expires_in_days)

            # 插入会话
            cursor.execute("""
                INSERT INTO sessions (user_id, session_token, expires_at)
                VALUES (?, ?, ?)
            """, (user_id, session_token, expires_at))

            conn.commit()
            return session_token
        finally:
            if not self.use_prepared:
                conn.close()

    def verify_session(self, session_token: str) -> Optional[Dict[str, Any]]:
        """验证会话

        Args:
            session_token: 会话令牌

        Returns:
            用户信息字典，如果验证失败返回 None
        """
        # 使用预编译语句（提升30-50%性能）
        if self.use_prepared and self._prepared_mgr:
            try:
                row = self._prepared_mgr.execute(
                    "verify_session",
                    (session_token,),
                    fetch_one=True
                )

                if not row:
                    return None

                user_id, username, email, expires_at = row

                # 检查会话是否过期
                if datetime.fromisoformat(expires_at) < datetime.now():
                    self.invalidate_session(session_token)
                    return None

                return {
                    'id': user_id,
                    'username': username,
                    'email': email
                }
            except Exception as e:
                logger.error(f"预编译语句验证会话失败: {e}")
                # 降级到传统模式

        # 传统模式
        conn = self._get_connection()
        try:
            cursor = conn.cursor()

            cursor.execute("""
                SELECT s.user_id, u.username, u.email, s.expires_at
                FROM sessions s
                JOIN users u ON s.user_id = u.id
                WHERE s.session_token = ? AND s.is_active = 1
            """, (session_token,))

            row = cursor.fetchone()

            if not row:
                return None

            user_id, username, email, expires_at = row

            # 检查会话是否过期
            if datetime.fromisoformat(expires_at) < datetime.now():
                self.invalidate_session(session_token)
                return None

            return {
                'id': user_id,
                'username': username,
                'email': email
            }
        finally:
            conn.close()

    def invalidate_session(self, session_token: str):
        """使会话失效

        Args:
            session_token: 会话令牌
        """
        # 使用预编译语句
        if self.use_prepared and self._prepared_mgr:
            try:
                self._prepared_mgr.execute(
                    "invalidate_session",
                    (session_token,),
                    commit=True
                )
                return
            except Exception as e:
                logger.error(f"预编译语句使会话失效失败: {e}")

        # 传统模式
        conn = self._get_connection()
        try:
            cursor = conn.cursor()

            cursor.execute("""
                UPDATE sessions
                SET is_active = 0
                WHERE session_token = ?
            """, (session_token,))

            conn.commit()
        finally:
            conn.close()

    # ==================== 头像管理 - v2.22.0 新增 ====================

    def update_user_avatar(self, user_id: int, avatar: str) -> bool:
        """更新用户头像

        Args:
            user_id: 用户 ID
            avatar: 头像（emoji 或图片路径）

        Returns:
            是否更新成功
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()

            cursor.execute("""
                UPDATE users
                SET user_avatar = ?
                WHERE id = ?
            """, (avatar, user_id))

            conn.commit()
            affected_rows = cursor.rowcount
            return affected_rows > 0
        except Exception as e:
            logger.error(f"更新用户头像失败: {e}")
            return False
        finally:
            if not self.use_prepared:
                conn.close()

    def update_ai_avatar(self, user_id: int, avatar: str) -> bool:
        """更新AI助手头像

        Args:
            user_id: 用户 ID
            avatar: 头像（emoji 或图片路径）

        Returns:
            是否更新成功
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()

            cursor.execute("""
                UPDATE users
                SET ai_avatar = ?
                WHERE id = ?
            """, (avatar, user_id))

            conn.commit()
            affected_rows = cursor.rowcount
            return affected_rows > 0
        except Exception as e:
            logger.error(f"更新AI助手头像失败: {e}")
            return False
        finally:
            if not self.use_prepared:
                conn.close()

    def get_user_avatars(self, user_id: int) -> Optional[Dict[str, str]]:
        """获取用户和AI助手头像

        Args:
            user_id: 用户 ID

        Returns:
            包含 user_avatar 和 ai_avatar 的字典，失败返回 None
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()

            cursor.execute("""
                SELECT user_avatar, ai_avatar
                FROM users
                WHERE id = ?
            """, (user_id,))

            row = cursor.fetchone()

            if row:
                return {
                    'user_avatar': row[0] or '👤',
                    'ai_avatar': row[1] or '🐱'
                }
            return None
        except Exception as e:
            logger.error(f"获取用户头像失败: {e}")
            return None
        finally:
            if not self.use_prepared:
                conn.close()
