"""
FFmpeg 自动配置（用于 pydub / FunASR 等音频依赖）

目标：
- 在未安装系统 ffmpeg 时，尽量自动提供可用的 ffmpeg 可执行文件；
- 必须在 import pydub / funasr 之前调用，才能避免其 import 阶段的噪声 warning/print；
- 失败时安全降级（仍允许 torchaudio/soundfile 路径工作）。
"""

from __future__ import annotations

import os
import shutil
import warnings
from pathlib import Path
from threading import Lock

from src.utils.logger import get_logger

logger = get_logger(__name__)

_ffmpeg_lock = Lock()
_ffmpeg_configured = False
_ffmpeg_path: str | None = None


def _prepend_path(dir_path: str) -> None:
    if not dir_path:
        return
    current = os.environ.get("PATH", "")
    parts = [p for p in current.split(os.pathsep) if p]
    if parts and parts[0].lower() == dir_path.lower():
        return
    if any(p.lower() == dir_path.lower() for p in parts):
        parts = [p for p in parts if p.lower() != dir_path.lower()]
    os.environ["PATH"] = dir_path + (os.pathsep + os.pathsep.join(parts) if parts else "")


def _mintchat_cache_dir() -> Path:
    # Prefer platform-native cache dirs when possible; fall back to ~/.cache on Windows too.
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_CACHE_HOME") or ""
    root = Path(base) if base else (Path.home() / ".cache")
    return root / "mintchat" / "ffmpeg"


def _ensure_ffmpeg_alias(exe: str) -> tuple[str, str]:
    """Return (ffmpeg_path, bin_dir).

    ffmpeg_path is discoverable by `shutil.which("ffmpeg")`.
    """
    bin_dir = os.path.dirname(exe)
    is_windows = os.name == "nt"
    alias_name = "ffmpeg.exe" if is_windows else "ffmpeg"
    preferred_alias = str(Path(bin_dir) / alias_name)

    if os.path.exists(preferred_alias):
        return preferred_alias, bin_dir

    # Try placing alias next to the real binary first.
    try:
        shutil.copyfile(exe, preferred_alias)
        return preferred_alias, bin_dir
    except PermissionError:
        pass
    except Exception as exc:
        logger.debug("生成 ffmpeg 别名失败（将尝试缓存目录）: %s", exc)

    # Fall back to a writable cache dir.
    cache_dir = _mintchat_cache_dir()
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        logger.debug("创建 ffmpeg 缓存目录失败: %s", exc)
        return exe, bin_dir

    cache_alias = str(cache_dir / alias_name)
    try:
        if not os.path.exists(cache_alias):
            shutil.copyfile(exe, cache_alias)
        return cache_alias, str(cache_dir)
    except Exception as exc:
        logger.debug("写入 ffmpeg 缓存别名失败: %s", exc)
        return exe, bin_dir


def ensure_ffmpeg_for_audio(*, quiet: bool = True) -> str | None:
    """Ensure `ffmpeg` is available on PATH and (if possible) configured for pydub.

    This mirrors `text.py::setup_ffmpeg_for_pydub()` but is safe to call from the app:
    - Optional dependency: imageio-ffmpeg
    - Thread-safe, idempotent
    - Best-effort configuration (no hard failure)
    """
    global _ffmpeg_configured, _ffmpeg_path

    with _ffmpeg_lock:
        if _ffmpeg_configured:
            return _ffmpeg_path
        _ffmpeg_configured = True

        existing = shutil.which("ffmpeg")
        if existing:
            _ffmpeg_path = existing
            return existing

        try:
            import imageio_ffmpeg  # type: ignore
        except Exception as exc:
            if not quiet:
                logger.info("未安装 imageio-ffmpeg，无法自动提供 ffmpeg：%s", exc)
            _ffmpeg_path = None
            return None

        try:
            exe = str(imageio_ffmpeg.get_ffmpeg_exe())
        except Exception as exc:
            if not quiet:
                logger.warning("定位/下载 ffmpeg 失败：%s", exc)
            _ffmpeg_path = None
            return None

        ffmpeg_path, path_dir = _ensure_ffmpeg_alias(exe)
        _prepend_path(path_dir)

        # Configure pydub converter (must happen after PATH update). Keep it best-effort.
        try:
            with warnings.catch_warnings():
                warnings.filterwarnings(
                    "ignore",
                    message=r".*Couldn't find ffmpeg or avconv.*",
                    category=RuntimeWarning,
                )
                from pydub import AudioSegment  # type: ignore

            AudioSegment.converter = ffmpeg_path
            AudioSegment.ffmpeg = ffmpeg_path
        except Exception:
            pass

        _ffmpeg_path = ffmpeg_path
        return _ffmpeg_path
