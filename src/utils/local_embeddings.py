"""
本地 Embedding 模型支持 (v2.48.12 - GPU加速优化)

支持本地 sentence-transformers 模型，避免 API 调用延迟。
支持GPU加速，自动检测CUDA可用性。

作者: MintChat Team
日期: 2025-11-18
"""

from typing import List, Optional
import time

from src.utils.logger import get_logger
from src.utils.embedding_cache import EmbeddingCache

logger = get_logger(__name__)

# 尝试导入 sentence-transformers
try:
    from sentence_transformers import SentenceTransformer

    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False
    logger.warning(
        "sentence-transformers 未安装，本地 embedding 功能不可用。"
        "安装方法: pip install sentence-transformers"
    )

# 尝试导入 torch 用于 GPU 检测
try:
    import torch
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    logger.debug("PyTorch 未安装，无法检测 GPU")


def get_optimal_device() -> str:
    """
    获取最优设备（智能GPU检测）

    Returns:
        设备名称（cuda/cpu）
    """
    if not TORCH_AVAILABLE:
        return "cpu"

    if torch.cuda.is_available():
        device_count = torch.cuda.device_count()
        device_name = torch.cuda.get_device_name(0)
        logger.info(f"检测到 {device_count} 个 CUDA 设备: {device_name}")
        return "cuda"
    else:
        logger.info("未检测到 CUDA 设备，使用 CPU")
        return "cpu"


class LocalEmbeddings:
    """本地 Embedding 模型包装器（支持GPU加速）"""

    def __init__(
        self,
        model_name: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        cache_dir: str = "data/cache/embeddings",
        device: Optional[str] = None,
        enable_cache: bool = True,
        auto_gpu: bool = True,
    ):
        """
        初始化本地 embedding 模型

        Args:
            model_name: 模型名称（HuggingFace 模型 ID）
            cache_dir: 缓存目录
            device: 设备（cpu/cuda），None时自动检测
            enable_cache: 是否启用缓存
            auto_gpu: 是否自动启用GPU（默认True）
        """
        if not SENTENCE_TRANSFORMERS_AVAILABLE:
            raise ImportError(
                "sentence-transformers 未安装，无法使用本地 embedding 功能。"
                "安装方法: pip install sentence-transformers"
            )

        # 智能设备选择
        if device is None and auto_gpu:
            device = get_optimal_device()
        elif device is None:
            device = "cpu"

        self.model_name = model_name
        self.device = device
        self.enable_cache = enable_cache

        # 初始化缓存
        if enable_cache:
            self.cache = EmbeddingCache(cache_dir=cache_dir)
        else:
            self.cache = None

        # 加载模型
        logger.info(f"正在加载本地 embedding 模型: {model_name} (设备: {device})")
        start_time = time.perf_counter()

        try:
            self.model = SentenceTransformer(model_name, device=device)
            load_time = (time.perf_counter() - start_time) * 1000

            # 显示GPU信息
            gpu_info = ""
            if device == "cuda" and TORCH_AVAILABLE and torch.cuda.is_available():
                gpu_info = f", GPU: {torch.cuda.get_device_name(0)}"

            logger.info(
                f"本地 embedding 模型加载成功: {model_name} "
                f"(耗时: {load_time:.2f}ms, 设备: {device}{gpu_info})"
            )
        except Exception as e:
            logger.error(f"加载本地 embedding 模型失败: {e}")
            raise

        # 性能统计
        self.total_embeddings = 0
        self.total_time_ms = 0.0

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """
        批量生成文档 embeddings

        Args:
            texts: 文本列表

        Returns:
            List[List[float]]: embedding 向量列表
        """
        if not texts:
            return []

        results = []
        uncached_texts = []
        uncached_indices = []

        # 1. 检查缓存
        if self.enable_cache and self.cache:
            for i, text in enumerate(texts):
                cached_embedding = self.cache.get(text, self.model_name)
                if cached_embedding is not None:
                    results.append(cached_embedding)
                else:
                    uncached_texts.append(text)
                    uncached_indices.append(i)
        else:
            uncached_texts = texts
            uncached_indices = list(range(len(texts)))

        # 2. 生成未缓存的 embeddings（GPU加速批量处理）
        if uncached_texts:
            start_time = time.perf_counter()

            try:
                # GPU加速优化：使用批量处理
                batch_size = 32 if self.device == "cuda" else 16

                embeddings = self.model.encode(
                    uncached_texts,
                    convert_to_numpy=True,
                    show_progress_bar=False,
                    batch_size=batch_size,  # GPU加速批量处理
                    normalize_embeddings=True,  # 归一化提升检索精度
                )
                embeddings_list = [emb.tolist() for emb in embeddings]

                # 保存到缓存
                if self.enable_cache and self.cache:
                    for text, embedding in zip(uncached_texts, embeddings_list):
                        self.cache.set(text, self.model_name, embedding)

                # 插入到结果中
                for idx, embedding in zip(uncached_indices, embeddings_list):
                    results.insert(idx, embedding)

                # 性能统计
                elapsed_ms = (time.perf_counter() - start_time) * 1000
                self.total_embeddings += len(uncached_texts)
                self.total_time_ms += elapsed_ms

                # 显示GPU加速信息
                device_info = f"GPU加速" if self.device == "cuda" else "CPU"
                logger.debug(
                    f"生成 {len(uncached_texts)} 个 embeddings ({device_info}): {elapsed_ms:.2f}ms "
                    f"({elapsed_ms / len(uncached_texts):.2f}ms/个, batch_size={batch_size})"
                )

            except Exception as e:
                logger.error(f"生成 embeddings 失败: {e}")
                raise

        return results

    def embed_query(self, text: str) -> List[float]:
        """
        生成查询 embedding

        Args:
            text: 查询文本

        Returns:
            List[float]: embedding 向量
        """
        # 1. 检查缓存
        if self.enable_cache and self.cache:
            cached_embedding = self.cache.get(text, self.model_name)
            if cached_embedding is not None:
                return cached_embedding

        # 2. 生成 embedding（GPU加速）
        start_time = time.perf_counter()

        try:
            embedding = self.model.encode(
                text,
                convert_to_numpy=True,
                show_progress_bar=False,
                normalize_embeddings=True,  # 归一化提升检索精度
            )
            embedding_list = embedding.tolist()

            # 保存到缓存
            if self.enable_cache and self.cache:
                self.cache.set(text, self.model_name, embedding_list)

            # 性能统计
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            self.total_embeddings += 1
            self.total_time_ms += elapsed_ms

            # 显示GPU加速信息
            device_info = f"GPU加速" if self.device == "cuda" else "CPU"
            logger.debug(f"生成 1 个 embedding ({device_info}): {elapsed_ms:.2f}ms")

            return embedding_list

        except Exception as e:
            logger.error(f"生成 embedding 失败: {e}")
            raise

    def get_stats(self) -> dict:
        """获取性能统计"""
        avg_time = (
            self.total_time_ms / self.total_embeddings
            if self.total_embeddings > 0
            else 0
        )

        stats = {
            "total_embeddings": self.total_embeddings,
            "total_time_ms": f"{self.total_time_ms:.2f}",
            "avg_time_ms": f"{avg_time:.2f}",
        }

        if self.enable_cache and self.cache:
            stats["cache"] = self.cache.get_stats()

        return stats

