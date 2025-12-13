"""
知识质量管理系统 (v2.30.41)

提供知识评分、验证和冲突检测功能，确保知识库的质量和准确性。

功能：
- 知识质量评分
- 知识验证
- 知识冲突检测
- 知识过期检测
"""

import math
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.config.settings import settings
from src.utils.logger import get_logger

logger = get_logger(__name__)

# 尝试导入 LangChain LLM（不要用“未安装”掩盖真实导入失败原因）
_LANGCHAIN_LLM_IMPORT_ERROR: Optional[BaseException] = None
try:
    from langchain_core.prompts import ChatPromptTemplate
    from src.llm.factory import get_llm
    HAS_LANGCHAIN_LLM = True
except Exception as exc:  # pragma: no cover - 环境依赖差异
    HAS_LANGCHAIN_LLM = False
    _LANGCHAIN_LLM_IMPORT_ERROR = exc
    ChatPromptTemplate = None  # type: ignore[assignment]
    get_llm = None  # type: ignore[assignment]
    if getattr(settings.agent, "use_llm_for_knowledge_extraction", False):
        logger.warning("LangChain LLM 依赖导入失败，冲突检测功能不可用: %s", exc)
    else:
        logger.debug("LangChain LLM 依赖导入失败（可忽略）: %s", exc)


class KnowledgeScorer:
    """
    知识评分器
    
    评分维度：
    - 使用频率（25%）
    - 用户反馈（30%）
    - 内容质量（30%）
    - 来源可信度（15%）
    """
    
    def calculate_quality_score(self, knowledge: Dict[str, Any]) -> float:
        """
        计算知识质量分数
        
        Args:
            knowledge: 知识条目
        
        Returns:
            float: 质量分数 (0-1)
        """
        # 使用频率分数
        usage_score = self._calculate_usage_score(knowledge)
        
        # 用户反馈分数
        feedback_score = self._calculate_feedback_score(knowledge)
        
        # 内容质量分数
        content_score = self._calculate_content_score(knowledge)
        
        # 来源可信度分数
        source_score = self._calculate_source_score(knowledge)
        
        # 综合评分
        quality_score = (
            usage_score * 0.25 +
            feedback_score * 0.3 +
            content_score * 0.3 +
            source_score * 0.15
        )
        
        return quality_score
    
    def _calculate_usage_score(self, knowledge: Dict[str, Any]) -> float:
        """使用频率分数"""
        usage_count = knowledge.get("usage_count", 0)
        if usage_count <= 0:
            return 0.0
        # 对数归一化：假设最大使用次数为 100
        return min(math.log(usage_count + 1) / math.log(100), 1.0)
    
    def _calculate_feedback_score(self, knowledge: Dict[str, Any]) -> float:
        """用户反馈分数"""
        positive = knowledge.get("positive_feedback", 0)
        negative = knowledge.get("negative_feedback", 0)
        total = positive + negative
        
        if total == 0:
            return 0.5  # 默认中性
        
        return positive / total
    
    def _calculate_content_score(self, knowledge: Dict[str, Any]) -> float:
        """内容质量分数"""
        content = knowledge.get("content", "")
        
        # 长度分数（太短或太长都不好）
        length = len(content)
        if length < 10:
            length_score = 0.3
        elif length < 50:
            length_score = 0.6
        elif length < 500:
            length_score = 1.0
        else:
            length_score = 0.8
        
        # 结构分数（是否有标点、段落等）
        has_punctuation = any(p in content for p in "。！？，、；：.!?,;:")
        structure_score = 1.0 if has_punctuation else 0.5
        
        # 关键词分数
        keywords = knowledge.get("keywords", "")
        keyword_score = 1.0 if keywords else 0.5
        
        return (length_score + structure_score + keyword_score) / 3
    
    def _calculate_source_score(self, knowledge: Dict[str, Any]) -> float:
        """来源可信度分数"""
        source = knowledge.get("source", "manual")
        
        source_scores = {
            "manual": 0.9,  # 手动添加，可信度高
            "conversation:llm": 0.8,  # LLM 提取，较可信
            "conversation": 0.6,  # 规则提取，一般
            "file": 0.7,  # 文件导入，较可信
            "mcp": 0.8,  # MCP 工具，较可信
            "import": 0.5,  # 批量导入，需验证
        }
        
        return source_scores.get(source, 0.5)


