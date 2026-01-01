"""
MCP (Model Context Protocol) 工具管理器。

目标：
- 以“可选依赖”的方式集成 MCP（未安装 mcp 时不影响主程序）
- 支持从配置启动/连接多个 MCP 服务器，并将其工具注册到 LangChain 工具列表
- 通过后台事件循环线程复用连接（stdio/http/sse 等），避免每次调用重复建联
"""

from __future__ import annotations

import asyncio
import json
import re
import threading
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.config.settings import settings
from src.utils.async_loop_thread import AsyncLoopThread
from src.utils.logger import get_logger
from src.utils.tool_context import get_current_tool_timeout_s

logger = get_logger(__name__)

_MCP_IMPORT_ERROR: Optional[BaseException] = None
try:
    from mcp import ClientSession, StdioServerParameters  # type: ignore
    from mcp.client.stdio import stdio_client  # type: ignore

    HAS_MCP = True
except Exception as exc:  # pragma: no cover - 环境依赖差异
    HAS_MCP = False
    _MCP_IMPORT_ERROR = exc
    ClientSession = None  # type: ignore[assignment]
    StdioServerParameters = None  # type: ignore[assignment]
    stdio_client = None  # type: ignore[assignment]


try:
    from pydantic import BaseModel, Field, create_model

    HAS_PYDANTIC = True
except Exception:  # pragma: no cover
    HAS_PYDANTIC = False
    BaseModel = object  # type: ignore[assignment]
    Field = None  # type: ignore[assignment]
    create_model = None  # type: ignore[assignment]


_STRUCTURED_TOOL_IMPORT_ERROR: Optional[BaseException] = None
try:
    from langchain_core.tools import StructuredTool  # type: ignore

    HAS_STRUCTURED_TOOL = True
except Exception as exc:  # pragma: no cover - 环境依赖差异
    HAS_STRUCTURED_TOOL = False
    _STRUCTURED_TOOL_IMPORT_ERROR = exc
    StructuredTool = None  # type: ignore[assignment]


_SAFE_NAME_RE = re.compile(r"[^0-9a-zA-Z_]+")


def _sanitize_name(value: str) -> str:
    value = (value or "").strip()
    if not value:
        return "unknown"
    value = value.replace("-", "_").replace(".", "_").replace(" ", "_")
    value = _SAFE_NAME_RE.sub("_", value)
    value = re.sub(r"_+", "_", value).strip("_")
    return value or "unknown"


