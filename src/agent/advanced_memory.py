"""
高级记忆系统模块

当前仅保留 CoreMemory（核心记忆）。
基于配置文件（config.user.yaml + config.dev.yaml，兼容 legacy config.yaml）中的配置。
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.config.settings import settings
from src.utils.chroma_helper import create_chroma_vectorstore, get_collection_count
from src.utils.logger import get_logger

logger = get_logger(__name__)


class CoreMemory:
    """
    核心记忆系统

    储存关于用户的重要信息（住址、爱好、喜欢的东西等）
    使用嵌入模型进行语义匹配（模糊搜索）
    """

    def __init__(self, persist_directory: Optional[str] = None, user_id: Optional[int] = None):
        """
        初始化核心记忆 (v2.29.21优化版)

        Args:
            persist_directory: 持久化目录
            user_id: 用户ID，用于创建用户特定的记忆路径
        """
        # 写入版本号：用于外部缓存失效（例如并发检索器的全局记忆缓存）
        self._write_version = 0

        if not settings.agent.is_core_mem:
            logger.info("核心记忆功能未启用")
            self.vectorstore = None
            return

        self.user_id = user_id
        self.collection_name = "core_memory"

        # 支持用户特定路径
        if persist_directory:
            persist_dir = persist_directory
        elif user_id is not None:
            persist_dir = str(
                Path(settings.data_dir) / "users" / str(user_id) / "memory" / "core_memory"
            )
        else:
            persist_dir = str(Path(settings.data_dir) / "memory" / "core_memory")

        self.persist_directory = str(Path(persist_dir))

        # 使用统一的ChromaDB初始化函数（v2.30.27: 支持本地 embedding 和缓存）
        self.vectorstore = create_chroma_vectorstore(
            collection_name=self.collection_name,
            persist_directory=self.persist_directory,
            use_local_embedding=settings.use_local_embedding,
            enable_cache=settings.enable_embedding_cache,
        )

        if self.vectorstore:
            count = get_collection_count(self.vectorstore)
            logger.info(f"核心记忆初始化完成，已有记忆: {count} 条")

    @property
    def write_version(self) -> int:
        """核心记忆写入版本号（仅在写入成功后递增）。"""
        return int(getattr(self, "_write_version", 0))

    def add_core_memory(
        self,
        content: str,
        category: str = "general",
        importance: float = 1.0,
    ) -> None:
        """
        添加核心记忆

        Args:
            content: 记忆内容
            category: 记忆类别（如：personal_info, preferences, habits）
            importance: 重要性（0.0-1.0）
        """
        if self.vectorstore is None:
            return

        metadata = {
            "category": category,
            "importance": importance,
            "timestamp": datetime.now().isoformat(),
            "type": "core_memory",
        }

        try:
            self.vectorstore.add_texts(
                texts=[content],
                metadatas=[metadata],
            )
            self._write_version += 1
            logger.info(f"添加核心记忆 [{category}]: {content[:50]}...")
        except Exception as e:
            logger.error(f"添加核心记忆失败: {e}")

    def search_core_memories(
        self,
        query: str,
        k: int = 3,
        category: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        搜索核心记忆（语义匹配）

        Args:
            query: 查询文本
            k: 返回数量
            category: 筛选类别

        Returns:
            List[Dict]: 记忆列表
        """
        if self.vectorstore is None:
            return []

        try:
            # 使用相似度搜索
            results = self.vectorstore.similarity_search_with_score(
                query, k=k * 2  # 多获取一些，后面过滤
            )

            memories = []
            for doc, score in results:
                # v2.48.5: 相似度转换（score 越小越相似）
                if (similarity := 1.0 - score) < settings.agent.mem_thresholds:
                    continue

                # 类别过滤（v2.48.5: 使用海象运算符优化）
                if category and doc.metadata.get("category") != category:
                    continue

                memories.append(
                    {
                        "content": doc.page_content,
                        "similarity": similarity,
                        "metadata": doc.metadata,
                    }
                )

                if len(memories) >= k:
                    break

            logger.debug(f"核心记忆搜索: 找到 {len(memories)} 条相关记忆")
            return memories

        except Exception as e:
            logger.error(f"核心记忆搜索失败: {e}")
            return []

    def get_all_core_memories(self) -> List[str]:
        """获取所有核心记忆"""
        if self.vectorstore is None:
            return []

        try:
            # 获取所有文档
            results = self.vectorstore.get()
            return results.get("documents", [])
        except Exception as e:
            logger.error(f"获取核心记忆失败: {e}")
            return []

    def clear_all(self) -> bool:
        """清空核心记忆（删除 collection 并重建）。"""
        if self.vectorstore is None:
            return False

        try:
            self.vectorstore.delete_collection()
            self.vectorstore = create_chroma_vectorstore(
                collection_name=self.collection_name,
                persist_directory=self.persist_directory,
                use_local_embedding=settings.use_local_embedding,
                enable_cache=settings.enable_embedding_cache,
            )
            if self.vectorstore is None:
                logger.error("核心记忆已删除，但向量库重新初始化失败")
                return False
            self._write_version += 1
            logger.info("核心记忆已清空")
            return True
        except Exception as e:
            logger.error(f"清空核心记忆失败: {e}")
            return False

    def import_records(
        self,
        records: List[Dict[str, Any]],
        *,
        overwrite: bool = False,
        batch_size: int = 128,
    ) -> int:
        """
        导入核心记忆记录（来自导出包的 advanced_memory.core_memory.items）。

        - overwrite=True 时会先清空现有 core_memory，并尽量保留原 ids
        - overwrite=False 时不清空，忽略原 ids，并写入 metadata.original_id
        """
        if self.vectorstore is None:
            return 0
        if not records:
            return 0

        if overwrite:
            if not self.clear_all():
                return 0
            if self.vectorstore is None:
                return 0

        texts: List[str] = []
        metadatas: List[Dict[str, Any]] = []
        ids: List[str] = []

        for item in records:
            if not isinstance(item, dict):
                continue
            content = item.get("content")
            if not content:
                continue
            meta = dict(item.get("metadata") or {})
            meta.setdefault("type", "core_memory")

            if overwrite:
                from uuid import uuid4

                ids.append(str(item.get("id") or uuid4().hex))
            else:
                original_id = item.get("id")
                if original_id:
                    meta.setdefault("original_id", str(original_id))

            texts.append(str(content))
            metadatas.append(meta)

        if not texts:
            return 0

        imported = 0
        batch_size = max(1, int(batch_size))

        for offset in range(0, len(texts), batch_size):
            chunk_texts = texts[offset : offset + batch_size]
            chunk_metas = metadatas[offset : offset + batch_size]
            try:
                if overwrite:
                    chunk_ids = ids[offset : offset + batch_size]
                    self.vectorstore.add_texts(
                        texts=chunk_texts, metadatas=chunk_metas, ids=chunk_ids
                    )
                else:
                    self.vectorstore.add_texts(texts=chunk_texts, metadatas=chunk_metas)
                imported += len(chunk_texts)
            except Exception as e:
                logger.error(f"导入核心记忆批次失败: {e}")

        if imported:
            self._write_version += imported
            logger.info(f"导入核心记忆完成: {imported} 条 (overwrite={overwrite})")
        return imported
