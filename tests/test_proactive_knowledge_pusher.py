from __future__ import annotations

from pathlib import Path

from src.agent.knowledge_recommender import ProactiveKnowledgePusher


def test_proactive_pusher_topic_change_requires_recent_topics():
    pusher = ProactiveKnowledgePusher(push_cooldown_s=0)

    assert (
        pusher.should_push(
            "u",
            {"topic": "work", "recent_topics": [], "user_message": "hi"},
        )
        is False
    )

    assert (
        pusher.should_push(
            "u",
            {"topic": "work", "recent_topics": ["life"], "user_message": "hi"},
        )
        is True
    )


def test_proactive_pusher_knowledge_gap_detection():
    pusher = ProactiveKnowledgePusher(push_cooldown_s=0)

    assert pusher.should_push("u", {"user_message": "怎么做？"}) is True
    assert pusher.should_push("u", {"user_message": "这能用吗"}) is True
    assert pusher.should_push("u", {"user_message": "今天真不错"}) is False


def test_proactive_pusher_disable_flag():
    pusher = ProactiveKnowledgePusher(push_cooldown_s=0)

    assert (
        pusher.should_push("u", {"user_message": "怎么做？", "disable_proactive_push": True})
        is False
    )


def test_proactive_pusher_related_trigger_ignores_filler_messages() -> None:
    pusher = ProactiveKnowledgePusher(push_cooldown_s=0)

    assert (
        pusher.should_push(
            "u",
            {"user_message": "好的", "last_used_knowledge": {"keywords": ["k"]}},
        )
        is False
    )

    assert (
        pusher.should_push(
            "u",
            {"user_message": "继续讲讲", "last_used_knowledge": {"keywords": ["k"]}},
        )
        is True
    )


def test_proactive_pusher_dedup_and_history_snapshot():
    pusher = ProactiveKnowledgePusher(push_cooldown_s=0, max_pushes_per_day=10)
    context = {
        "user_message": "怎么做？",
        "topic": "study",
        "recent_topics": ["life"],
        "keywords": ["Python"],
    }
    all_knowledge = [
        {
            "id": "k1",
            "title": "Python 入门",
            "content": "Python ...",
            "category": "study",
            "keywords": ["python"],
            "quality_score": 0.9,
        },
        # 缺失 id，但与上面重复（应通过 hash key 去重）
        {
            "title": "Python 入门",
            "content": "Python ...",
            "category": "study",
            "keywords": ["python"],
            "quality_score": 0.9,
        },
    ]

    pushed = pusher.push_knowledge("u", context, all_knowledge, k=3)
    assert len(pushed) == 1
    assert pusher.push_history
    assert "user_message" not in pusher.push_history[-1]["context"]


def test_proactive_pusher_daily_limit_blocks_second_push():
    pusher = ProactiveKnowledgePusher(push_cooldown_s=0, max_pushes_per_day=1)
    context = {
        "user_message": "怎么做？",
        "topic": "study",
        "recent_topics": ["life"],
    }
    all_knowledge = [
        {
            "id": "k1",
            "title": "A",
            "content": "A",
            "category": "study",
            "keywords": [],
            "quality_score": 0.9,
        },
        {
            "id": "k2",
            "title": "B",
            "content": "B",
            "category": "study",
            "keywords": [],
            "quality_score": 0.9,
        },
    ]

    first = pusher.push_knowledge("u", context, all_knowledge, k=1)
    assert len(first) == 1

    second = pusher.push_knowledge("u", context, all_knowledge, k=1)
    assert second == []


