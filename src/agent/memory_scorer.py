"""
记忆重要性评分系统

自动评估记忆的重要性，实现智能遗忘机制。
这是 v2.5 的核心记忆增强功能。
"""

from datetime import datetime
from typing import Dict, List, Optional

from src.utils.logger import get_logger

logger = get_logger(__name__)

_STRONG_EMOTIONS = (
    "非常",
    "特别",
    "超级",
    "极其",
    "太",
    "最",
    "！",
    "!!",
    "？？",
    "...",
    "……",
)
_EMOTION_WORDS = (
    "开心",
    "高兴",
    "快乐",
    "幸福",
    "兴奋",
    "难过",
    "伤心",
    "痛苦",
    "失望",
    "沮丧",
    "生气",
    "愤怒",
    "讨厌",
    "烦",
    "恼火",
    "害怕",
    "担心",
    "紧张",
    "焦虑",
    "恐惧",
    "爱",
    "喜欢",
    "想念",
    "思念",
    "牵挂",
)
_IMPORTANT_CATEGORIES = (
    "personal_info",
    "preferences",
    "important_events",
    "relationships",
    "goals",
    "commitments",
)


class MemoryScorer:
    """
    记忆重要性评分器

    功能：
    1. 自动评估记忆的重要性（0-1分）
    2. 基于时间的遗忘曲线
    3. 基于访问频率的强化
    4. 智能记忆淘汰
    """

    def __init__(self):
        """初始化记忆评分器"""
        # 重要性关键词权重
        self.importance_keywords = {
            # 个人信息 (高权重)
            "名字": 1.0, "姓名": 1.0, "叫": 0.8,
            "生日": 1.0, "年龄": 0.9, "住址": 0.9, "地址": 0.9,
            "电话": 0.9, "邮箱": 0.9,

            # 关系和情感 (高权重)
            "爱": 0.9, "喜欢": 0.8, "讨厌": 0.8, "恨": 0.8,
            "朋友": 0.7, "家人": 0.9, "父母": 0.9,

            # 重要事件 (中高权重)
            "重要": 0.8, "记住": 0.8, "别忘": 0.8,
            "一定要": 0.7, "必须": 0.7, "千万": 0.7,

            # 时间约定 (中高权重)
            "明天": 0.6, "后天": 0.6, "下周": 0.7, "下个月": 0.7,
            "约定": 0.8, "约好": 0.8, "提醒": 0.7,

            # 偏好和习惯 (中权重)
            "喜欢吃": 0.6, "爱吃": 0.6, "不吃": 0.5,
            "习惯": 0.6, "经常": 0.5, "总是": 0.5,

            # 目标和计划 (中权重)
            "目标": 0.7, "计划": 0.6, "打算": 0.6,
            "想要": 0.5, "希望": 0.5,
        }

        logger.info("记忆评分器初始化完成")

    def score_memory(
        self,
        content: str,
        metadata: Optional[Dict] = None,
    ) -> float:
        """
        评估记忆的重要性

        Args:
            content: 记忆内容
            metadata: 元数据（可选）

        Returns:
            float: 重要性分数 (0-1)
        """
        score = 0.0

        # 1. 基于关键词的评分
        keyword_score = self._score_by_keywords(content)
        score += keyword_score * 0.4  # 权重40%

        # 2. 基于内容长度的评分（长内容可能更重要）
        length_score = min(len(content) / 200, 1.0)  # 200字符为满分
        score += length_score * 0.1  # 权重10%

        # 3. 基于情感强度的评分
        emotion_score = self._score_by_emotion(content)
        score += emotion_score * 0.3  # 权重30%

        # 4. 基于元数据的评分
        if metadata:
            metadata_score = self._score_by_metadata(metadata)
            score += metadata_score * 0.2  # 权重20%

        # 限制在 0-1 范围
        score = max(0.0, min(1.0, score))

        logger.debug(f"记忆评分: {score:.2f}")
        return score

    def _score_by_keywords(self, content: str) -> float:
        """
        基于关键词评分

        Args:
            content: 内容

        Returns:
            float: 关键词分数 (0-1)
        """
        max_score = 0.0

        for keyword, weight in self.importance_keywords.items():
            if keyword in content:
                max_score = max(max_score, weight)

        return max_score

    @staticmethod
    def _score_by_emotion(content: str) -> float:
        """
        基于情感强度评分

        Args:
            content: 内容

        Returns:
            float: 情感分数 (0-1)
        """
        score = 0.0

        # 检查强情感词
        strong_count = sum(1 for word in _STRONG_EMOTIONS if word in content)
        score += min(strong_count * 0.2, 0.5)

        # 检查情感词
        emotion_count = sum(1 for word in _EMOTION_WORDS if word in content)
        score += min(emotion_count * 0.15, 0.5)

        return min(score, 1.0)

    @staticmethod
    def _score_by_metadata(metadata: Dict) -> float:
        """
        基于元数据评分

        Args:
            metadata: 元数据

        Returns:
            float: 元数据分数 (0-1)
        """
        score = 0.0

        # 如果有明确的重要性标记
        if "importance" in metadata:
            return float(metadata["importance"])

        # 如果有类别标记
        if metadata.get("category") in _IMPORTANT_CATEGORIES:
            score += 0.7

        # 如果有访问次数
        if "access_count" in metadata:
            access_score = min(metadata["access_count"] / 10, 0.3)
            score += access_score

        return min(score, 1.0)

    def calculate_decay_score(
        self,
        original_score: float,
        created_at: datetime,
        last_accessed: Optional[datetime] = None,
        access_count: int = 0,
    ) -> float:
        """
        计算衰减后的分数（遗忘曲线）

        Args:
            original_score: 原始分数
            created_at: 创建时间
            last_accessed: 最后访问时间
            access_count: 访问次数

        Returns:
            float: 衰减后的分数
        """
        now = datetime.now()

        # 1. 基于时间的衰减
        days_since_creation = (now - created_at).days
        time_decay = self._calculate_time_decay(days_since_creation)

        # 2. 基于访问的强化
        access_boost = min(access_count * 0.05, 0.3)  # 最多提升30%

        # 3. 基于最后访问时间的衰减
        recency_factor = 1.0
        if last_accessed:
            days_since_access = (now - last_accessed).days
            recency_factor = self._calculate_time_decay(days_since_access)

        # 综合计算
        decayed_score = original_score * time_decay * recency_factor + access_boost

        return max(0.0, min(1.0, decayed_score))

    @staticmethod
    def _calculate_time_decay(days: int) -> float:
        """
        计算时间衰减因子（艾宾浩斯遗忘曲线）

        Args:
            days: 天数

        Returns:
            float: 衰减因子 (0-1)
        """
        # 简化的艾宾浩斯遗忘曲线
        # R: 记忆保持率, t: 时间, S: 记忆强度常数

        import math

        S = 30  # 30天为半衰期
        decay_factor = math.exp(-days / S)

        return decay_factor

    @staticmethod
    def should_forget(
        score: float,
        threshold: float = 0.1,
    ) -> bool:
        """
        判断是否应该遗忘这条记忆

        Args:
            score: 当前分数
            threshold: 遗忘阈值

        Returns:
            bool: 是否应该遗忘
        """
        return score < threshold

    def prioritize_memories(
        self,
        memories: List[Dict],
        max_count: int = 100,
    ) -> List[Dict]:
        """
        对记忆进行优先级排序和淘汰

        Args:
            memories: 记忆列表
            max_count: 最大保留数量

        Returns:
            List[Dict]: 排序后的记忆列表
        """
        # 为每条记忆计算当前分数
        scored_memories = []
        for memory in memories:
            metadata = memory.get("metadata", {})

            # 获取原始分数
            original_score = metadata.get("importance", 0.5)

            # 获取时间信息
            created_at = datetime.fromisoformat(
                metadata.get("created_at", datetime.now().isoformat())
            )
            last_accessed = None
            if "last_accessed" in metadata:
                last_accessed = datetime.fromisoformat(metadata["last_accessed"])
            access_count = metadata.get("access_count", 0)

            # 计算衰减后的分数
            current_score = self.calculate_decay_score(
                original_score,
                created_at,
                last_accessed,
                access_count,
            )

            scored_memories.append({
                "memory": memory,
                "score": current_score,
            })

        # 按分数排序
        scored_memories.sort(key=lambda x: x["score"], reverse=True)

        # 保留前 max_count 条
        top_memories = [item["memory"] for item in scored_memories[:max_count]]

        # 记录被遗忘的记忆数量
        forgotten_count = len(memories) - len(top_memories)
        if forgotten_count > 0:
            logger.info(f"遗忘了 {forgotten_count} 条低重要性记忆")

        return top_memories

    @staticmethod
    def get_memory_stats(memories: List[Dict]) -> Dict:
        """
        获取记忆统计信息

        Args:
            memories: 记忆列表

        Returns:
            Dict: 统计信息
        """
        if not memories:
            return {
                "total": 0,
                "avg_score": 0.0,
                "high_importance": 0,
                "medium_importance": 0,
                "low_importance": 0,
            }

        scores = []
        for memory in memories:
            metadata = memory.get("metadata", {})
            score = metadata.get("importance", 0.5)
            scores.append(score)

        avg_score = sum(scores) / len(scores)
        high_count = sum(1 for s in scores if s >= 0.7)
        medium_count = sum(1 for s in scores if 0.4 <= s < 0.7)
        low_count = sum(1 for s in scores if s < 0.4)

        return {
            "total": len(memories),
            "avg_score": f"{avg_score:.2f}",
            "high_importance": high_count,
            "medium_importance": medium_count,
            "low_importance": low_count,
        }
