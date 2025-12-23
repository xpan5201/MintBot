"""
记忆系统优化器 (v3.2)

实现记忆系统的深度优化，包括：
1. 记忆缓存层 - 提升性能
2. 记忆巩固机制 - 自动从短期到长期的转移
3. 记忆去重 - 避免冗余
4. 角色一致性评分 - 与猫娘女仆人设关联
5. 批量操作优化 - 提升响应速度

基于2025年最新研究：
- Mem0: 生产级AI代理的可扩展长期记忆
- 分层记忆系统 (工作/情景/语义/程序记忆)
- Ebbinghaus遗忘曲线优化
"""

import hashlib
from collections import OrderedDict, deque
from datetime import datetime
from threading import Lock
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from src.utils.logger import get_logger

logger = get_logger(__name__)


class MemoryCache:
    """
    记忆缓存层

    功能：
    1. LRU缓存最近访问的记忆
    2. 嵌入向量缓存
    3. 查询结果缓存
    """

    def __init__(self, max_size: int = 100):
        """
        初始化记忆缓存

        Args:
            max_size: 最大缓存条目数
        """
        self.max_size = max_size
        self._lock = Lock()
        self.memory_cache: OrderedDict[str, Dict] = OrderedDict()
        self.embedding_cache: OrderedDict[str, List[float]] = OrderedDict()
        self.query_cache: OrderedDict[str, List[Dict]] = OrderedDict()

        logger.info("记忆缓存初始化完成，最大容量: %d", max_size)

    def get_memory(self, memory_id: str) -> Optional[Dict]:
        """获取缓存的记忆"""
        with self._lock:
            memory = self.memory_cache.get(memory_id)
            if memory is None:
                return None
            # LRU: 移到末尾
            self.memory_cache.move_to_end(memory_id)
            return memory

    def set_memory(self, memory_id: str, memory: Dict) -> None:
        """设置记忆缓存"""
        with self._lock:
            self.memory_cache[memory_id] = memory
            self.memory_cache.move_to_end(memory_id)

            # 超过容量时删除最旧的
            if len(self.memory_cache) > self.max_size:
                self.memory_cache.popitem(last=False)

    def get_embedding(self, text: str) -> Optional[List[float]]:
        """获取缓存的嵌入向量"""
        text_hash = hashlib.md5(text.encode("utf-8")).hexdigest()
        with self._lock:
            embedding = self.embedding_cache.get(text_hash)
            if embedding is None:
                return None
            self.embedding_cache.move_to_end(text_hash)
            return embedding

    def set_embedding(self, text: str, embedding: List[float]) -> None:
        """设置嵌入向量缓存"""
        text_hash = hashlib.md5(text.encode("utf-8")).hexdigest()
        with self._lock:
            self.embedding_cache[text_hash] = embedding
            self.embedding_cache.move_to_end(text_hash)

            if len(self.embedding_cache) > self.max_size:
                self.embedding_cache.popitem(last=False)

    def get_query_result(self, query: str) -> Optional[List[Dict]]:
        """获取缓存的查询结果"""
        query_hash = hashlib.md5(query.encode("utf-8")).hexdigest()
        with self._lock:
            cached = self.query_cache.get(query_hash)
            if cached is None:
                return None
            self.query_cache.move_to_end(query_hash)
            return cached

    def set_query_result(self, query: str, results: List[Dict]) -> None:
        """设置查询结果缓存"""
        query_hash = hashlib.md5(query.encode("utf-8")).hexdigest()
        with self._lock:
            self.query_cache[query_hash] = results
            self.query_cache.move_to_end(query_hash)

            if len(self.query_cache) > self.max_size:
                self.query_cache.popitem(last=False)

    def clear(self) -> None:
        """清空所有缓存"""
        with self._lock:
            self.memory_cache.clear()
            self.embedding_cache.clear()
            self.query_cache.clear()
        logger.info("记忆缓存已清空")

    def get_stats(self) -> Dict[str, int]:
        """获取缓存统计信息"""
        with self._lock:
            return {
                "memory_cache_size": len(self.memory_cache),
                "embedding_cache_size": len(self.embedding_cache),
                "query_cache_size": len(self.query_cache),
                "max_size": self.max_size,
            }


