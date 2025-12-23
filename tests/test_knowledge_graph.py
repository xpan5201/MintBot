from __future__ import annotations

from pathlib import Path

from src.agent.knowledge_graph import KnowledgeGraph, KnowledgeRelation


def test_build_graph_defers_save_to_single_write(temp_dir: Path) -> None:
    graph_file = temp_dir / "knowledge_graph.json"
    kg = KnowledgeGraph(graph_file=graph_file)

    save_calls = 0
    original_save = kg._save_graph

    def _spy_save() -> None:
        nonlocal save_calls
        save_calls += 1
        original_save()

    kg._save_graph = _spy_save  # type: ignore[method-assign]

    kg.build_graph_from_knowledge(
        [
            {"id": "a", "title": "A", "category": "general", "keywords": ["x"]},
            {"id": "b", "title": "B", "category": "general", "keywords": ["x", "y"]},
            {"id": "c", "title": "C", "category": "general", "keywords": ["z"]},
        ],
        use_llm=False,
        rebuild=True,
    )

    assert save_calls == 1
    assert graph_file.exists()


def test_find_related_knowledge_is_bidirectional_for_related_to(temp_dir: Path) -> None:
    graph_file = temp_dir / "knowledge_graph.json"
    kg = KnowledgeGraph(graph_file=graph_file)

    kg.build_graph_from_knowledge(
        [
            {"id": "a", "title": "A", "category": "character", "keywords": ["cat"]},
            {"id": "b", "title": "B", "category": "character", "keywords": ["cat"]},
        ],
        use_llm=False,
        rebuild=True,
    )

    related_a = {item["id"] for item in kg.find_related_knowledge("a", max_depth=1)}
    related_b = {item["id"] for item in kg.find_related_knowledge("b", max_depth=1)}

    assert "b" in related_a
    assert "a" in related_b


def test_find_related_knowledge_respects_max_depth(temp_dir: Path) -> None:
    graph_file = temp_dir / "knowledge_graph.json"
    kg = KnowledgeGraph(graph_file=graph_file)

    kg.build_graph_from_knowledge(
        [
            {"id": "a", "title": "A", "category": "general", "keywords": ["x"]},
            {"id": "b", "title": "B", "category": "general", "keywords": ["x"]},
        ],
        use_llm=False,
        rebuild=True,
    )

    assert kg.find_related_knowledge("a", max_depth=0) == []


def test_build_graph_attempts_llm_then_falls_back_to_rules(temp_dir: Path) -> None:
    graph_file = temp_dir / "knowledge_graph.json"
    kg = KnowledgeGraph(graph_file=graph_file)

    calls = {"llm": 0, "rules": 0}

    def _fake_llm(_knowledge_list):
        calls["llm"] += 1
        return []

    def _fake_rules(_knowledge_list):
        calls["rules"] += 1
        return []

    kg.extract_relations_llm = _fake_llm  # type: ignore[method-assign]
    kg.extract_relations_rule_based = _fake_rules  # type: ignore[method-assign]

    kg.build_graph_from_knowledge(
        [{"id": "a", "title": "A", "category": "general", "keywords": []}],
        use_llm=True,
        rebuild=True,
    )

    assert calls["llm"] == 1
    assert calls["rules"] == 1


def test_find_path_respects_min_confidence(temp_dir: Path) -> None:
    graph_file = temp_dir / "knowledge_graph.json"
    kg = KnowledgeGraph(graph_file=graph_file)

    kg.add_knowledge_node("a", title="A", category="general", keywords=["x"])
    kg.add_knowledge_node("b", title="B", category="general", keywords=["x"])
    kg.add_knowledge_node("c", title="C", category="general", keywords=["x"])

    kg.add_relation("a", "b", relation_type="precedes", confidence=0.4, bidirectional=False)
    kg.add_relation("b", "c", relation_type="precedes", confidence=0.9, bidirectional=False)

    assert kg.find_path("a", "c") == ["a", "b", "c"]
    assert kg.find_path("a", "c", min_confidence=0.5) is None


def test_refresh_rule_relations_adds_rule_edges(temp_dir: Path) -> None:
    graph_file = temp_dir / "knowledge_graph.json"
    kg = KnowledgeGraph(graph_file=graph_file)

    kg.add_knowledge_node("a", title="A", category="general", keywords=["x", "y"])
    kg.add_knowledge_node("b", title="B", category="general", keywords=["x"])

    kg.refresh_rule_relations_for_node("a")

    assert kg.graph.has_edge("a", "b")
    data = kg.graph.get_edge_data("a", "b") or {}
    assert data.get("relation_source") == "rule"
    assert data.get("relation_type") == "related_to"


def test_rule_relations_do_not_override_manual_edges(temp_dir: Path) -> None:
    graph_file = temp_dir / "knowledge_graph.json"
    kg = KnowledgeGraph(graph_file=graph_file)

    kg.add_knowledge_node("a", title="A", category="general", keywords=["x"])
    kg.add_knowledge_node("b", title="B", category="general", keywords=["x"])

    # 手动关系优先级更高，不应被 rule 刷新覆盖
    kg.add_relation("a", "b", relation_type="part_of", confidence=1.0, bidirectional=False)
    kg.refresh_rule_relations_for_node("a")

    data = kg.graph.get_edge_data("a", "b") or {}
    assert data.get("relation_source") == "manual"
    assert data.get("relation_type") == "part_of"


def test_build_graph_relation_source_llm(temp_dir: Path) -> None:
    graph_file = temp_dir / "knowledge_graph.json"
    kg = KnowledgeGraph(graph_file=graph_file)

    # 让 LLM 提取返回 1 条关系，确保 build_graph 使用 llm 来源标记
    def _fake_llm(_knowledge_list):
        return [
            KnowledgeRelation(
                source_id="a",
                target_id="b",
                relation_type="related_to",
                confidence=0.9,
                description="fake llm",
            )
        ]

    kg.extract_relations_llm = _fake_llm  # type: ignore[method-assign]

    kg.build_graph_from_knowledge(
        [
            {"id": "a", "title": "A", "category": "general", "keywords": ["x"]},
            {"id": "b", "title": "B", "category": "general", "keywords": ["x"]},
        ],
        use_llm=True,
        rebuild=True,
    )

    data = kg.graph.get_edge_data("a", "b") or {}
    assert data.get("relation_source") == "llm"


def test_autosave_false_requires_flush(temp_dir: Path) -> None:
    graph_file = temp_dir / "knowledge_graph.json"
    kg = KnowledgeGraph(graph_file=graph_file, autosave=False)

    kg.add_knowledge_node("a", title="A", category="general", keywords=["x"])
    assert not graph_file.exists()

    kg.flush()
    assert graph_file.exists()
