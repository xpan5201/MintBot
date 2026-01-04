from __future__ import annotations

import inspect
import typing
import types
from dataclasses import dataclass
from typing import Any, Callable, get_args, get_origin

from pydantic import BaseModel


def pydantic_to_strict_json_schema(model: type[BaseModel]) -> dict[str, Any]:
    """Build a strict JSON schema from a Pydantic model."""

    schema = model.model_json_schema()
    schema.setdefault("additionalProperties", False)
    return schema


def tool(
    func: Callable[..., Any] | None = None,
    *,
    name: str | None = None,
    description: str | None = None,
) -> Callable[..., Any]:
    """Lightweight tool decorator for native tool registry.

    This decorator does not depend on external agent frameworks. It attaches optional metadata
    (`name`/`description`) to the wrapped callable and returns the callable.
    """

    def decorator(inner: Callable[..., Any]) -> Callable[..., Any]:
        if name:
            setattr(inner, "name", str(name))
        if description:
            setattr(inner, "description", str(description))
        return inner

    if func is None:
        return decorator
    return decorator(func)


def _is_optional_annotation(annotation: Any) -> bool:
    if annotation is inspect.Signature.empty:
        return False
    origin = get_origin(annotation)
    if origin in (types.UnionType, typing.Union):
        return type(None) in get_args(annotation)
    return False


def _annotation_to_json_schema(annotation: Any) -> dict[str, Any]:
    if annotation is inspect.Signature.empty:
        return {"type": "string"}

    origin = get_origin(annotation)
    if origin in (types.UnionType, typing.Union):
        args = [a for a in get_args(annotation) if a is not type(None)]  # noqa: E721
        if len(args) == 1:
            return _annotation_to_json_schema(args[0])
        return {"type": "string"}

    if annotation is str:
        return {"type": "string"}
    if annotation is int:
        return {"type": "integer"}
    if annotation is float:
        return {"type": "number"}
    if annotation is bool:
        return {"type": "boolean"}

    if origin in (list, tuple):
        item = get_args(annotation)[0] if get_args(annotation) else str
        return {"type": "array", "items": _annotation_to_json_schema(item)}

    return {"type": "string"}


def callable_to_toolspec(  # noqa: PLR0912 - intentional small schema mapper
    tool_fn: Any,
    *,
    strict: bool | None = None,
) -> ToolSpec | None:
    """Best-effort conversion of a callable/tool object to ToolSpec.

    Supported inputs:
    - Plain callables (functions) -> JSON schema from signature + annotations
    - Callables with `__tool_parameters__` dict -> use as `parameters` directly
    """

    try:
        name = str(getattr(tool_fn, "name", "") or getattr(tool_fn, "__name__", "") or "").strip()
    except Exception:
        name = ""
    if not name:
        return None

    description_text = ""
    try:
        description_text = str(getattr(tool_fn, "description", "") or "").strip()
    except Exception:
        description_text = ""
    if not description_text:
        try:
            description_text = str(inspect.getdoc(tool_fn) or "").strip()
        except Exception:
            description_text = ""

    parameters = getattr(tool_fn, "__tool_parameters__", None)
    if isinstance(parameters, dict):
        params_schema: dict[str, Any] = dict(parameters)
        params_schema.setdefault("additionalProperties", False)
        return ToolSpec(
            name=name,
            description=description_text,
            parameters=params_schema,
            strict=strict,
        )

    try:
        target = inspect.unwrap(tool_fn)
    except Exception:
        target = tool_fn

    try:
        signature = inspect.signature(target)
    except Exception:
        return None

    properties: dict[str, Any] = {}
    required: list[str] = []
    for param in signature.parameters.values():
        if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
            continue
        if param.name in ("self", "cls"):
            continue

        annotation = param.annotation
        schema = _annotation_to_json_schema(annotation)
        properties[param.name] = schema

        if param.default is inspect.Signature.empty and not _is_optional_annotation(annotation):
            required.append(param.name)

    params_schema = {
        "type": "object",
        "properties": properties,
        "additionalProperties": False,
    }
    if required:
        params_schema["required"] = required

    return ToolSpec(
        name=name,
        description=description_text,
        parameters=params_schema,
        strict=strict,
    )


@dataclass(frozen=True, slots=True)
class ToolSpec:
    """Tool schema definition for OpenAI-compatible tool calling."""

    name: str
    description: str
    parameters: dict[str, Any]
    strict: bool | None = None

    def to_openai(self) -> dict[str, Any]:
        func: dict[str, Any] = {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }
        if self.strict is not None:
            func["strict"] = bool(self.strict)
        return {
            "type": "function",
            "function": func,
        }


class ToolRegistry:
    """Registry for tool specs (schema only)."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, tool: ToolSpec) -> None:
        if not tool.name:
            raise ValueError("tool.name is required")
        if tool.name in self._tools:
            raise ValueError(f"tool already registered: {tool.name}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> ToolSpec | None:
        return self._tools.get(name)

    def tools(self) -> list[ToolSpec]:
        return list(self._tools.values())

    def to_openai(self) -> list[dict[str, Any]]:
        return [tool.to_openai() for tool in self.tools()]