class MemoryDeduplicator:
    """
    记忆去重器

    功能：
    1. 检测重复或相似的记忆
    2. 合并相似记忆
    3. 保留最重要的版本
    """

    def __init__(
        self,
        similarity_threshold: float = 0.85,
        *,
        max_seen_hashes: int = 50_000,
    ):
        """
        初始化去重器

        Args:
            similarity_threshold: 相似度阈值 (0-1)
            max_seen_hashes: 维护的哈希数量上限（0 表示不限制）
        """
        self.similarity_threshold = similarity_threshold
        self._lock = Lock()
        self._max_seen_hashes = int(max_seen_hashes)
        self._hash_queue: Optional[deque[str]] = (
            deque(maxlen=self._max_seen_hashes) if self._max_seen_hashes > 0 else None
        )
        self.seen_hashes: Set[str] = set()

        logger.info(
            "记忆去重器初始化完成，相似度阈值: %.2f, max_seen_hashes=%s",
            similarity_threshold,
            self._max_seen_hashes if self._max_seen_hashes > 0 else "unlimited",
        )

    def get_content_hash(self, content: str) -> str:
        """获取内容哈希"""
        # 标准化内容：去除空格、标点、转小写
        normalized = "".join(content.split()).lower()
        return hashlib.md5(normalized.encode()).hexdigest()

    def contains_hash(self, content_hash: str) -> bool:
        if not content_hash:
            return False
        with self._lock:
            return content_hash in self.seen_hashes

    def add_hash(self, content_hash: str) -> bool:
        """添加哈希；若已存在返回 False。"""
        if not content_hash:
            return False
        with self._lock:
            if content_hash in self.seen_hashes:
                return False
            self.seen_hashes.add(content_hash)
            if self._hash_queue is not None:
                evicted = None
                if len(self._hash_queue) == self._hash_queue.maxlen:
                    evicted = self._hash_queue[0]
                self._hash_queue.append(content_hash)
                if evicted is not None and evicted != content_hash:
                    self.seen_hashes.discard(evicted)
            return True

    def add_hashes(self, hashes: Iterable[str]) -> int:
        """批量添加哈希，返回实际新增数量。"""
        added = 0
        with self._lock:
            for content_hash in hashes:
                if not content_hash or content_hash in self.seen_hashes:
                    continue
                self.seen_hashes.add(content_hash)
                if self._hash_queue is not None:
                    evicted = None
                    if len(self._hash_queue) == self._hash_queue.maxlen:
                        evicted = self._hash_queue[0]
                    self._hash_queue.append(content_hash)
                    if evicted is not None and evicted != content_hash:
                        self.seen_hashes.discard(evicted)
                added += 1
        return added

    def check_and_add(self, content: str) -> bool:
        """检查是否重复并在非重复时记录；True=新，False=重复。"""
        content_hash = self.get_content_hash(content)
        with self._lock:
            if content_hash in self.seen_hashes:
                return False
            self.seen_hashes.add(content_hash)
            if self._hash_queue is not None:
                evicted = None
                if len(self._hash_queue) == self._hash_queue.maxlen:
                    evicted = self._hash_queue[0]
                self._hash_queue.append(content_hash)
                if evicted is not None and evicted != content_hash:
                    self.seen_hashes.discard(evicted)
            return True

    def is_duplicate(self, content: str) -> bool:
        """检查是否重复"""
        return self.contains_hash(self.get_content_hash(content))

    def add_memory(self, content: str) -> bool:
        """
        添加记忆到去重集合

        Returns:
            bool: True表示是新记忆，False表示重复
        """
        return self.check_and_add(content)

    def calculate_similarity(self, text1: str, text2: str) -> float:
        """
        计算两段文本的相似度（简化版Jaccard相似度）

        Args:
            text1: 文本1
            text2: 文本2

        Returns:
            float: 相似度 (0-1)
        """
        # 分词（简单按字符）
        set1 = set(text1)
        set2 = set(text2)

        # Jaccard相似度
        intersection = len(set1 & set2)
        union = len(set1 | set2)

        if union == 0:
            return 0.0

        return intersection / union

    def find_similar_memories(
        self,
        new_memory: str,
        existing_memories: List[Dict],
    ) -> List[Tuple[int, float]]:
        """
        查找相似的记忆

        Args:
            new_memory: 新记忆内容
            existing_memories: 现有记忆列表

        Returns:
            List[Tuple[int, float]]: (索引, 相似度) 列表
        """
        similar = []

        for idx, memory in enumerate(existing_memories):
            content = memory.get("content", "")
            similarity = self.calculate_similarity(new_memory, content)

            if similarity >= self.similarity_threshold:
                similar.append((idx, similarity))

        return similar

    def merge_memories(
        self,
        memory1: Dict,
        memory2: Dict,
    ) -> Dict:
        """
        合并两条相似的记忆

        Args:
            memory1: 记忆1
            memory2: 记忆2

        Returns:
            Dict: 合并后的记忆
        """
        # 选择重要性更高的作为基础
        importance1 = memory1.get("metadata", {}).get("importance", 0.5)
        importance2 = memory2.get("metadata", {}).get("importance", 0.5)

        base_memory = memory1 if importance1 >= importance2 else memory2
        other_memory = memory2 if importance1 >= importance2 else memory1

        # 合并元数据
        merged_metadata = base_memory.get("metadata", {}).copy()

        # 更新访问次数
        access_count1 = memory1.get("metadata", {}).get("access_count", 0)
        access_count2 = memory2.get("metadata", {}).get("access_count", 0)
        merged_metadata["access_count"] = access_count1 + access_count2

        # 更新重要性（取平均）
        merged_metadata["importance"] = (importance1 + importance2) / 2

        # 记录合并信息
        merged_metadata["merged_from"] = merged_metadata.get("merged_from", [])
        merged_metadata["merged_from"].append({
            "content": other_memory.get("content", ""),
            "timestamp": datetime.now().isoformat(),
        })

        return {
            "content": base_memory.get("content", ""),
            "metadata": merged_metadata,
        }


