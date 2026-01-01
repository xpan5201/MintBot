"""
ChromaDB 辅助工具模块 (v2.30.27)

提供ChromaDB初始化和配置的公共函数，支持本地 embedding 和缓存。

优化内容:
- 支持本地 sentence-transformers 模型
- 支持 embedding 缓存
- 自动选择最优 embedding 方案

作者: MintChat Team
日期: 2025-11-16
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Optional

try:
    from langchain_chroma import Chroma

    _CHROMA_IMPORT_ERROR: Optional[BaseException] = None
    _CHROMA_IMPORT_ERROR_FALLBACK: Optional[BaseException] = None
except Exception as exc:  # pragma: no cover - 环境依赖差异
    _CHROMA_IMPORT_ERROR = exc
    _CHROMA_IMPORT_ERROR_FALLBACK = None
    try:
        from langchain_community.vectorstores import Chroma  # type: ignore

        _CHROMA_IMPORT_ERROR_FALLBACK = None
    except Exception as exc2:  # pragma: no cover - 环境依赖差异
        try:
            # 旧版 LangChain（未拆分 community/独立 chroma 包）
            from langchain.vectorstores import Chroma  # type: ignore

            _CHROMA_IMPORT_ERROR_FALLBACK = None
        except Exception as exc3:  # pragma: no cover - 环境依赖差异
            Chroma = None  # type: ignore[assignment]
            _CHROMA_IMPORT_ERROR_FALLBACK = exc3 or exc2

try:
    from langchain_openai import OpenAIEmbeddings

    _OPENAI_EMBEDDINGS_IMPORT_ERROR: Optional[BaseException] = None
    _OPENAI_EMBEDDINGS_IMPORT_ERROR_FALLBACK: Optional[BaseException] = None
except Exception as exc:  # pragma: no cover - 环境依赖差异
    _OPENAI_EMBEDDINGS_IMPORT_ERROR = exc
    _OPENAI_EMBEDDINGS_IMPORT_ERROR_FALLBACK = None
    try:
        # 旧版 LangChain（OpenAIEmbeddings 在 langchain.embeddings 下）
        from langchain.embeddings import OpenAIEmbeddings  # type: ignore

        _OPENAI_EMBEDDINGS_IMPORT_ERROR_FALLBACK = None
    except Exception as exc2:  # pragma: no cover - 环境依赖差异
        OpenAIEmbeddings = None  # type: ignore[assignment]
        _OPENAI_EMBEDDINGS_IMPORT_ERROR_FALLBACK = exc2

from src.config.settings import settings
from src.utils.logger import get_logger

logger = get_logger(__name__)

if "_CHROMA_IMPORT_ERROR" in globals() and _CHROMA_IMPORT_ERROR is not None:
    if "_CHROMA_IMPORT_ERROR_FALLBACK" in globals() and _CHROMA_IMPORT_ERROR_FALLBACK is not None:
        logger.warning(
            "Chroma 依赖导入失败（langchain-chroma/langchain-community/langchain），向量库功能将不可用: %s; %s",
            _CHROMA_IMPORT_ERROR,
            _CHROMA_IMPORT_ERROR_FALLBACK,
        )
    else:
        logger.warning(
            "Chroma 依赖导入失败（langchain-chroma/langchain-community/langchain），向量库功能将不可用: %s",
            _CHROMA_IMPORT_ERROR,
        )
if "_OPENAI_EMBEDDINGS_IMPORT_ERROR" in globals() and _OPENAI_EMBEDDINGS_IMPORT_ERROR is not None:
    if (
        "_OPENAI_EMBEDDINGS_IMPORT_ERROR_FALLBACK" in globals()
        and _OPENAI_EMBEDDINGS_IMPORT_ERROR_FALLBACK is not None
    ):
        logger.warning(
            "OpenAIEmbeddings 依赖导入失败（langchain-openai/langchain），API embedding 将不可用: %s; %s",
            _OPENAI_EMBEDDINGS_IMPORT_ERROR,
            _OPENAI_EMBEDDINGS_IMPORT_ERROR_FALLBACK,
        )
    else:
        logger.warning(
            "OpenAIEmbeddings 依赖导入失败（langchain-openai/langchain），API embedding 将不可用: %s",
            _OPENAI_EMBEDDINGS_IMPORT_ERROR,
        )

# 尝试导入本地 embedding 支持
try:
    from src.utils.local_embeddings import LocalEmbeddings, SENTENCE_TRANSFORMERS_AVAILABLE
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False
    logger.debug("本地 embedding 模块未找到，将使用 API embedding")

_DEFAULT_LOCAL_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
_LOCAL_MODEL_MAP = {
    "BAAI/bge-large-zh-v1.5": "BAAI/bge-large-zh-v1.5",
    "BAAI/bge-m3": "BAAI/bge-m3",
    "Qwen/Qwen3-Embedding-8B": _DEFAULT_LOCAL_MODEL,  # 替代
    "text-embedding-ada-002": "sentence-transformers/all-MiniLM-L6-v2",  # 替代
}
_EMBEDDING_CACHE_DIR = "data/cache/embeddings"


def _resolve_local_model(model: str) -> str:
    return _LOCAL_MODEL_MAP.get(model, _DEFAULT_LOCAL_MODEL)


@lru_cache(maxsize=8)
def _get_local_embedding_function(model_name: str, enable_cache: bool) -> "LocalEmbeddings":
    """
    复用本地 embedding 模型实例，避免为每个 collection 重复加载 SentenceTransformer。
    """
    if not SENTENCE_TRANSFORMERS_AVAILABLE:
        raise ImportError("sentence-transformers 未安装，无法使用本地 embedding")
    return LocalEmbeddings(
        model_name=model_name,
        cache_dir=_EMBEDDING_CACHE_DIR,
        device=None,  # 自动检测最优设备（GPU/CPU）
        enable_cache=enable_cache,
    )


@lru_cache(maxsize=8)
def _get_openai_embedding_function(model: str, api_base: str, api_key: str) -> "OpenAIEmbeddings":
    """复用 API embedding 客户端，减少重复初始化开销。"""
    if OpenAIEmbeddings is None:
        raise ImportError(
            "OpenAIEmbeddings 依赖未就绪，请安装 `langchain-openai`（或升级/安装 langchain）"
        ) from (_OPENAI_EMBEDDINGS_IMPORT_ERROR or _OPENAI_EMBEDDINGS_IMPORT_ERROR_FALLBACK)

    from src.llm.factory import _normalize_openai_base_url

    embeddings_kwargs = {
        "model": model,
        "api_key": api_key,
    }

    normalized_base_url = _normalize_openai_base_url(api_base)
    if normalized_base_url:
        embeddings_kwargs["base_url"] = normalized_base_url

    try:
        return OpenAIEmbeddings(**embeddings_kwargs)
    except TypeError:
        if "base_url" in embeddings_kwargs:
            fallback_kwargs = dict(embeddings_kwargs)
            base = fallback_kwargs.pop("base_url", None)
            if base:
                fallback_kwargs["openai_api_base"] = base
            return OpenAIEmbeddings(**fallback_kwargs)
        raise


def create_chroma_vectorstore(
    collection_name: str,
    persist_directory: str,
    embedding_model: Optional[str] = None,
    embedding_api_base: Optional[str] = None,
    api_key: Optional[str] = None,
    use_local_embedding: bool = False,
    enable_cache: bool = True,
) -> Optional[Chroma]:
    """
    创建ChromaDB向量存储实例（统一初始化函数）

    Args:
        collection_name: 集合名称
        persist_directory: 持久化目录
        embedding_model: 嵌入模型名称，默认使用配置中的模型
        embedding_api_base: 嵌入API地址，默认使用配置中的地址
        api_key: API密钥，默认使用配置中的密钥
        use_local_embedding: 是否使用本地 embedding 模型
        enable_cache: 是否启用 embedding 缓存

    Returns:
        Optional[Chroma]: ChromaDB实例，失败返回None
    """
    try:
        if Chroma is None:
            logger.error(
                "Chroma 向量库依赖未就绪，请安装 `langchain-chroma` 或 `langchain-community`"
            )
            return None

        # 确保目录存在
        persist_dir = Path(persist_directory)
        persist_dir.mkdir(parents=True, exist_ok=True)

        # 确定嵌入模型参数
        model = str(embedding_model or settings.embedding_model or "").strip()
        api_base = str(
            embedding_api_base or settings.embedding_api_base or settings.llm.api or ""
        ).strip()
        key = str(api_key or settings.llm.key or "").strip()

        # 选择 embedding 方案
        if use_local_embedding and SENTENCE_TRANSFORMERS_AVAILABLE:
            # 使用本地 embedding 模型
            logger.info("使用本地 embedding 模型: %s", model)
            local_model = _resolve_local_model(model)
            embedding_function = _get_local_embedding_function(local_model, bool(enable_cache))
        else:
            # 使用 API embedding
            logger.info("使用 API embedding 模型: %s", model)
            if OpenAIEmbeddings is None:
                logger.error(
                    "OpenAIEmbeddings 依赖未就绪，请安装 `langchain-openai`（或升级/安装 langchain）"
                )
                return None

            if not key:
                logger.error("embedding API key 未配置，无法初始化 API embedding")
                return None
            embedding_function = _get_openai_embedding_function(model, api_base, key)

        # 禁用 ChromaDB telemetry（避免版本兼容性问题）
        from chromadb.config import Settings as ChromaSettings

        chroma_settings = ChromaSettings(
            anonymized_telemetry=False,
            allow_reset=True,
        )

        # 创建向量存储
        vectorstore = Chroma(
            collection_name=collection_name,
            embedding_function=embedding_function,
            persist_directory=str(persist_dir),
            client_settings=chroma_settings,
        )

        embedding_type = (
            "本地" if use_local_embedding and SENTENCE_TRANSFORMERS_AVAILABLE else "API"
        )
        logger.info(
            "ChromaDB向量存储初始化成功: %s (路径: %s, 模型: %s, 类型: %s)",
            collection_name,
            persist_dir,
            model,
            embedding_type,
        )

        return vectorstore

    except Exception as e:
        logger.error("ChromaDB向量存储初始化失败 (%s): %s", collection_name, e)
        return None


def get_collection_count(vectorstore: Optional[Chroma]) -> int:
    """
    获取集合中的记忆数量

    Args:
        vectorstore: ChromaDB实例

    Returns:
        int: 记忆数量，失败返回0
    """
    if vectorstore is None:
        return 0

    try:
        collection = vectorstore._collection
        return collection.count()
    except (AttributeError, RuntimeError) as e:
        logger.debug(f"无法获取记忆数量: {e}")
        return 0


def optimize_chroma_settings() -> dict:
    """
    获取优化的ChromaDB设置

    Returns:
        dict: ChromaDB设置字典
    """
    from chromadb.config import Settings as ChromaSettings

    return ChromaSettings(
        anonymized_telemetry=False,
        allow_reset=True,
        # 性能优化设置
        chroma_db_impl="duckdb+parquet",  # 使用DuckDB后端提升性能
        persist_directory=None,  # 由Chroma类管理
    )
