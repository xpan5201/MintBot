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
        model = embedding_model or settings.embedding_model
        api_base = embedding_api_base or settings.embedding_api_base or settings.llm.api
        key = api_key or settings.llm.key

        # 选择 embedding 方案
        if use_local_embedding and SENTENCE_TRANSFORMERS_AVAILABLE:
            # 使用本地 embedding 模型
            logger.info("使用本地 embedding 模型: %s", model)

            # 本地模型映射（API 模型名 -> 本地模型名）
            local_model_map = {
                "BAAI/bge-large-zh-v1.5": "BAAI/bge-large-zh-v1.5",
                "BAAI/bge-m3": "BAAI/bge-m3",
                "Qwen/Qwen3-Embedding-8B": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",  # 替代
                "text-embedding-ada-002": "sentence-transformers/all-MiniLM-L6-v2",  # 替代
            }

            local_model = local_model_map.get(
                model,
                "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"  # 默认
            )

            embedding_function = LocalEmbeddings(
                model_name=local_model,
                cache_dir="data/cache/embeddings",
                device="cpu",  # TODO: 支持 GPU
                enable_cache=enable_cache,
            )
        else:
            # 使用 API embedding
            logger.info("使用 API embedding 模型: %s", model)
            if OpenAIEmbeddings is None:
                logger.error(
                    "OpenAIEmbeddings 依赖未就绪，请安装 `langchain-openai`（或升级/安装 langchain）"
                )
                return None

            embeddings_kwargs = {
                "model": model,
                "api_key": key,
            }

            # 如果不是 OpenAI 官方 API，设置 base_url
            if "openai.com" not in api_base.lower():
                embeddings_kwargs["base_url"] = api_base

            embedding_function = OpenAIEmbeddings(**embeddings_kwargs)

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

        embedding_type = "本地" if use_local_embedding and SENTENCE_TRANSFORMERS_AVAILABLE else "API"
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