class MemoryConsolidator:
    """
    记忆巩固器

    功能：
    1. 自动将重要的短期记忆转移到长期记忆
    2. 基于重要性和访问频率的巩固策略
    3. 模拟人类记忆巩固过程
    """

    def __init__(
        self,
        consolidation_threshold: float = 0.6,
        min_access_count: int = 2,
    ):
        """
        初始化记忆巩固器

        Args:
            consolidation_threshold: 巩固阈值（重要性分数）
            min_access_count: 最小访问次数
        """
        self.consolidation_threshold = consolidation_threshold
        self.min_access_count = min_access_count

        logger.info(
            f"记忆巩固器初始化完成，"
            f"巩固阈值: {consolidation_threshold}, "
            f"最小访问次数: {min_access_count}"
        )





    def should_consolidate(self, memory: Dict) -> bool:
        """
        判断是否应该巩固这条记忆

        Args:
            memory: 记忆

        Returns:
            bool: 是否应该巩固
        """
        metadata = memory.get("metadata", {})

        # 检查重要性
        importance = metadata.get("importance", 0.0)
        if importance < self.consolidation_threshold:
            return False

        # 检查访问次数
        access_count = metadata.get("access_count", 0)
        if access_count < self.min_access_count:
            return False

        # 检查是否已经在长期记忆中
        if metadata.get("in_long_term", False):
            return False

        return True

    def consolidate_memories(
        self,
        short_term_memories: List[Dict],
    ) -> Tuple[List[Dict], List[Dict]]:
        """
        巩固记忆

        Args:
            short_term_memories: 短期记忆列表

        Returns:
            Tuple[List[Dict], List[Dict]]: (待巩固的记忆, 保留在短期的记忆)
        """
        to_consolidate = []
        to_keep = []

        for memory in short_term_memories:
            if self.should_consolidate(memory):
                # 标记为已巩固
                memory["metadata"]["in_long_term"] = True
                memory["metadata"]["consolidated_at"] = datetime.now().isoformat()
                to_consolidate.append(memory)
            else:
                to_keep.append(memory)

        if to_consolidate:
            logger.info(f"巩固了 {len(to_consolidate)} 条记忆到长期存储")

        return to_consolidate, to_keep


