"""
应用配置类

使用 Pydantic 进行配置管理，支持从 YAML 配置文件加载。
基于 config.user.yaml + config.dev.yaml 的统一配置方案（兼容 config.yaml）。
"""

from pathlib import Path
from typing import Any, Dict, Optional
import sys

import yaml
from pydantic import AliasChoices, BaseModel, ConfigDict, Field

# 允许直接执行该模块时也能解析到 src.* 包
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.utils.logger import logger  # noqa: E402
from src.config.config_files import (  # noqa: E402
    DEFAULT_DEV_CONFIG_EXAMPLE_PATH,
    DEFAULT_DEV_CONFIG_PATH,
    DEFAULT_USER_CONFIG_EXAMPLE_PATH,
    DEFAULT_USER_CONFIG_PATH,
    LEGACY_CONFIG_PATH,
    deep_merge_dict,
    read_yaml_file,
    resolve_config_paths,
    to_project_path,
)

# ==================== LLM 配置模型 ====================


class LLMConfig(BaseModel):
    """LLM 配置"""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    api: str = Field(
        default="https://api.openai.com/v1",
        description="LLM API 地址",
    )

    key: str = Field(
        default="",
        description="LLM API Key",
    )

    model: str = Field(
        default="gpt-4o",
        description="模型名称",
    )

    temperature: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="模型温度参数（兼容旧版配置）",
    )

    max_tokens: int = Field(
        default=2000,
        ge=1,
        description="最大生成 tokens（兼容旧版配置）",
    )

    extra_config: Dict[str, Any] = Field(
        default_factory=dict,
        description="额外的模型参数（temperature、top_p 等）",
    )


# ==================== 视觉 LLM 配置模型 ====================
#
# 目标：将视觉识别所用模型与主 LLM 解耦（主 LLM 可能是纯文本模型）。
#


class VisionLLMConfig(BaseModel):
    """视觉 LLM 配置（独立于主 LLM，可选启用）。"""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    enabled: bool = Field(
        default=False,
        description="是否启用视觉 LLM（用于图片描述/OCR）。",
        validation_alias=AliasChoices("enabled", "enable"),
    )

    api: Optional[str] = Field(
        default=None,
        description="视觉 LLM API 地址（为空则继承主 LLM.api）。",
    )

    key: Optional[str] = Field(
        default=None,
        description="视觉 LLM API Key（为空则继承主 LLM.key）。",
    )

    model: Optional[str] = Field(
        default=None,
        description="视觉模型名称（为空则继承主 LLM.model）。",
    )

    temperature: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="视觉模型温度参数（为空则继承主 LLM.temperature）。",
    )

    max_tokens: Optional[int] = Field(
        default=None,
        ge=1,
        description="视觉模型最大 tokens（为空则继承主 LLM.max_tokens）。",
    )

    extra_config: Dict[str, Any] = Field(
        default_factory=dict,
        description="视觉模型额外参数（会覆盖/合并主 LLM.extra_config）。",
    )

    def resolve(self, base: LLMConfig) -> LLMConfig:
        """用主 LLM 作为底座补全视觉模型配置，返回可直接用于构建 Chat Model 的 LLMConfig。"""
        merged_extra: Dict[str, Any] = dict(base.extra_config or {})
        if self.extra_config:
            merged_extra.update(self.extra_config)
        return LLMConfig(
            api=self.api if self.api is not None else base.api,
            key=self.key if self.key is not None else base.key,
            model=self.model if self.model is not None else base.model,
            temperature=self.temperature if self.temperature is not None else base.temperature,
            max_tokens=self.max_tokens if self.max_tokens is not None else base.max_tokens,
            extra_config=merged_extra,
        )


# ==================== 情绪系统配置模型 ====================


class MoodFunctions(BaseModel):
    """情绪影响函数配置"""

    positive_impact: str = Field(
        default="1 + log(3 * pi * x) + 0.8 * sqrt(x)",
        description="正面情绪影响函数",
    )

    negative_impact: str = Field(
        default="(sqrt(pi) * x) / (1 + exp(sqrt(e) * 0.8 * (sqrt(pi) - x))) + sqrt(e)",
        description="负面情绪影响函数",
    )


# ==================== TTS 配置模型 ====================


class TTSConfig(BaseModel):
    """TTS (Text-to-Speech) 配置"""

    model_config = ConfigDict(extra="ignore")

    enabled: bool = Field(
        default=False,
        description="是否启用 TTS 功能",
    )

    api_url: str = Field(
        default="http://127.0.0.1:9880/tts",
        description="GPT-SoVITS API 地址",
    )

    ref_audio_path: str = Field(
        default="",
        description="参考音频路径（留空则使用 GPT-SoVITS 默认配置）",
    )

    ref_audio_text: str = Field(
        default="",
        description="参考音频文本",
    )

    text_lang: str = Field(
        default="zh",
        description="文本语言（zh=中文, en=英文, ja=日语）",
    )

    prompt_lang: str = Field(
        default="zh",
        description="提示语言",
    )

    top_k: int = Field(
        default=5,
        description="Top-K 采样参数",
    )

    top_p: float = Field(
        default=1.0,
        description="Top-P 采样参数",
    )

    temperature: float = Field(
        default=1.0,
        description="温度参数",
    )

    speed_factor: float = Field(
        default=1.0,
        description="语速因子",
    )

    text_split_method: str = Field(
        default="cut0",
        description="GPT-SoVITS 文本切分方法（cut0/cut1/cut2/cut3/cut4/cut5），默认不切分（cut0），由前端控制分句",
    )

    max_queue_size: int = Field(
        default=10,
        description="音频队列最大长度",
    )

    default_volume: float = Field(
        default=0.8,
        ge=0.0,
        le=1.0,
        description="默认音量（0.0-1.0）",
    )

    disk_cache_enabled: bool = Field(
        default=True,
        description="是否启用磁盘级 TTS 缓存",
    )

    disk_cache_dir: str = Field(
        default="data/tts_cache",
        description="TTS 磁盘缓存目录",
    )

    disk_cache_max_items: int = Field(
        default=400,
        description="磁盘缓存最大条目数",
    )

    disk_cache_max_bytes: int = Field(
        default=0,
        description="磁盘缓存磁盘占用上限（字节，0 表示不限）",
    )

    disk_cache_compress: bool = Field(
        default=True,
        description="磁盘缓存是否使用 gzip 压缩",
    )

    disk_cache_ttl_seconds: float = Field(
        default=0.0,
        description="磁盘缓存生存时间（秒，0 表示永久）",
    )

    max_parallel_requests: int = Field(
        default=2,
        ge=1,
        description="批量合成时的最大并发请求数",
    )

    paragraph_min_sentence_length: int = Field(
        default=8,
        ge=1,
        description="段落模式分句的最小长度",
    )

    client_max_retries: int = Field(
        default=3,
        ge=1,
        description="GPT-SoVITS HTTP 最大重试次数",
    )

    request_timeout: float = Field(
        default=30.0,
        gt=0.0,
        description="HTTP 客户端整体超时时间（秒）",
    )

    connect_timeout: float = Field(
        default=10.0,
        gt=0.0,
        description="HTTP 连接超时时间（秒）",
    )

    read_timeout: float = Field(
        default=30.0,
        gt=0.0,
        description="HTTP 读取超时时间（秒）",
    )

    write_timeout: float = Field(
        default=30.0,
        gt=0.0,
        description="HTTP 写入超时时间（秒）",
    )

    http2_enabled: bool = Field(
        default=False,
        description="是否启用 HTTP/2 连接（需 GPT-SoVITS 端支持）",
    )

    pool_max_connections: int = Field(
        default=10,
        ge=1,
        description="HTTP 连接池最大连接数",
    )

    pool_max_keepalive_connections: int = Field(
        default=5,
        ge=0,
        description="HTTP 连接池最大 Keep-Alive 连接数",
    )

    pool_keepalive_expiry: float = Field(
        default=30.0,
        gt=0.0,
        description="HTTP Keep-Alive 连接过期时间（秒）",
    )
    circuit_break_threshold: int = Field(
        default=4,
        ge=1,
        description="连续失败多少次后触发熔断",
    )
    circuit_break_cooldown: float = Field(
        default=15.0,
        gt=0.0,
        description="熔断后冷却时间（秒）",
    )