def _extract_tool_result_text(result: Any) -> str:
    """
    将 MCP call_tool 返回结果尽量转换为可读文本。
    """
    if result is None:
        return ""

    content = getattr(result, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: List[str] = []
        for item in content:
            text = getattr(item, "text", None)
            if isinstance(text, str) and text:
                parts.append(text)
                continue
            # 兼容 dict 结构
            if isinstance(item, dict):
                text = item.get("text") or item.get("content")
                if isinstance(text, str) and text:
                    parts.append(text)
        if parts:
            return "\n".join(parts)

    # 兼容 pydantic model_dump / dict
    try:
        if hasattr(result, "model_dump"):
            return json.dumps(result.model_dump(), ensure_ascii=False)
    except Exception:
        pass

    try:
        if isinstance(result, dict):
            return json.dumps(result, ensure_ascii=False)
    except Exception:
        pass

    return str(result)


def _json_schema_to_pydantic_model(
    *,
    model_name: str,
    schema: Optional[Dict[str, Any]],
) -> Optional[type[BaseModel]]:
    """
    将 MCP 工具的 JSON Schema（常见为 inputSchema）转换为 Pydantic args_schema。

    只实现常用字段：
    - type: object
    - properties / required
    - description / default
    """
    if not HAS_PYDANTIC or create_model is None or Field is None:
        return None

    if not schema or not isinstance(schema, dict):
        return None

    if schema.get("type") != "object":
        return None

    properties = schema.get("properties")
    if not isinstance(properties, dict) or not properties:
        return None

    required = schema.get("required") or []
    required_set = set(required) if isinstance(required, list) else set()

    def type_from(prop_schema: Dict[str, Any]) -> Any:
        t = prop_schema.get("type")
        if t == "string":
            return str
        if t == "integer":
            return int
        if t == "number":
            return float
        if t == "boolean":
            return bool
        if t == "array":
            return list
        if t == "object":
            return dict
        return Any

    fields: Dict[str, Tuple[Any, Any]] = {}
    for prop_name, prop_schema in properties.items():
        if not isinstance(prop_name, str):
            continue
        if not isinstance(prop_schema, dict):
            prop_schema = {}

        field_type = type_from(prop_schema)
        desc = prop_schema.get("description")
        default = prop_schema.get("default", None)

        if prop_name in required_set:
            fields[prop_name] = (
                field_type,
                Field(..., description=str(desc) if desc else ""),
            )  # type: ignore[arg-type]
        else:
            fields[prop_name] = (
                Optional[field_type],  # type: ignore[valid-type]
                Field(default, description=str(desc) if desc else ""),  # type: ignore[arg-type]
            )

    if not fields:
        return None

    try:
        return create_model(model_name, **fields)  # type: ignore[call-arg]
    except Exception:
        return None


@dataclass
class _ServerRuntime:
    name: str
    session: Any
    session_cm: Any
    client_cm: Any
    call_lock: asyncio.Semaphore


class MCPManager:
    """
    MCP 管理器：负责连接/维护 MCP 会话，并将其工具适配为 LangChain Tool。
    """

    def __init__(self) -> None:
        self._state_lock = threading.Lock()
        self._init_lock = threading.Lock()
        self._initialized = False

        self._runner = AsyncLoopThread(thread_name="mintchat-mcp")
        self._servers: Dict[str, _ServerRuntime] = {}
        self.sessions: Dict[str, Any] = {}
        self.tools: List[Any] = []

        # 连接超时（秒）
        self._connect_timeout_s = float(getattr(settings.agent, "tool_timeout_s", 30.0))

    @property
    def enabled(self) -> bool:
        cfg = getattr(settings, "mcp", None)
        if not cfg or not getattr(cfg, "enabled", False):
            return False
        servers = getattr(cfg, "servers", None) or {}
        return bool(servers)

    def initialize(self) -> None:
        """
        同步初始化（幂等）。

        - 未安装 mcp / 未启用 / 未配置 server 时：快速返回
        - 初始化失败：记录 warning 并快速返回（不影响主流程）
        """
        if self._initialized:
            return

        with self._init_lock:
            if self._initialized:
                return
            if not self.enabled:
                self._initialized = True
                return
            if not HAS_MCP:
                logger.warning("mcp 未安装，MCP 工具不可用: %s", _MCP_IMPORT_ERROR)
                self._initialized = True
                return

            try:
                self._runner.run(self._ainitialize(), timeout=self._connect_timeout_s)
            except Exception as exc:
                logger.warning("MCP 初始化失败，将跳过 MCP 工具: %s", exc)
            finally:
                self._initialized = True

    async def _ainitialize(self) -> None:
        cfg = settings.mcp
        servers = getattr(cfg, "servers", None) or {}
        enabled_items = [
            (name, server_cfg)
            for name, server_cfg in servers.items()
            if getattr(server_cfg, "enabled", True)
        ]
        if not enabled_items:
            return

        tasks = [
            self._connect_and_load_tools(name, server_cfg) for name, server_cfg in enabled_items
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        new_servers: Dict[str, _ServerRuntime] = {}
        new_tools: List[Any] = []
        new_sessions: Dict[str, Any] = {}

        for item in results:
            if isinstance(item, Exception) or not item:
                continue
            runtime, tools = item
            new_servers[runtime.name] = runtime
            new_sessions[runtime.name] = runtime.session
            new_tools.extend(tools)

        with self._state_lock:
            self._servers = new_servers
            self.sessions = new_sessions
            self.tools = new_tools

        if new_tools:
            logger.info("MCP 工具加载完成: servers=%d, tools=%d", len(new_servers), len(new_tools))

    async def _connect_and_load_tools(
        self, name: str, server_cfg: Any
    ) -> Optional[Tuple[_ServerRuntime, List[Any]]]:
        transport = str(getattr(server_cfg, "transport", "stdio") or "stdio").lower()
        if transport != "stdio":
            logger.warning("暂不支持 MCP transport=%s (server=%s)，已跳过", transport, name)
            return None

        command = str(getattr(server_cfg, "command", "") or "").strip()
        args = list(getattr(server_cfg, "args", []) or [])
        env = dict(getattr(server_cfg, "env", {}) or {})
        try:
            max_concurrency = int(getattr(server_cfg, "max_concurrency", 1) or 1)
        except Exception:
            max_concurrency = 1
        max_concurrency = max(1, min(32, max_concurrency))

        if not command:
            logger.warning("MCP server=%s 未配置 command，已跳过", name)
            return None

        server_name = _sanitize_name(name)
        try:
            params = StdioServerParameters(
                command=command,
                args=args,
                env=env,
            )  # type: ignore[misc]
        except Exception as exc:
            logger.warning("创建 MCP StdioServerParameters 失败 (server=%s): %s", name, exc)
            return None

        client_cm = stdio_client(params)  # type: ignore[misc]
        read = write = None
        session_cm = None
        session = None
        try:
            read, write = await client_cm.__aenter__()
            session_cm = ClientSession(read, write)  # type: ignore[misc]
            session = await session_cm.__aenter__()

            await asyncio.wait_for(session.initialize(), timeout=self._connect_timeout_s)
            tool_list = await asyncio.wait_for(
                session.list_tools(), timeout=self._connect_timeout_s
            )

            tools = getattr(tool_list, "tools", None) or []
            adapted = self._adapt_tools(server_name, tools)
            runtime = _ServerRuntime(
                name=server_name,
                session=session,
                session_cm=session_cm,
                client_cm=client_cm,
                call_lock=asyncio.Semaphore(max_concurrency),
            )
            return runtime, adapted
        except Exception as exc:
            logger.warning("连接 MCP server=%s 失败: %s", name, exc)
            try:
                if session_cm is not None:
                    await session_cm.__aexit__(type(exc), exc, getattr(exc, "__traceback__", None))
            except Exception:
                pass
            try:
                await client_cm.__aexit__(type(exc), exc, getattr(exc, "__traceback__", None))
            except Exception:
                pass
            return None

    def _adapt_tools(self, server_name: str, tools: Sequence[Any]) -> List[Any]:
        if not HAS_STRUCTURED_TOOL or StructuredTool is None:
            logger.warning(
                "StructuredTool 不可用，无法注册 MCP 工具: %s", _STRUCTURED_TOOL_IMPORT_ERROR
            )
            return []

        def make_invoke(raw_tool_name: str):
            def _invoke(**kwargs: Any) -> str:
                return self.call_tool_sync(server_name, raw_tool_name, kwargs)

            return _invoke

        adapted: List[Any] = []
        for tool_meta in tools or []:
            try:
                tool_name = str(getattr(tool_meta, "name", "") or "")
                description = str(getattr(tool_meta, "description", "") or "")
                schema = getattr(tool_meta, "inputSchema", None) or getattr(
                    tool_meta, "input_schema", None
                )
            except Exception:
                continue

            if not tool_name:
                continue

            public_name = f"mcp_{server_name}_{_sanitize_name(tool_name)}"
            model_name = f"MCP_{server_name}_{_sanitize_name(tool_name)}_Args"
            args_schema = _json_schema_to_pydantic_model(model_name=model_name, schema=schema)

            invoke_fn = make_invoke(tool_name)

            try:
                mcp_tool = StructuredTool.from_function(
                    invoke_fn,
                    name=public_name,
                    description=f"[MCP:{server_name}] {description}".strip(),
                    args_schema=args_schema,
                )
            except TypeError:
                # 兼容旧版 StructuredTool.from_function 签名
                mcp_tool = StructuredTool.from_function(  # type: ignore[call-arg]
                    invoke_fn,
                    name=public_name,
                    description=f"[MCP:{server_name}] {description}".strip(),
                )

            adapted.append(mcp_tool)

        return adapted

    async def call_tool_async(self, server: str, tool_name: str, arguments: Dict[str, Any]) -> str:
        with self._state_lock:
            runtime = self._servers.get(server)
        if runtime is None:
            return f"MCP server '{server}' 未初始化或不存在"

        async with runtime.call_lock:
            result = await runtime.session.call_tool(tool_name, arguments=arguments)
        return _extract_tool_result_text(result)

    def call_tool_sync(self, server: str, tool_name: str, arguments: Dict[str, Any]) -> str:
        self.initialize()
        timeout_s = self._connect_timeout_s
        tool_timeout_s = get_current_tool_timeout_s()
        if tool_timeout_s is not None:
            try:
                value = float(tool_timeout_s)
                if value > 0:
                    timeout_s = max(0.1, value - 0.05)
            except Exception:
                pass
        try:
            return self._runner.run(
                self.call_tool_async(server, tool_name, arguments),
                timeout=timeout_s,
            )
        except Exception as exc:
            return f"MCP 工具调用失败: {exc}"

    def get_tools(self) -> List[Any]:
        self.initialize()
        with self._state_lock:
            return list(self.tools)

    def close(self, timeout_s: float = 2.0) -> None:
        """关闭所有 MCP 会话与后台 loop（幂等）。"""
        with self._state_lock:
            servers = dict(self._servers)
            self._servers = {}
            self.sessions = {}
            self.tools = []

        if not servers:
            self._runner.close(timeout=max(0.1, float(timeout_s)))
            return

        async def _aclose_all() -> None:
            for runtime in servers.values():
                try:
                    await runtime.session_cm.__aexit__(None, None, None)
                except Exception:
                    pass
                try:
                    await runtime.client_cm.__aexit__(None, None, None)
                except Exception:
                    pass

        try:
            self._runner.run(_aclose_all(), timeout=max(0.1, float(timeout_s)))
        except Exception:
            pass
        finally:
            self._runner.close(timeout=max(0.1, float(timeout_s)))


mcp_manager = MCPManager()
