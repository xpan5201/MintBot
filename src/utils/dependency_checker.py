"""
轻量依赖检查工具

用于在启动阶段检测可选/扩展依赖是否缺失，给出明确提示，避免静默降级。
"""

from __future__ import annotations

import importlib
from typing import Dict, List

from src.utils.logger import get_logger

logger = get_logger(__name__)


def check_optional_dependencies() -> Dict[str, List[str]]:
    """
    检测可选依赖是否缺失，并返回缺失项列表。

    Returns:
        Dict[str, List[str]]: {"missing": [...], "installed": [...]}
    """
    deps = {
        "langchain": "pip install langchain langchain-openai",
        "langchain_openai": "pip install langchain-openai",
        "redis": "pip install redis",
    }

    missing: List[str] = []
    installed: List[str] = []

    for module_name in deps:
        try:
            importlib.import_module(module_name)
            installed.append(module_name)
        except Exception:
            missing.append(module_name)

    if missing:
        install_cmds = {name: deps[name] for name in missing if name in deps}
        logger.error(
            "检测到可选依赖缺失，将影响增强功能：%s。安装建议：%s",
            ", ".join(missing),
            "; ".join(f"{k}: {v}" for k, v in install_cmds.items()),
        )

    return {"missing": missing, "installed": installed}

