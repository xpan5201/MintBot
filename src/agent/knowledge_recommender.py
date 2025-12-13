"""
知识推荐系统模块 (v2.30.42)

功能：
1. 上下文感知推荐 - 根据对话上下文推荐相关知识
2. 主动知识推送 - 在合适的时机主动推送知识
3. 知识使用统计 - 跟踪知识使用情况
4. 推荐理由说明 - 解释为什么推荐这些知识

作者: AI Assistant
日期: 2025-11-16
版本: v2.30.42
"""

import json
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
from pathlib import Path
from src.utils.logger import get_logger

logger = get_logger(__name__)


class KnowledgeRecommender:
    """
    知识推荐器 - 基于上下文推荐相关知识
    
    推荐策略：
    1. 主题相关性 - 与当前对话主题相关
    2. 时效性 - 最近使用或更新的知识
    3. 质量分数 - 高质量知识优先
    4. 使用频率 - 常用知识优先
    5. 用户偏好 - 根据历史反馈调整
    """
    
    def __init__(self):
        """初始化推荐器"""
        self.recommendation_history = []  # 推荐历史
        self.user_preferences = {}  # 用户偏好
        logger.info("知识推荐器初始化完成")
    
    def recommend(
        self,
        context: Dict[str, Any],
        all_knowledge: List[Dict[str, Any]],
        k: int = 5,
        min_score: float = 0.3,
    ) -> List[Dict[str, Any]]:
        """
        推荐知识
        
        Args:
            context: 上下文信息
                - query: 当前查询
                - topic: 当前主题
                - keywords: 关键词列表
                - recent_topics: 最近讨论的主题
                - user_id: 用户ID（可选）
            all_knowledge: 所有知识列表
            k: 推荐数量
            min_score: 最低推荐分数
        
        Returns:
            List[Dict]: 推荐的知识列表，包含推荐分数和理由
        """
        if not all_knowledge:
            return []
        
        # 提取上下文信息
        query = context.get("query", "")
        topic = context.get("topic", "")
        keywords = context.get("keywords", [])
        recent_topics = context.get("recent_topics", [])
        user_id = context.get("user_id", "default")
        
        # 计算每个知识的推荐分数
        scored_knowledge = []
        for knowledge in all_knowledge:
            score, reasons = self._calculate_recommendation_score(
                knowledge, query, topic, keywords, recent_topics, user_id
            )
            
            if score >= min_score:
                scored_knowledge.append({
                    **knowledge,
                    "recommendation_score": score,
                    "recommendation_reasons": reasons,
                })
        
        # 排序并返回 top-k
        scored_knowledge.sort(key=lambda x: x["recommendation_score"], reverse=True)
        recommendations = scored_knowledge[:k]
        
        # 记录推荐历史
        self._record_recommendation(user_id, recommendations, context)
        
        logger.debug(f"推荐知识: {len(recommendations)} 条")
        return recommendations
    
    def _calculate_recommendation_score(
        self,
        knowledge: Dict[str, Any],
        query: str,
        topic: str,
        keywords: List[str],
        recent_topics: List[str],
        user_id: str,
    ) -> Tuple[float, List[str]]:
        """
        计算推荐分数
        
        Returns:
            Tuple[float, List[str]]: (推荐分数, 推荐理由列表)
        """
        score = 0.0
        reasons = []
        
        # 1. 主题相关性 (30%)
        topic_score = self._calculate_topic_relevance(knowledge, topic, recent_topics)
        if topic_score > 0:
            score += topic_score * 0.3
            if topic_score > 0.7:
                reasons.append(f"与当前主题 '{topic}' 高度相关")
            elif topic_score > 0.4:
                reasons.append(f"与当前主题 '{topic}' 相关")
        
        # 2. 关键词匹配 (25%)
        keyword_score = self._calculate_keyword_match(knowledge, keywords, query)
        if keyword_score > 0:
            score += keyword_score * 0.25
            if keyword_score > 0.7:
                reasons.append("包含多个关键词")
            elif keyword_score > 0.4:
                reasons.append("包含相关关键词")
        
        # 3. 时效性 (15%)
        recency_score = self._calculate_recency(knowledge)
        if recency_score > 0:
            score += recency_score * 0.15
            if recency_score > 0.8:
                reasons.append("最近更新或使用")
        
        # 4. 质量分数 (15%)
        quality_score = knowledge.get("quality_score", 0.5)
        score += quality_score * 0.15
        if quality_score > 0.7:
            reasons.append("高质量知识")
        
        # 5. 使用频率 (10%)
        usage_score = self._calculate_usage_score(knowledge)
        if usage_score > 0:
            score += usage_score * 0.1
            if usage_score > 0.7:
                reasons.append("常用知识")
        
        # 6. 用户偏好 (5%)
        preference_score = self._calculate_user_preference(knowledge, user_id)
        if preference_score > 0:
            score += preference_score * 0.05
            if preference_score > 0.7:
                reasons.append("符合您的偏好")
        
        return score, reasons

    def _calculate_topic_relevance(
        self,
        knowledge: Dict[str, Any],
        topic: str,
        recent_topics: List[str],
    ) -> float:
        """计算主题相关性"""
        if not topic:
            return 0.0

        # 检查类别匹配
        category = knowledge.get("category", "")
        if category.lower() == topic.lower():
            return 1.0

        # 检查标题和内容中的主题词
        title = knowledge.get("title", "").lower()
        content = knowledge.get("content", "").lower()
        topic_lower = topic.lower()

        score = 0.0
        if topic_lower in title:
            score += 0.5
        if topic_lower in content:
            score += 0.3

        # 检查最近主题
        for recent_topic in recent_topics:
            if recent_topic.lower() in title or recent_topic.lower() in content:
                score += 0.2
                break

        return min(1.0, score)

    def _calculate_keyword_match(
        self,
        knowledge: Dict[str, Any],
        keywords: List[str],
        query: str,
    ) -> float:
        """计算关键词匹配度"""
        if not keywords and not query:
            return 0.0

        title = knowledge.get("title", "").lower()
        content = knowledge.get("content", "").lower()
        knowledge_keywords = knowledge.get("keywords", [])

        # 转换为小写
        keywords_lower = [k.lower() for k in keywords]
        knowledge_keywords_lower = [k.lower() for k in knowledge_keywords]

        # 计算匹配数量
        match_count = 0
        total_keywords = len(keywords_lower)

        for keyword in keywords_lower:
            if keyword in title or keyword in content or keyword in knowledge_keywords_lower:
                match_count += 1

        # 检查查询词
        if query:
            query_lower = query.lower()
            if query_lower in title:
                match_count += 0.5
            if query_lower in content:
                match_count += 0.3
            total_keywords += 1

        if total_keywords == 0:
            return 0.0

        return min(1.0, match_count / total_keywords)

    def _calculate_recency(self, knowledge: Dict[str, Any]) -> float:
        """计算时效性分数（指数衰减）"""
        try:
            # 获取最后更新时间或创建时间
            timestamp_str = knowledge.get("last_used") or knowledge.get("timestamp")
            if not timestamp_str:
                return 0.5  # 默认中等分数

            timestamp = datetime.fromisoformat(timestamp_str)
            now = datetime.now()
            days_ago = (now - timestamp).days

            # 指数衰减：7天内为1.0，之后每7天衰减一半
            decay_rate = 0.1  # 每天衰减率
            score = max(0.0, 1.0 - (days_ago * decay_rate))

            return score

        except Exception as e:
            logger.warning(f"计算时效性失败: {e}")
            return 0.5

    def _calculate_usage_score(self, knowledge: Dict[str, Any]) -> float:
        """计算使用频率分数（对数归一化）"""
        import math

        usage_count = knowledge.get("usage_count", 0)
        if usage_count == 0:
            return 0.0

        # 对数归一化：log(usage_count + 1) / log(100)
        score = min(1.0, math.log(usage_count + 1) / math.log(100))
        return score

    def _calculate_user_preference(
        self,
        knowledge: Dict[str, Any],
        user_id: str,
    ) -> float:
        """计算用户偏好分数"""
        if user_id not in self.user_preferences:
            return 0.5  # 默认中等分数

        preferences = self.user_preferences[user_id]

        # 检查类别偏好
        category = knowledge.get("category", "")
        category_pref = preferences.get("categories", {}).get(category, 0.5)

        # 检查来源偏好
        source = knowledge.get("source", "")
        source_pref = preferences.get("sources", {}).get(source, 0.5)

        # 综合偏好
        score = (category_pref + source_pref) / 2
        return score

    def _record_recommendation(
        self,
        user_id: str,
        recommendations: List[Dict[str, Any]],
        context: Dict[str, Any],
    ):
        """记录推荐历史"""
        record = {
            "user_id": user_id,
            "timestamp": datetime.now().isoformat(),
            "context": context,
            "recommendations": [
                {
                    "id": r.get("id"),
                    "title": r.get("title"),
                    "score": r.get("recommendation_score"),
                }
                for r in recommendations
            ],
        }

        self.recommendation_history.append(record)

        # 保持历史记录在合理范围内（最多1000条）
        if len(self.recommendation_history) > 1000:
            self.recommendation_history = self.recommendation_history[-1000:]

    def update_user_preference(
        self,
        user_id: str,
        knowledge: Dict[str, Any],
        is_positive: bool,
    ):
        """
        更新用户偏好

        Args:
            user_id: 用户ID
            knowledge: 知识条目
            is_positive: 是否为正面反馈
        """
        if user_id not in self.user_preferences:
            self.user_preferences[user_id] = {
                "categories": {},
                "sources": {},
            }

        preferences = self.user_preferences[user_id]

        # 更新类别偏好
        category = knowledge.get("category", "")
        if category:
            current_pref = preferences["categories"].get(category, 0.5)
            # 正面反馈增加0.1，负面反馈减少0.1
            adjustment = 0.1 if is_positive else -0.1
            new_pref = max(0.0, min(1.0, current_pref + adjustment))
            preferences["categories"][category] = new_pref

        # 更新来源偏好
        source = knowledge.get("source", "")
        if source:
            current_pref = preferences["sources"].get(source, 0.5)
            adjustment = 0.1 if is_positive else -0.1
            new_pref = max(0.0, min(1.0, current_pref + adjustment))
            preferences["sources"][source] = new_pref

        logger.debug(f"更新用户偏好: {user_id}, 类别={category}, 来源={source}, 正面={is_positive}")


