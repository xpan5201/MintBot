"""
Phase 0-6（去外部编排框架计划）：Golden 基线录制脚本

用途：
- 录制当前 native(OpenAI-compatible) 的流式输出 chunks 与关键性能指标，
  作为后续阶段的对比基线与 Gate 验收资产。

注意：
- 该脚本不会在 CI/pytest 中自动运行；需要你本机配置好 LLM key 后手动执行。
- 默认不会写入长期记忆（避免污染向量库）；如需覆盖记忆链路请加 --save-long-term。
- Phase 4 起 native(OpenAI-compatible) 工具循环已接入主链路；
  Phase 5 可用 `--pipeline` 启用 native pipeline。

示例（Windows）：
  .\\.venv\\Scripts\\python.exe archives\\plans\\2026-01_de_langchain_phase0-7\\scripts\\de_langchain_capture_golden.py --prompt "你好"
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


PLAN_ROOT = Path(__file__).resolve().parent.parent


def _find_repo_root(start: Path) -> Path:
    for candidate in [start, *start.parents]:
        if (candidate / "pyproject.toml").is_file() and (candidate / "src").is_dir():
            return candidate
    return start


REPO_ROOT = _find_repo_root(PLAN_ROOT)


def _git_revision() -> str | None:
    try:
        out = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT)
        return out.decode("utf-8", errors="replace").strip()
    except Exception:
        return None


def _build_system_prompt() -> str:
    from src.character.config_loader import CharacterConfigLoader  # noqa: E402
    from src.character.personality import default_character  # noqa: E402

    config_prompt = CharacterConfigLoader.generate_system_prompt()
    base_system_prompt = config_prompt if config_prompt else default_character.get_system_prompt()
    enhanced_instruction = """

## 情感与记忆系统

你拥有情感系统和记忆系统，能够：
- **情感感知**：识别主人的情绪状态并产生共鸣
- **情感表达**：自然融入当前情感，让对话生动真实
- **记忆关联**：记住与主人的互动，建立深厚联系
- **个性化服务**：根据主人的喜好和习惯调整行为

## 多模态交互能力

当主人发送图片、语音或其他媒体时：
- **图片**：仔细观察并描述图片内容，结合主人的问题给出回应
- **语音**：理解语音内容，用温柔的语气回复
- **文件**：根据文件类型提供相应帮助

## 回复质量标准

✓ **准确性**：基于事实和已知信息回复，不编造内容
✓ **相关性**：紧扣主人的问题和需求
✓ **一致性**：保持角色设定和语言风格的连贯
✓ **自然性**：避免机械化表达，展现真实情感
✓ **简洁性**：清晰表达，避免冗长啰嗦

  ## 特殊情况处理

  - **不确定时**：诚实告知"我不太确定..."而非编造答案
 - **超出能力**：礼貌说明"这个可能超出我的能力范围..."
 - **工具失败**：温柔告知并提供替代方案
 - **敏感话题**：保持角色边界，委婉引导话题

## 工具使用与表达规范

- 工具返回只是“素材”，不要原样粘贴；要用角色语气把信息说得自然、贴心。
- 优先给**结论 + 3~5 个要点**；需要更多细节时，再向主人追问或分步展开。
- 尽量避免输出原始 JSON/超长列表/日志；必要时先总结，再补充关键链接或条目。
- 工具返回为空/失败/超时：说明原因，并给出下一步建议（换关键词、补充城市/出发地等）。

## Live2D 状态事件（可选，面向 GUI 角色表现）

- 你可以在回复中附加**隐藏 JSON 指令**来触发表情/动作：
  `[[live2d:{\\\"event\\\":\\\"EVENT\\\",\\\"intensity\\\":0.0-1.0,\\\"hold_s\\\":0.2-30}]]`
  - UI 会自动剥离该指令，不会显示给主人，也不会保存到聊天记录。
  - 仅用于 Live2D 控制，不要解释，不要放进正文；除这条隐藏指令外不要输出原始 JSON。
  - `event` 可以是**表情语义标签**：`angry/shy/dizzy/love/sad/surprise`，
    也可以是中文关键词（如“猫尾/雾气/鱼干/脸黑”），或直接写 `.exp3.json` 文件名。
  - `event` 也可以是**动作标签**（触发点头/摇头等）：`nod/shake`（同义：`yes/no/affirm/deny/肯定/否定/点头/摇头`）。
  - `intensity` 为 0~1（可省略），`hold_s` 为停留秒数（可省略）。
