"""
GPT-SoVITS TTS 客户端模块

高性能异步 TTS 客户端，支持连接池复用、智能重试和错误处理。

版本：v3.4.0
日期：2025-11-22
优化：改进类型注解、错误处理、连接池管理和性能
"""

import asyncio
import time
from typing import Any, Dict, Optional, Tuple, Union

import httpx

from src.utils.logger import logger


class GPTSoVITSClient:
    """
    GPT-SoVITS TTS API 客户端

    性能优化：
    - 复用 AsyncClient 实例以共享连接池
    - 指数退避重试策略
    - 完整的类型注解
    - 详细的错误处理和日志
    """

    def __init__(
        self,
        api_url: str = "http://127.0.0.1:9880/tts",
        timeout: float = 30.0,
        max_retries: int = 3,
        default_ref_audio_path: Optional[str] = None,
        default_ref_text: Optional[str] = None,
        default_text_lang: str = "zh",
        default_prompt_lang: str = "zh",
        *,
        connect_timeout: float = 10.0,
        read_timeout: float = 30.0,
        write_timeout: float = 30.0,
        http2_enabled: bool = False,
        pool_max_connections: int = 10,
        pool_max_keepalive_connections: int = 5,
        pool_keepalive_expiry: float = 30.0,
        circuit_break_threshold: int = 4,
        circuit_break_cooldown: float = 15.0,
    ) -> None:
        """
        初始化 GPT-SoVITS 客户端

        Args:
            api_url: GPT-SoVITS API 地址
            timeout: 请求超时时间（秒）
            max_retries: 最大重试次数
            default_ref_audio_path: 默认参考音频路径
            default_ref_text: 默认参考文本
            default_text_lang: 默认文本语言
            default_prompt_lang: 默认提示语言
        """
        self.api_url: str = api_url
        self.timeout: float = timeout
        self.max_retries: int = max_retries
        self.default_ref_audio_path: Optional[str] = default_ref_audio_path
        self.default_ref_text: Optional[str] = default_ref_text
        self.default_text_lang: str = default_text_lang
        self.default_prompt_lang: str = default_prompt_lang

        # 性能优化：复用 AsyncClient 以共享连接池
        self._client: Optional[httpx.AsyncClient] = None
        self._client_loop: Optional[asyncio.AbstractEventLoop] = None
        self._loop_locks: Dict[int, Tuple[asyncio.AbstractEventLoop, asyncio.Lock]] = {}
        self._http2_enabled = bool(http2_enabled)
        # v3.4.0: 优化超时设置，确保所有超时参数合理
        # 如果read_timeout未设置或为0，使用总超时时间
        effective_read_timeout = read_timeout if read_timeout and read_timeout > 0 else timeout
        # 如果connect_timeout未设置或为0，使用较小的默认值
        effective_connect_timeout = connect_timeout if connect_timeout and connect_timeout > 0 else min(10.0, timeout)
        # 如果write_timeout未设置或为0，使用总超时时间
        effective_write_timeout = write_timeout if write_timeout and write_timeout > 0 else timeout
        
        self._timeout = httpx.Timeout(
            connect=effective_connect_timeout,
            read=effective_read_timeout,
            write=effective_write_timeout,
            pool=timeout,  # 连接池超时使用总超时
        )
        self._limits = httpx.Limits(
            max_keepalive_connections=max(0, int(pool_max_keepalive_connections)),
            max_connections=max(1, int(pool_max_connections)),
            keepalive_expiry=pool_keepalive_expiry,
        )
        # 传输层重试遵循 httpx 官方文档，避免瞬时连接抖动
        self._transport_retries = max(0, self.max_retries - 1)
        self._circuit_threshold = max(1, int(circuit_break_threshold))
        self._circuit_cooldown = max(1.0, float(circuit_break_cooldown))
        self._circuit_failure_count = 0
        self._circuit_open_until = 0.0
        self._circuit_lock = asyncio.Lock()  # 熔断器并发安全锁

        # 统计信息
        self._stats: Dict[str, Union[int, float]] = {
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "total_retries": 0,
            "total_latency_ms": 0.0,
            "last_latency_ms": 0.0,
            "circuit_open_events": 0,
            "circuit_short_circuits": 0,
        }

        logger.info(f"初始化 GPT-SoVITS 客户端: {api_url}")

    def _cleanup_stale_locks(self) -> None:
        stale_ids = [
            loop_id
            for loop_id, (loop, _) in self._loop_locks.items()
            if loop.is_closed()
        ]
        for loop_id in stale_ids:
            self._loop_locks.pop(loop_id, None)

    def _get_loop_lock(self, loop: asyncio.AbstractEventLoop) -> asyncio.Lock:
        """获取事件循环对应的锁（线程安全）"""
        self._cleanup_stale_locks()
        loop_id = id(loop)
        entry = self._loop_locks.get(loop_id)
        if entry is None or entry[0] is not loop:
            lock = asyncio.Lock()
            self._loop_locks[loop_id] = (loop, lock)
            return lock
        return entry[1]

    def _needs_new_client(self, loop: asyncio.AbstractEventLoop) -> bool:
        if self._client is None or self._client_loop is None:
            return True
        if self._client_loop is not loop:
            return True
        if hasattr(self._client_loop, "is_closed") and self._client_loop.is_closed():
            return True
        return False

    async def _safe_close_client(self) -> None:
        """v3.4.0: 安全关闭客户端（优化资源清理）"""
        if self._client is None:
            return
        try:
            # 检查客户端是否已经关闭
            if hasattr(self._client, "is_closed") and self._client.is_closed:
                self._client = None
                self._client_loop = None
                return
            
            # 关闭客户端（httpx 会自动清理连接池）
            await self._client.aclose()
        except RuntimeError as e:
            # 事件循环关闭导致的错误，静默处理
            error_str = str(e) or ""
            if "Event loop is closed" not in error_str and "cannot be called from a running event loop" not in error_str:
                logger.debug(f"关闭客户端时遇到RuntimeError: {e}")
        except Exception as e:
            # 其他关闭错误，静默处理，减少日志噪音
            error_str = str(e) or ""
            if "closed" not in error_str.lower() and "shutdown" not in error_str.lower():
                logger.debug(f"关闭客户端时遇到异常: {e}")
        finally:
            # v3.4.0: 确保清理引用，防止内存泄漏
            self._client = None
            self._client_loop = None
            # 清理过期的循环锁
            self._cleanup_stale_locks()

    async def _create_client(self, loop: asyncio.AbstractEventLoop) -> None:
        await self._safe_close_client()
        transport = httpx.AsyncHTTPTransport(
            retries=self._transport_retries,
            http2=self._http2_enabled,
        )
        self._client = httpx.AsyncClient(
            timeout=self._timeout,
            limits=self._limits,
            transport=transport,
            http2=self._http2_enabled,
        )
        self._client_loop = loop
        # 不记录客户端创建日志，减少日志输出

    async def _get_client(self) -> httpx.AsyncClient:
        """获取或创建 AsyncClient 实例（线程安全 + 事件循环自愈）"""
        current_loop = asyncio.get_running_loop()
        lock = self._get_loop_lock(current_loop)
        async with lock:
            if self._needs_new_client(current_loop):
                await self._create_client(current_loop)
        return self._client  # type: ignore[return-value]

    async def close(self) -> None:
        """v3.4.0: 关闭客户端连接（优化资源清理）"""
        await self._safe_close_client()
        # 清理所有循环锁引用
        self._loop_locks.clear()
        # 重置熔断器状态
        async with self._circuit_lock:
            self._circuit_failure_count = 0
            self._circuit_open_until = 0.0

    async def synthesize(
        self,
        text: str,
        ref_audio_path: str,
        ref_text: str,
        text_lang: str = "zh",
        prompt_lang: str = "zh",
        top_k: int = 5,
        top_p: float = 1.0,
        temperature: float = 1.0,
        speed_factor: float = 1.0,
        **kwargs: Any,
    ) -> Optional[bytes]:
        """
        调用 GPT-SoVITS API 进行语音合成

        Args:
            text: 要合成的文本
            ref_audio_path: 参考音频路径
            ref_text: 参考音频文本
            text_lang: 文本语言（zh/en/ja）
            prompt_lang: 提示语言
            top_k: Top-K 采样参数
            top_p: Top-P 采样参数
            temperature: 温度参数
            speed_factor: 语速因子
            **kwargs: 其他参数

        Returns:
            bytes: 合成的音频数据（WAV 格式），失败返回 None
        """
        # 验证文本有效性
        if not text or not text.strip():
            logger.debug("TTS 合成跳过：文本为空")
            return None
        
        # 去除首尾空白，但保留内部空白
        text = text.strip()
        
        self._stats["total_requests"] += 1
        start_time = time.time()

        if await self._is_circuit_open():
            async with self._circuit_lock:
                remaining = max(0.0, self._circuit_open_until - time.time())
            self._stats["failed_requests"] += 1
            self._stats["circuit_short_circuits"] += 1
            logger.warning(
                "TTS 客户端熔断中 (剩余 %.1fs)，跳过文本: %s",
                remaining,
                text[:30],
            )
            return None

        # 构建请求数据
        data: Dict[str, Any] = {
            "text": text,
            "text_lang": text_lang,
            "ref_audio_path": ref_audio_path,
            "prompt_text": ref_text,
            "prompt_lang": prompt_lang,
            "top_k": top_k,
            "top_p": top_p,
            "temperature": temperature,
            "speed_factor": speed_factor,
        }
        data.update(kwargs)

        # 智能重试逻辑（指数退避）
        # 根据文本长度动态调整超时时间（长文本需要更长时间处理）
        text_len = len(text) if text else 0
        # 基础超时 + 每100字符增加1秒，最大不超过60秒
        dynamic_read_timeout = min(
            self._timeout.read + (text_len / 100.0),
            60.0
        )
        dynamic_timeout = httpx.Timeout(
            connect=self._timeout.connect,
            read=dynamic_read_timeout,
            write=self._timeout.write,
            pool=self._timeout.pool,
        )
        
        failure_reason: Optional[str] = None
        for attempt in range(self.max_retries):
            try:
                # 每次重试前检查并获取客户端（可能已关闭需要重建）
                client = await self._get_client()
                
                # v3.4.0: 检查客户端健康状态
                if hasattr(client, "is_closed") and client.is_closed:
                    await self._safe_close_client()
                    client = await self._get_client()
                
                # v3.4.0: 优化连接池状态检查，避免反射访问内部属性
                # 连接池管理由 httpx 自动处理，无需手动干预
                
                # v3.4.0: 使用动态超时，根据文本长度调整
                response = await client.post(
                    self.api_url,
                    json=data,
                    timeout=dynamic_timeout,
                )

                if response.status_code == 200:
                    elapsed = time.time() - start_time
                    elapsed_ms = elapsed * 1000.0
                    # 检查响应内容是否为空
                    if not response.content or len(response.content) == 0:
                        # 空响应可能是文本太短或服务器处理问题，记录警告而非错误
                        if attempt == self.max_retries - 1:
                            logger.warning(
                                "TTS 合成返回空结果（文本: %.30s，可能是文本过短或服务器处理问题）",
                                text[:30] if text else "(空文本)"
                            )
                        failure_reason = "empty-response"
                        if attempt < self.max_retries - 1:
                            wait_time = 2 ** attempt
                            await asyncio.sleep(wait_time)
                            continue
                        break
                    
                    self._stats["successful_requests"] += 1
                    self._stats["last_latency_ms"] = elapsed_ms
                    self._stats["total_latency_ms"] += elapsed_ms
                    await self._record_success()
                    return response.content
                else:
                    # 仅在最后一次尝试失败时记录错误
                    if attempt == self.max_retries - 1:
                        logger.error(f"TTS 合成失败: HTTP {response.status_code}")
                        if response.text:
                            logger.error(f"响应: {response.text[:200]}")
                    failure_reason = f"HTTP {response.status_code}"
                    # 非 5xx 错误不重试
                    if response.status_code < 500:
                        break

            except httpx.TimeoutException:
                self._stats["total_retries"] += 1
                # 仅在最后一次尝试失败时记录警告，减少日志噪音
                if attempt == self.max_retries - 1:
                    logger.warning(f"TTS 请求超时 (已重试 {self.max_retries} 次)")
                failure_reason = "timeout"
                if attempt < self.max_retries - 1:
                    # 指数退避：1s, 2s, 4s...
                    wait_time = 2 ** attempt
                    await asyncio.sleep(wait_time)

            except httpx.ConnectError as e:
                self._stats["total_retries"] += 1
                # 仅在最后一次尝试失败时记录错误
                if attempt == self.max_retries - 1:
                    logger.error(f"TTS 连接失败: {e}")
                failure_reason = f"connect-error: {e}"
                # 连接错误时关闭客户端并重建
                await self._safe_close_client()
                if attempt < self.max_retries - 1:
                    wait_time = 2 ** attempt
                    await asyncio.sleep(wait_time)

            except httpx.ReadError as e:
                # v3.4.0: 优化错误信息处理，ReadError 通常是响应流中断，不一定是服务器断开
                self._stats["total_retries"] += 1
                error_str = str(e).strip() if e else f"响应读取中断（{type(e).__name__}）"
                if not error_str or error_str == "":
                    error_str = "响应读取中断（可能是网络波动或响应超时）"
                # ReadError 通常是瞬时问题，仅在最后一次尝试失败时记录警告（而非错误）
                if attempt == self.max_retries - 1:
                    logger.warning(f"TTS 响应读取中断: {error_str}（已重试 {self.max_retries} 次）")
                failure_reason = f"read-error: {error_str}"
                # ReadError 时不要立即关闭客户端，可能是瞬时网络问题
                # 仅在多次重试失败后才关闭客户端
                if attempt >= self.max_retries - 1:
                    await self._safe_close_client()
                if attempt < self.max_retries - 1:
                    wait_time = 2 ** attempt
                    await asyncio.sleep(wait_time)

            except httpx.WriteError as e:
                # v3.4.0: 优化错误信息处理
                self._stats["total_retries"] += 1
                error_str = str(e).strip() if e else f"连接写入错误（{type(e).__name__}）"
                if attempt == self.max_retries - 1:
                    logger.error(f"TTS 连接写入错误: {error_str}")
                failure_reason = f"write-error: {error_str}"
                await self._safe_close_client()
                if attempt < self.max_retries - 1:
                    wait_time = 2 ** attempt
                    await asyncio.sleep(wait_time)

            except httpx.PoolTimeout as e:
                # 处理连接池超时
                self._stats["total_retries"] += 1
                if attempt == self.max_retries - 1:
                    logger.warning(f"TTS 连接池超时: {e}")
                failure_reason = f"pool-timeout: {e}"
                if attempt < self.max_retries - 1:
                    wait_time = 2 ** attempt
                    await asyncio.sleep(wait_time)

            except Exception as e:
                # v3.4.0: 优化通用异常处理
                self._stats["total_retries"] += 1
                error_type = type(e).__name__
                error_str = str(e).strip() if e else f"{error_type}（连接异常）"
                
                # 检查是否是连接相关的错误
                is_loop_closed = isinstance(e, RuntimeError) and "Event loop is closed" in error_str
                is_client_closed = (
                    "client has been closed" in error_str 
                    or "Cannot send a request" in error_str
                    or "Connection closed" in error_str
                )
                
                if is_loop_closed or is_client_closed:
                    # 连接相关错误，重建客户端
                    await self._safe_close_client()
                    failure_reason = f"connection-error: {error_type}"
                    if attempt < self.max_retries - 1:
                        await asyncio.sleep(0.1)  # 短暂等待后重试
                    continue
                else:
                    # 仅在最后一次尝试失败时记录错误
                    if attempt == self.max_retries - 1:
                        logger.error(
                            "TTS 合成异常 [%s]: %s",
                            error_type,
                            error_str[:200],
                            exc_info=False,
                        )
                    failure_reason = f"{error_type}: {error_str[:100]}"
                    if attempt < self.max_retries - 1:
                        wait_time = 2 ** attempt
                        await asyncio.sleep(wait_time)

        self._stats["failed_requests"] += 1
        await self._record_failure()
        # 统一记录最终失败信息，避免重复日志
        logger.error(
            "TTS 合成失败（已重试 %d 次）: %s",
            self.max_retries,
            failure_reason or "未知错误",
        )
        return None
    
    async def check_health(self) -> bool:
        """
        检查 GPT-SoVITS 服务是否可用

        使用轻量级 POST 请求测试 /tts 接口连通性。

        Returns:
            bool: 服务是否可用
        """
        try:
            data: Dict[str, Any] = {
                "text": "测试",
                "text_lang": self.default_text_lang,
                "ref_audio_path": self.default_ref_audio_path or "",
                "prompt_text": self.default_ref_text or "",
                "prompt_lang": self.default_prompt_lang,
                "top_k": 1,
                "top_p": 1.0,
                "temperature": 1.0,
                "speed_factor": 1.0,
            }

            client = await self._get_client()
            response = await client.post(
                self.api_url,
                json=data,
                timeout=5.0,  # 健康检查使用较短超时
            )

            if response.status_code == 200:
                # 健康检查成功，重置熔断器
                await self._record_success()
                return True
            else:
                # 健康检查失败，不记录日志（健康检查失败不应影响正常请求）
                return False

        except Exception as e:
            # 健康检查异常，不记录日志，避免日志噪音
            return False

    def get_stats(self) -> Dict[str, Union[int, float]]:
        """
        获取客户端统计信息

        Returns:
            Dict[str, int]: 统计信息字典
        """
        stats = self._stats.copy()
        successful = stats.get("successful_requests", 0) or 0
        stats["avg_latency_ms"] = (
            stats["total_latency_ms"] / successful if successful else 0.0
        )
        return stats

    def reset_stats(self) -> None:
        """重置统计信息"""
        self._stats = {
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "total_retries": 0,
            "total_latency_ms": 0.0,
            "last_latency_ms": 0.0,
            "circuit_open_events": 0,
            "circuit_short_circuits": 0,
        }
        # 不记录统计信息重置日志

    # ------------------------------------------------------------------ #
    # 熔断器
    # ------------------------------------------------------------------ #
    async def _is_circuit_open(self) -> bool:
        async with self._circuit_lock:
            if self._circuit_open_until <= 0:
                return False
            now = time.time()
            if now >= self._circuit_open_until:
                self._circuit_open_until = 0.0
                self._circuit_failure_count = 0
                return False
            return True

    async def _record_success(self) -> None:
        async with self._circuit_lock:
            self._circuit_failure_count = 0
            self._circuit_open_until = 0.0

    async def _record_failure(self) -> None:
        async with self._circuit_lock:
            self._circuit_failure_count += 1
            if self._circuit_failure_count < self._circuit_threshold:
                return

            self._circuit_failure_count = 0
            self._circuit_open_until = time.time() + self._circuit_cooldown
            self._stats["circuit_open_events"] += 1
            logger.warning(
                "TTS 客户端触发熔断：未来 %.1fs 内不再向 GPT-SoVITS 发起请求",
                self._circuit_cooldown,
            )

