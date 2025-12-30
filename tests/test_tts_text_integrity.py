"""TTS 文本完整性与分句行为测试

这些测试只验证本地文本处理链路（StreamProcessor 与 TTSManager），
不依赖真正的 GPT-SoVITS 服务，用于防止丢字/错误切句。
"""

import asyncio
from unittest.mock import AsyncMock

from src.utils.stream_processor import StreamProcessor
from src.multimodal.tts_cache import PersistentTTSAudioCache
from src.multimodal.tts_manager import AgentSpeechProfile, TTSConfig, TTSManager


SAMPLE_TEXT = """（（立刻扑进主人怀里，幸福地蹭蹭）喵~最喜欢和主人贴贴了！（用毛茸茸的脑袋轻蹭主人的脸颊）主人的怀抱最温暖了喵~）"""


def _strip_spaces(text: str) -> str:
    """辅助函数：移除所有空白，用于对比文本内容是否一致"""
    return "".join(text.split())


def test_stream_processor_text_integrity_for_complex_sentence() -> None:
    """复杂括号 + 拟声词场景下，StreamProcessor 不应丢字。

    逐字符喂入 SAMPLE_TEXT，收集 process_chunk + flush 的所有输出，
    拼接后应与原文在去除空白后完全一致。
    """

    processor = StreamProcessor(min_sentence_length=3, max_buffer_size=500)

    sentences: list[str] = []
    for ch in SAMPLE_TEXT:
        for sentence in processor.process_chunk(ch):
            sentences.append(sentence)

    remaining = processor.flush()
    if remaining:
        sentences.append(remaining)

    reconstructed = "".join(sentences)

    assert _strip_spaces(reconstructed) == _strip_spaces(SAMPLE_TEXT)


async def _run_ttsmanager_synthesize() -> None:
    """验证 TTSManager 调用 GPT-SoVITS 时使用 cut0 且不修改语义文本。"""

    # 使用最小化配置，重点验证 text 与 text_split_method
    config = TTSConfig(
        api_url="http://127.0.0.1:9880/tts",
        ref_audio_path="",
        ref_audio_text="",
        text_lang="zh",
        prompt_lang="zh",
        disk_cache_enabled=False,
    )

    manager = TTSManager(config)

    # 使用 AsyncMock 替代真实 GPT-SoVITS 客户端，避免真实网络调用
    dummy_client = type("DummyClient", (), {})()
    dummy_client.synthesize = AsyncMock(return_value=b"FAKE_AUDIO")
    dummy_client.check_health = AsyncMock(return_value=True)
    dummy_client.get_stats = lambda: {}
    dummy_client.close = AsyncMock()

    manager.client = dummy_client  # 注入假的客户端

    audio = await manager.synthesize_text(SAMPLE_TEXT)

    # 应该返回我们设定的伪造音频数据
    assert audio == b"FAKE_AUDIO"

    # 验证 synthesize 被正确调用
    dummy_client.synthesize.assert_awaited_once()
    _, kwargs = dummy_client.synthesize.call_args

    # 文本应为预处理后的 SAMPLE_TEXT
    expected_text = TTSManager.preprocess_text(SAMPLE_TEXT)
    assert kwargs["text"] == expected_text

    # text_split_method 应默认使用 cut0（由前端控制分句）
    assert kwargs.get("text_split_method") == "cut0"


def test_ttsmanager_uses_cut0_and_preserves_text() -> None:
    """同步入口：运行异步测试协程。"""

    asyncio.run(_run_ttsmanager_synthesize())


async def _run_disk_cache_roundtrip(tmp_path) -> None:
    """验证磁盘缓存可在新的管理器实例中复用。"""

    base_config = TTSConfig(
        api_url="http://127.0.0.1:9880/tts",
        disk_cache_enabled=True,
        disk_cache_dir=str(tmp_path),
    )

    # 第一次合成，写入磁盘缓存
    manager_first = TTSManager(base_config)
    dummy_client = type("DummyClient", (), {})()
    dummy_client.synthesize = AsyncMock(return_value=b"PERSIST_AUDIO")
    dummy_client.check_health = AsyncMock(return_value=True)
    dummy_client.get_stats = lambda: {}
    dummy_client.close = AsyncMock()
    manager_first.client = dummy_client
    await manager_first.synthesize_text("磁盘缓存测试")

    # 第二个实例，确保直接命中磁盘缓存而不触发 synthesize
    manager_second = TTSManager(base_config)
    dummy_client_second = type("DummyClient", (), {})()
    dummy_client_second.synthesize = AsyncMock(
        side_effect=AssertionError("不应在命中磁盘缓存时触发远程合成")
    )
    dummy_client_second.check_health = AsyncMock(return_value=True)
    dummy_client_second.get_stats = lambda: {}
    dummy_client_second.close = AsyncMock()
    manager_second.client = dummy_client_second

    audio = await manager_second.synthesize_text("磁盘缓存测试")
    assert audio == b"PERSIST_AUDIO"


