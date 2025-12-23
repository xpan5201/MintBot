"""
ASR 初始化模块（FunASR）

- 仅在 settings.asr.enabled 开启时初始化，避免阻塞 GUI 启动。
- 采用懒加载 + 全局单例，供 GUI 语音输入线程复用，减少重复加载开销。
"""

from __future__ import annotations

import io
import importlib
import re
from pathlib import Path
from threading import Lock
from typing import Any, Optional
import warnings
from contextlib import contextmanager, redirect_stderr, redirect_stdout

from src.config.settings import settings
from src.utils.logger import get_logger

logger = get_logger(__name__)

_SENSEVOICE_MS_MODEL_ID = "iic/SenseVoiceSmall"
_SENSEVOICE_HF_MODEL_ID = "FunAudioLLM/SenseVoiceSmall"
_DEFAULT_MODEL_ID = _SENSEVOICE_MS_MODEL_ID
_NANO_MODEL_ID = "FunAudioLLM/Fun-ASR-Nano-2512"
_DEFAULT_QWEN3_LLM_IDS: tuple[str, ...] = (
    "Qwen/Qwen3-0.6B",
    "Qwen/Qwen3-0.6B-Base",
)
_MODEL_ALIASES: dict[str, str] = {
    # Backward-compatible / user-friendly aliases
    "SenseVoice-Small": _DEFAULT_MODEL_ID,
    "sensevoice-small": _DEFAULT_MODEL_ID,
    "SenseVoiceSmall": _DEFAULT_MODEL_ID,
    "sensevoicesmall": _DEFAULT_MODEL_ID,
    # Explicit repo ids (HF / ModelScope)
    _SENSEVOICE_HF_MODEL_ID: _DEFAULT_MODEL_ID,
    _SENSEVOICE_MS_MODEL_ID: _DEFAULT_MODEL_ID,
    "Fun-ASR-Nano-2512": _NANO_MODEL_ID,
    "fun-asr-nano-2512": _NANO_MODEL_ID,
}

_asr_model: Any | None = None
_asr_available = False
_asr_init_attempted = False

_asr_init_lock = Lock()
_asr_model_lock = Lock()


@contextmanager
def _suppress_noisy_audio_dependency_output():
    """Suppress noisy third-party warnings/prints during optional audio dependency imports."""
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message=r".*Couldn't find ffmpeg or avconv.*",
            category=RuntimeWarning,
        )
        buf = io.StringIO()
        with redirect_stdout(buf), redirect_stderr(buf):
            yield


def _normalize_model_id(model: str) -> str:
    value = (model or "").strip()
    if not value:
        return _DEFAULT_MODEL_ID
    if value in _MODEL_ALIASES:
        return _MODEL_ALIASES[value]
    # If user provides a bare model name (no namespace), keep it,
    # but special-case known models to avoid repo_id errors.
    if "/" not in value:
        lowered = value.lower()
        if lowered == "fun-asr-nano-2512":
            return _NANO_MODEL_ID
        if lowered in {"sensevoice-small", "sensevoicesmall"}:
            return _DEFAULT_MODEL_ID
    return value


def _resolve_device(device: str) -> str:
    """Resolve user config device string into a FunASR-compatible device."""
    raw = str(device or "").strip()
    lowered = raw.lower()
    if lowered in {"auto", "cuda_if_available", "gpu"}:
        try:
            import torch  # type: ignore

            return "cuda" if torch.cuda.is_available() else "cpu"
        except Exception:
            return "cpu"

    if lowered == "cuda":
        try:
            import torch  # type: ignore

            if not torch.cuda.is_available():
                logger.warning("ASR 设备指定为 cuda，但未检测到 CUDA；将回退到 cpu")
                return "cpu"
        except Exception:
            logger.warning("ASR 设备指定为 cuda，但 torch 不可用；将回退到 cpu")
            return "cpu"

    return raw or "cpu"


def _looks_like_hf_repo_id(model_id: str) -> bool:
    # Best-effort heuristic: ModelScope repos often use `iic/` while HF examples use `FunAudioLLM/`.
    if not model_id or "/" not in model_id:
        return False
    owner = model_id.split("/", 1)[0].lower()
    return owner not in {"iic", "damo", "modelscope"}


def _infer_hub(model_id: str) -> str | None:
    model_id = (model_id or "").strip()
    if not model_id:
        return None
    if model_id.lower().startswith("iic/"):
        return "ms"
    if _looks_like_hf_repo_id(model_id):
        return "hf"
    return None