class ProactiveKnowledgePusher:
    """
    主动知识推送器 - 在合适的时机主动推送知识

    推送策略：
    1. 话题转换时 - 检测到新话题时推送相关知识
    2. 知识缺失时 - 检测到用户可能不知道某些信息时推送
    3. 定期推送 - 定期推送高质量但未使用的知识
    4. 相关知识 - 在使用某个知识后推送相关知识
    """

    def __init__(self):
        """初始化推送器"""
        self.push_history = []  # 推送历史
        self.last_push_time = {}  # 每个用户的最后推送时间
        self.push_cooldown = 300  # 推送冷却时间（秒）
        logger.info("主动知识推送器初始化完成")

    def should_push(
        self,
        user_id: str,
        context: Dict[str, Any],
    ) -> bool:
        """
        判断是否应该推送知识

        Args:
            user_id: 用户ID
            context: 上下文信息

        Returns:
            bool: 是否应该推送
        """
        # 检查冷却时间
        if not self._check_cooldown(user_id):
            return False

        # 检查推送触发条件
        triggers = [
            self._detect_topic_change(context),
            self._detect_knowledge_gap(context),
            self._detect_related_knowledge_opportunity(context),
        ]

        return any(triggers)

    def push_knowledge(
        self,
        user_id: str,
        context: Dict[str, Any],
        all_knowledge: List[Dict[str, Any]],
        k: int = 3,
    ) -> List[Dict[str, Any]]:
        """
        推送知识

        Args:
            user_id: 用户ID
            context: 上下文信息
            all_knowledge: 所有知识列表
            k: 推送数量

        Returns:
            List[Dict]: 推送的知识列表
        """
        if not self.should_push(user_id, context):
            return []

        # 筛选候选知识
        candidates = self._filter_push_candidates(
            all_knowledge, context, user_id
        )

        if not candidates:
            return []

        # 选择最佳推送知识
        pushed_knowledge = candidates[:k]

        # 记录推送
        self._record_push(user_id, pushed_knowledge, context)

        # 更新最后推送时间
        self.last_push_time[user_id] = datetime.now()

        logger.info(f"主动推送知识: {len(pushed_knowledge)} 条")
        return pushed_knowledge

    def _check_cooldown(self, user_id: str) -> bool:
        """检查冷却时间"""
        if user_id not in self.last_push_time:
            return True

        last_push = self.last_push_time[user_id]
        now = datetime.now()
        elapsed = (now - last_push).total_seconds()

        return elapsed >= self.push_cooldown

    def _detect_topic_change(self, context: Dict[str, Any]) -> bool:
        """检测话题转换"""
        current_topic = context.get("topic", "")
        recent_topics = context.get("recent_topics", [])

        # 如果当前话题不在最近话题中，说明话题转换了
        if current_topic and current_topic not in recent_topics:
            return True

        return False

    def _detect_knowledge_gap(self, context: Dict[str, Any]) -> bool:
        """检测知识缺失"""
        # 检查用户消息中的疑问词
        user_message = context.get("user_message", "").lower()
        question_words = ["什么", "怎么", "为什么", "哪里", "谁", "如何", "吗", "？"]

        for word in question_words:
            if word in user_message:
                return True

        return False

    def _detect_related_knowledge_opportunity(self, context: Dict[str, Any]) -> bool:
        """检测相关知识推送机会"""
        # 如果刚刚使用了某个知识，可以推送相关知识
        last_used_knowledge = context.get("last_used_knowledge")
        if last_used_knowledge:
            return True

        return False

    def _filter_push_candidates(
        self,
        all_knowledge: List[Dict[str, Any]],
        context: Dict[str, Any],
        user_id: str,
    ) -> List[Dict[str, Any]]:
        """筛选推送候选知识"""
        candidates = []

        # 获取已推送的知识ID
        pushed_ids = set()
        for record in self.push_history:
            if record["user_id"] == user_id:
                pushed_ids.update([k["id"] for k in record["pushed_knowledge"]])

        # 筛选候选知识
        for knowledge in all_knowledge:
            knowledge_id = knowledge.get("id")

            # 跳过已推送的知识
            if knowledge_id in pushed_ids:
                continue

            # 检查质量分数
            quality_score = knowledge.get("quality_score", 0.5)
            if quality_score < 0.5:
                continue

            # 检查相关性
            relevance_score = self._calculate_push_relevance(knowledge, context)
            if relevance_score < 0.3:
                continue

            candidates.append({
                **knowledge,
                "push_relevance": relevance_score,
            })

        # 排序
        candidates.sort(key=lambda x: x["push_relevance"], reverse=True)

        return candidates

    def _calculate_push_relevance(
        self,
        knowledge: Dict[str, Any],
        context: Dict[str, Any],
    ) -> float:
        """计算推送相关性"""
        score = 0.0

        # 主题相关性
        topic = context.get("topic", "")
        category = knowledge.get("category", "")
        if topic and category.lower() == topic.lower():
            score += 0.5

        # 关键词匹配
        keywords = context.get("keywords", [])
        knowledge_keywords = knowledge.get("keywords", [])
        if keywords and knowledge_keywords:
            match_count = len(set(keywords) & set(knowledge_keywords))
            score += min(0.3, match_count * 0.1)

        # 质量分数
        quality_score = knowledge.get("quality_score", 0.5)
        score += quality_score * 0.2

        return score

    def _record_push(
        self,
        user_id: str,
        pushed_knowledge: List[Dict[str, Any]],
        context: Dict[str, Any],
    ):
        """记录推送历史"""
        record = {
            "user_id": user_id,
            "timestamp": datetime.now().isoformat(),
            "context": context,
            "pushed_knowledge": [
                {
                    "id": k.get("id"),
                    "title": k.get("title"),
                    "relevance": k.get("push_relevance"),
                }
                for k in pushed_knowledge
            ],
        }

        self.push_history.append(record)

        # 保持历史记录在合理范围内
        if len(self.push_history) > 1000:
            self.push_history = self.push_history[-1000:]