- 使用原则：**少量、自然、服务于情绪表达**，不要在同一条回复里反复切换；不要向主人解释这些指令。
"""
    return base_system_prompt + enhanced_instruction


def _collect_backend_text_chunks(
    backend: Any,
    request: Any,
    *,
    min_chars: int,
    first_chunk_at: float | None,
    chunks: list[str],
) -> float | None:
    """
    Collect text output from a ChatBackend-like stream.

    Returns updated `first_chunk_at` timestamp (perf_counter) if first chunk is emitted.
    """

    buffer = ""
    stream = getattr(backend, "stream", None)
    if not callable(stream):
        raise TypeError("backend.stream is not callable")

    try:
        for event in stream(request):
            event_type = str(getattr(event, "type", "") or "")
            if event_type != "text.delta":
                continue
            delta = str(getattr(event, "delta", "") or "")
            if not delta:
                continue
            buffer += delta
            if len(buffer) < min_chars:
                continue
            if first_chunk_at is None:
                first_chunk_at = time.perf_counter()
            chunks.append(buffer)
            buffer = ""
    finally:
        close = getattr(backend, "close", None)
        if callable(close):
            try:
                close()
            except Exception:
                pass

    if buffer:
        if first_chunk_at is None:
            first_chunk_at = time.perf_counter()
        chunks.append(buffer)
    return first_chunk_at


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="de_langchain_capture_golden",
        description="Capture streaming output as golden baseline (agent/backend).",
    )
    parser.add_argument(
        "--runner",
        choices=["agent", "backend"],
        default="",
        help=(
            "Runner to capture: agent (full MintChatAgent) or backend (ChatBackend only). "
            "If omitted: agent."
        ),
    )
    parser.add_argument(
        "--out",
        default="",
        help=(
            "Output JSON path. If omitted, defaults to "
            "data/golden/<name>.json (based on backend/runner)."
        ),
    )
    parser.add_argument(
        "--user-id",
        type=int,
        default=1,
        help="User id for memory namespace (default: 1)",
    )
    parser.add_argument(
        "--prompt",
        action="append",
        dest="prompts",
        default=[],
        help="Prompt to run (repeatable). If omitted, use a built-in prompt.",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=None,
        help=(
            "Override temperature. If omitted: backend runner uses 0.0 for determinism; "
            "agent runner uses current settings."
        ),
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=None,
        help="Override max_tokens. If omitted, uses current settings.",
    )
    parser.add_argument(
        "--save-long-term",
        action="store_true",
        help="Enable saving to long-term memory during the run (default: false).",
    )
    parser.add_argument(
        "--tools",
        action="store_true",
        help=(
            "Enable tool calling loop (Phase 4) for backend runner. "
            "Warning: tools may have side-effects (files/notes/network)."
        ),
    )
    parser.add_argument(
        "--pipeline",
        action="store_true",
        help=(
            "Phase 5: Enable native pipeline stages for this run (native backend only). "
            "For --runner backend, the pipeline is applied only in --tools tool-loop mode."
        ),
    )
    args = parser.parse_args(argv)

    os.chdir(REPO_ROOT)
    sys.path.insert(0, str(REPO_ROOT))

    from src.agent.core import MintChatAgent  # noqa: E402
    from src.config.settings import settings  # noqa: E402

    try:
        settings.get_llm_api_key()
    except Exception as exc:
        print(f"[错误] LLM API Key 未配置或不可用: {exc}")
        print("请先配置 config.user.yaml（或 .env）中的 LLM.key。")
        return 2

    prompts: list[str] = list(args.prompts) if args.prompts else []

    runner = str(args.runner or "").strip()
    if not runner:
        runner = "agent"
    if runner not in ("agent", "backend"):
        print(f"[错误] 无效 runner: {runner!r}")
        return 2

    temperature = args.temperature
    if temperature is None and runner == "backend":
        temperature = 0.0
    max_tokens = (
        int(args.max_tokens) if args.max_tokens is not None else int(settings.model_max_tokens)
    )

    use_tools_requested = bool(args.tools) and runner == "backend"
    if bool(args.pipeline) and runner == "backend" and not use_tools_requested:
        print("[WARN] --pipeline 在 --runner backend 且未启用 --tools 时基本无效（无 tool-loop）。")

    if not prompts:
        if runner == "backend" and use_tools_requested:
            # Gate#5 Golden 默认用“无副作用”工具触发 tool-loop，避免 compare 时缺少 tool.result 事件。
            prompts = [
                (
                    "请严格按步骤完成：\n"
                    "1) 调用工具 get_current_time 获取当前本地时间。\n"
                    "2) 调用工具 calculator 计算 2 + 3 * 4。\n"
                    "3) 用一句话（角色语气）总结这两个结果。\n"
                    "必须通过工具获得结果，不要自行计算或猜测。"
                )
            ]
        else:
            prompts = ["你好，简单自我介绍一下。"]

    out_path = Path(args.out) if args.out else None
    if out_path is not None and not out_path.is_absolute():
        out_path = PLAN_ROOT / out_path
    if out_path is None:
        if runner == "agent":
            out_name = (
                "agent_pipeline_stream_golden.json"
                if bool(args.pipeline)
                else "agent_stream_golden.json"
            )
        else:
            if use_tools_requested:
                out_name = (
                    "backend_tool_loop_pipeline_golden.json"
                    if bool(args.pipeline)
                    else "backend_tool_loop_golden.json"
                )
            else:
                out_name = (
                    "backend_stream_pipeline_golden.json"
                    if bool(args.pipeline)
                    else "backend_stream_golden.json"
                )
        out_path = PLAN_ROOT / "data" / "golden" / out_name

    # Best-effort force the configured pipeline setting for this run.
    original_native_pipeline = getattr(
        getattr(settings, "agent", None), "native_pipeline_enabled", None
    )
    try:
        if hasattr(settings, "agent") and hasattr(settings.agent, "native_pipeline_enabled"):
            setattr(settings.agent, "native_pipeline_enabled", bool(args.pipeline))
    except Exception:
        pass

    agent: MintChatAgent | None = None
    try:
        if runner == "agent":
            agent = MintChatAgent(user_id=args.user_id)

        records: list[dict[str, Any]] = []
        for prompt in prompts:
            start = time.perf_counter()
            first_chunk_at: float | None = None
            chunks: list[str] = []
            events: list[dict[str, Any]] | None = None
            pipeline_stages: list[str] | None = None
            text_delta_count: int = 0
            text_delta_chars: int = 0
            error: str | None = None

            try:
                if runner == "agent":
                    assert agent is not None
                    for chunk in agent.chat_stream(prompt, save_to_long_term=args.save_long_term):
                        if first_chunk_at is None:
                            first_chunk_at = time.perf_counter()
                        chunks.append(chunk)
                else:
                    from src.llm_native.backend import BackendConfig, ChatRequest  # noqa: E402
                    from src.llm_native.messages import Message  # noqa: E402

                    system_prompt = _build_system_prompt()

                    min_chars = max(1, int(getattr(settings.agent, "stream_min_chunk_chars", 8)))
                    timeout_s = float(getattr(settings.agent, "llm_total_timeout_s", 120.0))
                    from src.llm_native.openai_backend import OpenAICompatibleBackend

                    backend = OpenAICompatibleBackend(
                        BackendConfig(
                            base_url=str(getattr(settings.llm, "api", "") or ""),
                            api_key=settings.get_llm_api_key(),
                            model=str(getattr(settings.llm, "model", "") or ""),
                            timeout_s=timeout_s,
                            max_retries=2,
                        )
                    )

                    ran_tool_loop = False
                    if use_tools_requested:
                        from src.agent.tools import ToolRegistry as AgentToolRegistry  # noqa: E402
                        from src.llm_native.agent_runner import (  # noqa: E402
                            AgentRunnerConfig,
                            NativeToolLoopRunner,
                        )
                        from src.llm_native.tool_runner import ToolRunner  # noqa: E402

                        tool_executor = AgentToolRegistry()
                        try:
                            tool_specs = tool_executor.get_tool_specs(strict=True)
                            if not tool_specs:
                                print(
                                    "[WARN] --tools 已启用，但 ToolSpec 为空，将回退为纯后端流式录制"
                                )
                            else:
                                runner_config = AgentRunnerConfig(
                                    max_tool_rounds=6,
                                    tool_timeout_s=float(
                                        getattr(settings.agent, "tool_timeout_s", 30.0)
                                    ),
                                    temperature=float(
                                        temperature
                                        if temperature is not None
                                        else settings.model_temperature
                                    ),
                                    max_tokens=max_tokens,
                                )

                                pipeline = None
                                selector_backend = None
                                if bool(args.pipeline):
                                    from src.llm_native.pipeline import Pipeline  # noqa: E402
                                    from src.llm_native.pipeline_stages import (  # noqa: E402
                                        ContextToolUsesTrimStage,
                                        PermissionScopedToolsStage,
                                        ToolCallLimitStage,
                                        ToolHeuristicPrefilterStage,
                                        ToolLlmSelectorStage,
                                        ToolTraceStage,
                                    )

                                    stages: list[Any] = []
                                    try:
                                        trim_tokens = int(
                                            getattr(
                                                settings.agent, "tool_context_trim_tokens", 1200
                                            )
                                            or 0
                                        )
                                        trim_tokens = max(0, trim_tokens)
                                    except Exception:
                                        trim_tokens = 1200
                                    if trim_tokens > 0:
                                        stages.append(
                                            ContextToolUsesTrimStage(
                                                max_tool_context_tokens=trim_tokens
                                            )
                                        )
                                    stages.append(
                                        PermissionScopedToolsStage(
                                            profile_map=getattr(
                                                settings.agent, "tool_permission_profiles", {}
                                            ),
                                            default_profile=str(
                                                getattr(
                                                    settings.agent,
                                                    "tool_permission_default",
                                                    "default",
                                                )
                                                or "default"
                                            ),
                                        )
                                    )
                                    if bool(getattr(settings.agent, "tool_selector_enabled", True)):
                                        try:
                                            allow_in_fast_mode = bool(
                                                getattr(
                                                    settings.agent,
                                                    "tool_selector_in_fast_mode",
                                                    False,
                                                )
                                            )
                                        except Exception:
                                            allow_in_fast_mode = False
                                        if not (
                                            getattr(settings.agent, "memory_fast_mode", False)
                                            and not allow_in_fast_mode
                                        ):
                                            try:
                                                min_tools = int(
                                                    getattr(
                                                        settings.agent,
                                                        "tool_selector_min_tools",
                                                        16,
                                                    )
                                                    or 0
                                                )
                                                min_tools = max(0, min_tools)
                                            except Exception:
                                                min_tools = 16

                                            tools_count = len(tool_specs) if tool_specs else 0
                                            if not (tools_count and tools_count < min_tools):
                                                try:
                                                    max_tools_raw = int(
                                                        getattr(
                                                            settings.agent,
                                                            "tool_selector_max_tools",
                                                            4,
                                                        )
                                                        or 0
                                                    )
                                                except Exception:
                                                    max_tools_raw = 4
                                                max_tools_for_llm = (
                                                    max(1, max_tools_raw) if max_tools_raw else 4
                                                )

                                                always_include = list(
                                                    getattr(
                                                        settings.agent,
                                                        "tool_selector_always_include",
                                                        [
                                                            "get_current_time",
                                                            "get_weather",
                                                            "web_search",
                                                            "map_search",
                                                        ],
                                                    )
                                                    or []
                                                )
                                                stages.append(
                                                    ToolHeuristicPrefilterStage(
                                                        always_include=always_include,
                                                        max_tools=max_tools_raw or None,
                                                        min_tools=min_tools,
                                                    )
                                                )

                                                try:
                                                    selector_timeout_s = float(
                                                        getattr(
                                                            settings.agent,
                                                            "tool_selector_timeout_s",
                                                            4.0,
                                                        )
                                                    )
                                                except Exception:
                                                    selector_timeout_s = 4.0
                                                try:
                                                    disable_cooldown_s = float(
                                                        getattr(
                                                            settings.agent,
                                                            "tool_selector_disable_cooldown_s",
                                                            300.0,
                                                        )
                                                    )
                                                except Exception:
                                                    disable_cooldown_s = 300.0

                                                selector_model_id = str(
                                                    getattr(
                                                        settings.agent,
                                                        "tool_selector_model",
                                                        "auto",
                                                    )
                                                    or "auto"
                                                )
                                                selector_model = str(
                                                    getattr(settings.llm, "model", "") or ""
                                                ).strip()
                                                if (
                                                    selector_model_id
                                                    and selector_model_id != "auto"
                                                ):
                                                    selector_model = selector_model_id

                                                from src.llm_native.backend import (
                                                    BackendConfig,
                                                )  # noqa: E402
                                                from src.llm_native.openai_backend import (
                                                    OpenAICompatibleBackend,
                                                )

                                                selector_backend = OpenAICompatibleBackend(
                                                    BackendConfig(
                                                        base_url=str(
                                                            getattr(settings.llm, "api", "") or ""
                                                        ),
                                                        api_key=settings.get_llm_api_key(),
                                                        model=selector_model,
                                                        timeout_s=max(
                                                            1.0, float(selector_timeout_s)
                                                        ),
                                                        max_retries=0,
                                                    )
                                                )
                                                stages.append(
                                                    ToolLlmSelectorStage(
                                                        backend=selector_backend,
                                                        max_tools=max_tools_for_llm,
                                                        min_tools=min_tools,
                                                        always_include=always_include,
                                                        disable_cooldown_s=disable_cooldown_s,
                                                    )
                                                )

                                    try:
                                        per_run_limit = int(
                                            getattr(settings.agent, "tool_call_limit_per_run", 0)
                                            or 0
                                        )
                                    except Exception:
                                        per_run_limit = 0
                                    if per_run_limit > 0:
                                        stages.append(
                                            ToolCallLimitStage(per_run_limit=per_run_limit)
                                        )

                                    try:
                                        tool_output_max_chars = int(
                                            getattr(settings.agent, "tool_output_max_chars", 12000)
                                            or 0
                                        )
                                        tool_output_max_chars = max(0, tool_output_max_chars)
                                    except Exception:
                                        tool_output_max_chars = 12000
                                    stages.append(
                                        ToolTraceStage(max_output_chars=tool_output_max_chars)
                                    )

                                    pipeline = Pipeline(stages=stages)
                                    pipeline_stages = [type(s).__name__ for s in stages]

                                tool_loop = NativeToolLoopRunner(
                                    backend=backend,
                                    tools=tool_specs,
                                    tool_runner=ToolRunner(
                                        tool_executor=tool_executor,
                                        default_timeout_s=runner_config.tool_timeout_s,
                                    ),
                                    config=runner_config,
                                    pipeline=pipeline,
                                )

                                events_list: list[dict[str, Any]] = []
                                buffer = ""
                                tool_profile = str(
                                    getattr(settings.agent, "tool_profile", "") or ""
                                ).strip()
                                pipeline_runtime = (
                                    {"tool_profile": tool_profile} if tool_profile else None
                                )
                                for event in tool_loop.stream(
                                    [
                                        Message(role="system", content=system_prompt),
                                        Message(role="user", content=prompt),
                                    ],
                                    pipeline_runtime=pipeline_runtime,
                                ):
                                    et = str(getattr(event, "type", "") or "")
                                    if et == "text.delta":
                                        delta = str(getattr(event, "delta", "") or "")
                                        if not delta:
                                            continue
                                        text_delta_count += 1
                                        text_delta_chars += len(delta)
                                        buffer += delta
                                        if len(buffer) < min_chars:
                                            continue
                                        if first_chunk_at is None:
                                            first_chunk_at = time.perf_counter()
                                        chunks.append(buffer)
                                        buffer = ""
                                        continue
                                    if et == "tool_call.delta":
                                        events_list.append(
                                            {
                                                "type": et,
                                                "t_s": round(time.perf_counter() - start, 6),
                                                "tool_call_id": str(
                                                    getattr(event, "tool_call_id", "") or ""
                                                ),
                                                "name": str(getattr(event, "name", "") or ""),
                                                "arguments_delta_chars": len(
                                                    str(getattr(event, "arguments_delta", "") or "")
                                                ),
                                            }
                                        )
                                        continue
                                    if et == "tool.result":
                                        content = str(getattr(event, "content", "") or "")
                                        events_list.append(
                                            {
                                                "type": et,
                                                "t_s": round(time.perf_counter() - start, 6),
                                                "tool_call_id": str(
                                                    getattr(event, "tool_call_id", "") or ""
                                                ),
                                                "content_chars": len(content),
                                                "content_sha256": hashlib.sha256(
                                                    content.encode("utf-8", errors="replace")
                                                ).hexdigest(),
                                            }
                                        )
                                        continue
                                    if et == "error":
                                        exc_type = str(
                                            getattr(event, "exception_type", "") or "RuntimeError"
                                        )
                                        msg = (
                                            str(getattr(event, "message", "") or "")
                                            or "tool loop error"
                                        )
                                        events_list.append(
                                            {
                                                "type": et,
                                                "t_s": round(time.perf_counter() - start, 6),
                                                "exception_type": exc_type,
                                                "message": msg,
                                            }
                                        )
                                        error = f"{exc_type}: {msg}" if msg else exc_type
                                        break
                                    if et == "done":
                                        events_list.append(
                                            {
                                                "type": et,
                                                "t_s": round(time.perf_counter() - start, 6),
                                                "finish_reason": str(
                                                    getattr(event, "finish_reason", "") or ""
                                                ),
                                            }
                                        )
                                        break

                                if buffer:
                                    if first_chunk_at is None:
                                        first_chunk_at = time.perf_counter()
                                    chunks.append(buffer)

                                events = events_list
                                ran_tool_loop = True
                                if selector_backend is not None:
                                    try:
                                        selector_backend.close()
                                    except Exception:
                                        pass
                        finally:
                            try:
                                tool_executor.close()
                            except Exception:
                                pass

                    if ran_tool_loop:
                        try:
                            close = getattr(backend, "close", None)
                            if callable(close):
                                close()
                        except Exception:
                            pass
                    else:
                        req = ChatRequest(
                            messages=[
                                Message(role="system", content=system_prompt),
                                Message(role="user", content=prompt),
                            ],
                            temperature=float(
                                temperature
                                if temperature is not None
                                else settings.model_temperature
                            ),
                            max_tokens=max_tokens,
                        )
                        first_chunk_at = _collect_backend_text_chunks(
                            backend,
                            req,
                            min_chars=min_chars,
                            first_chunk_at=first_chunk_at,
                            chunks=chunks,
                        )
            except Exception as exc:  # pragma: no cover - 依赖运行环境/网络
                error = f"{type(exc).__name__}: {exc}"

            end = time.perf_counter()
            text = "".join(chunks)

            record: dict[str, Any] = {
                "prompt": prompt,
                "chunks": chunks,
                "chunks_count": len(chunks),
                "chars_count": len(text),
                "first_chunk_latency_s": (
                    None if first_chunk_at is None else round(first_chunk_at - start, 6)
                ),
                "elapsed_s": round(end - start, 6),
                "error": error,
                "text_delta_count": int(text_delta_count),
                "text_delta_chars": int(text_delta_chars),
            }
            if events is not None:
                counts: dict[str, int] = {}
                for e in events:
                    t = str(e.get("type") or "")
                    if not t:
                        continue
                    counts[t] = counts.get(t, 0) + 1
                record["events"] = events
                record["event_counts"] = counts
            if pipeline_stages is not None:
                record["pipeline_stages"] = pipeline_stages

            records.append(record)

        payload = {
            "meta": {
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "python": sys.version,
                "git_revision": _git_revision(),
                "llm_api": getattr(settings.llm, "api", ""),
                "llm_model": getattr(settings.llm, "model", ""),
                "backend": "openai_compatible",
                "pipeline_enabled": bool(args.pipeline),
                "runner": runner,
                "tools": bool(use_tools_requested),
                "temperature": float(temperature) if temperature is not None else None,
                "max_tokens": max_tokens,
                "save_long_term": bool(args.save_long_term),
            },
            "records": records,
        }

        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"[OK] Golden 写入: {out_path}")
        return 0
    finally:
        try:
            if (
                original_native_pipeline is not None
                and hasattr(settings, "agent")
                and hasattr(settings.agent, "native_pipeline_enabled")
            ):
                setattr(settings.agent, "native_pipeline_enabled", original_native_pipeline)
        except Exception:
            pass
        if agent is not None:
            try:
                agent.close()
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