def _warmup_asr_model(model: Any, *, sample_rate: int) -> None:
    """Best-effort warmup to reduce first-call latency."""
    try:
        import numpy as np
    except Exception:
        return

    wav = np.zeros(int(max(8000, sample_rate) * 0.35), dtype=np.float32)
    with _asr_model_lock:
        try:
            # Keep kwargs minimal for maximum compatibility.
            model.generate(input=wav, sampling_rate=sample_rate)
        except TypeError:
            try:
                model.generate(input=wav, fs=sample_rate)
            except Exception:
                try:
                    model.generate(input=wav)
                except Exception:
                    return
        except Exception:
            return


def _call_automodel_with_fallback(AutoModel: Any, kwargs: dict[str, Any]) -> Any:
    """Call FunASR AutoModel with best-effort compatibility.

    FunASR's AutoModel signature may differ across versions; this helper retries by removing
    unsupported keyword arguments (e.g. disable_update / trust_remote_code).
    """

    for _ in range(4):
        try:
            return AutoModel(**kwargs)
        except TypeError as exc:
            msg = str(exc)
            m = re.search(r"unexpected keyword argument '([^']+)'", msg)
            if not m:
                raise
            bad_key = m.group(1)
            if bad_key not in kwargs:
                raise
            kwargs.pop(bad_key, None)
            continue
    return AutoModel(**kwargs)


def _camel_to_snake(name: str) -> str:
    # e.g. FunASRNano -> fun_asr_nano
    s1 = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s1).lower()


def _try_register_funasr_model(model_key: str) -> bool:
    """Best-effort import to register a FunASR model class.

    FunASR registers model classes via import side-effects (tables.register).
    Some models (e.g. FunASRNano) ship with FunASR but are not imported by default.
    """
    if not model_key:
        return False

    candidates: list[str] = []
    snake = _camel_to_snake(model_key)
    candidates.append(f"funasr.models.{snake}.model")
    candidates.append(f"funasr.models.{snake}")
    # Common suffixes: Some models register keys like `SenseVoiceSmall` under `sense_voice/`.
    if snake.endswith("_small"):
        base = snake[: -len("_small")]
        if base:
            candidates.append(f"funasr.models.{base}.model")
            candidates.append(f"funasr.models.{base}")
    # Some models might keep the class file at package root.
    candidates.append(f"funasr.models.{model_key}.model")
    candidates.append(f"funasr.models.{model_key}")

    last_error: Exception | None = None
    for module_name in candidates:
        try:
            with _suppress_noisy_audio_dependency_output():
                importlib.import_module(module_name)
            logger.info("已加载 FunASR 模型注册模块: %s", module_name)
            return True
        except Exception as exc:
            last_error = exc
            continue
    if last_error is not None:
        logger.warning("FunASR 模型注册模块加载失败 (%s): %s", model_key, last_error)
    return False


def _dir_has_transformers_weights(model_dir: Path) -> bool:
    if not model_dir.exists() or not model_dir.is_dir():
        return False
    # Transformers considers these canonical weight filenames; shards also end with .safetensors/.bin
    patterns = ("*.safetensors", "pytorch_model*.bin", "model*.safetensors", "model*.bin")
    for pat in patterns:
        if any(model_dir.glob(pat)):
            return True
    return False


def _download_qwen3_llm_weights() -> str | None:
    """Download Qwen3 LLM weights to satisfy FunASRNano dependency.

    Fun-ASR-Nano-2512's config points to a local tokenizer-only folder (`Qwen3-0.6B/`) and the
    upstream repo has removed the weight file in newer revisions ("combine models"). This makes
    `AutoModelForCausalLM.from_pretrained()` fail unless we provide a real weight directory.
    """

    def _try_modelscope() -> str | None:
        try:
            from modelscope import snapshot_download  # type: ignore
        except Exception:
            return None

        for model_id in _DEFAULT_QWEN3_LLM_IDS:
            try:
                logger.info("正在下载/检查 Qwen3 权重 (ModelScope): %s", model_id)
                local_dir = Path(snapshot_download(model_id))
                if _dir_has_transformers_weights(local_dir):
                    logger.info("Qwen3 权重就绪 (ModelScope): %s -> %s", model_id, local_dir)
                    return str(local_dir)
                logger.warning("已下载目录不包含权重文件: %s", local_dir)
            except Exception as exc:
                logger.warning("下载 Qwen3 权重失败 (ModelScope, %s): %s", model_id, exc)
                continue
        return None

    def _try_huggingface() -> str | None:
        try:
            from huggingface_hub import snapshot_download  # type: ignore
        except Exception:
            return None

        allow_patterns = [
            "*.safetensors",
            "pytorch_model*.bin",
            "model*.bin",
            "model*.safetensors",
            "*.index.json",
            "config.json",
            "generation_config.json",
            "tokenizer*",
            "merges.txt",
            "vocab.json",
            "*.txt",
        ]

        for repo_id in _DEFAULT_QWEN3_LLM_IDS:
            try:
                logger.info("正在下载/检查 Qwen3 权重 (HF): %s", repo_id)
                local_dir = Path(
                    snapshot_download(
                        repo_id=repo_id,
                        allow_patterns=allow_patterns,
                        local_dir_use_symlinks=False,
                    )
                )
                if _dir_has_transformers_weights(local_dir):
                    logger.info("Qwen3 权重就绪 (HF): %s -> %s", repo_id, local_dir)
                    return str(local_dir)
                logger.warning("已下载目录不包含权重文件: %s", local_dir)
            except Exception as exc:
                logger.warning("下载 Qwen3 权重失败 (HF, %s): %s", repo_id, exc)
                continue
        return None

    return _try_modelscope() or _try_huggingface()