# ==================== ASR 配置模型 ====================


class ASRConfig(BaseModel):
    """ASR (Speech-to-Text) 配置"""

    model_config = ConfigDict(extra="ignore")

    enabled: bool = Field(
        default=False,
        description="是否启用 ASR（语音转文本）功能",
    )

    model: str = Field(
        default="iic/SenseVoiceSmall",
        description="FunASR 模型名称/路径（默认 SenseVoiceSmall：iic/SenseVoiceSmall）",
    )

    hub: Optional[str] = Field(
        default=None,
        description="模型仓库来源（hf=HuggingFace, ms=ModelScope）；为空则自动推断",
    )

    trust_remote_code: bool = Field(
        default=True,
        description="是否信任模型仓库远程代码（仅 HuggingFace hub 生效；ModelScope 会忽略以避免噪声/失败日志）",
    )

    device: str = Field(
        default="auto",
        description="推理设备（auto/cpu/cuda），默认 auto（优先使用 CUDA）",
    )

    language: str = Field(
        default="auto",
        description="识别语言（auto/zh/en/ja/ko/yue 等），默认 auto",
    )

    use_itn: bool = Field(
        default=True,
        description="是否启用 ITN（数字/日期等文本规范化），默认开启",
    )

    ban_emo_unk: bool = Field(
        default=True,
        description="是否禁用未知情绪 token（减少 SenseVoice 输出噪声）",
    )

    vad_model: Optional[str] = Field(
        default="fsmn-vad",
        description="VAD 模型（建议 fsmn-vad）；为空/none 则禁用长音频切分",
    )

    vad_max_single_segment_time_ms: int = Field(
        default=30000,
        ge=1000,
        le=120000,
        description="VAD 单段最大时长（ms），默认 30000",
    )

    merge_vad: bool = Field(
        default=True,
        description="是否合并 VAD 分段结果（提升连贯性）",
    )

    merge_length_s: int = Field(
        default=15,
        ge=1,
        le=60,
        description="VAD 合并窗口（秒），默认 15",
    )

    batch_size_s: int = Field(
        default=60,
        ge=1,
        le=600,
        description="长音频动态 batch 时长上限（秒），默认 60",
    )

    sample_rate: int = Field(
        default=16000,
        ge=8000,
        le=48000,
        description="录音采样率（Hz），默认 16000",
    )

    partial_interval_ms: int = Field(
        default=600,
        ge=80,
        le=2000,
        description="实时转写刷新间隔（毫秒），越小越实时但越耗 CPU",
    )

    partial_window_s: float = Field(
        default=4.0,
        gt=0.5,
        le=20.0,
        description="实时转写窗口长度（秒）：每次识别取最近 N 秒音频（降低延迟与抖动）",
    )

    # ==================== Realtime Streaming ASR (Low Latency) ====================

    realtime_mode: str = Field(
        default="auto",
        description=(
            "实时语音输入模式：auto=优先流式（更低延迟）；window=滑窗（兼容旧逻辑）；"
            "streaming=仅流式；dual=流式 partial + 最终模型二次识别（更高准确度）"
        ),
    )

    streaming_model: str = Field(
        default="paraformer-zh-streaming",
        description="流式 ASR 模型（FunASR），用于低延迟 partial 更新（默认：paraformer-zh-streaming）",
    )

    streaming_hub: Optional[str] = Field(
        default=None,
        description="流式模型仓库来源（hf=HuggingFace, ms=ModelScope）；为空则自动推断",
    )

    streaming_chunk_size: list[int] = Field(
        default_factory=lambda: [0, 8, 4],
        description=(
            "流式 chunk_size：[0, chunk, lookahead]，单位 60ms；例如 [0,8,4]=480ms 粒度 + "
            "240ms lookahead"
        ),
    )

    streaming_encoder_chunk_look_back: int = Field(
        default=4,
        ge=0,
        le=20,
        description="流式：encoder self-attention 回看 chunk 数",
    )

    streaming_decoder_chunk_look_back: int = Field(
        default=1,
        ge=0,
        le=20,
        description="流式：decoder cross-attention 回看 encoder chunk 数",
    )

    dual_emit_streaming_final: bool = Field(
        default=True,
        description="dual 模式：先用流式结果立即写入输入框，再用最终模型覆盖（体感更快）",
    )

    silence_skip_partial: bool = Field(
        default=True,
        description="是否在静音时跳过 partial 推理（降低 CPU/提升流畅度）",
    )

    silence_rms_threshold: float = Field(
        default=0.006,
        gt=0.0,
        le=0.2,
        description="静音阈值（RMS，0-1）；低于该值认为静音，默认 0.006",
    )

    # ==================== Realtime Mic VAD / Endpointing ====================

    silence_threshold_mode: str = Field(
        default="auto",
        description="静音阈值模式：fixed=固定阈值（silence_rms_threshold），auto=自动噪声门限（推荐）",
    )

    silence_threshold_multiplier: float = Field(
        default=3.0,
        gt=1.0,
        le=20.0,
        description="auto 模式下：静音阈值 = max(silence_rms_threshold, noise_rms * multiplier)",
    )

    noise_calibration_ms: int = Field(
        default=400,
        ge=0,
        le=5000,
        description="auto 模式下噪声底噪估计的校准时长（ms），默认 400",
    )

    min_speech_ms: int = Field(
        default=180,
        ge=0,
        le=2000,
        description="判定开始说话所需的最短连续语音时长（ms），默认 180",
    )

    endpoint_silence_ms: int = Field(
        default=900,
        ge=0,
        le=10000,
        description="停顿自动结束阈值（ms）；为 0 则关闭自动结束，默认 900",
    )

    pre_roll_ms: int = Field(
        default=250,
        ge=0,
        le=3000,
        description="开始说话前保留的预卷帧（ms），避免吞掉第一个字，默认 250",
    )

    max_utterance_s: float = Field(
        default=25.0,
        gt=0.0,
        le=300.0,
        description="单次语音输入最长时长（秒），超过将自动结束，默认 25.0",
    )

    warmup: bool = Field(
        default=True,
        description="启动时是否做一次模型预热（降低首次识别延迟）",
    )


