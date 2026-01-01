"""
记忆系统模块

实现短期记忆和长期记忆管理，支持对话历史和语义检索。
"""

from __future__ import annotations

from collections import deque, OrderedDict
import math
import hashlib
import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from threading import Lock
import time
from uuid import uuid4
from typing import Any, Deque, Dict, Iterable, List, Optional, Sequence, TypedDict, Literal

from src.config.settings import settings
from src.utils.logger import get_logger
from src.utils.chroma_helper import create_chroma_vectorstore, get_collection_count

logger = get_logger(__name__)

# 轻量消息结构：避免短期记忆依赖 LangChain 消息类型，提升启动速度与兼容性
_ChatRole = Literal["user", "assistant", "system"]
_VALID_CHAT_ROLES: set[_ChatRole] = {"user", "assistant", "system"}


class _ChatMessage(TypedDict):
    role: _ChatRole
    content: str


# 重要性评估常量（热路径：避免每次调用重复构造列表）
_IMPORTANCE_KEYWORDS = (
    "喜欢",
    "讨厌",
    "爱好",
    "习惯",
    "生日",
    "家人",
    "朋友",
    "工作",
    "学习",
    "计划",
    "目标",
    "梦想",
    "重要",
    "记住",
    "名字",
    "叫",
    "是谁",
    "什么时候",
    "在哪",
    "为什么",
    "约定",
    "承诺",
    "答应",
    "保证",
    "一定",
    "必须",
)
_EMOTIONAL_KEYWORDS = (
    "开心",
    "高兴",
    "快乐",
    "幸福",
    "喜悦",
    "难过",
    "伤心",
    "痛苦",
    "难受",
    "失望",
    "生气",
    "愤怒",
    "讨厌",
    "烦",
    "恼",
    "爱",
    "喜欢",
    "想念",
    "思念",
    "关心",
)
_QUESTION_MARKERS = ("？", "?", "吗", "呢", "啊")

# v3.2: 导入记忆优化器
try:
    from src.agent.memory_optimizer import MemoryOptimizer

    MEMORY_OPTIMIZER_AVAILABLE = True
except ImportError:
    logger.warning("记忆优化器未安装，将使用基础记忆功能")
    MEMORY_OPTIMIZER_AVAILABLE = False

try:
    from src.agent.memory_optimizer import CharacterConsistencyScorer

    CHARACTER_SCORER_AVAILABLE = True
except ImportError:
    CharacterConsistencyScorer = None  # type: ignore[assignment]
    CHARACTER_SCORER_AVAILABLE = False


class ShortTermMemory:
    """短期记忆管理器"""

    def __init__(self, k: int = 10):
        """
        初始化短期记忆

        Args:
            k: 保留的最近交互次数（每次交互为 user+assistant 两条消息）。
        """
        self.k = max(0, int(k))
        # 每轮对话包含用户和助手消息：默认容量为 2*k；k<=0 时不限制（向后兼容）。
        limit = self.k * 2
        maxlen = limit if limit > 0 else None
        self.messages: Deque[_ChatMessage] = deque(maxlen=maxlen)
        self._lock = Lock()
        self._version = 0
        self._cached_pairs_version = -1
        self._cached_pairs: Optional[tuple[tuple[_ChatRole, str], ...]] = None
        if self.k > 0:
            logger.info(
                "短期记忆初始化完成，保留最近 %d 轮对话（最多 %d 条消息）", self.k, self.k * 2
            )
        else:
            logger.info("短期记忆初始化完成（不限制消息条数）")

    @property
    def version(self) -> int:
        """短期记忆版本号（每次写入/清空都会递增）。"""
        with self._lock:
            return int(self._version)

    def __len__(self) -> int:
        with self._lock:
            return len(self.messages)

    def add_message(self, role: str, content: str) -> None:
        """
        添加消息到短期记忆

        Args:
            role: 消息角色 (user/assistant/system)
            content: 消息内容
        """
        if role not in _VALID_CHAT_ROLES:
            logger.warning("未知的消息角色: %s", role)
            return

        self.add_messages(((role, content),))

    def add_messages(self, messages: Iterable[tuple[str, str]]) -> None:
        """批量添加消息（减少锁竞争，并保证同一轮对话的原子性）。"""
        pending: list[_ChatMessage] = []
        for role, content in messages:
            if role not in _VALID_CHAT_ROLES:
                logger.warning("未知的消息角色: %s", role)
                continue
            if content is None:  # type: ignore[comparison-overlap]
                content_text = ""
            else:
                content_text = str(content)
            pending.append({"role": role, "content": content_text})
        if not pending:
            return

        with self._lock:
            self.messages.extend(pending)
            self._version += 1
            self._cached_pairs_version = -1
            self._cached_pairs = None

    def set_k(self, k: int) -> None:
        """更新短期记忆容量（按交互次数），并在必要时裁剪旧消息。"""
        new_k = max(0, int(k))
        limit = new_k * 2
        maxlen = limit if limit > 0 else None

        with self._lock:
            if new_k == self.k and self.messages.maxlen == maxlen:
                return
            existing = list(self.messages)
            self.k = new_k
            self.messages = deque(existing, maxlen=maxlen)
            self._version += 1
            self._cached_pairs_version = -1
            self._cached_pairs = None

    def _get_pairs_snapshot(self) -> tuple[tuple[_ChatRole, str], ...]:
        with self._lock:
            cached = self._cached_pairs
            if cached is not None and self._cached_pairs_version == self._version:
                return cached

            built = tuple((item["role"], item["content"]) for item in self.messages)
            self._cached_pairs = built
            self._cached_pairs_version = self._version
            return built

    def get_messages(self) -> List[_ChatMessage]:
        """
        获取短期记忆中的消息

        Returns:
            List[_ChatMessage]: 消息列表
        """
        pairs = self._get_pairs_snapshot()
        return [{"role": role, "content": content} for role, content in pairs]

    def get_messages_as_dict(self) -> List[Dict[str, str]]:
        """
        获取短期记忆中的消息（字典格式）

        Returns:
            List[Dict[str, str]]: 消息列表
        """
        pairs = self._get_pairs_snapshot()
        # 返回新 dict，避免调用方误改缓存/内部状态导致难以排查的问题。
        return [{"role": role, "content": content} for role, content in pairs]

    def clear(self) -> None:
        """清空短期记忆"""
        with self._lock:
            self.messages.clear()
            self._version += 1
            self._cached_pairs_version = -1
            self._cached_pairs = None
        logger.info("短期记忆已清空")


