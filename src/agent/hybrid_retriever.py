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
import heapq
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

    def __init__(
        self,
        vectorstore: Any,
        documents: List[Dict[str, Any]],
        *,
        query_expander: Optional[Any] = None,
    ):
        """
        初始化混合检索器

        Args:
            vectorstore: ChromaDB 向量存储
            documents: 文档列表（包含 content 和 metadata）
        """
        self.vectorstore = vectorstore
        self.query_expander = query_expander

        self.documents = self._normalize_documents(documents)
        self._doc_index_by_id: Dict[str, int] = {}
        for idx, doc in enumerate(self.documents):
            doc_id = str(doc.get("metadata", {}).get("id") or "").strip()
            if doc_id and doc_id not in self._doc_index_by_id:
                self._doc_index_by_id[doc_id] = idx

        # 构建 BM25 索引
        if self.documents:
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
                tokenized_docs = [
                    self._tokenize(self._build_bm25_text(doc)) for doc in self.documents
                ]
                self.bm25 = BM25Okapi(tokenized_docs)
                logger.info("BM25 索引构建完成，文档数量: %d", len(self.documents))
        else:
            self.bm25 = None
            logger.warning("文档列表为空，BM25 索引未构建")

    @staticmethod
    def _normalize_keywords(raw: Any) -> str:
        if isinstance(raw, str):
            parts = [p.strip() for p in raw.split(",") if p.strip()]
        elif isinstance(raw, list):
            parts = [str(k).strip() for k in raw if str(k).strip()]
        else:
            parts = []
        return ",".join(parts)

    @classmethod
    def _normalize_documents(cls, documents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        normalized: List[Dict[str, Any]] = []
        for doc in documents or []:
            if not isinstance(doc, dict):
                continue

            metadata = doc.get("metadata")
            if isinstance(metadata, dict):
                meta = dict(metadata)
                doc_id = meta.get("id") or doc.get("id")
                if doc_id is None:
                    continue
                doc_id_str = str(doc_id).strip()
                if not doc_id_str:
                    continue
                title = str(meta.get("title") or doc.get("title") or "").strip()
                category = str(meta.get("category") or doc.get("category") or "").strip()
                source = str(meta.get("source") or doc.get("source") or "").strip()
                timestamp = str(meta.get("timestamp") or doc.get("timestamp") or "").strip()
                keywords = cls._normalize_keywords(
                    meta.get("keywords") or doc.get("keywords") or ""
                )

                content = str(doc.get("content") or "").strip()
                if title and content and not content.lstrip().startswith("【"):
                    content = f"【{title}】\n{content}"

                meta.update(
                    {
                        "id": doc_id_str,
                        "title": title,
                        "category": category,
                        "source": source,
                        "timestamp": timestamp,
                        "keywords": keywords,
                    }
                )
                normalized.append({"content": content, "metadata": meta})
                continue

            doc_id = doc.get("id")
            if doc_id is None:
                continue
            doc_id_str = str(doc_id).strip()
            if not doc_id_str:
                continue

            title = str(doc.get("title") or "").strip()
            content = str(doc.get("content") or "").strip()
            category = str(doc.get("category") or "").strip()
            source = str(doc.get("source") or "").strip()
            timestamp = str(doc.get("timestamp") or "").strip()
            keywords = cls._normalize_keywords(doc.get("keywords") or "")

            meta = {
                "id": doc_id_str,
                "title": title,
                "category": category,
                "source": source,
                "timestamp": timestamp,
                "keywords": keywords,
                "usage_count": doc.get("usage_count", 0),
                "update_count": doc.get("update_count", 0),
                "positive_feedback": doc.get("positive_feedback", 0),
                "negative_feedback": doc.get("negative_feedback", 0),
            }

            full_content = f"【{title}】\n{content}" if title and content else content
            normalized.append({"content": full_content, "metadata": meta})

        return normalized

    @staticmethod
    def _build_bm25_text(doc: Dict[str, Any]) -> str:
        """
        构建用于 BM25 的文本（不改变输出 content）。

        说明：BM25 更依赖关键词匹配，因此把 title/category/keywords/source 拼进来，提高命中率。
        """
        meta = doc.get("metadata") or {}
        if not isinstance(meta, dict):
            meta = {}

        parts = [
            str(meta.get("title") or "").strip(),
            str(meta.get("category") or "").strip(),
            str(meta.get("keywords") or "").strip(),
            str(meta.get("source") or "").strip(),
            str(doc.get("content") or "").strip(),
        ]
        text = " ".join([p for p in parts if p]).strip()
        # 性能保护：避免极长文本导致 BM25 token 化爆炸
        if len(text) > 8000:
            text = text[:8000].strip()
        return text

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
        query = str(query or "").strip()
        if not query:
            return []

        if not self.vectorstore:
            logger.warning("向量存储未初始化")
            return []

        if threshold is None:
            threshold = settings.agent.books_thresholds

        try:
            k = max(1, int(k))

            # 1. 向量检索
            vector_results = self.vectorstore.similarity_search_with_score(query, k=k * 3)

            # 2. BM25 关键词检索（仅取 top-n，避免 O(N) 结果合并）
            bm25_scores: List[float] = []
            bm25_bounds: Optional[Tuple[float, float]] = None
            if self.bm25 and self.documents:
                tokenized_query: List[str] = []
                if getattr(self.query_expander, "enabled", False) and hasattr(
                    self.query_expander, "expand_query"
                ):
                    try:
                        expanded = self.query_expander.expand_query(query)
                    except Exception:
                        expanded = [query]
                    for q in expanded or [query]:
                        tokenized_query.extend(self._tokenize(str(q)))
                else:
                    tokenized_query = self._tokenize(query)

                if tokenized_query:
                    # 性能保护：去重并限制 token 数量，避免极端查询导致 BM25 开销过大
                    if len(tokenized_query) > 64:
                        tokenized_query = list(dict.fromkeys(tokenized_query))[:64]
                    raw_scores = self.bm25.get_scores(tokenized_query)
                    if hasattr(raw_scores, "tolist"):  # numpy array
                        raw_scores = raw_scores.tolist()
                    try:
                        bm25_scores = [float(s) for s in list(raw_scores)]
                    except Exception:
                        bm25_scores = []

                if bm25_scores:
                    bm25_min = min(bm25_scores)
                    bm25_max = max(bm25_scores)
                    if bm25_max <= 0.0 or bm25_max <= bm25_min:
                        bm25_scores = []
                    else:
                        bm25_bounds = (bm25_min, bm25_max)

            effective_alpha = alpha if bm25_scores else 1.0

            # 3. 融合分数
            combined_results = self._combine_scores(
                vector_results,
                bm25_scores,
                effective_alpha,
                category,
                threshold,
                bm25_bounds=bm25_bounds,
                bm25_top_n=max(0, k * 10),
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
        *,
        bm25_bounds: Optional[Tuple[float, float]] = None,
        bm25_top_n: int = 0,
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
        # 构建结果字典
        results_dict = {}

        def _norm_bm25(raw: float) -> float:
            if not bm25_bounds:
                return 0.0
            bm25_min, bm25_max = bm25_bounds
            if bm25_max <= bm25_min:
                return 0.0
            value = (float(raw) - bm25_min) / (bm25_max - bm25_min)
            if value <= 0.0:
                return 0.0
            return min(value, 1.0)

        # 处理向量检索结果
        for doc, score in vector_results:
            doc_meta = getattr(doc, "metadata", {}) or {}
            if not isinstance(doc_meta, dict):
                doc_meta = {}
            doc_id = doc_meta.get("id")
            if not doc_id:
                continue
            doc_id = str(doc_id).strip()
            if not doc_id:
                continue

            # 类别过滤
            if category and str(doc_meta.get("category") or "") != str(category):
                continue

            # 计算向量相似度（ChromaDB 返回的是距离，需要转换）
            similarity = 1.0 - score

            # 应用阈值
            if similarity < threshold:
                continue

            merged_meta = dict(doc_meta)
            bm25_score = 0.0
            idx = self._doc_index_by_id.get(doc_id)
            if bm25_scores and idx is not None and 0 <= idx < len(bm25_scores):
                bm25_score = _norm_bm25(bm25_scores[idx])

            # 合并 documents 的元数据（更完整且更可能包含最新 usage_count 等）
            if idx is not None and 0 <= idx < len(self.documents):
                meta_from_docs = self.documents[idx].get("metadata") or {}
                if isinstance(meta_from_docs, dict):
                    merged_meta.update(meta_from_docs)

            results_dict[doc_id] = {
                "id": doc_id,
                "content": doc.page_content,
                "metadata": merged_meta,
                "vector_score": similarity,
                "bm25_score": bm25_score,
                "score": alpha * similarity + (1 - alpha) * bm25_score,
            }

        # 处理 BM25 检索结果
        if bm25_scores and self.documents and bm25_top_n > 0 and bm25_bounds:
            bm25_top_n = min(len(bm25_scores), int(bm25_top_n))
            top_idx = heapq.nlargest(
                bm25_top_n, range(len(bm25_scores)), key=bm25_scores.__getitem__
            )
            for i in top_idx:
                if i >= len(self.documents):
                    continue
                raw = bm25_scores[i]
                if raw <= 0.0:
                    continue
                bm25_score = _norm_bm25(raw)
                if bm25_score <= 0.0:
                    continue

                doc = self.documents[i]
                meta = doc.get("metadata") or {}
                if not isinstance(meta, dict):
                    meta = {}
                doc_id = str(meta.get("id") or "").strip()
                if not doc_id:
                    continue

                # 类别过滤
                if category and str(meta.get("category") or "") != str(category):
                    continue

                if doc_id in results_dict:
                    prev_bm25 = float(results_dict[doc_id].get("bm25_score", 0.0) or 0.0)
                    if bm25_score > prev_bm25:
                        results_dict[doc_id]["bm25_score"] = bm25_score
                        v = float(results_dict[doc_id].get("vector_score", 0.0) or 0.0)
                        results_dict[doc_id]["score"] = alpha * v + (1 - alpha) * bm25_score
                    continue

                results_dict[doc_id] = {
                    "id": doc_id,
                    "content": str(doc.get("content") or ""),
                    "metadata": meta,
                    "vector_score": 0.0,
                    "bm25_score": bm25_score,
                    "score": (1 - alpha) * bm25_score,
                }

        return list(results_dict.values())

    def apply_usage_increments(self, increments: Dict[str, int]) -> None:
        """
        将 usage_count 增量同步到内部 documents 元数据（不触发 BM25 重建）。

        说明：LoreBook 在 search 后会批量写回 usage_count；为了让 reranker 的 usage 维度更及时，
        这里同步内存态 documents 的 usage_count。
        """
        if not increments:
            return

        for doc_id, delta in increments.items():
            doc_id_str = str(doc_id).strip()
            if not doc_id_str:
                continue
            idx = self._doc_index_by_id.get(doc_id_str)
            if idx is None or not (0 <= idx < len(self.documents)):
                continue
            meta = self.documents[idx].get("metadata")
            if not isinstance(meta, dict):
                continue
            try:
                meta["usage_count"] = int(meta.get("usage_count", 0) or 0) + int(delta)
            except Exception:
                try:
                    meta["usage_count"] = int(delta)
                except Exception:
                    meta["usage_count"] = meta.get("usage_count", 0)

    def _normalize_scores(self, scores: List[float]) -> List[float]:
        """
        归一化分数到 [0, 1]（保留旧接口，供其他调用方可能使用）。

        注意：当所有分数相同（尤其是全 0）时，返回全 0，避免“无信息”被放大成强信号。
        """
        if hasattr(scores, "tolist"):
            scores = scores.tolist()
        if not isinstance(scores, list):
            scores = list(scores)
        if len(scores) == 0:
            return []

        min_score = min(scores)
        max_score = max(scores)
        if max_score <= min_score:
            return [0.0] * len(scores)
        if max_score <= 0.0:
            return [0.0] * len(scores)

        return [
            max(0.0, min((float(s) - min_score) / (max_score - min_score), 1.0)) for s in scores
        ]


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
                base_score * 0.3
                + recency_score * 0.15
                + importance_score * 0.2
                + usage_score * 0.15
                + context_score * 0.2
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
        except Exception:
            return 0.5

    def _calculate_usage_score(self, result: Dict[str, Any]) -> float:
        """
        计算使用频率分数

        Args:
            result: 检索结果

        Returns:
            float: 使用频率分数 (0-1)
        """
        usage_raw = result.get("metadata", {}).get("usage_count", 0)
        try:
            usage_count = int(usage_raw or 0)
        except Exception:
            usage_count = 0

        # 对数归一化：假设最大使用次数为 100
        if usage_count <= 0:
            return 0.0

        return min(math.log(usage_count + 1) / math.log(100), 1.0)

    def _calculate_context_score(self, result: Dict[str, Any], context: Dict[str, Any]) -> float:
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
        raw_context_keywords = context.get("keywords", [])
        if not isinstance(raw_context_keywords, list):
            raw_context_keywords = []
        context_keywords = {str(k).strip() for k in raw_context_keywords if str(k).strip()}

        raw_knowledge_keywords = result.get("metadata", {}).get("keywords", "")
        if isinstance(raw_knowledge_keywords, list):
            knowledge_keywords = {str(k).strip() for k in raw_knowledge_keywords if str(k).strip()}
        else:
            knowledge_keywords = {
                str(k).strip()
                for k in str(raw_knowledge_keywords or "").split(",")
                if str(k).strip()
            }

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
            prompt = ChatPromptTemplate.from_messages(
                [
                    (
                        "system",
                        """你是一个查询扩展专家。请为给定的查询生成 {max_expansions} 个相关的扩展查询。

扩展规则：
1. 使用同义词替换
2. 添加相关概念
3. 从不同角度描述
4. 保持语义相关性

请以 JSON 格式返回：
{{
    "expanded_queries": ["查询1", "查询2", "查询3"]
}}""",
                    ),
                    ("human", "原始查询: {query}"),
                ]
            )

            llm = get_llm()
            chain = prompt | llm

            result = chain.invoke({"query": query, "max_expansions": max_expansions})

            # 解析 JSON
            import json

            data = json.loads(result.content)
            expanded = data.get("expanded_queries", [])

            # 确保包含原始查询
            if query not in expanded:
                expanded.insert(0, query)

            logger.debug("查询扩展完成: 原始=%.80s 扩展=%d个", query, len(expanded))
            return expanded[: max_expansions + 1]

        except Exception as e:
            logger.warning("查询扩展失败: %s", e)
            return [query]
