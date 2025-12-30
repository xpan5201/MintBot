"""
高级记忆系统模块 (v2.30.43优化版)

实现核心记忆、日记功能和知识库（世界书）。
基于配置文件（config.user.yaml + config.dev.yaml，兼容 legacy config.yaml）中的高级配置。

优化内容:
- 使用统一的ChromaDB初始化函数，消除代码重复
- 改进错误处理和日志记录
- 优化性能和内存使用
- v2.30.32: 增加 LLM 辅助提取情感和主题，提升准确率
- v2.30.32: 增加元数据提取（人物、地点、时间、事件）
- v2.30.40: 集成混合检索系统（向量 + BM25）
- v2.30.40: 增加重排序机制和查询扩展
- v2.30.41: 集成知识质量管理系统
- v2.30.42: 集成知识推荐系统（上下文感知推荐、主动推送、使用统计）
- v2.30.43: 集成知识图谱系统（关系建模、知识推理、图谱可视化）
- v2.30.44: 性能优化（多级缓存、异步处理、ChromaDB 调优）
"""

import time
import hashlib
import json
import re
import difflib
from threading import Lock
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.config.settings import settings
from src.utils.logger import get_logger
from src.utils.chroma_helper import create_chroma_vectorstore, get_collection_count

logger = get_logger(__name__)

_CONTENT_CATEGORY_KEYWORDS = {
    "character": ("人物", "角色", "人", "她", "他", "名字"),
    "location": ("地点", "位置", "地方", "在", "位于"),
    "item": ("物品", "东西", "道具", "装备"),
    "event": ("事件", "发生", "经历", "故事"),
}
_CHINESE_KEYWORDS_PATTERN = re.compile(r"[\u4e00-\u9fa5]{2,4}")

# v2.30.40: 导入混合检索系统
try:
    from src.agent.hybrid_retriever import HybridRetriever, Reranker, QueryExpander

    HAS_HYBRID_RETRIEVER = True
except Exception as exc:  # pragma: no cover - 环境依赖差异
    HAS_HYBRID_RETRIEVER = False
    HybridRetriever = None  # type: ignore[assignment]
    Reranker = None  # type: ignore[assignment]
    QueryExpander = None  # type: ignore[assignment]
    logger.warning("混合检索系统导入失败，将使用传统向量检索: %s", exc)

# v2.30.41: 导入知识质量管理系统
try:
    from src.agent.knowledge_quality import KnowledgeQualityManager

    HAS_QUALITY_MANAGER = True
except Exception as exc:  # pragma: no cover - 环境依赖差异
    HAS_QUALITY_MANAGER = False
    KnowledgeQualityManager = None  # type: ignore[assignment]
    logger.warning("知识质量管理系统导入失败，将跳过质量检查: %s", exc)

# v2.30.42: 导入知识推荐系统
try:
    from src.agent.knowledge_recommender import (
        KnowledgeRecommender,
        ProactiveKnowledgePusher,
        KnowledgeUsageTracker,
    )

    HAS_RECOMMENDER = True
except Exception as exc:  # pragma: no cover - 环境依赖差异
    HAS_RECOMMENDER = False
    KnowledgeRecommender = None  # type: ignore[assignment]
    ProactiveKnowledgePusher = None  # type: ignore[assignment]
    KnowledgeUsageTracker = None  # type: ignore[assignment]
    logger.warning("知识推荐系统导入失败，将跳过推荐功能: %s", exc)

# v2.30.43: 导入知识图谱系统
try:
    from src.agent.knowledge_graph import KnowledgeGraph

    HAS_KNOWLEDGE_GRAPH = True
except Exception as exc:  # pragma: no cover - 环境依赖差异
    HAS_KNOWLEDGE_GRAPH = False
    KnowledgeGraph = None  # type: ignore[assignment]
    logger.warning("知识图谱系统导入失败，将跳过图谱功能: %s", exc)

# v2.30.44: 导入性能优化器
try:
    from src.agent.performance_optimizer import (
        MultiLevelCache,
        AsyncProcessor,
    )

    HAS_PERFORMANCE_OPTIMIZER = True
except ImportError:
    HAS_PERFORMANCE_OPTIMIZER = False
    logger.debug("性能优化器未安装，将跳过性能优化功能")

# 尝试导入 LangChain LLM
try:
    from langchain_openai import ChatOpenAI

    HAS_LANGCHAIN_LLM = True
except ImportError:
    HAS_LANGCHAIN_LLM = False
    logger.debug("langchain_openai 未安装，LLM 辅助提取功能将不可用")


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
            logger.info(f"导入核心记忆完成: {imported} 条 (overwrite={overwrite})")
        return imported


