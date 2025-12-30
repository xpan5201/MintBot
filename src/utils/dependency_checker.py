"""
轻量依赖检查工具

用于在启动阶段检测可选/扩展依赖是否缺失或导入失败，给出明确提示，避免静默降级。
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Dict, List, TypedDict

UV_SYNC_BASE = "uv sync --locked --no-install-project"


class DependencyStatus(TypedDict):
    """
    Optional dependency status.

    Notes:
        - missing: 模块本身未安装（ModuleNotFoundError.name == module_name）。
        - broken: 模块存在，但导入时抛错（包含子依赖缺失/二进制不匹配/元数据损坏等）。
    """

    missing: List[str]
    installed: List[str]
    broken: Dict[str, str]
    hints: Dict[str, str]
    python_executable: str
    in_project_venv: bool


def _format_exc(err: BaseException) -> str:
    text = str(err).strip()
    if text:
        text = text.splitlines()[0]
        return f"{type(err).__name__}: {text}"
    return type(err).__name__


def _is_project_venv(project_root: Path) -> bool:
    try:
        venv_root = (project_root / ".venv").resolve()
        prefix = Path(sys.prefix).resolve()
        return prefix == venv_root
    except Exception:
        return False


def check_optional_dependencies() -> DependencyStatus:
    """
    检测可选/扩展依赖是否缺失或导入失败，并返回状态。

    Returns:
        DependencyStatus
    """
    project_root = Path(__file__).resolve().parents[2]

    deps: Dict[str, str] = {
        "langchain": "langchain",
        "langchain_openai": "langchain-openai",
        "redis": "redis",
    }

    missing: List[str] = []
    installed: List[str] = []
    broken: Dict[str, str] = {}
    hints: Dict[str, str] = {}

    for module_name, package_name in deps.items():
        try:
            importlib.import_module(module_name)
            installed.append(module_name)
        except ModuleNotFoundError as e:
            if e.name == module_name:
                missing.append(module_name)
                hints[module_name] = UV_SYNC_BASE
            else:
                broken[module_name] = _format_exc(e)
                hints[module_name] = f"{UV_SYNC_BASE} --reinstall-package {package_name}"
        except Exception as e:
            broken[module_name] = _format_exc(e)
            hints[module_name] = f"{UV_SYNC_BASE} --reinstall-package {package_name}"

    return {
        "missing": missing,
        "installed": installed,
        "broken": broken,
        "hints": hints,
        "python_executable": sys.executable,
        "in_project_venv": _is_project_venv(project_root),
    }
