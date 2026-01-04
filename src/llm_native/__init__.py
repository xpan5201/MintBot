"""
MintChat native 协议层与运行时组件。

本包用于承载 OpenAI-compatible 后端与自研管线的公共协议与抽象，包括：
- Message 协议（对齐 OpenAI Chat Completions messages 形状）
- StreamEvent 协议（统一流式语义：TextDelta/ToolCallDelta/ToolResult/Error/Done）
- ToolSpec/ToolRegistry（工具 schema 与注册表）
- ChatBackend 接口（complete/stream）
 - ToolRunner / AgentRunner（自研工具执行与循环）

说明：该包的接口面向“稳定优先”，避免与 GUI/业务层强耦合。
"""

from .backend import BackendConfig, ChatBackend, ChatRequest, ChatResponse
from .events import (
    DoneEvent,
    ErrorEvent,
    StreamEvent,
    TextDeltaEvent,
    ToolCallAccumulator,
    ToolCallDeltaEvent,
    ToolCallState,
    ToolResultEvent,
)
from .messages import ImageURLPart, Message, Role, TextPart, ToolCall
from .agent_runner import AgentRunnerConfig, NativeToolLoopRunner
from .tool_runner import ToolExecutor, ToolRunner
from .tools import ToolRegistry, ToolSpec, pydantic_to_strict_json_schema

__all__ = [
    "AgentRunnerConfig",
    "BackendConfig",
    "ChatBackend",
    "ChatRequest",
    "ChatResponse",
    "DoneEvent",
    "ErrorEvent",
    "ImageURLPart",
    "Message",
    "Role",
    "StreamEvent",
    "TextDeltaEvent",
    "TextPart",
    "ToolExecutor",
    "ToolCall",
    "ToolCallAccumulator",
    "ToolCallDeltaEvent",
    "ToolCallState",
    "ToolRunner",
    "ToolRegistry",
    "ToolResultEvent",
    "ToolSpec",
    "NativeToolLoopRunner",
    "pydantic_to_strict_json_schema",
]