# ==================== MCP 配置模型 ====================


class MCPServerConfig(BaseModel):
    """单个 MCP 服务器配置"""

    model_config = ConfigDict(extra="ignore")
    enabled: bool = Field(
        default=True,
        description="是否启用此 MCP 服务器",
    )

    command: str = Field(
        default="",
        description="MCP 服务器启动命令",
    )

    args: list[str] = Field(
        default_factory=list,
        description="MCP 服务器启动参数",
    )

    env: Dict[str, str] = Field(
        default_factory=dict,
        description="MCP 服务器环境变量",
    )

    transport: str = Field(
        default="stdio",
        description="MCP 传输协议 (stdio, sse, http)",
    )

    max_concurrency: int = Field(
        default=1,
        ge=1,
        description="单个 MCP 服务器最大并发调用数（默认 1，建议按 server 能力调整）",
    )


class MCPConfig(BaseModel):
    """MCP (Model Context Protocol) 配置"""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)
    enabled: bool = Field(
        default=True,
        description="是否启用 MCP 系统",
        alias="enable",
    )

    servers: Dict[str, MCPServerConfig] = Field(
        default_factory=dict,
        description="MCP 服务器配置字典",
    )


# ==================== Agent 配置模型 ====================


class AgentConfig(BaseModel):
    """Agent 配置"""

    model_config = ConfigDict(extra="ignore")
    # 基础配置
    is_up: bool = Field(
        default=True,
        description="是否启用角色模板功能",
    )

    char: str = Field(
        default="小雪糕",
        description="角色名称",
    )

    user: str = Field(
        default="主人",
        description="用户名称",
    )

    enable_streaming: bool = Field(
        default=True,
        description="Enable streaming output (compat)",
    )

    max_history_length: int = Field(
        default=20,
        ge=1,
        description="Max history length (compat)",
    )

    enable_tools: bool = Field(
        default=True,
        description="Enable tools (compat)",
    )

    # 记忆系统配置
    long_memory: bool = Field(
        default=True,
        description="是否启用日记功能（长期记忆）",
    )

    is_check_memorys: bool = Field(
        default=True,
        description="启用日记检索加强",
    )

    is_core_mem: bool = Field(
        default=True,
        description="是否启用核心记忆功能",
    )

    mem_thresholds: float = Field(
        default=0.385,
        ge=0.0,
        le=1.0,
        description="日记内容搜索阈值",
    )

    # v3.2 记忆优化器配置
    memory_optimizer_enabled: bool = Field(
        default=True,
        description="是否启用记忆优化器（缓存、去重、巩固、角色一致性）",
    )
    memory_dedup_max_hashes: int = Field(
        default=50_000,
        ge=0,
        le=1_000_000,
        description="去重器保留的 content_hash 最大数量（0 表示不限制，但会增加内存占用）",
    )
    memory_character_consistency_weight: float = Field(
        default=0.1,
        ge=0.0,
        le=1.0,
        description="长期记忆检索重排序中角色一致性权重（0 表示不参与）。",
    )

    # 长期记忆（向量库）写入策略
    long_term_batch_size: int = Field(
        default=10,
        ge=1,
        le=1000,
        description="长期记忆批量写入阈值（条）。达到阈值会触发一次向量库写入。",
    )
    long_term_batch_flush_interval_s: float = Field(
        default=30.0,
        ge=0.0,
        le=3600.0,
        description="长期记忆批量写入强制刷新间隔（秒）。0 表示仅按条数触发。",
    )
    long_term_write_buffer_max: int = Field(
        default=256,
        ge=0,
        le=10000,
        description="长期记忆后台写入缓冲区最大条数（用于将向量写入移出对话热路径）。0 表示不限制。",
    )
    long_term_write_drain_max_items: int = Field(
        default=32,
        ge=0,
        le=10000,
        description="长期记忆后台写入每次 drain 的最大处理条数（分片执行，避免后台线程池长期占用）。0 表示不限制。",
    )
    long_term_write_drain_budget_s: float = Field(
        default=0.25,
        ge=0.0,
        le=10.0,
        description="长期记忆后台写入每次 drain 的时间预算（秒）。0 表示不限制。",
    )

    # v3.2.1 性能优化配置
    memory_fast_mode: bool = Field(
        default=True,
        description="启用快速模式（异步执行非关键操作，提升响应速度）",
    )
    memory_retriever_source_timeout_s: float = Field(
        default=0.25,
        ge=0.0,
        le=10.0,
        description="并发记忆检索每个来源的超时（秒），0 表示不启用超时保护。",
    )
    memory_breaker_threshold: int = Field(
        default=3,
        ge=1,
        le=100,
        description="记忆检索熔断器阈值（连续失败次数）。",
    )
    memory_breaker_cooldown: float = Field(
        default=3.0,
        ge=0.0,
        le=60.0,
        description="记忆检索熔断器冷却时间（秒）。",
    )

    # Redis 缓存配置（用于多级缓存 L2）
    redis_enabled: bool = Field(
        default=False,
        description="启用 Redis 作为二级缓存（关闭后仅使用内存缓存）",
    )
    redis_validate_on_startup: bool = Field(
        default=False,
        description="启动时是否 ping Redis 验证连接（开启会增加启动耗时）",
    )
    redis_host: str = Field(
        default="127.0.0.1",
        description="Redis 主机地址",
    )
    redis_port: int = Field(
        default=6379,
        ge=1,
        description="Redis 端口",
    )
    redis_db: int = Field(
        default=0,
        ge=0,
        description="Redis 数据库索引",
    )
    redis_password: str = Field(
        default="",
        description="Redis 认证密码（留空则不使用认证）",
    )
    redis_connect_timeout: float = Field(
        default=1.0,
        ge=0.1,
        description="Redis 连接超时时间（秒）",
    )
    redis_socket_timeout: float = Field(
        default=1.0,
        ge=0.1,
        description="Redis 读写超时时间（秒）",
    )

    # 工具系统配置（v3.3.5）
    enable_builtin_tools: bool = Field(
        default=True,
        description="是否启用内置高级工具（Bing/高德等，依赖 aiohttp/bs4 等）",
    )
    enable_mcp_tools: bool = Field(
        default=True,
        description="是否启用 MCP 工具注册（需要配置 MCP.servers，且安装 mcp SDK）",
    )

    # v2.30.36 智能日记系统配置
    smart_diary_enabled: bool = Field(
        default=True,
        description="启用智能日记系统（只记录重要对话，像人类写日记一样）",
    )

    diary_importance_threshold: float = Field(
        default=0.6,
        ge=0.0,
        le=1.0,
        description="日记重要性阈值（只保存重要性 >= 此值的对话）",
    )
    diary_daily_max_entries: int = Field(
        default=5,
        ge=1,
        description="每天最多保存的日记条数，超过后跳过（仍可生成每日总结）",
    )
    diary_max_entries: int = Field(
        default=500,
        ge=1,
        description="日记最大保留条数（超过后自动清理最旧条目）",
    )
    diary_max_days: int = Field(
        default=90,
        ge=1,
        description="日记最大保留天数（超过后自动清理最旧条目）",
    )
    diary_min_chars: int = Field(
        default=10,
        ge=1,
        description="日记最小字符数（低于该长度将不记录）",
    )
    diary_min_interval_minutes: int = Field(
        default=10,
        ge=1,
        description="日记记录的最小时间间隔（分钟），避免短时间内重复记录",
    )
    diary_similarity_threshold: float = Field(
        default=0.9,
        ge=0.0,
        le=1.0,
        description="日记内容近似去重阈值（0-1，越高越严格）",
    )
    diary_daily_highlights: int = Field(
        default=3,
        ge=1,
        description="每日总结高光时刻保留条数",
    )

    daily_summary_enabled: bool = Field(
        default=True,
        description="启用每日总结（自动生成今天的对话总结）",
    )

    # 知识库配置
    lore_books: bool = Field(
        default=True,
        description="是否启用世界书（知识库）",
    )

    books_thresholds: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="知识库检索阈值",
    )

    scan_depth: int = Field(
        default=4,
        gt=0,
        description="知识库搜索深度",
    )

    # v2.30.38 智能学习配置
    auto_learn_from_conversation: bool = Field(
        default=True,
        description="是否从对话中自动学习知识",
    )

    # TTS 预取优化
    tts_auto_prefetch: bool = Field(
        default=True,
        description="在生成文本后是否后台预取 TTS 音频",
    )
    tts_prefetch_min_chars: int = Field(
        default=48,
        ge=1,
        description="触发 TTS 预取的最小回复长度（字符）",
    )

    # v2.30.39 LLM 辅助提取配置
    use_llm_for_knowledge_extraction: bool = Field(
        default=False,
        description="是否使用 LLM 辅助知识提取（更智能但更慢，需要消耗 API）",
    )

    # 主动知识推送（ProactiveKnowledgePusher）
    proactive_push_enabled: bool = Field(
        default=True,
        description="是否启用主动知识推送（将知识库内容作为辅助角色扮演的轻量提示）",
    )
    proactive_push_k: int = Field(
        default=2,
        ge=0,
        description="每次最多推送知识条数（0 为禁用）",
    )
    proactive_push_timeout_s: float = Field(
        default=0.18,
        ge=0.0,
        le=10.0,
        description="主动知识推送在请求热路径的预算超时（秒）。0 表示不限制（可能显著增加延迟）。",
    )
    proactive_push_in_fast_mode: bool = Field(
        default=False,
        description="在 memory_fast_mode 下是否仍注入主动知识提示（会影响首包延迟）。",
    )
    bundle_prepare_timeout_s: float = Field(
        default=0.35,
        ge=0.0,
        le=30.0,
        description="构建对话上下文/消息列表的总体超时预算（秒）。0 表示不限制。",
    )
    proactive_push_recent_topics_max_len: int = Field(
        default=8,
        ge=0,
        description="保留的最近主题数（用于话题转换触发，0 为不保留）",
    )
    proactive_push_cooldown_s: float = Field(
        default=300.0,
        ge=0.0,
        description="主动推送冷却时间（秒）",
    )
    proactive_push_daily_limit: int = Field(
        default=10,
        ge=0,
        description="每日最大推送次数（0 为不限制）",
    )
    proactive_push_min_quality_score: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="推送知识的最低质量分数阈值（0-1）",
    )
    proactive_push_min_relevance_score: float = Field(
        default=0.3,
        ge=0.0,
        le=1.0,
        description="推送知识的最低相关性分数阈值（0-1）",
    )
    proactive_push_max_history: int = Field(
        default=1000,
        ge=0,
        description="内部保存的推送历史最大条数（0 为不保留）",
    )
    proactive_push_max_pushed_per_user: int = Field(
        default=500,
        ge=0,
        description="每个用户记录的“已推送知识”去重 key 最大条数（0 为不限制）",
    )
    proactive_push_candidate_pool_size: int = Field(
        default=60,
        ge=0,
        description="主动推送向量检索候选池大小（0 为禁用，回退为全库扫描）",
    )
    proactive_push_persist_state: bool = Field(
        default=True,
        description="是否持久化主动推送去重/冷却/每日计数状态（重启后仍生效）",
    )
    proactive_push_state_file: str = Field(
        default="",
        description="主动推送状态文件路径（留空则使用 data_dir/memory/proactive_push_state.json）",
    )
    proactive_push_max_chars_per_item: int = Field(
        default=480,
        ge=0,
        description="注入提示词时，每条知识内容最大字符数（0 为不截断）",
    )

    # 知识图谱配置（关系提取/查询性能保护）
    knowledge_graph_enabled: bool = Field(
        default=True,
        description="是否启用知识图谱系统（仅当依赖可用时生效）",
    )
    knowledge_graph_auto_update: bool = Field(
        default=True,
        description="知识增删改时是否自动增量更新图谱（避免手动重建）",
    )
    knowledge_graph_auto_update_edges: bool = Field(
        default=True,
        description="增量更新时是否同时更新规则关系边（更智能但更耗时）",
    )
    knowledge_graph_auto_update_async: bool = Field(
        default=True,
        description="图谱增量更新是否放到后台线程执行（需要性能优化器/线程池可用）",
    )
    knowledge_graph_autosave: bool = Field(
        default=True,
        description="知识图谱是否自动落盘（关闭可显著减少写盘，但异常退出会丢最后未 flush 的更新）",
    )
    knowledge_graph_save_pretty_json: bool = Field(
        default=True,
        description="知识图谱保存 JSON 时是否缩进美化（更易读但更慢更大）",
    )
    knowledge_graph_save_sort: bool = Field(
        default=True,
        description="知识图谱保存 JSON 时是否对节点/边排序（便于 diff 但更慢）",
    )
    knowledge_graph_rule_max_ids_per_keyword: int = Field(
        default=200,
        ge=1,
        description="规则提取时每个关键词最多参与匹配的知识数量（防止公共词爆炸）",
    )
    knowledge_graph_rule_max_keyword_links_per_node: int = Field(
        default=12,
        ge=0,
        description="规则提取时每个知识最多保留的关键词相关边数（0 表示不限制）",
    )
    knowledge_graph_rule_category_anchor_count: int = Field(
        default=2,
        ge=0,
        description="规则提取时每个类别的锚点数量（用于稀疏化类别边）",
    )
    knowledge_graph_rule_max_relations: int = Field(
        default=100_000,
        ge=0,
        description="规则提取最大关系数量（0 表示不限制）",
    )
    knowledge_graph_rule_shared_keywords_desc_limit: int = Field(
        default=12,
        ge=1,
        description="关系描述中最多显示的共享关键词数量",
    )
    knowledge_graph_find_max_results: int = Field(
        default=200,
        ge=0,
        description="图谱相关知识查询最大返回数（0 表示不限制）",
    )
    knowledge_graph_find_max_nodes_visited: int = Field(
        default=5000,
        ge=0,
        description="图谱相关知识查询最大遍历节点数（0 表示不限制）",
    )
    knowledge_graph_find_include_incoming: bool = Field(
        default=True,
        description="图谱相关知识查询是否包含入边（True 更适合“相关知识”检索）",
    )

    # 情绪系统配置
    mood_system_enabled: bool = Field(
        default=True,
        description="是否启用情绪系统",
    )

    mood_persists: bool = Field(
        default=True,
        description="重启后是否保持情绪值 (v3.1 默认启用)",
    )
    mood_persist_interval_s: float = Field(
        default=1.0,
        ge=0.0,
        description="情绪系统状态写盘最小间隔（秒）。0 表示每次更新都写盘。",
    )
    mood_history_max_len: int = Field(
        default=500,
        ge=0,
        description="情绪系统历史记录最大内存条数（0 表示不限制，不推荐）。",
    )

    character_state_persist_interval_s: float = Field(
        default=2.0,
        ge=0.0,
        description="角色状态（CharacterState）写盘最小间隔（秒）。0 表示每次更新都写盘。",
    )

    # v3.1 新增情绪系统配置
    emotion_memory_enabled: bool = Field(
        default=True,
        description="是否启用情绪记忆系统",
    )
    emotion_persist_interval_s: float = Field(
        default=1.0,
        ge=0.0,
        description="情感引擎状态写盘最小间隔（秒）。0 表示每次更新都写盘。",
    )

    dual_source_emotion: bool = Field(
        default=True,
        description="是否启用双源情绪融合",
    )

    mood_functions: MoodFunctions = Field(
        default_factory=MoodFunctions,
        description="情绪影响函数配置",
    )

    context_auto_compress_ratio: float = Field(
        default=0.75,
        ge=0.1,
        le=1.0,
        description="上下文 token 超过该比例时触发自动压缩",
    )
    context_auto_compress_min_messages: int = Field(
        default=12,
        ge=4,
        description="消息条数达到该值时尝试自动压缩",
    )

    # 流式/线程池/工具执行配置
    llm_executor_workers: int = Field(
        default=2,
        ge=1,
        description="LLM 执行线程池大小",
    )
    llm_first_chunk_timeout_s: float = Field(
        default=18.0,
        gt=0.0,
        description="LLM 流式首包超时（秒）",
    )
    llm_idle_chunk_timeout_s: float = Field(
        default=30.0,
        gt=0.0,
        description="LLM 流式增量空闲超时（秒）",
    )
    llm_total_timeout_s: float = Field(
        default=120.0,
        gt=0.0,
        description="LLM 总超时（秒，包含工具执行）",
    )
    llm_stream_disable_after_failures: int = Field(
        default=2,
        ge=1,
        description="连续流式失败达到该次数后临时禁用 streaming",
    )
    llm_stream_disable_cooldown_s: float = Field(
        default=60.0,
        ge=0.0,
        description="临时禁用 streaming 的冷却时间（秒）。0 表示仅本次禁用，下次对话自动恢复。",
    )
    stream_executor_workers: int = Field(
        default=2,
        ge=1,
        description="流式执行线程池大小",
    )
    stream_min_chunk_chars: int = Field(
        default=8,
        ge=1,
        description="流式输出合并的最小字符数阈值",
    )
    tool_executor_workers: int = Field(
        default=4,
        ge=1,
        description="工具执行线程池大小",
    )
    tool_timeout_s: float = Field(
        default=30.0,
        gt=0.0,
        description="工具执行默认超时时间（秒）",
    )
    tool_output_max_chars: int = Field(
        default=12000,
        ge=0,
        description="工具执行结果最大字符数（避免 prompt 膨胀导致超时），0 表示不限制",
    )
    tool_rewrite_timeout_s: float = Field(
        default=8.0,
        gt=0.0,
        description="工具结果兜底重写调用超时（秒）。用于空回复/仅进度回复时，基于工具结果生成最终回答。",
    )
    implicit_tool_rescue_enabled: bool = Field(
        default=True,
        description=(
            "当模型输出“我这就去查/让我看看”等进度话术但未实际触发工具调用时，"
            "允许本地执行轻量工具并生成最终回复（防止时间/日期等问题空回复或只剩进度话术）。"
        ),
    )
    tool_direct_grace_s: float = Field(
        default=1.5,
        ge=0.0,
        description="工具结果直出等待 LLM 继续输出的宽限时间（秒）",
    )
    tool_selector_enabled: bool = Field(
        default=True,
        description="启用 LLM 工具筛选中间件（会额外调用一次 LLM）",
    )
    tool_selector_in_fast_mode: bool = Field(
        default=False,
        description="在 memory_fast_mode 下是否仍启用 LLM 工具筛选（会额外调用一次 LLM，增加首包延迟）。",
    )
    tool_selector_timeout_s: float = Field(
        default=4.0,
        gt=0.0,
        description="LLM 工具筛选调用超时（秒）。超时将跳过筛选，避免阻塞流式输出。",
    )
    tool_selector_disable_cooldown_s: float = Field(
        default=300.0,
        ge=0.0,
        description="工具筛选失败/超时后的熔断时间（秒）。0 表示仅本次跳过，不熔断。",
    )
    tool_selector_min_tools: int = Field(
        default=16,
        ge=0,
        description="当工具数量小于该值时跳过 LLM 工具筛选（性能优化）",
    )
    context_cache_max_entries: int = Field(
        default=16,
        ge=0,
        description="对话上下文准备的缓存最大条目数，0 表示禁用",
    )

    # 对话风格学习器（v2.5）
    style_learning_enabled: bool = Field(
        default=True,
        description="是否启用对话风格学习器（根据用户消息自适应回复节奏/语气）",
    )
    style_persist_interval_s: float = Field(
        default=15.0,
        ge=0.0,
        description="风格学习配置落盘节流间隔（秒）。达到间隔或条数阈值会触发写盘。",
    )
    style_persist_every_n_interactions: int = Field(
        default=10,
        ge=1,
        description="风格学习配置按交互次数强制落盘间隔（条）。",
    )
    style_history_max_len: int = Field(
        default=100,
        ge=10,
        description="风格学习器统计窗口大小（保留最近 N 条消息长度）。",
    )
    style_word_counter_max: int = Field(
        default=100,
        ge=0,
        description="保存的高频词最大数量（0 表示不保存）。",
    )
    style_topic_counter_max: int = Field(
        default=50,
        ge=0,
        description="保存的话题统计最大数量（0 表示不保存）。",
    )
    style_learning_max_message_chars: int = Field(
        default=800,
        ge=50,
        description="超过该长度的消息将跳过风格学习（防止日志/代码污染）。",
    )
    style_learning_max_message_lines: int = Field(
        default=12,
        ge=1,
        description="超过该行数的消息将跳过风格学习（防止日志/代码污染）。",
    )
    style_guidance_min_interactions: int = Field(
        default=6,
        ge=0,
        description="累计学习到的有效交互数小于该值时不输出风格指导。",
    )
    style_guidance_max_chars: int = Field(
        default=600,
        ge=0,
        description="风格指导最大字符数（0 表示不限制）。",
    )
    style_topic_decay: float = Field(
        default=0.985,
        ge=0.0,
        le=1.0,
        description="话题偏好随时间衰减系数（每次交互乘以该值）。1.0 表示不衰减。",
    )
    style_formality_decay: float = Field(
        default=0.99,
        ge=0.0,
        le=1.0,
        description="语气偏好随时间衰减系数（每次交互乘以该值）。1.0 表示不衰减。",
    )

    # 角色设定
    char_settings: str = Field(
        default="",
        description="角色的基本设定",
    )

    char_personalities: str = Field(
        default="",
        description="角色性格设定",
    )

    mask: str = Field(
        default="",
        description="关于用户自身的设定",
    )

    message_example: str = Field(
        default="",
        description="对话示例，用于强化 AI 的文风",
    )

    prompt: str = Field(
        default="",
        description="自定义提示词",
    )

    start_with: Optional[list] = Field(
        default=None,
        description="开场白",
    )