class DiaryMemory:
    """
    日记功能（长期记忆）- v2.30.36 智能日记系统

    像人类写日记一样，只记录重要的事情：
    1. 重要对话（importance >= 0.6）
    2. 每日总结（自动生成）
    3. 美好瞬间（特殊情感时刻）
    4. 重要事件（包含人物、地点、事件的对话）

    长期储存对话信息，并根据用户输入的时间信息进行检索
    例如："昨天做了什么？"、"两天前吃的午饭是什么？"
    """

    def __init__(self, persist_directory: Optional[str] = None, user_id: Optional[int] = None):
        """
        初始化日记功能

        Args:
            persist_directory: 持久化目录
            user_id: 用户ID，用于创建用户特定的记忆路径
        """
        if not settings.agent.long_memory:
            logger.info("日记功能未启用")
            self.vectorstore = None
            self.diary_file = None
            return

        self.user_id = user_id
        self.collection_name = "diary_memory"

        # 支持用户特定路径
        if persist_directory:
            persist_dir = persist_directory
        elif user_id is not None:
            persist_dir = str(Path(settings.data_dir) / "users" / str(user_id) / "memory" / "diary")
        else:
            persist_dir = str(Path(settings.data_dir) / "memory" / "diary")

        self.persist_directory = str(Path(persist_dir))
        Path(self.persist_directory).mkdir(parents=True, exist_ok=True)

        # JSON 文件存储日记（便于时间检索）
        self.diary_file = Path(self.persist_directory) / "diary.json"
        if not self.diary_file.exists():
            self.diary_file.write_text("[]", encoding="utf-8")

        # 向量数据库（用于语义检索）- 使用统一的初始化函数（v2.30.27: 支持本地 embedding 和缓存）
        self.vectorstore = create_chroma_vectorstore(
            collection_name=self.collection_name,
            persist_directory=self.persist_directory,
            use_local_embedding=settings.use_local_embedding,
            enable_cache=settings.enable_embedding_cache,
        )

        if self.vectorstore:
            count = get_collection_count(self.vectorstore)
            logger.info(f"日记功能初始化完成，已有日记: {count} 条")

        # v2.30.32: 初始化 LLM（用于辅助提取）
        self.llm = None
        self.use_llm_extraction = getattr(
            settings.agent, "use_llm_extraction", False
        )  # 默认关闭，避免过度调用
        if self.use_llm_extraction and HAS_LANGCHAIN_LLM:
            try:
                self.llm = ChatOpenAI(
                    model=settings.llm.model,
                    temperature=0.0,  # 使用低温度以获得更稳定的结果
                    max_tokens=500,  # 限制 token 数量
                    api_key=settings.llm.key,
                    base_url=settings.llm.api,
                )
                logger.info("LLM 辅助提取已启用")
            except Exception as e:
                logger.warning(f"LLM 初始化失败，将使用关键词匹配: {e}")
                self.use_llm_extraction = False

        # v2.30.34: 性能优化 - 预编译情感和主题关键词字典（避免每次调用时重新创建）
        self._init_emotion_keywords()
        self._init_topic_keywords()

        # v2.30.36: 智能日记系统 - 临时对话缓存（用于每日总结）
        self.daily_conversations = []  # 当天的所有对话
        self.last_summary_date = None  # 上次总结的日期
        self.smart_diary_enabled = getattr(settings.agent, "smart_diary_enabled", True)
        self.diary_importance_threshold = getattr(settings.agent, "diary_importance_threshold", 0.6)
        self.daily_summary_enabled = getattr(settings.agent, "daily_summary_enabled", True)
        self.diary_daily_max_entries = max(
            1, int(getattr(settings.agent, "diary_daily_max_entries", 5))
        )
        self.diary_max_entries = max(1, int(getattr(settings.agent, "diary_max_entries", 500)))
        self.diary_max_days = max(1, int(getattr(settings.agent, "diary_max_days", 90)))
        self.diary_min_chars = max(1, int(getattr(settings.agent, "diary_min_chars", 10)))
        self.diary_min_interval_minutes = max(
            1, int(getattr(settings.agent, "diary_min_interval_minutes", 10))
        )
        self.diary_similarity_threshold = min(
            1.0, max(0.0, float(getattr(settings.agent, "diary_similarity_threshold", 0.9)))
        )
        self.diary_daily_highlights = max(
            1, int(getattr(settings.agent, "diary_daily_highlights", 3))
        )
        self._last_diary_ts: Optional[datetime] = None
        self._diary_cache: Optional[List[Dict[str, Any]]] = None
        self._diary_lock = Lock()

    def _init_emotion_keywords(self) -> None:
        """初始化情感关键词字典 (v2.30.34 性能优化)"""
        cls = self.__class__
        cached_keywords = getattr(cls, "_EMOTION_KEYWORDS_CACHE", None)
        if cached_keywords is not None:
            self.emotion_keywords = cached_keywords
            self.negation_words = getattr(cls, "_NEGATION_WORDS_CACHE", [])
            self.degree_words = getattr(cls, "_DEGREE_WORDS_CACHE", {})
            self.emotion_opposite = getattr(cls, "_EMOTION_OPPOSITE_CACHE", {})
            self.transition_words = getattr(cls, "_TRANSITION_WORDS_CACHE", [])
            return

        self.emotion_keywords = {
            "happy": {
                "开心": 1.0,
                "高兴": 1.0,
                "快乐": 1.0,
                "愉快": 1.0,
                "喜悦": 1.0,
                "幸福": 1.0,
                "满足": 0.8,
                "欣喜": 1.0,
                "喵~": 0.6,
                "欢乐": 0.9,
                "欣慰": 0.8,
                "舒心": 0.8,
                "畅快": 0.8,
                "哈哈": 0.8,
                "嘻嘻": 0.8,
                "呵呵": 0.6,
                "笑": 0.7,
                "哈哈哈": 0.9,
                "嘿嘿": 0.7,
                "嘿": 0.6,
                "笑了": 0.7,
                "好": 0.5,
                "不错": 0.6,
                "棒": 0.7,
                "赞": 0.7,
                "美": 0.6,
                "妙": 0.6,
                "爽": 0.7,
                "舒服": 0.6,
            },
            "sad": {
                "难过": 1.0,
                "伤心": 1.0,
                "悲伤": 1.0,
                "失落": 0.9,
                "沮丧": 0.9,
                "郁闷": 0.8,
                "不开心": 1.0,
                "痛苦": 1.0,
                "心痛": 1.0,
                "悲痛": 1.0,
                "忧伤": 0.9,
                "哀伤": 0.9,
                "凄凉": 0.8,
                "哭": 0.9,
                "呜呜": 0.8,
                "泪": 0.7,
                "眼泪": 0.8,
                "哭了": 0.9,
                "流泪": 0.8,
                "泪水": 0.8,
                "哭泣": 0.9,
                "累": 0.5,
                "疲惫": 0.6,
                "无奈": 0.6,
                "失望": 0.7,
                "绝望": 0.8,
                "心酸": 0.7,
                "委屈": 0.7,
                "孤独": 0.6,
            },
            "angry": {
                "生气": 1.0,
                "愤怒": 1.0,
                "恼火": 0.9,
                "气愤": 1.0,
                "讨厌": 0.8,
                "烦": 0.7,
                "哼": 0.6,
                "火大": 0.9,
                "气死": 1.0,
                "暴怒": 1.0,
                "发火": 0.9,
                "恼怒": 0.9,
                "愤慨": 0.9,
                "可恶": 0.8,
                "混蛋": 0.9,
                "该死": 0.9,
                "烦死": 0.8,
                "烦人": 0.7,
                "讨厌死": 0.8,
                "气人": 0.8,
                "可气": 0.8,
            },
            "anxious": {
                "担心": 1.0,
                "焦虑": 1.0,
                "紧张": 1.0,
                "不安": 0.9,
                "害怕": 1.0,
                "恐惧": 1.0,
                "忧虑": 0.9,
                "慌": 0.8,
                "怕": 0.7,
                "惊慌": 0.9,
                "恐慌": 0.9,
                "惶恐": 0.8,
                "惊恐": 0.9,
                "紧迫": 0.7,
                "压力": 0.8,
                "忐忑": 0.9,
                "慌张": 0.8,
                "慌乱": 0.8,
                "不知所措": 0.9,
                "手足无措": 0.9,
                "心慌": 0.8,
            },
            "excited": {
                "兴奋": 1.0,
                "激动": 1.0,
                "期待": 0.9,
                "迫不及待": 1.0,
                "太棒了": 1.0,
                "好棒": 0.9,
                "厉害": 0.8,
                "牛": 0.7,
                "盼望": 0.9,
                "渴望": 0.9,
                "向往": 0.8,
                "憧憬": 0.8,
                "哇": 0.7,
                "耶": 0.8,
                "赞": 0.7,
                "哇塞": 0.8,
                "天啊": 0.7,
                "太好了": 0.9,
                "真棒": 0.8,
                "酷": 0.7,
                "帅": 0.7,
                "期盼": 0.6,
                "想": 0.4,
                "希望": 0.5,
                "等不及": 0.8,
            },
        }

        self.negation_words = ["不", "没", "无", "未", "别", "莫", "勿", "毋"]

        self.degree_words = {
            "超级": 2.0,
            "非常": 2.0,
            "特别": 2.0,
            "极其": 2.0,
            "十分": 2.0,
            "太": 2.0,
            "最": 2.0,
            "极": 2.0,
            "超": 1.8,
            "巨": 1.9,
            "无比": 2.0,
            "格外": 1.9,
            "异常": 1.9,
            "很": 1.5,
            "挺": 1.5,
            "相当": 1.5,
            "颇": 1.5,
            "蛮": 1.5,
            "够": 1.4,
            "实在": 1.5,
            "真": 1.5,
            "真的": 1.5,
            "比较": 1.2,
            "还": 1.2,
            "稍微": 0.8,
            "有点": 0.8,
            "略": 0.8,
            "稍": 0.8,
            "些许": 0.7,
            "一点": 0.8,
            "点": 0.7,
        }

        self.emotion_opposite = {
            "happy": "sad",
            "sad": "happy",
            "angry": "happy",
            "anxious": "happy",
            "excited": "neutral",
        }

        self.transition_words = ["但是", "但", "可是", "不过", "然而", "却", "只是", "就是"]
        # v3.3.5: 关键词大字典只读复用，避免多实例重复构造
        setattr(cls, "_EMOTION_KEYWORDS_CACHE", self.emotion_keywords)
        setattr(cls, "_NEGATION_WORDS_CACHE", self.negation_words)
        setattr(cls, "_DEGREE_WORDS_CACHE", self.degree_words)
        setattr(cls, "_EMOTION_OPPOSITE_CACHE", self.emotion_opposite)
        setattr(cls, "_TRANSITION_WORDS_CACHE", self.transition_words)

    def _init_topic_keywords(self) -> None:
        """初始化主题关键词字典 (v2.30.34 性能优化)"""
        cls = self.__class__
        cached_topics = getattr(cls, "_TOPIC_KEYWORDS_CACHE", None)
        if cached_topics is not None:
            self.topic_keywords = cached_topics
            return

        self.topic_keywords = {
            "work": {
                "工作": 2.0,
                "项目": 2.0,
                "任务": 1.8,
                "会议": 2.0,
                "同事": 1.5,
                "老板": 1.8,
                "公司": 1.8,
                "加班": 2.0,
                "职业": 1.5,
                "业务": 1.5,
                "客户": 1.5,
                "合同": 1.8,
                "上班": 1.8,
                "下班": 1.5,
                "办公": 1.5,
                "职场": 1.5,
                "领导": 1.8,
                "部门": 1.5,
                "团队": 1.5,
                "绩效": 1.8,
                "报告": 1.5,
                "文档": 1.2,
                "邮件": 1.2,
                "电话": 1.0,
            },
            "life": {
                "生活": 2.0,
                "家": 1.8,
                "家人": 1.8,
                "父母": 1.5,
                "吃饭": 1.5,
                "睡觉": 1.5,
                "休息": 1.5,
                "购物": 1.5,
                "做饭": 1.5,
                "打扫": 1.5,
                "洗衣": 1.2,
                "家务": 1.5,
                "日常": 1.5,
                "琐事": 1.2,
                "生活琐事": 1.5,
            },
            "study": {
                "学习": 2.0,
                "考试": 2.0,
                "作业": 1.8,
                "课程": 1.8,
                "老师": 1.5,
                "同学": 1.5,
                "学校": 1.8,
                "上课": 1.8,
                "复习": 1.8,
                "预习": 1.5,
                "笔记": 1.5,
                "教材": 1.5,
                "知识": 1.5,
                "技能": 1.5,
                "培训": 1.5,
                "证书": 1.5,
            },
            "entertainment": {
                "娱乐": 2.0,
                "游戏": 1.8,
                "电影": 1.8,
                "音乐": 1.8,
                "看剧": 1.8,
                "追剧": 1.8,
                "动漫": 1.5,
                "小说": 1.5,
                "玩": 1.5,
                "逛街": 1.5,
                "旅游": 1.8,
                "旅行": 1.8,
                "聚会": 1.5,
                "派对": 1.5,
                "唱歌": 1.5,
                "跳舞": 1.5,
            },
            "health": {
                "健康": 2.0,
                "身体": 1.8,
                "生病": 1.8,
                "医院": 1.8,
                "医生": 1.5,
                "药": 1.5,
                "治疗": 1.5,
                "检查": 1.5,
                "运动": 1.8,
                "锻炼": 1.8,
                "健身": 1.8,
                "跑步": 1.5,
                "饮食": 1.5,
                "营养": 1.5,
                "睡眠": 1.5,
                "休息": 1.2,
            },
            "relationship": {
                "朋友": 2.0,
                "友情": 2.0,
                "恋爱": 2.0,
                "爱情": 2.0,
                "男友": 1.8,
                "女友": 1.8,
                "伴侣": 1.8,
                "对象": 1.8,
                "家人": 1.8,
                "亲人": 1.8,
                "关系": 1.5,
                "相处": 1.5,
                "聊天": 1.2,
                "交流": 1.2,
                "沟通": 1.5,
                "理解": 1.2,
            },
        }
        # v3.3.5: 主题关键词字典只读复用，避免多实例重复构造
        setattr(cls, "_TOPIC_KEYWORDS_CACHE", self.topic_keywords)

    def _extract_with_llm(self, content: str) -> Dict[str, Any]:
        """
        使用 LLM 提取元数据（v2.30.32: 新增）

        Args:
            content: 日记内容

        Returns:
            Dict[str, Any]: 提取的元数据，包含 emotion, topic, people, location, time, event
        """
        if not self.llm:
            return {}

        try:
            prompt = f"""请分析以下对话内容，提取以下信息（以JSON格式返回）：

对话内容：
{content}

请提取：
1. emotion（情感）：happy（开心）、sad（难过）、angry（生气）、anxious（焦虑）、excited（兴奋）、neutral（中性）之一
2. topic（主题）：work（工作）、life（生活）、study（学习）、entertainment（娱乐）、health（健康）、relationship（人际关系）、other（其他）之一
3. people（人物）：对话中提到的人物列表（如：朋友、家人、同事等）
4. location（地点）：对话中提到的地点（如：公司、家、餐厅等）
5. time（时间）：对话中提到的时间信息（如：明天、下周、昨天等）
6. event（事件）：对话中提到的重要事件（如：会议、考试、旅行等）

返回格式（JSON）：
{{
    "emotion": "happy",
    "topic": "work",
    "people": ["同事", "老板"],
    "location": "公司",
    "time": "明天",
    "event": "项目会议"
}}

如果某项信息不存在，请返回 null 或空列表。只返回 JSON，不要其他内容。"""

            response = self.llm.invoke(prompt)
            result_text = response.content.strip()

            # 提取 JSON（可能被包裹在代码块中）
            if "```json" in result_text:
                result_text = result_text.split("```json")[1].split("```")[0].strip()
            elif "```" in result_text:
                result_text = result_text.split("```")[1].split("```")[0].strip()

            result = json.loads(result_text)
            logger.debug(f"LLM 提取结果: {result}")
            return result

        except Exception as e:
            logger.warning(f"LLM 提取失败: {e}")
            return {}

    def _should_save_as_diary(
        self,
        importance: float,
        emotion: str,
        people: List[str],
        location: Optional[str],
        event: Optional[str],
        content_len: int,
        existing_happy_count: int,
    ) -> tuple[bool, str]:
        """
        判断是否应该保存为日记（v2.30.36: 智能过滤）

        像人类写日记一样，只记录重要的事情：
        1. 重要对话（importance >= 0.6）
        2. 美好瞬间（happy, excited 情感）
        3. 重要事件（包含人物、地点、事件）
        4. 特殊情感（sad, angry 等需要记录的情感）

        Args:
            importance: 重要性评分
            emotion: 情感标签
            people: 人物列表
            location: 地点
            event: 事件

        Returns:
            tuple[bool, str]: (是否保存, 保存原因)
        """
        reasons = []

        # 1. 重要对话（importance >= threshold）
        if importance >= self.diary_importance_threshold:
            reasons.append(f"重要对话(重要性:{importance:.2f})")

        # 2. 美好瞬间（happy, excited 情感）- 需有足够长度或事件信息
        if (
            emotion in ["happy", "excited"]
            and existing_happy_count < 2
            and (
                importance >= self.diary_importance_threshold
                or content_len >= max(30, self.diary_min_chars * 2)
                or people
                or location
                or event
            )
        ):
            reasons.append(f"美好瞬间({emotion})")

        # 3. 重要事件（包含人物、地点、事件）
        if (people and len(people) > 0) or location or event:
            event_info = []
            if people:
                event_info.append(f"人物:{','.join(people)}")
            if location:
                event_info.append(f"地点:{location}")
            if event:
                event_info.append(f"事件:{event}")
            reasons.append(f"重要事件({' '.join(event_info)})")

        # 4. 特殊情感（sad, angry 等需要记录的情感）
        if emotion in ["sad", "angry", "anxious"] and (
            importance >= 0.4 or content_len >= max(30, self.diary_min_chars * 2)
        ):
            reasons.append(f"特殊情感({emotion})")

        # 如果有任何一个条件满足，就保存
        should_save = len(reasons) > 0
        reason_str = " | ".join(reasons) if reasons else "不满足日记条件"

        return should_save, reason_str

    def _extract_diary_metadata(
        self,
        content: str,
        emotion: Optional[str],
        topic: Optional[str],
        importance: Optional[float],
        people: Optional[List[str]],
        location: Optional[str],
        time_info: Optional[str],
        event: Optional[str],
    ) -> Dict[str, Any]:
        """
        提取日记元数据（辅助方法，v2.48.4）

        Args:
            content: 日记内容
            emotion: 情感标签（可选）
            topic: 主题标签（可选）
            importance: 重要性评分（可选）
            people: 人物列表（可选）
            location: 地点（可选）
            time_info: 时间信息（可选）
            event: 事件（可选）

        Returns:
            Dict[str, Any]: 提取的元数据
        """
        # v2.30.32: 使用 LLM 辅助提取（如果启用）
        llm_result = {}
        if self.use_llm_extraction and self.llm:
            llm_result = self._extract_with_llm(content)

        # v2.30.32: 融合 LLM 结果和关键词匹配结果
        return {
            "emotion": emotion or llm_result.get("emotion") or self._extract_emotion(content),
            "topic": topic or llm_result.get("topic") or self._extract_topic(content),
            "importance": (
                importance if importance is not None else self._calculate_importance(content)
            ),
            "people": people or llm_result.get("people") or [],
            "location": location or llm_result.get("location"),
            "time_info": time_info or llm_result.get("time"),
            "event": event or llm_result.get("event"),
        }

    def _save_diary_to_json(
        self,
        content: str,
        timestamp: datetime,
        metadata: Dict[str, Any],
    ) -> bool:
        """
        保存日记到 JSON 文件（辅助方法，v2.48.4）

        Args:
            content: 日记内容
            timestamp: 时间戳
            metadata: 元数据字典
        """
        try:
            diaries = self._get_diaries()
            # 简单去重：最近 50 条存在同样内容则跳过
            recent_window = diaries[-50:] if len(diaries) > 50 else diaries
            for entry in reversed(recent_window):
                if entry.get("content") == content:
                    logger.debug("跳过重复日记内容（最近窗口已存在）")
                    return False
                if self._is_similar(entry.get("content", ""), content):
                    logger.debug("跳过重复日记内容（相似度过高）")
                    return False

            diary_entry = {
                "content": content,
                "timestamp": timestamp.isoformat(),
                "date": timestamp.strftime("%Y-%m-%d"),
                "time": timestamp.strftime("%H:%M:%S"),
                **metadata,  # 展开元数据
            }
            diaries.append(diary_entry)

            diaries = self._prune_diaries(diaries)

            self._write_diaries(diaries)
            return True
        except Exception as e:
            logger.error(f"添加日记到 JSON 失败: {e}")
            return False

    def _prune_diaries(self, diaries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        根据配置裁剪日记：按时间排序，限制天数与总条数。
        """
        if not diaries:
            return diaries

        # 按时间排序，保证最新在后
        def _parse_ts(entry: Dict[str, Any]) -> float:
            ts = entry.get("timestamp") or entry.get("date")
            try:
                return datetime.fromisoformat(ts).timestamp() if ts else 0.0
            except Exception:
                return 0.0

        diaries = sorted(diaries, key=_parse_ts)

        # 过滤超过保留天数的老记录
        if self.diary_max_days:
            cutoff = datetime.now() - timedelta(days=self.diary_max_days)
            diaries = [
                entry
                for entry in diaries
                if (ts := entry.get("timestamp")) and self._safe_parse_datetime(ts) >= cutoff
            ] or diaries[-self.diary_max_entries :]

        # 限制最大条数（保留最新）
        if self.diary_max_entries and len(diaries) > self.diary_max_entries:
            diaries = diaries[-self.diary_max_entries :]

        return diaries

    def _is_daily_cap_reached(self, date_str: str) -> bool:
        """
        判断某天的日记条数是否达到上限。
        """
        try:
            diaries = self._get_diaries()
            count = sum(1 for d in diaries if d.get("date") == date_str)
            return count >= self.diary_daily_max_entries
        except Exception as e:
            logger.warning(f"检查每日日记上限失败: {e}")
            return False

    def _count_daily_emotion(
        self, date_str: str, target_emotions: Optional[set[str]] = None
    ) -> int:
        """
        统计某天指定情绪的日记条数。
        """
        target_emotions = target_emotions or set()
        try:
            diaries = self._get_diaries()
            return sum(
                1
                for d in diaries
                if d.get("date") == date_str and d.get("emotion") in target_emotions
            )
        except Exception as e:
            logger.warning(f"统计日记情绪失败: {e}")
            return 0

    def _is_similar(self, existing: str, candidate: str) -> bool:
        """
        判断两段文本是否相似（用于日记去重）。
        """
        if not existing or not candidate:
            return False
        existing_norm = existing.strip()
        candidate_norm = candidate.strip()
        if not existing_norm or not candidate_norm:
            return False
        ratio = difflib.SequenceMatcher(None, existing_norm, candidate_norm).ratio()
        return ratio >= self.diary_similarity_threshold

    def _get_diaries(self) -> List[Dict[str, Any]]:
        """
        读取日记列表，带内存缓存，减少频繁 I/O。
        """
        with self._diary_lock:
            if self._diary_cache is not None:
                return list(self._diary_cache)
            try:
                diaries = json.loads(self.diary_file.read_text(encoding="utf-8"))
                self._diary_cache = diaries
                return list(diaries)
            except Exception as e:
                logger.warning(f"读取日记缓存失败: {e}")
                self._diary_cache = []
                return []

    def _write_diaries(self, diaries: List[Dict[str, Any]]) -> None:
        """
        写回日记文件并刷新缓存。
        """
        with self._diary_lock:
            self.diary_file.write_text(
                json.dumps(diaries, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            self._diary_cache = list(diaries)

    def clear_all(self) -> bool:
        """清空日记（JSON + 向量库），并重建 collection。"""
        if self.vectorstore is None or not self.diary_file:
            return False

        try:
            self._write_diaries([])
            self.vectorstore.delete_collection()
            self.vectorstore = create_chroma_vectorstore(
                collection_name=self.collection_name,
                persist_directory=self.persist_directory,
                use_local_embedding=settings.use_local_embedding,
                enable_cache=settings.enable_embedding_cache,
            )
            self.daily_conversations = []
            self.last_summary_date = None
            self._last_diary_ts = None
            logger.info("日记已清空")
            return self.vectorstore is not None
        except Exception as e:
            logger.error(f"清空日记失败: {e}")
            return False

    def import_entries(
        self,
        entries: List[Dict[str, Any]],
        *,
        overwrite: bool = False,
        batch_size: int = 128,
    ) -> int:
        """
        导入日记条目（来自导出包的 advanced_memory.diary.items）。

        说明：
        - 以 diary.json 为事实来源；导入后会重建向量库，确保语义检索可用。
        - overwrite=True 时会先清空现有日记。
        """
        if self.vectorstore is None or not self.diary_file:
            return 0
        if not entries:
            return 0

        existing = [] if overwrite else self._get_diaries()
        existing_count = len(existing)

        normalized: List[Dict[str, Any]] = []
        for raw in entries:
            if not isinstance(raw, dict):
                continue
            content = raw.get("content")
            if not content:
                continue

            ts_value = raw.get("timestamp") or ""
            ts = self._safe_parse_datetime(str(ts_value)) if ts_value else datetime.now()
            if ts == datetime.min:
                ts = datetime.now()

            people = raw.get("people") or []
            if not isinstance(people, list):
                people = []

            try:
                importance = float(raw.get("importance", 0.5) or 0.5)
            except Exception:
                importance = 0.5
            importance = max(0.0, min(1.0, importance))

            normalized.append(
                {
                    "content": str(content),
                    "timestamp": ts.isoformat(),
                    "date": ts.strftime("%Y-%m-%d"),
                    "time": ts.strftime("%H:%M:%S"),
                    "emotion": str(raw.get("emotion") or "neutral"),
                    "topic": str(raw.get("topic") or "general"),
                    "importance": importance,
                    "people": people,
                    "location": raw.get("location") or "",
                    "time_info": raw.get("time_info") or "",
                    "event": raw.get("event") or "",
                }
            )

        if not normalized:
            return 0

        diaries = existing + normalized
        diaries = self._prune_diaries(diaries)
        self._write_diaries(diaries)

        # 重建向量库，避免旧内容残留/重复
        try:
            self.vectorstore.delete_collection()
        except Exception as exc:
            logger.debug("清空日记向量库失败（可忽略）: %s", exc)

        self.vectorstore = create_chroma_vectorstore(
            collection_name=self.collection_name,
            persist_directory=self.persist_directory,
            use_local_embedding=settings.use_local_embedding,
            enable_cache=settings.enable_embedding_cache,
        )
        if self.vectorstore is None:
            logger.warning("日记向量库重建失败：已导入 JSON，但语义检索不可用")
            return len(normalized) if overwrite else max(0, len(diaries) - existing_count)

        texts: List[str] = []
        metadatas: List[Dict[str, Any]] = []
        for entry in diaries:
            content = entry.get("content", "")
            if not content:
                continue
            ts = self._safe_parse_datetime(str(entry.get("timestamp", "")))
            if ts == datetime.min:
                ts = datetime.now()
            people = entry.get("people") or []
            if not isinstance(people, list):
                people = []
            metadatas.append(
                {
                    "timestamp": ts.isoformat(),
                    "date": ts.strftime("%Y-%m-%d"),
                    "type": "diary",
                    "emotion": entry.get("emotion", "neutral"),
                    "topic": entry.get("topic", "general"),
                    "importance": entry.get("importance", 0.5),
                    "people": json.dumps(people, ensure_ascii=False) if people else "[]",
                    "location": entry.get("location") or "",
                    "time_info": entry.get("time_info") or "",
                    "event": entry.get("event") or "",
                }
            )
            texts.append(str(content))

        imported_vs = 0
        batch_size = max(1, int(batch_size))
        for offset in range(0, len(texts), batch_size):
            chunk_texts = texts[offset : offset + batch_size]
            chunk_metas = metadatas[offset : offset + batch_size]
            try:
                self.vectorstore.add_texts(texts=chunk_texts, metadatas=chunk_metas)
                imported_vs += len(chunk_texts)
            except Exception as e:
                logger.error(f"导入日记向量库批次失败: {e}")

        imported = len(diaries) if overwrite else max(0, len(diaries) - existing_count)
        logger.info(
            f"导入日记完成: json_total={len(diaries)}, vectorstore_added={imported_vs}, overwrite={overwrite}"
        )
        return imported

    @staticmethod
    def _safe_parse_datetime(value: str) -> datetime:
        try:
            return datetime.fromisoformat(value)
        except Exception:
            return datetime.min

    def _save_diary_to_vectorstore(
        self,
        content: str,
        timestamp: datetime,
        metadata: Dict[str, Any],
    ) -> None:
        """
        保存日记到向量数据库（辅助方法，v2.48.4）

        Args:
            content: 日记内容
            timestamp: 时间戳
            metadata: 元数据字典
        """
        vector_metadata = {
            "timestamp": timestamp.isoformat(),
            "date": timestamp.strftime("%Y-%m-%d"),
            "type": "diary",
            "emotion": metadata["emotion"],
            "topic": metadata["topic"],
            "importance": metadata["importance"],
            "people": (
                json.dumps(metadata["people"], ensure_ascii=False) if metadata["people"] else "[]"
            ),
            "location": metadata.get("location") or "",
            "time_info": metadata.get("time_info") or "",
            "event": metadata.get("event") or "",
        }

        try:
            self.vectorstore.add_texts(
                texts=[content],
                metadatas=[vector_metadata],
            )
            # v2.30.32: 增强日志输出
            log_msg = (
                f"添加日记: {timestamp.strftime('%Y-%m-%d %H:%M')} - "
                f"情感:{metadata['emotion']} 主题:{metadata['topic']} 重要性:{metadata['importance']:.2f}"
            )
            if metadata["people"]:
                log_msg += f" 人物:{','.join(metadata['people'])}"
            if metadata.get("location"):
                log_msg += f" 地点:{metadata['location']}"
            if metadata.get("event"):
                log_msg += f" 事件:{metadata['event']}"
            log_msg += f" - {content[:50]}..."
            logger.info(log_msg)
        except Exception as e:
            logger.error(f"添加日记到向量库失败: {e}")

    def add_diary_entry(
        self,
        content: str,
        timestamp: Optional[datetime] = None,
        emotion: Optional[str] = None,
        topic: Optional[str] = None,
        importance: Optional[float] = None,
        people: Optional[List[str]] = None,
        location: Optional[str] = None,
        time_info: Optional[str] = None,
        event: Optional[str] = None,
        force_save: bool = False,  # v2.30.36: 强制保存（用于每日总结等）
    ) -> None:
        """
        添加日记条目（v2.30.36: 智能过滤 + 每日总结）

        v2.48.4 重构优化：
        - 提取辅助方法，减少函数长度
        - 提高代码可维护性

        像人类写日记一样，只记录重要的事情：
        1. 重要对话（importance >= 0.6）
        2. 美好瞬间（happy, excited 情感）
        3. 重要事件（包含人物、地点、事件）
        4. 特殊情感（sad, angry 等需要记录的情感）

        Args:
            content: 日记内容
            timestamp: 时间戳（默认为当前时间）
            emotion: 情感标签（如：happy, sad, neutral）
            topic: 主题标签（如：工作、生活、学习）
            importance: 重要性评分（0.0-1.0）
            people: 人物列表（v2.30.32 新增）
            location: 地点（v2.30.32 新增）
            time_info: 时间信息（v2.30.32 新增）
            event: 事件（v2.30.32 新增）
            force_save: 强制保存（v2.30.36 新增，用于每日总结等）
        """
        if self.vectorstore is None or not self.diary_file:
            return

        if not content or len(content.strip()) < self.diary_min_chars:
            logger.debug("跳过日记保存：内容过短(<%d)", self.diary_min_chars)
            return

        timestamp = timestamp or datetime.now()
        date_str = timestamp.strftime("%Y-%m-%d")

        # 先提取元数据，后续过滤/统计都会用到
        metadata = self._extract_diary_metadata(
            content, emotion, topic, importance, people, location, time_info, event
        )

        # 频率限制：避免短时间内连续记录
        if (
            not force_save
            and self._last_diary_ts is not None
            and (timestamp - self._last_diary_ts).total_seconds()
            < self.diary_min_interval_minutes * 60
        ):
            logger.debug(
                "跳过日记保存：距离上次日记不足 %d 分钟",
                self.diary_min_interval_minutes,
            )
            if self.daily_summary_enabled:
                self.daily_conversations.append(
                    {
                        "content": content,
                        "timestamp": timestamp,
                        **metadata,
                    }
                )
            return

        # v2.30.36: 智能过滤 - 判断是否应该保存为日记
        if not force_save and self.smart_diary_enabled:
            should_save, reason = self._should_save_as_diary(
                importance=metadata["importance"],
                emotion=metadata["emotion"],
                people=metadata["people"],
                location=metadata.get("location"),
                event=metadata.get("event"),
                content_len=len(content),
                existing_happy_count=self._count_daily_emotion(
                    date_str, target_emotions={"happy", "excited"}
                ),
            )
            if not should_save:
                logger.debug("跳过日记保存: %s - %.30s...", reason, content)
                # 添加到临时对话缓存（用于每日总结）
                if self.daily_summary_enabled:
                    self.daily_conversations.append(
                        {
                            "content": content,
                            "timestamp": timestamp,
                            **metadata,
                        }
                    )
                return
            else:
                logger.info("保存日记: %s", reason)

        # 每日条数上限
        if self._is_daily_cap_reached(date_str):
            logger.debug("跳过日记保存：已达到每日上限 %d", self.diary_daily_max_entries)
            if self.daily_summary_enabled:
                self.daily_conversations.append(
                    {
                        "content": content,
                        "timestamp": timestamp,
                        **metadata,
                    }
                )
            return

        # v2.48.4: 使用辅助方法保存日记
        saved = self._save_diary_to_json(content, timestamp, metadata)
        if saved:
            self._save_diary_to_vectorstore(content, timestamp, metadata)
            self._last_diary_ts = timestamp
            if self.daily_summary_enabled:
                self.daily_conversations.append(
                    {
                        "content": content,
                        "timestamp": timestamp,
                        **metadata,
                    }
                )

    def generate_daily_summary(self, force: bool = False) -> Optional[str]:
        """
        生成每日总结（v2.30.36: 智能日记系统）

        在一天结束时（或手动触发），自动生成今天的对话总结并保存为日记

        Args:
            force: 强制生成总结（即使今天已经生成过）

        Returns:
            Optional[str]: 生成的总结内容，如果没有对话则返回 None
        """
        if self.vectorstore is None or not self.diary_file:
            return None

        today = datetime.now().date()

        # 检查是否已经生成过今天的总结
        if not force and self.last_summary_date == today:
            logger.debug("今天已经生成过总结，跳过")
            return None

        # 检查是否有对话需要总结
        if not self.daily_conversations:
            logger.debug("今天没有对话需要总结")
            return None

        # 统计今天的对话
        total_conversations = len(self.daily_conversations)
        emotion_counts = {}
        topic_counts = {}
        avg_importance = 0.0

        for conv in self.daily_conversations:
            emotion = conv.get("emotion", "neutral")
            topic = conv.get("topic", "other")
            importance = conv.get("importance", 0.0)

            emotion_counts[emotion] = emotion_counts.get(emotion, 0) + 1
            topic_counts[topic] = topic_counts.get(topic, 0) + 1
            avg_importance += importance

        avg_importance /= total_conversations if total_conversations > 0 else 1

        # 生成总结
        emotion_summary = ", ".join([f"{k}:{v}次" for k, v in emotion_counts.items()])
        topic_summary = ", ".join([f"{k}:{v}次" for k, v in topic_counts.items()])
        highlights = sorted(
            self.daily_conversations,
            key=lambda x: (
                x.get("importance", 0.0),
                x.get("timestamp", datetime.min),
            ),
            reverse=True,
        )[: self.diary_daily_highlights]

        highlight_lines = []
        for h in highlights:
            ts = h.get("timestamp")
            ts_str = ts.strftime("%H:%M") if isinstance(ts, datetime) else ""
            emo = h.get("emotion", "neutral")
            topic = h.get("topic", "other")
            snippet = h.get("content", "")[:60]
            highlight_lines.append(f"- {ts_str} [{emo}/{topic}] {snippet}")

        summary = (
            f"【{today.strftime('%Y年%m月%d日')} 每日总结】\n\n"
            f"今天和主人一共聊了 {total_conversations} 次天。\n\n"
            f"情感分布: {emotion_summary}\n"
            f"话题分布: {topic_summary}\n"
            f"平均重要性: {avg_importance:.2f}\n\n"
            "今天的高光时刻：\n"
            + ("\n".join(highlight_lines) if highlight_lines else "（暂无）")
            + "\n\n"
            "今天是美好的一天，期待明天继续和主人聊天喵~ 💕"
        )

        # 保存总结为日记（强制保存）
        self.add_diary_entry(
            content=summary,
            timestamp=datetime.now(),
            emotion="happy",
            topic="life",
            importance=0.8,  # 每日总结都是重要的
            force_save=True,  # 强制保存
        )

        # 清空今天的对话缓存
        self.daily_conversations = []
        self.last_summary_date = today

        logger.info(f"生成每日总结: {total_conversations} 次对话")
        return summary

    def _extract_emotion(self, content: str) -> str:
        """
        提取情感标签（v2.30.34: 性能优化 - 使用预编译的关键词字典）

        Args:
            content: 日记内容

        Returns:
            str: 情感标签（happy, sad, angry, anxious, excited, neutral）
        """
        # v2.30.31: 混合情感识别 - 识别"虽然...但是..."句式
        # 检查是否有转折词
        has_transition = False
        transition_pos = -1
        for word in self.transition_words:
            pos = content.find(word)
            if pos != -1:
                has_transition = True
                transition_pos = max(transition_pos, pos + len(word))

        # 如果有转折词，只分析转折词后面的内容
        if has_transition and transition_pos > 0:
            content = content[transition_pos:]

        # v2.30.34: 使用预编译的关键词字典（性能优化）
        emotion_keywords = self.emotion_keywords
        negation_words = self.negation_words
        degree_words = self.degree_words
        emotion_opposite = self.emotion_opposite

        # 计算每种情感的加权得分
        emotion_scores = {}
        for emotion, keywords in emotion_keywords.items():
            total_score = 0.0

            for keyword, base_weight in keywords.items():
                if keyword not in content:
                    continue

                # 找到关键词的所有位置
                start = 0
                while True:
                    pos = content.find(keyword, start)
                    if pos == -1:
                        break

                    # 检查前面是否有否定词（前3个字符内）
                    has_negation = False
                    check_start = max(0, pos - 3)
                    prefix = content[check_start:pos]
                    for neg_word in negation_words:
                        if neg_word in prefix:
                            has_negation = True
                            break

                    # 检查前面是否有程度副词（前5个字符内，增加范围以支持"非常"）
                    degree_multiplier = 1.0
                    check_start = max(0, pos - 5)
                    prefix = content[check_start:pos]
                    for degree_word, multiplier in degree_words.items():
                        if degree_word in prefix:
                            degree_multiplier = max(degree_multiplier, multiplier)

                    # 计算最终得分
                    score = base_weight * degree_multiplier

                    # 如果有否定词，情感反转
                    if has_negation:
                        # 将得分添加到相反的情感
                        opposite_emotion = emotion_opposite.get(emotion, "neutral")
                        if opposite_emotion not in emotion_scores:
                            emotion_scores[opposite_emotion] = 0.0
                        emotion_scores[opposite_emotion] += score * 0.8  # 否定后的情感强度略减
                    else:
                        # 正常情感
                        total_score += score

                    start = pos + len(keyword)

            if total_score > 0:
                emotion_scores[emotion] = emotion_scores.get(emotion, 0.0) + total_score

        # 返回得分最高的情感，如果没有匹配则返回 neutral
        if emotion_scores:
            return max(emotion_scores, key=emotion_scores.get)
        return "neutral"

    def _extract_topic(self, content: str) -> str:
        """
        提取主题标签（v2.30.34: 性能优化 - 使用预编译的关键词字典）

        Args:
            content: 日记内容

        Returns:
            str: 主题标签（work, life, study, entertainment, health, relationship, other）
        """
        # v2.30.34: 使用预编译的关键词字典（性能优化）
        topic_keywords = self.topic_keywords

        # 主题优先级（数字越小优先级越高）
        topic_priority = {
            "relationship": 1,  # 最高优先级
            "health": 2,
            "work": 3,
            "study": 4,
            "entertainment": 5,
            "life": 6,  # 最低优先级
        }

        # 计算每个主题的加权得分
        topic_scores = {}
        for topic, keywords in topic_keywords.items():
            total_score = 0.0
            for keyword, weight in keywords.items():
                if keyword in content:
                    # 计算关键词出现次数
                    count = content.count(keyword)
                    total_score += weight * count

            if total_score > 0:
                # 应用优先级加成（优先级越高，加成越大）
                priority = topic_priority.get(topic, 10)
                priority_bonus = 1.0 + (10 - priority) * 0.1  # 优先级1加成1.9，优先级6加成1.4
                topic_scores[topic] = total_score * priority_bonus

        # 返回得分最高的主题，如果没有匹配则返回 other
        if topic_scores:
            return max(topic_scores, key=topic_scores.get)
        return "other"

    def _calculate_importance(self, content: str) -> float:
        """
        计算重要性评分（v2.30.30: 增强版 - 更精细的权重和更多关键词）

        Args:
            content: 日记内容

        Returns:
            float: 重要性评分（0.0-1.0）
        """
        # 基础分数：基于内容长度（调整公式，让长消息得分更高）
        # 使用对数函数，让长度影响更平滑
        import math

        length_score = min(math.log(len(content) + 1) / 10, 0.3)  # 最多0.3分

        # 重要性关键词（带权重）
        important_keywords = {
            # 极高重要性（权重 0.25）
            "紧急": 0.25,
            "严重": 0.25,
            "危险": 0.25,
            "警告": 0.25,
            "立即": 0.25,
            "马上": 0.25,
            "赶紧": 0.25,
            # 高重要性（权重 0.20）
            "重要": 0.20,
            "关键": 0.20,
            "必须": 0.20,
            "一定": 0.20,
            "务必": 0.20,
            "千万": 0.20,
            "切记": 0.20,
            # 中重要性（权重 0.15）
            "记住": 0.15,
            "提醒": 0.15,
            "别忘": 0.15,
            "注意": 0.15,
            "小心": 0.15,
            "当心": 0.15,
            "留意": 0.15,
            # 低重要性（权重 0.10）
            "需要": 0.10,
            "应该": 0.10,
            "最好": 0.10,
            "建议": 0.10,
            "希望": 0.08,
            "想要": 0.08,
            "打算": 0.08,
        }

        # 关键词加分（累加所有匹配的关键词权重）
        keyword_score = 0.0
        for keyword, weight in important_keywords.items():
            if keyword in content:
                # 计算关键词出现次数
                count = content.count(keyword)
                keyword_score += weight * count

        # 限制关键词得分上限
        keyword_score = min(keyword_score, 0.6)  # 最多0.6分

        # 特殊事件加分
        special_events = {
            # 时间相关（权重 0.15）
            "明天": 0.15,
            "今天": 0.10,
            "下周": 0.15,
            "下月": 0.15,
            "截止": 0.20,
            "期限": 0.20,
            "日期": 0.10,
            # 人物相关（权重 0.10）
            "会议": 0.15,
            "面试": 0.20,
            "约会": 0.15,
            "聚会": 0.10,
            "生日": 0.15,
            "纪念日": 0.15,
            # 事件相关（权重 0.10）
            "考试": 0.20,
            "比赛": 0.15,
            "演出": 0.15,
            "活动": 0.10,
            "项目": 0.15,
            "任务": 0.12,
        }

        # 特殊事件加分
        event_score = 0.0
        for event, weight in special_events.items():
            if event in content:
                count = content.count(event)
                event_score += weight * count

        # 限制事件得分上限
        event_score = min(event_score, 0.2)  # 最多0.2分

        # 总分
        total_score = length_score + keyword_score + event_score

        # 归一化到 0.0-1.0
        return min(max(total_score, 0.0), 1.0)

    def search_by_time(
        self,
        time_query: str,
        k: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        根据时间查询日记

        Args:
            time_query: 时间查询（如："昨天"、"两天前"、"上周"）
            k: 返回数量

        Returns:
            List[Dict]: 日记列表
        """
        if not self.diary_file:
            return []

        # 解析时间查询
        target_date = self._parse_time_query(time_query)
        if not target_date:
            logger.warning(f"无法解析时间查询: {time_query}")
            return []

        try:
            diaries = self._get_diaries()

            # 筛选目标日期的日记
            results = []
            for diary in diaries:
                diary_date = datetime.fromisoformat(diary["timestamp"]).date()
                if diary_date == target_date:
                    results.append(diary)

            logger.debug(f"时间检索 [{time_query}]: 找到 {len(results)} 条日记")
            return results[:k]

        except Exception as e:
            logger.error(f"时间检索失败: {e}")
            return []

    def search_by_content(
        self,
        query: str,
        k: int = 3,
        emotion: Optional[str] = None,
        topic: Optional[str] = None,
        min_importance: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """
        根据内容搜索日记（语义匹配 + 元数据过滤）

        Args:
            query: 查询文本
            k: 返回数量
            emotion: 情感过滤（如：happy, sad）
            topic: 主题过滤（如：work, life）
            min_importance: 最小重要性（0.0-1.0）

        Returns:
            List[Dict]: 日记列表
        """
        if self.vectorstore is None:
            return []

        try:
            # v2.30.29: 支持元数据过滤
            filter_dict = {}
            if emotion:
                filter_dict["emotion"] = emotion
            if topic:
                filter_dict["topic"] = topic

            # 获取更多结果用于过滤（v2.48.5: 使用海象运算符优化）
            results = self.vectorstore.similarity_search_with_score(
                query, k=k * 3, filter=filter_dict or None
            )

            memories = []
            for doc, score in results:
                similarity = 1.0 - score

                # 应用阈值
                if settings.agent.is_check_memorys and similarity < settings.agent.mem_thresholds:
                    continue

                # v2.48.5: 使用海象运算符优化重要性过滤
                if (
                    min_importance is not None
                    and doc.metadata.get("importance", 0.0) < min_importance
                ):
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

            logger.debug(
                f"内容检索: 找到 {len(memories)} 条相关日记 "
                f"(情感:{emotion}, 主题:{topic}, 最小重要性:{min_importance})"
            )
            return memories

        except Exception as e:
            logger.error(f"内容检索失败: {e}")
            return []

    def search_by_emotion(
        self,
        emotion: str,
        k: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        按情感搜索日记（v2.30.29 新增）

        Args:
            emotion: 情感标签（happy, sad, angry, anxious, excited, neutral）
            k: 返回数量

        Returns:
            List[Dict]: 日记列表
        """
        if not self.diary_file:
            return []

        try:
            diaries = self._get_diaries()

            # 筛选指定情感的日记
            results = [diary for diary in diaries if diary.get("emotion") == emotion]

            # 按重要性排序
            results.sort(key=lambda x: x.get("importance", 0.0), reverse=True)

            logger.debug(f"情感检索 [{emotion}]: 找到 {len(results)} 条日记")
            return results[:k]

        except Exception as e:
            logger.error(f"情感检索失败: {e}")
            return []

    def search_by_topic(
        self,
        topic: str,
        k: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        按主题搜索日记（v2.30.29 新增）

        Args:
            topic: 主题标签（work, life, study, entertainment, health, relationship, other）
            k: 返回数量

        Returns:
            List[Dict]: 日记列表
        """
        if not self.diary_file:
            return []

        try:
            diaries = self._get_diaries()

            # 筛选指定主题的日记
            results = [diary for diary in diaries if diary.get("topic") == topic]

            # 按重要性排序
            results.sort(key=lambda x: x.get("importance", 0.0), reverse=True)

            logger.debug(f"主题检索 [{topic}]: 找到 {len(results)} 条日记")
            return results[:k]

        except Exception as e:
            logger.error(f"主题检索失败: {e}")
            return []

    def get_emotion_stats(self) -> Dict[str, int]:
        """
        获取情感统计（v2.30.29 新增）

        Returns:
            Dict: 情感统计 {emotion: count}
        """
        if not self.diary_file:
            return {}

        try:
            diaries = self._get_diaries()

            # 统计每种情感的数量
            emotion_counts = {}
            for diary in diaries:
                emotion = diary.get("emotion", "neutral")
                emotion_counts[emotion] = emotion_counts.get(emotion, 0) + 1

            return emotion_counts

        except Exception as e:
            logger.error(f"获取情感统计失败: {e}")
            return {}

    def get_topic_stats(self) -> Dict[str, int]:
        """
        获取主题统计（v2.30.29 新增）

        Returns:
            Dict: 主题统计 {topic: count}
        """
        if not self.diary_file:
            return {}

        try:
            diaries = self._get_diaries()

            # 统计每个主题的数量
            topic_counts = {}
            for diary in diaries:
                topic = diary.get("topic", "other")
                topic_counts[topic] = topic_counts.get(topic, 0) + 1

            return topic_counts

        except Exception as e:
            logger.error(f"获取主题统计失败: {e}")
            return {}

    @staticmethod
    def _parse_time_query(time_query: str) -> Optional[datetime.date]:
        """
        解析时间查询

        Args:
            time_query: 时间查询字符串

        Returns:
            datetime.date: 目标日期
        """
        today = datetime.now().date()

        # 匹配模式
        patterns = {
            r"今天|今日": 0,
            r"昨天|昨日": 1,
            r"前天": 2,
            r"(\d+)天前": lambda m: int(m.group(1)),
            r"上周|一周前": 7,
            r"(\d+)周前": lambda m: int(m.group(1)) * 7,
        }

        for pattern, days in patterns.items():
            match = re.search(pattern, time_query)
            if match:
                if callable(days):
                    days = days(match)
                return today - timedelta(days=days)

        return None


class LoreBook:
    """
    知识库（世界书）- v2.30.38 增强版

    用于给大模型添加知识，如：人物、物品、事件等
    强化 AI 的能力，也可用于强化角色扮演

    v2.30.38 新增功能：
    - 更新知识条目
    - 删除知识条目
    - 批量导入/导出
    - 统计信息
    - 智能学习（从对话、文件、MCP学习）
    """

    def __init__(self, persist_directory: Optional[str] = None, user_id: Optional[int] = None):
        """
        初始化知识库

        Args:
            persist_directory: 持久化目录
            user_id: 用户ID，用于创建用户特定的记忆路径
        """
        # 并发读写保护：质量检查等后台任务可能与主线程同时访问 JSON/缓存
        self._lock = Lock()
        # 混合检索器初始化保护：避免并发触发导致重复构建 BM25 索引
        self._hybrid_init_lock = Lock()
        # 使用次数写盘缓冲（避免每次 search 都读写 JSON + 清缓存）
        self._usage_buffer: Dict[str, int] = {}
        self._usage_pending_total: int = 0
        self._usage_flush_running: bool = False
        self._usage_last_flush: float = time.monotonic()
        self._usage_flush_interval_s: float = max(
            1.0, float(getattr(settings.agent, "lore_usage_flush_interval_s", 10.0))
        )
        self._usage_flush_max_pending: int = max(
            1, int(getattr(settings.agent, "lore_usage_flush_max_pending", 50))
        )

        if not settings.agent.lore_books:
            logger.info("知识库功能未启用")
            self.vectorstore = None
            self.json_file = None
            self._cache = None
            self.multi_cache = None
            self.async_processor = None
            return

        # 支持用户特定路径
        if persist_directory:
            persist_dir = persist_directory
        elif user_id is not None:
            persist_dir = str(
                Path(settings.data_dir) / "users" / str(user_id) / "memory" / "lore_books"
            )
        else:
            persist_dir = str(Path(settings.data_dir) / "memory" / "lore_books")

        Path(persist_dir).mkdir(parents=True, exist_ok=True)

        # v2.30.38: 添加 JSON 文件存储（用于元数据和管理）
        self.json_file = Path(persist_dir) / "lore_books.json"
        if not self.json_file.exists():
            self.json_file.write_text("[]", encoding="utf-8")

        # 使用统一的ChromaDB初始化函数（v2.30.27: 支持本地 embedding 和缓存）
        self.vectorstore = create_chroma_vectorstore(
            collection_name="lore_books",
            persist_directory=persist_dir,
            use_local_embedding=settings.use_local_embedding,
            enable_cache=settings.enable_embedding_cache,
        )

        # v2.30.39: 添加内存缓存（提升性能）
        self._cache = {
            "all_lores": None,  # 缓存所有知识
            "lore_by_id": None,  # 缓存 ID->知识 索引（性能优化：O(1) 查找）
            "statistics": None,  # 缓存统计信息
            "last_update": None,  # 最后更新时间
        }

        # v3.3.6: 记录最近一次知识库搜索命中（用于“相关知识”类的主动推送上下文）
        self._last_search_hit: Optional[Dict[str, Any]] = None

        # v2.30.40: 初始化混合检索器
        self.hybrid_retriever = None
        self.reranker = None
        self.query_expander = None

        if HAS_HYBRID_RETRIEVER:
            # 延迟初始化，在第一次搜索时构建
            self.reranker = Reranker()
            self.query_expander = QueryExpander()
            logger.info("混合检索系统已启用")

        # v2.30.41: 初始化知识质量管理器
        self.quality_manager = None
        if HAS_QUALITY_MANAGER:
            self.quality_manager = KnowledgeQualityManager()
            logger.info("知识质量管理系统已启用")

        # v2.30.42: 初始化知识推荐系统
        self.recommender = None
        self.pusher = None
        self.usage_tracker = None

        if HAS_RECOMMENDER:
            self.recommender = KnowledgeRecommender()

            persist_push_state = bool(getattr(settings.agent, "proactive_push_persist_state", True))
            configured_state_file = getattr(settings.agent, "proactive_push_state_file", None)
            state_file: Optional[Path] = None
            if persist_push_state:
                try:
                    if configured_state_file:
                        state_file = Path(str(configured_state_file))
                    else:
                        state_file = (
                            Path(settings.data_dir) / "memory" / "proactive_push_state.json"
                        )
                except Exception:
                    state_file = None
            self.pusher = ProactiveKnowledgePusher(
                push_cooldown_s=float(getattr(settings.agent, "proactive_push_cooldown_s", 300.0)),
                max_history=int(getattr(settings.agent, "proactive_push_max_history", 1000)),
                max_pushed_per_user=int(
                    getattr(settings.agent, "proactive_push_max_pushed_per_user", 500)
                ),
                max_pushes_per_day=int(getattr(settings.agent, "proactive_push_daily_limit", 10)),
                min_quality_score=float(
                    getattr(settings.agent, "proactive_push_min_quality_score", 0.5)
                ),
                min_relevance_score=float(
                    getattr(settings.agent, "proactive_push_min_relevance_score", 0.3)
                ),
                persist_state=persist_push_state,
                state_file=state_file,
            )
            self.usage_tracker = KnowledgeUsageTracker()
            logger.info("知识推荐系统已启用")

        # v2.30.43: 初始化知识图谱系统
        self.knowledge_graph = None

        if HAS_KNOWLEDGE_GRAPH and getattr(settings.agent, "knowledge_graph_enabled", True):
            self.knowledge_graph = KnowledgeGraph(
                autosave=bool(getattr(settings.agent, "knowledge_graph_autosave", True)),
                rule_max_ids_per_keyword=getattr(
                    settings.agent, "knowledge_graph_rule_max_ids_per_keyword", 200
                ),
                rule_max_keyword_links_per_node=getattr(
                    settings.agent, "knowledge_graph_rule_max_keyword_links_per_node", 12
                ),
                rule_category_anchor_count=getattr(
                    settings.agent, "knowledge_graph_rule_category_anchor_count", 2
                ),
                rule_max_relations=getattr(
                    settings.agent, "knowledge_graph_rule_max_relations", 100_000
                ),
                rule_shared_keywords_desc_limit=getattr(
                    settings.agent, "knowledge_graph_rule_shared_keywords_desc_limit", 12
                ),
                save_pretty_json=bool(
                    getattr(settings.agent, "knowledge_graph_save_pretty_json", True)
                ),
                save_sort=bool(getattr(settings.agent, "knowledge_graph_save_sort", True)),
            )
            logger.info("知识图谱系统已启用")
        elif HAS_KNOWLEDGE_GRAPH:
            logger.info("知识图谱系统已禁用（Agent.knowledge_graph_enabled=false）")

        # v2.30.44: 初始化性能优化器
        self.multi_cache = None
        self.async_processor = None

        if HAS_PERFORMANCE_OPTIMIZER:
            # 多级缓存
            self.multi_cache = MultiLevelCache(
                redis_host=getattr(settings.agent, "redis_host", "localhost"),
                redis_port=getattr(settings.agent, "redis_port", 6379),
                redis_db=getattr(settings.agent, "redis_db", 0),
                redis_password=getattr(settings.agent, "redis_password", None),
                default_ttl=3600,  # 1小时
                max_memory_items=1000,
                enable_redis=getattr(settings.agent, "redis_enabled", True),
                connect_timeout=getattr(settings.agent, "redis_connect_timeout", 2.0),
                socket_timeout=getattr(settings.agent, "redis_socket_timeout", 2.0),
                validate_connection=bool(
                    getattr(settings.agent, "redis_validate_on_startup", False)
                ),
            )

            # 异步处理器
            self.async_processor = AsyncProcessor(max_workers=4)

            logger.info("性能优化器已启用（多级缓存 + 异步处理）")

        if self.vectorstore:
            count = get_collection_count(self.vectorstore)
            logger.info(f"知识库初始化完成，已有知识: {count} 条")

    def _perform_quality_check(
        self,
        title: str,
        content: str,
        category: str,
        keywords: Optional[List[str]],
        source: str,
    ) -> None:
        """
        执行知识质量检查（辅助方法，v2.48.4）

        Args:
            title: 知识标题
            content: 知识内容
            category: 类别
            keywords: 关键词列表
            source: 来源
        """
        if not self.quality_manager:
            return

        knowledge_data = {
            "title": title,
            "content": content,
            "category": category,
            "keywords": ",".join(keywords) if keywords else "",
            "source": source,
            "timestamp": datetime.now().isoformat(),
        }

        # 获取现有知识（用于冲突检测）
        existing_knowledge = self.get_all_lores(use_cache=True)

        # 评估知识质量
        assessment = self.quality_manager.assess_knowledge(knowledge_data, existing_knowledge)

        # 记录评估结果
        if not assessment["is_valid"]:
            logger.warning(f"知识验证失败: {assessment['issues']}")

        if assessment["has_conflicts"]:
            logger.warning(f"检测到知识冲突: {len(assessment['conflicts'])} 个")

        if assessment["quality_score"] < 0.3:
            logger.warning(f"知识质量较低: {assessment['quality_score']:.2f}")

        logger.info(f"知识质量评分: {assessment['quality_score']:.2f}")

    # ==================== 知识图谱增量同步（v2.30.43+ 增强） ====================

    def _kg_auto_update_enabled(self) -> bool:
        if not self.knowledge_graph:
            return False
        return bool(getattr(settings.agent, "knowledge_graph_auto_update", True))

    def _kg_submit(self, func, *args, **kwargs) -> None:
        """按配置选择同步/异步执行知识图谱更新任务。"""
        if not self.knowledge_graph:
            return

        if (
            getattr(settings.agent, "knowledge_graph_auto_update_async", True)
            and self.async_processor
        ):
            try:
                self.async_processor.submit(func, *args, **kwargs)
                return
            except Exception as exc:
                logger.debug("提交知识图谱后台任务失败，回退为同步执行: %s", exc)

        try:
            func(*args, **kwargs)
        except Exception as exc:
            logger.debug("知识图谱增量更新失败（可忽略）: %s", exc)

    def _kg_upsert_entry(self, entry: Dict[str, Any]) -> None:
        if not self._kg_auto_update_enabled() or not self.knowledge_graph:
            return

        update_edges = bool(getattr(settings.agent, "knowledge_graph_auto_update_edges", True))

        def _do() -> None:
            self.knowledge_graph.upsert_knowledge_entry(entry, update_edges=update_edges)

        self._kg_submit(_do)

    def _kg_upsert_entries(self, entries: List[Dict[str, Any]]) -> None:
        if not self._kg_auto_update_enabled() or not self.knowledge_graph or not entries:
            return

        update_edges = bool(getattr(settings.agent, "knowledge_graph_auto_update_edges", True))

        def _do() -> None:
            self.knowledge_graph.upsert_knowledge_entries(entries, update_edges=update_edges)

        self._kg_submit(_do)

    def _kg_delete_node(self, lore_id: str) -> None:
        if not self._kg_auto_update_enabled() or not self.knowledge_graph or not lore_id:
            return

        def _do() -> None:
            self.knowledge_graph.remove_knowledge_node(str(lore_id))

        self._kg_submit(_do)

    def _kg_delete_nodes(self, lore_ids: List[str]) -> None:
        if not self._kg_auto_update_enabled() or not self.knowledge_graph or not lore_ids:
            return

        def _do() -> None:
            self.knowledge_graph.remove_knowledge_nodes([str(i) for i in lore_ids if i])

        self._kg_submit(_do)

    def _create_lore_metadata(
        self,
        lore_id: str,
        title: str,
        category: str,
        keywords: Optional[List[str]],
        source: str,
    ) -> Dict[str, Any]:
        """
        创建知识元数据（辅助方法，v2.48.4）

        Args:
            lore_id: 知识ID
            title: 知识标题
            category: 类别
            keywords: 关键词列表
            source: 来源

        Returns:
            Dict[str, Any]: 元数据字典
        """
        return {
            "id": lore_id,
            "title": title,
            "category": category,
            "keywords": ",".join(keywords) if keywords else "",
            "source": source,
            "timestamp": datetime.now().isoformat(),
            "update_count": 0,
            "usage_count": 0,
            "positive_feedback": 0,
            "negative_feedback": 0,
        }

    def add_lore(
        self,
        title: str,
        content: str,
        category: str = "general",
        keywords: Optional[List[str]] = None,
        source: str = "manual",  # v2.30.38: 添加来源标记
        skip_quality_check: bool = False,  # v2.30.41: 是否跳过质量检查
    ) -> Optional[str]:
        """
        添加知识条目 - v2.30.41 增强版

        v2.48.4 重构优化：
        - 提取辅助方法，减少函数长度
        - 提高代码可维护性

        Args:
            title: 知识标题
            content: 知识内容
            category: 类别（如：character, item, event, location, general）
            keywords: 关键词列表
            source: 来源（manual, conversation, file, mcp）
            skip_quality_check: 是否跳过质量检查

        Returns:
            str: 知识ID，失败返回 None
        """
        if self.vectorstore is None:
            return None

        # v2.48.4: 使用辅助方法进行质量检查
        if not skip_quality_check:
            # 质量检查只产生告警/评分，不影响写入结果；放到后台避免阻塞主流程
            if self.async_processor:
                try:
                    self.async_processor.submit(
                        self._perform_quality_check,
                        title,
                        content,
                        category,
                        keywords,
                        source,
                    )
                except Exception as exc:
                    logger.debug("提交质量检查任务失败，回退为同步执行: %s", exc)
                    self._perform_quality_check(title, content, category, keywords, source)
            else:
                self._perform_quality_check(title, content, category, keywords, source)

        # v2.30.38: 生成唯一ID
        import uuid

        lore_id = str(uuid.uuid4())

        # v2.48.4: 使用辅助方法创建元数据
        metadata = self._create_lore_metadata(lore_id, title, category, keywords, source)

        # 组合标题和内容
        full_content = f"【{title}】\n{content}"

        try:
            # 添加到向量数据库
            self.vectorstore.add_texts(
                texts=[full_content],
                metadatas=[metadata],
                ids=[lore_id],
            )

            # v2.30.38: 保存到 JSON 文件
            self._save_to_json(
                {
                    "id": lore_id,
                    "title": title,
                    "content": content,
                    "category": category,
                    "keywords": keywords or [],
                    "source": source,
                    "timestamp": metadata["timestamp"],
                    "update_count": 0,
                    "usage_count": 0,
                    "positive_feedback": 0,
                    "negative_feedback": 0,
                }
            )

            # v2.30.39: 清除缓存
            self._invalidate_cache()

            # v2.30.43+: 知识图谱增量同步（避免手动重建）
            self._kg_upsert_entry(
                {
                    "id": lore_id,
                    "title": title,
                    "category": category,
                    "keywords": keywords or [],
                }
            )

            logger.info(f"添加知识 [{category}] [{source}]: {title}")
            return lore_id

        except Exception as e:
            logger.error(f"添加知识失败: {e}")
            return None

    def close(self) -> None:
        """显式清理资源（线程池、缓存等）。"""
        try:
            # 最终刷盘：把尚未落盘的 usage_count 写回 JSON
            self._flush_usage_counts()

            # 最终刷盘：知识图谱（autosave=false 时尤为重要）
            if self.knowledge_graph:
                try:
                    self.knowledge_graph.flush()
                except Exception as exc:
                    logger.debug("知识图谱 flush 失败（可忽略）: %s", exc)

            if self.async_processor:
                self.async_processor.close()
        except Exception as exc:
            logger.debug("关闭异步处理器失败（可忽略）: %s", exc)
        finally:
            self.async_processor = None

        try:
            if self.multi_cache:
                close_fn = getattr(self.multi_cache, "close", None)
                if callable(close_fn):
                    close_fn()
        except Exception as exc:
            logger.debug("关闭多级缓存失败（可忽略）: %s", exc)
        finally:
            self.multi_cache = None

    def update_lore(
        self,
        lore_id: str,
        title: Optional[str] = None,
        content: Optional[str] = None,
        category: Optional[str] = None,
        keywords: Optional[List[str]] = None,
    ) -> bool:
        """
        更新知识条目 - v2.30.38 新增

        Args:
            lore_id: 知识ID
            title: 新标题（可选）
            content: 新内容（可选）
            category: 新类别（可选）
            keywords: 新关键词（可选）

        Returns:
            bool: 是否成功
        """
        if self.vectorstore is None:
            return False

        try:
            # 从 JSON 文件读取原始数据
            lore_data = self._get_lore_by_id(lore_id)
            if not lore_data:
                logger.warning(f"知识ID不存在: {lore_id}")
                return False

            # 更新字段
            if title is not None:
                lore_data["title"] = title
            if content is not None:
                lore_data["content"] = content
            if category is not None:
                lore_data["category"] = category
            if keywords is not None:
                lore_data["keywords"] = keywords

            lore_data["update_count"] = lore_data.get("update_count", 0) + 1
            lore_data["last_update"] = datetime.now().isoformat()

            # 删除旧的向量
            self.vectorstore.delete(ids=[lore_id])

            # 添加新的向量
            full_content = f"【{lore_data['title']}】\n{lore_data['content']}"
            metadata = {
                "id": lore_id,
                "title": lore_data["title"],
                "category": lore_data["category"],
                "keywords": ",".join(lore_data["keywords"]) if lore_data["keywords"] else "",
                "source": lore_data.get("source", "manual"),
                "timestamp": lore_data["timestamp"],
                "update_count": lore_data["update_count"],
                "last_update": lore_data["last_update"],
            }

            self.vectorstore.add_texts(
                texts=[full_content],
                metadatas=[metadata],
                ids=[lore_id],
            )

            # 更新 JSON 文件
            self._update_json(lore_data)

            # v2.30.39: 清除缓存
            self._invalidate_cache()

            # v2.30.43+: 知识图谱增量同步
            self._kg_upsert_entry(
                {
                    "id": lore_id,
                    "title": lore_data.get("title", ""),
                    "category": lore_data.get("category", "general"),
                    "keywords": lore_data.get("keywords", []) or [],
                }
            )

            logger.info(f"更新知识: {lore_data['title']}")
            return True

        except Exception as e:
            logger.error(f"更新知识失败: {e}")
            return False

    def delete_lore(self, lore_id: str) -> bool:
        """
        删除知识条目 - v2.30.38 新增

        Args:
            lore_id: 知识ID

        Returns:
            bool: 是否成功
        """
        if self.vectorstore is None:
            return False

        try:
            # 从向量数据库删除
            self.vectorstore.delete(ids=[lore_id])

            # 从 JSON 文件删除
            self._delete_from_json(lore_id)

            # v2.30.39: 清除缓存
            self._invalidate_cache()

            # v2.30.43+: 知识图谱增量同步
            self._kg_delete_node(lore_id)

            logger.info(f"删除知识: {lore_id}")
            return True

        except Exception as e:
            logger.error(f"删除知识失败: {e}")
            return False

    def _ensure_hybrid_retriever(self):
        """
        确保混合检索器已初始化 (v2.30.40)

        延迟初始化，避免启动时加载所有文档
        """
        if not HAS_HYBRID_RETRIEVER or self.hybrid_retriever is not None:
            return

        try:
            with self._hybrid_init_lock:
                if self.hybrid_retriever is not None:
                    return

                # 获取所有文档
                all_lores = self.get_all_lores(use_cache=True)

                if all_lores:
                    # 构建混合检索器
                    self.hybrid_retriever = HybridRetriever(
                        vectorstore=self.vectorstore,
                        documents=all_lores,
                        query_expander=self.query_expander,
                    )
                    logger.info(f"混合检索器初始化完成，文档数量: {len(all_lores)}")
        except Exception as e:
            logger.error(f"混合检索器初始化失败: {e}")

    def _search_with_hybrid_retriever(
        self,
        query: str,
        k: int,
        category: Optional[str],
        use_rerank: bool,
        context: Optional[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        使用混合检索器搜索（辅助方法，v2.48.4）

        Args:
            query: 查询文本
            k: 返回数量
            category: 筛选类别
            use_rerank: 是否使用重排序
            context: 上下文信息

        Returns:
            List[Dict[str, Any]]: 搜索结果
        """
        # 确保混合检索器已初始化
        self._ensure_hybrid_retriever()

        if not self.hybrid_retriever:
            return []

        # 混合检索
        results = self.hybrid_retriever.search(
            query=query,
            k=k,
            alpha=0.6,  # 向量检索权重 60%，BM25 权重 40%
            category=category,
            threshold=settings.agent.books_thresholds,
        )

        # 重排序
        if use_rerank and self.reranker and results:
            results = self.reranker.rerank(
                results=results,
                query=query,
                context=context or {},
            )

        # 转换格式
        lores = []
        for result in results:
            lores.append(
                {
                    "content": result.get("content", ""),
                    "similarity": result.get("final_score", result.get("score", 0.0)),
                    "metadata": result.get("metadata", {}),
                }
            )

        logger.debug(f"混合检索完成: 找到 {len(lores)} 条相关知识")
        return lores

    def _search_with_vector_store(
        self,
        query: str,
        k: int,
        category: Optional[str],
    ) -> List[Dict[str, Any]]:
        """
        使用传统向量检索（辅助方法，v2.48.4）

        Args:
            query: 查询文本
            k: 返回数量
            category: 筛选类别

        Returns:
            List[Dict[str, Any]]: 搜索结果
        """
        results = self.vectorstore.similarity_search_with_score(query, k=k * 2)

        lores = []
        for doc, score in results:
            similarity = 1.0 - score

            # 应用阈值
            if similarity < settings.agent.books_thresholds:
                continue

            # 类别过滤
            if category and doc.metadata.get("category") != category:
                continue

            lores.append(
                {
                    "content": doc.page_content,
                    "similarity": similarity,
                    "metadata": doc.metadata,
                }
            )

            if len(lores) >= k:
                break

        logger.debug(f"向量检索完成: 找到 {len(lores)} 条相关知识")
        return lores

    @staticmethod
    def _summarize_search_hit(lores: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """
        提取最近一次搜索的首条命中（轻量摘要），用于后续“相关知识”类主动推送上下文。

        search_lore 返回的是 vectorstore 结构：{"content": ..., "similarity": ..., "metadata": {...}}
        """
        if not lores:
            return None
        first = lores[0]
        if not isinstance(first, dict):
            return None

        meta = first.get("metadata") or {}
        if not isinstance(meta, dict):
            meta = {}

        lore_id = meta.get("id") or first.get("id")
        title = meta.get("title") or first.get("title")
        category = meta.get("category") or first.get("category")
        source = meta.get("source") or first.get("source")

        raw_keywords = meta.get("keywords") or first.get("keywords") or []
        if isinstance(raw_keywords, str):
            keywords = [p.strip() for p in raw_keywords.split(",") if p.strip()]
        elif isinstance(raw_keywords, list):
            keywords = [str(k).strip() for k in raw_keywords if str(k).strip()]
        else:
            keywords = []

        similarity = first.get("similarity")
        try:
            similarity_f = float(similarity) if similarity is not None else None
        except Exception:
            similarity_f = None

        hit: Dict[str, Any] = {
            "id": str(lore_id) if lore_id is not None else None,
            "title": str(title) if title is not None else "",
            "category": str(category) if category is not None else "",
            "source": str(source) if source is not None else "",
            "keywords": keywords,
        }
        if similarity_f is not None:
            hit["similarity"] = similarity_f
        return hit

    def get_last_search_hit(self) -> Optional[Dict[str, Any]]:
        hit = getattr(self, "_last_search_hit", None)
        return dict(hit) if isinstance(hit, dict) else None

    def search_lore(
        self,
        query: str,
        k: Optional[int] = None,
        category: Optional[str] = None,
        use_hybrid: bool = True,
        use_rerank: bool = True,
        context: Optional[Dict[str, Any]] = None,
        use_cache: bool = True,  # v2.30.44: 是否使用缓存
    ) -> List[Dict[str, Any]]:
        """
        搜索知识库 (v2.30.44 增强版)

        v2.48.4 重构优化：
        - 提取辅助方法，减少函数长度
        - 提高代码可维护性

        Args:
            query: 查询文本
            k: 返回数量（默认使用 scan_depth）
            category: 筛选类别
            use_hybrid: 是否使用混合检索（默认 True）
            use_rerank: 是否使用重排序（默认 True）
            context: 上下文信息（用于重排序）
            use_cache: 是否使用缓存（默认 True）

        Returns:
            List[Dict]: 知识列表
        """
        if self.vectorstore is None:
            return []

        k = k or settings.agent.scan_depth

        # v2.30.44: 尝试从缓存获取
        # 注意：query 可能很长，直接拼接会导致缓存 key 过大/内存放大；这里使用 hash 固定长度
        query_hash = hashlib.md5(str(query).encode("utf-8")).hexdigest()
        # 混合检索的查询扩展开关会改变检索结果，需纳入缓存 key（避免切换配置后命中旧缓存）。
        qe = False
        if use_hybrid and HAS_HYBRID_RETRIEVER:
            qe = bool(getattr(self.query_expander, "enabled", False))

        # 缓存 key 必须覆盖所有“影响结果”的参数：阈值/重排序上下文等
        try:
            thr_i = int(round(float(settings.agent.books_thresholds) * 1000))
        except Exception:
            thr_i = 0

        ctx_hash = "0"
        if use_hybrid and use_rerank and HAS_HYBRID_RETRIEVER and isinstance(context, dict):
            try:
                topic_cf = str(context.get("topic", "") or "").strip().casefold()
                raw_keywords = context.get("keywords", [])
                if isinstance(raw_keywords, list):
                    kw_set = {
                        str(k).strip().casefold() for k in raw_keywords[:64] if str(k).strip()
                    }
                else:
                    kw_set = set()

                kw_sorted = sorted(kw_set)
                sig = f"{topic_cf}|{','.join(kw_sorted)[:512]}"
                ctx_hash = hashlib.md5(sig.encode("utf-8")).hexdigest()
            except Exception:
                ctx_hash = "0"

        cache_key = f"search:{query_hash}:{k}:{category}:{use_hybrid}:{use_rerank}:{int(qe)}:{thr_i}:{ctx_hash}"
        if use_cache and self.multi_cache:
            cached_results = self.multi_cache.get(cache_key, prefix="lorebook")
            if cached_results is not None:
                logger.debug(
                    "从缓存获取搜索结果: query_hash=%s query=%.80s",
                    query_hash,
                    query,
                )
                return cached_results

        try:
            # v2.48.4: 使用辅助方法进行检索
            if use_hybrid and HAS_HYBRID_RETRIEVER:
                lores = self._search_with_hybrid_retriever(query, k, category, use_rerank, context)
            else:
                lores = self._search_with_vector_store(query, k, category)

            # 更新使用次数
            self._update_usage_count(lores)

            # v3.3.6: 记录最近命中，供主动推送“相关知识”触发使用
            try:
                self._last_search_hit = self._summarize_search_hit(lores)
            except Exception:
                self._last_search_hit = None

            # v2.30.44: 保存到缓存
            if use_cache and self.multi_cache:
                self.multi_cache.set(cache_key, lores, ttl=600, prefix="lorebook")

            return lores

        except Exception as e:
            logger.error(f"知识库搜索失败: {e}")
            self._last_search_hit = None
            return []

    def _update_usage_count(self, lores: List[Dict[str, Any]]):
        """
        更新知识使用次数 (v2.30.40)

        Args:
            lores: 知识列表
        """
        if not lores or self.json_file is None:
            return

        # 统计本次命中的知识 ID（通常 k 很小，避免 O(n^2) 扫描）
        increments: Dict[str, int] = {}
        for lore in lores:
            lore_id = None
            try:
                lore_id = lore.get("metadata", {}).get("id")  # vectorstore 返回结构
            except Exception:
                lore_id = None
            lore_id = lore_id or lore.get("id")
            if lore_id:
                lore_id = str(lore_id)
                increments[lore_id] = increments.get(lore_id, 0) + 1

        if not increments:
            return

        should_flush = False
        now = time.monotonic()
        with self._lock:
            # 将使用次数增量同步到混合检索器的内存文档元数据，避免重排序的 usage 维度长期为 0。
            try:
                if self.hybrid_retriever and hasattr(
                    self.hybrid_retriever, "apply_usage_increments"
                ):
                    self.hybrid_retriever.apply_usage_increments(increments)  # type: ignore[call-arg]
            except Exception:
                pass
            for lore_id, delta in increments.items():
                self._usage_buffer[lore_id] = self._usage_buffer.get(lore_id, 0) + int(delta)
                self._usage_pending_total += int(delta)

            if (
                not self._usage_flush_running
                and self._usage_pending_total > 0
                and (
                    self._usage_pending_total >= self._usage_flush_max_pending
                    or (now - self._usage_last_flush) >= self._usage_flush_interval_s
                )
            ):
                self._usage_flush_running = True
                should_flush = True

        if not should_flush:
            return

        try:
            if self.async_processor:
                self.async_processor.submit(self._flush_usage_counts)
            else:
                self._flush_usage_counts()
        except Exception as e:
            with self._lock:
                self._usage_flush_running = False
            logger.warning(f"提交使用次数刷新任务失败: {e}")

    def _flush_usage_counts(self) -> None:
        """
        将累积的 usage_count 写回 JSON（后台/收尾使用）。

        设计目标：
        - 不在每次 search 时写盘
        - flush 失败不丢数据（回填缓冲）
        - 与 add/update/delete 等写操作共享同一把锁，避免并发 JSON 损坏/丢更新
        """
        if self.json_file is None:
            with self._lock:
                self._usage_flush_running = False
            return

        pending: Dict[str, int] = {}
        with self._lock:
            if not self._usage_buffer:
                self._usage_flush_running = False
                return
            pending = dict(self._usage_buffer)
            self._usage_buffer.clear()
            self._usage_pending_total = 0

        try:
            updated = False
            with self._lock:
                records = self._read_json_records_unlocked()
                if not records:
                    self._usage_last_flush = time.monotonic()
                    return

                by_id = {str(r.get("id")): r for r in records if r.get("id")}
                for lore_id, delta in pending.items():
                    record = by_id.get(str(lore_id))
                    if record is None:
                        continue
                    try:
                        record["usage_count"] = int(record.get("usage_count", 0)) + int(delta)
                    except Exception:
                        record["usage_count"] = int(delta)
                    updated = True

                if updated:
                    self._write_json_records_unlocked(records)
                self._usage_last_flush = time.monotonic()

        except Exception as e:
            # 写盘失败：回填缓冲，避免丢失
            with self._lock:
                for lore_id, delta in pending.items():
                    self._usage_buffer[lore_id] = self._usage_buffer.get(lore_id, 0) + int(delta)
                    self._usage_pending_total += int(delta)
            logger.warning(f"刷新使用次数失败: {e}")
        finally:
            with self._lock:
                self._usage_flush_running = False

    def get_all_lores(self, use_cache: bool = True) -> List[Dict[str, Any]]:
        """
        获取所有知识条目 - v2.30.44 增强版（支持多级缓存）

        Args:
            use_cache: 是否使用缓存（默认 True）

        Returns:
            List[Dict]: 所有知识列表
        """
        if self.json_file is None or not self.json_file.exists():
            return []

        def _build_lore_by_id(lores: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
            result: Dict[str, Dict[str, Any]] = {}
            for lore in lores:
                if not isinstance(lore, dict):
                    continue
                lore_id = lore.get("id")
                if lore_id:
                    result[str(lore_id)] = lore
            return result

        # v2.30.44: 尝试从多级缓存获取
        if use_cache and self.multi_cache:
            cached_data = self.multi_cache.get("all_lores", prefix="lorebook")
            if cached_data is not None:
                logger.debug("从多级缓存获取所有知识")
                if self._cache is not None:
                    self._cache["all_lores"] = cached_data
                    self._cache["lore_by_id"] = _build_lore_by_id(cached_data)
                    self._cache["last_update"] = datetime.now()
                return cached_data

        # v2.30.39: 使用本地缓存
        if use_cache and self._cache and self._cache["all_lores"] is not None:
            return self._cache["all_lores"]

        try:
            data = self._read_json_records()

            # v2.30.44: 保存到多级缓存
            if use_cache and self.multi_cache:
                self.multi_cache.set("all_lores", data, ttl=300, prefix="lorebook")  # 5分钟

            # 更新本地缓存
            if self._cache is not None:
                self._cache["all_lores"] = data
                self._cache["lore_by_id"] = _build_lore_by_id(data)
                self._cache["last_update"] = datetime.now()

            return data
        except Exception as e:
            logger.error(f"读取知识库失败: {e}")
            return []

    def get_lore_by_id(self, lore_id: str) -> Optional[Dict[str, Any]]:
        """
        根据ID获取知识条目 - v2.30.38 新增

        Args:
            lore_id: 知识ID

        Returns:
            Dict: 知识数据，不存在返回 None
        """
        return self._get_lore_by_id(lore_id)

    def get_statistics(self, use_cache: bool = True) -> Dict[str, Any]:
        """
        获取知识库统计信息 - v2.30.44 增强版（支持多级缓存）

        Args:
            use_cache: 是否使用缓存（默认 True）

        Returns:
            Dict: 统计信息
        """
        # v2.30.44: 尝试从多级缓存获取
        if use_cache and self.multi_cache:
            cached_stats = self.multi_cache.get("statistics", prefix="lorebook")
            if cached_stats is not None:
                logger.debug("从多级缓存获取统计信息")
                return cached_stats

        # v2.30.39: 使用本地缓存
        if use_cache and self._cache and self._cache["statistics"] is not None:
            return self._cache["statistics"]

        all_lores = self.get_all_lores(use_cache=use_cache)

        if not all_lores:
            return {
                "total": 0,
                "by_category": {},
                "by_source": {},
                "recent_count": 0,
            }

        # 按类别统计
        by_category = {}
        for lore in all_lores:
            category = lore.get("category", "general")
            by_category[category] = by_category.get(category, 0) + 1

        # 按来源统计
        by_source = {}
        for lore in all_lores:
            source = lore.get("source", "manual")
            by_source[source] = by_source.get(source, 0) + 1

        # 最近7天新增数量
        from datetime import timedelta

        seven_days_ago = datetime.now() - timedelta(days=7)
        recent_count = 0
        for lore in all_lores:
            timestamp_str = lore.get("timestamp", "")
            if timestamp_str:
                try:
                    timestamp = datetime.fromisoformat(timestamp_str)
                    if timestamp >= seven_days_ago:
                        recent_count += 1
                except (ValueError, TypeError) as e:
                    # 忽略无效的时间戳格式
                    logger.debug(f"无效的时间戳格式: {timestamp_str}, 错误: {e}")
                    pass

        stats = {
            "total": len(all_lores),
            "by_category": by_category,
            "by_source": by_source,
            "recent_count": recent_count,
        }

        # v2.30.44: 保存到多级缓存
        if use_cache and self.multi_cache:
            self.multi_cache.set("statistics", stats, ttl=300, prefix="lorebook")  # 5分钟

        # 更新本地缓存
        if self._cache is not None:
            self._cache["statistics"] = stats

        return stats

    def export_to_json(self, filepath: str) -> bool:
        """
        导出知识库到 JSON 文件 - v2.30.38 新增

        Args:
            filepath: 导出文件路径

        Returns:
            bool: 是否成功
        """
        try:
            all_lores = self.get_all_lores()
            Path(filepath).write_text(
                json.dumps(all_lores, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            logger.info(f"导出知识库成功: {filepath} ({len(all_lores)} 条)")
            return True
        except Exception as e:
            logger.error(f"导出知识库失败: {e}")
            return False

    def import_from_json(self, filepath: str, overwrite: bool = False) -> int:
        """
        从 JSON 文件导入知识库 - v2.30.38 新增

        Args:
            filepath: 导入文件路径
            overwrite: 是否覆盖已存在的知识

        Returns:
            int: 成功导入的数量
        """
        try:
            data = json.loads(Path(filepath).read_text(encoding="utf-8"))
            if not isinstance(data, list):
                logger.error("导入文件格式错误：应该是列表")
                return 0

            imported_count = 0
            for lore in data:
                # 检查必需字段
                if "title" not in lore or "content" not in lore:
                    logger.warning(f"跳过无效条目: {lore}")
                    continue

                # 检查是否已存在
                lore_id = lore.get("id")
                if lore_id and not overwrite:
                    existing = self._get_lore_by_id(lore_id)
                    if existing:
                        logger.debug(f"跳过已存在的知识: {lore['title']}")
                        continue

                # 添加知识
                result = self.add_lore(
                    title=lore["title"],
                    content=lore["content"],
                    category=lore.get("category", "general"),
                    keywords=lore.get("keywords", []),
                    source=lore.get("source", "import"),
                )

                if result:
                    imported_count += 1

            logger.info(f"导入知识库成功: {filepath} ({imported_count} 条)")
            return imported_count

        except Exception as e:
            logger.error(f"导入知识库失败: {e}")
            return 0

    def import_records(
        self,
        records: List[Dict[str, Any]],
        *,
        overwrite: bool = False,
        batch_size: int = 128,
    ) -> int:
        """
        导入知识库记录（来自导出包的 advanced_memory.lore_book.items）。

        - overwrite=True 时会先清空现有知识库，并尽量保留原 ids
        - overwrite=False 时不清空，若 id 已存在则跳过
        """
        if self.vectorstore is None or self.json_file is None:
            return 0
        if not records:
            return 0

        if overwrite:
            self.clear_all()

        existing_ids: set[str] = set()
        if not overwrite:
            try:
                existing = self._read_json_records()
                existing_ids = {str(item.get("id")) for item in existing if item.get("id")}
            except Exception:
                existing_ids = set()

        from uuid import uuid4

        now_iso = datetime.now().isoformat()
        json_records: List[Dict[str, Any]] = []
        texts: List[str] = []
        metadatas: List[Dict[str, Any]] = []
        ids: List[str] = []

        for lore in records:
            if not isinstance(lore, dict):
                continue
            title = lore.get("title")
            content = lore.get("content")
            if not title or not content:
                continue

            lore_id = str(lore.get("id") or uuid4().hex)
            if not overwrite and lore_id in existing_ids:
                continue

            category = str(lore.get("category") or "general")
            keywords = lore.get("keywords") or []
            if not isinstance(keywords, list):
                keywords = [str(keywords)]
            source = str(lore.get("source") or "import")
            timestamp = str(lore.get("timestamp") or now_iso)

            def _to_int(value: Any, default: int = 0) -> int:
                try:
                    return int(value)
                except Exception:
                    return int(default)

            update_count = _to_int(lore.get("update_count", 0))
            usage_count = _to_int(lore.get("usage_count", 0))
            positive_feedback = _to_int(lore.get("positive_feedback", 0))
            negative_feedback = _to_int(lore.get("negative_feedback", 0))

            metadata = {
                "id": lore_id,
                "title": str(title),
                "category": category,
                "keywords": ",".join([str(k) for k in keywords]) if keywords else "",
                "source": source,
                "timestamp": timestamp,
                "update_count": update_count,
                "usage_count": usage_count,
                "positive_feedback": positive_feedback,
                "negative_feedback": negative_feedback,
            }

            full_content = f"【{title}】\n{content}"
            texts.append(full_content)
            metadatas.append(metadata)
            ids.append(lore_id)

            json_records.append(
                {
                    "id": lore_id,
                    "title": str(title),
                    "content": str(content),
                    "category": category,
                    "keywords": keywords,
                    "source": source,
                    "timestamp": timestamp,
                    "update_count": update_count,
                    "usage_count": usage_count,
                    "positive_feedback": positive_feedback,
                    "negative_feedback": negative_feedback,
                }
            )

        if not texts:
            return 0

        # 先写 JSON，确保导入后可持久化恢复
        try:
            if overwrite:
                self._write_json_records(json_records)
            else:
                merged = self._read_json_records()
                merged.extend(json_records)
                self._write_json_records(merged)
        except Exception as e:
            logger.error(f"写入知识 JSON 失败: {e}")

        imported = 0
        batch_size = max(1, int(batch_size))
        for offset in range(0, len(texts), batch_size):
            chunk_texts = texts[offset : offset + batch_size]
            chunk_metas = metadatas[offset : offset + batch_size]
            chunk_ids = ids[offset : offset + batch_size]
            try:
                self.vectorstore.add_texts(texts=chunk_texts, metadatas=chunk_metas, ids=chunk_ids)
                imported += len(chunk_texts)
            except Exception as e:
                logger.error(f"导入知识库向量库批次失败: {e}")

        self._invalidate_cache()
        logger.info(f"导入知识库完成: {imported} 条 (overwrite={overwrite})")
        return imported

    def clear_all(self) -> bool:
        """
        清空所有知识 - v2.30.38 新增

        Returns:
            bool: 是否成功
        """
        if self.json_file is None:
            return False

        previous_records: List[Dict[str, Any]] = []
        lore_ids: List[str] = []

        try:
            with self._lock:
                previous_records = self._read_json_records_unlocked()
                lore_ids = [
                    str(record.get("id")) for record in previous_records if record.get("id")
                ]
                self._write_json_records_unlocked([])

            if self.vectorstore and lore_ids:
                self.vectorstore.delete(ids=lore_ids)

            self._invalidate_cache()
            logger.info("清空知识库成功")
            return True

        except Exception as e:
            # 尝试回滚 JSON，避免“JSON 已清空但向量库未清空”的不一致状态
            try:
                with self._lock:
                    self._write_json_records_unlocked(previous_records)
            except Exception:
                pass

            logger.error(f"清空知识库失败: {e}")
            return False

    # ==================== 私有辅助方法 ====================

    def _read_json_records_unlocked(self) -> List[Dict[str, Any]]:
        """读取知识 JSON（需在 self._lock 内调用）。"""
        if self.json_file is None or not self.json_file.exists():
            return []

        raw = ""
        try:
            raw = self.json_file.read_text(encoding="utf-8")
        except Exception as e:
            logger.error(f"读取知识 JSON 失败: {e}")
            return []

        if not raw.strip():
            return []

        try:
            data = json.loads(raw)
            return data if isinstance(data, list) else []
        except Exception as e:
            logger.error(f"解析知识 JSON 失败: {e}")
            return []

    def _write_json_records_unlocked(self, data: List[Dict[str, Any]]) -> None:
        """写入知识 JSON（需在 self._lock 内调用，原子替换避免损坏）。"""
        if self.json_file is None:
            return

        payload = json.dumps(data, ensure_ascii=False, indent=2)
        target = self.json_file
        temp_file = target.with_suffix(".tmp")

        try:
            temp_file.write_text(payload, encoding="utf-8")
            temp_file.replace(target)
        except Exception as e:
            logger.error(f"写入知识 JSON 失败: {e}")
            try:
                if temp_file.exists():
                    temp_file.unlink(missing_ok=True)
            except Exception:
                pass

    def _read_json_records(self) -> List[Dict[str, Any]]:
        """线程安全地读取知识 JSON 文件（返回 list）。"""
        if self.json_file is None or not self.json_file.exists():
            return []
        with self._lock:
            return self._read_json_records_unlocked()

    def _write_json_records(self, data: List[Dict[str, Any]]) -> None:
        """线程安全地写入知识 JSON 文件（原子替换，避免写入过程中损坏）。"""
        if self.json_file is None:
            return
        with self._lock:
            self._write_json_records_unlocked(data)

    def _save_to_json(self, lore_data: Dict[str, Any]) -> None:
        """保存知识到 JSON 文件"""
        if self.json_file is None:
            return

        try:
            with self._lock:
                data = self._read_json_records_unlocked()
                data.append(lore_data)
                self._write_json_records_unlocked(data)

        except Exception as e:
            logger.error(f"保存到 JSON 失败: {e}")

    def _update_json(self, lore_data: Dict[str, Any]) -> None:
        """更新 JSON 文件中的知识"""
        if self.json_file is None:
            return

        try:
            with self._lock:
                data = self._read_json_records_unlocked()

                # 查找并更新
                for i, lore in enumerate(data):
                    if lore.get("id") == lore_data.get("id"):
                        data[i] = lore_data
                        break

                self._write_json_records_unlocked(data)

        except Exception as e:
            logger.error(f"更新 JSON 失败: {e}")

    def _delete_from_json(self, lore_id: str) -> bool:
        """从 JSON 文件删除知识"""
        if self.json_file is None:
            return False

        try:
            with self._lock:
                data = self._read_json_records_unlocked()
                before = len(data)

                # 过滤掉要删除的条目
                data = [lore for lore in data if lore.get("id") != lore_id]
                deleted = len(data) != before

                if deleted:
                    self._write_json_records_unlocked(data)
                return deleted

        except Exception as e:
            logger.error(f"从 JSON 删除失败: {e}")
            return False

    def _get_lore_by_id(self, lore_id: str) -> Optional[Dict[str, Any]]:
        """根据ID获取知识"""
        if self.json_file is None or not self.json_file.exists():
            return None

        try:
            if self._cache is not None:
                lore_by_id = self._cache.get("lore_by_id")
                if isinstance(lore_by_id, dict) and lore_id in lore_by_id:
                    return lore_by_id.get(lore_id)

            for lore in self.get_all_lores(use_cache=True):
                if lore.get("id") == lore_id:
                    return lore
            return None

        except Exception as e:
            logger.error(f"获取知识失败: {e}")
            return None

    # ==================== 智能学习系统 (v2.30.38 新增) ====================

    def learn_from_conversation(
        self,
        user_message: str,
        ai_response: str,
        auto_extract: bool = True,
        use_llm: bool = True,
    ) -> List[str]:
        """
        从对话中学习知识 - v2.30.39 增强版（支持 LLM 辅助提取）

        Args:
            user_message: 用户消息
            ai_response: AI回复
            auto_extract: 是否自动提取知识
            use_llm: 是否使用 LLM 辅助提取（更智能但更慢）

        Returns:
            List[str]: 学习到的知识ID列表
        """
        if not auto_extract:
            return []

        learned_ids = []

        try:
            # v2.30.39: 使用 LLM 辅助提取（如果启用）
            if use_llm and getattr(settings.agent, "use_llm_for_knowledge_extraction", False):
                learned_ids = self._llm_extract_knowledge(user_message, ai_response)
                if learned_ids:
                    return learned_ids

            # 回退到基于规则的提取
            # 检测是否包含知识性内容
            knowledge_keywords = [
                "是",
                "叫",
                "名字",
                "介绍",
                "说明",
                "解释",
                "定义",
                "含义",
                "意思",
                "特点",
                "特征",
                "位于",
                "在",
                "地点",
                "地方",
                "位置",
                "用于",
                "用来",
                "作用",
                "功能",
                "用途",
                "喜欢",
                "讨厌",
                "爱好",
                "兴趣",
                "习惯",  # v2.30.39: 新增情感相关
                "生日",
                "年龄",
                "身高",
                "体重",
                "外貌",  # v2.30.39: 新增属性相关
            ]

            combined_text = user_message + " " + ai_response

            # 简单的知识提取逻辑
            if any(keyword in combined_text for keyword in knowledge_keywords):
                # 提取标题（从用户消息中）
                title = self._extract_title_from_message(user_message)
                if not title:
                    return []

                # 提取内容（从AI回复中）
                content = ai_response

                # 提取类别
                category = self._extract_category_from_content(combined_text)

                # 提取关键词
                keywords = self._extract_keywords_from_content(combined_text)

                # v2.30.39: 检查是否重复
                if self._is_duplicate_knowledge(title, content):
                    logger.debug(f"跳过重复知识: {title}")
                    return []

                # 添加知识
                lore_id = self.add_lore(
                    title=title,
                    content=content,
                    category=category,
                    keywords=keywords,
                    source="conversation",
                )

                if lore_id:
                    learned_ids.append(lore_id)
                    logger.info(f"从对话中学习到知识: {title}")

        except Exception as e:
            logger.error(f"从对话中学习失败: {e}")

        return learned_ids

    def learn_from_file(
        self,
        filepath: str,
        file_type: Optional[str] = None,
        chunk_size: int = 1000,
    ) -> List[str]:
        """
        从文件中学习知识 - v2.30.38 新增

        Args:
            filepath: 文件路径
            file_type: 文件类型（txt, md, pdf, docx）
            chunk_size: 分块大小

        Returns:
            List[str]: 学习到的知识ID列表
        """
        if self.vectorstore is None:
            return []

        learned_ids: List[str] = []
        try:
            content = self._read_file_content(filepath, file_type)
            if not content:
                return []

            chunks = self._split_content_into_chunks(content, chunk_size)
            if not chunks:
                return []

            # v3.x: 批量写入向量库 + 一次性写 JSON（避免逐条 add_texts / 频繁 invalidate cache）
            try:
                import uuid

                ids: list[str] = []
                metadatas: list[Dict[str, Any]] = []
                texts: list[str] = []
                json_records: list[Dict[str, Any]] = []

                for i, chunk in enumerate(chunks):
                    title = self._extract_title_from_chunk(chunk, i)
                    category = self._extract_category_from_content(chunk)
                    keywords = self._extract_keywords_from_content(chunk)

                    lore_id = str(uuid.uuid4())
                    ids.append(lore_id)

                    metadata = self._create_lore_metadata(
                        lore_id=lore_id,
                        title=title,
                        category=category,
                        keywords=keywords,
                        source="file",
                    )
                    metadatas.append(metadata)
                    texts.append(f"【{title}】\n{chunk}")
                    json_records.append(
                        {
                            "id": lore_id,
                            "title": title,
                            "content": chunk,
                            "category": category,
                            "keywords": keywords or [],
                            "source": "file",
                            "timestamp": metadata["timestamp"],
                            "update_count": 0,
                            "usage_count": 0,
                            "positive_feedback": 0,
                            "negative_feedback": 0,
                        }
                    )

                self.vectorstore.add_texts(texts=texts, metadatas=metadatas, ids=ids)

                # 一次性写入 JSON，提升大文件学习性能
                try:
                    with self._lock:
                        existing = self._read_json_records_unlocked()
                        existing.extend(json_records)
                        self._write_json_records_unlocked(existing)
                except Exception as exc:
                    logger.error("批量保存到 JSON 失败，将回退逐条追加: %s", exc)
                    for record in json_records:
                        self._save_to_json(record)

                self._invalidate_cache()
                learned_ids = ids

            except Exception as batch_exc:
                logger.error("批量写入失败，回退为逐条写入: %s", batch_exc)
                learned_ids = []
                for i, chunk in enumerate(chunks):
                    title = self._extract_title_from_chunk(chunk, i)
                    category = self._extract_category_from_content(chunk)
                    keywords = self._extract_keywords_from_content(chunk)
                    lore_id = self.add_lore(
                        title=title,
                        content=chunk,
                        category=category,
                        keywords=keywords,
                        source="file",
                        skip_quality_check=True,
                    )
                    if lore_id:
                        learned_ids.append(lore_id)

            logger.info("从文件中学习到 %s 条知识: %s", len(learned_ids), filepath)
            return learned_ids

        except Exception as e:
            logger.error(f"从文件中学习失败: {e}")
            return learned_ids

    def learn_from_mcp(
        self,
        mcp_data: Dict[str, Any],
        source_name: str = "mcp",
    ) -> Optional[str]:
        """
        从 MCP 数据中学习知识 - v2.30.38 新增

        Args:
            mcp_data: MCP 返回的数据
            source_name: MCP 来源名称

        Returns:
            str: 学习到的知识ID，失败返回 None
        """
        try:
            # 提取标题
            title = mcp_data.get("title") or mcp_data.get("name") or "MCP数据"

            # 提取内容
            content = mcp_data.get("content") or mcp_data.get("description") or str(mcp_data)

            # 提取类别
            category = mcp_data.get("category") or "general"

            # 提取关键词
            keywords = mcp_data.get("keywords") or []

            # 添加知识
            lore_id = self.add_lore(
                title=title,
                content=content,
                category=category,
                keywords=keywords,
                source=f"mcp:{source_name}",
            )

            if lore_id:
                logger.info(f"从 MCP 中学习到知识: {title}")

            return lore_id

        except Exception as e:
            logger.error(f"从 MCP 中学习失败: {e}")
            return None

    # ==================== LLM 辅助提取方法 (v2.30.39 新增) ====================

    def _llm_extract_knowledge(self, user_message: str, ai_response: str) -> List[str]:
        """
        使用 LLM 辅助提取知识 - v2.30.39 新增

        Args:
            user_message: 用户消息
            ai_response: AI回复

        Returns:
            List[str]: 学习到的知识ID列表
        """
        learned_ids = []

        try:
            from langchain_core.prompts import ChatPromptTemplate
            from langchain_core.output_parsers import JsonOutputParser

            # 构建提示词
            extraction_prompt = ChatPromptTemplate.from_messages(
                [
                    (
                        "system",
                        """你是一个知识提取专家。请从对话中提取有价值的知识信息。

提取规则：
1. 只提取事实性、可记录的知识（人物、地点、事件、物品、特征等）
2. 忽略日常闲聊、天气、心情等临时性信息
3. 每条知识应该独立、完整、有意义

请以 JSON 格式返回提取的知识列表：
{{
    "has_knowledge": true/false,
    "knowledge_list": [
        {{
            "title": "知识标题（简短概括）",
            "content": "知识内容（详细描述）",
            "category": "类别（character/location/item/event/general）",
            "keywords": ["关键词1", "关键词2", ...]
        }}
    ]
}}

如果对话中没有值得记录的知识，返回 {{"has_knowledge": false, "knowledge_list": []}}""",
                    ),
                    ("human", "用户: {user_message}\nAI: {ai_response}"),
                ]
            )

            # 创建链
            from src.llm.factory import get_llm

            llm = get_llm()
            parser = JsonOutputParser()
            chain = extraction_prompt | llm | parser

            # 执行提取
            result = chain.invoke(
                {
                    "user_message": user_message,
                    "ai_response": ai_response,
                }
            )

            # 处理结果
            if result.get("has_knowledge") and result.get("knowledge_list"):
                for knowledge in result["knowledge_list"]:
                    # 检查必需字段
                    if not knowledge.get("title") or not knowledge.get("content"):
                        continue

                    # 检查是否重复
                    if self._is_duplicate_knowledge(knowledge["title"], knowledge["content"]):
                        logger.debug(f"跳过重复知识: {knowledge['title']}")
                        continue

                    # 添加知识
                    lore_id = self.add_lore(
                        title=knowledge["title"],
                        content=knowledge["content"],
                        category=knowledge.get("category", "general"),
                        keywords=knowledge.get("keywords", []),
                        source="conversation:llm",
                    )

                    if lore_id:
                        learned_ids.append(lore_id)
                        logger.info(f"LLM 提取到知识: {knowledge['title']}")

        except Exception as e:
            logger.warning(f"LLM 辅助提取失败，回退到规则提取: {e}")

        return learned_ids

    def _is_duplicate_knowledge(self, title: str, content: str, threshold: float = 0.85) -> bool:
        """
        检查知识是否重复 - v2.30.39 新增

        Args:
            title: 知识标题
            content: 知识内容
            threshold: 相似度阈值（默认 0.85）

        Returns:
            bool: 是否重复
        """
        if self.vectorstore is None:
            return False

        try:
            # 搜索相似知识
            query = f"{title} {content}"
            results = self.vectorstore.similarity_search_with_score(query, k=3)

            for doc, score in results:
                similarity = 1.0 - score

                # 如果相似度很高，认为是重复
                if similarity >= threshold:
                    logger.debug(
                        f"发现相似知识: {doc.metadata.get('title')} (相似度: {similarity:.2f})"
                    )
                    return True

            return False

        except Exception as e:
            logger.error(f"检查重复知识失败: {e}")
            return False

    # ==================== 智能提取辅助方法 ====================

    def _extract_title_from_message(self, message: str) -> Optional[str]:
        """从消息中提取标题"""
        # 简单的标题提取逻辑
        # 提取第一句话或前20个字符
        lines = message.strip().split("\n")
        first_line = lines[0] if lines else message

        # 移除问号等
        title = first_line.replace("？", "").replace("?", "").strip()

        # 限制长度
        if len(title) > 50:
            title = title[:50] + "..."

        return title if title else None

    def _extract_title_from_chunk(self, chunk: str, index: int) -> str:
        """从文本块中提取标题"""
        # 尝试提取第一行作为标题
        lines = chunk.strip().split("\n")
        first_line = lines[0] if lines else ""

        # 如果第一行是标题格式（# 开头或很短）
        if first_line.startswith("#"):
            title = first_line.lstrip("#").strip()
        elif len(first_line) < 50:
            title = first_line.strip()
        else:
            # 使用前30个字符
            title = chunk[:30].strip() + "..."

        # 添加索引
        if not title:
            title = f"知识片段 {index + 1}"

        return title

    def _extract_category_from_content(self, content: str) -> str:
        """从内容中提取类别"""
        # 简单的类别识别
        for category, keywords in _CONTENT_CATEGORY_KEYWORDS.items():
            if any(keyword in content for keyword in keywords):
                return category

        return "general"

    def _extract_keywords_from_content(self, content: str) -> List[str]:
        """从内容中提取关键词"""
        # 简单的关键词提取（提取名词）
        # 这里使用简单的规则，实际可以使用 NLP 工具
        # 提取中文词语（2-4个字）
        words = _CHINESE_KEYWORDS_PATTERN.findall(content)

        # 去重并限制数量（保持稳定顺序，避免 set 带来的随机性）
        unique_words = list(dict.fromkeys(words))
        return unique_words[:10]

    def _read_file_content(self, filepath: str, file_type: Optional[str] = None) -> Optional[str]:
        """读取文件内容"""
        try:
            path = Path(filepath)
            if not path.exists():
                logger.error(f"文件不存在: {filepath}")
                return None

            # 自动检测文件类型
            file_type = (file_type or path.suffix).lower().lstrip(".")

            # 读取上限：避免超大文件占用过多内存/阻塞 UI（用于“从文件学习”等场景）
            max_chars = 200_000
            max_bytes = 20 * 1024 * 1024
            max_pdf_pages = 80
            max_csv_rows = 2000

            def _truncate(text: str) -> str:
                text = (text or "").strip()
                if max_chars > 0 and len(text) > max_chars:
                    return text[:max_chars].strip()
                return text

            def _read_text_bytes() -> Optional[bytes]:
                try:
                    with open(path, "rb") as f:
                        data = f.read(max_bytes + 1)
                    if len(data) > max_bytes:
                        data = data[:max_bytes]
                    return data
                except Exception as exc:
                    logger.error("读取文件失败: %s", exc)
                    return None

            def _decode_text(data: bytes) -> str:
                for encoding in ("utf-8", "utf-8-sig", "gbk", "gb2312", "latin-1"):
                    try:
                        return data.decode(encoding)
                    except UnicodeDecodeError:
                        continue
                return data.decode("utf-8", errors="replace")

            # 读取不同类型的文件
            if file_type in ["txt", "md"]:
                data = _read_text_bytes()
                if data is None:
                    return None
                return _truncate(_decode_text(data))

            elif file_type == "pdf":
                # 需要 PyPDF2 或 pdfplumber
                try:
                    import PyPDF2

                    with open(path, "rb") as f:
                        reader = PyPDF2.PdfReader(f)
                        parts: list[str] = []
                        total = 0
                        for i, page in enumerate(reader.pages):
                            if i >= max_pdf_pages:
                                break
                            page_text = page.extract_text() or ""
                            if not page_text:
                                continue
                            parts.append(page_text)
                            total += len(page_text)
                            if max_chars > 0 and total >= max_chars:
                                break
                        return _truncate("\n".join(parts))
                except ImportError:
                    logger.warning("需要安装 PyPDF2: uv pip install PyPDF2")
                    return None

            elif file_type == "docx":
                # 需要 python-docx
                try:
                    import docx

                    doc = docx.Document(path)
                    parts: list[str] = []
                    total = 0
                    for para in doc.paragraphs:
                        text = (para.text or "").strip()
                        if not text:
                            continue
                        parts.append(text)
                        total += len(text)
                        if max_chars > 0 and total >= max_chars:
                            break
                    return _truncate("\n".join(parts))
                except ImportError:
                    logger.warning("需要安装 python-docx: uv pip install python-docx")
                    return None

            elif file_type in ["html", "htm"]:
                # v2.30.39: 支持 HTML 文件
                try:
                    from bs4 import BeautifulSoup

                    data = _read_text_bytes()
                    if data is None:
                        return None
                    html_content = _decode_text(data)
                    soup = BeautifulSoup(html_content, "html.parser")
                    # 移除 script 和 style 标签
                    for script in soup(["script", "style"]):
                        script.decompose()
                    text = soup.get_text(separator="\n\n")
                    # 清理多余空行
                    lines = [line.strip() for line in text.split("\n") if line.strip()]
                    return _truncate("\n\n".join(lines))
                except ImportError:
                    logger.warning("需要安装 beautifulsoup4: uv pip install beautifulsoup4")
                    return None

            elif file_type == "json":
                # v2.30.39: 支持 JSON 文件
                try:
                    raw = _read_text_bytes()
                    if raw is None:
                        return None
                    data = json.loads(_decode_text(raw))
                    # 将 JSON 转换为可读文本
                    return _truncate(json.dumps(data, ensure_ascii=False, indent=2))
                except Exception as e:
                    logger.error(f"解析 JSON 文件失败: {e}")
                    return None

            elif file_type == "csv":
                # v2.30.39: 支持 CSV 文件
                try:
                    import csv
                    from io import StringIO

                    raw = _read_text_bytes()
                    if raw is None:
                        return None
                    content = _decode_text(raw)
                    reader = csv.DictReader(StringIO(content))

                    text_lines: list[str] = []
                    total = 0
                    for i, row in enumerate(reader):
                        if i >= max_csv_rows:
                            break
                        line = ", ".join([f"{k}: {v}" for k, v in row.items()])
                        if not line.strip():
                            continue
                        text_lines.append(line)
                        total += len(line)
                        if max_chars > 0 and total >= max_chars:
                            break
                    return _truncate("\n\n".join(text_lines))
                except Exception as e:
                    logger.error(f"解析 CSV 文件失败: {e}")
                    return None

            else:
                logger.warning(f"不支持的文件类型: {file_type}")
                return None

        except Exception as e:
            logger.error(f"读取文件失败: {e}")
            return None

    def _split_content_into_chunks(
        self,
        content: str,
        chunk_size: int,
        overlap: int = 100,
    ) -> List[str]:
        """
        将内容分块 - v2.30.39 增强版（支持重叠）

        Args:
            content: 内容
            chunk_size: 分块大小
            overlap: 重叠大小（默认 100 字符）

        Returns:
            List[str]: 分块列表
        """
        # 按段落分割
        paragraphs = content.split("\n\n")

        chunks = []
        current_chunk = ""
        previous_chunk_end = ""  # 用于重叠

        for para in paragraphs:
            # 如果当前块加上新段落不超过大小
            if len(current_chunk) + len(para) < chunk_size:
                current_chunk += para + "\n\n"
            else:
                # 保存当前块
                if current_chunk:
                    chunks.append(current_chunk.strip())
                    # 保存末尾用于重叠
                    previous_chunk_end = (
                        current_chunk[-overlap:] if len(current_chunk) > overlap else current_chunk
                    )

                # 开始新块，包含重叠部分
                if previous_chunk_end:
                    current_chunk = previous_chunk_end + para + "\n\n"
                else:
                    current_chunk = para + "\n\n"

        # 保存最后一块
        if current_chunk:
            chunks.append(current_chunk.strip())

        return chunks

    # ==================== 性能优化方法 (v2.30.39 新增) ====================

    def _invalidate_cache(
        self, *, reset_hybrid: bool = True, clear_search_cache: bool = True
    ) -> None:
        """清除缓存 - v2.30.44 增强版（支持更细粒度的失效策略）。"""
        if self._cache is not None:
            self._cache["all_lores"] = None
            self._cache["lore_by_id"] = None
            self._cache["statistics"] = None
            self._cache["last_update"] = datetime.now()
            logger.debug("知识库缓存已清除")

        # v2.30.40: 重置混合检索器（需要重新构建索引）
        if reset_hybrid and HAS_HYBRID_RETRIEVER:
            self.hybrid_retriever = None
            logger.debug("混合检索器已重置")

        # v2.30.44: 清除多级缓存
        if self.multi_cache:
            if clear_search_cache:
                self.multi_cache.clear(prefix="lorebook")
                logger.debug("多级缓存已清除")
            else:
                # 仅清理元数据相关缓存，保留 search:* 结果，避免无谓的缓存击穿
                self.multi_cache.delete("all_lores", prefix="lorebook")
                self.multi_cache.delete("statistics", prefix="lorebook")
                logger.debug("多级缓存（元数据）已清除")

    def batch_add_lores(self, lores: List[Dict[str, Any]]) -> List[str]:
        """
        批量添加知识 - v2.30.39 新增

        Args:
            lores: 知识列表，每个元素包含 title, content, category, keywords, source

        Returns:
            List[str]: 成功添加的知识ID列表
        """
        if self.vectorstore is None:
            return []

        added_ids: List[str] = []

        try:
            # 准备批量数据
            texts = []
            metadatas = []
            ids = []
            json_records: List[Dict[str, Any]] = []

            import uuid

            for lore in lores:
                # 生成ID
                lore_id = str(uuid.uuid4())

                # 准备数据
                title = lore.get("title", "")
                content = lore.get("content", "")
                category = lore.get("category", "general")
                keywords = lore.get("keywords", [])
                source = lore.get("source", "manual")

                full_content = f"【{title}】\n{content}"
                metadata = {
                    "id": lore_id,
                    "title": title,
                    "category": category,
                    "keywords": ",".join(keywords) if keywords else "",
                    "source": source,
                    "timestamp": datetime.now().isoformat(),
                    "update_count": 0,
                }

                texts.append(full_content)
                metadatas.append(metadata)
                ids.append(lore_id)
                json_records.append(
                    {
                        "id": lore_id,
                        "title": title,
                        "content": content,
                        "category": category,
                        "keywords": keywords or [],
                        "source": source,
                        "timestamp": metadata["timestamp"],
                        "update_count": 0,
                    }
                )

            # 批量添加到向量数据库
            self.vectorstore.add_texts(
                texts=texts,
                metadatas=metadatas,
                ids=ids,
            )

            try:
                with self._lock:
                    data = self._read_json_records_unlocked()
                    data.extend(json_records)
                    self._write_json_records_unlocked(data)
            except Exception as e:
                # 回滚向量库写入，避免“向量库有但 JSON 没有”的不一致状态
                logger.error(f"批量保存到 JSON 失败，将回滚向量库写入: {e}")
                try:
                    self.vectorstore.delete(ids=ids)
                except Exception as rollback_exc:
                    logger.warning(f"回滚向量库写入失败（可能导致不一致）: {rollback_exc}")
                return []

            added_ids.extend(ids)

            # 清除缓存
            self._invalidate_cache()

            # v2.30.43+: 知识图谱增量同步（批量）
            self._kg_upsert_entries(
                [
                    {
                        "id": r.get("id"),
                        "title": r.get("title", ""),
                        "category": r.get("category", "general"),
                        "keywords": r.get("keywords", []) or [],
                    }
                    for r in json_records
                ]
            )

            logger.info(f"批量添加 {len(added_ids)} 条知识")
            return added_ids

        except Exception as e:
            logger.error(f"批量添加知识失败: {e}")
            return added_ids

    def batch_delete_lores(self, lore_ids: List[str]) -> int:
        """
        批量删除知识 - v2.30.39 新增

        Args:
            lore_ids: 知识ID列表

        Returns:
            int: 成功删除的数量
        """
        if self.vectorstore is None:
            return 0

        if not lore_ids:
            return 0

        deleted_count = 0

        try:
            # 去重，避免重复 delete 造成额外开销
            unique_ids = list(dict.fromkeys([str(i) for i in lore_ids if i]))
            if not unique_ids:
                return 0

            previous_records: List[Dict[str, Any]] = []
            try:
                with self._lock:
                    previous_records = self._read_json_records_unlocked()
                    id_set = set(unique_ids)
                    filtered = [lore for lore in previous_records if lore.get("id") not in id_set]
                    deleted_count = len(previous_records) - len(filtered)
                    if deleted_count:
                        self._write_json_records_unlocked(filtered)
            except Exception as e:
                logger.error(f"批量删除知识（JSON 更新）失败: {e}")
                return 0

            # 批量从向量数据库删除（在 JSON 成功写入后执行，失败则回滚 JSON）
            try:
                self.vectorstore.delete(ids=unique_ids)
            except Exception as e:
                try:
                    with self._lock:
                        self._write_json_records_unlocked(previous_records)
                except Exception:
                    pass
                logger.error(f"批量删除知识（向量库删除）失败，已回滚 JSON: {e}")
                return 0

            # 清除缓存
            self._invalidate_cache()

            # v2.30.43+: 知识图谱增量同步（批量）
            self._kg_delete_nodes(unique_ids)

            logger.info(f"批量删除 {deleted_count} 条知识")
            return deleted_count

        except Exception as e:
            logger.error(f"批量删除知识失败: {e}")
            return deleted_count

    # ==================== 知识质量管理方法 (v2.30.41 新增) ====================

    def provide_feedback(
        self,
        lore_id: str,
        is_positive: bool,
    ) -> bool:
        """
        提供知识反馈 - v2.30.41 新增

        Args:
            lore_id: 知识ID
            is_positive: 是否为正面反馈

        Returns:
            bool: 是否成功
        """
        if self.json_file is None:
            return False

        try:
            updated = False
            with self._lock:
                all_lores = self._read_json_records_unlocked()
                for lore in all_lores:
                    if lore.get("id") == lore_id:
                        if is_positive:
                            lore["positive_feedback"] = lore.get("positive_feedback", 0) + 1
                        else:
                            lore["negative_feedback"] = lore.get("negative_feedback", 0) + 1
                        updated = True
                        self._write_json_records_unlocked(all_lores)
                        break

            if not updated:
                logger.warning(f"未找到知识: {lore_id}")
                return False

            # 清除缓存（反馈不影响向量检索结果，但会影响元数据展示）
            self._invalidate_cache(reset_hybrid=False, clear_search_cache=False)
            logger.info(f"知识反馈已记录: {lore_id} ({'正面' if is_positive else '负面'})")
            return True

        except Exception as e:
            logger.error(f"提供反馈失败: {e}")
            return False

    def assess_knowledge_quality(
        self,
        lore_id: str,
    ) -> Optional[Dict[str, Any]]:
        """
        评估知识质量 - v2.30.41 新增

        Args:
            lore_id: 知识ID

        Returns:
            Dict: 评估结果，失败返回 None
        """
        if not self.quality_manager:
            logger.warning("知识质量管理系统未启用")
            return None

        try:
            # 获取知识
            all_lores = self.get_all_lores(use_cache=True)
            knowledge = None

            for lore in all_lores:
                if lore.get("id") == lore_id:
                    knowledge = lore
                    break

            if not knowledge:
                logger.warning(f"未找到知识: {lore_id}")
                return None

            # 评估
            assessment = self.quality_manager.assess_knowledge(knowledge, all_lores)

            return assessment

        except Exception as e:
            logger.error(f"评估知识质量失败: {e}")
            return None

    def get_low_quality_knowledge(
        self,
        threshold: float = 0.3,
    ) -> List[Dict[str, Any]]:
        """
        获取低质量知识列表 - v2.30.41 新增

        Args:
            threshold: 质量阈值（低于此值认为是低质量）

        Returns:
            List[Dict]: 低质量知识列表
        """
        if not self.quality_manager:
            return []

        try:
            all_lores = self.get_all_lores(use_cache=True)
            low_quality = []

            for lore in all_lores:
                quality_score = self.quality_manager.scorer.calculate_quality_score(lore)
                if quality_score < threshold:
                    low_quality.append(
                        {
                            **lore,
                            "quality_score": quality_score,
                        }
                    )

            # 按质量分数排序
            low_quality.sort(key=lambda x: x["quality_score"])

            logger.info(f"找到 {len(low_quality)} 条低质量知识")
            return low_quality

        except Exception as e:
            logger.error(f"获取低质量知识失败: {e}")
            return []

    # ==================== 知识推荐方法 (v2.30.42 新增) ====================

    def recommend_knowledge(
        self,
        context: Dict[str, Any],
        k: int = 5,
        min_score: float = 0.3,
    ) -> List[Dict[str, Any]]:
        """
        推荐知识 - v2.30.42 新增

        Args:
            context: 上下文信息
                - query: 当前查询
                - topic: 当前主题
                - keywords: 关键词列表
                - recent_topics: 最近讨论的主题
                - user_id: 用户ID（可选）
            k: 推荐数量
            min_score: 最低推荐分数

        Returns:
            List[Dict]: 推荐的知识列表
        """
        if not self.recommender:
            logger.warning("知识推荐系统未启用")
            return []

        try:
            # 获取所有知识
            all_lores = self.get_all_lores(use_cache=True)

            # 推荐
            recommendations = self.recommender.recommend(context, all_lores, k, min_score)

            # 记录使用统计
            if self.usage_tracker:
                for rec in recommendations:
                    self.usage_tracker.record_usage(
                        rec.get("id"), context, usage_type="recommendation"
                    )

            logger.info(f"推荐知识: {len(recommendations)} 条")
            return recommendations

        except Exception as e:
            logger.error(f"推荐知识失败: {e}")
            return []

    def push_knowledge(
        self,
        user_id: str,
        context: Dict[str, Any],
        k: int = 3,
    ) -> List[Dict[str, Any]]:
        """
        主动推送知识 - v2.30.42 新增

        Args:
            user_id: 用户ID
            context: 上下文信息
            k: 推送数量

        Returns:
            List[Dict]: 推送的知识列表
        """
        if not self.pusher:
            logger.warning("主动推送系统未启用")
            return []

        try:
            if k <= 0:
                return []

            # 统一注入全局开关，避免调用方遗漏导致行为不一致
            ctx = dict(context or {})
            ctx.setdefault(
                "proactive_push_enabled",
                bool(getattr(settings.agent, "proactive_push_enabled", True)),
            )

            # 先做轻量触发判断，避免频繁加载整库
            triggers = None
            should_push_with_triggers = getattr(self.pusher, "should_push_with_triggers", None)
            if callable(should_push_with_triggers):
                ok, triggers = should_push_with_triggers(user_id, ctx)
                if not ok:
                    return []
            else:
                if not self.pusher.should_push(user_id, ctx):
                    return []

            # 优先用向量检索构建候选池（避免全库扫描；为空则回退）
            candidate_pool_size = int(
                getattr(settings.agent, "proactive_push_candidate_pool_size", 60)
            )
            candidates: List[Dict[str, Any]] = []
            if (
                candidate_pool_size > 0
                and self.vectorstore is not None
                and hasattr(self.vectorstore, "similarity_search_with_score")
            ):

                def _normalize_keywords(raw: Any) -> List[str]:
                    if isinstance(raw, str):
                        return [p.strip() for p in raw.split(",") if p.strip()]
                    if isinstance(raw, list):
                        return [str(k).strip() for k in raw if str(k).strip()]
                    return []

                def _build_query() -> str:
                    msg = str(ctx.get("user_message", "") or "").strip()
                    topic = str(ctx.get("topic", "") or "").strip()
                    kws = ctx.get("keywords", [])
                    if not isinstance(kws, list):
                        kws = []
                    kw_text = " ".join([str(k).strip() for k in kws[:12] if str(k).strip()])

                    parts: list[str] = []
                    if msg:
                        parts.append(msg)
                    if topic:
                        parts.append(topic)
                    if kw_text:
                        parts.append(kw_text)

                    last_used = ctx.get("last_used_knowledge")
                    if isinstance(last_used, dict):
                        title = str(last_used.get("title", "") or "").strip()
                        last_kws = _normalize_keywords(last_used.get("keywords") or [])
                        if title:
                            parts.append(title)
                        if last_kws:
                            parts.append(" ".join(last_kws[:12]))

                    query = " ".join([p for p in parts if p]).strip()
                    if len(query) > 800:
                        query = query[:800].strip()
                    return query

                query = _build_query()
                if query:
                    try:
                        results = self.vectorstore.similarity_search_with_score(
                            query, k=int(candidate_pool_size)
                        )
                    except Exception:
                        results = []

                    seen_ids: set[str] = set()
                    for doc, score in results or []:
                        meta = getattr(doc, "metadata", {}) or {}
                        if not isinstance(meta, dict):
                            meta = {}
                        lore_id = meta.get("id")
                        lore_id = str(lore_id).strip() if lore_id is not None else ""
                        if lore_id and lore_id in seen_ids:
                            continue
                        if lore_id:
                            seen_ids.add(lore_id)

                        cand = {
                            "id": lore_id or None,
                            "title": str(meta.get("title") or "").strip(),
                            "category": str(meta.get("category") or "").strip(),
                            "source": str(meta.get("source") or "").strip(),
                            "keywords": _normalize_keywords(meta.get("keywords") or []),
                            "content": str(getattr(doc, "page_content", "") or "").strip(),
                        }
                        try:
                            similarity = 1.0 - float(score) if score is not None else None
                        except Exception:
                            similarity = None
                        cand["similarity"] = similarity

                        if "quality_score" not in cand and self.quality_manager:
                            try:
                                cand["quality_score"] = (
                                    self.quality_manager.scorer.calculate_quality_score(cand)
                                )
                            except Exception:
                                pass

                        candidates.append(cand)

            if candidates:
                pushed = self.pusher.push_knowledge(
                    user_id,
                    ctx,
                    candidates,
                    k,
                    triggers=triggers,
                    checked=triggers is not None,
                )
            else:
                # 回退：获取所有知识（可能较重）
                all_lores = self.get_all_lores(use_cache=True)
                pushed = self.pusher.push_knowledge(
                    user_id,
                    ctx,
                    all_lores,
                    k,
                    triggers=triggers,
                    checked=triggers is not None,
                )

            # 记录使用统计
            if self.usage_tracker:
                for knowledge in pushed:
                    self.usage_tracker.record_usage(knowledge.get("id"), ctx, usage_type="push")

            logger.info(f"主动推送知识: {len(pushed)} 条")
            return pushed

        except Exception as e:
            logger.error(f"主动推送知识失败: {e}")
            return []

    def update_recommendation_preference(
        self,
        user_id: str,
        knowledge: Dict[str, Any],
        is_positive: bool,
    ):
        """
        更新推荐偏好 - v2.30.42 新增

        Args:
            user_id: 用户ID
            knowledge: 知识条目
            is_positive: 是否为正面反馈
        """
        if not self.recommender:
            return

        try:
            # 更新推荐器的用户偏好
            self.recommender.update_user_preference(user_id, knowledge, is_positive)

            # 记录反馈统计
            if self.usage_tracker:
                self.usage_tracker.record_feedback(knowledge.get("id"), is_positive)

            logger.debug(f"更新推荐偏好: {user_id}, 正面={is_positive}")

        except Exception as e:
            logger.error(f"更新推荐偏好失败: {e}")

    def get_knowledge_usage_stats(self, knowledge_id: str) -> Optional[Dict[str, Any]]:
        """
        获取知识使用统计 - v2.30.42 新增

        Args:
            knowledge_id: 知识ID

        Returns:
            Dict: 统计信息，不存在返回 None
        """
        if not self.usage_tracker:
            return None

        return self.usage_tracker.get_knowledge_stats(knowledge_id)

    def get_top_used_knowledge(self, k: int = 10) -> List[Dict[str, Any]]:
        """
        获取最常用的知识 - v2.30.42 新增

        Args:
            k: 返回数量

        Returns:
            List[Dict]: 知识ID和使用次数列表
        """
        if not self.usage_tracker:
            return []

        return self.usage_tracker.get_top_used_knowledge(k)

    def get_unused_knowledge(self, days: int = 30) -> List[str]:
        """
        获取未使用的知识 - v2.30.42 新增

        Args:
            days: 多少天内未使用

        Returns:
            List[str]: 未使用的知识ID列表
        """
        if not self.usage_tracker:
            return []

        try:
            all_lores = self.get_all_lores(use_cache=True)
            all_ids = [lore.get("id") for lore in all_lores if lore.get("id")]

            return self.usage_tracker.get_unused_knowledge(all_ids, days)

        except Exception as e:
            logger.error(f"获取未使用知识失败: {e}")
            return []

    def generate_usage_report(self) -> str:
        """
        生成使用统计报告 - v2.30.42 新增

        Returns:
            str: 统计报告文本
        """
        if not self.usage_tracker:
            return "知识使用统计系统未启用"

        return self.usage_tracker.generate_report()

    # ==================== 知识图谱方法 (v2.30.43 新增) ====================

    def build_knowledge_graph(self, use_llm: bool = False):
        """
        构建知识图谱 - v2.30.43 新增

        Args:
            use_llm: 是否使用 LLM 提取关系
        """
        if not self.knowledge_graph:
            logger.warning("知识图谱系统未启用")
            return

        try:
            # 获取所有知识
            all_lores = self.get_all_lores(use_cache=True)

            # 构建图谱
            self.knowledge_graph.build_graph_from_knowledge(all_lores, use_llm=use_llm)

            logger.info("知识图谱构建完成")

        except Exception as e:
            logger.error(f"构建知识图谱失败: {e}")

    def find_related_knowledge_by_graph(
        self,
        knowledge_id: str,
        max_depth: int = 2,
        min_confidence: float = 0.5,
    ) -> List[Dict[str, Any]]:
        """
        通过图谱查找相关知识 - v2.30.43 新增

        Args:
            knowledge_id: 知识ID
            max_depth: 最大深度
            min_confidence: 最小置信度

        Returns:
            List[Dict]: 相关知识列表
        """
        if not self.knowledge_graph:
            logger.warning("知识图谱系统未启用")
            return []

        try:
            related_ids = self.knowledge_graph.find_related_knowledge(
                knowledge_id,
                max_depth,
                min_confidence,
                include_incoming=getattr(
                    settings.agent, "knowledge_graph_find_include_incoming", True
                ),
                max_results=getattr(settings.agent, "knowledge_graph_find_max_results", 200),
                max_nodes_visited=getattr(
                    settings.agent, "knowledge_graph_find_max_nodes_visited", 5000
                ),
            )

            # 获取完整的知识信息
            all_lores = self.get_all_lores(use_cache=True)
            lore_dict = {lore.get("id"): lore for lore in all_lores}

            related_lores = []
            for rel in related_ids:
                lore_id = rel.get("id")
                if lore_id in lore_dict:
                    lore = lore_dict[lore_id].copy()
                    lore["graph_relation"] = {
                        "relation_type": rel.get("relation_type"),
                        "confidence": rel.get("confidence"),
                        "description": rel.get("description"),
                        "depth": rel.get("depth"),
                    }
                    related_lores.append(lore)

            logger.info(f"通过图谱找到 {len(related_lores)} 个相关知识")
            return related_lores

        except Exception as e:
            logger.error(f"通过图谱查找相关知识失败: {e}")
            return []

    def find_knowledge_path(
        self,
        source_id: str,
        target_id: str,
    ) -> Optional[List[Dict[str, Any]]]:
        """
        查找两个知识之间的路径 - v2.30.43 新增

        Args:
            source_id: 源知识ID
            target_id: 目标知识ID

        Returns:
            Optional[List[Dict]]: 路径（知识列表），不存在返回 None
        """
        if not self.knowledge_graph:
            logger.warning("知识图谱系统未启用")
            return None

        try:
            path_ids = self.knowledge_graph.find_path(source_id, target_id)

            if not path_ids:
                return None

            # 获取完整的知识信息
            all_lores = self.get_all_lores(use_cache=True)
            lore_dict = {lore.get("id"): lore for lore in all_lores}

            path_lores = []
            for lore_id in path_ids:
                if lore_id in lore_dict:
                    path_lores.append(lore_dict[lore_id])

            logger.info(f"找到知识路径: {len(path_lores)} 个节点")
            return path_lores

        except Exception as e:
            logger.error(f"查找知识路径失败: {e}")
            return None

    def infer_new_relations(self, knowledge_id: str) -> List[Dict[str, Any]]:
        """
        推理新的知识关系 - v2.30.43 新增

        Args:
            knowledge_id: 知识ID

        Returns:
            List[Dict]: 推理出的新关系列表
        """
        if not self.knowledge_graph:
            logger.warning("知识图谱系统未启用")
            return []

        try:
            inferences = self.knowledge_graph.infer_knowledge(knowledge_id)
            logger.info(f"推理出 {len(inferences)} 条新关系")
            return inferences

        except Exception as e:
            logger.error(f"推理新关系失败: {e}")
            return []

    def get_graph_statistics(self) -> Dict[str, Any]:
        """
        获取图谱统计信息 - v2.30.43 新增

        Returns:
            Dict: 统计信息
        """
        if not self.knowledge_graph:
            return {"error": "知识图谱系统未启用"}

        return self.knowledge_graph.get_statistics()

    def export_graph_for_visualization(self) -> Dict[str, Any]:
        """
        导出图谱数据用于可视化 - v2.30.43 新增

        Returns:
            Dict: 可视化数据
        """
        if not self.knowledge_graph:
            return {"error": "知识图谱系统未启用"}

        return self.knowledge_graph.export_for_visualization()
