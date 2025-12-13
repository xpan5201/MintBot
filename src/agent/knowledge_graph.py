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
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

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
    logger.warning("LangChain LLM 依赖导入失败，LLM 辅助关系提取不可用: %s", exc)


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
    
    def __init__(self, graph_file: Optional[Path] = None):
        """
        初始化知识图谱
        
        Args:
            graph_file: 图谱数据文件路径
        """
        self.graph_file = graph_file or Path("data/memory/knowledge_graph.json")
        self.graph_file.parent.mkdir(parents=True, exist_ok=True)
        
        # 创建有向图
        self.graph = nx.DiGraph()
        
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
        
        # 加载图谱数据
        self._load_graph()
        
        # LLM 延迟初始化（首次需要 LLM 辅助提取时再创建）
        self.llm = None
        
        logger.info("知识图谱初始化完成")
    
    def _load_graph(self):
        """加载图谱数据"""
        if self.graph_file.exists():
            try:
                with open(self.graph_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                
                # 加载节点
                for node_data in data.get("nodes", []):
                    self.graph.add_node(
                        node_data["id"],
                        **node_data.get("attributes", {})
                    )
                
                # 加载边
                for edge_data in data.get("edges", []):
                    self.graph.add_edge(
                        edge_data["source"],
                        edge_data["target"],
                        relation_type=edge_data.get("relation_type", "related_to"),
                        confidence=edge_data.get("confidence", 1.0),
                        description=edge_data.get("description"),
                        created_at=edge_data.get("created_at"),
                    )
                
                logger.info(f"加载知识图谱: {self.graph.number_of_nodes()} 个节点, {self.graph.number_of_edges()} 条边")
            
            except Exception as e:
                logger.error(f"加载知识图谱失败: {e}")
    
    def _save_graph(self):
        """保存图谱数据"""
        try:
            # 准备节点数据
            nodes = [
                {
                    "id": node,
                    "attributes": self.graph.nodes[node],
                }
                for node in self.graph.nodes()
            ]
            
            # 准备边数据
            edges = [
                {
                    "source": u,
                    "target": v,
                    "relation_type": data.get("relation_type", "related_to"),
                    "confidence": data.get("confidence", 1.0),
                    "description": data.get("description"),
                    "created_at": data.get("created_at"),
                }
                for u, v, data in self.graph.edges(data=True)
            ]

            # 保存到文件
            with open(self.graph_file, "w", encoding="utf-8") as f:
                json.dump(
                    {"nodes": nodes, "edges": edges},
                    f,
                    ensure_ascii=False,
                    indent=2
                )

            logger.debug(f"保存知识图谱: {len(nodes)} 个节点, {len(edges)} 条边")

        except Exception as e:
            logger.error(f"保存知识图谱失败: {e}")

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
        self.graph.add_node(
            knowledge_id,
            title=title,
            category=category,
            keywords=keywords or [],
            created_at=datetime.now().isoformat(),
        )

        self._save_graph()
        logger.debug(f"添加知识节点: {title}")

    def add_relation(
        self,
        source_id: str,
        target_id: str,
        relation_type: str = "related_to",
        confidence: float = 1.0,
        description: Optional[str] = None,
    ):
        """
        添加知识关系

        Args:
            source_id: 源知识ID
            target_id: 目标知识ID
            relation_type: 关系类型
            confidence: 置信度
            description: 关系描述
        """
        # 检查节点是否存在
        if source_id not in self.graph:
            logger.warning(f"源知识节点不存在: {source_id}")
            return

        if target_id not in self.graph:
            logger.warning(f"目标知识节点不存在: {target_id}")
            return

        # 添加边
        self.graph.add_edge(
            source_id,
            target_id,
            relation_type=relation_type,
            confidence=confidence,
            description=description,
            created_at=datetime.now().isoformat(),
        )

        self._save_graph()
        logger.debug(f"添加关系: {source_id} -> {target_id} ({relation_type})")

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
        relations = []

        for i, k1 in enumerate(knowledge_list):
            for k2 in knowledge_list[i+1:]:
                # 规则1: 相同类别的知识相关
                if k1.get("category") == k2.get("category"):
                    relations.append(KnowledgeRelation(
                        source_id=k1.get("id"),
                        target_id=k2.get("id"),
                        relation_type="related_to",
                        confidence=0.6,
                        description="相同类别",
                    ))

                # 规则2: 关键词重叠的知识相关
                keywords1 = set(k1.get("keywords", []))
                keywords2 = set(k2.get("keywords", []))
                overlap = keywords1 & keywords2

                if overlap:
                    confidence = len(overlap) / max(len(keywords1), len(keywords2))
                    relations.append(KnowledgeRelation(
                        source_id=k1.get("id"),
                        target_id=k2.get("id"),
                        relation_type="related_to",
                        confidence=confidence,
                        description=f"共享关键词: {', '.join(overlap)}",
                    ))

        logger.info(f"规则提取关系: {len(relations)} 条")
        return relations

    def build_graph_from_knowledge(
        self,
        knowledge_list: List[Dict[str, Any]],
        use_llm: bool = True,
    ):
        """
        从知识列表构建图谱

        Args:
            knowledge_list: 知识列表
            use_llm: 是否使用 LLM 提取关系
        """
        # 添加节点
        for knowledge in knowledge_list:
            self.add_knowledge_node(
                knowledge_id=knowledge.get("id"),
                title=knowledge.get("title"),
                category=knowledge.get("category"),
                keywords=knowledge.get("keywords", []),
            )

        # 提取关系
        if use_llm and self.llm:
            relations = self.extract_relations_llm(knowledge_list)
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
            )

        logger.info(f"构建知识图谱完成: {self.graph.number_of_nodes()} 个节点, {self.graph.number_of_edges()} 条边")

    def find_related_knowledge(
        self,
        knowledge_id: str,
        max_depth: int = 2,
        min_confidence: float = 0.5,
    ) -> List[Dict[str, Any]]:
        """
        查找相关知识

        Args:
            knowledge_id: 知识ID
            max_depth: 最大深度
            min_confidence: 最小置信度

        Returns:
            List[Dict]: 相关知识列表
        """
        if knowledge_id not in self.graph:
            logger.warning(f"知识节点不存在: {knowledge_id}")
            return []

        related = []
        visited = set()
        queue = [(knowledge_id, 0)]

        while queue:
            current_id, depth = queue.pop(0)

            if current_id in visited or depth > max_depth:
                continue

            visited.add(current_id)

            # 获取邻居节点
            for neighbor in self.graph.neighbors(current_id):
                edge_data = self.graph[current_id][neighbor]
                confidence = edge_data.get("confidence", 1.0)

                if confidence >= min_confidence and neighbor not in visited:
                    related.append({
                        "id": neighbor,
                        "title": self.graph.nodes[neighbor].get("title"),
                        "category": self.graph.nodes[neighbor].get("category"),
                        "relation_type": edge_data.get("relation_type"),
                        "confidence": confidence,
                        "description": edge_data.get("description"),
                        "depth": depth + 1,
                    })

                    if depth + 1 < max_depth:
                        queue.append((neighbor, depth + 1))

        # 按置信度排序
        related.sort(key=lambda x: x["confidence"], reverse=True)

        logger.debug(f"找到 {len(related)} 个相关知识")
        return related

    def find_path(
        self,
        source_id: str,
        target_id: str,
    ) -> Optional[List[str]]:
        """
        查找两个知识之间的路径

        Args:
            source_id: 源知识ID
            target_id: 目标知识ID

        Returns:
            Optional[List[str]]: 路径（知识ID列表），不存在返回 None
        """
        if source_id not in self.graph or target_id not in self.graph:
            return None

        try:
            path = nx.shortest_path(self.graph, source_id, target_id)
            logger.debug(f"找到路径: {len(path)} 个节点")
            return path
        except nx.NetworkXNoPath:
            logger.debug(f"不存在路径: {source_id} -> {target_id}")
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
                            confidence = min(
                                edge1.get("confidence", 1.0),
                                edge2.get("confidence", 1.0)
                            ) * 0.8  # 降低推理的置信度

                            inferences.append({
                                "source_id": knowledge_id,
                                "target_id": second_neighbor,
                                "relation_type": "part_of",
                                "confidence": confidence,
                                "description": f"通过 {neighbor} 推理",
                                "inference_type": "transitive",
                            })

        # 推理规则2: 对称性关系
        # 如果 A -> B (similar_to)，则 B -> A (similar_to)
        for neighbor in self.graph.neighbors(knowledge_id):
            edge = self.graph[knowledge_id][neighbor]

            if edge.get("relation_type") == "similar_to":
                # 检查是否已存在反向关系
                if not self.graph.has_edge(neighbor, knowledge_id):
                    inferences.append({
                        "source_id": neighbor,
                        "target_id": knowledge_id,
                        "relation_type": "similar_to",
                        "confidence": edge.get("confidence", 1.0),
                        "description": "对称关系",
                        "inference_type": "symmetric",
                    })

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
            "avg_degree": sum(dict(self.graph.degree()).values()) / max(self.graph.number_of_nodes(), 1),
            "density": nx.density(self.graph),
            "relation_types": {},
        }

        # 统计关系类型
        for u, v, data in self.graph.edges(data=True):
            relation_type = data.get("relation_type", "related_to")
            stats["relation_types"][relation_type] = stats["relation_types"].get(relation_type, 0) + 1

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
            nodes.append({
                "id": node_id,
                "label": node_data.get("title", node_id),
                "category": node_data.get("category", "general"),
                "keywords": node_data.get("keywords", []),
            })

        edges = []
        for u, v, data in self.graph.edges(data=True):
            edges.append({
                "source": u,
                "target": v,
                "label": self.relation_types.get(
                    data.get("relation_type", "related_to"),
                    "相关"
                ),
                "confidence": data.get("confidence", 1.0),
            })

        return {
            "nodes": nodes,
            "edges": edges,
            "statistics": self.get_statistics(),
        }