# ==================== 主配置类 ====================


class Settings(BaseModel):
    """应用程序配置类（基于 YAML）"""

    # LLM 配置
    llm: LLMConfig = Field(
        default_factory=LLMConfig,
        description="LLM 配置",
    )

    # 视觉 LLM 配置（独立于主 LLM）
    vision_llm: VisionLLMConfig = Field(
        default_factory=VisionLLMConfig,
        description="Vision LLM 配置（用于图片描述/OCR，主 LLM 可为纯文本模型）。",
    )

    # Agent 配置
    agent: AgentConfig = Field(
        default_factory=AgentConfig,
        description="Agent 配置",
    )

    # MCP 配置 (v2.30.15 新增)
    mcp: MCPConfig = Field(
        default_factory=MCPConfig,
        description="MCP (Model Context Protocol) 配置",
    )

    # TTS 配置 (v2.48.10 新增)
    tts: TTSConfig = Field(
        default_factory=TTSConfig,
        description="TTS (Text-to-Speech) 配置",
    )

    # ASR 配置 (v2.56.0 新增)
    asr: ASRConfig = Field(
        default_factory=ASRConfig,
        description="ASR (Speech-to-Text) 配置",
    )

    # 日志配置
    log_level: str = Field(
        default="INFO",
        description="日志级别（DEBUG, INFO, WARNING, ERROR, CRITICAL）",
    )
    log_dir: str = Field(
        default="logs",
        description="日志输出目录（默认项目根目录下 logs/）",
    )
    log_rotation: str = Field(
        default="50 MB",
        description="日志轮转条件（loguru 兼容格式，如 '50 MB' 或 '1 week'）",
    )
    log_retention: str = Field(
        default="14 days",
        description="日志保留时间（loguru 兼容格式，例如 '14 days'）",
    )
    log_json: bool = Field(
        default=True,
        description="是否额外输出 JSON 行格式日志，便于分析与上报",
    )
    log_quiet_libs: list[str] = Field(
        default_factory=list,
        description="需要降低噪声的三方 logger 名称列表（空列表表示使用内置默认）",
    )
    log_quiet_level: str = Field(
        default="WARNING",
        description="对 log_quiet_libs 应用的日志级别",
    )
    log_drop_keywords: list[str] = Field(
        default_factory=list,
        description="附加丢弃关键词列表（空列表表示仅使用内置默认）",
    )

    # 数据路径配置
    data_dir: str = Field(
        default="./data",
        description="数据根目录",
    )

    vector_db_path: str = Field(
        default="./data/vector_db",
        description="向量数据库路径",
    )

    memory_path: str = Field(
        default="./data/memory",
        description="记忆数据路径",
    )

    cache_path: str = Field(
        default="./data/cache",
        description="缓存数据路径",
    )

    # 嵌入模型配置
    embedding_model: str = Field(
        default="BAAI/bge-large-zh-v1.5",
        description="嵌入模型名称（用于向量数据库）",
    )

    embedding_api_base: str = Field(
        default="",
        description="嵌入模型 API 地址（为空则使用 LLM API）",
    )

    # 性能优化配置 (v2.30.27)
    use_local_embedding: bool = Field(
        default=False,
        description="是否使用本地 embedding 模型（需要安装 sentence-transformers）",
    )

    enable_embedding_cache: bool = Field(
        default=True,
        description="是否启用 embedding 缓存",
    )

    # 多模态配置
    max_image_size: int = Field(
        default=1024,
        gt=0,
        description="图像最大尺寸（像素），超过此尺寸将自动缩放",
    )

    max_audio_duration: int = Field(
        default=300,
        gt=0,
        description="音频最大时长（秒）",
    )

    # ==================== 兼容性属性 ====================

    @property
    def openai_api_key(self) -> Optional[str]:
        """
        兼容旧版：OpenAI API Key

        注意：对于 OpenAI 兼容的 API（如 SiliconFlow），
        也需要返回 API Key，因为它们使用相同的客户端
        """
        # 始终返回 LLM API Key，因为 OpenAI 兼容的 API 都需要
        return self.llm.key if self.llm.key else None

    @property
    def anthropic_api_key(self) -> Optional[str]:
        """兼容旧版：Anthropic API Key"""
        return self.llm.key if "anthropic" in self.llm.api.lower() else None

    @property
    def google_api_key(self) -> Optional[str]:
        """兼容旧版：Google API Key"""
        return self.llm.key if "google" in self.llm.api.lower() else None

    @property
    def default_llm_provider(self) -> str:
        """兼容旧版：默认 LLM 提供商"""
        api_lower = self.llm.api.lower()
        if "openai" in api_lower:
            return "openai"
        elif "anthropic" in api_lower:
            return "anthropic"
        elif "google" in api_lower:
            return "google"
        else:
            return "custom"

    @property
    def default_model_name(self) -> str:
        """兼容旧版：默认模型名称"""
        return self.llm.model

    @property
    def model_temperature(self) -> float:
        """兼容旧版：模型温度参数"""
        return self.llm.extra_config.get("temperature", 0.7)

    @property
    def model_max_tokens(self) -> int:
        """兼容旧版：模型最大 token 数"""
        return self.llm.extra_config.get("max_tokens", 2000)

    @property
    def character_name(self) -> str:
        """兼容旧版：角色名称"""
        return self.agent.char

    @property
    def short_term_memory_k(self) -> int:
        """兼容旧版：短期记忆数量"""
        return max(1, int(getattr(self.agent, "max_history_length", 10) or 10))

    @property
    def long_term_memory_enabled(self) -> bool:
        """兼容旧版：是否启用长期记忆"""
        return self.agent.long_memory

    @property
    def long_term_memory_top_k(self) -> int:
        """兼容旧版：长期记忆检索数量"""
        return 5  # 默认检索 5 条相关记忆

    # ==================== 方法 ====================

    def get_llm_api_key(self) -> str:
        """
        获取 LLM API Key

        Returns:
            str: API Key

        Raises:
            ValueError: 如果未配置 API Key
        """
        if not self.llm.key:
            raise ValueError("LLM API Key 未配置，请在 config.user.yaml 中设置 LLM.key")
        return self.llm.key

    def ensure_directories(self) -> None:
        """确保必要的目录存在"""
        base = Path(self.data_dir)
        required_paths = [
            Path(self.vector_db_path),
            Path(self.memory_path),
            Path(self.cache_path),
            base / "exports",
            base / "audio",
            base / "images",
        ]
        for path in required_paths:
            path.mkdir(parents=True, exist_ok=True)

    @classmethod
    def from_yaml(cls, config_path: str = DEFAULT_USER_CONFIG_PATH) -> "Settings":
        """
        从 YAML 文件加载配置（单文件）。

        说明：
        - 默认读取 `config.user.yaml`（普通用户配置）。
        - 可选叠加 `config.dev.yaml`（开发者配置）的逻辑在 `load_settings()` 中实现。

        Args:
            config_path: 配置文件路径

        Returns:
            Settings: 配置实例

        Raises:
            FileNotFoundError: 如果配置文件不存在
            ValueError: 如果配置文件格式错误
        """
        config_file = to_project_path(config_path)

        if not config_file.exists():
            raise FileNotFoundError(
                f"配置文件不存在: {config_file}\n"
                f"首次运行请复制 {DEFAULT_USER_CONFIG_EXAMPLE_PATH} 为 {DEFAULT_USER_CONFIG_PATH} 并填写配置。\n"
                f"开发者可选复制 {DEFAULT_DEV_CONFIG_EXAMPLE_PATH} 为 {DEFAULT_DEV_CONFIG_PATH}。"
            )

        try:
            config_data = read_yaml_file(config_file)

            if not config_data:
                raise ValueError("配置文件为空")

            return cls.from_dict(config_data)

        except yaml.YAMLError as e:
            raise ValueError(f"配置文件格式错误: {e}")
        except Exception as e:
            raise ValueError(f"加载配置文件失败: {e}")

    @classmethod
    def from_dict(cls, config_data: Dict[str, Any]) -> "Settings":
        """从 dict 加载配置（通常来自多文件合并结果）。"""
        if not config_data:
            raise ValueError("配置数据为空")

        # 转换为小写键名（兼容性处理）
        llm_config = config_data.get("LLM", {})
        vision_llm_config = config_data.get("VISION_LLM", {}) or {}
        agent_config = config_data.get("Agent", {})
        log_level = config_data.get("log_level", "INFO")
        log_dir = config_data.get("log_dir", "logs")
        log_rotation = config_data.get("log_rotation", "50 MB")
        log_retention = config_data.get("log_retention", "14 days")
        log_json = config_data.get("log_json", True)
        log_quiet_libs = config_data.get("log_quiet_libs")
        if not isinstance(log_quiet_libs, list):
            log_quiet_libs = []
        log_quiet_level = config_data.get("log_quiet_level", "WARNING")
        log_drop_keywords = config_data.get("log_drop_keywords")
        if not isinstance(log_drop_keywords, list):
            log_drop_keywords = []

        # 处理 extra_config（可能为 None）
        if "extra_config" in llm_config and llm_config["extra_config"] is None:
            llm_config["extra_config"] = {}
        if "extra_config" in vision_llm_config and vision_llm_config["extra_config"] is None:
            vision_llm_config["extra_config"] = {}

        # 处理 Agent 配置中可能为 None 的字符串字段
        none_fields = [
            "char_settings",
            "char_personalities",
            "mask",
            "message_example",
            "prompt",
        ]
        for field in none_fields:
            if field in agent_config and agent_config[field] is None:
                agent_config[field] = ""

        # 处理情绪函数配置
        if "mood_functions" in agent_config:
            mood_funcs = agent_config["mood_functions"]
            if mood_funcs:
                agent_config["mood_functions"] = MoodFunctions(**mood_funcs)

        # 构建完整的配置参数
        settings_kwargs = {
            "llm": LLMConfig(**llm_config),
            "vision_llm": VisionLLMConfig(**vision_llm_config),
            "agent": AgentConfig(**agent_config),
            "log_level": log_level,
            "log_dir": log_dir,
            "log_rotation": log_rotation,
            "log_retention": log_retention,
            "log_json": log_json,
            "log_quiet_libs": log_quiet_libs,
            "log_quiet_level": log_quiet_level,
            "log_drop_keywords": log_drop_keywords,
        }

        # 加载其他配置项（如果存在）
        # 数据路径配置
        if "data_dir" in config_data:
            settings_kwargs["data_dir"] = config_data["data_dir"]
        if "vector_db_path" in config_data:
            settings_kwargs["vector_db_path"] = config_data["vector_db_path"]
        if "memory_path" in config_data:
            settings_kwargs["memory_path"] = config_data["memory_path"]
        if "cache_path" in config_data:
            settings_kwargs["cache_path"] = config_data["cache_path"]

        # 嵌入模型配置（关键修复）
        if "embedding_model" in config_data:
            settings_kwargs["embedding_model"] = config_data["embedding_model"]
        if "embedding_api_base" in config_data:
            settings_kwargs["embedding_api_base"] = config_data["embedding_api_base"]

        # 性能优化配置 (v2.30.27)
        if "use_local_embedding" in config_data:
            settings_kwargs["use_local_embedding"] = config_data["use_local_embedding"]
        if "enable_embedding_cache" in config_data:
            settings_kwargs["enable_embedding_cache"] = config_data["enable_embedding_cache"]

        # 多模态配置
        if "max_image_size" in config_data:
            settings_kwargs["max_image_size"] = config_data["max_image_size"]
        if "max_audio_duration" in config_data:
            settings_kwargs["max_audio_duration"] = config_data["max_audio_duration"]

        # MCP 配置 (v2.30.15 新增)
        if "MCP" in config_data:
            mcp_config_data = config_data["MCP"]
            if mcp_config_data:
                # 处理服务器配置
                servers = {}
                if "servers" in mcp_config_data and mcp_config_data["servers"]:
                    for server_name, server_config in mcp_config_data["servers"].items():
                        if server_config:
                            servers[server_name] = MCPServerConfig(**server_config)

                # ???? MCP ????
                enabled_value = mcp_config_data.get("enabled", mcp_config_data.get("enable", True))
                mcp_config = MCPConfig(enabled=enabled_value, servers=servers)
                settings_kwargs["mcp"] = mcp_config

        # TTS 配置 (v2.48.10 新增)
        if "TTS" in config_data:
            tts_config_data = config_data["TTS"]
            if tts_config_data:
                # 创建 TTS 配置
                tts_config = TTSConfig(**tts_config_data)
                settings_kwargs["tts"] = tts_config

        # ASR 配置 (v2.56.0 新增)
        if "ASR" in config_data:
            asr_config_data = config_data["ASR"]
            if asr_config_data:
                asr_config = ASRConfig(**asr_config_data)
                settings_kwargs["asr"] = asr_config

        return cls(**settings_kwargs)

    def to_yaml(self, output_path: str) -> None:
        """
        将当前配置保存为 YAML 文件

        Args:
            output_path: 输出文件路径
        """
        config_dict = {
            "LLM": self.llm.model_dump(by_alias=True, exclude_none=True),
            "VISION_LLM": self.vision_llm.model_dump(by_alias=True, exclude_none=True),
            "Agent": self.agent.model_dump(by_alias=True, exclude_none=True),
            "log_level": self.log_level,
            "log_dir": self.log_dir,
            "log_rotation": self.log_rotation,
            "log_retention": self.log_retention,
            "log_json": self.log_json,
            "log_quiet_libs": self.log_quiet_libs,
            "log_quiet_level": self.log_quiet_level,
            "log_drop_keywords": self.log_drop_keywords,
            "data_dir": self.data_dir,
            "vector_db_path": self.vector_db_path,
            "memory_path": self.memory_path,
            "cache_path": self.cache_path,
            "embedding_model": self.embedding_model,
            "embedding_api_base": self.embedding_api_base,
            "use_local_embedding": self.use_local_embedding,
            "enable_embedding_cache": self.enable_embedding_cache,
            "max_image_size": self.max_image_size,
            "max_audio_duration": self.max_audio_duration,
        }

        # 可选配置按原有大写键输出，保持向后兼容
        if hasattr(self, "mcp") and self.mcp is not None:
            config_dict["MCP"] = self.mcp.model_dump(by_alias=True, exclude_none=True)
        if hasattr(self, "tts") and self.tts is not None:
            config_dict["TTS"] = self.tts.model_dump(by_alias=True, exclude_none=True)
        if hasattr(self, "asr") and self.asr is not None:
            config_dict["ASR"] = self.asr.model_dump(by_alias=True, exclude_none=True)

        with open(output_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(config_dict, f, allow_unicode=True, sort_keys=False)


# ==================== 全局配置实例 ====================


# 配置缓存
_settings_cache: Optional[Settings] = None
_settings_cache_key: Optional[tuple[str, str, int | None, int | None]] = None


def load_settings(
    user_config_path: str = DEFAULT_USER_CONFIG_PATH,
    dev_config_path: str = DEFAULT_DEV_CONFIG_PATH,
    use_cache: bool = True,
    *,
    allow_legacy: bool = True,
) -> Settings:
    """
    加载配置（带缓存优化）

    Args:
        user_config_path: 普通用户配置文件路径（默认 config.user.yaml；兼容 legacy config.yaml）
        dev_config_path: 开发者配置文件路径（默认 config.dev.yaml；可选）
        use_cache: 是否使用缓存（默认True，提升性能）
        allow_legacy: 是否允许回退到 legacy config.yaml（默认 True）

    Returns:
        Settings: 配置实例
    """
    global _settings_cache, _settings_cache_key

    user_path, dev_path, legacy_used = resolve_config_paths(
        user_config_path=user_config_path,
        dev_config_path=dev_config_path,
        allow_legacy=allow_legacy,
    )

    def _mtime_ns(path: Path | None) -> int | None:
        if path is None:
            return None
        try:
            return path.stat().st_mtime_ns
        except FileNotFoundError:
            return None

    cache_key = (
        str(user_path),
        str(dev_path) if dev_path is not None else "",
        _mtime_ns(user_path),
        _mtime_ns(dev_path),
    )

    # 使用缓存（避免重复加载）
    if use_cache and _settings_cache is not None and _settings_cache_key == cache_key:
        logger.debug(f"配置缓存命中: user={user_path} dev={dev_path}")
        return _settings_cache

    if legacy_used:
        logger.info(
            f"检测到 legacy 配置文件: {LEGACY_CONFIG_PATH}；"
            f"建议迁移到 {DEFAULT_USER_CONFIG_PATH} + {DEFAULT_DEV_CONFIG_PATH}。"
        )

    try:
        user_data: Dict[str, Any] = {}
        if user_path.exists():
            user_data = read_yaml_file(user_path)
        else:
            if user_config_path == DEFAULT_USER_CONFIG_PATH and not legacy_used:
                logger.warning(
                    f"未找到配置文件 {DEFAULT_USER_CONFIG_PATH}，将使用默认配置；"
                    f"首次运行请复制 {DEFAULT_USER_CONFIG_EXAMPLE_PATH} 为 {DEFAULT_USER_CONFIG_PATH}。"
                )
            else:
                logger.warning(f"配置文件不存在: {user_path}，将使用默认配置。")

        dev_data: Dict[str, Any] = {}
        if dev_path is not None:
            try:
                dev_data = read_yaml_file(dev_path)
            except Exception as exc:
                logger.warning(f"开发者配置文件读取失败，将忽略: {dev_path} ({exc})")
                dev_data = {}

        config_data = deep_merge_dict(user_data, dev_data)
        settings_instance = Settings.from_dict(config_data)
    except Exception as exc:
        logger.warning(f"加载配置失败，将使用默认配置: {exc}")
        settings_instance = Settings()

    settings_instance.ensure_directories()
    try:
        from src.utils.logger import apply_settings as apply_logging_settings

        apply_logging_settings(settings_instance)
    except Exception as exc:
        logger.warning(f"日志配置应用失败，将使用默认日志: {exc}")

    # 更新缓存
    if use_cache:
        _settings_cache = settings_instance
        _settings_cache_key = cache_key

    return settings_instance


# 创建全局配置实例
settings = load_settings()
