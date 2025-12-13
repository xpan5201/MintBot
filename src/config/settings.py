"""
应用配置类

使用 Pydantic 进行配置管理，支持从 YAML 配置文件加载。
基于 config.yaml 的统一配置方案。
"""

from pathlib import Path
from typing import Any, Dict, Optional
import sys

import yaml
from pydantic import BaseModel, Field, ConfigDict

# 允许直接执行该模块时也能解析到 src.* 包
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.utils.logger import logger

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

    batch_size: int = Field(
        default=1,
        description="批处理大小",
    )

    seed: int = Field(
        default=-1,
        description="随机种子（-1 表示随机）",
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

    ex_config: Dict[str, Any] = Field(
        default_factory=dict,
        description="额外配置（可选）",
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

    # v3.2.1 性能优化配置
    memory_fast_mode: bool = Field(
        default=True,
        description="启用快速模式（异步执行非关键操作，提升响应速度）",
    )

    # Redis 缓存配置（用于多级缓存 L2）
    redis_enabled: bool = Field(
        default=False,
        description="启用 Redis 作为二级缓存（关闭后仅使用内存缓存）",
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

    auto_learn_from_file: bool = Field(
        default=True,
        description="是否从文件中自动学习知识",
    )

    auto_learn_from_mcp: bool = Field(
        default=True,
        description="是否从MCP中自动学习知识",
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

    knowledge_deduplication_threshold: float = Field(
        default=0.85,
        ge=0.0,
        le=1.0,
        description="知识去重相似度阈值（相似度 >= 此值认为重复）",
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

    # v3.1 新增情绪系统配置
    emotion_memory_enabled: bool = Field(
        default=True,
        description="是否启用情绪记忆系统",
    )

    dual_source_emotion: bool = Field(
        default=True,
        description="是否启用双源情绪融合",
    )

    mood_functions: MoodFunctions = Field(
        default_factory=MoodFunctions,
        description="情绪影响函数配置",
    )

    # 上下文配置
    context_length: int = Field(
        default=40,
        ge=0,
        description="上下文长度，0 表示保存所有上下文",
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
    context_cache_max_entries: int = Field(
        default=16,
        ge=0,
        description="对话上下文准备的缓存最大条目数，0 表示禁用",
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
        default_factory=lambda: [
            "httpx", "asyncio", "urllib3", "charset_normalizer",
            "multipart.multipart", "httpcore", "openai", "chromadb", "posthog",
            "langchain", "src.agent.hybrid_retriever",
            "src.agent.knowledge_quality", "src.agent.knowledge_graph",
            "src.agent.performance_optimizer",
        ],
        description="需要降低噪声的三方 logger 名称列表",
    )
    log_quiet_level: str = Field(
        default="WARNING",
        description="对 log_quiet_libs 应用的日志级别",
    )
    log_drop_keywords: list[str] = Field(
        default_factory=lambda: [
            "Request options:",
            "Sending HTTP Request:",
            "HTTP Response:",
            "receive_response_body.started",
            "receive_response_headers.started",
            "send_request_headers.started",
            "send_request_body.started",
            "插入消息:",
            "已显示",
        ],
        description="包含任意关键词的日志将被丢弃（不输出）",
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
        return self.agent.context_length if self.agent.context_length > 0 else 10

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
            raise ValueError("LLM API Key 未配置，请在 config.yaml 中设置 LLM.key")
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
    def from_yaml(cls, config_path: str = "config.yaml") -> "Settings":
        """
        从 YAML 文件加载配置

        Args:
            config_path: 配置文件路径

        Returns:
            Settings: 配置实例

        Raises:
            FileNotFoundError: 如果配置文件不存在
            ValueError: 如果配置文件格式错误
        """
        config_file = Path(config_path)

        if not config_file.exists():
            raise FileNotFoundError(
                f"配置文件不存在: {config_path}\n"
                f"请复制 config.yaml.example 为 config.yaml 并填写配置"
            )

        try:
            with open(config_file, "r", encoding="utf-8") as f:
                config_data = yaml.safe_load(f)

            if not config_data:
                raise ValueError("配置文件为空")

            # 转换为小写键名（兼容性处理）
            llm_config = config_data.get("LLM", {})
            agent_config = config_data.get("Agent", {})
            log_level = config_data.get("log_level", "INFO")
            log_dir = config_data.get("log_dir", "logs")
            log_rotation = config_data.get("log_rotation", "50 MB")
            log_retention = config_data.get("log_retention", "14 days")
            log_json = config_data.get("log_json", True)
            log_quiet_libs = config_data.get("log_quiet_libs", [
                "httpx", "asyncio", "urllib3", "charset_normalizer", "multipart.multipart"
            ])
            log_quiet_level = config_data.get("log_quiet_level", "WARNING")
            log_drop_keywords = config_data.get("log_drop_keywords", [
                "Request options:",
                "Sending HTTP Request:",
                "HTTP Response:",
                "receive_response_body.started",
                "receive_response_headers.started",
                "send_request_headers.started",
                "send_request_body.started",
            ])

            # 处理 extra_config（可能为 None）
            if "extra_config" in llm_config and llm_config["extra_config"] is None:
                llm_config["extra_config"] = {}

            # 处理 Agent 配置中可能为 None 的字符串字段
            none_fields = [
                "char_settings", "char_personalities", "mask",
                "message_example", "prompt"
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
                    mcp_config = MCPConfig(
                        enabled=enabled_value,
                        servers=servers
                    )
                    settings_kwargs["mcp"] = mcp_config

            # TTS 配置 (v2.48.10 新增)
            if "TTS" in config_data:
                tts_config_data = config_data["TTS"]
                if tts_config_data:
                    # 处理 ex_config（可能为 None）
                    if "ex_config" in tts_config_data and tts_config_data["ex_config"] is None:
                        tts_config_data["ex_config"] = {}

                    # 创建 TTS 配置
                    tts_config = TTSConfig(**tts_config_data)
                    settings_kwargs["tts"] = tts_config

            return cls(**settings_kwargs)

        except yaml.YAMLError as e:
            raise ValueError(f"配置文件格式错误: {e}")
        except Exception as e:
            raise ValueError(f"加载配置文件失败: {e}")

    def to_yaml(self, output_path: str) -> None:
        """
        将当前配置保存为 YAML 文件

        Args:
            output_path: 输出文件路径
        """
        config_dict = {
            "LLM": self.llm.model_dump(by_alias=True, exclude_none=True),
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

        with open(output_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(config_dict, f, allow_unicode=True, sort_keys=False)


# ==================== 全局配置实例 ====================


# 配置缓存
_settings_cache: Optional[Settings] = None
_settings_cache_path: Optional[str] = None


def load_settings(config_path: str = "config.yaml", use_cache: bool = True) -> Settings:
    """
    加载配置（带缓存优化）

    Args:
        config_path: 配置文件路径
        use_cache: 是否使用缓存（默认True，提升性能）

    Returns:
        Settings: 配置实例
    """
    global _settings_cache, _settings_cache_path

    # 使用缓存（避免重复加载）
    if use_cache and _settings_cache is not None and _settings_cache_path == config_path:
        logger.debug(f"配置缓存命中: {config_path}")
        return _settings_cache

    try:
        settings_instance = Settings.from_yaml(config_path)
        settings_instance.ensure_directories()
        try:
            from src.utils.logger import apply_settings as apply_logging_settings
            apply_logging_settings(settings_instance)
        except Exception as exc:
            logger.warning(f"日志配置应用失败，将使用默认日志: {exc}")

        # 更新缓存
        if use_cache:
            _settings_cache = settings_instance
            _settings_cache_path = config_path

        return settings_instance
    except FileNotFoundError:
        # 如果配置文件不存在，使用默认配置
        logger.warning(f"警告: 配置文件 {config_path} 不存在，使用默认配置")
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
            _settings_cache_path = config_path

        return settings_instance


# 创建全局配置实例
settings = load_settings()
