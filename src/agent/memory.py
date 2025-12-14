"""
记忆系统模块

实现短期记忆和长期记忆管理，支持对话历史和语义检索。
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Optional, Sequence, TypedDict, Literal

from src.config.settings import settings
from src.utils.logger import get_logger
from src.utils.chroma_helper import create_chroma_vectorstore, get_collection_count

logger = get_logger(__name__)

# 轻量消息结构：避免短期记忆依赖 LangChain 消息类型，提升启动速度与兼容性
class _ChatMessage(TypedDict):
    role: Literal["user", "assistant", "system"]
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


class ShortTermMemory:
    """短期记忆管理器"""

    def __init__(self, k: int = 10):
        """
        初始化短期记忆

        Args:
            k: 保留的最近消息数量
        """
        self.k = k
        self.messages: List[_ChatMessage] = []
        self._lock = Lock()
        logger.info("短期记忆初始化完成，保留最近 %d 条消息", k)

    def add_message(self, role: str, content: str) -> None:
        """
        添加消息到短期记忆

        Args:
            role: 消息角色 (user/assistant/system)
            content: 消息内容
        """
        if role not in {"user", "assistant", "system"}:
            logger.warning("未知的消息角色: %s", role)
            return

        msg: _ChatMessage = {"role": role, "content": content}
        with self._lock:
            self.messages.append(msg)
            # 保持窗口大小：每轮对话包含用户和助手消息
            limit = self.k * 2
            if limit > 0 and len(self.messages) > limit:
                self.messages = self.messages[-limit:]

    def get_messages(self) -> List[_ChatMessage]:
        """
        获取短期记忆中的消息

        Returns:
            List[_ChatMessage]: 消息列表
        """
        with self._lock:
            return list(self.messages)

    def get_messages_as_dict(self) -> List[Dict[str, str]]:
        """
        获取短期记忆中的消息（字典格式）

        Returns:
            List[Dict[str, str]]: 消息列表
        """
        with self._lock:
            return [dict(item) for item in self.messages]

    def clear(self) -> None:
        """清空短期记忆"""
        with self._lock:
            self.messages = []
        logger.info("短期记忆已清空")


class LongTermMemory:
    """长期记忆管理器 (v3.3.2: 性能优化)"""

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
            self.persist_directory = Path(settings.data_dir) / "users" / str(user_id) / "vectordb" / "long_term_memory"
        else:
            # 全局路径（向后兼容）
            self.persist_directory = Path(settings.vector_db_path) / "long_term_memory"

        self.persist_directory = Path(self.persist_directory)
        self.persist_directory.mkdir(parents=True, exist_ok=True)
        self.collection_name = collection_name

        # v3.3.2: 批量操作缓冲区（线程安全）
        self._batch_buffer: List[Dict[str, Any]] = []
        self._batch_buffer_lock = Lock()  # 保护批量缓冲区的锁
        self._batch_size = 10  # 每10条记忆批量写入一次

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

        # 添加时间戳
        metadata["timestamp"] = datetime.now().isoformat()

        # v3.3.2: 批量模式 - 添加到缓冲区（线程安全）
        if batch:
            should_flush = False
            buffer_to_flush = None
            with self._batch_buffer_lock:
                self._batch_buffer.append({"content": content, "metadata": metadata})
                # 达到批量大小时自动提交
                if len(self._batch_buffer) >= self._batch_size:
                    # 在锁外调用flush_batch，避免死锁
                    buffer_to_flush = self._batch_buffer.copy()
                    self._batch_buffer.clear()
                    should_flush = True
            # 在锁外执行批量写入
            if should_flush and buffer_to_flush:
                try:
                    contents = [item["content"] for item in buffer_to_flush]
                    metadatas = [item["metadata"] for item in buffer_to_flush]
                    self.vectorstore.add_texts(
                        texts=contents,
                        metadatas=metadatas,
                    )
                    logger.info("批量添加了 %d 条记忆", len(buffer_to_flush))
                except Exception as e:
                    logger.error("批量添加记忆失败: %s", e)
                    # 失败时把内容放回缓冲区，避免丢失（尽量保证“至少一次”写入）
                    with self._batch_buffer_lock:
                        self._batch_buffer = buffer_to_flush + self._batch_buffer
                    return False
            return True

        try:
            self.vectorstore.add_texts(
                texts=[content],
                metadatas=[metadata],
            )

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

        timestamp = datetime.now().isoformat()
        for meta in metadata_list:
            meta.setdefault("timestamp", timestamp)

        try:
            self.vectorstore.add_texts(
                texts=texts,
                metadatas=metadata_list,
            )
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

            self.vectorstore.add_texts(
                texts=contents,
                metadatas=metadatas,
            )

            # v2.26.0: ChromaDB 0.4.0+ 自动持久化，无需手动调用 persist()
            # ChromaDB 会自动将所有写入操作持久化到磁盘
            logger.debug("批量记忆已添加（自动持久化）")

            count = len(buffer_to_flush)
            logger.info("批量添加了 %d 条记忆", count)
            return count

        except Exception as e:
            logger.error("批量添加记忆失败: %s", e)
            # 失败时把内容放回缓冲区，避免丢失（尽量保证“至少一次”写入）
            with self._batch_buffer_lock:
                self._batch_buffer = buffer_to_flush + self._batch_buffer
            return 0

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

            results = self.vectorstore.similarity_search_with_score(
                query=query,
                k=search_k,
                filter=filter_dict,
            )

            now = datetime.now()
            memories = []
            for doc, score in results:
                # v3.3: 计算相似度（ChromaDB的score越小越相似）
                similarity = 1.0 / (1.0 + score)  # 转换为0-1之间的相似度

                # v3.3: 应用相似度阈值过滤
                if similarity < 0.3:  # 过滤低相关性记忆
                    continue

                # v3.3: 时间衰减（最近的记忆更重要）
                timestamp = doc.metadata.get("timestamp")
                recency_score = 1.0
                if timestamp:
                    try:
                        mem_time = datetime.fromisoformat(timestamp)
                        age_days = (now - mem_time).days
                        # 30天内的记忆不衰减，之后逐渐衰减
                        recency_score = max(0.5, 1.0 - (age_days - 30) / 365.0) if age_days > 30 else 1.0
                    except (ValueError, TypeError) as e:
                        logger.debug("解析时间戳失败: %s", e)
                        pass

                # v3.3: 重要性加权
                importance = doc.metadata.get("importance", 0.5)

                # v3.3: 综合评分 = 相似度(60%) + 时间性(20%) + 重要性(20%)
                final_score = (
                    similarity * 0.6 +
                    recency_score * 0.2 +
                    importance * 0.2
                )

                memories.append({
                    "content": doc.page_content,
                    "metadata": doc.metadata,
                    "score": score,  # 原始分数
                    "similarity": similarity,  # 相似度
                    "recency_score": recency_score,  # 时间性
                    "importance": importance,  # 重要性
                    "final_score": final_score,  # 综合评分
                })

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
            return collection.count()
        except (AttributeError, RuntimeError) as e:
            logger.debug("无法获取记忆数量: %s", e)
            return 0

    def clear(self) -> None:
        """清空长期记忆"""
        if self.vectorstore is None:
            logger.warning("向量数据库未初始化")
            return

        try:
            # 删除集合并重新创建
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
            enable_long_term
            if enable_long_term is not None
            else settings.long_term_memory_enabled
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
            else getattr(settings.agent, 'memory_optimizer_enabled', True)
        )

        if self.enable_optimizer and MEMORY_OPTIMIZER_AVAILABLE:
            self.optimizer = MemoryOptimizer(
                enable_cache=True,
                enable_deduplication=True,
                enable_consolidation=True,
                enable_character_scoring=True,
                user_id=user_id,
            )
            logger.info("记忆优化器已启用")
        else:
            self.optimizer = None
            if self.enable_optimizer and not MEMORY_OPTIMIZER_AVAILABLE:
                logger.warning("记忆优化器未安装")

        # v3.3: 自动巩固（可选，避免与 Agent 自身后台巩固重复）
        self._auto_consolidate_enabled = (
            bool(enable_auto_consolidate)
            if enable_auto_consolidate is not None
            else True
        )
        self._auto_consolidate_interval = max(1, int(auto_consolidate_interval or 10))
        self._auto_consolidate_count = 0
        self._auto_consolidate_lock = Lock()
        self._auto_consolidate_running = False
        # 短期记忆版本号：用于构建上下文缓存的可靠失效键
        self._short_term_version = 0

        logger.info("记忆管理器初始化完成 (用户ID: %s)", user_id or "全局")

    @property
    def short_term_version(self) -> int:
        """短期记忆版本号（每次 add_interaction/clear_all 都会递增）。"""
        return int(self._short_term_version)

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
        self.short_term.add_message("user", user_message)
        self.short_term.add_message("assistant", assistant_message)
        self._short_term_version += 1

        # 添加到长期记忆
        if save_to_long_term and self.long_term:
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
                return

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
                    if content_hash in deduplicator.seen_hashes:
                        logger.debug("跳过重复记忆: %.30s...", interaction)
                        return

                # 直接添加到长期记忆（延迟角色一致性评分）
                stored = self.long_term.add_memory(
                    content=interaction,
                    metadata=metadata,
                )
                if stored and deduplicator and content_hash:
                    deduplicator.seen_hashes.add(content_hash)

                # 更新统计
                self.optimizer.stats["total_memories_processed"] += 1
                logger.debug(
                    "保存记忆 (重要性: %.2f): %.30s...",
                    importance,
                    interaction,
                )
            else:
                # 原有逻辑
                self.long_term.add_memory(
                    content=interaction,
                    metadata={
                        "type": "conversation",
                        "importance": importance,
                    },
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

        # v3.3: 智能缓存键（考虑语义相似性）
        cache_key = query.strip().lower()[:100]  # 标准化查询

        # v3.2.1: 优化性能 - 先检查缓存
        if self.optimizer and self.optimizer.cache:
            cached_result = self.optimizer.cache.get_query_result(cache_key)
            if cached_result is not None:
                self.optimizer.stats["cache_hits"] += 1
                logger.debug("缓存命中: %.30s...", query)
                return [mem["content"] for mem in cached_result[:k]]
            self.optimizer.stats["cache_misses"] += 1

        # v3.3: 执行增强的向量搜索
        memories = self.long_term.search_memories(query, k=k)

        # v3.3: 记忆去重（基于内容相似度）
        if memories and len(memories) > 1:
            unique_memories = []
            seen_contents = set()

            for mem in memories:
                # 简单的内容指纹（前50字符）
                content_fingerprint = mem["content"][:50].strip()
                if content_fingerprint not in seen_contents:
                    unique_memories.append(mem)
                    seen_contents.add(content_fingerprint)

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
            timestamp = metadata.get("timestamp")
            if timestamp:
                try:
                    mem_time = datetime.fromisoformat(timestamp)
                    time_desc = self._get_time_description(mem_time)
                    content = f"[{time_desc}] {content}"
                except (ValueError, TypeError) as e:
                    logger.debug("解析时间戳失败: %s", e)
                    pass

            # v3.3: 添加重要性标记
            importance = metadata.get("importance", 0.5)
            if importance >= 0.8:
                content = f"⭐ {content}"  # 高重要性标记

            enhanced_memories.append(content)

        # v3.2.1: 缓存结果
        if self.optimizer and memories:
            memory_dicts = [
                {
                    "content": content,
                    "metadata": mem.get("metadata", {}),
                }
                for content, mem in zip(enhanced_memories, memories)
            ]

            if self.optimizer.cache:
                self.optimizer.cache.set_query_result(cache_key, memory_dicts)

        return enhanced_memories

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
            if (short_term_messages[i]["role"] == "user" and
                short_term_messages[i+1]["role"] == "assistant"):
                user_msg = short_term_messages[i]["content"]
                assistant_msg = short_term_messages[i+1]["content"]

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
                    if deduplicator:
                        content_hash = deduplicator.get_content_hash(content)
                        if content_hash in deduplicator.seen_hashes:
                            i += 2
                            continue
                        pending_hashes.append(content_hash)
                    contents.append(content)
                    metadatas.append(metadata)

                i += 2
            else:
                i += 1

        if not contents:
            return 0

        consolidated_count = self.long_term.add_memories(contents, metadatas)
        if consolidated_count == len(contents) and deduplicator and pending_hashes:
            deduplicator.seen_hashes.update(pending_hashes)

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
            "short_term_count": len(self.short_term.get_messages()),
            "short_term_capacity": self.short_term.k * 2,
        }

        if self.long_term and self.long_term.vectorstore:
            try:
                # 尝试获取长期记忆数量
                collection = self.long_term.vectorstore._collection
                stats["long_term_count"] = collection.count()

                # v3.3.2: 批量缓冲区状态
                stats["batch_buffer_size"] = len(self.long_term._batch_buffer)
                stats["batch_threshold"] = self.long_term._batch_size
            except (AttributeError, RuntimeError) as e:
                logger.debug("获取长期记忆统计失败: %s", e)
                stats["long_term_count"] = "未知"
                stats["batch_buffer_size"] = 0
                stats["batch_threshold"] = 0
        else:
            stats["long_term_count"] = 0
            stats["batch_buffer_size"] = 0
            stats["batch_threshold"] = 0

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
        self._short_term_version += 1
        if self.long_term:
            self.long_term.clear()
        logger.info("所有记忆已清空")

    def cleanup_cache(self) -> None:
        """清理内存缓存 (v2.28.0: 新增内存管理优化)

        清理长期记忆中的嵌入向量缓存，释放内存
        """
        if self.long_term and hasattr(self.long_term, '_embedding_cache'):
            cache_size = len(self.long_term._embedding_cache)
            if cache_size > 0:
                self.long_term._embedding_cache.clear()
                logger.info("已清理 %d 个嵌入向量缓存，释放内存", cache_size)

        # 清理批量缓冲区
        if self.long_term and hasattr(self.long_term, '_batch_buffer'):
            # 先刷新缓冲区到数据库
            if hasattr(self.long_term, 'flush_batch'):
                try:
                    flushed_count = self.long_term.flush_batch()
                    if flushed_count > 0:
                        logger.info("已刷新 %d 个批量缓冲记忆到数据库", flushed_count)
                except Exception as e:
                    logger.warning("刷新批量缓冲区失败: %s", e)

    def export_memories(self, filepath: Path) -> None:
        """
        导出记忆到文件

        Args:
            filepath: 导出文件路径
        """
        data = {
            "short_term": self.get_recent_messages(),
            "export_time": datetime.now().isoformat(),
        }

        filepath.parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        logger.info("记忆已导出到: %s", filepath)
