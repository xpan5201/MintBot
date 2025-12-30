"""
TTS 持久化缓存模块

提供磁盘级别的音频缓存，配合内存 LRU 缓存实现两级缓存体系。

版本：v3.4.0
优化：改进错误处理、性能和类型注解

设计目标：
- 将 GPT-SoVITS 的重复文本合成结果落盘，跨进程复用
- 保持简单的 JSON 索引结构，便于调试和清理
- 支持可选压缩，兼顾磁盘占用和 CPU 成本
- 线程安全，支持在不同线程/事件循环中被同时访问
"""

from __future__ import annotations

import gzip
import json
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Dict, Optional

from src.utils.logger import logger


@dataclass
class CacheEntry:
    """磁盘缓存条目描述"""

    key: str
    filename: str
    size: int
    timestamp: float
    hits: int = 0
    compressed: bool = True
    disk_size: int = 0
    expires_at: Optional[float] = None


class PersistentTTSAudioCache:
    """
    简单的文件系统缓存实现（LRU）

    音频以 {key}.bin 格式存放在 data/tts_cache/audio/ 目录下，
    metadata 则记录在 cache_index.json 中。
    """

    def __init__(
        self,
        root_dir: Path | str,
        max_entries: int = 400,
        max_disk_usage_bytes: int | None = None,
        compress: bool = True,
        ttl_seconds: float | None = None,
        time_provider: Optional[Callable[[], float]] = None,
    ) -> None:
        self.root_dir = Path(root_dir)
        self.audio_dir = self.root_dir / "audio"
        self.index_path = self.root_dir / "cache_index.json"
        self.max_entries = max(1, int(max_entries))
        self.max_disk_usage_bytes = (
            max(1, int(max_disk_usage_bytes)) if max_disk_usage_bytes else None
        )
        self.compress = compress
        self.ttl_seconds = ttl_seconds if ttl_seconds and ttl_seconds > 0 else None
        self._time = time_provider or time.time
        self._lock = threading.Lock()
        self._entries: Dict[str, CacheEntry] = {}
        self._disk_usage: int = 0
        self._stats: Dict[str, int] = {
            "hits": 0,
            "misses": 0,
            "evictions": 0,
            "expired": 0,
        }

        self.root_dir.mkdir(parents=True, exist_ok=True)
        self.audio_dir.mkdir(parents=True, exist_ok=True)

        self._load_index()

    # --------------------------------------------------------------------- #
    # 基础读写
    # --------------------------------------------------------------------- #
    def _now(self) -> float:
        return float(self._time())

    def _load_index(self) -> None:
        """从磁盘加载索引"""
        if not self.index_path.exists():
            # 不记录索引创建日志，减少日志输出
            return

        try:
            data = json.loads(self.index_path.read_text(encoding="utf-8"))
            entries = data.get("entries", {})
            loaded = 0
            for key, payload in entries.items():
                filename = payload.get("filename")
                if not filename:
                    continue
                file_path = self.audio_dir / filename
                if not file_path.exists():
                    continue
                timestamp = payload.get("timestamp", self._now())
                expires_at = payload.get("expires_at")
                disk_size = payload.get("disk_size")
                if disk_size is None:
                    try:
                        disk_size = file_path.stat().st_size
                    except OSError:
                        disk_size = 0
                entry = CacheEntry(
                    key=key,
                    filename=filename,
                    size=payload.get("size", file_path.stat().st_size),
                    timestamp=timestamp,
                    hits=payload.get("hits", 0),
                    compressed=payload.get("compressed", True),
                    disk_size=disk_size,
                    expires_at=expires_at,
                )
                if self._is_expired(entry):
                    self._remove_entry(file_path, entry)
                    self._stats["expired"] += 1
                    continue
                self._entries[key] = entry
                self._disk_usage += entry.disk_size
                loaded += 1
            # 不记录缓存加载日志，减少日志输出
        except Exception as exc:
            logger.warning("读取 TTS 磁盘缓存索引失败，将重新创建: %s", exc)
            self._entries.clear()
            self._disk_usage = 0

    def _save_index(self) -> None:
        """将索引写回磁盘"""
        try:
            payload = {
                "version": 3,
                "entries": {key: asdict(entry) for key, entry in self._entries.items()},
                "updated_at": self._now(),
            }
            self.index_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as exc:
            # 仅在严重错误时记录警告
            logger.warning("写入 TTS 磁盘缓存索引失败: %s", exc)

    # --------------------------------------------------------------------- #
    # 公开接口
    # --------------------------------------------------------------------- #
    def get(self, key: str) -> Optional[bytes]:
        """读取缓存"""
        # 先在锁内读取元信息，避免长时间持锁进行磁盘 I/O
        with self._lock:
            entry = self._entries.get(key)
            if not entry:
                self._stats["misses"] += 1
                return None

            filename = entry.filename
            compressed = bool(entry.compressed)
            file_path = self.audio_dir / filename

            if self._is_expired(entry):
                # 不记录过期日志，减少日志输出
                self._remove_entry(file_path, entry)
                self._stats["expired"] += 1
                self._stats["misses"] += 1
                self._save_index()
                return None

        # 锁外做磁盘读取/解压，降低并发读写阻塞
        if not file_path.exists():
            with self._lock:
                current = self._entries.get(key)
                if current and current.filename == filename:
                    self._entries.pop(key, None)
                    self._save_index()
                self._stats["misses"] += 1
            return None

        try:
            data = file_path.read_bytes()
            if compressed:
                data = gzip.decompress(data)
        except (gzip.BadGzipFile, EOFError) as exc:
            logger.warning("TTS 缓存文件损坏（压缩格式错误），移除条目: %s", exc)
            with self._lock:
                current = self._entries.get(key)
                if current and current.filename == filename:
                    self._remove_entry(file_path, current)
                    self._save_index()
                self._stats["misses"] += 1
            return None
        except (OSError, IOError) as exc:
            logger.warning("读取 TTS 磁盘缓存失败，移除条目: %s", exc)
            with self._lock:
                current = self._entries.get(key)
                if current and current.filename == filename:
                    self._entries.pop(key, None)
                    try:
                        file_path.unlink(missing_ok=True)
                    except OSError:
                        pass
                    self._save_index()
                self._stats["misses"] += 1
            return None

        with self._lock:
            current = self._entries.get(key)
            if not current or current.filename != filename:
                self._stats["misses"] += 1
                return None
            current.timestamp = self._now()
            current.hits += 1
            self._entries[key] = current
            self._stats["hits"] += 1
            return data

    def set(self, key: str, audio_data: bytes) -> None:
        """写入缓存"""
        if not audio_data:
            return

        with self._lock:
            self._evict_if_needed()

            filename = f"{key}.bin"
            file_path = self.audio_dir / filename

            payload = gzip.compress(audio_data) if self.compress else audio_data
            disk_size = len(payload)

            try:
                # 先写入临时文件，然后原子性重命名，避免写入过程中文件损坏
                temp_file = file_path.with_suffix(".tmp")
                temp_file.write_bytes(payload)
                temp_file.replace(file_path)
            except (OSError, IOError) as exc:
                logger.warning("写入 TTS 磁盘缓存失败: %s", exc)
                # 清理可能残留的临时文件
                try:
                    temp_file = file_path.with_suffix(".tmp")
                    if temp_file.exists():
                        temp_file.unlink(missing_ok=True)
                except Exception:
                    pass
                return

            entry = CacheEntry(
                key=key,
                filename=filename,
                size=len(audio_data),
                timestamp=self._now(),
                hits=0,
                compressed=self.compress,
                disk_size=disk_size,
                expires_at=self._compute_expiry(),
            )
            self._entries[key] = entry
            self._disk_usage += disk_size
            # 立即保存索引，避免数据丢失
            self._save_index()

    def clear(self) -> None:
        """清空缓存"""
        with self._lock:
            for entry in self._entries.values():
                try:
                    (self.audio_dir / entry.filename).unlink(missing_ok=True)
                except OSError:
                    pass
            self._entries.clear()
            self._disk_usage = 0
            try:
                if self.index_path.exists():
                    self.index_path.unlink()
            except OSError:
                pass
            self._stats = {k: 0 for k in self._stats}

    def stats(self) -> Dict[str, float]:
        """返回缓存统计数据"""
        with self._lock:
            total_size = sum(entry.size for entry in self._entries.values())
            return {
                "entries": len(self._entries),
                "max_entries": self.max_entries,
                "disk_usage": total_size,
                "disk_usage_bytes": self._disk_usage,
                "compress": self.compress,
                **self._stats,
            }

    # --------------------------------------------------------------------- #
    # 内部工具
    # --------------------------------------------------------------------- #
    def _evict_if_needed(self) -> None:
        if len(self._entries) > self.max_entries:
            self._cull(len(self._entries) - self.max_entries + 1)

        if self.max_disk_usage_bytes is not None and self._disk_usage > self.max_disk_usage_bytes:
            excess_bytes = self._disk_usage - self.max_disk_usage_bytes
            self._cull_bytes(excess_bytes)

    def _cull(self, remove_count: int) -> None:
        if remove_count <= 0:
            return
        sorted_entries = sorted(self._entries.values(), key=lambda item: item.timestamp)
        for entry in sorted_entries[:remove_count]:
            file_path = self.audio_dir / entry.filename
            self._remove_entry(file_path, entry)
            self._stats["evictions"] += 1

        self._save_index()

    def _cull_bytes(self, excess_bytes: int) -> None:
        if excess_bytes <= 0:
            return
        sorted_entries = sorted(self._entries.values(), key=lambda item: item.timestamp)
        removed = 0
        for entry in sorted_entries:
            if removed >= excess_bytes:
                break
            file_path = self.audio_dir / entry.filename
            removed += entry.disk_size
            self._remove_entry(file_path, entry)
            self._stats["evictions"] += 1

        self._save_index()

    def _remove_entry(self, file_path: Path, entry: CacheEntry) -> None:
        try:
            file_path.unlink(missing_ok=True)
        except OSError:
            pass
        self._entries.pop(entry.key, None)
        self._disk_usage = max(0, self._disk_usage - entry.disk_size)

    def _is_expired(self, entry: CacheEntry) -> bool:
        if entry.expires_at is None:
            return False
        return self._now() >= entry.expires_at

    def _compute_expiry(self) -> Optional[float]:
        if not self.ttl_seconds:
            return None
        return self._now() + self.ttl_seconds


__all__ = ["PersistentTTSAudioCache", "CacheEntry"]