class CharacterConsistencyScorer:
    """
    角色一致性评分器

    功能：
    1. 评估记忆与猫娘女仆角色人设的一致性
    2. 情感上下文标记
    3. 关系感知的记忆优先级
    """

    def __init__(self):
        """初始化角色一致性评分器"""
        # 猫娘女仆角色关键词
        self.character_keywords = {
            # 高度相关 (1.0)
            "主人": 1.0, "喵": 1.0, "nya": 1.0,
            "服侍": 1.0, "照顾": 0.9, "陪伴": 0.9,

            # 中度相关 (0.7)
            "温柔": 0.8, "可爱": 0.8, "乖巧": 0.8,
            "撒娇": 0.7, "亲昵": 0.7, "依赖": 0.7,

            # 情感相关 (0.6)
            "喜欢": 0.6, "爱": 0.6, "想念": 0.6,
            "开心": 0.6, "高兴": 0.6, "快乐": 0.6,
        }

        # 情感上下文类型
        self.emotion_contexts = {
            "positive": ["开心", "高兴", "快乐", "幸福", "兴奋", "喜欢", "爱"],
            "negative": ["难过", "伤心", "失望", "沮丧", "生气", "讨厌"],
            "intimate": ["撒娇", "亲昵", "依赖", "想念", "牵挂", "陪伴"],
            "caring": ["照顾", "关心", "担心", "保护", "服侍"],
        }

        logger.info("角色一致性评分器初始化完成")

    def score_character_consistency(self, content: str) -> float:
        """
        评估记忆与角色人设的一致性

        Args:
            content: 记忆内容

        Returns:
            float: 一致性分数 (0-1)
        """
        score = 0.0

        # 1. 基于角色关键词
        for keyword, weight in self.character_keywords.items():
            if keyword in content:
                score = max(score, weight)

        # 2. 基于情感上下文
        emotion_score = self._score_emotion_context(content)
        score = max(score, emotion_score * 0.8)

        # 3. 基于关系词
        relationship_score = self._score_relationship(content)
        score = max(score, relationship_score * 0.9)

        return min(score, 1.0)

    def _score_emotion_context(self, content: str) -> float:
        """评估情感上下文"""
        max_score = 0.0

        for context_type, keywords in self.emotion_contexts.items():
            count = sum(1 for keyword in keywords if keyword in content)
            if count > 0:
                # 亲密和关怀类情感得分更高
                if context_type in ["intimate", "caring"]:
                    max_score = max(max_score, min(count * 0.3, 1.0))
                else:
                    max_score = max(max_score, min(count * 0.2, 0.8))

        return max_score

    def _score_relationship(self, content: str) -> float:
        """评估关系相关性"""
        relationship_keywords = [
            "主人", "小喵", "我们", "一起", "陪伴",
            "照顾", "服侍", "依赖", "信任", "亲密"
        ]

        count = sum(1 for keyword in relationship_keywords if keyword in content)
        return min(count * 0.25, 1.0)


    def tag_emotion_context(self, content: str) -> List[str]:
        """
        标记情感上下文

        Args:
            content: 记忆内容

        Returns:
            List[str]: 情感标签列表
        """
        tags = []

        for context_type, keywords in self.emotion_contexts.items():
            if any(keyword in content for keyword in keywords):
                tags.append(context_type)

        return tags

    def enhance_memory_metadata(self, memory: Dict) -> Dict:
        """
        增强记忆元数据

        Args:
            memory: 记忆

        Returns:
            Dict: 增强后的记忆
        """
        content = memory.get("content", "")
        metadata = memory.get("metadata", {})

        # 添加角色一致性分数
        metadata["character_consistency"] = self.score_character_consistency(content)

        # 添加情感标签
        metadata["emotion_tags"] = self.tag_emotion_context(content)

        # 更新重要性（考虑角色一致性）
        original_importance = metadata.get("importance", 0.5)
        character_boost = metadata["character_consistency"] * 0.2  # 最多提升20%
        metadata["importance"] = min(original_importance + character_boost, 1.0)

        memory["metadata"] = metadata
        return memory


