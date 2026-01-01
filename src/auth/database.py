"""
用户数据库模型

使用 SQLite 存储用户信息和会话数据
"""

import sqlite3
import hashlib
import secrets
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from src.utils.logger import get_logger

logger = get_logger(__name__)

_USER_DB_INIT_GUARD_LOCK = threading.Lock()
_USER_DB_INIT_PER_DB_LOCKS: dict[str, threading.Lock] = {}
_USER_DB_INITIALIZED: set[str] = set()


def _ensure_user_db_initialized(db_key: str, init_fn: Callable[[], None]) -> None:
    """Run init once per process for each unique database path.

    Uses a per-db lock so concurrent initializers will wait (instead of skipping).
    """
    with _USER_DB_INIT_GUARD_LOCK:
        lock = _USER_DB_INIT_PER_DB_LOCKS.get(db_key)
        if lock is None:
            lock = threading.Lock()
            _USER_DB_INIT_PER_DB_LOCKS[db_key] = lock

    with lock:
        if db_key in _USER_DB_INITIALIZED:
            return
        init_fn()
        _USER_DB_INITIALIZED.add(db_key)


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
        db_path_obj = Path(db_path)
        # 若用户修改了 settings.data_dir，则默认 users.db 应跟随 data_dir
        if db_path_obj == Path("data/users.db"):
            try:
                from src.config.settings import settings

                db_path_obj = Path(settings.data_dir) / "users.db"
            except Exception:
                pass

        self.db_path = db_path_obj
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.timeout = 10.0

        # 使用预编译语句管理器
        self.use_prepared = use_prepared and HAS_PREPARED_STATEMENTS
        if self.use_prepared:
            try:
                self._prepared_mgr = get_prepared_statement_manager(self.db_path)
                logger.info("用户数据库使用预编译语句模式: %s", self.db_path)
            except Exception as e:
                logger.error(f"预编译语句初始化失败，切换到传统模式: {e}")
                self.use_prepared = False
                self._prepared_mgr = None
        else:
            self._prepared_mgr = None
            logger.info("用户数据库使用传统模式: %s", self.db_path)

        db_key = str(self.db_path.resolve())
        _ensure_user_db_initialized(db_key, self._init_database)

    def _configure_connection(self, conn: sqlite3.Connection) -> None:
        """Apply connection-level SQLite PRAGMAs for performance & integrity."""
        pragmas = [
            ("journal_mode", "WAL"),
            ("synchronous", "NORMAL"),
            ("foreign_keys", "ON"),
            ("busy_timeout", "5000"),
            ("cache_size", "-64000"),
            ("temp_store", "MEMORY"),
            ("mmap_size", "268435456"),
        ]
        for key, value in pragmas:
            try:
                conn.execute(f"PRAGMA {key} = {value}")
            except Exception:
                continue

    def _get_connection(self) -> sqlite3.Connection:
        """获取数据库连接"""
        conn = sqlite3.connect(str(self.db_path), timeout=self.timeout)
        self._configure_connection(conn)
        return conn

    def close(self) -> None:
        """关闭预编译语句连接等资源（幂等）。"""
        if not getattr(self, "use_prepared", False):
            return

        db_path = getattr(self, "db_path", None)
        if db_path is None:
            return

        try:
            from src.utils.prepared_statements import close_prepared_statement_manager

            close_prepared_statement_manager(db_path)
        except Exception:
            pass
        finally:
            try:
                self._prepared_mgr = None
            except Exception:
                pass

    def _init_database(self):
        """初始化数据库表 (v2.25.0: 修复连接管理)"""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()

            # 启用 WAL 模式以提高并发性能
            cursor.execute("PRAGMA journal_mode=WAL")

            # 用户表 - v2.22.0 新增：用户头像和AI助手头像字段
            cursor.execute(
                """
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
            """
            )

            # 会话表
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    session_token TEXT UNIQUE NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP NOT NULL,
                    is_active INTEGER DEFAULT 1,
                    FOREIGN KEY (user_id) REFERENCES users (id)
                )
            """
            )

            # 创建索引
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_username ON users(username)
            """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_email ON users(email)
            """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_session_token ON sessions(session_token)
            """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_sessions_user_active
                ON sessions(user_id, is_active)
            """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_sessions_expires_at
                ON sessions(expires_at)
            """
            )

            # 启动时清理过期会话（避免 sessions 表长期膨胀导致查询变慢）
            now = datetime.now().isoformat(sep=" ", timespec="microseconds")
            cursor.execute(
                """
                UPDATE sessions
                SET is_active = 0
                WHERE is_active = 1 AND expires_at < ?
            """,
                (now,),
            )

            # v2.22.0 数据库迁移：添加头像字段（如果不存在）
            try:
                cursor.execute("SELECT user_avatar FROM users LIMIT 1")
            except sqlite3.OperationalError:
                # 字段不存在，添加字段
                cursor.execute("ALTER TABLE users ADD COLUMN user_avatar TEXT DEFAULT '👤'")
                cursor.execute("ALTER TABLE users ADD COLUMN ai_avatar TEXT DEFAULT '🐱'")
                logger.info("数据库迁移：已添加用户头像和AI助手头像字段")

            # 邮箱规范化：统一存为小写，确保登录/找回密码大小写不敏感
            try:
                cursor.execute(
                    """
                    UPDATE users
                    SET email = lower(email)
                    WHERE email IS NOT NULL AND email != lower(email)
                """
                )
            except Exception:
                pass

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
            "sha256", password.encode("utf-8"), salt.encode("utf-8"), 100000
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
        username_norm = (username or "").strip()
        email_norm = (email or "").strip().lower()

        # 生成盐值
        salt = secrets.token_hex(32)

        # 哈希密码
        password_hash = self._hash_password(password, salt)

        if self.use_prepared and self._prepared_mgr:
            try:
                user_id = self._prepared_mgr.execute(
                    "insert_user",
                    (username_norm, email_norm, password_hash, salt),
                    commit=True,
                )
                return int(user_id) if user_id else None
            except sqlite3.IntegrityError:
                return None
            except Exception as e:
                logger.error("预编译语句创建用户失败，降级到传统模式: %s", e)

        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                    INSERT INTO users (username, email, password_hash, salt)
                    VALUES (?, ?, ?, ?)
                """,
                (username_norm, email_norm, password_hash, salt),
            )
            user_id = cursor.lastrowid
            conn.commit()
            return user_id
        except sqlite3.IntegrityError:
            return None
        finally:
            conn.close()

    def verify_user(self, username: str, password: str) -> Optional[Dict[str, Any]]:
        """验证用户登录 (v2.24.0: 优化连接管理)

        Args:
            username: 用户名或邮箱
            password: 密码

        Returns:
            用户信息字典，如果验证失败返回 None
        """
        identifier = (username or "").strip()
        if "@" in identifier:
            identifier = identifier.lower()

        # 快路径：复用预编译语句连接，减少频繁 connect/close 开销
        if self.use_prepared and self._prepared_mgr:
            try:
                stmt = "get_user_by_email" if "@" in identifier else "get_user_by_username"
                row = self._prepared_mgr.execute(stmt, (identifier,), fetch_one=True)
                if not row:
                    return None

                # users 表结构：
                # id, username, email, password_hash, salt, user_avatar, ai_avatar
                # created_at, last_login, is_active
                user_id = row[0]
                username_db = row[1]
                email = row[2]
                password_hash = row[3]
                salt = row[4]
                is_active = row[-1]

                if not is_active:
                    return None

                candidate = self._hash_password(password, salt)
                if not secrets.compare_digest(candidate, password_hash):
                    return None

                try:
                    self._prepared_mgr.execute("update_last_login", (user_id,), commit=True)
                except Exception:
                    # last_login 写入失败不应阻断登录
                    pass

                return {"id": user_id, "username": username_db, "email": email}
            except Exception as e:
                logger.error("预编译语句验证用户失败，降级到传统模式: %s", e)

        conn = self._get_connection()
        try:
            cursor = conn.cursor()

            query = (
                """
                SELECT id, username, email, password_hash, salt, is_active
                FROM users
                WHERE email = ?
            """
                if "@" in identifier
                else """
                SELECT id, username, email, password_hash, salt, is_active
                FROM users
                WHERE username = ?
            """
            )
            cursor.execute(query, (identifier,))

            row = cursor.fetchone()

            if not row:
                return None

            user_id, username, email, password_hash, salt, is_active = row

            # 检查用户是否激活
            if not is_active:
                return None

            # 验证密码
            candidate = self._hash_password(password, salt)
            if not secrets.compare_digest(candidate, password_hash):
                return None

            # 更新最后登录时间（在同一个连接中）
            cursor.execute(
                """
                UPDATE users
                SET last_login = CURRENT_TIMESTAMP
                WHERE id = ?
            """,
                (user_id,),
            )

            conn.commit()

            return {"id": user_id, "username": username, "email": email}
        finally:
            conn.close()

    def _update_last_login(self, user_id: int):
        """更新最后登录时间 (v2.24.0: 优化连接管理)"""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()

            cursor.execute(
                """
                UPDATE users
                SET last_login = CURRENT_TIMESTAMP
                WHERE id = ?
            """,
                (user_id,),
            )

            conn.commit()
        finally:
            conn.close()

    def change_password(self, user_id: int, old_password: str, new_password: str) -> bool:
        """修改密码 (v2.24.0: 优化连接管理)

        Args:
            user_id: 用户 ID
            old_password: 旧密码
            new_password: 新密码

        Returns:
            是否修改成功
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()

            # 获取用户信息
            cursor.execute(
                """
                SELECT password_hash, salt
                FROM users
                WHERE id = ?
            """,
                (user_id,),
            )

            row = cursor.fetchone()
            if not row:
                return False

            password_hash, salt = row

            # 验证旧密码
            candidate_old = self._hash_password(old_password, salt)
            if not secrets.compare_digest(candidate_old, password_hash):
                return False

            # 生成新盐值
            new_salt = secrets.token_hex(32)

            # 哈希新密码
            new_password_hash = self._hash_password(new_password, new_salt)

            # 更新密码
            cursor.execute(
                """
                UPDATE users
                SET password_hash = ?, salt = ?
                WHERE id = ?
            """,
                (new_password_hash, new_salt, user_id),
            )

            conn.commit()

            return True
        finally:
            conn.close()

    def reset_password(self, username: str, email: str, new_password: str) -> bool:
        """重置密码（通过用户名+邮箱匹配，不需要旧密码）

        Args:
            username: 用户名
            email: 邮箱（必须与用户名匹配）
            new_password: 新密码

        Returns:
            是否重置成功
        """
        username_norm = (username or "").strip()
        email_norm = (email or "").strip().lower()
        conn = self._get_connection()
        try:
            cursor = conn.cursor()

            # 获取用户信息
            cursor.execute(
                """
                SELECT id
                FROM users
                WHERE username = ? AND email = ? AND is_active = 1
            """,
                (username_norm, email_norm),
            )

            row = cursor.fetchone()
            if not row:
                return False

            user_id = row[0]

            # 生成新盐值
            new_salt = secrets.token_hex(32)

            # 哈希新密码
            new_password_hash = self._hash_password(new_password, new_salt)

            # 更新密码
            cursor.execute(
                """
                UPDATE users
                SET password_hash = ?, salt = ?
                WHERE id = ?
            """,
                (new_password_hash, new_salt, user_id),
            )

            # 安全策略：重置密码后使该用户所有会话失效
            cursor.execute(
                """
                UPDATE sessions
                SET is_active = 0
                WHERE user_id = ? AND is_active = 1
            """,
                (user_id,),
            )

            conn.commit()
            return True
        finally:
            conn.close()

    def create_session(self, user_id: int, expires_in_days: int = 30) -> str:
        """创建会话

        Args:
            user_id: 用户 ID
            expires_in_days: 会话有效期（天）

        Returns:
            会话令牌
        """
        # 生成会话令牌
        session_token = secrets.token_urlsafe(64)

        # 计算过期时间（存储为 ISO 字符串，避免 sqlite3 默认 datetime adapter 的弃用警告）
        expires_at = (datetime.now() + timedelta(days=expires_in_days)).isoformat(
            sep=" ", timespec="microseconds"
        )

        if self.use_prepared and self._prepared_mgr:
            try:
                # 同一用户只保留一个活跃会话，避免 sessions 表膨胀与歧义
                self._prepared_mgr.execute(
                    "deactivate_user_sessions",
                    (user_id,),
                    commit=True,
                )
                self._prepared_mgr.execute(
                    "insert_session",
                    (user_id, session_token, expires_at),
                    commit=True,
                )
                return session_token
            except Exception as e:
                logger.error("预编译语句创建会话失败，降级到传统模式: %s", e)

        conn = self._get_connection()
        try:
            cursor = conn.cursor()

            # 同一用户只保留一个活跃会话，避免 sessions 表膨胀与歧义
            cursor.execute(
                """
                UPDATE sessions
                SET is_active = 0
                WHERE user_id = ? AND is_active = 1
            """,
                (user_id,),
            )

            # 插入会话
            cursor.execute(
                """
                INSERT INTO sessions (user_id, session_token, expires_at)
                VALUES (?, ?, ?)
            """,
                (user_id, session_token, expires_at),
            )

            conn.commit()
            return session_token
        finally:
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
                row = self._prepared_mgr.execute("verify_session", (session_token,), fetch_one=True)

                if not row:
                    return None

                user_id, username, email, expires_at = row

                # 检查会话是否过期
                if datetime.fromisoformat(expires_at) < datetime.now():
                    self.invalidate_session(session_token)
                    return None

                return {"id": user_id, "username": username, "email": email}
            except Exception as e:
                logger.error(f"预编译语句验证会话失败: {e}")
                # 降级到传统模式

        # 传统模式
        conn = self._get_connection()
        try:
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT s.user_id, u.username, u.email, s.expires_at
                FROM sessions s
                JOIN users u ON s.user_id = u.id
                WHERE s.session_token = ? AND s.is_active = 1
            """,
                (session_token,),
            )

            row = cursor.fetchone()

            if not row:
                return None

            user_id, username, email, expires_at = row

            # 检查会话是否过期
            if datetime.fromisoformat(expires_at) < datetime.now():
                self.invalidate_session(session_token)
                return None

            return {"id": user_id, "username": username, "email": email}
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
                self._prepared_mgr.execute("invalidate_session", (session_token,), commit=True)
                return
            except Exception as e:
                logger.error(f"预编译语句使会话失效失败: {e}")

        # 传统模式
        conn = self._get_connection()
        try:
            cursor = conn.cursor()

            cursor.execute(
                """
                UPDATE sessions
                SET is_active = 0
                WHERE session_token = ?
            """,
                (session_token,),
            )

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
        avatar_norm = (avatar or "").strip() or "👤"
        # 防御性限制：避免将超长字符串写入 users.db
        if len(avatar_norm) > 512:
            avatar_norm = avatar_norm[:512]

        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            row = None
            try:
                cursor.execute(
                    """
                    UPDATE users
                    SET user_avatar = ?
                    WHERE id = ?
                    RETURNING id
                """,
                    (avatar_norm, user_id),
                )
                row = cursor.fetchone()
            except sqlite3.OperationalError:
                cursor.execute(
                    """
                    UPDATE users
                    SET user_avatar = ?
                    WHERE id = ?
                """,
                    (avatar_norm, user_id),
                )
                cursor.execute(
                    """
                    SELECT id
                    FROM users
                    WHERE id = ?
                """,
                    (user_id,),
                )
                row = cursor.fetchone()

            conn.commit()
            return row is not None
        except Exception as e:
            logger.error("更新用户头像失败: %s", e)
            return False
        finally:
            conn.close()

    def update_ai_avatar(self, user_id: int, avatar: str) -> bool:
        """更新AI助手头像

        Args:
            user_id: 用户 ID
            avatar: 头像（emoji 或图片路径）

        Returns:
            是否更新成功
        """
        avatar_norm = (avatar or "").strip() or "🐱"
        # 防御性限制：避免将超长字符串写入 users.db
        if len(avatar_norm) > 512:
            avatar_norm = avatar_norm[:512]

        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            row = None
            try:
                cursor.execute(
                    """
                    UPDATE users
                    SET ai_avatar = ?
                    WHERE id = ?
                    RETURNING id
                """,
                    (avatar_norm, user_id),
                )
                row = cursor.fetchone()
            except sqlite3.OperationalError:
                cursor.execute(
                    """
                    UPDATE users
                    SET ai_avatar = ?
                    WHERE id = ?
                """,
                    (avatar_norm, user_id),
                )
                cursor.execute(
                    """
                    SELECT id
                    FROM users
                    WHERE id = ?
                """,
                    (user_id,),
                )
                row = cursor.fetchone()

            conn.commit()
            return row is not None
        except Exception as e:
            logger.error("更新AI助手头像失败: %s", e)
            return False
        finally:
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

            cursor.execute(
                """
                SELECT user_avatar, ai_avatar
                FROM users
                WHERE id = ?
            """,
                (user_id,),
            )

            row = cursor.fetchone()

            if row:
                return {"user_avatar": row[0] or "👤", "ai_avatar": row[1] or "🐱"}
            return None
        except Exception as e:
            logger.error(f"获取用户头像失败: {e}")
            return None
        finally:
            conn.close()
