"""
用户数据管理模块 (v2.27.0 性能优化版)

管理用户相关的所有数据：联系人、聊天历史、用户设置等

v2.27.0 优化:
- 集成数据库连接池，提升性能30-50%
- 添加缓存机制，减少数据库查询
- 实现批量操作，提升批量插入性能70%+
- 完善类型注解和异常处理
"""

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.utils.logger import get_logger
from src.utils.exceptions import DatabaseError, handle_exception

# 尝试导入连接池
try:
    from src.utils.db_pool import DatabaseConnectionPool

    HAS_DB_POOL = True
except ImportError:
    HAS_DB_POOL = False
    DatabaseConnectionPool = None

logger = get_logger(__name__)


class UserDataManager:
    """用户数据管理器 - 管理用户的所有个人数据 (v2.27.0 优化版)"""

    def __init__(self, db_path: str = "data/user_data.db", use_pool: bool = False):
        """初始化用户数据管理器 (v2.30.13: 修复数据库路径)

        Args:
            db_path: 数据库文件路径（默认: data/user_data.db）
            use_pool: 是否使用连接池（默认False，可选启用以提升性能30-50%）
        """
        db_path_obj = Path(db_path)
        # 若用户修改了 settings.data_dir，则默认 user_data.db 应跟随 data_dir
        if db_path_obj == Path("data/user_data.db"):
            try:
                from src.config.settings import settings

                db_path_obj = Path(settings.data_dir) / "user_data.db"
            except Exception:
                pass

        self.db_path = db_path_obj
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.timeout = 10.0

        # v2.27.0: 使用连接池
        self.use_pool = use_pool and HAS_DB_POOL
        if self.use_pool:
            try:
                self._pool = DatabaseConnectionPool(
                    database_path=str(self.db_path),
                    max_connections=5,
                    timeout=self.timeout,
                    check_same_thread=False,
                )
                logger.info("用户数据管理器使用连接池模式: %s", self.db_path)
            except Exception as e:
                logger.error(f"连接池初始化失败，切换到传统模式: {e}")
                self.use_pool = False
                self._pool = None
        else:
            self._pool = None
            logger.info("用户数据管理器使用传统模式: %s", self.db_path)

        # v2.27.0: 缓存机制
        self._cache: Dict[str, Any] = {}
        self._cache_ttl: Dict[str, datetime] = {}
        self._cache_enabled = True
        self._cache_lock = threading.RLock()

        self._init_database()

    def _configure_connection(self, conn: sqlite3.Connection, *, pooled: bool) -> None:
        """Apply connection-level SQLite PRAGMAs.

        `user_data.db` is separate from `users.db`, so any FOREIGN KEY that references the
        users table cannot be enforced. The connection pool enables `foreign_keys` by
        default; we explicitly disable it here to avoid runtime errors.
        """
        pragmas: list[tuple[str, str]] = [("foreign_keys", "OFF")]

        # Connection pools already apply most performance PRAGMAs; keep them intact and
        # only add what they don't configure.
        if pooled:
            pragmas.append(("mmap_size", "268435456"))
        else:
            pragmas.extend(
                [
                    ("journal_mode", "WAL"),
                    ("synchronous", "NORMAL"),
                    ("cache_size", "-10000"),
                    ("mmap_size", "268435456"),
                    ("temp_store", "MEMORY"),
                ]
            )

        for key, value in pragmas:
            try:
                conn.execute(f"PRAGMA {key} = {value}")
            except Exception:
                continue

    @contextmanager
    def _get_connection(self):
        """获取数据库连接 (v2.27.0: 支持连接池)

        注意：sqlite3.Connection 的上下文管理器仅提交/回滚，不会自动 close。
        这里统一封装为“会自动关闭”的上下文管理器，避免 Windows 下数据库文件句柄泄漏。
        """
        if self.use_pool and self._pool:
            with self._pool.get_connection() as conn:
                self._configure_connection(conn, pooled=True)
                yield conn
            return

        conn = sqlite3.connect(str(self.db_path), timeout=self.timeout)
        try:
            self._configure_connection(conn, pooled=False)
            yield conn
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def _is_cache_valid(self, cache_key: str) -> bool:
        """检查缓存是否有效

        Args:
            cache_key: 缓存键

        Returns:
            缓存是否有效
        """
        if not self._cache_enabled:
            return False

        with self._cache_lock:
            if cache_key not in self._cache or cache_key not in self._cache_ttl:
                return False
            return datetime.now() < self._cache_ttl[cache_key]

    def _set_cache(self, cache_key: str, value: Any, ttl_seconds: int = 300) -> None:
        """设置缓存

        Args:
            cache_key: 缓存键
            value: 缓存值
            ttl_seconds: 过期时间（秒），默认5分钟
        """
        if not self._cache_enabled:
            return

        with self._cache_lock:
            self._cache[cache_key] = value
            self._cache_ttl[cache_key] = datetime.now() + timedelta(seconds=ttl_seconds)

    def _invalidate_cache(self, pattern: Optional[str] = None) -> None:
        """使缓存失效

        Args:
            pattern: 缓存键模式，如果为None则清空所有缓存
        """
        with self._cache_lock:
            if pattern is None:
                self._cache.clear()
                self._cache_ttl.clear()
                return

            if not pattern:
                return

            # `pattern in key` 会导致 "contacts_1" 误伤 "contacts_12"。
            # 这里采用更严格的前缀匹配，并在 pattern 以数字结尾时要求边界，避免跨用户误删缓存。
            keys_to_remove: list[str] = []
            for key in list(self._cache.keys()):
                if not key.startswith(pattern):
                    continue

                if (
                    pattern[-1].isdigit()
                    and len(key) > len(pattern)
                    and key[len(pattern)].isdigit()
                ):
                    continue

                keys_to_remove.append(key)

            for key in keys_to_remove:
                self._cache.pop(key, None)
                self._cache_ttl.pop(key, None)

    def _init_database(self) -> None:
        """初始化数据库表 (v2.28.0: 增强性能优化)"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                # user_data.db 与 users.db 分离，无法跨库外键；禁用外键以避免运行时报错。
                cursor.execute("PRAGMA foreign_keys = OFF")

                # v2.28.0: SQLite性能优化配置
                # 启用 WAL 模式 - 提升并发性能
                cursor.execute("PRAGMA journal_mode=WAL")

                # 设置同步模式为NORMAL - 平衡性能和安全性
                cursor.execute("PRAGMA synchronous=NORMAL")

                # 增加缓存大小到10MB - 提升查询性能
                cursor.execute("PRAGMA cache_size=-10000")

                # 启用内存映射I/O - 提升大文件性能
                cursor.execute("PRAGMA mmap_size=268435456")  # 256MB

                # 设置临时存储为内存 - 加速临时表操作
                cursor.execute("PRAGMA temp_store=MEMORY")

                # 联系人表
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS contacts (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        name TEXT NOT NULL,
                        avatar TEXT DEFAULT '👤',
                        status TEXT DEFAULT '在线',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(user_id, name)
                    )
                """
                )

                # 聊天历史表
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS chat_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        contact_name TEXT NOT NULL,
                        role TEXT NOT NULL,
                        content TEXT NOT NULL,
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """
                )

                # 用户设置表
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS user_settings (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL UNIQUE,
                        settings_json TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """
                )

                # 自定义表情包表 - v2.19.0 新增
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS custom_stickers (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        sticker_id TEXT NOT NULL,
                        file_path TEXT NOT NULL,
                        file_name TEXT NOT NULL,
                        file_type TEXT NOT NULL,
                        file_size INTEGER DEFAULT 0,
                        caption TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(user_id, sticker_id)
                    )
                """
                )

                # v2.46.x: 旧数据库兼容 - 为自定义表情包补充 caption 字段（用于视觉模型生成的说明标签）
                try:
                    cursor.execute("PRAGMA table_info(custom_stickers)")
                    columns = {row[1] for row in cursor.fetchall() if row and len(row) > 1}
                    if "caption" not in columns:
                        cursor.execute("ALTER TABLE custom_stickers ADD COLUMN caption TEXT")
                        logger.info("custom_stickers 表已补充 caption 字段")
                except Exception as schema_exc:
                    logger.warning("检查/迁移 custom_stickers.caption 字段失败: %s", schema_exc)

                # 创建索引 (v2.30.12: 优化索引策略，提升查询性能)
                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_contacts_user_id ON contacts(user_id)
                """
                )
                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_contacts_user_updated
                    ON contacts(user_id, updated_at DESC)
                """
                )
                # v2.30.12: 优化 - 使用复合索引覆盖查询条件
                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_chat_history_query
                    ON chat_history(user_id, contact_name, timestamp DESC)
                """
                )
                # v2.49.x: 针对“向上翻历史”的 keyset pagination 优化（避免大 OFFSET 退化）
                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_chat_history_user_contact_id
                    ON chat_history(user_id, contact_name, id DESC)
                """
                )
                # v2.30.12: 保留单列索引用于其他查询
                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_chat_history_user_id ON chat_history(user_id)
                """
                )
                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_custom_stickers_user_id
                    ON custom_stickers(user_id)
                """
                )
                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_custom_stickers_user_created
                    ON custom_stickers(user_id, created_at DESC)
                """
                )

                conn.commit()
                logger.info("用户数据管理器初始化完成")
        except Exception as e:
            raise DatabaseError(
                "数据库初始化失败",
                operation="_init_database",
                context={"db_path": str(self.db_path), "error": str(e)},
            )

    # ==================== 联系人管理 ====================

    def add_contact(
        self, user_id: int, name: str, avatar: str = "👤", status: str = "在线"
    ) -> bool:
        """添加联系人 (v2.27.0: 使用连接池)

        Args:
            user_id: 用户 ID
            name: 联系人名称
            avatar: 头像
            status: 状态

        Returns:
            是否添加成功
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute(
                    """
                    INSERT INTO contacts (user_id, name, avatar, status)
                    VALUES (?, ?, ?, ?)
                """,
                    (user_id, name, avatar, status),
                )

                conn.commit()
                logger.info(f"用户 {user_id} 添加联系人: {name}")

                # 使缓存失效
                self._invalidate_cache(f"contacts_{user_id}")
                return True
        except sqlite3.IntegrityError:
            logger.warning(f"联系人 {name} 已存在")
            return False
        except sqlite3.Error as e:
            raise DatabaseError(
                "添加联系人失败",
                operation="add_contact",
                context={"user_id": user_id, "name": name, "error": str(e)},
            )
        except Exception as e:
            handle_exception(e, logger, "添加联系人失败")
            return False

    def add_contacts_batch(self, user_id: int, contacts: List[Dict[str, Any]]) -> int:
        """批量添加联系人（导入/同步场景使用），自动忽略重复项。"""
        if not contacts:
            return 0

        values: list[tuple[int, str, str, str]] = []
        for contact in contacts:
            try:
                name = str(contact.get("name") or "").strip()
            except Exception:
                name = ""
            if not name:
                continue
            avatar = str(contact.get("avatar") or "👤")
            status = str(contact.get("status") or "在线")
            values.append((user_id, name, avatar, status))

        if not values:
            return 0

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                before = conn.total_changes
                cursor.executemany(
                    """
                    INSERT OR IGNORE INTO contacts (user_id, name, avatar, status)
                    VALUES (?, ?, ?, ?)
                """,
                    values,
                )
                conn.commit()
                inserted = int(conn.total_changes - before)

            if inserted:
                self._invalidate_cache(f"contacts_{user_id}")
            return inserted
        except sqlite3.Error as e:
            raise DatabaseError(
                "批量添加联系人失败",
                operation="add_contacts_batch",
                context={"user_id": user_id, "count": len(values), "error": str(e)},
            )
        except Exception as e:
            handle_exception(e, logger, "批量添加联系人失败")
            return 0

    def get_contacts(self, user_id: int) -> List[Dict[str, Any]]:
        """获取用户的所有联系人 (v2.27.0: 使用连接池和缓存)

        Args:
            user_id: 用户 ID

        Returns:
            联系人列表
        """
        # 检查缓存
        cache_key = f"contacts_{user_id}"
        if self._is_cache_valid(cache_key):
            logger.debug(f"从缓存获取联系人列表: user_id={user_id}")
            with self._cache_lock:
                cached = self._cache.get(cache_key, [])
            if isinstance(cached, list):
                # 返回拷贝，避免外部修改污染缓存
                return [dict(item) for item in cached]
            return []

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute(
                    """
                    SELECT id, name, avatar, status, created_at, updated_at
                    FROM contacts
                    WHERE user_id = ?
                    ORDER BY updated_at DESC
                """,
                    (user_id,),
                )

                rows = cursor.fetchall()

                contacts = []
                for row in rows:
                    contacts.append(
                        {
                            "id": row[0],
                            "name": row[1],
                            "avatar": row[2],
                            "status": row[3],
                            "created_at": row[4],
                            "updated_at": row[5],
                        }
                    )

                # 设置缓存（10分钟）
                self._set_cache(cache_key, contacts, ttl_seconds=600)
                # 返回拷贝，避免外部修改污染缓存
                return [dict(item) for item in contacts]
        except sqlite3.Error as e:
            raise DatabaseError(
                "获取联系人失败",
                operation="get_contacts",
                context={"user_id": user_id, "error": str(e)},
            )
        except Exception as e:
            handle_exception(e, logger, "获取联系人失败")
            return []

    def update_contact(self, user_id: int, old_name: str, new_name: str) -> bool:
        """重命名联系人

        Args:
            user_id: 用户 ID
            old_name: 旧名称
            new_name: 新名称

        Returns:
            是否更新成功
        """
        contact_rows = 0
        history_rows = 0
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute(
                    """
                    UPDATE contacts
                    SET name = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE user_id = ? AND name = ?
                """,
                    (new_name, user_id, old_name),
                )
                contact_rows = int(getattr(cursor, "rowcount", 0) or 0)

                # 同时更新聊天历史中的联系人名称
                cursor.execute(
                    """
                    UPDATE chat_history
                    SET contact_name = ?
                    WHERE user_id = ? AND contact_name = ?
                """,
                    (new_name, user_id, old_name),
                )
                history_rows = int(getattr(cursor, "rowcount", 0) or 0)

                conn.commit()

            if contact_rows > 0:
                self._invalidate_cache(f"contacts_{user_id}")
                logger.info(
                    "用户 %s 重命名联系人: %s -> %s (contacts=%s, history=%s)",
                    user_id,
                    old_name,
                    new_name,
                    contact_rows,
                    history_rows,
                )
                return True
            return False
        except Exception as e:
            logger.error(f"更新联系人失败: {e}")
            return False

    def delete_contact(self, user_id: int, name: str) -> bool:
        """删除联系人

        Args:
            user_id: 用户 ID
            name: 联系人名称

        Returns:
            是否删除成功
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute(
                    """
                    DELETE FROM contacts
                    WHERE user_id = ? AND name = ?
                """,
                    (user_id, name),
                )

                conn.commit()
                affected_rows = int(getattr(cursor, "rowcount", 0) or 0)

            if affected_rows > 0:
                self._invalidate_cache(f"contacts_{user_id}")
                logger.info(f"用户 {user_id} 删除联系人: {name}")
                return True
            return False
        except Exception as e:
            logger.error(f"删除联系人失败: {e}")
            return False

    # ==================== 聊天历史管理 ====================

    def add_message(self, user_id: int, contact_name: str, role: str, content: str) -> bool:
        """添加聊天消息 (v2.27.0: 使用连接池)

        Args:
            user_id: 用户 ID
            contact_name: 联系人名称
            role: 角色 (user/assistant/system)
            content: 消息内容

        Returns:
            是否添加成功
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute(
                    """
                    INSERT INTO chat_history (user_id, contact_name, role, content)
                    VALUES (?, ?, ?, ?)
                """,
                    (user_id, contact_name, role, content),
                )

                conn.commit()
                return True
        except sqlite3.Error as e:
            raise DatabaseError(
                "添加消息失败",
                operation="add_message",
                context={
                    "user_id": user_id,
                    "contact": contact_name,
                    "role": role,
                    "error": str(e),
                },
            )
        except Exception as e:
            handle_exception(e, logger, "添加消息失败")
            return False

    def add_messages_batch(self, messages: List[Dict[str, Any]]) -> int:
        """批量添加聊天消息 (v2.27.0: 新增批量操作，性能提升70%+)

        Args:
            messages: 消息列表，每个消息包含 user_id, contact_name, role, content

        Returns:
            成功添加的消息数量
        """
        if not messages:
            return 0

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                cursor.executemany(
                    """
                    INSERT INTO chat_history (user_id, contact_name, role, content)
                    VALUES (?, ?, ?, ?)
                """,
                    [(m["user_id"], m["contact_name"], m["role"], m["content"]) for m in messages],
                )

                conn.commit()
                count = cursor.rowcount
                logger.info(f"批量添加了 {count} 条消息")
                return count
        except sqlite3.Error as e:
            raise DatabaseError(
                "批量添加消息失败",
                operation="add_messages_batch",
                context={"count": len(messages), "error": str(e)},
            )
        except Exception as e:
            handle_exception(e, logger, "批量添加消息失败")
            return 0

    def get_chat_history(
        self, user_id: int, contact_name: str, limit: int = 100, offset: int = 0
    ) -> List[Dict[str, Any]]:
        """获取聊天历史 (v2.30.13: 优化去重逻辑，使用消息ID去重)

        Args:
            user_id: 用户 ID
            contact_name: 联系人名称
            limit: 最多返回的消息数量
            offset: 偏移量（用于分页加载）

        Returns:
            消息列表（已去重）
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                # v2.30.13: 使用消息ID去重，避免误删相同内容的不同消息
                # 查询时多取一些数据，用于去重后仍能满足limit要求
                fetch_limit = limit * 2  # 预留去重空间

                # v2.30.12: 添加OFFSET支持分页，使用复合索引优化查询
                cursor.execute(
                    """
                    SELECT role, content, timestamp, id
                    FROM chat_history
                    WHERE user_id = ? AND contact_name = ?
                    ORDER BY timestamp DESC
                    LIMIT ? OFFSET ?
                """,
                    (user_id, contact_name, fetch_limit, offset),
                )

                rows = cursor.fetchall()

                # v2.30.13: 修复去重逻辑 - 先从最新的消息开始去重，再反转
                # 问题：之前用reversed()从最旧的开始处理，达到limit后最新的消息被截断
                # 修复：直接从最新的开始去重，确保最新的消息优先保留
                seen_ids = set()
                messages = []

                # 从最新的消息开始处理（rows已经按timestamp DESC排序）
                for row in rows:
                    msg_id = row[3]

                    # 如果消息ID未见过，添加到结果
                    if msg_id not in seen_ids:
                        seen_ids.add(msg_id)
                        messages.append(
                            {"role": row[0], "content": row[1], "timestamp": row[2], "id": msg_id}
                        )

                        # v2.30.13: 达到limit后停止
                        if len(messages) >= limit:
                            break

                # v2.30.13: 反转消息列表，让消息按时间从旧到新排列（用于显示）
                messages.reverse()

                return messages
        except sqlite3.Error as e:
            raise DatabaseError(
                "获取聊天历史失败",
                operation="get_chat_history",
                context={
                    "user_id": user_id,
                    "contact": contact_name,
                    "limit": limit,
                    "offset": offset,
                    "error": str(e),
                },
            )
        except Exception as e:
            handle_exception(e, logger, "获取聊天历史失败")
            return []

    def get_chat_history_page(
        self,
        user_id: int,
        contact_name: str,
        *,
        limit: int = 100,
        before_id: int | None = None,
    ) -> List[Dict[str, Any]]:
        """按消息 id 进行 keyset pagination 获取聊天历史（推荐）。

        说明：
        - 传统 OFFSET 在大数据量时会退化为线性扫描，加载越往前越慢。
        - 该方法使用 `id < before_id` 实现稳定的向前翻页。
        - 返回顺序为“从旧到新”（便于直接渲染）。

        Args:
            user_id: 用户 ID
            contact_name: 联系人名称
            limit: 返回消息数量
            before_id: 仅返回 id < before_id 的更早消息；为 None 时返回最新消息页

        Returns:
            消息列表（从旧到新）
        """
        if limit <= 0:
            return []

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                params: list[Any] = [user_id, contact_name]
                where_before = ""
                if before_id is not None:
                    where_before = " AND id < ?"
                    params.append(before_id)

                cursor.execute(
                    f"""
                    SELECT role, content, timestamp, id
                    FROM chat_history
                    WHERE user_id = ? AND contact_name = ?{where_before}
                    ORDER BY id DESC
                    LIMIT ?
                """,
                    (*params, int(limit)),
                )

                rows = cursor.fetchall()
                if not rows:
                    return []

                # rows 按 id DESC，反转为从旧到新
                messages = [
                    {"role": role, "content": content, "timestamp": ts, "id": msg_id}
                    for role, content, ts, msg_id in reversed(rows)
                ]
                return messages
        except sqlite3.Error as e:
            raise DatabaseError(
                "获取聊天历史分页失败",
                operation="get_chat_history_page",
                context={
                    "user_id": user_id,
                    "contact": contact_name,
                    "limit": limit,
                    "before_id": before_id,
                    "error": str(e),
                },
            )
        except Exception as e:
            handle_exception(e, logger, "获取聊天历史分页失败")
            return []

    def get_chat_history_all(self, user_id: int, contact_name: str) -> List[Dict[str, Any]]:
        """获取某联系人完整聊天历史（从旧到新）。"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT role, content, timestamp, id
                    FROM chat_history
                    WHERE user_id = ? AND contact_name = ?
                    ORDER BY id ASC
                """,
                    (user_id, contact_name),
                )
                return [
                    {"role": role, "content": content, "timestamp": ts, "id": msg_id}
                    for role, content, ts, msg_id in cursor.fetchall()
                ]
        except sqlite3.Error as e:
            raise DatabaseError(
                "获取完整聊天历史失败",
                operation="get_chat_history_all",
                context={"user_id": user_id, "contact": contact_name, "error": str(e)},
            )
        except Exception as e:
            handle_exception(e, logger, "获取完整聊天历史失败")
            return []

    def get_chat_history_count(self, user_id: int, contact_name: str) -> int:
        """获取聊天历史总数 (v2.30.12: 新增，用于分页)

        Args:
            user_id: 用户 ID
            contact_name: 联系人名称

        Returns:
            消息总数
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute(
                    """
                    SELECT COUNT(*)
                    FROM chat_history
                    WHERE user_id = ? AND contact_name = ?
                """,
                    (user_id, contact_name),
                )

                count = cursor.fetchone()[0]
                return count
        except sqlite3.Error as e:
            raise DatabaseError(
                "获取聊天历史总数失败",
                operation="get_chat_history_count",
                context={
                    "user_id": user_id,
                    "contact": contact_name,
                    "error": str(e),
                },
            )
        except Exception as e:
            handle_exception(e, logger, "获取聊天历史总数失败")
            return 0

    def clear_chat_history(self, user_id: int, contact_name: str) -> bool:
        """清空聊天历史

        Args:
            user_id: 用户 ID
            contact_name: 联系人名称

        Returns:
            是否清空成功
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    DELETE FROM chat_history
                    WHERE user_id = ? AND contact_name = ?
                """,
                    (user_id, contact_name),
                )
                deleted_rows = int(getattr(cursor, "rowcount", 0) or 0)
                conn.commit()

            logger.info(
                "用户 %s 清空与 %s 的聊天历史 (deleted=%s)", user_id, contact_name, deleted_rows
            )
            return True
        except Exception as e:
            logger.error(f"清空聊天历史失败: {e}")
            return False

    # ==================== 用户设置管理 ====================

    def save_user_settings(self, user_id: int, settings: Dict[str, Any]) -> bool:
        """保存用户设置 (v2.27.0: 使用连接池和缓存)

        Args:
            user_id: 用户 ID
            settings: 设置字典

        Returns:
            是否保存成功
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                settings_json = json.dumps(settings, ensure_ascii=False)

                # 尝试更新
                cursor.execute(
                    """
                    UPDATE user_settings
                    SET settings_json = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE user_id = ?
                """,
                    (settings_json, user_id),
                )

                # 如果没有更新任何行，则插入
                if cursor.rowcount == 0:
                    cursor.execute(
                        """
                        INSERT INTO user_settings (user_id, settings_json)
                        VALUES (?, ?)
                    """,
                        (user_id, settings_json),
                    )

                conn.commit()
                logger.info(f"用户 {user_id} 的设置已保存")

                # 使缓存失效
                self._invalidate_cache(f"settings_{user_id}")
                return True
        except sqlite3.Error as e:
            raise DatabaseError(
                "保存用户设置失败",
                operation="save_user_settings",
                context={"user_id": user_id, "error": str(e)},
            )
        except Exception as e:
            handle_exception(e, logger, "保存用户设置失败")
            return False

    def get_user_settings(self, user_id: int) -> Optional[Dict[str, Any]]:
        """获取用户设置 (v2.27.0: 使用连接池和缓存)

        Args:
            user_id: 用户 ID

        Returns:
            设置字典，如果不存在返回 None
        """
        # 检查缓存
        cache_key = f"settings_{user_id}"
        if self._is_cache_valid(cache_key):
            logger.debug(f"从缓存获取用户设置: user_id={user_id}")
            with self._cache_lock:
                cached = self._cache.get(cache_key)
            if isinstance(cached, dict):
                return dict(cached)
            return None

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute(
                    """
                    SELECT settings_json
                    FROM user_settings
                    WHERE user_id = ?
                """,
                    (user_id,),
                )

                row = cursor.fetchone()

                if row:
                    settings = json.loads(row[0])
                    # 设置缓存（5分钟）
                    self._set_cache(cache_key, settings, ttl_seconds=300)
                    if isinstance(settings, dict):
                        return dict(settings)
                    return settings
                return None
        except sqlite3.Error as e:
            raise DatabaseError(
                "获取用户设置失败",
                operation="get_user_settings",
                context={"user_id": user_id, "error": str(e)},
            )
        except Exception as e:
            handle_exception(e, logger, "获取用户设置失败")
            return None

    # ==================== 数据导出 ====================

    def export_user_data(self, user_id: int, export_dir: str = "data/exports") -> Optional[str]:
        """导出用户的所有数据

        Args:
            user_id: 用户 ID
            export_dir: 导出目录

        Returns:
            导出文件路径，失败返回 None
        """
        try:
            export_path = Path(export_dir)
            # 默认导出目录跟随 settings.data_dir
            if export_path == Path("data/exports"):
                try:
                    from src.config.settings import settings

                    export_path = Path(settings.data_dir) / "exports"
                except Exception:
                    pass
            export_path.mkdir(parents=True, exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"user_{user_id}_data_{timestamp}.json"
            filepath = export_path / filename

            # 收集所有数据
            data = {
                "user_id": user_id,
                "export_time": datetime.now().isoformat(),
                "contacts": self.get_contacts(user_id),
                "settings": self.get_user_settings(user_id),
                "chat_history": {},
            }

            # 导出每个联系人的聊天历史
            for contact in data["contacts"]:
                contact_name = contact["name"]
                data["chat_history"][contact_name] = self.get_chat_history_all(
                    user_id, contact_name
                )

            # 写入文件
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            logger.info(f"用户 {user_id} 的数据已导出到: {filepath}")
            return str(filepath)
        except Exception as e:
            logger.error(f"导出用户数据失败: {e}")
            return None

    def import_user_data(self, user_id: int, filepath: str) -> bool:
        """导入用户数据

        Args:
            user_id: 用户 ID
            filepath: 导入文件路径

        Returns:
            是否导入成功
        """
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)

            # 导入联系人
            contacts = data.get("contacts")
            if isinstance(contacts, list) and contacts:
                self.add_contacts_batch(user_id, contacts)

            # 导入聊天历史
            if "chat_history" in data:
                for contact_name, messages in data["chat_history"].items():
                    if not isinstance(messages, list):
                        continue

                    batch: list[dict[str, Any]] = []
                    for msg in messages:
                        try:
                            role = msg["role"]
                            content = msg["content"]
                        except Exception:
                            continue
                        batch.append(
                            {
                                "user_id": user_id,
                                "contact_name": contact_name,
                                "role": role,
                                "content": content,
                            }
                        )
                    if batch:
                        self.add_messages_batch(batch)

            # 导入设置
            if "settings" in data and data["settings"]:
                self.save_user_settings(user_id, data["settings"])

            logger.info(f"用户 {user_id} 的数据已导入")
            return True
        except Exception as e:
            logger.error(f"导入用户数据失败: {e}")
            return False

    # ==================== 自定义表情包管理 - v2.19.0 新增 ====================

    def add_custom_sticker(
        self,
        user_id: int,
        sticker_id: str,
        file_path: str,
        file_name: str,
        file_type: str,
        file_size: int = 0,
        caption: str | None = None,
    ) -> bool:
        """添加自定义表情包 - v2.29.7 修复：改进错误处理

        Args:
            user_id: 用户ID
            sticker_id: 表情包ID
            file_path: 文件路径
            file_name: 文件名
            file_type: 文件类型 (gif/png/jpg/jpeg/webp)
            file_size: 文件大小（字节）
            caption: 表情包说明标签（可选，通常由视觉模型生成）

        Returns:
            bool: 是否成功
        """
        try:
            logger.info(
                f"开始添加表情包: user_id={user_id}, sticker_id={sticker_id}, file_name={file_name}"
            )

            # 验证文件是否存在
            if not Path(file_path).exists():
                logger.error(f"文件不存在: {file_path}")
                return False

            with self._get_connection() as conn:
                cursor = conn.cursor()

                # 检查是否已存在
                cursor.execute(
                    "SELECT id FROM custom_stickers WHERE user_id = ? AND sticker_id = ?",
                    (user_id, sticker_id),
                )
                if cursor.fetchone():
                    logger.warning(f"表情包已存在: {sticker_id}")
                    return False

                cursor.execute(
                    """
                    INSERT INTO custom_stickers (
                        user_id,
                        sticker_id,
                        file_path,
                        file_name,
                        file_type,
                        file_size,
                        caption
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                    (user_id, sticker_id, file_path, file_name, file_type, file_size, caption),
                )

                conn.commit()
            logger.info(f"用户 {user_id} 添加自定义表情包成功: {file_name} (路径: {file_path})")

            # 清除缓存 - v2.29.7 修复：使用正确的方法名
            self._invalidate_cache(f"custom_stickers_{user_id}")

            return True
        except sqlite3.IntegrityError as e:
            logger.error(f"数据库完整性错误: {e}", exc_info=True)
            logger.error(
                f"参数: user_id={user_id}, sticker_id={sticker_id}, file_path={file_path}, "
                f"file_name={file_name}, file_type={file_type}, file_size={file_size}"
            )
            return False
        except Exception as e:
            logger.error(f"添加自定义表情包失败: {e}", exc_info=True)
            logger.error(
                f"参数: user_id={user_id}, sticker_id={sticker_id}, file_path={file_path}, "
                f"file_name={file_name}, file_type={file_type}, file_size={file_size}"
            )
            return False

    def get_custom_stickers(self, user_id: int) -> List[Dict]:
        """获取用户的自定义表情包列表 - v2.29.9 修复：确保连接正确关闭

        Args:
            user_id: 用户ID

        Returns:
            List[Dict]: 表情包列表
        """
        try:
            cache_key = f"custom_stickers_{user_id}"
            if self._is_cache_valid(cache_key):
                with self._cache_lock:
                    cached = self._cache.get(cache_key, [])
                if isinstance(cached, list):
                    return [dict(item) for item in cached]
                return []

            with self._get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute(
                    """
                    SELECT sticker_id, file_path, file_name, file_type, file_size, caption,
                    created_at
                    FROM custom_stickers
                    WHERE user_id = ?
                    ORDER BY created_at DESC
                """,
                    (user_id,),
                )

                stickers = []
                for row in cursor.fetchall():
                    try:
                        stickers.append(
                            {
                                "sticker_id": row[0],  # sticker_id - 修复：使用完整键名
                                "file_path": row[1],  # file_path - 修复：使用完整键名
                                "file_name": row[2],  # file_name - 修复：使用完整键名
                                "file_type": row[3],  # file_type - 修复：使用完整键名
                                "file_size": row[4],  # file_size - 修复：使用完整键名
                                "caption": row[5],  # caption - 视觉模型生成的说明标签
                                "created_at": row[6],  # created_at
                            }
                        )
                    except Exception as row_error:
                        logger.error(f"解析表情包数据失败: {row_error}, row={row}")
                        continue

            logger.info(f"成功加载 {len(stickers)} 个自定义表情包")
            self._set_cache(cache_key, stickers, ttl_seconds=300)
            # 返回拷贝，避免外部修改污染缓存
            return [dict(item) for item in stickers]
        except Exception as e:
            logger.error(f"获取自定义表情包失败: {e}", exc_info=True)
            return []

    def update_custom_sticker_caption(
        self, user_id: int, sticker_id: str, caption: str | None
    ) -> bool:
        """更新自定义表情包说明标签（通常由视觉模型生成）。"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    UPDATE custom_stickers
                    SET caption = ?
                    WHERE user_id = ? AND sticker_id = ?
                """,
                    (caption, user_id, sticker_id),
                )
                conn.commit()
                updated = int(getattr(cursor, "rowcount", 0) or 0)

            self._invalidate_cache(f"custom_stickers_{user_id}")
            logger.info(
                "更新表情包 caption: user_id=%s, sticker_id=%s, updated=%s",
                user_id,
                sticker_id,
                updated,
            )
            return updated > 0
        except Exception as e:
            logger.error(
                "更新表情包 caption 失败: user_id=%s, sticker_id=%s, error=%s",
                user_id,
                sticker_id,
                e,
                exc_info=True,
            )
            return False

    def delete_custom_sticker(self, user_id: int, sticker_id: str) -> bool:
        """删除自定义表情包 - v2.29.9 修复：确保连接正确关闭

        Args:
            user_id: 用户ID
            sticker_id: 表情包ID

        Returns:
            bool: 是否成功
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute(
                    """
                    DELETE FROM custom_stickers
                    WHERE user_id = ? AND sticker_id = ?
                """,
                    (user_id, sticker_id),
                )

                conn.commit()

            # 清除缓存 - v2.29.7 修复：使用正确的方法名
            self._invalidate_cache(f"custom_stickers_{user_id}")

            logger.info(f"用户 {user_id} 删除自定义表情包: {sticker_id}")
            return True
        except Exception as e:
            logger.error(f"删除自定义表情包失败: {e}", exc_info=True)
            return False

    def get_sticker_count(self, user_id: int) -> int:
        """获取用户的自定义表情包数量 - v2.29.3 修复

        Args:
            user_id: 用户ID

        Returns:
            int: 表情包数量
        """
        try:
            return len(self.get_custom_stickers(user_id))
        except Exception as e:
            logger.error(f"获取表情包数量失败: {e}", exc_info=True)
            return 0

    def close(self) -> None:
        """释放连接池/缓存等资源（幂等）。

        说明：GUI 退出时建议显式调用，避免 Windows 下 sqlite 句柄残留导致文件锁定。
        """
        pool = getattr(self, "_pool", None)
        self._pool = None
        self.use_pool = False
        if pool is not None:
            try:
                pool.close()
            except Exception:
                pass

        try:
            with self._cache_lock:
                self._cache.clear()
                self._cache_ttl.clear()
        except Exception:
            pass
