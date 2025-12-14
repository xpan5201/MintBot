from __future__ import annotations

from pathlib import Path

from src.agent.tools import PROJECT_ROOT, ToolRegistry, _sanitize_note_title


def test_calculator_disallows_pow_operator() -> None:
    registry = ToolRegistry()
    try:
        result = registry.execute_tool("calculator", expression="9**9")
        assert "**" in result or "不允许" in result or "不安全" in result
    finally:
        registry.close()


def test_file_tools_reject_base_dir_escape() -> None:
    registry = ToolRegistry()
    try:
        result = registry.execute_tool("write_file", filepath="x.txt", content="hi", base_dir="..")
        assert "只能访问项目目录内" in result
    finally:
        registry.close()


def test_file_tools_block_sensitive_files() -> None:
    registry = ToolRegistry()
    try:
        result = registry.execute_tool("read_file", filepath="config.yaml", base_dir=".")
        assert "安全" in result
    finally:
        registry.close()


def test_file_tools_write_read_and_list_under_tmp(tmp_path: Path) -> None:
    registry = ToolRegistry()
    base_dir = str(tmp_path.relative_to(PROJECT_ROOT))

    try:
        write_result = registry.execute_tool("write_file", filepath="a.txt", content="hello", base_dir=base_dir)
        assert "写入" in write_result or "写入到" in write_result

        read_result = registry.execute_tool("read_file", filepath="a.txt", base_dir=base_dir)
        assert "hello" in read_result

        (tmp_path / "config.yaml").write_text("secret", encoding="utf-8")
        list_result = registry.execute_tool("list_files", directory=".", base_dir=base_dir)
        assert "config.yaml" not in list_result
    finally:
        registry.close()


def test_sanitize_note_title_removes_path_chars() -> None:
    assert _sanitize_note_title("a/b:c") == "a_b_c"

