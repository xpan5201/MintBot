"""
PyTorch 运行时优化（GPU / CUDA）

目标：
- 尽量使用安全且通用的设置提升吞吐（例如 TF32 / matmul precision）
- 仅在检测到 CUDA 可用时启用，避免影响纯 CPU 环境
"""

from __future__ import annotations

from dataclasses import dataclass

from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class TorchOptimStatus:
    enabled: bool
    device: str
    torch_version: str | None = None
    cuda_version: str | None = None
    gpu_name: str | None = None


_APPLIED = False


def apply_torch_optimizations(*, verbose: bool = False) -> TorchOptimStatus:
    """
    Apply safe, global PyTorch runtime optimizations.

    Notes:
        - This function is idempotent.
        - It intentionally avoids hard requirements on torch; if torch isn't available it returns disabled.
    """
    global _APPLIED

    try:
        import torch  # type: ignore
    except Exception:
        return TorchOptimStatus(enabled=False, device="cpu")

    device = "cuda" if torch.cuda.is_available() else "cpu"
    if device != "cuda":
        return TorchOptimStatus(
            enabled=False,
            device=device,
            torch_version=getattr(torch, "__version__", None),
            cuda_version=getattr(getattr(torch, "version", None), "cuda", None),
        )

    # Apply once: these are global flags.
    if not _APPLIED:
        _APPLIED = True

        # Prefer higher matmul precision for transformers / embeddings.
        try:
            torch.set_float32_matmul_precision("high")
        except Exception:
            pass

        # Enable TF32 on Ampere+ (safe, typical for inference; slight numeric differences are acceptable).
        try:
            torch.backends.cuda.matmul.allow_tf32 = True  # type: ignore[attr-defined]
        except Exception:
            pass
        try:
            torch.backends.cudnn.allow_tf32 = True  # type: ignore[attr-defined]
        except Exception:
            pass

        # cuDNN autotune can improve some kernels (harmless for transformer-heavy workloads).
        try:
            torch.backends.cudnn.benchmark = True  # type: ignore[attr-defined]
        except Exception:
            pass

        # Prefer optimized SDP kernels when available (Flash / MemEff).
        try:
            cuda_backends = getattr(torch.backends, "cuda", None)
            if cuda_backends is not None:
                for fn_name in ("enable_flash_sdp", "enable_mem_efficient_sdp", "enable_math_sdp"):
                    fn = getattr(cuda_backends, fn_name, None)
                    if callable(fn):
                        fn(True)
        except Exception:
            pass

    gpu_name = None
    try:
        gpu_name = torch.cuda.get_device_name(0)
    except Exception:
        pass

    status = TorchOptimStatus(
        enabled=True,
        device=device,
        torch_version=getattr(torch, "__version__", None),
        cuda_version=getattr(getattr(torch, "version", None), "cuda", None),
        gpu_name=gpu_name,
    )

    if verbose:
        logger.info(
            "Torch 优化已应用: torch=%s cuda=%s gpu=%s",
            status.torch_version,
            status.cuda_version,
            status.gpu_name or "unknown",
        )

    return status
