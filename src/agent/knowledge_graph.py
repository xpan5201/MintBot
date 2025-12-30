"""
知识图谱系统 v2.30.43

实现知识关系建模、知识推理和知识可视化功能。

核心功能：
1. 知识关系建模 - 自动提取知识之间的关系
2. 知识推理 - 基于关系进行推理
3. 知识可视化 - 生成知识图谱可视化
4. 关系查询 - 查询知识之间的关系路径
"""

import json
import os
import tempfile
import threading
from collections import defaultdict, deque
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
import heapq

import networkx as nx
from src.utils.logger import get_logger

logger = get_logger(__name__)

# 导入 Pydantic
from pydantic import BaseModel, Field

# 尝试导入 LangChain LLM（不要用“未安装”掩盖真实导入失败原因）
_LANGCHAIN_LLM_IMPORT_ERROR: Optional[BaseException] = None
try:
    from src.llm.factory import get_llm

    # 兼容不同 LangChain 版本的导入路径
    try:
        from langchain_core.output_parsers import PydanticOutputParser  # type: ignore
    except Exception:  # pragma: no cover - 版本差异
        from langchain.output_parsers import PydanticOutputParser  # type: ignore

    try:
        from langchain_core.prompts import PromptTemplate  # type: ignore
    except Exception:  # pragma: no cover - 版本差异
        from langchain.prompts import PromptTemplate  # type: ignore

    HAS_LANGCHAIN_LLM = True
except Exception as exc:  # pragma: no cover - 环境依赖差异
    HAS_LANGCHAIN_LLM = False
    _LANGCHAIN_LLM_IMPORT_ERROR = exc
    get_llm = None  # type: ignore[assignment]
    PydanticOutputParser = None  # type: ignore[assignment]
    PromptTemplate = None  # type: ignore[assignment]
    # 默认仅 debug：LLM 辅助是可选能力，真正需要时会在调用处给出 warning。
    logger.debug("LangChain LLM 依赖导入失败（可忽略）: %s", exc)


class KnowledgeRelation(BaseModel):
    """知识关系模型"""

    source_id: str = Field(description="源知识ID")
    target_id: str = Field(description="目标知识ID")
    relation_type: str = Field(description="关系类型")
    confidence: float = Field(description="置信度", ge=0.0, le=1.0)
    description: Optional[str] = Field(default=None, description="关系描述")


class RelationExtractionResult(BaseModel):
    """关系提取结果"""

    relations: List[KnowledgeRelation] = Field(description="提取的关系列表")


