"""
TTS 初始化模块

在应用启动时初始化 TTS 服务，并进行健康检查。

版本：v3.4.0
日期：2025-11-22
优化：改进初始化逻辑、健康检查和错误处理
"""

import asyncio
import concurrent.futures
from typing import TYPE_CHECKING

from src.config.settings import load_settings
from src.utils.logger import logger

# 全局实例
_tts_manager = None
_tts_config = None
_tts_available = False

if TYPE_CHECKING:
    from src.multimodal.tts_manager import TTSConfig


async def _test_tts_service(tts_config: "TTSConfig") -> bool:
    """
    TTS 健康检查

    Args:
        tts_config: TTS 配置

    Returns:
        bool: TTS 服务是否可用
    """
    from src.multimodal.gpt_sovits_client import GPTSoVITSClient

    tts_client = GPTSoVITSClient(
        api_url=tts_config.api_url,
        timeout=tts_config.request_timeout,
        max_retries=max(1, int(tts_config.client_max_retries)),
        default_ref_audio_path=tts_config.ref_audio_path,
        default_ref_text=tts_config.ref_audio_text,
        default_text_lang=tts_config.text_lang,
        default_prompt_lang=tts_config.prompt_lang,
        connect_timeout=tts_config.connect_timeout,
        read_timeout=tts_config.read_timeout,
        write_timeout=tts_config.write_timeout,
        http2_enabled=tts_config.http2_enabled,
        pool_max_connections=tts_config.pool_max_connections,
        pool_max_keepalive_connections=tts_config.pool_max_keepalive_connections,
        pool_keepalive_expiry=tts_config.pool_keepalive_expiry,
        circuit_break_threshold=tts_config.circuit_break_threshold,
        circuit_break_cooldown=tts_config.circuit_break_cooldown,
    )

    try:
        is_available = await tts_client.check_health()

        if is_available:
            logger.debug("TTS 健康检查成功")
            return True
        else:
            logger.debug("TTS 健康检查失败")
            return False

    except Exception as e:
        logger.debug(f"TTS 健康检查异常: {e}")
        return False
    finally:
        await tts_client.close()


