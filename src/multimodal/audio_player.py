"""
音频播放器模块

提供音频播放功能，支持音量控制和错误处理。

版本：v2.54.0
日期：2025-11-20
"""

import io
import threading
import time
from collections import deque
from pathlib import Path
from typing import Callable, Optional, Deque, Tuple

# 使用 sounddevice 作为播放器
try:
    import sounddevice as sd  # type: ignore[import-untyped]
    import soundfile as sf  # type: ignore[import-untyped]
    _has_sounddevice = True
    _sounddevice_error = None
except Exception as e:
    _has_sounddevice = False
    _sounddevice_error = e

from src.utils.logger import logger


class AudioPlayer:
    """
    音频播放器

    使用 sounddevice 播放音频，支持音量控制和错误处理。
    """

    def __init__(
        self,
        default_volume: float = 0.8,
        max_queue_size: int = 0,
    ) -> None:
        """
        初始化音频播放器

        Args:
            default_volume: 默认音量（0.0-1.0）
            max_queue_size: 播放队列上限，0 表示不限制
        """
        self._volume: float = max(0.0, min(1.0, float(default_volume)))
        self._is_playing: bool = False
        self._queue: Deque[Tuple[object, int]] = deque()
        self._queue_lock = threading.Lock()
        self._queue_event = threading.Event()
        self._stop_event = threading.Event()
        self._worker: Optional[threading.Thread] = None
        self._max_queue_size = max(0, int(max_queue_size))
        self._on_playback_start: list[Callable[[list[float], float, float], None]] = []

        if not _has_sounddevice:
            logger.warning(
                "sounddevice 未安装，音频播放功能不可用"
            )
            if _sounddevice_error:
                logger.debug(f"导入错误: {_sounddevice_error}")
        else:
            logger.info(f"初始化音频播放器（sounddevice）: 音量={self._volume}")
            self._worker = threading.Thread(
                target=self._playback_loop, name="AudioPlayerWorker", daemon=True
            )
            self._worker.start()

    def _playback_loop(self) -> None:
        """后台线程：顺序播放队列中的音频，避免互相打断。"""
        if not _has_sounddevice:
            return

        while not self._stop_event.is_set():
            self._queue_event.wait()
            if self._stop_event.is_set():
                break

            while True:
                with self._queue_lock:
                    if not self._queue:
                        self._queue_event.clear()
                        break
                    data, samplerate = self._queue.popleft()

                try:
                    logger.debug(
                        "AudioPlayer 播放队列出队: %d 帧, 采样率=%d",
                        getattr(data, "shape", (0,))[0],
                        samplerate,
                    )
                    try:
                        env, step_s = self._compute_level_envelope(data, samplerate, fps=60)
                        if env:
                            start_t = time.monotonic()
                            self._emit_playback_start(env, step_s, start_t)
                    except Exception:
                        pass
                    sd.play(data, samplerate)
                    self._is_playing = True
                    sd.wait()
                except Exception as e:
                    logger.error(f"播放音频失败: {e}", exc_info=True)
                finally:
                    self._is_playing = False

        # 停止可能残留的播放
        try:
            sd.stop()
        except Exception:
            pass

    def register_playback_start_observer(self, callback: Callable[[list[float], float, float], None]) -> None:
        """Register a callback invoked when a queued audio segment actually starts playing.

        Args:
            callback: called as (envelope, step_seconds, start_monotonic)
        """
        if not callable(callback):
            return
        try:
            self._on_playback_start.append(callback)
        except Exception:
            pass

    def _emit_playback_start(self, envelope: list[float], step_s: float, start_t: float) -> None:
        callbacks = None
        try:
            callbacks = list(self._on_playback_start)
        except Exception:
            callbacks = None
        if not callbacks:
            return
        for cb in callbacks:
            try:
                cb(list(envelope), float(step_s), float(start_t))
            except Exception:
                pass

    def _compute_level_envelope(self, data, samplerate: int, *, fps: int = 60) -> tuple[list[float], float]:
        """Compute a coarse RMS envelope (0-1) for lip-sync/visualizers.

        This is intentionally lightweight and vectorized; it returns ~fps values per second.
        """
        try:
            import numpy as np  # type: ignore[import-not-found]
        except Exception:
            return ([], 1.0 / float(max(1, int(fps))))

        try:
            sr = max(1, int(samplerate))
        except Exception:
            sr = 44100
        step = max(1, int(sr / float(max(1, int(fps)))))
        step_s = float(step) / float(sr)

        try:
            x = data
            if x is None:
                return ([], step_s)
            if hasattr(x, "ndim") and int(getattr(x, "ndim", 1)) > 1:
                try:
                    x = np.mean(x, axis=1)
                except Exception:
                    x = x[:, 0]
            x = np.asarray(x, dtype=np.float32)
            if x.size <= 0:
                return ([], step_s)
        except Exception:
            return ([], step_s)

        n = int(x.shape[0])
        blocks = int(n // step)
        if blocks <= 0:
            try:
                rms = float(np.sqrt(np.mean(np.square(x))) or 0.0)
            except Exception:
                rms = 0.0
            v = 1.0 if rms > 0.02 else 0.0
            return ([float(v)], step_s)

        try:
            trimmed = x[: blocks * step]
            frames = trimmed.reshape(blocks, step)
            rms = np.sqrt(np.mean(np.square(frames), axis=1))
            # Robust normalization: 95th percentile keeps occasional spikes from squashing everything.
            denom = float(np.percentile(rms, 95) + 1e-6)
            env = np.clip(rms / denom, 0.0, 1.0)
            # Gentle compression so quiet speech still moves, loud speech doesn't over-open.
            env = np.power(env, 0.65)
            return (env.astype(np.float32).tolist(), step_s)
        except Exception:
            return ([], step_s)

    def _enqueue_audio(self, data, samplerate: int) -> int:
        """将解码后的音频推入播放队列。"""
        with self._queue_lock:
            self._queue.append((data, samplerate))
            if self._max_queue_size and len(self._queue) > self._max_queue_size:
                overflow = len(self._queue) - self._max_queue_size
                for _ in range(overflow):
                    self._queue.popleft()
                logger.debug(
                    "音频队列达到上限，丢弃最旧的 %d 段音频以保持顺序", overflow
                )
            self._queue_event.set()
            return len(self._queue)

    def set_queue_limit(self, max_queue_size: int) -> None:
        """设置播放队列上限，0 表示不限制。"""
        with self._queue_lock:
            self._max_queue_size = max(0, int(max_queue_size))
            if self._max_queue_size and len(self._queue) > self._max_queue_size:
                overflow = len(self._queue) - self._max_queue_size
                for _ in range(overflow):
                    self._queue.popleft()
                logger.debug(
                    "调整音频队列上限，立即丢弃最旧的 %d 段音频", overflow
                )

    def clear_queue(self) -> None:
        """清空待播放队列。"""
        with self._queue_lock:
            self._queue.clear()
            self._queue_event.clear()

    def _play_with_sounddevice(self, audio_data: bytes) -> bool:
        """
        使用 sounddevice 播放音频数据

        Args:
            audio_data: 音频数据（WAV 格式）

        Returns:
            bool: 是否成功开始播放
        """
        if not _has_sounddevice:
            logger.warning("sounddevice 不可用，无法播放音频")
            return False

        if not audio_data:
            logger.warning("音频数据为空，跳过播放")
            return False

        try:
            # 解析音频数据
            with sf.SoundFile(io.BytesIO(audio_data)) as f:
                data = f.read(dtype="float32")
                samplerate = f.samplerate
        except Exception as e:
            logger.error(f"解析音频数据失败: {e}", exc_info=True)
            return False

        if not hasattr(data, "size") or data.size == 0:
            logger.warning("解析后的音频数据为空，跳过播放")
            return False

        # 应用音量
        if self._volume != 1.0:
            data = data * self._volume

        queue_len = self._enqueue_audio(data, samplerate)
        logger.debug(
            "音频加入播放队列: %d 帧, 采样率=%d, 音量=%.2f, 队列长度=%d",
            data.shape[0],
            samplerate,
            self._volume,
            queue_len,
        )
        return True

    def play_audio(self, audio_data: bytes) -> bool:
        """
        播放音频数据

        Args:
            audio_data: 音频数据（WAV 格式）

        Returns:
            bool: 是否成功开始播放
        """
        return self._play_with_sounddevice(audio_data)

    def play_file(self, file_path: str) -> bool:
        """
        播放音频文件

        Args:
            file_path: 音频文件路径

        Returns:
            bool: 是否成功开始播放
        """
        path = Path(file_path)
        if not path.exists():
            logger.error(f"音频文件不存在: {file_path}")
            return False

        try:
            audio_bytes = path.read_bytes()
        except Exception as e:
            logger.error(f"读取音频文件失败: {e}", exc_info=True)
            return False

        return self._play_with_sounddevice(audio_bytes)

    def stop(self) -> None:
        """停止播放"""
        if _has_sounddevice:
            try:
                sd.stop()
                self._is_playing = False
                logger.debug("停止播放")
            except Exception as e:
                logger.debug(f"停止播放时出错: {e}")

    def pause(self) -> None:
        """暂停播放（sounddevice 不支持暂停，等同于停止）"""
        self.stop()

    def set_volume(self, volume: float) -> None:
        """
        设置音量

        Args:
            volume: 音量（0.0-1.0）
        """
        volume = max(0.0, min(1.0, float(volume)))
        self._volume = volume
        logger.debug(f"设置音量: {volume:.2f}")

    def get_volume(self) -> float:
        """
        获取当前音量

        Returns:
            float: 当前音量（0.0-1.0）
        """
        return self._volume

    def is_playing(self) -> bool:
        """
        检查是否正在播放

        Returns:
            bool: 是否正在播放
        """
        return self._is_playing


# 全局音频播放器实例
_audio_player: Optional[AudioPlayer] = None


def get_audio_player(
    default_volume: float = 0.8,
    max_queue_size: Optional[int] = None,
) -> AudioPlayer:
    """
    获取音频播放器单例

    Args:
        default_volume: 默认音量（0.0-1.0）

    Returns:
        AudioPlayer: 音频播放器实例
    """
    global _audio_player

    if _audio_player is None:
        _audio_player = AudioPlayer(
            default_volume=default_volume,
            max_queue_size=max_queue_size or 0,
        )
    else:
        if max_queue_size is not None:
            _audio_player.set_queue_limit(max_queue_size)
        if abs(_audio_player.get_volume() - float(default_volume)) > 1e-6:
            _audio_player.set_volume(default_volume)

    return _audio_player