class KnowledgeGraph:
    """
    知识图谱 - 管理知识之间的关系

    功能：
    1. 自动提取知识关系
    2. 存储和查询关系
    3. 知识推理
    4. 图谱可视化
    """

    def __init__(
        self,
        graph_file: Optional[Path] = None,
        autosave: bool = True,
        rule_max_ids_per_keyword: int = 200,
        rule_max_keyword_links_per_node: int = 12,
        rule_category_anchor_count: int = 2,
        rule_max_relations: int = 100_000,
        rule_shared_keywords_desc_limit: int = 12,
        save_pretty_json: bool = True,
        save_sort: bool = True,
    ):
        """
        初始化知识图谱

        Args:
            graph_file: 图谱数据文件路径
            autosave: 是否自动保存到磁盘（默认 True）
            rule_max_ids_per_keyword: 规则提取中每个关键词最多参与匹配的知识数量（避免公共词爆炸）
            rule_max_keyword_links_per_node: 规则提取中每个知识最多保留的关键词相关边数
            rule_category_anchor_count: 规则提取中每个类别选择的“锚点”节点数量（用于稀疏化类别相关边）
            rule_max_relations: 规则提取最大关系数量（超出将截断）
            rule_shared_keywords_desc_limit: 关系描述中最多列出的共享关键词数量
            save_pretty_json: 保存 JSON 时是否启用缩进美化（更易读但更慢更大）
            save_sort: 保存 JSON 时是否对节点/边排序（便于 diff 但更慢）
        """
        self.graph_file = graph_file or Path("data/memory/knowledge_graph.json")
        self.graph_file.parent.mkdir(parents=True, exist_ok=True)

        # 创建有向图
        self.graph = nx.DiGraph()

        # 并发保护：知识图谱在 GUI/异步任务场景下可能被并发访问
        self._lock = threading.RLock()

        # 自动保存控制（批量更新时可延迟保存，避免频繁 I/O）
        self.autosave = autosave
        self._defer_save_depth = 0
        self._dirty = False

        # 规则提取性能控制（避免 O(n^2) 关系爆炸）
        self.rule_max_ids_per_keyword = max(1, int(rule_max_ids_per_keyword))
        self.rule_max_keyword_links_per_node = max(0, int(rule_max_keyword_links_per_node))
        self.rule_category_anchor_count = max(0, int(rule_category_anchor_count))
        self.rule_max_relations = max(0, int(rule_max_relations))
        self.rule_shared_keywords_desc_limit = max(1, int(rule_shared_keywords_desc_limit))

        # JSON 保存策略
        self.save_pretty_json = bool(save_pretty_json)
        self.save_sort = bool(save_sort)

        # 关系类型定义
        self.relation_types = {
            "related_to": "相关",
            "part_of": "属于",
            "causes": "导致",
            "precedes": "先于",
            "similar_to": "相似",
            "opposite_to": "相反",
            "example_of": "示例",
            "defined_by": "定义",
            "located_in": "位于",
            "owned_by": "拥有",
        }

        # 对称关系：默认自动写入双向边，避免从任一节点都能查询到相关项
        self._symmetric_relations = {"related_to", "similar_to", "opposite_to"}

        # 索引（不持久化）：用于增量更新/快速候选检索
        self._category_index: Dict[str, Set[str]] = defaultdict(set)
        self._keyword_index: Dict[str, Set[str]] = defaultdict(set)

        # 加载图谱数据
        self._load_graph()

        # LLM 延迟初始化（首次需要 LLM 辅助提取时再创建）
        self.llm = None

        logger.info("知识图谱初始化完成")

    def _load_graph(self):
        """加载图谱数据"""
        if not self.graph_file.exists():
            return

        with self._lock:
            try:
                with open(self.graph_file, "r", encoding="utf-8") as f:
                    data = json.load(f)

                # 先清空，避免重复加载
                self.graph.clear()

                # 加载节点
                for node_data in data.get("nodes", []):
                    node_id = node_data.get("id")
                    if not node_id:
                        continue
                    self.graph.add_node(node_id, **node_data.get("attributes", {}))

                # 加载边
                for edge_data in data.get("edges", []):
                    source = edge_data.get("source")
                    target = edge_data.get("target")
                    if not source or not target:
                        continue

                    relation_type = edge_data.get("relation_type", "related_to")
                    if relation_type not in self.relation_types:
                        relation_type = "related_to"

                    try:
                        confidence = float(edge_data.get("confidence", 1.0))
                    except Exception:
                        confidence = 1.0
                    confidence = max(0.0, min(1.0, confidence))

                    self.graph.add_edge(
                        source,
                        target,
                        relation_type=relation_type,
                        confidence=confidence,
                        description=edge_data.get("description"),
                        created_at=edge_data.get("created_at"),
                        updated_at=edge_data.get("updated_at"),
                        relation_source=edge_data.get("relation_source"),
                    )

                # 重建索引（节点/边加载完毕后）
                self._rebuild_indexes_unlocked()

                self._dirty = False
                logger.info(
                    "加载知识图谱: %d 个节点, %d 条边",
                    self.graph.number_of_nodes(),
                    self.graph.number_of_edges(),
                )

            except json.JSONDecodeError as e:
                # 文件损坏时保留副本，避免启动即崩溃/循环报错
                backup = self.graph_file.with_suffix(
                    f"{self.graph_file.suffix}.corrupt.{datetime.now().strftime('%Y%m%d%H%M%S')}"
                )
                try:
                    self.graph_file.replace(backup)
                except Exception:
                    pass

                self.graph.clear()
                self._rebuild_indexes_unlocked()
                self._dirty = False
                logger.error("知识图谱文件解析失败，已备份到 %s: %s", backup, e)

            except Exception as e:
                logger.error(f"加载知识图谱失败: {e}")

    def _normalize_keywords(self, keywords: Any) -> List[str]:
        """将关键词字段规范化为 list[str]。"""
        if keywords is None:
            return []
        if isinstance(keywords, list):
            result: List[str] = []
            for kw in keywords:
                if isinstance(kw, str) and kw.strip():
                    result.append(kw.strip())
            return result
        if isinstance(keywords, str):
            parts = [p.strip() for p in keywords.split(",")]
            return [p for p in parts if p]
        return []

    def _rebuild_indexes_unlocked(self) -> None:
        self._category_index.clear()
        self._keyword_index.clear()
        for node_id in self.graph.nodes():
            attrs = self.graph.nodes[node_id]
            category = str(attrs.get("category") or "general")
            keywords_list = self._normalize_keywords(attrs.get("keywords"))
            # 写回规范化后的结构，避免后续逻辑分支过多
            attrs["category"] = category
            attrs["keywords"] = keywords_list

            self._category_index[category].add(node_id)
            for kw in keywords_list:
                self._keyword_index[kw].add(node_id)

    def _unindex_node_unlocked(self, node_id: str) -> None:
        if not self.graph.has_node(node_id):
            return
        attrs = self.graph.nodes[node_id]
        category = str(attrs.get("category") or "general")
        keywords_list = self._normalize_keywords(attrs.get("keywords"))

        if category in self._category_index:
            self._category_index[category].discard(node_id)
            if not self._category_index[category]:
                self._category_index.pop(category, None)

        for kw in keywords_list:
            if kw in self._keyword_index:
                self._keyword_index[kw].discard(node_id)
                if not self._keyword_index[kw]:
                    self._keyword_index.pop(kw, None)

    def _index_node_unlocked(self, node_id: str) -> None:
        if not self.graph.has_node(node_id):
            return
        attrs = self.graph.nodes[node_id]
        category = str(attrs.get("category") or "general")
        keywords_list = self._normalize_keywords(attrs.get("keywords"))
        attrs["category"] = category
        attrs["keywords"] = keywords_list

        self._category_index[category].add(node_id)
        for kw in keywords_list:
            self._keyword_index[kw].add(node_id)

    def _save_graph(self):
        """保存图谱数据"""
        with self._lock:
            try:
                # 准备节点数据
                nodes = [
                    {"id": node, "attributes": dict(self.graph.nodes[node])}
                    for node in self.graph.nodes()
                ]
                if self.save_sort:
                    nodes.sort(key=lambda x: x["id"])

                # 准备边数据
                edges = [
                    {
                        "source": u,
                        "target": v,
                        "relation_type": data.get("relation_type", "related_to"),
                        "confidence": data.get("confidence", 1.0),
                        "description": data.get("description"),
                        "created_at": data.get("created_at"),
                        "updated_at": data.get("updated_at"),
                        "relation_source": data.get("relation_source"),
                    }
                    for u, v, data in self.graph.edges(data=True)
                ]
                if self.save_sort:
                    edges.sort(key=lambda x: (x["source"], x["target"], x.get("relation_type", "")))

                payload = {"nodes": nodes, "edges": edges}

                # 原子写入：避免半写入导致 JSON 损坏
                tmp_path = None
                try:
                    with tempfile.NamedTemporaryFile(
                        "w",
                        encoding="utf-8",
                        dir=str(self.graph_file.parent),
                        prefix=f".{self.graph_file.stem}.",
                        suffix=".tmp",
                        delete=False,
                    ) as f:
                        tmp_path = f.name
                        indent = 2 if self.save_pretty_json else None
                        separators = None if self.save_pretty_json else (",", ":")
                        json.dump(
                            payload,
                            f,
                            ensure_ascii=False,
                            indent=indent,
                            separators=separators,
                        )
                        f.flush()
                        os.fsync(f.fileno())

                    Path(tmp_path).replace(self.graph_file)
                    self._dirty = False

                finally:
                    if tmp_path:
                        try:
                            Path(tmp_path).unlink(missing_ok=True)
                        except Exception:
                            pass

                logger.debug("保存知识图谱: %d 个节点, %d 条边", len(nodes), len(edges))

            except Exception as e:
                # 保持 dirty，便于后续重试
                self._dirty = True
                logger.error(f"保存知识图谱失败: {e}")

    def _request_save(self) -> None:
        """请求保存：支持批量更新时延迟保存以减少 I/O。"""
        if not self.autosave:
            self._dirty = True
            return

        if self._defer_save_depth > 0:
            self._dirty = True
            return

        # 直接保存（内部会持锁）
        self._save_graph()

    def flush(self) -> None:
        """将脏数据刷盘（autosave=False 时用于手动落盘/程序退出收尾）。"""
        with self._lock:
            dirty = bool(self._dirty)

        if dirty:
            self._save_graph()

    @contextmanager
    def bulk_update(self):
        """
        批量更新上下文：在 context 内的多次 add_node/add_edge 将只触发一次保存。

        用法：
            with kg.bulk_update():
                ...
        """
        with self._lock:
            self._defer_save_depth += 1

        try:
            yield self
        finally:
            with self._lock:
                self._defer_save_depth = max(0, self._defer_save_depth - 1)
                should_save = self._defer_save_depth == 0 and self._dirty and self.autosave

            if should_save:
                self._save_graph()

    def clear(self, delete_file: bool = False) -> None:
        """清空图谱，可选删除持久化文件。"""
        with self._lock:
            self.graph.clear()
            self._rebuild_indexes_unlocked()
            self._dirty = True

            if delete_file and self.graph_file.exists():
                try:
                    self.graph_file.unlink()
                    self._dirty = False
                except Exception as exc:
                    logger.warning("删除知识图谱文件失败（可忽略）: %s", exc)

            if not delete_file:
                self._request_save()

    def add_knowledge_node(
        self,
        knowledge_id: str,
        title: str,
        category: str,
        keywords: Optional[List[str]] = None,
    ):
        """
        添加知识节点

        Args:
            knowledge_id: 知识ID
            title: 知识标题
            category: 知识类别
            keywords: 关键词列表
        """
        if not knowledge_id:
            return

        with self._lock:
            now = datetime.now().isoformat()
            node_attrs = {
                "title": title,
                "category": category,
                "keywords": self._normalize_keywords(keywords),
            }

            if self.graph.has_node(knowledge_id):
                # 更新前先移除旧索引
                self._unindex_node_unlocked(knowledge_id)
                existing = self.graph.nodes[knowledge_id]
                existing.update(node_attrs)
                if not existing.get("created_at"):
                    existing["created_at"] = now
                existing["updated_at"] = now
            else:
                self.graph.add_node(knowledge_id, **node_attrs, created_at=now, updated_at=now)

            # 写入新索引
            self._index_node_unlocked(knowledge_id)

            self._dirty = True
            self._request_save()

        logger.debug("添加知识节点: %s", title)

    def remove_knowledge_node(self, knowledge_id: str) -> bool:
        """删除知识节点（同时删除相关边）。"""
        if not knowledge_id:
            return False

        with self.bulk_update():
            with self._lock:
                if not self.graph.has_node(knowledge_id):
                    return False

                self._unindex_node_unlocked(knowledge_id)
                self.graph.remove_node(knowledge_id)
                self._dirty = True
                self._request_save()

        logger.debug("删除知识节点: %s", knowledge_id)
        return True

    def upsert_knowledge_entry(
        self, knowledge: Dict[str, Any], *, update_edges: bool = True
    ) -> bool:
        """
        用知识条目增量更新图谱（节点 + 可选规则边）。

        Args:
            knowledge: 至少包含 id/title/category/keywords 的字典
            update_edges: 是否刷新该节点的规则关系边
        """
        knowledge_id = knowledge.get("id")
        if not knowledge_id:
            return False

        title = knowledge.get("title") or str(knowledge_id)
        category = knowledge.get("category") or "general"
        keywords = knowledge.get("keywords") or []

        with self.bulk_update():
            self.add_knowledge_node(
                knowledge_id=str(knowledge_id),
                title=str(title),
                category=str(category),
                keywords=self._normalize_keywords(keywords),
            )
            if update_edges:
                self.refresh_rule_relations_for_node(str(knowledge_id))

        return True

    def upsert_knowledge_entries(
        self, knowledge_entries: List[Dict[str, Any]], *, update_edges: bool = True
    ) -> int:
        """批量增量更新（节点 + 可选规则边），返回成功数量。"""
        if not knowledge_entries:
            return 0

        updated = 0
        with self.bulk_update():
            for entry in knowledge_entries:
                if self.upsert_knowledge_entry(entry, update_edges=update_edges):
                    updated += 1
        return updated

    def remove_knowledge_nodes(self, knowledge_ids: List[str]) -> int:
        """批量删除节点，返回成功删除数量。"""
        if not knowledge_ids:
            return 0

        deleted = 0
        with self.bulk_update():
            for knowledge_id in knowledge_ids:
                if self.remove_knowledge_node(str(knowledge_id)):
                    deleted += 1
        return deleted

    def refresh_rule_relations_for_node(self, knowledge_id: str) -> None:
        """刷新指定节点的规则关系（只会重建 relation_source=rule 的边，不影响手动/LLM 关系）。"""
        if not knowledge_id:
            return

        if not self.graph.has_node(knowledge_id):
            return

        with self.bulk_update():
            with self._lock:
                node_attrs = self.graph.nodes[knowledge_id]
                category = str(node_attrs.get("category") or "general")
                keywords_set = set(self._normalize_keywords(node_attrs.get("keywords")))

                # 删除旧的规则边（出入边都处理）
                to_remove: List[Tuple[str, str]] = []
                for neighbor in list(self.graph.successors(knowledge_id)):
                    data = self.graph.get_edge_data(knowledge_id, neighbor) or {}
                    if data.get("relation_source") == "rule":
                        to_remove.append((knowledge_id, neighbor))
                for neighbor in list(self.graph.predecessors(knowledge_id)):
                    data = self.graph.get_edge_data(neighbor, knowledge_id) or {}
                    if data.get("relation_source") == "rule":
                        to_remove.append((neighbor, knowledge_id))

                for u, v in to_remove:
                    if self.graph.has_edge(u, v):
                        self.graph.remove_edge(u, v)

                self._dirty = True

            # 1) 类别锚点（稀疏连接）
            if self.rule_category_anchor_count > 0:
                same_category = self._category_index.get(category, set())
                anchors = [
                    a
                    for a in heapq.nsmallest(self.rule_category_anchor_count, same_category)
                    if a != knowledge_id
                ]
                for anchor_id in anchors:
                    # 不覆盖已有非 rule 边
                    if self.graph.has_edge(knowledge_id, anchor_id) or self.graph.has_edge(
                        anchor_id, knowledge_id
                    ):
                        continue
                    self.add_relation(
                        source_id=knowledge_id,
                        target_id=anchor_id,
                        relation_type="related_to",
                        confidence=0.6,
                        description=f"相同类别: {category}",
                        relation_source="rule",
                    )

            # 2) 关键词 Top-K
            if keywords_set and self.rule_max_keyword_links_per_node > 0:
                candidates: Dict[str, Set[str]] = defaultdict(set)
                limit = self.rule_max_ids_per_keyword
                for kw in keywords_set:
                    ids = self._keyword_index.get(kw, set())
                    if not ids:
                        continue
                    # 限制公共词参与匹配的数量
                    for other_id in heapq.nsmallest(limit, ids):
                        if other_id == knowledge_id:
                            continue
                        candidates[other_id].add(kw)

                if candidates:
                    scored: List[Tuple[float, str, Set[str]]] = []
                    for other_id, shared in candidates.items():
                        other_keywords = set(
                            self._normalize_keywords(self.graph.nodes[other_id].get("keywords"))
                        )
                        denom = max(len(keywords_set), len(other_keywords), 1)
                        confidence = len(shared) / denom
                        scored.append((confidence, other_id, shared))

                    scored.sort(key=lambda x: x[0], reverse=True)
                    for confidence, other_id, shared in scored[
                        : self.rule_max_keyword_links_per_node
                    ]:
                        # 不覆盖已有非 rule 边
                        if self.graph.has_edge(knowledge_id, other_id) or self.graph.has_edge(
                            other_id, knowledge_id
                        ):
                            continue
                        shared_sorted = sorted(shared)
                        shown = shared_sorted[: self.rule_shared_keywords_desc_limit]
                        extra = len(shared_sorted) - len(shown)
                        desc = f"共享关键词: {', '.join(shown)}"
                        if extra > 0:
                            desc += f" (+{extra} more)"

                        self.add_relation(
                            source_id=knowledge_id,
                            target_id=other_id,
                            relation_type="related_to",
                            confidence=float(confidence),
                            description=desc,
                            relation_source="rule",
                        )

    def _is_symmetric_relation(self, relation_type: str) -> bool:
        return relation_type in self._symmetric_relations

    def add_relation(
        self,
        source_id: str,
        target_id: str,
        relation_type: str = "related_to",
        confidence: float = 1.0,
        description: Optional[str] = None,
        bidirectional: Optional[bool] = None,
        relation_source: str = "manual",
    ):
        """
        添加知识关系

        Args:
            source_id: 源知识ID
            target_id: 目标知识ID
            relation_type: 关系类型
            confidence: 置信度
            description: 关系描述
            bidirectional: 是否写入双向关系（None 表示根据 relation_type 自动判断）
            relation_source: 关系来源（manual/llm/rule/inference/unknown），用于避免低质量边覆盖高质量边
        """
        if not source_id or not target_id:
            return

        if source_id == target_id:
            logger.debug("忽略自环关系: %s", source_id)
            return

        if relation_type not in self.relation_types:
            logger.warning("未知关系类型 '%s'，已回退为 related_to", relation_type)
            relation_type = "related_to"

        try:
            confidence = float(confidence)
        except Exception:
            confidence = 1.0
        confidence = max(0.0, min(1.0, confidence))

        if bidirectional is None:
            bidirectional = self._is_symmetric_relation(relation_type)

        def _source_priority(src: Any) -> int:
            if not src:
                return 5  # unknown
            src_str = str(src)
            priorities = {
                "rule": 0,
                "inference": 10,
                "unknown": 5,
                "llm": 20,
                "manual": 30,
            }
            return priorities.get(src_str, 5)

        with self._lock:
            # 检查节点是否存在
            if source_id not in self.graph:
                logger.warning(f"源知识节点不存在: {source_id}")
                return

            if target_id not in self.graph:
                logger.warning(f"目标知识节点不存在: {target_id}")
                return

            now = datetime.now().isoformat()

            def _upsert_edge(u: str, v: str) -> None:
                existing = self.graph.get_edge_data(u, v) or {}
                existing_priority = _source_priority(existing.get("relation_source"))
                new_priority = _source_priority(relation_source)

                # 低优先级来源不得覆盖高优先级来源
                if existing and new_priority < existing_priority:
                    return

                try:
                    existing_confidence = float(existing.get("confidence", 1.0))
                except Exception:
                    existing_confidence = 1.0

                # 同优先级时，保留更高置信度的边；但允许补齐 description
                if (
                    existing
                    and new_priority == existing_priority
                    and confidence <= existing_confidence
                ):
                    if description and not existing.get("description"):
                        self.graph.add_edge(
                            u,
                            v,
                            relation_type=existing.get("relation_type", relation_type),
                            confidence=existing_confidence,
                            description=description,
                            created_at=existing.get("created_at") or now,
                            updated_at=now,
                            relation_source=existing.get("relation_source", relation_source),
                        )
                    return

                created_at = existing.get("created_at") or now
                self.graph.add_edge(
                    u,
                    v,
                    relation_type=relation_type,
                    confidence=confidence,
                    description=description,
                    created_at=created_at,
                    updated_at=now,
                    relation_source=relation_source,
                )

            _upsert_edge(source_id, target_id)
            if bidirectional:
                _upsert_edge(target_id, source_id)

            self._dirty = True
            self._request_save()

        logger.debug("添加关系: %s -> %s (%s)", source_id, target_id, relation_type)

    def extract_relations_llm(
        self,
        knowledge_list: List[Dict[str, Any]],
    ) -> List[KnowledgeRelation]:
        """
        使用 LLM 提取知识关系

        Args:
            knowledge_list: 知识列表

        Returns:
            List[KnowledgeRelation]: 提取的关系列表
        """
        if not HAS_LANGCHAIN_LLM:
            logger.warning("LangChain LLM 不可用，无法提取关系")
            return []

        if not self.llm:
            try:
                # 关系提取更适合低温度（确定性更强）
                self.llm = get_llm(temperature=0.0)
            except Exception as exc:
                logger.warning("初始化 LLM 失败，无法提取关系: %s", exc)
                return []

        try:
            # 准备知识信息
            knowledge_info = []
            for k in knowledge_list:
                info = f"ID: {k.get('id')}\n"
                info += f"标题: {k.get('title')}\n"
                info += f"类别: {k.get('category')}\n"
                info += f"内容: {k.get('content', '')[:200]}\n"
                knowledge_info.append(info)

            # 创建提示词
            parser = PydanticOutputParser(pydantic_object=RelationExtractionResult)

            prompt = PromptTemplate(
                template="""你是一个知识图谱专家。请分析以下知识，提取它们之间的关系。

知识列表：
{knowledge_info}

关系类型：
- related_to: 相关
- part_of: 属于
- causes: 导致
- precedes: 先于
- similar_to: 相似
- opposite_to: 相反
- example_of: 示例
- defined_by: 定义
- located_in: 位于
- owned_by: 拥有

请提取知识之间的关系，包括：
1. 源知识ID
2. 目标知识ID
3. 关系类型
4. 置信度（0.0-1.0）
5. 关系描述（可选）

{format_instructions}
""",
                input_variables=["knowledge_info"],
                partial_variables={"format_instructions": parser.get_format_instructions()},
            )

            # 调用 LLM
            chain = prompt | self.llm | parser
            result = chain.invoke({"knowledge_info": "\n\n".join(knowledge_info)})

            logger.info(f"LLM 提取关系: {len(result.relations)} 条")
            return result.relations

        except Exception as e:
            logger.error(f"LLM 提取关系失败: {e}")
            return []

    def extract_relations_rule_based(
        self,
        knowledge_list: List[Dict[str, Any]],
    ) -> List[KnowledgeRelation]:
        """
        基于规则提取知识关系

        Args:
            knowledge_list: 知识列表

        Returns:
            List[KnowledgeRelation]: 提取的关系列表
        """
        relations: List[KnowledgeRelation] = []

        # 预处理：构建 id->keywords_set, category->ids, keyword->ids 索引。
        # 注意：旧实现会在类别/关键词上生成 clique（O(n^2)），大规模知识库会直接不可用；
        # 这里使用“锚点 + Top-K”策略稀疏化图谱，保证可扩展性。
        id_to_keywords: Dict[str, Set[str]] = {}
        category_to_ids: Dict[str, List[str]] = defaultdict(list)
        keyword_to_ids: Dict[str, List[str]] = defaultdict(list)

        for k in knowledge_list:
            k_id = k.get("id")
            if not k_id:
                continue

            category = k.get("category") or "general"
            keywords_set = set(self._normalize_keywords(k.get("keywords")))

            id_to_keywords[k_id] = keywords_set
            category_to_ids[category].append(k_id)
            for kw in keywords_set:
                keyword_to_ids[kw].append(k_id)

        # 去重并对高频关键词截断，避免公共词导致候选爆炸
        max_ids_per_kw = self.rule_max_ids_per_keyword
        for kw, ids in list(keyword_to_ids.items()):
            if len(ids) <= 1:
                continue
            unique_ids = list(dict.fromkeys(ids))
            if len(unique_ids) > max_ids_per_kw:
                unique_ids = unique_ids[:max_ids_per_kw]
            keyword_to_ids[kw] = unique_ids

        # pair_key: (min_id, max_id) -> {"confidence": float, "descriptions": set[str]}
        pair_info: Dict[Tuple[str, str], Dict[str, Any]] = {}
        max_relations = self.rule_max_relations

        def _over_limit() -> bool:
            return max_relations > 0 and len(pair_info) >= max_relations

        def _pair_key(a: str, b: str) -> Tuple[str, str]:
            return (a, b) if a <= b else (b, a)

        def _upsert_pair(a: str, b: str, confidence: float, desc: str) -> None:
            if a == b:
                return
            key = _pair_key(a, b)
            if key not in pair_info:
                pair_info[key] = {
                    "confidence": confidence,
                    "descriptions": {desc} if desc else set(),
                }
                return

            info = pair_info[key]
            info["confidence"] = max(float(info["confidence"]), confidence)
            if desc:
                info["descriptions"].add(desc)

        # 规则1：相同类别（使用少量锚点稀疏连接）
        if self.rule_category_anchor_count > 0:
            for category, ids in category_to_ids.items():
                if len(ids) < 2:
                    continue

                anchors = ids[: self.rule_category_anchor_count]
                for node_id in ids:
                    for anchor_id in anchors:
                        if node_id == anchor_id:
                            continue
                        _upsert_pair(node_id, anchor_id, 0.6, f"相同类别: {category}")
                        if _over_limit():
                            break
                    if _over_limit():
                        break
                if _over_limit():
                    break

        # 规则2：共享关键词（Top-K 连接）
        if not _over_limit() and self.rule_max_keyword_links_per_node > 0:
            topk = self.rule_max_keyword_links_per_node
            desc_limit = self.rule_shared_keywords_desc_limit

            for node_id, keywords_set in id_to_keywords.items():
                if _over_limit():
                    break
                if not keywords_set:
                    continue

                candidates: Dict[str, Set[str]] = defaultdict(set)
                for kw in keywords_set:
                    for other_id in keyword_to_ids.get(kw, []):
                        if other_id == node_id:
                            continue
                        candidates[other_id].add(kw)

                if not candidates:
                    continue

                scored: List[Tuple[float, str, Set[str]]] = []
                for other_id, shared in candidates.items():
                    keywords_other = id_to_keywords.get(other_id, set())
                    denom = max(len(keywords_set), len(keywords_other), 1)
                    confidence = len(shared) / denom
                    scored.append((confidence, other_id, shared))

                scored.sort(key=lambda x: x[0], reverse=True)
                for confidence, other_id, shared in scored[:topk]:
                    if _over_limit():
                        break
                    shared_sorted = sorted(shared)
                    shown = shared_sorted[:desc_limit]
                    extra = len(shared_sorted) - len(shown)
                    desc = f"共享关键词: {', '.join(shown)}"
                    if extra > 0:
                        desc += f" (+{extra} more)"
                    _upsert_pair(node_id, other_id, float(confidence), desc)

        for (a, b), info in pair_info.items():
            desc = "；".join(sorted(info["descriptions"])) if info["descriptions"] else None
            relations.append(
                KnowledgeRelation(
                    source_id=a,
                    target_id=b,
                    relation_type="related_to",
                    confidence=float(info["confidence"]),
                    description=desc,
                )
            )

        truncated = _over_limit()
        if truncated:
            logger.warning("规则提取关系达到上限，已截断: max_relations=%d", max_relations)
        logger.info("规则提取关系: %d 条", len(relations))
        return relations

    def build_graph_from_knowledge(
        self,
        knowledge_list: List[Dict[str, Any]],
        use_llm: bool = True,
        rebuild: bool = True,
    ):
        """
        从知识列表构建图谱

        Args:
            knowledge_list: 知识列表
            use_llm: 是否使用 LLM 提取关系
            rebuild: 是否重建图谱（默认 True，会清空旧图谱并重新生成）
        """
        with self.bulk_update():
            if rebuild:
                with self._lock:
                    self.graph.clear()
                    self._rebuild_indexes_unlocked()
                    self._dirty = True

            # 添加节点（批量模式下不会频繁落盘）
            for knowledge in knowledge_list:
                k_id = knowledge.get("id")
                if not k_id:
                    continue

                title = knowledge.get("title") or str(k_id)
                category = knowledge.get("category") or "general"

                self.add_knowledge_node(
                    knowledge_id=k_id,
                    title=title,
                    category=category,
                    keywords=knowledge.get("keywords", []),
                )

            # 提取关系：优先 LLM，失败/无结果回退规则
            relations: List[KnowledgeRelation] = []
            relation_source = "rule"
            if use_llm:
                relations = self.extract_relations_llm(knowledge_list)
                if relations:
                    relation_source = "llm"
                else:
                    relations = self.extract_relations_rule_based(knowledge_list)
            else:
                relations = self.extract_relations_rule_based(knowledge_list)

            # 添加关系
            for relation in relations:
                self.add_relation(
                    source_id=relation.source_id,
                    target_id=relation.target_id,
                    relation_type=relation.relation_type,
                    confidence=relation.confidence,
                    description=relation.description,
                    relation_source=relation_source,
                )

        logger.info(
            "构建知识图谱完成: %d 个节点, %d 条边",
            self.graph.number_of_nodes(),
            self.graph.number_of_edges(),
        )

    def find_related_knowledge(
        self,
        knowledge_id: str,
        max_depth: int = 2,
        min_confidence: float = 0.5,
        include_incoming: bool = True,
        max_results: int = 200,
        max_nodes_visited: int = 5000,
    ) -> List[Dict[str, Any]]:
        """
        查找相关知识

        Args:
            knowledge_id: 知识ID
            max_depth: 最大深度
            min_confidence: 最小置信度
            include_incoming: 是否同时考虑入边（默认 True，更适合“相关知识”查询）
            max_results: 最多返回的结果数量（默认 200，避免大图返回过多）
            max_nodes_visited: 最多遍历的节点数（默认 5000，用于保护性能）

        Returns:
            List[Dict]: 相关知识列表
        """
        if knowledge_id not in self.graph:
            logger.warning(f"知识节点不存在: {knowledge_id}")
            return []

        visited: Set[str] = set()
        queue: deque[Tuple[str, int]] = deque([(knowledge_id, 0)])
        seen_depth: Dict[str, int] = {knowledge_id: 0}

        best_by_id: Dict[str, Dict[str, Any]] = {}
        visited_count = 0

        while queue:
            current_id, depth = queue.popleft()

            if current_id in visited or depth > max_depth:
                continue

            visited.add(current_id)
            visited_count += 1
            if max_nodes_visited > 0 and visited_count > max_nodes_visited:
                logger.warning(
                    "相关知识查询触发遍历上限，已提前停止: visited=%d max_nodes_visited=%d",
                    visited_count,
                    max_nodes_visited,
                )
                break

            if depth >= max_depth:
                continue

            neighbors: Set[str] = set(self.graph.neighbors(current_id))
            if include_incoming:
                neighbors.update(self.graph.predecessors(current_id))

            for neighbor in neighbors:
                if neighbor in visited:
                    continue

                next_depth = depth + 1
                if next_depth > max_depth:
                    continue

                # 记录更短路径深度，避免重复入队
                prev_depth = seen_depth.get(neighbor)
                if prev_depth is None or next_depth < prev_depth:
                    seen_depth[neighbor] = next_depth
                    if next_depth < max_depth:
                        queue.append((neighbor, next_depth))

                # 优先使用出边数据；若仅存在入边，则使用入边数据
                edge_data = None
                direction = "out"
                if self.graph.has_edge(current_id, neighbor):
                    edge_data = self.graph[current_id][neighbor]
                elif include_incoming and self.graph.has_edge(neighbor, current_id):
                    edge_data = self.graph[neighbor][current_id]
                    direction = "in"

                if not edge_data:
                    continue

                try:
                    confidence = float(edge_data.get("confidence", 1.0))
                except Exception:
                    confidence = 1.0

                if confidence < min_confidence:
                    continue

                result = {
                    "id": neighbor,
                    "title": self.graph.nodes[neighbor].get("title"),
                    "category": self.graph.nodes[neighbor].get("category"),
                    "relation_type": edge_data.get("relation_type"),
                    "relation_source": edge_data.get("relation_source"),
                    "confidence": confidence,
                    "description": edge_data.get("description"),
                    "depth": next_depth,
                    "direction": direction,
                }

                existing = best_by_id.get(neighbor)
                if existing is None:
                    best_by_id[neighbor] = result
                else:
                    # 更高置信度优先；同置信度更浅优先
                    if confidence > float(existing.get("confidence", 0.0)) or (
                        confidence == float(existing.get("confidence", 0.0))
                        and next_depth < int(existing.get("depth", next_depth))
                    ):
                        best_by_id[neighbor] = result

        # Top-K 返回，避免对大结果集全量排序
        results = list(best_by_id.values())
        if max_results > 0 and len(results) > max_results:
            heap: List[Tuple[float, int, Dict[str, Any]]] = []
            counter = 0
            for item in results:
                counter += 1
                conf = float(item.get("confidence", 0.0))
                tup = (conf, counter, item)
                if len(heap) < max_results:
                    heapq.heappush(heap, tup)
                elif conf > heap[0][0]:
                    heapq.heapreplace(heap, tup)
            results = [t[2] for t in heap]

        results.sort(key=lambda x: float(x.get("confidence", 0.0)), reverse=True)

        logger.debug("找到 %d 个相关知识", len(results))
        return results

    def find_path(
        self,
        source_id: str,
        target_id: str,
        min_confidence: float = 0.0,
        allowed_relation_types: Optional[Set[str]] = None,
    ) -> Optional[List[str]]:
        """
        查找两个知识之间的路径

        Args:
            source_id: 源知识ID
            target_id: 目标知识ID
            min_confidence: 路径上每条边的最小置信度（默认 0.0）
            allowed_relation_types: 允许的关系类型集合（None 表示不限制）

        Returns:
            Optional[List[str]]: 路径（知识ID列表），不存在返回 None
        """
        if source_id not in self.graph or target_id not in self.graph:
            return None

        try:
            if min_confidence <= 0.0 and not allowed_relation_types:
                path = nx.shortest_path(self.graph, source_id, target_id)
                logger.debug("找到路径: %d 个节点", len(path))
                return path

            try:
                min_confidence = float(min_confidence)
            except Exception:
                min_confidence = 0.0

            allowed = set(allowed_relation_types) if allowed_relation_types else None

            def _edge_ok(u: str, v: str) -> bool:
                data = self.graph.get_edge_data(u, v) or {}
                if allowed is not None and data.get("relation_type") not in allowed:
                    return False
                try:
                    conf = float(data.get("confidence", 1.0))
                except Exception:
                    conf = 1.0
                return conf >= min_confidence

            view = nx.subgraph_view(self.graph, filter_edge=_edge_ok)
            path = nx.shortest_path(view, source_id, target_id)
            logger.debug("找到路径: %d 个节点", len(path))
            return path
        except nx.NetworkXNoPath:
            logger.debug("不存在路径: %s -> %s", source_id, target_id)
            return None

    def infer_knowledge(
        self,
        knowledge_id: str,
    ) -> List[Dict[str, Any]]:
        """
        基于关系推理知识

        Args:
            knowledge_id: 知识ID

        Returns:
            List[Dict]: 推理结果列表
        """
        if knowledge_id not in self.graph:
            return []

        inferences = []

        # 推理规则1: 传递性关系
        # 如果 A -> B (part_of) 且 B -> C (part_of)，则 A -> C (part_of)
        for neighbor in self.graph.neighbors(knowledge_id):
            edge1 = self.graph[knowledge_id][neighbor]

            if edge1.get("relation_type") == "part_of":
                for second_neighbor in self.graph.neighbors(neighbor):
                    edge2 = self.graph[neighbor][second_neighbor]

                    if edge2.get("relation_type") == "part_of":
                        # 检查是否已存在直接关系
                        if not self.graph.has_edge(knowledge_id, second_neighbor):
                            confidence = (
                                min(edge1.get("confidence", 1.0), edge2.get("confidence", 1.0))
                                * 0.8
                            )  # 降低推理的置信度

                            inferences.append(
                                {
                                    "source_id": knowledge_id,
                                    "target_id": second_neighbor,
                                    "relation_type": "part_of",
                                    "confidence": confidence,
                                    "description": f"通过 {neighbor} 推理",
                                    "inference_type": "transitive",
                                }
                            )

        # 推理规则2: 对称性关系
        # 如果 A -> B (similar_to)，则 B -> A (similar_to)
        for neighbor in self.graph.neighbors(knowledge_id):
            edge = self.graph[knowledge_id][neighbor]

            if edge.get("relation_type") == "similar_to":
                # 检查是否已存在反向关系
                if not self.graph.has_edge(neighbor, knowledge_id):
                    inferences.append(
                        {
                            "source_id": neighbor,
                            "target_id": knowledge_id,
                            "relation_type": "similar_to",
                            "confidence": edge.get("confidence", 1.0),
                            "description": "对称关系",
                            "inference_type": "symmetric",
                        }
                    )

        logger.debug(f"推理出 {len(inferences)} 条新关系")
        return inferences

    def get_statistics(self) -> Dict[str, Any]:
        """
        获取图谱统计信息

        Returns:
            Dict: 统计信息
        """
        stats = {
            "node_count": self.graph.number_of_nodes(),
            "edge_count": self.graph.number_of_edges(),
            "avg_degree": sum(dict(self.graph.degree()).values())
            / max(self.graph.number_of_nodes(), 1),
            "density": nx.density(self.graph),
            "relation_types": {},
            "relation_sources": {},
        }

        # 统计关系类型
        for u, v, data in self.graph.edges(data=True):
            relation_type = data.get("relation_type", "related_to")
            stats["relation_types"][relation_type] = (
                stats["relation_types"].get(relation_type, 0) + 1
            )

            relation_source = data.get("relation_source") or "unknown"
            stats["relation_sources"][relation_source] = (
                stats["relation_sources"].get(relation_source, 0) + 1
            )

        return stats

    def export_for_visualization(self) -> Dict[str, Any]:
        """
        导出图谱数据用于可视化

        Returns:
            Dict: 可视化数据
        """
        nodes = []
        for node_id in self.graph.nodes():
            node_data = self.graph.nodes[node_id]
            nodes.append(
                {
                    "id": node_id,
                    "label": node_data.get("title", node_id),
                    "category": node_data.get("category", "general"),
                    "keywords": node_data.get("keywords", []),
                }
            )

        edges = []
        for u, v, data in self.graph.edges(data=True):
            edges.append(
                {
                    "source": u,
                    "target": v,
                    "relation_type": data.get("relation_type", "related_to"),
                    "relation_source": data.get("relation_source") or "unknown",
                    "label": self.relation_types.get(
                        data.get("relation_type", "related_to"), "相关"
                    ),
                    "confidence": data.get("confidence", 1.0),
                }
            )

        return {
            "nodes": nodes,
            "edges": edges,
            "statistics": self.get_statistics(),
        }
