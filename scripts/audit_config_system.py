#!/usr/bin/env python3
"""
Audit the configuration system:

1) Example YAML coverage: ensure curated "config surface" keys exist.
2) Settings schema vs code usage: show which Settings fields are referenced and which are likely unused.

This script prints key *names only* (never prints secret values).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import ast
import sys
from typing import get_args, get_origin

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True, slots=True)
class ExampleAudit:
    name: str
    path: Path
    missing_paths: list[str]
    extra_top_level_keys: list[str]


def _load_yaml_mapping(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(path)
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"YAML must be a mapping/object: {path}")
    return raw


def _iter_py_files() -> Iterable[Path]:
    for base in (PROJECT_ROOT / "src", PROJECT_ROOT / "tests"):
        if not base.exists():
            continue
        yield from base.rglob("*.py")


def _extract_settings_chain_from_expr(
    node: ast.AST, *, env: Mapping[str, list[str]] | None = None
) -> list[str] | None:
    """
    Extract attribute/key chain from expressions rooted at `settings`.

    Supports both:
    - settings.agent.enable_streaming
    - getattr(settings.agent, "tool_timeout_s", 30.0)
    - getattr(getattr(settings, "asr", None), "endpoint_silence_ms", 0)
    """
    if isinstance(node, ast.Name) and node.id == "settings":
        return []
    if env is not None and isinstance(node, ast.Name):
        mapped = env.get(node.id)
        if mapped is not None:
            return list(mapped)

    if isinstance(node, ast.Attribute):
        base = _extract_settings_chain_from_expr(node.value, env=env)
        if base is None:
            return None
        return [*base, node.attr]

    if isinstance(node, ast.Call):
        # getattr(settings.<...>, "field", default)
        if isinstance(node.func, ast.Name) and node.func.id == "getattr" and len(node.args) >= 2:
            key_node = node.args[1]
            if isinstance(key_node, ast.Constant) and isinstance(key_node.value, str):
                base = _extract_settings_chain_from_expr(node.args[0], env=env)
                if base is None:
                    return None
                return [*base, str(key_node.value)]
        return None

    return None


def collect_used_settings_paths() -> set[str]:
    used: set[str] = set()
    settings_roots = {"llm", "vision_llm", "agent", "tts", "asr", "mcp"}

    class Visitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self._env_stack: list[dict[str, list[str]]] = [{}]
            self._wrapper_stack: list[dict[str, str]] = [{}]

        def _env_get(self, name: str) -> list[str] | None:
            for env in reversed(self._env_stack):
                if name in env:
                    return env[name]
            return None

        def _env_set(self, name: str, chain: list[str]) -> None:
            self._env_stack[-1][name] = chain

        def _wrapper_get(self, name: str) -> str | None:
            for env in reversed(self._wrapper_stack):
                if name in env:
                    return env[name]
            return None

        def _wrapper_set(self, name: str, base_var: str) -> None:
            self._wrapper_stack[-1][name] = base_var

        def _extract(self, expr: ast.AST) -> list[str] | None:
            merged_env: dict[str, list[str]] = {}
            for env in self._env_stack:
                merged_env.update(env)
            return _extract_settings_chain_from_expr(expr, env=merged_env)

        def _detect_getattr_wrapper_base(
            self, node: ast.FunctionDef | ast.AsyncFunctionDef
        ) -> str | None:
            """
            Detect simple wrapper functions like:
                def _cfg_int(name, default):
                    return int(getattr(asr_cfg, name, default))
            and return the base variable name (e.g. "asr_cfg").
            """
            if not node.args.args:
                return None
            name_arg = node.args.args[0].arg
            if not name_arg:
                return None
            for inner in ast.walk(node):
                if not isinstance(inner, ast.Call):
                    continue
                if not (isinstance(inner.func, ast.Name) and inner.func.id == "getattr"):
                    continue
                if len(inner.args) < 2:
                    continue
                base, key = inner.args[0], inner.args[1]
                if isinstance(base, ast.Name) and isinstance(key, ast.Name) and key.id == name_arg:
                    return base.id
            return None

        def visit_Assign(self, node: ast.Assign) -> None:
            chain = self._extract(node.value)
            if chain and chain[0] in settings_roots:
                # Track intermediate settings objects, e.g. `asr_cfg = getattr(settings, "asr", None)`.
                for target in node.targets:
                    if isinstance(target, ast.Name) and len(chain) >= 1:
                        self._env_set(target.id, chain)
            self.generic_visit(node)

        def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
            if node.value is not None:
                chain = self._extract(node.value)
                if chain and chain[0] in settings_roots and isinstance(node.target, ast.Name):
                    self._env_set(node.target.id, chain)
            self.generic_visit(node)

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            base_var = self._detect_getattr_wrapper_base(node)
            if base_var is not None:
                self._wrapper_set(node.name, base_var)

            self._env_stack.append({})
            self._wrapper_stack.append({})
            try:
                self.generic_visit(node)
            finally:
                self._env_stack.pop()
                self._wrapper_stack.pop()

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            base_var = self._detect_getattr_wrapper_base(node)
            if base_var is not None:
                self._wrapper_set(node.name, base_var)

            self._env_stack.append({})
            self._wrapper_stack.append({})
            try:
                self.generic_visit(node)
            finally:
                self._env_stack.pop()
                self._wrapper_stack.pop()

        def visit_Attribute(self, node: ast.Attribute) -> None:
            chain = self._extract(node)
            if chain:
                used.add(".".join(chain))
            self.generic_visit(node)

        def visit_Call(self, node: ast.Call) -> None:
            # Wrapper calls like: _cfg_int("endpoint_silence_ms", 900)
            if isinstance(node.func, ast.Name) and node.args:
                wrapper_base = self._wrapper_get(node.func.id)
                if wrapper_base is not None:
                    key_node = node.args[0]
                    if isinstance(key_node, ast.Constant) and isinstance(key_node.value, str):
                        base_chain = self._env_get(wrapper_base)
                        if base_chain:
                            used.add(".".join([*base_chain, str(key_node.value)]))

            chain = self._extract(node)
            if chain:
                used.add(".".join(chain))
            self.generic_visit(node)

    for py_file in _iter_py_files():
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        except Exception:
            continue

        Visitor().visit(tree)
    return used


def _is_pydantic_model_type(tp: Any) -> bool:
    try:
        from pydantic import BaseModel
    except Exception:  # pragma: no cover - environment dependency variance
        return False

    return isinstance(tp, type) and issubclass(tp, BaseModel)


def _unwrap_pydantic_model_type(tp: Any) -> Any | None:
    """
    Return a BaseModel subclass if the annotation contains one (e.g. Optional[Model]).
    Only handles direct / Optional / Union cases (treat list/dict of models as leaf).
    """
    if tp is None:
        return None

    if _is_pydantic_model_type(tp):
        return tp

    origin = get_origin(tp)
    if origin is None:
        return None

    # Containers of models are treated as leafs for this audit (usage is hard to statically track).
    if origin in {list, tuple, set, dict}:
        return None

    # Union / Optional / X | None
    args = get_args(tp) or ()
    for arg in args:
        if _is_pydantic_model_type(arg):
            return arg
    return None


def _collect_model_paths(
    prefix: str, model: Any, out: set[str], *, _stack: set[tuple[Any, str]]
) -> None:
    try:
        fields = getattr(model, "model_fields", {}) or {}
    except Exception:
        return

    for field_name, field_info in fields.items():
        if not isinstance(field_name, str):
            continue
        path = f"{prefix}.{field_name}" if prefix else field_name
        out.add(path)

        submodel = _unwrap_pydantic_model_type(getattr(field_info, "annotation", None))
        if submodel is None:
            continue

        key = (submodel, path)
        if key in _stack:
            continue
        _stack.add(key)
        _collect_model_paths(path, submodel, out, _stack=_stack)
        _stack.remove(key)


def collect_defined_settings_fields() -> set[str]:
    # Import locally to avoid leaking config values; we only use schema metadata.
    from src.config.settings import Settings

    defined: set[str] = set()

    section_map = {
        "llm": "LLM",
        "vision_llm": "VISION_LLM",
        "agent": "Agent",
        "tts": "TTS",
        "asr": "ASR",
        "mcp": "MCP",
    }

    fields = getattr(Settings, "model_fields", {}) or {}
    for field_name, field_info in fields.items():
        if not isinstance(field_name, str):
            continue

        # Expand nested config sections.
        if field_name in section_map:
            model = _unwrap_pydantic_model_type(getattr(field_info, "annotation", None))
            if model is not None:
                _collect_model_paths(section_map[field_name], model, defined, _stack=set())
            continue

        # Flat keys at the root of YAML.
        defined.add(field_name)

        model = _unwrap_pydantic_model_type(getattr(field_info, "annotation", None))
        if model is not None:
            _collect_model_paths(field_name, model, defined, _stack=set())

    return defined


def _map_settings_path_to_yaml_path(path: str) -> str:
    # settings.llm.api -> LLM.api
    # settings.agent.enable_streaming -> Agent.enable_streaming
    mapping = {
        "llm": "LLM",
        "vision_llm": "VISION_LLM",
        "agent": "Agent",
        "tts": "TTS",
        "asr": "ASR",
        "mcp": "MCP",
    }
    parts = (path or "").split(".")
    if not parts:
        return path
    if parts[0] == "settings":
        parts = parts[1:]
    if not parts:
        return path
    section = mapping.get(parts[0])
    if section and len(parts) >= 2:
        return ".".join([section, *parts[1:]])
    return ".".join(parts)


def _audit_example(name: str, path: Path, required_paths: Iterable[str]) -> ExampleAudit:
    data = _load_yaml_mapping(path)
    missing: list[str] = []
    for key_path in required_paths:
        from src.config.config_surface import has_config_path

        if not has_config_path(data, key_path):
            missing.append(key_path)

    extra_top_level = sorted(
        [
            k
            for k in data.keys()
            if isinstance(k, str) and k not in {"LLM", "VISION_LLM", "Agent", "TTS", "ASR", "MCP"}
        ]
    )
    return ExampleAudit(
        name=name, path=path, missing_paths=sorted(missing), extra_top_level_keys=extra_top_level
    )


def _iter_yaml_paths(mapping: Mapping[str, Any], *, prefix: str = "") -> set[str]:
    out: set[str] = set()
    for k, v in (mapping or {}).items():
        if not isinstance(k, str):
            continue
        path = f"{prefix}.{k}" if prefix else k
        out.add(path)
        if isinstance(v, Mapping):
            out |= _iter_yaml_paths(v, prefix=path)
    return out


_CANONICAL_SEGMENT = {
    "llm": "LLM",
    "vision_llm": "VISION_LLM",
    "agent": "Agent",
    "tts": "TTS",
    "asr": "ASR",
    "mcp": "MCP",
    "tavily": "TAVILY",
    "amap": "AMAP",
    "gui": "GUI",
}


def _canonicalize_path_parts(parts: list[str]) -> list[str]:
    return [_CANONICAL_SEGMENT.get(p, p) for p in parts]


def _call_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


_CONFIG_LOADER_CALLS = {
    "load_merged_config",
    "load_config",
    "_get_config",
    "_load_local_config",
    "read_yaml_file",
}
_CONFIG_LOADER_RETURNS_TUPLE = {"load_merged_config"}


class _ConfigUseVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.used_paths: set[str] = set()
        self._env_stack: list[dict[str, list[str]]] = [{}]

    def _env_get(self, name: str) -> list[str] | None:
        for env in reversed(self._env_stack):
            if name in env:
                return env[name]
        return None

    def _env_set(self, name: str, path: list[str]) -> None:
        self._env_stack[-1][name] = path

    def _is_config_loader_call(self, call: ast.Call) -> bool:
        name = _call_name(call.func)
        return bool(name and name in _CONFIG_LOADER_CALLS)

    def _extract_config_path_from_expr(self, expr: ast.AST) -> list[str] | None:
        # Root config dict variable.
        if isinstance(expr, ast.Name):
            return self._env_get(expr.id)

        # Root returned directly from a loader call.
        if isinstance(expr, ast.Call) and self._is_config_loader_call(expr):
            return []

        # Nested mapping access: base.get("key")
        if (
            isinstance(expr, ast.Call)
            and isinstance(expr.func, ast.Attribute)
            and expr.func.attr == "get"
        ):
            if not expr.args:
                return None
            key_node = expr.args[0]
            if not isinstance(key_node, ast.Constant) or not isinstance(key_node.value, str):
                return None
            base_path = self._extract_config_path_from_expr(expr.func.value)
            if base_path is None:
                return None
            return [*base_path, str(key_node.value)]

        # Nested mapping access: base["key"]
        if isinstance(expr, ast.Subscript):
            key_node = expr.slice
            if isinstance(key_node, ast.Constant) and isinstance(key_node.value, str):
                base_path = self._extract_config_path_from_expr(expr.value)
                if base_path is None:
                    return None
                return [*base_path, str(key_node.value)]
            return None

        # Ternary: pick the configish branch.
        if isinstance(expr, ast.IfExp):
            body_path = self._extract_config_path_from_expr(expr.body)
            if body_path is not None:
                return body_path
            return self._extract_config_path_from_expr(expr.orelse)

        # `a or b or {}` patterns.
        if isinstance(expr, ast.BoolOp) and isinstance(expr.op, ast.Or):
            for value in expr.values:
                path = self._extract_config_path_from_expr(value)
                if path is not None:
                    return path
            return None

        return None

    def visit_Assign(self, node: ast.Assign) -> None:
        # Special-case tuple unpacking: merged, *_ = load_merged_config()
        if (
            isinstance(node.value, ast.Call)
            and _call_name(node.value.func) in _CONFIG_LOADER_RETURNS_TUPLE
            and node.targets
        ):
            for target in node.targets:
                if isinstance(target, (ast.Tuple, ast.List)) and target.elts:
                    first = target.elts[0]
                    if isinstance(first, ast.Name):
                        self._env_set(first.id, [])

        # Handle simple Name targets.
        value_path = self._extract_config_path_from_expr(node.value)
        if value_path is not None:
            for target in node.targets:
                if isinstance(target, ast.Name):
                    self._env_set(target.id, value_path)

        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if node.value is not None:
            value_path = self._extract_config_path_from_expr(node.value)
            if value_path is not None and isinstance(node.target, ast.Name):
                self._env_set(node.target.id, value_path)
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._env_stack.append({})
        try:
            self.generic_visit(node)
        finally:
            self._env_stack.pop()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._env_stack.append({})
        try:
            self.generic_visit(node)
        finally:
            self._env_stack.pop()

    def visit_Call(self, node: ast.Call) -> None:
        # Record config dict usage via `.get("...")`.
        if isinstance(node.func, ast.Attribute) and node.func.attr == "get" and node.args:
            path = self._extract_config_path_from_expr(node)
            if path:
                canon = ".".join(_canonicalize_path_parts(path))
                self.used_paths.add(canon)

        self.generic_visit(node)

    def visit_Subscript(self, node: ast.Subscript) -> None:
        path = self._extract_config_path_from_expr(node)
        if path:
            canon = ".".join(_canonicalize_path_parts(path))
            self.used_paths.add(canon)
        self.generic_visit(node)


def collect_used_config_paths() -> set[str]:
    """
    Best-effort scan for raw YAML config dict usage, e.g.:
      - config.get("GUI").get("theme")
      - _load_local_config().get("AMAP", {}).get("api_key")
    """
    visitor = _ConfigUseVisitor()
    for py_file in _iter_py_files():
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        except Exception:
            continue
        visitor.visit(tree)
    return visitor.used_paths


def _path_prefixes(path: str) -> set[str]:
    parts = [p for p in (path or "").split(".") if p]
    out: set[str] = set()
    for i in range(1, len(parts) + 1):
        out.add(".".join(parts[:i]))
    return out


def _is_covered_by_used(path: str, used: set[str], used_prefixes: set[str]) -> bool:
    if path in used:
        return True
    if path in used_prefixes:
        return True
    for prefix in _path_prefixes(path):
        if prefix in used:
            return True
    return False


def main() -> int:
    sys.path.insert(0, str(PROJECT_ROOT))

    from src.config.config_surface import DEV_CONFIG_REQUIRED_PATHS, USER_EXAMPLE_REQUIRED_PATHS

    user_example = PROJECT_ROOT / "config.user.yaml.example"
    dev_example = PROJECT_ROOT / "config.dev.yaml"

    audits = [
        _audit_example("user", user_example, USER_EXAMPLE_REQUIRED_PATHS),
        _audit_example("dev", dev_example, DEV_CONFIG_REQUIRED_PATHS),
    ]

    ok = True
    for audit in audits:
        if audit.missing_paths:
            ok = False
            print(f"[FAIL] Missing required paths in {audit.path}:")
            for item in audit.missing_paths:
                print(f"  - {item}")
        else:
            print(f"[OK] {audit.path} covers the required config surface.")

    # Settings schema vs code usage (best-effort static scan)
    used_settings_raw = collect_used_settings_paths()
    used_settings_yaml = sorted({_map_settings_path_to_yaml_path(p) for p in used_settings_raw})
    defined_settings = collect_defined_settings_fields()

    used_settings_defined = sorted([p for p in used_settings_yaml if p in defined_settings])
    surface_paths = set(USER_EXAMPLE_REQUIRED_PATHS) | set(DEV_CONFIG_REQUIRED_PATHS)
    unused_settings_candidates = sorted(
        [
            p
            for p in defined_settings
            if p not in set(used_settings_defined) and p not in surface_paths
        ]
    )

    # Raw config dict usage (best-effort)
    used_config = sorted(collect_used_config_paths())

    print()
    print(
        f"[INFO] settings usage (best-effort): {len(used_settings_defined)} defined paths referenced in code/tests"
    )
    print("  sample:", ", ".join(used_settings_defined[:20]))
    print(
        f"[INFO] settings schema candidates not referenced (review before removing): {len(unused_settings_candidates)}"
    )
    print("  sample:", ", ".join(unused_settings_candidates[:20]))

    print()
    print(f"[INFO] raw config dict usage (best-effort): {len(used_config)} key paths referenced")
    print("  sample:", ", ".join(used_config[:20]))

    # Example redundancy hints (safe: key names only)
    user_example_data = _load_yaml_mapping(user_example)
    dev_example_data = _load_yaml_mapping(dev_example)
    example_paths = _iter_yaml_paths(user_example_data) | _iter_yaml_paths(dev_example_data)
    used_all = set(used_settings_defined) | set(used_config)
    used_prefixes = set().union(*(_path_prefixes(p) for p in used_all)) if used_all else set()
    example_unused = sorted(
        [
            p
            for p in example_paths
            if p not in surface_paths and not _is_covered_by_used(p, used_all, used_prefixes)
        ]
    )
    if example_unused:
        print()
        print(
            f"[WARN] example yaml paths not referenced by code (review/remove if stale): {len(example_unused)}"
        )
        print("  sample:", ", ".join(example_unused[:20]))

    # Local config file hints (if present): never prints values
    for local_name in ("config.user.yaml", "config.dev.yaml"):
        local_path = PROJECT_ROOT / local_name
        if not local_path.exists():
            continue
        try:
            local_data = _load_yaml_mapping(local_path)
        except Exception as exc:
            print()
            print(f"[WARN] failed to read local config {local_path}: {exc}")
            continue

        local_paths = _iter_yaml_paths(local_data)
        unused_local = sorted(
            [
                p
                for p in local_paths
                if p not in surface_paths and not _is_covered_by_used(p, used_all, used_prefixes)
            ]
        )

        if unused_local:
            print()
            print(
                f"[WARN] {local_path} contains paths not referenced by code (review/remove): {len(unused_local)}"
            )
            print("  sample:", ", ".join(unused_local[:20]))

    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
