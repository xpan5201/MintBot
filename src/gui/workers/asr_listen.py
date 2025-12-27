"""
ASR 语音输入后台线程（FunASR + QAudioSource）

设计目标：
- 不阻塞 GUI 主线程：录音采集 + 推理均在 QThread 内执行。
- 低延迟：按间隔对最近窗口音频做识别，发出 partial 文本。
- 可降级：FunASR/QtMultimedia 不可用时给出明确错误提示。
"""

from __future__ import annotations

from contextlib import nullcontext
import re
import time
from threading import Event
from typing import Any, Optional

import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal

from src.multimodal.vad_rms import RmsVad
from src.utils.logger import get_logger

logger = get_logger(__name__)

_UNEXPECTED_KW_RE = re.compile(r"unexpected keyword argument '([^']+)'")
_RICH_TOKEN_RE = re.compile(r"<\|[^>]*\|>")
_WHITESPACE_RE = re.compile(r"\s+")
_FAST_INFERENCE_DEPS: tuple[Any, Any, Any] | bool | None = None  # (torch, prepare_data_iterator, deep_update)
_TORCH: Any | bool | None = None
_RICH_POSTPROCESS: Any | bool | None = None


def _get_funasr_fast_inference_deps() -> tuple[Any, Any, Any] | None:
    global _FAST_INFERENCE_DEPS
    if isinstance(_FAST_INFERENCE_DEPS, tuple):
        return _FAST_INFERENCE_DEPS
    if _FAST_INFERENCE_DEPS is False:
        return None
    try:
        import torch
        from funasr.auto.auto_model import prepare_data_iterator  # type: ignore
        from funasr.utils.misc import deep_update  # type: ignore

        _FAST_INFERENCE_DEPS = (torch, prepare_data_iterator, deep_update)
        return _FAST_INFERENCE_DEPS
    except Exception:
        _FAST_INFERENCE_DEPS = False
        return None


def _get_torch() -> Any | None:
    global _TORCH
    if _TORCH is False:
        return None
    if _TORCH is not None:
        return _TORCH
    try:
        import torch

        _TORCH = torch
        return torch
    except Exception:
        _TORCH = False
        return None


def _get_rich_postprocess() -> Any | None:
    global _RICH_POSTPROCESS
    if _RICH_POSTPROCESS is False:
        return None
    if callable(_RICH_POSTPROCESS):
        return _RICH_POSTPROCESS
    try:
        from funasr.utils.postprocess_utils import rich_transcription_postprocess  # type: ignore

        _RICH_POSTPROCESS = rich_transcription_postprocess
        return rich_transcription_postprocess
    except Exception:
        _RICH_POSTPROCESS = False
        return None


def _extract_funasr_text(result: Any) -> str:
    if result is None:
        return ""
    if isinstance(result, str):
        return result
    if isinstance(result, dict):
        text = result.get("text")
        return str(text or "")
    if isinstance(result, list) and result:
        for item in result:
            if isinstance(item, dict) and "text" in item:
                return str(item.get("text") or "")
            if isinstance(item, str) and item.strip():
                return str(item)
        # FunASR 也可能返回 list[list[dict]] 等复杂结构
        try:
            first = result[0]
            if isinstance(first, list):
                for sub in first:
                    if isinstance(sub, dict) and "text" in sub:
                        return str(sub.get("text") or "")
        except Exception:
            pass
    return str(result)


def _postprocess_asr_text(text: str) -> str:
    """Post-process FunASR text for chat input.

    SenseVoice outputs may contain rich tokens like `<|zh|>`; prefer FunASR's official postprocess
    helper when available, then fall back to a small regex cleanup.
    """
    text = (text or "").strip()
    if not text:
        return ""

    # Prefer FunASR official postprocess for SenseVoice rich transcription.
    rich_post = _get_rich_postprocess()
    if rich_post is not None:
        try:
            text = str(rich_post(text) or "").strip()
        except Exception:
            pass

    # Remove leftover rich tokens like `<|zh|>` / `<|HAPPY|>` etc.
    text = _RICH_TOKEN_RE.sub("", text)
    text = _WHITESPACE_RE.sub(" ", text).strip()
    return text


