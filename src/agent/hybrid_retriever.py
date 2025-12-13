"""
混合检索系统 (v2.30.40)

结合向量检索和 BM25 关键词检索，提供更准确的知识检索能力。

功能：
- 混合检索（向量 + BM25）
- 多维度重排序
- 查询扩展
- 上下文感知检索
"""

import math
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from src.utils.logger import get_logger

logger = get_logger(__name__)

_BM25_IMPORT_ERROR: Optional[BaseException] = None
try:
    from rank_bm25 import BM25Okapi

    HAS_RANK_BM25 = True
except Exception as exc:  # pragma: no cover - 环境依赖差异
    HAS_RANK_BM25 = False
    _BM25_IMPORT_ERROR = exc
    BM25Okapi = None  # type: ignore[assignment]

_WARNED_BM25_UNAVAILABLE = False

from src.config.settings import settings

_TOKENIZE_CLEAN_RE = re.compile(r"[^\w\s]+")

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
        logger.warning("LangChain LLM 依赖导入失败，查询扩展功能不可用: %s", exc)
    else:
        logger.debug("LangChain LLM 依赖导入失败（可忽略）: %s", exc)


class HybridRetriever:
    """
    混合检索器 - 结合向量检索和关键词检索
    
    特点：
    - 向量检索：语义相似度匹配
    - BM25 检索：关键词精确匹配
    - 自适应融合：根据查询类型调整权重
    """
    
    def __init__(self, vectorstore, documents: List[Dict[str, Any]]):
        """
        初始化混合检索器
        
        Args:
            vectorstore: ChromaDB 向量存储
            documents: 文档列表（包含 content 和 metadata）
        """
        self.vectorstore = vectorstore
        self.documents = documents
        
        # 构建 BM25 索引
        if documents:
            if BM25Okapi is None:
                self.bm25 = None
                global _WARNED_BM25_UNAVAILABLE
                if not _WARNED_BM25_UNAVAILABLE:
                    _WARNED_BM25_UNAVAILABLE = True
                    if _BM25_IMPORT_ERROR:
                        logger.warning(
                            "rank-bm25 导入失败，BM25 索引未构建（仅向量检索）: %s",
                            _BM25_IMPORT_ERROR,
                        )
                    else:
                        logger.warning("rank-bm25 不可用，BM25 索引未构建（仅向量检索）")
            else:
                # 简单分词（中文按字符，英文按空格）
                tokenized_docs = [self._tokenize(doc.get("content", "")) for doc in documents]
                self.bm25 = BM25Okapi(tokenized_docs)
                logger.info("BM25 索引构建完成，文档数量: %d", len(documents))
        else:
            self.bm25 = None
            logger.warning("文档列表为空，BM25 索引未构建")
    
    def _tokenize(self, text: str) -> List[str]:
        """
        简单分词
        
        Args:
            text: 文本
        
        Returns:
            List[str]: 分词结果
        """
        # 中文按字符分词，英文按空格分词
        tokens = []
        
        # 移除标点符号
        text = _TOKENIZE_CLEAN_RE.sub(" ", text)
        
        # 分词
        for word in text.split():
            if word.strip():
                # 英文单词
                if word.isascii():
                    tokens.append(word.lower())
                else:
                    # 中文按字符
                    tokens.extend(list(word))
        
        return tokens
    
    def search(
        self,
        query: str,
        k: int = 5,
        alpha: float = 0.5,
        category: Optional[str] = None,
        threshold: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """
        混合检索
        
        Args:
            query: 查询文本
            k: 返回数量
            alpha: 向量检索权重（0-1），1-alpha 为关键词检索权重
            category: 类别过滤
            threshold: 相似度阈值
        
        Returns:
            List[Dict]: 检索结果
        """
        if not self.vectorstore:
            logger.warning("向量存储未初始化")
            return []
        
        if threshold is None:
            threshold = settings.agent.books_thresholds
        
        try:
            # 1. 向量检索
            vector_results = self.vectorstore.similarity_search_with_score(query, k=k*3)

            # 2. BM25 关键词检索
            bm25_scores = []
            if self.bm25 and self.documents:
                tokenized_query = self._tokenize(query)
                bm25_scores = self.bm25.get_scores(tokenized_query)
            effective_alpha = alpha if bm25_scores else 1.0

            # 3. 融合分数
            combined_results = self._combine_scores(
                vector_results, bm25_scores, effective_alpha, category, threshold
            )

            # 4. 排序并返回 top-k
            combined_results.sort(key=lambda x: x["score"], reverse=True)

            result_count = min(k, len(combined_results))
            logger.debug("混合检索完成: query=%.80s 结果数=%d", query, result_count)
            return combined_results[:k]

        except Exception as e:
            logger.exception("混合检索失败: %s", e)
            return []
    
    def _combine_scores(
        self,
        vector_results: List[Tuple],
        bm25_scores: List[float],
        alpha: float,
        category: Optional[str],
        threshold: float,
    ) -> List[Dict[str, Any]]:
        """
        融合向量检索和 BM25 检索的分数
        
        Args:
            vector_results: 向量检索结果 [(doc, score), ...]
            bm25_scores: BM25 分数列表
            alpha: 向量检索权重
            category: 类别过滤
            threshold: 相似度阈值
        
        Returns:
            List[Dict]: 融合后的结果
        """
        # 归一化 BM25 分数
        normalized_bm25 = self._normalize_scores(bm25_scores) if len(bm25_scores) > 0 else []

        # 构建结果字典
        results_dict = {}

        # 处理向量检索结果
        for doc, score in vector_results:
            doc_id = doc.metadata.get("id")
            if not doc_id:
                continue

            # 类别过滤
            if category and doc.metadata.get("category") != category:
                continue

            # 计算向量相似度（ChromaDB 返回的是距离，需要转换）
            similarity = 1.0 - score

            # 应用阈值
            if similarity < threshold:
                continue

            results_dict[doc_id] = {
                "id": doc_id,
                "content": doc.page_content,
                "metadata": doc.metadata,
                "vector_score": similarity,
                "bm25_score": 0.0,
                "score": alpha * similarity,
            }

        # 处理 BM25 检索结果
        if normalized_bm25 and self.documents:
            for i, bm25_score in enumerate(normalized_bm25):
                if i >= len(self.documents):
                    break

                doc = self.documents[i]
                doc_id = doc.get("metadata", {}).get("id")
                if not doc_id:
                    continue

                # 类别过滤
                if category and doc.get("metadata", {}).get("category") != category:
                    continue

                if doc_id in results_dict:
                    # 已存在，更新分数
                    results_dict[doc_id]["bm25_score"] = bm25_score
                    results_dict[doc_id]["score"] += (1 - alpha) * bm25_score
                else:
                    # 新结果
                    results_dict[doc_id] = {
                        "id": doc_id,
                        "content": doc.get("content", ""),
                        "metadata": doc.get("metadata", {}),
                        "vector_score": 0.0,
                        "bm25_score": bm25_score,
                        "score": (1 - alpha) * bm25_score,
                    }

        return list(results_dict.values())

    def _normalize_scores(self, scores: List[float]) -> List[float]:
        """
        归一化分数到 [0, 1]

        Args:
            scores: 原始分数列表

        Returns:
            List[float]: 归一化后的分数
        """
        # 转换为列表（如果是 numpy 数组）
        if hasattr(scores, 'tolist'):
            scores = scores.tolist()

        # 确保是列表
        if not isinstance(scores, list):
            scores = list(scores)

        # 检查是否为空
        if len(scores) == 0:
            return []

        min_score = min(scores)
        max_score = max(scores)

        if max_score == min_score:
            return [1.0] * len(scores)

        return [(float(s) - min_score) / (max_score - min_score) for s in scores]


class Reranker:
    """
    重排序器 - 使用多维度评分重新排序检索结果

    评分维度：
    - 基础相似度
    - 时效性（新知识优先）
    - 重要性（用户标记）
    - 使用频率（热门知识优先）
    - 上下文相关性
    """

    def rerank(
        self,
        results: List[Dict[str, Any]],
        query: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        重排序

        Args:
            results: 初始检索结果
            query: 查询文本
            context: 上下文信息（对话历史、用户偏好等）

        Returns:
            List[Dict]: 重排序后的结果
        """
        if not results:
            return []

        context = context or {}

        for result in results:
            # 基础相似度分数
            base_score = result.get("score", 0.5)

            # 时效性分数
            recency_score = self._calculate_recency_score(result)

            # 重要性分数
            importance_score = result.get("metadata", {}).get("importance", 0.5)

            # 使用频率分数
            usage_score = self._calculate_usage_score(result)

            # 上下文相关性分数
            context_score = self._calculate_context_score(result, context)

            # 综合评分（可配置权重）
            final_score = (
                base_score * 0.3 +
                recency_score * 0.15 +
                importance_score * 0.2 +
                usage_score * 0.15 +
                context_score * 0.2
            )

            result["final_score"] = final_score
            result["score_breakdown"] = {
                "base": base_score,
                "recency": recency_score,
                "importance": importance_score,
                "usage": usage_score,
                "context": context_score,
            }

        # 按综合评分排序
        results.sort(key=lambda x: x["final_score"], reverse=True)

        logger.debug("重排序完成: 结果数=%d", len(results))
        return results

    def _calculate_recency_score(self, result: Dict[str, Any]) -> float:
        """
        计算时效性分数

        Args:
            result: 检索结果

        Returns:
            float: 时效性分数 (0-1)
        """
        timestamp = result.get("metadata", {}).get("timestamp")
        if not timestamp:
            return 0.5  # 默认中性

        try:
            created_time = datetime.fromisoformat(timestamp)
            now = datetime.now()
            days_old = (now - created_time).days

            # 指数衰减：一年后衰减到 37%
            return math.exp(-days_old / 365)
        except:
            return 0.5

    def _calculate_usage_score(self, result: Dict[str, Any]) -> float:
        """
        计算使用频率分数

        Args:
            result: 检索结果

        Returns:
            float: 使用频率分数 (0-1)
        """
        usage_count = result.get("metadata", {}).get("usage_count", 0)

        # 对数归一化：假设最大使用次数为 100
        if usage_count <= 0:
            return 0.0

        return min(math.log(usage_count + 1) / math.log(100), 1.0)

    def _calculate_context_score(
        self,
        result: Dict[str, Any],
        context: Dict[str, Any]
    ) -> float:
        """
        计算上下文相关性分数

        Args:
            result: 检索结果
            context: 上下文信息

        Returns:
            float: 上下文相关性分数 (0-1)
        """
        # 检查知识类别是否与当前对话主题相关
        current_topic = context.get("topic", "")
        knowledge_category = result.get("metadata", {}).get("category", "")

        if not current_topic or not knowledge_category:
            return 0.5  # 默认中性

        # 简单的主题匹配
        if current_topic.lower() in knowledge_category.lower():
            return 1.0

        # 检查关键词匹配
        context_keywords = set(context.get("keywords", []))
        knowledge_keywords = set(result.get("metadata", {}).get("keywords", "").split(","))

        if context_keywords and knowledge_keywords:
            common_keywords = context_keywords & knowledge_keywords
            if common_keywords:
                return len(common_keywords) / len(context_keywords)

        return 0.5


class QueryExpander:
    """
    查询扩展器 - 使用 LLM 扩展查询

    功能：
    - 同义词替换
    - 相关概念补充
    - 多角度描述
    """

    def __init__(self):
        """初始化查询扩展器"""
        self.enabled = HAS_LANGCHAIN_LLM and settings.agent.use_llm_for_knowledge_extraction

    def expand_query(self, query: str, max_expansions: int = 3) -> List[str]:
        """
        扩展查询

        Args:
            query: 原始查询
            max_expansions: 最大扩展数量

        Returns:
            List[str]: 扩展后的查询列表（包含原始查询）
        """
        if not self.enabled:
            return [query]

        try:
            prompt = ChatPromptTemplate.from_messages([
                ("system", """你是一个查询扩展专家。请为给定的查询生成 {max_expansions} 个相关的扩展查询。

扩展规则：
1. 使用同义词替换
2. 添加相关概念
3. 从不同角度描述
4. 保持语义相关性

请以 JSON 格式返回：
{{
    "expanded_queries": ["查询1", "查询2", "查询3"]
}}"""),
                ("human", "原始查询: {query}"),
            ])

            llm = get_llm()
            chain = prompt | llm

            result = chain.invoke({
                "query": query,
                "max_expansions": max_expansions
            })

            # 解析 JSON
            import json
            data = json.loads(result.content)
            expanded = data.get("expanded_queries", [])

            # 确保包含原始查询
            if query not in expanded:
                expanded.insert(0, query)

            logger.debug("查询扩展完成: 原始=%.80s 扩展=%d个", query, len(expanded))
            return expanded[:max_expansions + 1]

        except Exception as e:
            logger.warning("查询扩展失败: %s", e)
            return [query]