_MISSING_WEIGHTS_RE = re.compile(r"found in directory\s+(.+?)[\s\.]*$", re.IGNORECASE)


def _extract_missing_weights_dir(exc: BaseException) -> Path | None:
    msg = str(exc)
    if "no file named" not in msg:
        return None
    m = _MISSING_WEIGHTS_RE.search(msg)
    if m:
        path_str = m.group(1).strip().strip("'\"")
    else:
        # Fallback for slightly different message formats.
        marker = "found in directory"
        idx = msg.lower().rfind(marker)
        if idx < 0:
            return None
        path_str = msg[idx + len(marker) :].strip().strip("'\"").rstrip(".")
    try:
        return Path(path_str)
    except Exception:
        return None


def init_asr(*, force: bool = False) -> bool:
    """初始化 FunASR（单例）。

    Returns:
        bool: 初始化成功返回 True；否则 False。
    """
    global _asr_model, _asr_available, _asr_init_attempted

    with _asr_init_lock:
        if force:
            _asr_init_attempted = False
            _asr_available = False
            _asr_model = None

        if _asr_init_attempted:
            return bool(_asr_available and _asr_model is not None)
        _asr_init_attempted = True

    try:
        asr_cfg = getattr(settings, "asr", None)
        if asr_cfg is None or not bool(getattr(asr_cfg, "enabled", False)):
            logger.info("ASR 功能未启用")
            _asr_available = False
            _asr_model = None
            return False
    except Exception:
        logger.info("ASR 配置不可用（将视为未启用）")
        _asr_available = False
        _asr_model = None
        return False

    # 在导入 funasr/pydub 之前尽量准备好 ffmpeg，避免其 import 阶段噪声输出。
    try:
        from .ffmpeg_setup import ensure_ffmpeg_for_audio

        ensure_ffmpeg_for_audio(quiet=True)
    except Exception:
        pass

    try:
        with _suppress_noisy_audio_dependency_output():
            from funasr import AutoModel  # type: ignore
    except Exception as exc:
        logger.warning("未检测到 FunASR，ASR 不可用: %s", exc)
        logger.info("如需启用 ASR，请先安装可选依赖：uv sync --locked --no-install-project --extra asr")
        _asr_available = False
        _asr_model = None
        return False

    raw_model_name = str(getattr(settings.asr, "model", "") or "")
    model_name = _normalize_model_id(raw_model_name)
    device = _resolve_device(getattr(settings.asr, "device", "auto"))

    try:
        if raw_model_name.strip() and raw_model_name.strip() != model_name:
            logger.info("ASR 模型别名已解析: %s -> %s", raw_model_name.strip(), model_name)
        logger.info("初始化 FunASR 模型: %s (device=%s)", model_name, device)
        if device == "cuda":
            try:
                from src.utils.torch_optim import apply_torch_optimizations

                apply_torch_optimizations(verbose=True)
            except Exception:
                pass
        # NOTE: FunASR 会在首次加载时下载/准备模型资源，建议在后台线程预热。
        kwargs: dict[str, Any] = {
            "model": model_name,
            "device": device,
            "disable_update": True,
            "disable_pbar": True,
        }
        # hub: prefer explicit config; otherwise infer from model id.
        try:
            hub = getattr(settings.asr, "hub", None)
            hub = str(hub).strip() if hub is not None else ""
        except Exception:
            hub = ""
        if not hub:
            hub = _infer_hub(model_name) or ""
        # Guard against common misconfiguration: SenseVoiceSmall is typically provided via ModelScope (ms),
        # while some users may set hub=hf by habit.
        try:
            hub_norm = hub.lower()
        except Exception:
            hub_norm = ""
        if model_name.lower().startswith("iic/") and hub_norm in {"hf", "huggingface"}:
            logger.warning("ASR hub=%s 与模型 %s 不匹配；将自动切换为 ms", hub, model_name)
            hub = "ms"
        if hub:
            kwargs["hub"] = hub

        # VAD for long audio: SenseVoice supports long audio with a VAD model (e.g. fsmn-vad).
        try:
            vad_model = getattr(settings.asr, "vad_model", None)
            vad_model = str(vad_model).strip() if vad_model is not None else ""
        except Exception:
            vad_model = ""
        if vad_model and vad_model.lower() != "none":
            kwargs["vad_model"] = vad_model
            try:
                max_ms = int(getattr(settings.asr, "vad_max_single_segment_time_ms", 0) or 0)
            except Exception:
                max_ms = 0
            if max_ms > 0:
                kwargs["vad_kwargs"] = {"max_single_segment_time": max_ms}

        # Remote code: only pass trust_remote_code for HuggingFace hub.
        # For ModelScope SenseVoiceSmall, enabling it can trigger noisy warnings like:
        # "Loading remote code failed: model, No module named 'model'".
        try:
            if hub_norm in {"hf", "huggingface"} and bool(getattr(settings.asr, "trust_remote_code", False)):
                kwargs["trust_remote_code"] = True
        except Exception:
            pass

        max_attempts = 3
        attempt = 0
        while True:
            attempt += 1
            try:
                # Prefer direct call; fall back by stripping unsupported kwargs.
                _asr_model = _call_automodel_with_fallback(AutoModel, dict(kwargs))
                break
            except AssertionError as exc:
                # FunASR model classes are registered via import side-effects.
                # If a model isn't registered, try importing its module then retry once.
                msg = str(exc)
                if " is not registered" in msg and attempt < max_attempts:
                    model_key = msg.split(" is not registered", 1)[0].strip()
                    # If the failing key looks like a hub repo id, prefer switching to the official
                    # SenseVoiceSmall ModelScope id (FunASR expects internal keys like "SenseVoiceSmall").
                    if "/" in model_key:
                        lowered = model_key.lower()
                        if "sensevoice" in lowered:
                            logger.warning(
                                "ASR 模型未注册（%s），将回退到 SenseVoiceSmall 官方 ModelScope 仓库: %s",
                                model_key,
                                _SENSEVOICE_MS_MODEL_ID,
                            )
                            kwargs["model"] = _SENSEVOICE_MS_MODEL_ID
                            kwargs["hub"] = "ms"
                            continue
                    if _try_register_funasr_model(model_key):
                        continue
                raise
            except OSError as exc:
                # Transformers can fail when a local directory contains tokenizers but no weights.
                # Fun-ASR-Nano-2512 currently points to a tokenizer-only `Qwen3-0.6B/` folder.
                missing_dir = _extract_missing_weights_dir(exc)
                if (
                    missing_dir is not None
                    and attempt < max_attempts
                    and model_name == _NANO_MODEL_ID
                    and missing_dir.name.lower().startswith("qwen3-0.6b")
                    and not _dir_has_transformers_weights(missing_dir)
                ):
                    qwen_dir = _download_qwen3_llm_weights()
                    if qwen_dir:
                        kwargs["llm_conf"] = {"init_param_path": qwen_dir}
                        logger.info("已覆盖 llm_conf.init_param_path -> %s", qwen_dir)
                        continue
                raise

        _asr_available = True
        logger.info("ASR 初始化完成")
        try:
            if bool(getattr(settings.asr, "warmup", True)) and _asr_model is not None:
                sample_rate = int(getattr(settings.asr, "sample_rate", 16000) or 16000)
                _warmup_asr_model(_asr_model, sample_rate=sample_rate)
        except Exception:
            pass
        return True
    except Exception as exc:
        logger.error("ASR 初始化失败: %s", exc, exc_info=True)
        _asr_available = False
        _asr_model = None
        return False


def is_asr_available() -> bool:
    return bool(_asr_available and _asr_model is not None)


def get_asr_model_instance() -> Any | None:
    return _asr_model


def get_asr_model_lock() -> Lock:
    """返回模型互斥锁（用于跨线程串行化推理调用，避免底层线程不安全）。"""
    return _asr_model_lock


def get_asr_model_name() -> Optional[str]:
    try:
        if _asr_model is None:
            return None
        return str(getattr(settings.asr, "model", "") or "").strip() or None
    except Exception:
        return None