def test_lore_book_push_knowledge_skips_loading_all_lores_when_not_triggered() -> None:
    from src.agent.advanced_memory import LoreBook

    lore_book = LoreBook.__new__(LoreBook)

    class DummyPusher:
        def should_push(self, _user_id: str, _context: dict) -> bool:
            return False

        def push_knowledge(self, *_args: object, **_kwargs: object) -> None:  # pragma: no cover
            raise AssertionError("push_knowledge should not be called")

    lore_book.pusher = DummyPusher()
    lore_book.usage_tracker = None

    def get_all_lores(*_args: object, **_kwargs: object) -> None:  # pragma: no cover
        raise AssertionError("get_all_lores should not be called")

    lore_book.get_all_lores = get_all_lores  # type: ignore[assignment]

    assert lore_book.push_knowledge("u", {"user_message": "hi"}, k=3) == []


def test_proactive_pusher_persist_state_blocks_by_cooldown(tmp_path: Path) -> None:
    state_file = tmp_path / "proactive_push_state.json"

    pusher = ProactiveKnowledgePusher(
        push_cooldown_s=3600,
        max_pushes_per_day=10,
        persist_state=True,
        state_file=state_file,
    )
    context = {"user_message": "怎么做？", "topic": "study", "recent_topics": ["life"]}
    all_knowledge = [
        {
            "id": "k1",
            "title": "A",
            "content": "A",
            "category": "study",
            "keywords": [],
            "quality_score": 0.9,
        }
    ]

    first = pusher.push_knowledge("u", context, all_knowledge, k=1)
    assert len(first) == 1
    assert state_file.exists()

    pusher2 = ProactiveKnowledgePusher(
        push_cooldown_s=3600,
        max_pushes_per_day=10,
        persist_state=True,
        state_file=state_file,
    )
    assert pusher2.should_push("u", {"user_message": "怎么做？"}) is False


def test_proactive_pusher_persist_state_dedup_across_restart(tmp_path: Path) -> None:
    state_file = tmp_path / "proactive_push_state.json"

    context = {"user_message": "怎么做？", "topic": "study", "recent_topics": ["life"]}
    all_knowledge = [
        {
            "id": "k1",
            "title": "A",
            "content": "A",
            "category": "study",
            "keywords": [],
            "quality_score": 0.9,
        }
    ]

    pusher = ProactiveKnowledgePusher(
        push_cooldown_s=0,
        max_pushes_per_day=10,
        persist_state=True,
        state_file=state_file,
    )
    assert pusher.push_knowledge("u", context, all_knowledge, k=1)

    pusher2 = ProactiveKnowledgePusher(
        push_cooldown_s=0,
        max_pushes_per_day=10,
        persist_state=True,
        state_file=state_file,
    )
    assert pusher2.push_knowledge("u", context, all_knowledge, k=1) == []


def test_lore_book_push_knowledge_prefers_candidate_pool_over_full_scan() -> None:
    from src.agent.advanced_memory import LoreBook

    class _Doc:
        def __init__(self, *, page_content: str, metadata: dict) -> None:
            self.page_content = page_content
            self.metadata = metadata

    class _VS:
        def similarity_search_with_score(self, _query: str, *, k: int):  # noqa: ANN001
            doc = _Doc(
                page_content="【A】\nA",
                metadata={
                    "id": "k1",
                    "title": "A",
                    "category": "study",
                    "keywords": "python",
                    "source": "unit-test",
                },
            )
            return [(doc, 0.0)][:k]

    lore_book = LoreBook.__new__(LoreBook)
    lore_book.vectorstore = _VS()
    lore_book.pusher = ProactiveKnowledgePusher(push_cooldown_s=0)
    lore_book.usage_tracker = None
    lore_book.quality_manager = None

    def get_all_lores(*_args: object, **_kwargs: object) -> None:  # pragma: no cover
        raise AssertionError("get_all_lores should not be called")

    lore_book.get_all_lores = get_all_lores  # type: ignore[assignment]

    pushed = lore_book.push_knowledge(
        "u",
        {
            "user_message": "怎么做？",
            "topic": "study",
            "recent_topics": ["life"],
            "keywords": ["python"],
        },
        k=1,
    )
    assert pushed and pushed[0].get("id") == "k1"