class KnowledgeValidator:
    """
    知识验证器
    
    验证内容：
    - 基本验证（标题、内容）
    - 内容质量验证
    - 一致性验证
    - 时效性验证
    """
    
    def validate_knowledge(self, knowledge: Dict[str, Any]) -> Dict[str, Any]:
        """
        验证知识

        Args:
            knowledge: 知识条目

        Returns:
            Dict: 验证结果
        """
        results = {
            "is_valid": True,
            "issues": [],
            "suggestions": [],
            "quality_score": 0.0,
        }

        # 1. 基本验证
        if not knowledge.get("title"):
            results["is_valid"] = False
            results["issues"].append("缺少标题")

        if not knowledge.get("content"):
            results["is_valid"] = False
            results["issues"].append("缺少内容")

        # 2. 内容质量验证
        content = knowledge.get("content", "")
        if len(content) < 10:
            results["issues"].append("内容过短")
            results["suggestions"].append("建议补充更多细节")

        if len(content) > 2000:
            results["issues"].append("内容过长")
            results["suggestions"].append("建议拆分为多个知识条目")

        # 3. 一致性验证
        consistency_issues = self._check_consistency(knowledge)
        if consistency_issues:
            results["issues"].extend(consistency_issues)

        # 4. 时效性验证
        if self._is_outdated(knowledge):
            results["issues"].append("知识可能已过时")
            results["suggestions"].append("建议更新或验证")

        # 5. 计算质量分数
        scorer = KnowledgeScorer()
        results["quality_score"] = scorer.calculate_quality_score(knowledge)

        return results

    def _check_consistency(self, knowledge: Dict[str, Any]) -> List[str]:
        """检查一致性"""
        issues = []

        # 检查标题和内容是否一致
        title = knowledge.get("title", "").lower()
        content = knowledge.get("content", "").lower()

        if not title or not content:
            return issues

        # 简单的关键词匹配
        title_words = set(title.split())
        content_words = set(content.split())

        # 移除常见停用词
        stop_words = {"的", "了", "是", "在", "和", "与", "或", "a", "an", "the", "is", "are", "was", "were"}
        title_words = title_words - stop_words
        content_words = content_words - stop_words

        if title_words:
            common_words = title_words & content_words
            if len(common_words) < len(title_words) * 0.3:
                issues.append("标题和内容相关性较低")

        return issues

    def _is_outdated(self, knowledge: Dict[str, Any]) -> bool:
        """检查是否过时"""
        timestamp = knowledge.get("timestamp")
        if not timestamp:
            return False

        try:
            created_time = datetime.fromisoformat(timestamp)
            now = datetime.now()
            days_old = (now - created_time).days

            # 超过一年认为可能过时
            return days_old > 365
        except:
            return False


class ConflictDetector:
    """
    冲突检测器

    检测知识之间的矛盾和冲突
    """

    def __init__(self):
        """初始化冲突检测器"""
        self.enabled = HAS_LANGCHAIN_LLM and settings.agent.use_llm_for_knowledge_extraction

    def detect_conflicts(
        self,
        knowledge: Dict[str, Any],
        existing_knowledge: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        检测知识冲突

        Args:
            knowledge: 新知识
            existing_knowledge: 现有知识列表

        Returns:
            List[Dict]: 冲突列表
        """
        if not self.enabled:
            return []

        conflicts = []

        for existing in existing_knowledge:
            # 检查是否是相同主题
            if not self._is_same_topic(knowledge, existing):
                continue

            # 检查是否有矛盾
            if self._has_contradiction(knowledge, existing):
                conflicts.append({
                    "existing_knowledge": existing,
                    "conflict_type": "contradiction",
                    "confidence": 0.8,
                })

        return conflicts

    def _is_same_topic(self, k1: Dict[str, Any], k2: Dict[str, Any]) -> bool:
        """检查是否是相同主题"""
        # 检查类别
        if k1.get("category") == k2.get("category"):
            # 检查关键词
            k1_keywords = set(k1.get("keywords", "").split(","))
            k2_keywords = set(k2.get("keywords", "").split(","))

            common_keywords = k1_keywords & k2_keywords
            if len(common_keywords) > 0:
                return True

        return False

    def _has_contradiction(self, k1: Dict[str, Any], k2: Dict[str, Any]) -> bool:
        """检测是否有矛盾"""
        if not self.enabled:
            return False

        try:
            prompt = ChatPromptTemplate.from_messages([
                ("system", """你是一个知识冲突检测专家。请判断两条知识是否存在矛盾。

判断规则：
1. 如果两条知识描述的是同一事物，但内容相互矛盾，返回 true
2. 如果两条知识描述的是不同事物，或内容不矛盾，返回 false
3. 如果只是补充或细化，不算矛盾

请以 JSON 格式返回：
{{
    "has_contradiction": true/false,
    "reason": "矛盾原因或说明"
}}"""),
                ("human", "知识1: {title1}\n{content1}\n\n知识2: {title2}\n{content2}"),
            ])

            llm = get_llm()
            chain = prompt | llm

            result = chain.invoke({
                "title1": k1.get("title", ""),
                "content1": k1.get("content", ""),
                "title2": k2.get("title", ""),
                "content2": k2.get("content", ""),
            })

            import json
            data = json.loads(result.content)
            return data.get("has_contradiction", False)

        except Exception as e:
            logger.warning(f"冲突检测失败: {e}")
            return False


class KnowledgeQualityManager:
    """
    知识质量管理器

    整合评分、验证和冲突检测功能
    """

    def __init__(self):
        """初始化知识质量管理器"""
        self.scorer = KnowledgeScorer()
        self.validator = KnowledgeValidator()
        self.conflict_detector = ConflictDetector()

    def assess_knowledge(
        self,
        knowledge: Dict[str, Any],
        existing_knowledge: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        全面评估知识

        Args:
            knowledge: 知识条目
            existing_knowledge: 现有知识列表（用于冲突检测）

        Returns:
            Dict: 评估结果
        """
        # 验证
        validation_result = self.validator.validate_knowledge(knowledge)

        # 评分
        quality_score = self.scorer.calculate_quality_score(knowledge)

        # 冲突检测
        conflicts = []
        if existing_knowledge:
            conflicts = self.conflict_detector.detect_conflicts(
                knowledge, existing_knowledge
            )

        return {
            "is_valid": validation_result["is_valid"],
            "quality_score": quality_score,
            "issues": validation_result["issues"],
            "suggestions": validation_result["suggestions"],
            "conflicts": conflicts,
            "has_conflicts": len(conflicts) > 0,
        }
