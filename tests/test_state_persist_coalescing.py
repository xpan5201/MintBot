from __future__ import annotations

from concurrent.futures import Future
from threading import Lock

from src.agent.core import MintChatAgent


def test_post_reply_state_persist_is_coalesced() -> None:
    agent = MintChatAgent.__new__(MintChatAgent)

    # Minimal attributes used by _post_reply_actions()
    agent._state_persist_lock = Lock()  # type: ignore[attr-defined]
    agent._pending_state_persist = None  # type: ignore[attr-defined]

    agent._save_interaction_to_memory = lambda *_a, **_k: None  # type: ignore[assignment]
    agent._save_stream_interaction = lambda *_a, **_k: None  # type: ignore[assignment]
    agent._run_background_memory_tasks = lambda *_a, **_k: None  # type: ignore[assignment]
    agent._prefetch_tts_segments = lambda *_a, **_k: None  # type: ignore[assignment]

    class _DummyEmotionEngine:
        def analyze_message(self, _text: str):  # noqa: ANN001
            return None

        def is_negative_interaction(self, _text: str, _emotion):  # noqa: ANN001
            return False

        def update_user_profile(self, *_, **__):  # noqa: ANN001
            return None

        def decay_emotion(self, *_, **__):  # noqa: ANN001
            return None

        def persist(self, *_, **__):  # noqa: ANN001
            return None

    class _DummyPersist:
        def persist(self, *_, **__):  # noqa: ANN001
            return None

    agent.emotion_engine = _DummyEmotionEngine()  # type: ignore[assignment]
    agent.mood_system = _DummyPersist()  # type: ignore[assignment]
    agent.style_learner = _DummyPersist()  # type: ignore[assignment]
    agent.character_state = _DummyPersist()  # type: ignore[assignment]

    submitted: list[str] = []
    pending = Future()

    def submit_task(func, *, label: str):  # noqa: ANN001
        submitted.append(label)
        # Do not run func; we only want to verify scheduling behavior.
        return pending

    agent._submit_background_task = submit_task  # type: ignore[assignment]

    agent._post_reply_actions("hi", "ok", save_to_long_term=False, stream=False)
    agent._post_reply_actions("hi", "ok", save_to_long_term=False, stream=False)

    assert submitted == ["state-persist"]