class LongTermMemory:
    """长期记忆管理器 (v3.3.2: 性能优化)"""

    @staticmethod
    def _compute_content_hash(content: str) -> str:
        """生成稳定内容指纹（用于持久化去重/检索去重）。"""
        normalized = "".join(str(content).split()).lower()
        return hashlib.md5(normalized.encode("utf-8")).hexdigest()

    @staticmethod
    def _parse_timestamp_to_unix(timestamp: str) -> Optional[float]:
        """Parse ISO timestamp string into unix seconds (supports trailing 'Z')."""
        if not isinstance(timestamp, str):
            return None
        ts = timestamp.strip()
        if not ts:
            return None
        if ts.endswith("Z"):
            ts = ts[:-1] + "+00:00"
        try:
            return datetime.fromisoformat(ts).timestamp()
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _ensure_timestamp_unix(
        metadata: Dict[str, Any],
        *,
        fallback_unix: Optional[float] = None,
    ) -> None:
        """确保 metadata 中存在数值型 timestamp_unix（epoch seconds）。"""
        existing = metadata.get("timestamp_unix")
        if isinstance(existing, (int, float)):
            return
        if isinstance(existing, str):
            try:
                metadata["timestamp_unix"] = float(existing)
                return
            except ValueError:
                pass

        timestamp = metadata.get("timestamp")
        if isinstance(timestamp, str) and timestamp:
            parsed = LongTermMemory._parse_timestamp_to_unix(timestamp)
            if parsed is not None:
                metadata["timestamp_unix"] = parsed
                return

        metadata["timestamp_unix"] = float(
            fallback_unix if fallback_unix is not None else time.time()
        )

    def __init__(
        self,
        persist_directory: Optional[Path] = None,
        collection_name: str = "long_term_memory",
        user_id: Optional[int] = None,
    ):
        """
        初始化长期记忆

        Args:
            persist_directory: 持久化目录
            collection_name: 集合名称
            user_id: 用户ID，用于创建用户特定的记忆路径
        """
        # 支持用户特定路径
        if persist_directory:
            self.persist_directory = persist_directory
        elif user_id is not None:
            # 用户特定路径
            self.persist_directory = (
                Path(settings.data_dir) / "users" / str(user_id) / "vectordb" / "long_term_memory"
            )
        else:
            # 全局路径（向后兼容）
            self.persist_directory = Path(settings.vector_db_path) / "long_term_memory"

        self.persist_directory = Path(self.persist_directory)
        self.persist_directory.mkdir(parents=True, exist_ok=True)
        self.collection_name = collection_name

        # v3.3.2: 批量操作缓冲区（线程安全）
        self._batch_buffer: List[Dict[str, Any]] = []
        self._batch_buffer_lock = Lock()  # 保护批量缓冲区的锁
        self._batch_size = max(
            1,
            int(getattr(getattr(settings, "agent", object()), "long_term_batch_size", 10)),
        )
        # 定时刷新（避免长期运行时“少量缓冲”一直不落盘）
        self._batch_flush_interval_s = max(
            0.0,
            float(
                getattr(
                    getattr(settings, "agent", object()),
                    "long_term_batch_flush_interval_s",
                    30.0,
                )
            ),
        )
        self._last_batch_flush_mono = time.monotonic()
        # 写入版本号：用于检索缓存失效（只在向量库实际写入成功后递增）
        self._write_version = 0
        # 底层向量库（Chroma/SQLite）在并发读写下可能出现锁冲突或不稳定：用锁串行化访问更稳
        self._vectorstore_lock = Lock()
        # 角色一致性评分器：只在检索时使用（低开销但避免重复初始化）
        self._character_scorer = None
        # 角色一致性分数缓存：用于给历史数据（缺少字段时）做“按需回填”并避免反复计算
        self._character_score_cache: OrderedDict[str, tuple[float, int]] = OrderedDict()
        self._character_score_cache_lock = Lock()
        self._character_score_cache_max = 2048

        # 初始化向量数据库 - 使用统一的初始化函数（v2.30.27: 支持本地 embedding 和缓存）
        self.vectorstore = create_chroma_vectorstore(
            collection_name=collection_name,
            persist_directory=str(self.persist_directory),
            use_local_embedding=settings.use_local_embedding,
            enable_cache=settings.enable_embedding_cache,
        )

        if self.vectorstore:
            count = get_collection_count(self.vectorstore)
            logger.info(
                "长期记忆初始化完成，存储路径: %s，已有记忆: %d 条",
                self.persist_directory,
                count,
            )
        else:
            logger.warning("长期记忆向量库初始化失败，长期记忆功能将不可用")

    def add_memory(
        self,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
        batch: bool = False,
    ) -> bool:
        """
        添加记忆到长期存储 (v3.3.2: 支持批量操作)

        Args:
            content: 记忆内容
            metadata: 元数据（如时间、类型等）
            batch: 是否批量模式（True时不立即写入，等待批量提交）
        """
        if self.vectorstore is None:
            logger.warning("向量数据库未初始化，无法添加长期记忆")
            return False

        if metadata is None:
            metadata = {}

        # 添加时间戳（保留调用方传入的 timestamp）
        timestamp = metadata.get("timestamp")
        if not isinstance(timestamp, str) or not timestamp:
            now_unix = time.time()
            metadata["timestamp_unix"] = float(now_unix)
            metadata["timestamp"] = datetime.fromtimestamp(now_unix).isoformat()
        else:
            self._ensure_timestamp_unix(metadata)
        # 追加内容指纹（用于跨进程/跨会话去重与统计）
        metadata.setdefault("content_hash", self._compute_content_hash(content))

        # v3.3.2: 批量模式 - 添加到缓冲区（线程安全）
        if batch:
            should_flush = False
            buffer_to_flush = None
            with self._batch_buffer_lock:
                self._batch_buffer.append({"content": content, "metadata": metadata})
                # 达到批量大小时自动提交
                now_mono = time.monotonic()
                due_by_time = (
                    self._batch_flush_interval_s > 0
                    and (now_mono - self._last_batch_flush_mono) >= self._batch_flush_interval_s
                )
                if len(self._batch_buffer) >= self._batch_size or due_by_time:
                    # 在锁外调用flush_batch，避免死锁
                    buffer_to_flush = self._batch_buffer.copy()
                    self._batch_buffer.clear()
                    should_flush = True
            # 在锁外执行批量写入
            if should_flush and buffer_to_flush:
                try:
                    contents = [item["content"] for item in buffer_to_flush]
                    metadatas = [item["metadata"] for item in buffer_to_flush]
                    with self._vectorstore_lock:
                        self.vectorstore.add_texts(
                            texts=contents,
                            metadatas=metadatas,
                        )
                        self._write_version += len(buffer_to_flush)
                    self._last_batch_flush_mono = time.monotonic()
                    logger.info("批量添加了 %d 条记忆", len(buffer_to_flush))
                except Exception as e:
                    logger.error("批量添加记忆失败: %s", e)
                    # 失败时把内容放回缓冲区，避免丢失（尽量保证“至少一次”写入）
                    with self._batch_buffer_lock:
                        self._batch_buffer = buffer_to_flush + self._batch_buffer
                    return False
            return True

        try:
            with self._vectorstore_lock:
                self.vectorstore.add_texts(
                    texts=[content],
                    metadatas=[metadata],
                )
                self._write_version += 1

            # v2.26.0: ChromaDB 0.4.0+ 自动持久化，无需手动调用 persist()
            # ChromaDB 会自动将所有写入操作持久化到磁盘
            logger.debug("记忆已添加（自动持久化）: %.30s...", content)

            logger.debug("添加长期记忆: %.50s...", content)
            return True
        except Exception as e:
            from src.utils.exceptions import handle_exception

            handle_exception(e, logger, "添加长期记忆失败")
            return False

    def add_memories(
        self,
        contents: Sequence[str],
        metadatas: Sequence[Dict[str, Any]],
    ) -> int:
        """
        批量添加长期记忆（一次 add_texts，减少 Chroma 写入开销）。

        Returns:
            int: 成功添加的条数（失败返回 0）
        """
        if self.vectorstore is None:
            logger.warning("向量数据库未初始化，无法批量添加长期记忆")
            return 0

        texts = list(contents or [])
        if not texts:
            return 0

        metadata_list = list(metadatas or [])
        if metadata_list and len(metadata_list) != len(texts):
            raise ValueError("contents 与 metadatas 长度不一致")

        if not metadata_list:
            metadata_list = [{} for _ in texts]

        now_unix = time.time()
        now_iso = datetime.fromtimestamp(now_unix).isoformat()
        for text, meta in zip(texts, metadata_list):
            timestamp = meta.get("timestamp")
            if not isinstance(timestamp, str) or not timestamp:
                meta["timestamp"] = now_iso
                meta.setdefault("timestamp_unix", float(now_unix))
            else:
                self._ensure_timestamp_unix(meta, fallback_unix=now_unix)
            meta.setdefault("content_hash", self._compute_content_hash(text))

        try:
            with self._vectorstore_lock:
                self.vectorstore.add_texts(
                    texts=texts,
                    metadatas=metadata_list,
                )
                self._write_version += len(texts)
            logger.info("批量添加了 %d 条记忆", len(texts))
            return len(texts)
        except Exception as e:
            from src.utils.exceptions import handle_exception

            handle_exception(e, logger, "批量添加长期记忆失败")
            return 0

    def flush_batch(self) -> int:
        """
        提交批量缓冲区中的记忆 (v3.3.2，线程安全版本)

        Returns:
            int: 成功添加的记忆数量
        """
        if self.vectorstore is None:
            return 0

        # 线程安全地获取并清空缓冲区
        with self._batch_buffer_lock:
            if not self._batch_buffer:
                return 0
            buffer_to_flush = self._batch_buffer.copy()
            self._batch_buffer.clear()

        # 在锁外执行批量写入，避免长时间持有锁
        try:
            contents = [item["content"] for item in buffer_to_flush]
            metadatas = [item["metadata"] for item in buffer_to_flush]

            with self._vectorstore_lock:
                self.vectorstore.add_texts(
                    texts=contents,
                    metadatas=metadatas,
                )
                self._write_version += len(buffer_to_flush)

            # v2.26.0: ChromaDB 0.4.0+ 自动持久化，无需手动调用 persist()
            # ChromaDB 会自动将所有写入操作持久化到磁盘
            logger.debug("批量记忆已添加（自动持久化）")

            count = len(buffer_to_flush)
            self._last_batch_flush_mono = time.monotonic()
            logger.info("批量添加了 %d 条记忆", count)
            return count

        except Exception as e:
            logger.error("批量添加记忆失败: %s", e)
            # 失败时把内容放回缓冲区，避免丢失（尽量保证“至少一次”写入）
            with self._batch_buffer_lock:
                self._batch_buffer = buffer_to_flush + self._batch_buffer
            return 0

    def export_records(
        self,
        *,
        include_embeddings: bool = False,
        batch_size: int = 500,
    ) -> Dict[str, Any]:
        """
        导出长期记忆（不包含向量，默认仅 documents + metadatas + ids）。

        Returns:
            Dict[str, Any]:
                {
                  "collection_name": str,
                  "count": int,
                  "items": [{"id": str, "content": str, "metadata": dict}, ...],
                }
        """
        if self.vectorstore is None:
            return {"collection_name": self.collection_name, "count": 0, "items": []}

        # 导出前尽量落盘缓冲区，避免“导出文件缺少最近记忆”
        try:
            self.flush_batch()
        except Exception as e:
            logger.debug("导出前刷新批量缓冲区失败（可忽略）: %s", e)

        try:
            collection = getattr(self.vectorstore, "_collection", None)
            if collection is None:
                logger.warning("长期记忆向量库不支持导出（缺少 _collection）")
                return {"collection_name": self.collection_name, "count": 0, "items": []}

            with self._vectorstore_lock:
                total = int(collection.count())
            # Chroma get() always returns ids; don't include "ids" (strict include validation).
            include = ["documents", "metadatas"]
            if include_embeddings:
                include.append("embeddings")

            items: List[Dict[str, Any]] = []
            batch_size = max(1, int(batch_size))
            now_unix = time.time()

            for offset in range(0, total, batch_size):
                with self._vectorstore_lock:
                    chunk = collection.get(
                        include=include,
                        limit=batch_size,
                        offset=offset,
                    )

                ids = chunk.get("ids") or []
                documents = chunk.get("documents") or []
                metadatas = chunk.get("metadatas") or []

                for doc_id, content, metadata in zip(ids, documents, metadatas):
                    if not content:
                        continue
                    meta = dict(metadata or {})
                    meta.setdefault("content_hash", self._compute_content_hash(content))
                    self._ensure_timestamp_unix(meta, fallback_unix=now_unix)
                    items.append(
                        {
                            "id": str(doc_id),
                            "content": content,
                            "metadata": meta,
                        }
                    )

            return {
                "collection_name": self.collection_name,
                "count": total,
                "items": items,
            }
        except TypeError:
            # 兼容少数旧版 chromadb：get() 不支持 offset/limit
            try:
                collection = getattr(self.vectorstore, "_collection", None)
                if collection is None:
                    return {"collection_name": self.collection_name, "count": 0, "items": []}
                with self._vectorstore_lock:
                    chunk = collection.get(include=["documents", "metadatas", "ids"])
                ids = chunk.get("ids") or []
                documents = chunk.get("documents") or []
                metadatas = chunk.get("metadatas") or []
                items = []
                now_unix = time.time()
                for doc_id, content, metadata in zip(ids, documents, metadatas):
                    if not content:
                        continue
                    meta = dict(metadata or {})
                    meta.setdefault("content_hash", self._compute_content_hash(content))
                    self._ensure_timestamp_unix(meta, fallback_unix=now_unix)
                    items.append({"id": str(doc_id), "content": content, "metadata": meta})
                return {
                    "collection_name": self.collection_name,
                    "count": len(items),
                    "items": items,
                }
            except Exception as e:
                logger.warning("导出长期记忆失败（兼容路径）: %s", e)
                return {"collection_name": self.collection_name, "count": 0, "items": []}
        except Exception as e:
            logger.exception("导出长期记忆失败: %s", e)
            return {"collection_name": self.collection_name, "count": 0, "items": []}

    def import_records(
        self,
        records: Sequence[Dict[str, Any]],
        *,
        overwrite: bool = False,
        batch_size: int = 128,
    ) -> int:
        """
        导入长期记忆（不导入向量，写入时会重新生成 embedding）。

        Args:
            records: 形如 export_records()["items"] 的列表
            overwrite: True 时会清空现有长期记忆再导入，并尽量保留原 id；False 时不清空且忽略原 id

        Returns:
            int: 成功导入的条数
        """
        if self.vectorstore is None:
            logger.warning("向量数据库未初始化，无法导入长期记忆")
            return 0

        if not records:
            return 0

        if overwrite:
            self.clear()
            if self.vectorstore is None:
                logger.warning("清空后向量库初始化失败，无法导入长期记忆")
                return 0

        texts: List[str] = []
        metadatas: List[Dict[str, Any]] = []
        ids: List[str] = []

        now_unix = time.time()
        now_iso = datetime.fromtimestamp(now_unix).isoformat()
        for item in records:
            content = (item or {}).get("content")
            if not content:
                continue
            metadata = dict((item or {}).get("metadata") or {})
            timestamp = metadata.get("timestamp")
            if not isinstance(timestamp, str) or not timestamp:
                metadata["timestamp"] = now_iso
                metadata.setdefault("timestamp_unix", float(now_unix))
            else:
                self._ensure_timestamp_unix(metadata, fallback_unix=now_unix)
            metadata.setdefault("content_hash", self._compute_content_hash(content))

            if overwrite:
                ids.append(str((item or {}).get("id") or uuid4().hex))
            else:
                original_id = (item or {}).get("id")
                if original_id:
                    metadata.setdefault("original_id", str(original_id))

            texts.append(content)
            metadatas.append(metadata)

        if not texts:
            return 0

        imported = 0
        batch_size = max(1, int(batch_size))

        for idx in range(0, len(texts), batch_size):
            chunk_texts = texts[idx : idx + batch_size]
            chunk_metas = metadatas[idx : idx + batch_size]
            try:
                with self._vectorstore_lock:
                    if overwrite:
                        chunk_ids = ids[idx : idx + batch_size]
                        self.vectorstore.add_texts(
                            texts=chunk_texts,
                            metadatas=chunk_metas,
                            ids=chunk_ids,
                        )
                    else:
                        self.vectorstore.add_texts(
                            texts=chunk_texts,
                            metadatas=chunk_metas,
                        )
                    self._write_version += len(chunk_texts)
                imported += len(chunk_texts)
            except Exception as e:
                logger.warning("导入长期记忆批次失败（idx=%d）: %s", idx, e)

        if imported:
            logger.info("导入长期记忆完成: %d 条 (overwrite=%s)", imported, overwrite)
        return imported

    def prune(
        self,
        *,
        max_items: Optional[int] = None,
        max_age_days: Optional[int] = None,
        preserve_importance_above: float = 0.85,
        dry_run: bool = True,
        batch_size: int = 500,
    ) -> Dict[str, Any]:
        """
        清理/裁剪长期记忆（默认 dry_run，不会真正删除）。

        规则（安全优先）：
        - max_age_days: 删除超过指定天数且 importance < preserve_importance_above 的记忆
        - max_items: 在保护高重要性记忆的前提下，将总量裁剪到 max_items

        Returns:
            Dict[str, Any]: 清理统计信息
        """
        if self.vectorstore is None:
            return {
                "dry_run": dry_run,
                "total_before": 0,
                "deleted": 0,
                "protected": 0,
                "would_delete_ids": [],
            }

        # 先落盘缓冲区，避免“删错/漏删”
        try:
            self.flush_batch()
        except Exception as e:
            logger.debug("prune 前刷新批量缓冲区失败（可忽略）: %s", e)

        collection = getattr(self.vectorstore, "_collection", None)
        if collection is None or not hasattr(collection, "get") or not hasattr(collection, "count"):
            return {
                "dry_run": dry_run,
                "total_before": 0,
                "deleted": 0,
                "protected": 0,
                "would_delete_ids": [],
            }

        now_unix = time.time()
        preserve_importance_above = min(1.0, max(0.0, float(preserve_importance_above)))

        protected_ids: set[str] = set()
        ids_to_delete: set[str] = set()
        candidates: list[tuple[str, Optional[float], float]] = []
        total_before = 0

        cutoff_unix: Optional[float] = None
        if max_age_days is not None:
            max_age_days = max(0, int(max_age_days))
            cutoff_unix = now_unix - float(max_age_days) * 86400.0

        def _iter_id_meta() -> Iterable[tuple[str, Dict[str, Any]]]:
            # Chroma get() always returns ids; don't include "ids" (strict include validation).
            include = ["metadatas"]
            try:
                with self._vectorstore_lock:
                    total = int(collection.count())
                step = max(1, int(batch_size))
                for offset in range(0, total, step):
                    with self._vectorstore_lock:
                        chunk = collection.get(include=include, limit=step, offset=offset)
                    ids = chunk.get("ids") or []
                    metadatas = chunk.get("metadatas") or []
                    for doc_id, meta in zip(ids, metadatas):
                        yield str(doc_id), dict(meta or {})
            except TypeError:
                with self._vectorstore_lock:
                    chunk = collection.get(include=include)
                ids = chunk.get("ids") or []
                metadatas = chunk.get("metadatas") or []
                for doc_id, meta in zip(ids, metadatas):
                    yield str(doc_id), dict(meta or {})

        for doc_id, meta in _iter_id_meta():
            if not doc_id:
                continue
            total_before += 1

            importance = float(meta.get("importance", 0.5) or 0.5)
            is_protected = importance >= preserve_importance_above
            if is_protected:
                protected_ids.add(doc_id)

            ts_unix: Optional[float] = None
            ts_unix_raw = meta.get("timestamp_unix")
            if isinstance(ts_unix_raw, (int, float)):
                ts_unix = float(ts_unix_raw)
            elif isinstance(ts_unix_raw, str):
                try:
                    ts_unix = float(ts_unix_raw)
                except ValueError:
                    ts_unix = None

            if ts_unix is None:
                ts = meta.get("timestamp")
                if isinstance(ts, str) and ts:
                    ts_unix = self._parse_timestamp_to_unix(ts)

            # 1) 按年龄裁剪（仅删除低重要性）
            if (cutoff_unix is not None) and (not is_protected):
                if ts_unix is not None and ts_unix < cutoff_unix:
                    ids_to_delete.add(doc_id)
                    continue

            # 2) 按数量裁剪（保护高重要性）
            if max_items is not None and not is_protected:
                candidates.append((doc_id, ts_unix, importance))

        if total_before == 0:
            return {
                "dry_run": dry_run,
                "total_before": 0,
                "deleted": 0,
                "protected": 0,
                "would_delete_ids": [],
            }

        if max_items is not None:
            import heapq

            max_items = max(0, int(max_items))
            protected_count = len(protected_ids)
            allowance = max(max_items - protected_count, 0)

            def _sort_key(item_tuple: tuple[str, Optional[float], float]) -> tuple[float, float]:
                _, ts_unix, importance = item_tuple
                return (importance, float(ts_unix or 0.0))

            if allowance == 0:
                ids_to_delete.update({doc_id for doc_id, _, _ in candidates})
            elif candidates:
                keep = heapq.nlargest(allowance, candidates, key=_sort_key)
                keep_ids = {doc_id for doc_id, _, _ in keep}
                for doc_id, _, _ in candidates:
                    if doc_id not in keep_ids:
                        ids_to_delete.add(doc_id)

        # 真正删除（分批，避免一次性 ids 过多）
        deleted = 0
        if ids_to_delete and not dry_run:
            collection = getattr(self.vectorstore, "_collection", None)
            if collection is None or not hasattr(collection, "delete"):
                logger.warning("长期记忆向量库不支持 delete，无法执行 prune")
            else:
                delete_ids = list(ids_to_delete)
                for offset in range(0, len(delete_ids), batch_size):
                    chunk = delete_ids[offset : offset + batch_size]
                    with self._vectorstore_lock:
                        collection.delete(ids=chunk)
                        self._write_version += 1  # 删除也会改变检索结果，触发缓存失效
                    deleted += len(chunk)

        return {
            "dry_run": dry_run,
            "total_before": total_before,
            "deleted": deleted if not dry_run else 0,
            "protected": len(protected_ids),
            "would_delete": len(ids_to_delete),
            "would_delete_ids": sorted(ids_to_delete)[:200],
        }

    def get_memories_time_range(
        self,
        *,
        start_unix: float,
        end_unix: float,
        limit: int = 20,
        batch_size: int = 500,
    ) -> List[Dict[str, Any]]:
        """按时间范围获取长期记忆（不依赖语义相似度，适用于“今天/刚才/1小时前”等时间类查询）。"""
        if self.vectorstore is None:
            return []

        try:
            start_unix_f = float(start_unix)
            end_unix_f = float(end_unix)
        except Exception:
            return []

        if start_unix_f > end_unix_f:
            start_unix_f, end_unix_f = end_unix_f, start_unix_f

        limit = max(1, int(limit))
        batch_size = max(1, int(batch_size))

        collection = getattr(self.vectorstore, "_collection", None)
        if collection is None or not hasattr(collection, "get"):
            return []

        # Chroma get() always returns ids; don't include "ids" (strict versions validate include).
        include = ["documents", "metadatas"]

        def _iter_chunk(chunk: Dict[str, Any]) -> Iterable[tuple[str, Dict[str, Any]]]:
            documents = chunk.get("documents") or []
            metadatas = chunk.get("metadatas") or []
            for content, metadata in zip(documents, metadatas):
                if not content:
                    continue
                yield str(content), dict(metadata or {})

        now_unix = time.time()
        heap: list[tuple[float, str, Dict[str, Any]]] = []

        def _maybe_add(content: str, meta: Dict[str, Any]) -> None:
            if not content:
                return
            meta.setdefault("content_hash", self._compute_content_hash(content))
            self._ensure_timestamp_unix(meta, fallback_unix=now_unix)
            ts_unix_raw = meta.get("timestamp_unix")
            try:
                ts_unix = float(ts_unix_raw)
            except (TypeError, ValueError):
                return
            if not (start_unix_f <= ts_unix <= end_unix_f):
                return

            import heapq

            if len(heap) < limit:
                heapq.heappush(heap, (ts_unix, content, meta))
                return
            if ts_unix > heap[0][0]:
                heapq.heapreplace(heap, (ts_unix, content, meta))

        chunk: Optional[Dict[str, Any]] = None
        # Prefer server-side filtering when available.
        # Fallback scan handles stores/records missing numeric timestamp_unix.
        try:
            where = {"timestamp_unix": {"$gte": start_unix_f, "$lte": end_unix_f}}
            with self._vectorstore_lock:
                chunk = collection.get(where=where, include=include)
        except Exception:
            chunk = None

        try:
            has_any = False
            if chunk is not None:
                for content, meta in _iter_chunk(chunk):
                    has_any = True
                    _maybe_add(content, meta)

            # Fallback scan: handle stores that don't support where filtering,
            # or records missing timestamp_unix.
            if not has_any:
                include_all = include
                if hasattr(collection, "count"):
                    try:
                        with self._vectorstore_lock:
                            total = int(collection.count())
                        for offset in range(0, total, batch_size):
                            with self._vectorstore_lock:
                                part = collection.get(
                                    include=include_all,
                                    limit=batch_size,
                                    offset=offset,
                                )
                            for content, meta in _iter_chunk(part):
                                _maybe_add(content, meta)
                    except TypeError:
                        with self._vectorstore_lock:
                            part = collection.get(include=include_all)
                        for content, meta in _iter_chunk(part):
                            _maybe_add(content, meta)
                else:
                    with self._vectorstore_lock:
                        part = collection.get(include=include_all)
                    for content, meta in _iter_chunk(part):
                        _maybe_add(content, meta)
        except Exception:
            return []

        heap.sort(key=lambda item: item[0], reverse=True)
        return [{"content": content, "metadata": meta} for _, content, meta in heap]

    def search_memories(
        self,
        query: str,
        k: int = 5,
        filter_dict: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        搜索相关记忆 (v3.3.4: 性能优化 - 智能缓存和批量检索)

        Args:
            query: 查询文本
            k: 返回的记忆数量
            filter_dict: 过滤条件

        Returns:
            List[Dict[str, Any]]: 相关记忆列表
        """
        if self.vectorstore is None:
            logger.warning("向量数据库未初始化，无法搜索长期记忆")
            return []

        try:
            # v3.3: 增加检索数量，后续重排序
            search_k = min(k * 3, 20)  # 检索3倍数量，最多20条

            character_weight = float(
                getattr(
                    getattr(settings, "agent", object()),
                    "memory_character_consistency_weight",
                    0.1,
                )
            )
            if not math.isfinite(character_weight):
                character_weight = 0.0
            character_weight = max(0.0, min(character_weight, 1.0))

            scorer = None
            scorer_version: Optional[int] = None
            if (
                CHARACTER_SCORER_AVAILABLE
                and character_weight > 0.0
                and CharacterConsistencyScorer is not None
            ):
                scorer = getattr(self, "_character_scorer", None)
                if scorer is None:
                    try:
                        scorer = CharacterConsistencyScorer()
                        self._character_scorer = scorer
                    except Exception as e:
                        logger.debug("角色一致性评分器初始化失败: %s", e)
                        scorer = None
                scorer_version = getattr(CharacterConsistencyScorer, "SCORER_VERSION", None)

            with self._vectorstore_lock:
                results = self.vectorstore.similarity_search_with_score(
                    query=query,
                    k=search_k,
                    filter=filter_dict,
                )

            now_unix = time.time()
            memories = []
            for doc, score in results:
                metadata = dict(getattr(doc, "metadata", None) or {})
                metadata.setdefault(
                    "content_hash",
                    self._compute_content_hash(doc.page_content),
                )
                # v3.3: 计算相似度（ChromaDB的score越小越相似）
                similarity = 1.0 / (1.0 + score)  # 转换为0-1之间的相似度

                # v3.3: 应用相似度阈值过滤
                if similarity < 0.3:  # 过滤低相关性记忆
                    continue

                # v3.3: 时间衰减（最近的记忆更重要）
                recency_score = 1.0
                mem_ts_unix: Optional[float] = None
                ts_unix_raw = metadata.get("timestamp_unix")
                if isinstance(ts_unix_raw, (int, float)):
                    mem_ts_unix = float(ts_unix_raw)
                elif isinstance(ts_unix_raw, str):
                    try:
                        mem_ts_unix = float(ts_unix_raw)
                        metadata["timestamp_unix"] = mem_ts_unix
                    except ValueError:
                        mem_ts_unix = None

                if mem_ts_unix is None:
                    timestamp = metadata.get("timestamp")
                    if isinstance(timestamp, str) and timestamp:
                        parsed = self._parse_timestamp_to_unix(timestamp)
                        if parsed is not None:
                            mem_ts_unix = parsed
                            metadata["timestamp_unix"] = mem_ts_unix
                        else:
                            logger.debug("解析时间戳失败: %s", timestamp)
                            mem_ts_unix = None

                if mem_ts_unix is not None:
                    age_days = max(0.0, (now_unix - mem_ts_unix) / 86400.0)
                    # 30天内的记忆不衰减，之后逐渐衰减
                    if age_days > 30:
                        recency_score = max(0.5, 1.0 - (age_days - 30) / 365.0)
                    else:
                        recency_score = 1.0

                # v3.3: 重要性加权
                importance = metadata.get("importance", 0.5)

                character_consistency = 0.5
                use_character_weight = False
                existing = metadata.get("character_consistency")
                if isinstance(existing, (int, float)) and 0.0 <= float(existing) <= 1.0:
                    character_consistency = float(existing)
                    use_character_weight = character_weight > 0.0

                if scorer is not None and character_weight > 0.0:
                    existing_version = metadata.get("character_consistency_version")
                    needs_rescore = (
                        not isinstance(existing, (int, float))
                        or not (0.0 <= float(existing) <= 1.0)
                        or (scorer_version is not None and existing_version != scorer_version)
                    )
                    content_hash = metadata.get("content_hash")
                    cache_version = int(scorer_version or 0)
                    if needs_rescore and isinstance(content_hash, str) and content_hash:
                        with self._character_score_cache_lock:
                            cached = self._character_score_cache.get(content_hash)
                            if cached is not None and cached[1] == cache_version:
                                cached_score = float(cached[0])
                                character_consistency = float(min(max(cached_score, 0.0), 1.0))
                                metadata["character_consistency"] = character_consistency
                                # Cache hit: keep `existing` in sync.
                                existing = character_consistency
                                if cache_version:
                                    metadata["character_consistency_version"] = cache_version
                                self._character_score_cache.move_to_end(content_hash)
                                needs_rescore = False

                    if needs_rescore:
                        try:
                            character_consistency = float(
                                scorer.score_character_consistency(doc.page_content)
                            )
                            metadata["character_consistency"] = character_consistency
                            if scorer_version is not None:
                                metadata["character_consistency_version"] = int(scorer_version)
                            if isinstance(content_hash, str) and content_hash:
                                with self._character_score_cache_lock:
                                    self._character_score_cache[content_hash] = (
                                        float(min(max(character_consistency, 0.0), 1.0)),
                                        cache_version,
                                    )
                                    self._character_score_cache.move_to_end(content_hash)
                                    while (
                                        len(self._character_score_cache)
                                        > self._character_score_cache_max
                                    ):
                                        self._character_score_cache.popitem(last=False)
                        except Exception as e:
                            logger.debug("角色一致性评分失败: %s", e)
                            character_consistency = 0.5
                    else:
                        if isinstance(existing, (int, float)):
                            character_consistency = float(existing)
                    character_consistency = float(min(max(character_consistency, 0.0), 1.0))
                    use_character_weight = True

                # v3.3: 综合评分 = 相似度(60%) + 时间性(20%) + 重要性(20%) + 角色一致性(可配权重)
                numerator = similarity * 0.6 + recency_score * 0.2 + float(importance) * 0.2
                denom = 1.0
                if use_character_weight:
                    numerator += character_consistency * character_weight
                    denom += character_weight
                final_score = numerator / denom

                memories.append(
                    {
                        "content": doc.page_content,
                        "metadata": metadata,
                        "score": score,  # 原始分数
                        "similarity": similarity,  # 相似度
                        "recency_score": recency_score,  # 时间性
                        "importance": importance,  # 重要性
                        "character_consistency": character_consistency,  # 角色一致性
                        "final_score": final_score,  # 综合评分
                    }
                )

            # v3.3: 按综合评分排序，返回top-k
            memories.sort(key=lambda x: x["final_score"], reverse=True)
            memories = memories[:k]

            logger.debug(
                "搜索到 %d 条相关记忆（从%d条中筛选）",
                len(memories),
                len(results),
            )
            return memories

        except Exception as e:
            logger.exception("搜索长期记忆失败: %s", e)
            return []

    def summarize_memory(self, content: str, max_length: int = 200) -> str:
        """
        智能压缩记忆内容 (v3.3.2)

        Args:
            content: 原始记忆内容
            max_length: 最大长度

        Returns:
            str: 压缩后的记忆
        """
        if len(content) <= max_length:
            return content

        # 简单的智能截断：保留开头和结尾
        half = max_length // 2 - 10
        return f"{content[:half]}... [省略] ...{content[-half:]}"

    def get_memory_count(self) -> int:
        """
        获取记忆总数 (v3.3.2)

        Returns:
            int: 记忆数量
        """
        if self.vectorstore is None:
            return 0

        try:
            collection = self.vectorstore._collection
            with self._vectorstore_lock:
                return collection.count()
        except (AttributeError, RuntimeError) as e:
            logger.debug("无法获取记忆数量: %s", e)
            return 0

    @property
    def write_version(self) -> int:
        """长期记忆写入版本号（仅在向量库写入成功后递增）。"""
        return int(getattr(self, "_write_version", 0))

    def clear(self) -> None:
        """清空长期记忆"""
        if self.vectorstore is None:
            logger.warning("向量数据库未初始化")
            return

        try:
            # clear 表示显式丢弃未落盘的批量缓冲区
            with self._batch_buffer_lock:
                self._batch_buffer.clear()
            self._last_batch_flush_mono = time.monotonic()

            # 删除集合并重新创建
            with self._vectorstore_lock:
                self.vectorstore.delete_collection()
                self.vectorstore = create_chroma_vectorstore(
                    collection_name=self.collection_name,
                    persist_directory=str(self.persist_directory),
                    use_local_embedding=settings.use_local_embedding,
                    enable_cache=settings.enable_embedding_cache,
                )
            if self.vectorstore is None:
                logger.error("长期记忆已删除，但向量库重新初始化失败")
            else:
                self._write_version += 1
                logger.info("长期记忆已清空")
        except Exception as e:
            logger.error("清空长期记忆失败: %s", e)


class MemoryManager:
    """记忆管理器，统一管理短期和长期记忆"""

    def __init__(
        self,
        short_term_k: Optional[int] = None,
        enable_long_term: Optional[bool] = None,
        user_id: Optional[int] = None,
        enable_optimizer: Optional[bool] = None,
        enable_auto_consolidate: Optional[bool] = None,
        auto_consolidate_interval: Optional[int] = None,
    ):
        """
        初始化记忆管理器

        Args:
            short_term_k: 短期记忆保留的消息数量
            enable_long_term: 是否启用长期记忆
            user_id: 用户ID，用于创建用户特定的记忆路径
            enable_optimizer: 是否启用记忆优化器 (v3.2)
            enable_auto_consolidate: 是否在 MemoryManager 内部自动触发巩固（默认 True）
            auto_consolidate_interval: 自动巩固触发间隔（交互次数），默认 10
        """
        self.user_id = user_id

        # 短期记忆
        k = short_term_k or settings.short_term_memory_k
        self.short_term = ShortTermMemory(k=k)

        # 长期记忆
        self.enable_long_term = (
            enable_long_term if enable_long_term is not None else settings.long_term_memory_enabled
        )

        if self.enable_long_term:
            self.long_term = LongTermMemory(user_id=user_id)
        else:
            self.long_term = None
            logger.info("长期记忆未启用")

        # v3.2: 记忆优化器
        self.enable_optimizer = (
            enable_optimizer
            if enable_optimizer is not None
            else getattr(settings.agent, "memory_optimizer_enabled", True)
        )

        if self.enable_optimizer and MEMORY_OPTIMIZER_AVAILABLE:
            dedup_max_hashes = int(
                getattr(
                    getattr(settings, "agent", object()),
                    "memory_dedup_max_hashes",
                    50_000,
                )
            )
            self.optimizer = MemoryOptimizer(
                enable_cache=True,
                enable_deduplication=True,
                enable_consolidation=True,
                enable_character_scoring=True,
                dedup_max_hashes=dedup_max_hashes,
                user_id=user_id,
            )
            logger.info("记忆优化器已启用")
        else:
            self.optimizer = None
            if self.enable_optimizer and not MEMORY_OPTIMIZER_AVAILABLE:
                logger.warning("记忆优化器未安装")

        # v3.3: 自动巩固（可选，避免与 Agent 自身后台巩固重复）
        self._auto_consolidate_enabled = (
            bool(enable_auto_consolidate) if enable_auto_consolidate is not None else True
        )
        self._auto_consolidate_interval = max(1, int(auto_consolidate_interval or 10))
        self._auto_consolidate_count = 0
        self._auto_consolidate_lock = Lock()
        self._auto_consolidate_running = False

        logger.info("记忆管理器初始化完成 (用户ID: %s)", user_id or "全局")

    @property
    def short_term_version(self) -> int:
        """短期记忆版本号（每次 add_interaction/clear_all 都会递增）。"""
        return int(getattr(self.short_term, "version", 0))

    def add_interaction(
        self,
        user_message: str,
        assistant_message: str,
        save_to_long_term: bool = False,
        importance: Optional[float] = None,
    ) -> None:
        """
        添加一次交互到记忆 (v3.3: 智能重要性评估)

        Args:
            user_message: 用户消息
            assistant_message: 助手回复
            save_to_long_term: 是否保存到长期记忆
            importance: 重要性分数 (0-1)，如果未提供则自动评估
        """
        # 添加到短期记忆（快速路径）
        self.short_term.add_messages((("user", user_message), ("assistant", assistant_message)))

        # 添加到长期记忆
        if save_to_long_term:
            self.add_interaction_long_term(
                user_message=user_message,
                assistant_message=assistant_message,
                importance=importance,
            )

        # v3.3: 自动巩固（每N次交互，可选）
        if self._auto_consolidate_enabled and self.optimizer and self.long_term:
            self._auto_consolidate_count += 1
            if self._auto_consolidate_count >= self._auto_consolidate_interval:
                self._auto_consolidate_count = 0
                should_start = False
                with self._auto_consolidate_lock:
                    if not self._auto_consolidate_running:
                        self._auto_consolidate_running = True
                        should_start = True

                if should_start:
                    # 在后台线程中执行巩固，不阻塞响应
                    try:
                        import threading

                        def background_consolidate() -> None:
                            try:
                                consolidated = self.consolidate_memories()
                                if consolidated > 0:
                                    logger.info("自动巩固了 %d 条记忆", consolidated)
                            except Exception as e:
                                logger.warning("自动巩固失败: %s", e)
                            finally:
                                with self._auto_consolidate_lock:
                                    self._auto_consolidate_running = False

                        thread = threading.Thread(target=background_consolidate, daemon=True)
                        thread.start()
                    except Exception as e:
                        logger.warning("启动自动巩固线程失败: %s", e)
                        with self._auto_consolidate_lock:
                            self._auto_consolidate_running = False

    def add_interaction_long_term(
        self,
        *,
        user_message: str,
        assistant_message: str,
        importance: Optional[float] = None,
    ) -> bool:
        """
        仅将一次交互写入长期记忆（不影响短期记忆）。

        设计目的：
        - GUI/流式热路径可先写入短期记忆，长期记忆写入放到后台线程，避免向量写入阻塞首包/流式体验。
        - 便于 Agent 侧做任务合并（coalesce）与背压控制。

        Returns:
            bool: 是否成功写入（或加入批量缓冲区）
        """
        if not self.long_term:
            return False

        user_name = getattr(settings.agent, "user", "主人")
        char_name = getattr(settings.agent, "char", "小雪糕")
        interaction = f"{user_name}: {user_message}\n{char_name}: {assistant_message}"

        # v3.3: 智能重要性评估（如果未提供）
        if importance is None:
            importance = self._estimate_importance(user_message, assistant_message)

        # v3.3: 自动决定是否保存（低重要性的对话不保存）
        if importance < 0.3:
            logger.debug(
                "跳过低重要性记忆 (重要性: %.2f): %.30s...",
                importance,
                interaction,
            )
            return False

        # v3.2.1: 优化性能 - 快速路径
        if self.optimizer:
            metadata = {
                "type": "conversation",
                "importance": importance,
                "access_count": 0,
                "user_message_length": len(user_message),
                "assistant_message_length": len(assistant_message),
            }

            # 快速去重检查（只检查哈希，不做复杂处理）
            deduplicator = self.optimizer.deduplicator
            content_hash: Optional[str] = None
            if deduplicator:
                content_hash = deduplicator.get_content_hash(interaction)
                if deduplicator.contains_hash(content_hash):
                    logger.debug("跳过重复记忆: %.30s...", interaction)
                    return False
                metadata["content_hash"] = content_hash

            # 角色一致性评分（低开销：规则/关键词，不调用 LLM）
            character_scorer = getattr(self.optimizer, "character_scorer", None)
            if character_scorer is not None:
                try:
                    metadata["character_consistency"] = float(
                        character_scorer.score_character_consistency(interaction)
                    )
                    metadata["character_consistency_version"] = int(
                        getattr(character_scorer, "SCORER_VERSION", 0) or 0
                    )
                except Exception as e:
                    logger.debug("角色一致性评分失败: %s", e)

            stored = self.long_term.add_memory(
                content=interaction,
                metadata=metadata,
                batch=True,
            )
            if stored and deduplicator and content_hash:
                try:
                    deduplicator.add_hash(content_hash)
                except Exception:
                    pass

            # 更新统计
            try:
                self.optimizer.stats["total_memories_processed"] += 1
            except Exception:
                pass
            logger.debug(
                "保存记忆 (重要性: %.2f): %.30s...",
                importance,
                interaction,
            )
            return bool(stored)

        stored = self.long_term.add_memory(
            content=interaction,
            metadata={
                "type": "conversation",
                "importance": importance,
            },
            batch=True,
        )
        return bool(stored)

    def _estimate_importance(self, user_message: str, assistant_message: str) -> float:
        """
        估算对话重要性 (v3.3: 基于规则的快速评估)

        Args:
            user_message: 用户消息
            assistant_message: 助手回复

        Returns:
            float: 重要性分数 (0-1)
        """
        importance = 0.5  # 基础分数

        # v3.3: 长度因素（较长的对话通常更重要）
        total_length = len(user_message) + len(assistant_message)
        if total_length > 200:
            importance += 0.1
        if total_length > 500:
            importance += 0.1

        user_lower = user_message.lower()
        # v3.3: 关键词检测（个人信息、重要事件）
        for keyword in _IMPORTANCE_KEYWORDS:
            if keyword in user_lower:
                importance += 0.05

        # v3.3: 问题检测（问题通常需要记住）
        if any(q in user_message for q in _QUESTION_MARKERS):
            importance += 0.05

        # v3.3: 情感强度检测
        for keyword in _EMOTIONAL_KEYWORDS:
            if keyword in user_lower:
                importance += 0.1
                break

        # v3.3: 限制在0-1范围内
        importance = max(0.0, min(1.0, importance))

        return importance

    def get_recent_messages(self) -> List[Dict[str, str]]:
        """
        获取最近的消息

        Returns:
            List[Dict[str, str]]: 消息列表
        """
        return self.short_term.get_messages_as_dict()

    def search_relevant_memories(
        self,
        query: str,
        k: Optional[int] = None,
    ) -> List[str]:
        """
        搜索相关的长期记忆 (v3.3: 增强检索质量)

        Args:
            query: 查询文本
            k: 返回的记忆数量

        Returns:
            List[str]: 相关记忆内容列表
        """
        if not self.long_term:
            return []

        k = k or settings.long_term_memory_top_k

        time_range = self._parse_time_query_unix_range(query)

        # v3.3: 智能缓存键（考虑语义相似性）
        # 将长期记忆写入版本纳入 key，避免写入后命中旧缓存导致“找不到新记忆”
        lt_version = getattr(getattr(self, "long_term", None), "write_version", 0)
        cache_key = f"{query.strip().lower()[:100]}|v{lt_version}"  # 标准化查询

        # v3.2.1: 优化性能 - 先检查缓存
        if time_range is None and self.optimizer and self.optimizer.cache:
            cached_result = self.optimizer.cache.get_query_result(cache_key)
            if cached_result is not None:
                self.optimizer.stats["cache_hits"] += 1
                logger.debug("缓存命中: %.30s...", query)
                return [mem["content"] for mem in cached_result[:k]]
            self.optimizer.stats["cache_misses"] += 1

        # v3.3: 执行增强检索
        if time_range is not None:
            start_unix, end_unix = time_range
            time_k = max(int(k), 8)
            memories = self.long_term.get_memories_time_range(
                start_unix=float(start_unix),
                end_unix=float(end_unix),
                limit=time_k,
            )
            if not memories:
                memories = self.long_term.search_memories(query, k=k)
        else:
            memories = self.long_term.search_memories(query, k=k)

        # v3.3: 记忆去重（基于内容相似度）
        if memories and len(memories) > 1:
            unique_memories = []
            seen_contents = set()

            for mem in memories:
                meta = mem.get("metadata", {}) or {}
                content_hash = meta.get("content_hash")
                if not content_hash:
                    content_hash = LongTermMemory._compute_content_hash(mem.get("content", ""))
                if content_hash and content_hash not in seen_contents:
                    unique_memories.append(mem)
                    seen_contents.add(content_hash)

            memories = unique_memories
            logger.debug("去重后保留 %d 条记忆", len(memories))

        # v3.3: 记忆增强（添加上下文信息）
        enhanced_memories = []
        for mem in memories:
            content = mem["content"]
            metadata = mem.get("metadata", {})

            # v3.3.2: 智能压缩长记忆
            if len(content) > 500 and self.long_term:
                content = self.long_term.summarize_memory(content, max_length=400)

            # v3.3: 添加时间上下文
            mem_time: Optional[datetime] = None
            ts_unix_raw = metadata.get("timestamp_unix")
            if isinstance(ts_unix_raw, (int, float)):
                mem_time = datetime.fromtimestamp(float(ts_unix_raw))
            elif isinstance(ts_unix_raw, str):
                try:
                    ts_unix_val = float(ts_unix_raw)
                    metadata["timestamp_unix"] = ts_unix_val
                    mem_time = datetime.fromtimestamp(ts_unix_val)
                except ValueError:
                    mem_time = None

            if mem_time is None:
                timestamp = metadata.get("timestamp")
                if isinstance(timestamp, str) and timestamp:
                    parsed = LongTermMemory._parse_timestamp_to_unix(timestamp)
                    if parsed is not None:
                        metadata["timestamp_unix"] = parsed
                        mem_time = datetime.fromtimestamp(parsed)
                    else:
                        logger.debug("解析时间戳失败: %s", timestamp)
                        mem_time = None

            if mem_time is not None:
                time_desc = self._get_time_description(mem_time)
                content = f"[{time_desc}] {content}"

            # v3.3: 添加重要性标记
            importance = metadata.get("importance", 0.5)
            if importance >= 0.8:
                content = f"⭐ {content}"  # 高重要性标记

            enhanced_memories.append(content)

        # v3.2.1: 缓存结果
        # 允许缓存空结果：cache_key 已包含 long_term.write_version，因此写入后会自动失效
        if time_range is None and self.optimizer and self.optimizer.cache is not None:
            memory_dicts = [
                {
                    "content": content,
                    "metadata": mem.get("metadata", {}),
                }
                for content, mem in zip(enhanced_memories, memories)
            ]

            self.optimizer.cache.set_query_result(cache_key, memory_dicts)

        return enhanced_memories

    @staticmethod
    def _parse_time_query_unix_range(query: str) -> Optional[tuple[float, float]]:
        """将“今天/昨天/刚才/1小时前”等时间表达解析成 unix 时间范围（闭区间）。"""
        text = (query or "").strip()
        if not text:
            return None

        now_dt = datetime.now()
        now_unix = time.time()

        chinese_digit: Dict[str, int] = {
            "零": 0,
            "〇": 0,
            "一": 1,
            "二": 2,
            "两": 2,
            "三": 3,
            "四": 4,
            "五": 5,
            "六": 6,
            "七": 7,
            "八": 8,
            "九": 9,
        }

        def parse_int(value: str) -> Optional[int]:
            v = (value or "").strip()
            if not v:
                return None
            if v.isdigit():
                return int(v)
            if v in chinese_digit:
                return chinese_digit[v]
            if v == "十":
                return 10
            if v.startswith("十"):
                return 10 + chinese_digit.get(v[1:], 0)
            if "十" in v:
                left, right = v.split("十", 1)
                tens = chinese_digit.get(left)
                if tens is None:
                    return None
                ones = chinese_digit.get(right, 0) if right else 0
                return tens * 10 + ones
            return None

        if any(token in text for token in ("刚才", "刚刚", "方才")):
            return now_unix - 3600.0, now_unix

        match = re.search(r"([0-9]+|[一二两三四五六七八九十]+)\s*(?:个)?\s*小时(?:前|之前)", text)
        if match:
            hours = parse_int(match.group(1))
            if hours is not None and hours > 0:
                return now_unix - float(hours) * 3600.0, now_unix

        match = re.search(r"([0-9]+|[一二两三四五六七八九十]+)\s*(?:个)?\s*分钟(?:前|之前)", text)
        if match:
            minutes = parse_int(match.group(1))
            if minutes is not None and minutes > 0:
                return now_unix - float(minutes) * 60.0, now_unix

        today_start = datetime(now_dt.year, now_dt.month, now_dt.day).timestamp()
        if any(token in text for token in ("今天", "今日")):
            return float(today_start), now_unix

        if any(token in text for token in ("昨天", "昨日")):
            start = datetime(now_dt.year, now_dt.month, now_dt.day).timestamp() - 86400.0
            return float(start), float(today_start)

        if "前天" in text:
            start = datetime(now_dt.year, now_dt.month, now_dt.day).timestamp() - 2 * 86400.0
            end = datetime(now_dt.year, now_dt.month, now_dt.day).timestamp() - 86400.0
            return float(start), float(end)

        return None

    def _get_time_description(self, mem_time: datetime) -> str:
        """
        获取时间描述 (v3.3)

        Args:
            mem_time: 记忆时间

        Returns:
            str: 时间描述
        """
        now = datetime.now()
        delta = now - mem_time

        if delta < timedelta(hours=1):
            return "刚才"
        elif delta < timedelta(hours=24):
            hours = int(delta.total_seconds() / 3600)
            return f"{hours}小时前"
        elif delta < timedelta(days=7):
            days = delta.days
            return f"{days}天前"
        elif delta < timedelta(days=30):
            weeks = delta.days // 7
            return f"{weeks}周前"
        elif delta < timedelta(days=365):
            months = delta.days // 30
            return f"{months}个月前"
        else:
            years = delta.days // 365
            return f"{years}年前"

    def consolidate_memories(self) -> int:
        """
        巩固记忆：将重要的短期记忆转移到长期记忆 (v3.3: 智能巩固)

        Returns:
            int: 巩固的记忆数量
        """
        if not self.optimizer or not self.long_term:
            return 0

        # 获取短期记忆
        short_term_messages = self.short_term.get_messages_as_dict()

        if not short_term_messages:
            return 0

        # v3.3: 转换为对话对（用户-助手），并批量写入长期记忆
        deduplicator = self.optimizer.deduplicator
        contents: List[str] = []
        metadatas: List[Dict[str, Any]] = []
        pending_hashes: List[str] = []
        i = 0
        while i < len(short_term_messages) - 1:
            if (
                short_term_messages[i]["role"] == "user"
                and short_term_messages[i + 1]["role"] == "assistant"
            ):
                user_msg = short_term_messages[i]["content"]
                assistant_msg = short_term_messages[i + 1]["content"]

                # v3.3: 评估重要性
                importance = self._estimate_importance(user_msg, assistant_msg)

                # v3.3: 只巩固重要的对话
                if importance >= 0.6:
                    user_name = getattr(settings.agent, "user", "主人")
                    char_name = getattr(settings.agent, "char", "小雪糕")
                    content = f"{user_name}: {user_msg}\n{char_name}: {assistant_msg}"
                    metadata = {
                        "type": "conversation",
                        "importance": importance,
                        "access_count": 0,
                        "consolidated": True,
                    }
                    character_scorer = getattr(self.optimizer, "character_scorer", None)
                    if character_scorer is not None:
                        try:
                            metadata["character_consistency"] = float(
                                character_scorer.score_character_consistency(content)
                            )
                            metadata["character_consistency_version"] = int(
                                getattr(character_scorer, "SCORER_VERSION", 0) or 0
                            )
                        except Exception as e:
                            logger.debug("角色一致性评分失败: %s", e)
                    if deduplicator:
                        content_hash = deduplicator.get_content_hash(content)
                        if deduplicator.contains_hash(content_hash):
                            i += 2
                            continue
                        pending_hashes.append(content_hash)
                        metadata["content_hash"] = content_hash
                    contents.append(content)
                    metadatas.append(metadata)

                i += 2
            else:
                i += 1

        if not contents:
            return 0

        consolidated_count = self.long_term.add_memories(contents, metadatas)
        if consolidated_count == len(contents) and deduplicator and pending_hashes:
            deduplicator.add_hashes(pending_hashes)

        if consolidated_count > 0:
            logger.info("巩固了 %d 条重要记忆到长期存储", consolidated_count)

        return consolidated_count

    def summarize_memories(self, query: str, max_length: int = 500) -> str:
        """
        摘要相关记忆 (v3.3: 记忆压缩)

        Args:
            query: 查询文本
            max_length: 最大摘要长度

        Returns:
            str: 记忆摘要
        """
        memories = self.search_relevant_memories(query, k=10)

        if not memories:
            return ""

        # v3.3: 简单的摘要策略
        summary_parts = []
        current_length = 0

        for memory in memories:
            # 移除时间标记和重要性标记
            clean_memory = memory.replace("⭐ ", "").split("] ", 1)[-1]

            # 截断过长的记忆
            if len(clean_memory) > 100:
                clean_memory = clean_memory[:97] + "..."

            if current_length + len(clean_memory) <= max_length:
                summary_parts.append(clean_memory)
                current_length += len(clean_memory)
            else:
                break

        return "\n".join(summary_parts)

    def get_memory_stats(self) -> Dict[str, Any]:
        """
        获取记忆统计信息 (v3.3.2: 增强统计)

        Returns:
            Dict[str, Any]: 统计信息
        """
        stats = {
            "short_term_count": len(self.short_term),
            "short_term_capacity": self.short_term.k * 2,
        }

        if self.long_term and self.long_term.vectorstore:
            try:
                stats["long_term_count"] = self.long_term.get_memory_count()

                # v3.3.2: 批量缓冲区状态
                stats["batch_buffer_size"] = len(self.long_term._batch_buffer)
                stats["batch_threshold"] = self.long_term._batch_size
                stats["batch_flush_interval_s"] = getattr(
                    self.long_term,
                    "_batch_flush_interval_s",
                    0.0,
                )
                stats["long_term_write_version"] = getattr(
                    self.long_term,
                    "write_version",
                    0,
                )
            except (AttributeError, RuntimeError) as e:
                logger.debug("获取长期记忆统计失败: %s", e)
                stats["long_term_count"] = "未知"
                stats["batch_buffer_size"] = 0
                stats["batch_threshold"] = 0
                stats["batch_flush_interval_s"] = 0.0
                stats["long_term_write_version"] = 0
        else:
            stats["long_term_count"] = 0
            stats["batch_buffer_size"] = 0
            stats["batch_threshold"] = 0
            stats["batch_flush_interval_s"] = 0.0
            stats["long_term_write_version"] = 0

        if self.optimizer:
            optimizer_stats = self.optimizer.get_stats()
            stats.update(optimizer_stats)

        return stats

    def get_optimizer_stats(self) -> Optional[Dict[str, Any]]:
        """
        获取优化器统计信息 (v3.2)

        Returns:
            Optional[Dict[str, Any]]: 统计信息，如果优化器未启用则返回None
        """
        if not self.optimizer:
            return None

        return self.optimizer.get_stats()

    def clear_all(self) -> None:
        """清空所有记忆"""
        self.short_term.clear()
        if self.long_term:
            self.long_term.clear()
        logger.info("所有记忆已清空")

    def cleanup_cache(self) -> None:
        """
        清理记忆相关缓存 / 缓冲区。

        - 刷新长期记忆批量缓冲区（避免进程退出导致最近记忆丢失）
        - 清理 MemoryOptimizer 缓存（降低常驻内存占用）
        """
        # 1) 刷新批量缓冲区（更重要：保证数据完整性）
        if self.long_term:
            try:
                flushed_count = self.long_term.flush_batch()
                if flushed_count > 0:
                    logger.info("已刷新 %d 个批量缓冲记忆到数据库", flushed_count)
            except Exception as e:
                logger.warning("刷新批量缓冲区失败: %s", e)

        # 2) 清理优化器缓存（可选）
        if self.optimizer:
            try:
                self.optimizer.clear_cache()
            except Exception as e:
                logger.debug("清理优化器缓存失败（可忽略）: %s", e)

    def prune_long_term(
        self,
        *,
        max_items: Optional[int] = None,
        max_age_days: Optional[int] = None,
        preserve_importance_above: float = 0.85,
        dry_run: bool = True,
    ) -> Dict[str, Any]:
        """裁剪长期记忆（默认 dry_run，不会真正删除）。"""
        if not self.long_term:
            return {
                "dry_run": dry_run,
                "total_before": 0,
                "deleted": 0,
                "protected": 0,
                "would_delete": 0,
                "would_delete_ids": [],
            }

        return self.long_term.prune(
            max_items=max_items,
            max_age_days=max_age_days,
            preserve_importance_above=preserve_importance_above,
            dry_run=dry_run,
        )

    def export_memories(
        self,
        filepath: Path,
        *,
        include_long_term: bool = True,
        include_optimizer_stats: bool = False,
    ) -> None:
        """
        导出记忆到文件

        Args:
            filepath: 导出文件路径
            include_long_term: 是否导出长期记忆（默认 True）
            include_optimizer_stats: 是否附带优化器统计（默认 False）
        """
        data = self.get_export_data(
            include_long_term=include_long_term,
            include_optimizer_stats=include_optimizer_stats,
        )

        filepath.parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        logger.info("记忆已导出到: %s", filepath)

    def get_export_data(
        self,
        *,
        include_long_term: bool = True,
        include_optimizer_stats: bool = False,
    ) -> Dict[str, Any]:
        """获取可序列化的记忆导出数据（不写文件）。"""
        data: Dict[str, Any] = {
            "format_version": 2,
            "user_id": self.user_id,
            "short_term": self.get_recent_messages(),
            "export_time": datetime.now().isoformat(),
        }

        if include_long_term and self.long_term:
            data["long_term"] = self.long_term.export_records()

        if include_optimizer_stats and self.optimizer:
            data["optimizer_stats"] = self.optimizer.get_stats()

        return data

    def import_from_data(
        self,
        data: Dict[str, Any],
        *,
        overwrite_long_term: bool = False,
        replace_short_term: bool = True,
    ) -> Dict[str, int]:
        """
        从 dict 导入记忆（支持 v2+ 导出结构，兼容旧结构）。

        Returns:
            Dict[str, int]: {"short_term": int, "long_term": int}
        """
        if not isinstance(data, dict):
            raise ValueError("记忆导入数据格式错误：应为 dict")

        imported_short = 0
        imported_long = 0

        short_term = data.get("short_term") or []
        if isinstance(short_term, list):
            if replace_short_term:
                self.short_term.clear()
            pairs: List[tuple[str, str]] = []
            for msg in short_term:
                if not isinstance(msg, dict):
                    continue
                role = msg.get("role")
                content = msg.get("content")
                if not role or not content:
                    continue
                pairs.append((str(role), str(content)))
            if pairs:
                self.short_term.add_messages(pairs)
                imported_short = len(pairs)

        long_term = data.get("long_term") or {}
        if (
            self.long_term
            and isinstance(long_term, dict)
            and isinstance(long_term.get("items"), list)
        ):
            imported_long = self.long_term.import_records(
                long_term.get("items", []),
                overwrite=overwrite_long_term,
            )

        logger.info(
            "导入记忆完成: short_term=%d, long_term=%d (overwrite_long_term=%s)",
            imported_short,
            imported_long,
            overwrite_long_term,
        )

        return {"short_term": imported_short, "long_term": imported_long}

    def import_memories(
        self,
        filepath: Path,
        *,
        overwrite_long_term: bool = False,
        replace_short_term: bool = True,
    ) -> Dict[str, int]:
        """
        从文件导入记忆。

        支持：
        - v2+ 导出格式（包含 short_term / long_term）
        - 旧格式（仅 short_term）

        Returns:
            Dict[str, int]: {"short_term": int, "long_term": int}
        """
        if not filepath.exists():
            raise FileNotFoundError(filepath)

        data = json.loads(filepath.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("记忆导入文件格式错误：应为 JSON object")

        return self.import_from_data(
            data,
            overwrite_long_term=overwrite_long_term,
            replace_short_term=replace_short_term,
        )
