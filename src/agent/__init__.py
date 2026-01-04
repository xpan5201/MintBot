"""
智能体核心模块

包含 Agent 核心逻辑、记忆系统、工具集等。
"""

from typing import TYPE_CHECKING, Any

__all__ = ["MintChatAgent", "MemoryManager", "ToolRegistry"]


if TYPE_CHECKING:  # pragma: no cover
    from .core import MintChatAgent as MintChatAgent
    from .memory import MemoryManager as MemoryManager
    from .tools import ToolRegistry as ToolRegistry


def __getattr__(name: str) -> Any:  # pragma: no cover - 运行时懒加载
    """
    懒加载：避免 `import src.agent` 时强制导入重依赖，提升启动速度与可用性。

    说明：`from src.agent import MintChatAgent` 仍然可用，会在此处按需导入。
    """
    if name == "MintChatAgent":
        from .core import MintChatAgent as _MintChatAgent

        return _MintChatAgent
    if name == "MemoryManager":
        from .memory import MemoryManager as _MemoryManager

        return _MemoryManager
    if name == "ToolRegistry":
        from .tools import ToolRegistry as _ToolRegistry

        return _ToolRegistry
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