def init_tts() -> bool:
    """
    初始化 TTS 服务

    Returns:
        bool: 初始化是否成功
    """
    global _tts_manager, _tts_config, _tts_available

    try:
        # 加载配置
        settings = load_settings()

        # 检查 TTS 是否启用
        if not settings.tts.enabled:
            logger.info("TTS 功能未启用")
            return False

        logger.info("=" * 60)
        logger.info("🎤 初始化 GPT-SoVITS TTS 服务")
        logger.info("=" * 60)

        # 导入 TTS 模块
        try:
            from src.multimodal.tts_manager import TTSConfig, get_tts_manager
        except ImportError as e:
            logger.error(f"导入 TTS 模块失败: {e}")
            logger.error("请先执行: uv sync --locked --no-install-project")
            return False

        # 创建 TTS 配置
        _tts_config = TTSConfig(
            api_url=settings.tts.api_url,
            ref_audio_path=settings.tts.ref_audio_path,
            ref_audio_text=settings.tts.ref_audio_text,
            text_lang=settings.tts.text_lang,
            prompt_lang=settings.tts.prompt_lang,
            top_k=settings.tts.top_k,
            top_p=settings.tts.top_p,
            temperature=settings.tts.temperature,
            speed_factor=settings.tts.speed_factor,
            text_split_method=settings.tts.text_split_method,
            cache_enabled=True,
            cache_max_size=100,
            disk_cache_enabled=settings.tts.disk_cache_enabled,
            disk_cache_dir=settings.tts.disk_cache_dir,
            disk_cache_max_items=settings.tts.disk_cache_max_items,
            disk_cache_compress=settings.tts.disk_cache_compress,
            disk_cache_max_bytes=settings.tts.disk_cache_max_bytes,
            disk_cache_ttl_seconds=settings.tts.disk_cache_ttl_seconds,
            max_parallel_requests=settings.tts.max_parallel_requests,
            paragraph_min_sentence_length=settings.tts.paragraph_min_sentence_length,
            client_max_retries=settings.tts.client_max_retries,
            request_timeout=settings.tts.request_timeout,
            connect_timeout=settings.tts.connect_timeout,
            read_timeout=settings.tts.read_timeout,
            write_timeout=settings.tts.write_timeout,
            http2_enabled=settings.tts.http2_enabled,
            pool_max_connections=settings.tts.pool_max_connections,
            pool_max_keepalive_connections=settings.tts.pool_max_keepalive_connections,
            pool_keepalive_expiry=settings.tts.pool_keepalive_expiry,
            circuit_break_threshold=settings.tts.circuit_break_threshold,
            circuit_break_cooldown=settings.tts.circuit_break_cooldown,
        )

        logger.info("📋 TTS 配置:")
        logger.info(f"   API URL: {_tts_config.api_url}")
        logger.info(f"   文本语言: {_tts_config.text_lang}")
        logger.info(f"   参考音频: {_tts_config.ref_audio_path or '(默认)'}")
        logger.info(f"   缓存: {'启用' if _tts_config.cache_enabled else '禁用'}")
        if _tts_config.disk_cache_enabled:
            logger.info(
                "   磁盘缓存: 启用 (dir=%s, max=%d)",
                _tts_config.disk_cache_dir,
                _tts_config.disk_cache_max_items,
            )

        # 健康检查
        logger.info("🔍 检查 GPT-SoVITS 服务状态...")
        try:
            # 检查是否已有事件循环
            try:
                asyncio.get_running_loop()

                # 如果已有事件循环，在新线程中运行（避免阻塞当前事件循环）
                def run_in_new_loop():
                    """在新线程中创建新的事件循环并运行健康检查"""
                    new_loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(new_loop)
                    try:
                        return new_loop.run_until_complete(_test_tts_service(_tts_config))
                    finally:
                        new_loop.close()

                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(run_in_new_loop)
                    try:
                        is_available = future.result(timeout=10.0)  # 健康检查超时10秒
                    except concurrent.futures.TimeoutError:
                        logger.warning("TTS 健康检查超时（10秒），服务可能不可用")
                        is_available = False
                    except Exception as e:
                        logger.warning(f"TTS 健康检查线程执行失败: {e}")
                        is_available = False
            except RuntimeError:
                # 没有运行中的事件循环，直接使用 asyncio.run
                try:
                    is_available = asyncio.run(_test_tts_service(_tts_config))
                except Exception as e:
                    logger.warning(f"TTS 健康检查失败: {e}")
                    is_available = False

            _tts_available = is_available
            if is_available:
                logger.info("✅ GPT-SoVITS 服务可用")
            else:
                logger.warning("⚠️ GPT-SoVITS 服务不可用")
                logger.warning("   请确保已启动 GPT-SoVITS 服务")
        except Exception as e:
            logger.error(f"健康检查失败: {e}")
            _tts_available = False
            logger.warning("TTS 功能将在服务可用后自动启用")

        # 初始化 TTS 管理器（即使健康检查失败也初始化，允许后续重试）
        try:
            _tts_manager = get_tts_manager(_tts_config)
            logger.info("✅ TTS 管理器初始化成功")
        except Exception as e:
            logger.error(f"TTS 管理器初始化失败: {e}")
            _tts_manager = None
            _tts_available = False
            logger.info("=" * 60)
            return False

        logger.info("=" * 60)
        return True

    except Exception as e:
        logger.error(f"❌ TTS 初始化失败: {e}", exc_info=True)
        logger.info("=" * 60)
        return False


def get_tts_manager_instance():
    """
    获取 TTS 管理器实例

    Returns:
        TTSManager | None: TTS 管理器实例，如果未初始化则返回 None
    """
    return _tts_manager


def get_tts_config_instance():
    """
    获取 TTS 配置实例

    Returns:
        TTSConfig | None: TTS 配置实例，如果未初始化则返回 None
    """
    return _tts_config


def is_tts_available() -> bool:
    """
    检查 TTS 是否可用

    Returns:
        bool: TTS 是否可用
    """
    return _tts_available