class KnowledgeUsageTracker:
    """
    知识使用统计器 - 跟踪知识使用情况

    统计内容：
    1. 使用次数 - 每个知识被使用的次数
    2. 使用时间 - 最后使用时间和使用时间分布
    3. 使用场景 - 在什么场景下使用
    4. 使用效果 - 用户反馈和满意度
    """

    def __init__(self, stats_file: Optional[Path] = None):
        """
        初始化统计器

        Args:
            stats_file: 统计数据文件路径
        """
        self.stats_file = stats_file or Path("data/memory/knowledge_usage_stats.json")
        self.stats_file.parent.mkdir(parents=True, exist_ok=True)

        # 加载统计数据
        self.stats = self._load_stats()

        logger.info("知识使用统计器初始化完成")

    def _load_stats(self) -> Dict[str, Any]:
        """加载统计数据"""
        if self.stats_file.exists():
            try:
                with open(self.stats_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"加载统计数据失败: {e}")

        return {
            "knowledge_stats": {},  # 每个知识的统计
            "global_stats": {  # 全局统计
                "total_usage": 0,
                "total_recommendations": 0,
                "total_pushes": 0,
            },
        }

    def _save_stats(self):
        """保存统计数据"""
        try:
            with open(self.stats_file, "w", encoding="utf-8") as f:
                json.dump(self.stats, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存统计数据失败: {e}")

    def record_usage(
        self,
        knowledge_id: str,
        context: Dict[str, Any],
        usage_type: str = "search",  # search, recommendation, push
    ):
        """
        记录知识使用

        Args:
            knowledge_id: 知识ID
            context: 使用上下文
            usage_type: 使用类型（search, recommendation, push）
        """
        if knowledge_id not in self.stats["knowledge_stats"]:
            self.stats["knowledge_stats"][knowledge_id] = {
                "usage_count": 0,
                "last_used": None,
                "usage_history": [],
                "contexts": [],
                "feedback_count": 0,
                "positive_feedback": 0,
            }

        knowledge_stats = self.stats["knowledge_stats"][knowledge_id]

        # 更新使用次数
        knowledge_stats["usage_count"] += 1

        # 更新最后使用时间
        knowledge_stats["last_used"] = datetime.now().isoformat()

        # 记录使用历史
        usage_record = {
            "timestamp": datetime.now().isoformat(),
            "type": usage_type,
            "context": {
                "topic": context.get("topic", ""),
                "keywords": context.get("keywords", []),
            },
        }
        knowledge_stats["usage_history"].append(usage_record)

        # 保持历史记录在合理范围内（最多100条）
        if len(knowledge_stats["usage_history"]) > 100:
            knowledge_stats["usage_history"] = knowledge_stats["usage_history"][-100:]

        # 更新全局统计
        self.stats["global_stats"]["total_usage"] += 1
        if usage_type == "recommendation":
            self.stats["global_stats"]["total_recommendations"] += 1
        elif usage_type == "push":
            self.stats["global_stats"]["total_pushes"] += 1

        # 保存
        self._save_stats()

        logger.debug(f"记录知识使用: {knowledge_id}, 类型={usage_type}")

    def record_feedback(
        self,
        knowledge_id: str,
        is_positive: bool,
    ):
        """
        记录用户反馈

        Args:
            knowledge_id: 知识ID
            is_positive: 是否为正面反馈
        """
        if knowledge_id not in self.stats["knowledge_stats"]:
            return

        knowledge_stats = self.stats["knowledge_stats"][knowledge_id]

        # 更新反馈统计
        knowledge_stats["feedback_count"] += 1
        if is_positive:
            knowledge_stats["positive_feedback"] += 1

        # 保存
        self._save_stats()

        logger.debug(f"记录知识反馈: {knowledge_id}, 正面={is_positive}")

    def get_knowledge_stats(self, knowledge_id: str) -> Optional[Dict[str, Any]]:
        """
        获取知识统计信息

        Args:
            knowledge_id: 知识ID

        Returns:
            Dict: 统计信息，不存在返回 None
        """
        return self.stats["knowledge_stats"].get(knowledge_id)

    def get_top_used_knowledge(self, k: int = 10) -> List[Dict[str, Any]]:
        """
        获取最常用的知识

        Args:
            k: 返回数量

        Returns:
            List[Dict]: 知识ID和使用次数列表
        """
        knowledge_list = [
            {
                "knowledge_id": kid,
                "usage_count": stats["usage_count"],
                "last_used": stats["last_used"],
            }
            for kid, stats in self.stats["knowledge_stats"].items()
        ]

        # 排序
        knowledge_list.sort(key=lambda x: x["usage_count"], reverse=True)

        return knowledge_list[:k]

    def get_unused_knowledge(
        self,
        all_knowledge_ids: List[str],
        days: int = 30,
    ) -> List[str]:
        """
        获取未使用的知识

        Args:
            all_knowledge_ids: 所有知识ID列表
            days: 多少天内未使用

        Returns:
            List[str]: 未使用的知识ID列表
        """
        unused = []
        cutoff_date = datetime.now() - timedelta(days=days)

        for kid in all_knowledge_ids:
            if kid not in self.stats["knowledge_stats"]:
                # 从未使用过
                unused.append(kid)
            else:
                stats = self.stats["knowledge_stats"][kid]
                last_used_str = stats.get("last_used")

                if not last_used_str:
                    unused.append(kid)
                else:
                    try:
                        last_used = datetime.fromisoformat(last_used_str)
                        if last_used < cutoff_date:
                            unused.append(kid)
                    except Exception:
                        pass

        return unused

    def get_global_stats(self) -> Dict[str, Any]:
        """获取全局统计信息"""
        return self.stats["global_stats"]

    def generate_report(self) -> str:
        """
        生成统计报告

        Returns:
            str: 统计报告文本
        """
        global_stats = self.stats["global_stats"]
        knowledge_count = len(self.stats["knowledge_stats"])

        # 获取最常用的知识
        top_used = self.get_top_used_knowledge(k=5)

        report = f"""
知识使用统计报告
================

全局统计:
- 总使用次数: {global_stats['total_usage']}
- 推荐次数: {global_stats['total_recommendations']}
- 主动推送次数: {global_stats['total_pushes']}
- 有使用记录的知识数: {knowledge_count}

最常用的知识 (Top 5):
"""

        for i, item in enumerate(top_used, 1):
            report += f"{i}. 知识ID: {item['knowledge_id']}, 使用次数: {item['usage_count']}\n"

        return report