class MemoryOptimizer:
    """
    记忆系统优化器（主类）

    整合所有优化组件：
    1. 缓存层
    2. 去重器
    3. 巩固器
    4. 角色一致性评分器
    """

    def __init__(
        self,
        enable_cache: bool = True,
        enable_deduplication: bool = True,
        enable_consolidation: bool = True,
        enable_character_scoring: bool = True,
        dedup_max_hashes: int = 50_000,
        user_id: Optional[int] = None,
    ):
        """
        初始化记忆优化器

        Args:
            enable_cache: 是否启用缓存
            enable_deduplication: 是否启用去重
            enable_consolidation: 是否启用巩固
            enable_character_scoring: 是否启用角色一致性评分
            dedup_max_hashes: 去重器保留的哈希数量上限（0 表示不限制）
            user_id: 用户ID
        """
        self.user_id = user_id

        # 初始化组件
        self.cache = MemoryCache() if enable_cache else None
        self.deduplicator = (
            MemoryDeduplicator(max_seen_hashes=dedup_max_hashes) if enable_deduplication else None
        )
        self.consolidator = MemoryConsolidator() if enable_consolidation else None
        self.character_scorer = CharacterConsistencyScorer() if enable_character_scoring else None

        # 统计信息
        self.stats = {
            "total_memories_processed": 0,
            "duplicates_removed": 0,
            "memories_consolidated": 0,
            "cache_hits": 0,
            "cache_misses": 0,
        }

        logger.info(
            f"记忆优化器初始化完成 (用户ID: {user_id if user_id else '全局'})\n"
            f"  - 缓存: {'启用' if enable_cache else '禁用'}\n"
            f"  - 去重: {'启用' if enable_deduplication else '禁用'}\n"
            f"  - 巩固: {'启用' if enable_consolidation else '禁用'}\n"
            f"  - 角色评分: {'启用' if enable_character_scoring else '禁用'}"
        )

    def process_new_memory(self, content: str, metadata: Optional[Dict] = None) -> Optional[Dict]:
        """
        处理新记忆

        Args:
            content: 记忆内容
            metadata: 元数据

        Returns:
            Optional[Dict]: 处理后的记忆，如果是重复则返回None
        """
        self.stats["total_memories_processed"] += 1

        # 1. 检查去重
        if self.deduplicator:
            if not self.deduplicator.check_and_add(content):
                self.stats["duplicates_removed"] += 1
                logger.debug("检测到重复记忆")
                return None

        # 2. 构建记忆对象
        if metadata is None:
            metadata = {}

        memory = {
            "content": content,
            "metadata": metadata,
        }

        # 3. 角色一致性评分
        if self.character_scorer:
            memory = self.character_scorer.enhance_memory_metadata(memory)

        # 4. 添加到缓存
        if self.cache:
            memory_id = hashlib.md5(content.encode()).hexdigest()
            self.cache.set_memory(memory_id, memory)

        return memory


    def optimize_memory_retrieval(
        self,
        query: str,
        memories: List[Dict],
        k: int = 5,
    ) -> List[Dict]:
        """
        优化记忆检索

        Args:
            query: 查询
            memories: 记忆列表
            k: 返回数量

        Returns:
            List[Dict]: 优化后的记忆列表
        """
        # 1. 检查缓存
        if self.cache:
            cached_result = self.cache.get_query_result(query)
            if cached_result is not None:
                self.stats["cache_hits"] += 1
                logger.debug("缓存命中")
                return cached_result[:k]
            self.stats["cache_misses"] += 1

        # 2. 按重要性和角色一致性排序
        scored_memories = []
        for memory in memories:
            metadata = memory.get("metadata", {})
            importance = metadata.get("importance", 0.5)
            character_consistency = metadata.get("character_consistency", 0.5)

            # 综合分数
            score = importance * 0.6 + character_consistency * 0.4
            scored_memories.append((score, memory))

        # 排序并取前k个
        scored_memories.sort(key=lambda x: x[0], reverse=True)
        result = [memory for _, memory in scored_memories[:k]]

        # 3. 缓存结果
        if self.cache:
            self.cache.set_query_result(query, result)

        return result

    def consolidate_short_term_memories(
        self,
        short_term_memories: List[Dict],
    ) -> Tuple[List[Dict], List[Dict]]:
        """
        巩固短期记忆

        Args:
            short_term_memories: 短期记忆列表

        Returns:
            Tuple[List[Dict], List[Dict]]: (待巩固的记忆, 保留的记忆)
        """
        if not self.consolidator:
            return [], short_term_memories

        to_consolidate, to_keep = self.consolidator.consolidate_memories(short_term_memories)
        self.stats["memories_consolidated"] += len(to_consolidate)

        return to_consolidate, to_keep

    def get_stats(self) -> Dict[str, Any]:
        """获取优化器统计信息"""
        stats = self.stats.copy()

        if self.cache:
            stats["cache_stats"] = self.cache.get_stats()

            # 计算缓存命中率
            total_queries = stats["cache_hits"] + stats["cache_misses"]
            if total_queries > 0:
                stats["cache_hit_rate"] = f"{stats['cache_hits'] / total_queries * 100:.1f}%"
            else:
                stats["cache_hit_rate"] = "N/A"

        return stats

    def clear_cache(self) -> None:
        """清空缓存"""
        if self.cache:
            self.cache.clear()
            logger.info("记忆优化器缓存已清空")
