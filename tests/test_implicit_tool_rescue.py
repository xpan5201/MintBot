from __future__ import annotations

from src.agent.core import AgentConversationBundle, MintChatAgent
from src.config.settings import settings
from src.utils.tool_context import ToolTraceRecorder


def test_chat_progress_only_triggers_implicit_time_rescue(monkeypatch) -> None:
    monkeypatch.setattr(settings.agent, "implicit_tool_rescue_enabled", True, raising=False)

    agent = MintChatAgent.__new__(MintChatAgent)

    class DummyRegistry:
        def execute_tool(self, name: str, timeout: float = 30.0, **kwargs: object) -> str:
            assert name == "get_current_time"
            return "TOOL_RESULT: get_current_time\nlocal_time: 2099-01-01 00:00:00"

    def build_bundle(message: str, **kwargs: object) -> AgentConversationBundle:
        return AgentConversationBundle(
            messages=[],
            save_message=message,
            original_message=message,
            processed_message=message,
            tool_recorder=ToolTraceRecorder(),
        )

    agent.tool_registry = DummyRegistry()  # type: ignore[assignment]
    agent._build_agent_bundle = build_bundle  # type: ignore[assignment]
    agent._invoke_with_failover = lambda bundle, **kwargs: {  # type: ignore[assignment]
        "messages": [{"role": "assistant", "content": "小雪糕这就帮主人看看时间喵~"}]
    }
    agent._post_reply_actions = lambda *args, **kwargs: None  # type: ignore[assignment]

    reply = MintChatAgent.chat(agent, "现在几点了？")
    assert "2099-01-01 00:00:00" in reply


def test_empty_reply_rescue_triggers_implicit_date_rescue(monkeypatch) -> None:
    monkeypatch.setattr(settings.agent, "implicit_tool_rescue_enabled", True, raising=False)

    agent = MintChatAgent.__new__(MintChatAgent)

    class DummyRegistry:
        def execute_tool(self, name: str, timeout: float = 30.0, **kwargs: object) -> str:
            assert name == "get_current_date"
            return "\n".join(
                [
                    "TOOL_RESULT: get_current_date",
                    "local_date: 2099-01-02",
                    "weekday: 星期六",
                ]
            )

    agent.tool_registry = DummyRegistry()  # type: ignore[assignment]
    agent._build_image_analysis_fallback_reply = lambda bundle: ""  # type: ignore[assignment]
    agent._fast_retry_enabled = False  # type: ignore[assignment]

    msg = "今天是几号？星期几？"
    bundle = AgentConversationBundle(
        messages=[],
        save_message=msg,
        original_message=msg,
        processed_message=msg,
        tool_recorder=ToolTraceRecorder(),
    )

    rescued = MintChatAgent._rescue_empty_reply(agent, bundle, raw_reply="", source="chat")
    assert rescued is not None
    assert "2099-01-02" in rescued
    assert "星期六" in rescued