def _call_funasr_generate(model: Any, kwargs: dict[str, Any]) -> Any:
    """Call model.generate with best-effort kwarg compatibility."""
    for _ in range(6):
        try:
            return model.generate(**kwargs)
        except TypeError as exc:
            msg = str(exc)
            m = _UNEXPECTED_KW_RE.search(msg)
            if not m:
                raise
            bad_key = m.group(1)
            if bad_key not in kwargs:
                raise
            kwargs.pop(bad_key, None)
            continue
    return model.generate(**kwargs)


def _call_funasr_inference(model: Any, kwargs: dict[str, Any]) -> Any:
    """Call model.inference with best-effort kwarg compatibility."""
    for _ in range(6):
        try:
            return model.inference(**kwargs)
        except TypeError as exc:
            msg = str(exc)
            m = _UNEXPECTED_KW_RE.search(msg)
            if not m:
                raise
            bad_key = m.group(1)
            if bad_key not in kwargs:
                raise
            kwargs.pop(bad_key, None)
            continue
    return model.inference(**kwargs)


def _call_funasr_model_inference_with_fallback(model: Any, batch: dict[str, Any], kwargs: dict[str, Any]) -> Any:
    """Call a FunASR model's `inference` method with best-effort kwarg compatibility."""
    for _ in range(6):
        try:
            return model.inference(**batch, **kwargs)
        except TypeError as exc:
            msg = str(exc)
            m = _UNEXPECTED_KW_RE.search(msg)
            if not m:
                raise
            bad_key = m.group(1)
            if bad_key not in kwargs:
                raise
            kwargs.pop(bad_key, None)
            continue
    return model.inference(**batch, **kwargs)


def _call_funasr_inference_fast(automodel: Any, kwargs: dict[str, Any]) -> Any:
    """Fast-path inference that avoids AutoModel.inference_with_vad overhead.

    - Skips FunASR internal VAD (used by `generate()` when `vad_model` is configured).
    - Avoids tqdm progress bar and per-call CUDA cache clearing in some FunASR versions.
    """
    deps = _get_funasr_fast_inference_deps()
    if deps is None:
        return _call_funasr_inference(automodel, dict(kwargs))
    torch, prepare_data_iterator, deep_update = deps

    model_impl = getattr(automodel, "model", None)
    base_cfg = getattr(automodel, "kwargs", None)
    if model_impl is None or not isinstance(base_cfg, dict):
        return _call_funasr_inference(automodel, dict(kwargs))

    cfg = dict(kwargs)
    data_in = cfg.pop("input", None)
    if data_in is None:
        return _call_funasr_inference(automodel, dict(kwargs))
    input_len = cfg.pop("input_len", None)
    key = cfg.pop("key", None)

    model_kwargs = dict(base_cfg)
    model_kwargs.pop("cache", None)
    deep_update(model_kwargs, cfg)
    model_kwargs.setdefault("batch_size", 1)
    model_kwargs["disable_pbar"] = True

    try:
        model_impl.eval()
    except Exception:
        pass

    key_list, data_list = prepare_data_iterator(
        data_in, input_len=input_len, data_type=model_kwargs.get("data_type", None), key=key
    )

    results_list: list[Any] = []
    batch_size = int(model_kwargs.get("batch_size", 1) or 1)
    batch_size = max(1, batch_size)
    for beg_idx in range(0, len(data_list), batch_size):
        end_idx = min(len(data_list), beg_idx + batch_size)
        data_batch = data_list[beg_idx:end_idx]
        key_batch = key_list[beg_idx:end_idx]
        batch = {"data_in": data_batch, "key": key_batch}

        if (end_idx - beg_idx) == 1 and model_kwargs.get("data_type", None) == "fbank":
            batch["data_in"] = data_batch[0]
            batch["data_lengths"] = input_len

        try:
            inference_ctx = torch.inference_mode()
        except Exception:
            inference_ctx = torch.no_grad()
        with inference_ctx:
            res = _call_funasr_model_inference_with_fallback(model_impl, batch, model_kwargs)

        if isinstance(res, (list, tuple)):
            results = res[0] if len(res) > 0 else [{"text": ""}]
        else:
            results = res

        if results is None:
            continue
        if isinstance(results, list):
            results_list.extend(results)
        else:
            results_list.append(results)

    return results_list


