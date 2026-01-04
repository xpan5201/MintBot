"""
ChromaDB 辅助工具模块 (v2.30.27)

提供 ChromaDB 初始化和配置的公共函数，支持本地 embedding 和缓存。

优化内容:
- 支持本地 sentence-transformers 模型
- 支持 embedding 缓存
- 自动选择最优 embedding 方案
- 历史：移除第三方 wrapper 依赖，直连 chromadb + OpenAI-compatible embeddings

作者: MintChat Team
日期: 2025-11-16
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from threading import Lock, RLock
from typing import Any, Optional, Protocol
from uuid import uuid4

from src.config.settings import settings
from src.utils.logger import get_logger

logger = get_logger(__name__)

try:
    import chromadb
    from chromadb.config import Settings as ChromaSettings

    _CHROMADB_IMPORT_ERROR: Optional[BaseException] = None
except Exception as exc:  # pragma: no cover - 环境依赖差异
    chromadb = None  # type: ignore[assignment]
    ChromaSettings = None  # type: ignore[assignment]
    _CHROMADB_IMPORT_ERROR = exc

try:
    from openai import OpenAI

    _OPENAI_IMPORT_ERROR: Optional[BaseException] = None
except Exception as exc:  # pragma: no cover - 环境依赖差异
    OpenAI = None  # type: ignore[assignment]
    _OPENAI_IMPORT_ERROR = exc

# 尝试导入本地 embedding 支持
try:
    from src.utils.local_embeddings import LocalEmbeddings, SENTENCE_TRANSFORMERS_AVAILABLE
except ImportError:  # pragma: no cover - 可选依赖
    SENTENCE_TRANSFORMERS_AVAILABLE = False
    logger.debug("本地 embedding 模块未找到，将使用 API embedding")


class EmbeddingFunction(Protocol):
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError

    def embed_query(self, text: str) -> list[float]:
        raise NotImplementedError


@dataclass(slots=True)
class Document:
    page_content: str
    metadata: dict[str, Any]


class OpenAIEmbeddingClient:
    def __init__(
        self,
        *,
        model: str,
        api_key: str,
        base_url: str | None = None,
        enable_cache: bool = True,
    ) -> None:
        if OpenAI is None:
            raise ImportError("openai SDK 未安装，无法使用 API embedding") from _OPENAI_IMPORT_ERROR
        if not model:
            raise ValueError("embedding model 不能为空")
        if not api_key:
            raise ValueError("embedding API key 不能为空")

        client_kwargs: dict[str, Any] = {"api_key": api_key}
        if base_url:
            client_kwargs["base_url"] = base_url

        # Embeddings 请求通常属于“非关键热路径”，但一旦阻塞会显著拉高首包延迟或导致后台线程堆积。
        # 这里默认设置一个更稳健的 timeout/retry，并允许通过 llm.extra_config 覆盖（无需新增配置键）。  # noqa: E501
        extra = getattr(settings.llm, "extra_config", {}) or {}
        try:
            timeout_s = float(
                extra.get("embedding_timeout_s")
                or extra.get("timeout_s")
                or extra.get("timeout")
                or 30.0
            )
        except Exception:
            timeout_s = 30.0
        try:
            max_retries = int(extra.get("embedding_max_retries") or extra.get("max_retries") or 2)
        except Exception:
            max_retries = 2
        client_kwargs.setdefault("timeout", timeout_s)
        client_kwargs.setdefault("max_retries", max_retries)

        self._client = OpenAI(**client_kwargs)
        self._model = model
        self._enable_cache = bool(enable_cache)
        self._cache_lock = Lock()
        self._cache: OrderedDict[str, list[float]] = OrderedDict()
        self._cache_max = 1024

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        normalized = [str(t) for t in texts]
        out: list[list[float] | None] = [None] * len(normalized)
        missing_map: dict[str, list[int]] = {}

        if self._enable_cache:
            with self._cache_lock:
                for idx, text in enumerate(normalized):
                    cached = self._cache.get(text)
                    if cached is not None:
                        self._cache.move_to_end(text)
                        out[idx] = cached
                    else:
                        missing_map.setdefault(text, []).append(idx)
        else:
            for idx, text in enumerate(normalized):
                missing_map.setdefault(text, []).append(idx)

        if missing_map:
            missing_texts = list(missing_map.keys())
            resp = self._client.embeddings.create(model=self._model, input=missing_texts)
            data = sorted(resp.data, key=lambda item: int(getattr(item, "index", 0)))
            vectors = [list(item.embedding) for item in data]
            if len(vectors) != len(missing_texts):
                raise RuntimeError(
                    f"embedding 返回数量异常: expected={len(missing_texts)} got={len(vectors)}"
                )

            if self._enable_cache:
                with self._cache_lock:
                    for text, vec in zip(missing_texts, vectors):
                        for idx in missing_map.get(text, []):
                            out[idx] = vec
                        self._cache[text] = vec
                        self._cache.move_to_end(text)
                    while len(self._cache) > self._cache_max:
                        self._cache.popitem(last=False)
            else:
                for text, vec in zip(missing_texts, vectors):
                    for idx in missing_map.get(text, []):
                        out[idx] = vec

        return [vec if vec is not None else [] for vec in out]

    def embed_query(self, text: str) -> list[float]:
        vectors = self.embed_documents([text])
        return vectors[0] if vectors else []


class ChromaVectorStore:
    def __init__(
        self,
        *,
        collection_name: str,
        persist_directory: str,
        embedding_function: EmbeddingFunction,
        client_settings: Any,
    ) -> None:
        if chromadb is None:
            raise ImportError("chromadb 未安装，无法使用向量库") from _CHROMADB_IMPORT_ERROR

        self.collection_name = collection_name
        self.persist_directory = persist_directory
        self._embedding_function = embedding_function
        self._client = chromadb.PersistentClient(path=persist_directory, settings=client_settings)
        self._collection = self._client.get_or_create_collection(name=collection_name)
        self._lock = RLock()

    def add_texts(
        self,
        *,
        texts: list[str],
        metadatas: list[dict[str, Any]],
        ids: list[str] | None = None,
    ) -> None:
        if not texts:
            return
        if len(texts) != len(metadatas):
            raise ValueError("texts 与 metadatas 长度不一致")

        if ids is None:
            ids = [uuid4().hex for _ in texts]
        if len(ids) != len(texts):
            raise ValueError("ids 与 texts 长度不一致")

        embeddings = self._embedding_function.embed_documents(texts)
        with self._lock:
            self._collection.add(
                ids=[str(x) for x in ids],
                documents=[str(x) for x in texts],
                metadatas=[dict(x or {}) for x in metadatas],
                embeddings=embeddings,
            )

    def similarity_search_with_score(
        self,
        query: str,
        *,
        k: int = 5,
        filter: dict[str, Any] | None = None,  # noqa: A002 - keep compat with old call-sites
    ) -> list[tuple[Document, float]]:
        if k <= 0:
            return []

        try:
            query_embedding = self._embedding_function.embed_query(query)
        except Exception as exc:  # pragma: no cover - 依赖/网络差异
            logger.debug("embedding query 失败，将跳过相似度检索: %s", exc)
            return []
        if not query_embedding:
            return []

        try:
            with self._lock:
                result = self._collection.query(
                    query_embeddings=[query_embedding],
                    n_results=int(k),
                    where=filter,
                    include=["documents", "metadatas", "distances"],
                )
        except Exception as exc:  # pragma: no cover - 依赖/存储差异
            logger.debug("chroma query 失败，将跳过相似度检索: %s", exc)
            return []

        docs = (result.get("documents") or [[]])[0] or []
        metas = (result.get("metadatas") or [[]])[0] or []
        dists = (result.get("distances") or [[]])[0] or []

        out: list[tuple[Document, float]] = []
        for doc, meta, dist in zip(docs, metas, dists):
            out.append((Document(page_content=str(doc), metadata=dict(meta or {})), float(dist)))
        return out

    def get(self, **kwargs: Any) -> dict[str, Any]:
        with self._lock:
            return dict(self._collection.get(**kwargs))

    def delete_collection(self) -> None:
        with self._lock:
            self._client.delete_collection(name=self.collection_name)


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
def _get_openai_embedding_function(
    model: str, api_base: str, api_key: str, enable_cache: bool
) -> OpenAIEmbeddingClient:
    """复用 API embedding 客户端，减少重复初始化开销。"""
    if OpenAI is None:
        raise ImportError("openai SDK 未就绪，无法使用 API embedding") from _OPENAI_IMPORT_ERROR

    from src.llm.factory import _normalize_openai_base_url

    normalized_base_url = _normalize_openai_base_url(api_base)
    if normalized_base_url:
        return OpenAIEmbeddingClient(
            model=model,
            api_key=api_key,
            base_url=normalized_base_url,
            enable_cache=bool(enable_cache),
        )
    return OpenAIEmbeddingClient(model=model, api_key=api_key, enable_cache=bool(enable_cache))


def create_chroma_vectorstore(
    collection_name: str,
    persist_directory: str,
    embedding_model: Optional[str] = None,
    embedding_api_base: Optional[str] = None,
    api_key: Optional[str] = None,
    use_local_embedding: bool = False,
    enable_cache: bool = True,
) -> Optional[ChromaVectorStore]:
    """
    创建 ChromaDB 向量存储实例（统一初始化函数）

    Args:
        collection_name: 集合名称
        persist_directory: 持久化目录
        embedding_model: 嵌入模型名称，默认使用配置中的模型
        embedding_api_base: 嵌入API地址，默认使用配置中的地址
        api_key: API密钥，默认使用配置中的密钥
        use_local_embedding: 是否使用本地 embedding 模型
        enable_cache: 是否启用 embedding 缓存

    Returns:
        Optional[ChromaVectorStore]: 向量库实例，失败返回 None
    """
    if chromadb is None or ChromaSettings is None:
        logger.error("ChromaDB 依赖未就绪，请安装 `chromadb`: %s", _CHROMADB_IMPORT_ERROR)
        return None

    try:
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
        embedding_function: EmbeddingFunction
        if use_local_embedding and SENTENCE_TRANSFORMERS_AVAILABLE:
            # 使用本地 embedding 模型
            logger.info("使用本地 embedding 模型: %s", model)
            local_model = _resolve_local_model(model)
            embedding_function = _get_local_embedding_function(local_model, bool(enable_cache))
        else:
            # 使用 API embedding
            logger.info("使用 API embedding 模型: %s", model)
            if OpenAI is None:
                logger.error(
                    "openai SDK 未就绪，无法初始化 API embedding: %s", _OPENAI_IMPORT_ERROR
                )
                return None
            if not key:
                logger.error("embedding API key 未配置，无法初始化 API embedding")
                return None
            if not model:
                logger.error("embedding model 未配置，无法初始化 API embedding")
                return None
            embedding_function = _get_openai_embedding_function(
                model, api_base, key, bool(enable_cache)
            )

        # 禁用 ChromaDB telemetry（避免版本兼容性问题）
        chroma_settings = ChromaSettings(
            anonymized_telemetry=False,
            allow_reset=True,
        )

        vectorstore = ChromaVectorStore(
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


def get_collection_count(vectorstore: Optional[ChromaVectorStore]) -> int:
    """
    获取集合中的记忆数量

    Args:
        vectorstore: 向量库实例

    Returns:
        int: 记忆数量，失败返回0
    """
    if vectorstore is None:
        return 0

    try:
        return int(vectorstore._collection.count())
    except (AttributeError, RuntimeError) as e:
        logger.debug("无法获取记忆数量: %s", e)
        return 0


def optimize_chroma_settings() -> Any:
    """
    获取优化的 ChromaDB Settings（保守版本，避免使用已废弃/不兼容字段）
    """
    if ChromaSettings is None:
        raise ImportError("chromadb 未安装，无法创建 Settings") from _CHROMADB_IMPORT_ERROR

    return ChromaSettings(
        anonymized_telemetry=False,
        allow_reset=True,
    )