def test_ttsmanager_disk_cache_persistence(tmp_path) -> None:
    """同步运行磁盘缓存测试"""

    asyncio.run(_run_disk_cache_roundtrip(tmp_path))


async def _run_agent_profile_adjustment() -> None:
    """验证 AgentSpeechProfile 会调节参数"""

    config = TTSConfig(
        api_url="http://127.0.0.1:9880/tts",
        disk_cache_enabled=False,
    )
    manager = TTSManager(config)
    dummy_client = type("DummyClient", (), {})()
    dummy_client.synthesize = AsyncMock(return_value=b"PROFILE_AUDIO")
    dummy_client.check_health = AsyncMock(return_value=True)
    dummy_client.get_stats = lambda: {}
    dummy_client.close = AsyncMock()
    manager.client = dummy_client

    profile = AgentSpeechProfile(
        mood_value=0.8,
        energy=0.6,
        persona="测试猫娘",
        speaking_style="撒娇",
        emphasis="亲昵",
    )

    await manager.synthesize_text("情绪调节测试", agent_profile=profile)
    kwargs = dummy_client.synthesize.call_args.kwargs

    assert kwargs["speed_factor"] > config.speed_factor
    assert kwargs["temperature"] > config.temperature
    assert kwargs["voice_name"] == "测试猫娘"
    assert kwargs["style"] == "撒娇"
    assert kwargs["emphasis"] == "亲昵"


def test_agent_profile_adjustment() -> None:
    asyncio.run(_run_agent_profile_adjustment())


class _FakeClock:
    def __init__(self) -> None:
        self.now = 1_000.0

    def time(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def test_disk_cache_respects_ttl(tmp_path) -> None:
    """磁盘缓存超过 TTL 后应自动过期并记录统计。"""

    fake_clock = _FakeClock()
    cache = PersistentTTSAudioCache(
        root_dir=tmp_path,
        max_entries=10,
        ttl_seconds=5,
        compress=False,
        time_provider=fake_clock.time,
    )

    cache.set("ttl-key", b"HELLO")
    assert cache.get("ttl-key") == b"HELLO"

    fake_clock.advance(10)
    assert cache.get("ttl-key") is None

    stats = cache.stats()
    assert stats["expired"] == 1


async def _run_inflight_deduplication() -> None:
    """同一文本的并发请求应只触发一次远程合成。"""

    config = TTSConfig(
        api_url="http://127.0.0.1:9880/tts",
        disk_cache_enabled=False,
    )
    manager = TTSManager(config)

    gate = asyncio.Event()

    async def _delayed_synthesize(*args, **kwargs):
        await gate.wait()
        return b"DEDUP_AUDIO"

    dummy_client = type("DummyClient", (), {})()
    dummy_client.synthesize = AsyncMock(side_effect=_delayed_synthesize)
    dummy_client.check_health = AsyncMock(return_value=True)
    dummy_client.get_stats = lambda: {}
    dummy_client.close = AsyncMock()
    manager.client = dummy_client

    task_1 = asyncio.create_task(manager.synthesize_text("并发测试"))
    await asyncio.sleep(0)
    task_2 = asyncio.create_task(manager.synthesize_text("并发测试"))
    await asyncio.sleep(0)

    gate.set()
    result_1, result_2 = await asyncio.gather(task_1, task_2)

    assert result_1 == result_2 == b"DEDUP_AUDIO"
    assert dummy_client.synthesize.await_count == 1


def test_ttsmanager_deduplicates_inflight_requests() -> None:
    asyncio.run(_run_inflight_deduplication())


async def _run_paragraph_split() -> None:
    """整段文本应通过 StreamProcessor 切分并逐句合成。"""

    config = TTSConfig(
        api_url="http://127.0.0.1:9880/tts",
        max_parallel_requests=3,
        disk_cache_enabled=False,
    )
    manager = TTSManager(config)

    captured_texts: list[str] = []

    async def _capture_text(*args, **kwargs):
        captured_texts.append(kwargs["text"])
        return kwargs["text"].encode("utf-8")

    dummy_client = type("DummyClient", (), {})()
    dummy_client.synthesize = AsyncMock(side_effect=_capture_text)
    dummy_client.check_health = AsyncMock(return_value=True)
    dummy_client.get_stats = lambda: {}
    dummy_client.close = AsyncMock()
    manager.client = dummy_client

    paragraph = "第一句。然后是第二句！最后来一句问候？"
    audios = await manager.synthesize_paragraph(
        paragraph,
        min_sentence_length=2,
    )

    assert len(audios) == 3
    assert captured_texts == [
        "第一句。",
        "然后是第二句！",
        "最后来一句问候？",
    ]


def test_ttsmanager_paragraph_split() -> None:
    asyncio.run(_run_paragraph_split())