class ASRListenThread(QThread):
    """实时语音转写线程：采集麦克风 PCM -> 周期性推理 -> 输出 partial/final 文本。"""

    partial_text = pyqtSignal(str)
    final_text = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(
        self,
        *,
        sample_rate: int = 16000,
        partial_interval_ms: int = 260,
        partial_window_s: float = 6.0,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.sample_rate = max(8000, int(sample_rate))
        self.partial_interval_ms = max(80, int(partial_interval_ms))
        self.partial_window_s = max(0.5, float(partial_window_s))

        self._stop_event = Event()
        self._pcm = bytearray()
        self._last_emit_text = ""
        self._last_infer_at = 0.0
        self._last_infer_bytes = 0
        self._funasr_cache: dict[str, Any] = {}
        self._skip_final = False

        # Soft cap: avoid unbounded growth if user forgets to stop recording.
        self._max_record_s = 120.0

    def stop(self, *, skip_final: bool = False) -> None:
        if skip_final:
            self._skip_final = True
        self._stop_event.set()
        try:
            self.requestInterruption()
        except Exception:
            pass

    @staticmethod
    def _infer_text(
        model: Any,
        model_lock: Any,
        pcm_bytes: bytes | memoryview,
        *,
        sample_rate: int,
        is_final: bool,
        gen_kwargs: Optional[dict[str, Any]] = None,
    ) -> str:
        if not pcm_bytes:
            return ""
        wav = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        if wav.size <= 0:
            return ""

        extra = dict(gen_kwargs or {})
        # SenseVoice recommended args (ignored safely if not supported by current FunASR version).
        if "merge_vad" not in extra:
            extra["merge_vad"] = bool(is_final)

        # FunASR 不同版本的参数签名存在差异：做少量兼容尝试。
        result: Any = None
        torch = _get_torch()
        inference_ctx = nullcontext()
        if torch is not None:
            try:
                inference_ctx = torch.inference_mode()
            except Exception:
                inference_ctx = torch.no_grad()
        with model_lock, inference_ctx:
            for base in (
                {"input": wav, "sampling_rate": sample_rate},
                {"input": wav, "fs": sample_rate},
                {"input": wav},
            ):
                try:
                    kwargs = dict(base)
                    kwargs.update(extra)
                    if is_final:
                        # Final: allow internal VAD / merge_vad behavior configured in AutoModel.generate().
                        try:
                            result = _call_funasr_generate(model, kwargs)
                        except Exception:
                            if hasattr(model, "inference"):
                                result = _call_funasr_inference(model, kwargs)
                            else:
                                raise
                    else:
                        # Partial: prefer inference (skip FunASR internal VAD) to reduce latency and CPU/GPU cost.
                        if hasattr(model, "inference"):
                            try:
                                result = _call_funasr_inference_fast(model, kwargs)
                            except Exception:
                                result = _call_funasr_inference(model, kwargs)
                        else:
                            result = _call_funasr_generate(model, kwargs)
                    break
                except TypeError:
                    continue
        return _postprocess_asr_text(_extract_funasr_text(result))

    def _should_infer(self, now: float, bytes_per_second: int) -> bool:
        interval_s = self.partial_interval_ms / 1000.0
        if now - self._last_infer_at < interval_s:
            return False
        # 至少新增约 200ms 音频再做一次推理（降低抖动与 CPU 占用）
        min_new_s = max(0.25, min(0.5, interval_s * 0.6))
        if len(self._pcm) < self._last_infer_bytes + int(bytes_per_second * min_new_s):
            return False
        return True

    def run(self) -> None:  # pragma: no cover - QThread
        try:
            try:
                from PyQt6.QtMultimedia import QAudioFormat, QAudioSource, QMediaDevices
            except Exception as exc:
                self.error.emit(f"缺少 PyQt6.QtMultimedia，无法录音：{exc}")
                return

            try:
                from src.multimodal.asr_initializer import (
                    get_asr_model_instance,
                    get_asr_model_lock,
                    init_asr,
                    is_asr_available,
                )
            except Exception as exc:
                self.error.emit(f"导入 ASR 模块失败：{exc}")
                return

            if not init_asr() or not is_asr_available():
                self.error.emit("ASR 未启用或初始化失败（请检查设置/依赖）")
                return

            model = get_asr_model_instance()
            model_lock = get_asr_model_lock()
            if model is None:
                self.error.emit("ASR 模型不可用（初始化失败）")
                return

            # Load tuning knobs from config (best-effort).
            try:
                from src.config.settings import settings  # local import to avoid startup cost

                lang = str(getattr(settings.asr, "language", "auto") or "auto").strip() or "auto"
                use_itn = bool(getattr(settings.asr, "use_itn", True))
                ban_emo_unk = bool(getattr(settings.asr, "ban_emo_unk", True))
                merge_vad_enabled = bool(getattr(settings.asr, "merge_vad", True))
                merge_length_s = int(getattr(settings.asr, "merge_length_s", 15) or 15)
                batch_size_s = int(getattr(settings.asr, "batch_size_s", 60) or 60)
                silence_skip = bool(getattr(settings.asr, "silence_skip_partial", True))
                silence_rms = float(getattr(settings.asr, "silence_rms_threshold", 0.006) or 0.006)
                threshold_mode = str(getattr(settings.asr, "silence_threshold_mode", "fixed") or "fixed").strip()
                threshold_mode = threshold_mode.lower()
                if threshold_mode not in {"fixed", "auto"}:
                    threshold_mode = "fixed"
                threshold_multiplier = float(getattr(settings.asr, "silence_threshold_multiplier", 3.0) or 3.0)
                noise_calibration_ms = int(getattr(settings.asr, "noise_calibration_ms", 400) or 400)
                min_speech_ms = int(getattr(settings.asr, "min_speech_ms", 180) or 180)
                endpoint_silence_ms = int(getattr(settings.asr, "endpoint_silence_ms", 900) or 900)
                pre_roll_ms = int(getattr(settings.asr, "pre_roll_ms", 250) or 250)
                max_utterance_s = float(getattr(settings.asr, "max_utterance_s", 25.0) or 25.0)
            except Exception:
                lang = "auto"
                use_itn = True
                ban_emo_unk = True
                merge_vad_enabled = True
                merge_length_s = 15
                batch_size_s = 60
                silence_skip = True
                silence_rms = 0.006
                threshold_mode = "fixed"
                threshold_multiplier = 3.0
                noise_calibration_ms = 400
                min_speech_ms = 180
                endpoint_silence_ms = 900
                pre_roll_ms = 250
                max_utterance_s = 25.0

            gen_kwargs_partial: dict[str, Any] = {
                "language": lang,
                "use_itn": use_itn,
                "ban_emo_unk": ban_emo_unk,
                "cache": self._funasr_cache,
                "merge_vad": False,
                "disable_pbar": True,
            }
            gen_kwargs_final: dict[str, Any] = {
                "language": lang,
                "use_itn": use_itn,
                "ban_emo_unk": ban_emo_unk,
                "cache": self._funasr_cache,
                "merge_vad": merge_vad_enabled,
                "merge_length_s": merge_length_s,
                "batch_size_s": batch_size_s,
                "disable_pbar": True,
            }

            fmt = QAudioFormat()
            fmt.setSampleRate(self.sample_rate)
            fmt.setChannelCount(1)
            fmt.setSampleFormat(QAudioFormat.SampleFormat.Int16)

            device = QMediaDevices.defaultAudioInput()
            try:
                if device is None or getattr(device, "isNull", lambda: True)():
                    self.error.emit("未检测到可用的麦克风设备")
                    return
            except Exception:
                pass

            source = QAudioSource(device, fmt)
            try:
                # 缓冲区越小延迟越低，但过小可能导致丢帧；取约 200ms。
                source.setBufferSize(int(self.sample_rate * 2 * 0.2))
            except Exception:
                pass

            io = source.start()
            if io is None:
                self.error.emit("无法打开麦克风（QAudioSource.start() 返回空）")
                return

            bytes_per_second = self.sample_rate * 2
            window_bytes = int(bytes_per_second * self.partial_window_s)
            max_bytes = int(bytes_per_second * self._max_record_s)

            vad = RmsVad(
                sample_rate=self.sample_rate,
                threshold_mode="auto" if threshold_mode == "auto" else "fixed",
                fixed_threshold=silence_rms,
                threshold_multiplier=threshold_multiplier,
                noise_calibration_ms=noise_calibration_ms,
                min_speech_ms=min_speech_ms,
                endpoint_silence_ms=endpoint_silence_ms,
                pre_roll_ms=pre_roll_ms,
                max_utterance_s=max_utterance_s,
                recording_pcm=self._pcm,
            )
            last_rms = 0.0
            last_threshold = float(silence_rms)

            while not self._stop_event.is_set() and not self.isInterruptionRequested():
                try:
                    avail = int(io.bytesAvailable())
                except Exception:
                    avail = 0
                if avail > 0:
                    try:
                        chunk = bytes(io.read(avail))
                    except Exception:
                        try:
                            chunk = bytes(io.readAll())
                        except Exception:
                            chunk = b""
                    if chunk:
                        vad_result = vad.process_chunk(chunk)
                        last_rms = float(vad_result.rms)
                        last_threshold = float(vad_result.threshold)
                        if vad_result.endpoint_reached:
                            self._stop_event.set()
                            break
                        if len(self._pcm) > max_bytes:
                            # Fail-safe: avoid unbounded growth if user forgets to stop.
                            self._stop_event.set()
                            break

                now = time.monotonic()
                if vad.speech_started and self._should_infer(now, bytes_per_second):
                    self._last_infer_at = now
                    self._last_infer_bytes = len(self._pcm)
                    pcm_view = memoryview(self._pcm)
                    segment = pcm_view[-window_bytes:] if len(pcm_view) > window_bytes else pcm_view
                    if silence_skip and last_rms < last_threshold:
                        # Skip noisy inference on silence to reduce CPU.
                        self.msleep(20)
                        continue
                    text = self._infer_text(
                        model,
                        model_lock,
                        segment,
                        sample_rate=self.sample_rate,
                        is_final=False,
                        gen_kwargs=dict(gen_kwargs_partial),
                    ).strip()
                    if text and text != self._last_emit_text:
                        self._last_emit_text = text
                        self.partial_text.emit(text)

                # 轻量轮询：避免占满 CPU
                self.msleep(20)

            try:
                source.stop()
            except Exception:
                pass
            try:
                io.close()
            except Exception:
                pass

            # 最终推理（全量音频）
            if bool(getattr(self, "_skip_final", False)):
                return
            final_pcm = bytes(self._pcm) if vad.speech_started else vad.captured_audio_bytes()
            final = self._infer_text(
                model,
                model_lock,
                final_pcm,
                sample_rate=self.sample_rate,
                is_final=True,
                gen_kwargs=dict(gen_kwargs_final),
            ).strip()
            if final:
                self.final_text.emit(final)
        except Exception as exc:
            logger.error("ASRListenThread 运行失败: %s", exc, exc_info=True)
            self.error.emit(str(exc))

