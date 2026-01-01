"""
TTS 管理器模块

提供 TTS 任务队列管理、文本处理、音频合成和缓存功能。

版本：v3.4.0
日期：2025-11-22
优化：改进类型注解、缓存机制、异步处理和代码结构
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

from src.multimodal.gpt_sovits_client import GPTSoVITSClient
from src.multimodal.tts_cache import PersistentTTSAudioCache
from src.utils.stream_processor import StreamProcessor
from src.utils.logger import logger


@dataclass
class TTSConfig:
    """TTS 配置数据类"""

    api_url: str = "http://127.0.0.1:9880/tts"
    ref_audio_path: str = ""
    ref_audio_text: str = ""
    text_lang: str = "zh"
    prompt_lang: str = "zh"
    top_k: int = 5
    top_p: float = 1.0
    temperature: float = 1.0
    speed_factor: float = 1.0
    text_split_method: str = "cut0"  # GPT-SoVITS 文本切分策略（默认不切分，由前端控制）
    batch_size: int = 1
    seed: int = -1
    cache_enabled: bool = True  # 是否启用缓存
    cache_max_size: int = 100  # 缓存最大条目数
    disk_cache_enabled: bool = True
    disk_cache_dir: str = "data/tts_cache"
    disk_cache_max_items: int = 400
    disk_cache_max_bytes: int = 0
    disk_cache_compress: bool = True
    disk_cache_ttl_seconds: float = 0.0
    max_parallel_requests: int = 2
    paragraph_min_sentence_length: int = 8
    client_max_retries: int = 3
    request_timeout: float = 30.0
    connect_timeout: float = 10.0
    read_timeout: float = 30.0
    write_timeout: float = 30.0
    http2_enabled: bool = False
    pool_max_connections: int = 10
    pool_max_keepalive_connections: int = 5
    pool_keepalive_expiry: float = 30.0
    circuit_break_threshold: int = 4
    circuit_break_cooldown: float = 15.0


@dataclass
class AgentSpeechProfile:
    """面向智能体的情感语音参数"""

    mood_value: float = 0.0  # -1.0 (低落) ~ 1.0 (兴奋)
    energy: float = 0.0  # -1.0 (低沉) ~ 1.0 (活力)
    persona: str = ""  # 角色名称，用于日志和可选 voice tag
    speaking_style: str = ""  # 语音风格提示词
    emphasis: Optional[str] = None  # 额外强调的情绪，如 "撒娇"、"认真"


class TTSManager:
    """
    TTS 管理器

    负责管理 TTS 任务队列、文本预处理、音频合成和缓存。

    性能优化：
    - LRU 缓存机制减少重复合成
    - 改进的文本预处理
    - 完整的类型注解
    """

    def __init__(self, config: TTSConfig) -> None:
        """
        初始化 TTS 管理器

        Args:
            config: TTS 配置
        """
        self.config: TTSConfig = config
        self.client: GPTSoVITSClient = GPTSoVITSClient(
            api_url=config.api_url,
            timeout=config.request_timeout,
            max_retries=max(1, int(config.client_max_retries)),
            default_ref_audio_path=config.ref_audio_path,
            default_ref_text=config.ref_audio_text,
            default_text_lang=config.text_lang,
            default_prompt_lang=config.prompt_lang,
            connect_timeout=config.connect_timeout,
            read_timeout=config.read_timeout,
            write_timeout=config.write_timeout,
            http2_enabled=config.http2_enabled,
            pool_max_connections=config.pool_max_connections,
            pool_max_keepalive_connections=config.pool_max_keepalive_connections,
            pool_keepalive_expiry=config.pool_keepalive_expiry,
            circuit_break_threshold=config.circuit_break_threshold,
            circuit_break_cooldown=config.circuit_break_cooldown,
        )
        self._running: bool = False

        # 音频缓存（使用字典实现 LRU）
        self._cache: Dict[str, bytes] = {}
        self._cache_order: list[str] = []  # 记录访问顺序
        self._cache_enabled: bool = config.cache_enabled
        self._cache_max_size: int = config.cache_max_size

        # 磁盘缓存
        self._disk_cache: Optional[PersistentTTSAudioCache] = None
        if config.disk_cache_enabled:
            cache_dir = Path(config.disk_cache_dir).expanduser()
            self._disk_cache = PersistentTTSAudioCache(
                root_dir=cache_dir,
                max_entries=config.disk_cache_max_items,
                max_disk_usage_bytes=(config.disk_cache_max_bytes or None),
                compress=config.disk_cache_compress,
                ttl_seconds=(config.disk_cache_ttl_seconds or None),
            )
            logger.info(
                "TTS 磁盘缓存启用: dir=%s, 最大条目=%d",
                cache_dir,
                config.disk_cache_max_items,
            )

        # 统计信息
        self._stats: Dict[str, int] = {
            "total_synthesize": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "inflight_waits": 0,
        }

        self._inflight_futures: Dict[str, asyncio.Future] = {}
        self._inflight_lock = asyncio.Lock()
        self._cache_lock = asyncio.Lock()  # 内存缓存并发安全锁（异步）
        self._cache_thread_lock = threading.Lock()  # 内存缓存线程安全锁（同步）
        self._parallel_semaphore = asyncio.Semaphore(max(1, int(config.max_parallel_requests)))

        logger.info(f"初始化 TTS 管理器: {config.api_url}")
        if self._cache_enabled:
            logger.info(f"TTS 缓存已启用 (最大 {self._cache_max_size} 条)")

    @staticmethod
    def preprocess_text(text: str) -> str:
        """预处理文本（保留全部语义内容）

        仅做轻量级清洗：
        - 去除零宽字符等不可见控制符
        - 统一空白为单个空格，保留句内/句间空格

        Args:
            text: 原始文本

        Returns:
            str: 处理后的文本
        """
        if not text:
            return ""

        # 去除零宽字符和不可见控制符
        for ch in ("\u200b", "\u200c", "\u200d"):
            text = text.replace(ch, "")

        # 将全角空格替换为半角空格
        text = text.replace("\u3000", " ")

        # 压缩连续空白为单个空格，保留句内空格
        text = re.sub(r"\s+", " ", text).strip()

        # 不记录文本预处理日志，减少日志输出

        return text

    def _generate_cache_key(
        self,
        text: str,
        ref_audio_path: str,
        ref_text: str,
        **params: Any,
    ) -> str:
        """
        生成缓存键

        Args:
            text: 文本
            ref_audio_path: 参考音频路径
            ref_text: 参考文本
            **params: 其他参数

        Returns:
            str: 缓存键（MD5 哈希）
        """
        # 将所有参数组合成字符串
        params_fingerprint = self._serialize_cache_params(params)
        payload = {
            "text": text,
            "ref_audio_path": ref_audio_path or "",
            "ref_text": ref_text or "",
            "params": params_fingerprint,
        }
        key_str = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.md5(key_str.encode("utf-8")).hexdigest()

    @staticmethod
    def _serialize_cache_params(params: Dict[str, Any]) -> str:
        """将 TTS 参数规范化后序列化，确保不同参数组合不会互相命中缓存。"""
        normalized: Dict[str, Any] = {}
        for key in sorted(params.keys()):
            value = params[key]
            if isinstance(value, float):
                normalized[key] = round(value, 6)
            elif isinstance(value, (list, dict)):
                normalized[key] = value
            else:
                normalized[key] = str(value)
        return json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    async def _get_from_cache(self, cache_key: str) -> Optional[bytes]:
        """从缓存获取音频数据（并发安全，支持内存和磁盘两级缓存）"""
        if not self._cache_enabled:
            return None

        # 先检查内存缓存
        async with self._cache_lock:
            if cache_key in self._cache:
                # 更新访问顺序（移到最后）
                if cache_key in self._cache_order:
                    self._cache_order.remove(cache_key)
                self._cache_order.append(cache_key)
                self._stats["cache_hits"] += 1
                return self._cache[cache_key]

        # 尝试从磁盘缓存恢复（磁盘缓存本身是线程安全的）
        # 注意：磁盘缓存操作是同步的，需要在异步锁外执行，避免阻塞事件循环
        if self._disk_cache is not None:
            try:
                loop = asyncio.get_running_loop()
                disk_audio = await loop.run_in_executor(None, self._disk_cache.get, cache_key)
                if disk_audio is not None:
                    self._stats["cache_hits"] += 1
                    # 回灌到内存缓存，以加快后续访问
                    if self._cache_enabled:
                        async with self._cache_lock:
                            # 如果缓存已满，先移除最旧的条目
                            if len(self._cache) >= self._cache_max_size:
                                if self._cache_order:
                                    oldest_key = self._cache_order.pop(0)
                                    del self._cache[oldest_key]
                            self._cache[cache_key] = disk_audio
                            self._cache_order.append(cache_key)
                    return disk_audio
            except Exception as e:
                # 磁盘缓存读取失败，不影响主流程
                logger.debug(f"从磁盘缓存读取失败: {e}")

        self._stats["cache_misses"] += 1
        return None

    async def _add_to_cache(self, cache_key: str, audio_data: bytes) -> None:
        """添加音频数据到缓存（并发安全，支持内存和磁盘两级缓存）"""
        if not self._cache_enabled or not audio_data:
            return

        # 写入内存缓存
        async with self._cache_lock:
            # 如果缓存已满，移除最旧的条目
            if len(self._cache) >= self._cache_max_size:
                if self._cache_order:
                    oldest_key = self._cache_order.pop(0)
                    del self._cache[oldest_key]
            self._cache[cache_key] = audio_data
            self._cache_order.append(cache_key)

        # 异步写入磁盘缓存（避免阻塞事件循环）
        if self._disk_cache is not None:
            try:
                # 使用线程池执行同步的磁盘写入操作
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(
                    None,
                    self._disk_cache.set,
                    cache_key,
                    audio_data,
                )
            except Exception as e:
                # 磁盘缓存写入失败，不影响主流程
                logger.debug(f"写入磁盘缓存失败: {e}")

    @staticmethod
    def _clamp(value: float, min_value: float, max_value: float) -> float:
        return max(min_value, min(max_value, value))

    def _apply_agent_profile(
        self, params: Dict[str, Any], profile: Optional[AgentSpeechProfile]
    ) -> None:
        """根据智能体的情绪 / 语气调整 TTS 采样参数"""
        if profile is None:
            return

        mood = self._clamp(profile.mood_value, -1.0, 1.0)
        energy = self._clamp(profile.energy, -1.0, 1.0)

        base_speed = float(params.get("speed_factor", self.config.speed_factor))
        speed_delta = 0.12 * mood + 0.08 * energy
        params["speed_factor"] = round(self._clamp(base_speed + speed_delta, 0.6, 1.5), 3)

        base_temperature = float(params.get("temperature", self.config.temperature))
        temp_delta = 0.15 * energy
        params["temperature"] = round(self._clamp(base_temperature + temp_delta, 0.6, 1.5), 3)

        # 轻微调节 top_p/top_k，保证兴奋语气更具随机性
        base_top_p = float(params.get("top_p", self.config.top_p))
        params["top_p"] = round(self._clamp(base_top_p + 0.1 * mood, 0.6, 1.0), 3)

        base_top_k = int(params.get("top_k", self.config.top_k))
        params["top_k"] = max(1, min(10, base_top_k + int(energy * 2)))

        if profile.speaking_style:
            params.setdefault("style", profile.speaking_style)
        if profile.emphasis:
            params.setdefault("emphasis", profile.emphasis)
        if profile.persona:
            params.setdefault("voice_name", profile.persona)

    async def synthesize_text(
        self,
        text: str,
        ref_audio_path: Optional[str] = None,
        ref_text: Optional[str] = None,
        agent_profile: Optional[AgentSpeechProfile] = None,
        **kwargs: Any,
    ) -> Optional[bytes]:
        """
        合成单个文本（支持缓存）

        Args:
            text: 要合成的文本
            ref_audio_path: 参考音频路径（可选，默认使用配置中的）
            ref_text: 参考音频文本（可选，默认使用配置中的）
            agent_profile: 智能体语音风格 / 情绪配置
            **kwargs: 其他参数

        Returns:
            bytes: 合成的音频数据，失败返回 None
        """
        self._stats["total_synthesize"] += 1

        # 预处理文本
        processed_text = self.preprocess_text(text)

        # 检查文本是否为空
        if not processed_text:
            logger.warning(f"文本预处理后为空: {text}")
            return None

        # 使用配置中的参考音频（如果未指定）
        if ref_audio_path is None:
            ref_audio_path = self.config.ref_audio_path
        if ref_text is None:
            ref_text = self.config.ref_audio_text

        # 构建参数（默认使用前端已切好的句子，因此强制使用 GPT-SoVITS 的 cut0 不切分策略）
        params: Dict[str, Any] = {
            "text_lang": self.config.text_lang,
            "prompt_lang": self.config.prompt_lang,
            "top_k": self.config.top_k,
            "top_p": self.config.top_p,
            "temperature": self.config.temperature,
            "speed_factor": self.config.speed_factor,
            # 明确告知 GPT-SoVITS 不再二次切句，避免丢失文本
            "text_split_method": getattr(self.config, "text_split_method", "cut0"),
        }
        params.update(kwargs)
        self._apply_agent_profile(params, agent_profile)

        # 生成缓存键
        cache_key = self._generate_cache_key(
            processed_text,
            ref_audio_path,
            ref_text,
            **params,
        )

        # 尝试从缓存获取
        cached_audio = await self._get_from_cache(cache_key)
        if cached_audio is not None:
            return cached_audio

        return await self._synthesize_with_dedup(
            cache_key=cache_key,
            text=processed_text,
            ref_audio_path=ref_audio_path,
            ref_text=ref_text,
            params=params,
        )

    async def synthesize_sentences(
        self,
        sentences: Sequence[str],
        *,
        ref_audio_path: Optional[str] = None,
        ref_text: Optional[str] = None,
        agent_profile: Optional[AgentSpeechProfile] = None,
        shared_kwargs: Optional[Dict[str, Any]] = None,
    ) -> list[Optional[bytes]]:
        """
        批量合成多句文本，适用于智能体在生成整段台词时的预取。

        Args:
            sentences: 需要合成的句子列表
            ref_audio_path: 自定义参考音频
            ref_text: 自定义参考文本
            agent_profile: 智能体情绪 / 语气配置
            shared_kwargs: 共享给 synthesize_text 的其他参数

        Returns:
            list[Optional[bytes]]: 与 sentences 一一对应的音频字节数组
        """
        extra = shared_kwargs or {}
        if not sentences:
            return []

        semaphore = self._parallel_semaphore
        results: list[Optional[bytes]] = [None] * len(sentences)

        async def _worker(idx: int, sentence: str) -> None:
            # 跳过空句子，但处理所有非空句子（包括短句子）
            if not sentence or not sentence.strip():
                logger.debug(f"跳过空句子（索引 {idx}）")
                return
            async with semaphore:
                results[idx] = await self.synthesize_text(
                    sentence,
                    ref_audio_path=ref_audio_path,
                    ref_text=ref_text,
                    agent_profile=agent_profile,
                    **extra,
                )

        await asyncio.gather(*[_worker(idx, sentence) for idx, sentence in enumerate(sentences)])
        return results

    async def synthesize_paragraph(
        self,
        text: str,
        *,
        ref_audio_path: Optional[str] = None,
        ref_text: Optional[str] = None,
        agent_profile: Optional[AgentSpeechProfile] = None,
        min_sentence_length: Optional[int] = None,
        shared_kwargs: Optional[Dict[str, Any]] = None,
    ) -> list[Optional[bytes]]:
        """
        将整段文本按 StreamProcessor 切分后批量合成。

        Args:
            text: 原始整段文本
            ref_audio_path: 自定义参考音频
            ref_text: 自定义参考文本
            agent_profile: 智能体情绪/语气配置
            min_sentence_length: 自定义分句最小长度（为空则取配置）
            shared_kwargs: 额外透传给 synthesize_text 的参数
        """
        processor = StreamProcessor(
            min_sentence_length=(min_sentence_length or self.config.paragraph_min_sentence_length)
        )
        sentences = list(processor.process_chunk(text))
        # flush 时输出所有剩余内容，确保开头结尾的文本不会被丢失
        remaining = processor.flush()
        if remaining and remaining.strip():
            sentences.append(remaining)
            logger.debug(f"flush 添加剩余文本: {remaining[:30]}...")

        return await self.synthesize_sentences(
            sentences,
            ref_audio_path=ref_audio_path,
            ref_text=ref_text,
            agent_profile=agent_profile,
            shared_kwargs=shared_kwargs,
        )

    async def check_service(self) -> bool:
        """
        检查 TTS 服务是否可用

        Returns:
            bool: 服务是否可用
        """
        return await self.client.check_health()

    async def clear_cache(self) -> None:
        """清空缓存（并发安全）"""
        async with self._cache_lock:
            self._cache.clear()
            self._cache_order.clear()
        if self._disk_cache is not None:
            try:
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(None, self._disk_cache.clear)
            except Exception as e:
                logger.debug(f"清空磁盘缓存失败: {e}")
        logger.info("TTS 缓存已清空")

    def get_stats(self) -> Dict[str, Any]:
        """
        获取统计信息（并发安全，支持同步和异步调用）

        Returns:
            Dict[str, Any]: 统计信息
        """
        stats = self._stats.copy()
        # 使用线程锁，支持同步和异步调用
        with self._cache_thread_lock:
            stats["cache_size"] = len(self._cache)
        client_stats = self.client.get_stats()
        stats["client_stats"] = client_stats

        # GUI 兼容字段（部分面板依赖扁平字段）
        stats.setdefault("total_requests", int(client_stats.get("total_requests", 0) or 0))
        stats.setdefault(
            "successful_requests", int(client_stats.get("successful_requests", 0) or 0)
        )
        stats.setdefault("failed_requests", int(client_stats.get("failed_requests", 0) or 0))
        stats.setdefault("retry_count", int(client_stats.get("total_retries", 0) or 0))
        stats.setdefault("timeout_errors", 0)
        stats.setdefault("network_errors", 0)
        stats.setdefault("api_errors", 0)
        stats.setdefault("queue_size", 0)
        if self._disk_cache is not None:
            stats["disk_cache"] = self._disk_cache.stats()
        # inflight_futures 主要在异步环境中使用，使用线程锁也安全
        with self._cache_thread_lock:
            stats["inflight_active"] = len(self._inflight_futures)

        # 计算缓存命中率
        total_requests = stats["cache_hits"] + stats["cache_misses"]
        if total_requests > 0:
            stats["cache_hit_rate"] = stats["cache_hits"] / total_requests
        else:
            stats["cache_hit_rate"] = 0.0

        return stats

    async def _synthesize_with_dedup(
        self,
        *,
        cache_key: str,
        text: str,
        ref_audio_path: str,
        ref_text: str,
        params: Dict[str, Any],
    ) -> Optional[bytes]:
        future, is_owner = await self._get_or_create_inflight(cache_key)
        if not is_owner:
            # 等待其他正在进行的相同请求完成
            try:
                return await future
            except Exception:
                # 如果其他请求失败，返回None，不抛出异常
                return None

        try:
            audio_data = await self.client.synthesize(
                text=text,
                ref_audio_path=ref_audio_path,
                ref_text=ref_text,
                **params,
            )
            if audio_data is not None:
                await self._add_to_cache(cache_key, audio_data)
            # 确保future被设置（无论成功还是失败）
            if not future.done():
                future.set_result(audio_data)
            return audio_data
        except Exception as exc:
            # 确保 future 被设置，避免其他等待者永远等待
            if not future.done():
                try:
                    future.set_exception(exc)
                except Exception:
                    # future可能已经被设置或取消，忽略
                    pass
            # 不重新抛出异常，让调用者处理 None 返回值
            # 客户端已经记录了错误日志，这里不需要重复记录
            return None
        finally:
            await self._release_inflight(cache_key, future)

    async def _get_or_create_inflight(self, cache_key: str) -> tuple[asyncio.Future, bool]:
        async with self._inflight_lock:
            future = self._inflight_futures.get(cache_key)
            if future is None:
                loop = asyncio.get_running_loop()
                future = loop.create_future()
                self._inflight_futures[cache_key] = future
                return future, True
            self._stats["inflight_waits"] += 1
            return future, False

    async def _release_inflight(self, cache_key: str, future: asyncio.Future) -> None:
        """释放正在进行的请求（并发安全）"""
        async with self._inflight_lock:
            current = self._inflight_futures.get(cache_key)
            if current is future:
                self._inflight_futures.pop(cache_key, None)
            # 如果future未完成且未被取消，确保它被清理（防止内存泄漏）
            elif current is not None and not current.done() and not current.cancelled():
                # 如果future不是当前future，说明有新的请求，保留新的
                pass

    async def close(self) -> None:
        """v3.4.0: 关闭 TTS 管理器（优化资源清理）"""
        # 1. 取消所有未完成的inflight请求
        async with self._inflight_lock:
            for cache_key, future in list(self._inflight_futures.items()):
                if not future.done() and not future.cancelled():
                    try:
                        future.cancel()
                    except Exception:
                        pass
            self._inflight_futures.clear()

        # 2. 关闭客户端
        try:
            await self.client.close()
        except Exception as e:
            logger.warning(f"关闭TTS客户端时出错: {e}")

        # 3. 清空缓存
        try:
            await self.clear_cache()
        except Exception as e:
            logger.warning(f"清空TTS缓存时出错: {e}")

        self._running = False
        logger.info("TTS 管理器已关闭")


# 全局 TTS 管理器实例
_tts_manager: Optional[TTSManager] = None


def get_tts_manager(config: Optional[TTSConfig] = None) -> TTSManager:
    """
    获取 TTS 管理器单例

    Args:
        config: TTS 配置（首次调用时必须提供）

    Returns:
        TTSManager: TTS 管理器实例

    Raises:
        ValueError: 首次调用时未提供配置
    """
    global _tts_manager

    if _tts_manager is None:
        if config is None:
            raise ValueError("首次调用 get_tts_manager() 必须提供 config 参数")
        _tts_manager = TTSManager(config)

    return _tts_manager
