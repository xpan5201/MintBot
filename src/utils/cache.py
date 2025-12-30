"""
缓存系统

提供响应缓存功能，提升性能并降低 API 调用成本。
"""

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Optional, Dict

from src.utils.logger import get_logger

logger = get_logger(__name__)


class ResponseCache:
    """响应缓存系统"""

    def __init__(
        self,
        cache_dir: Optional[Path] = None,
        ttl: int = 3600,  # 默认缓存 1 小时
        max_size: int = 1000,  # 最大缓存条目数
        auto_cleanup: bool = True,  # v2.28.0: 自动清理过期缓存
    ):
        """
        初始化缓存系统 (v2.28.0: 增强自动清理)

        Args:
            cache_dir: 缓存目录
            ttl: 缓存过期时间（秒）
            max_size: 最大缓存条目数
            auto_cleanup: 是否自动清理过期缓存
        """
        self.cache_dir = Path(cache_dir or "data/cache")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.ttl = ttl
        self.max_size = max_size
        self.auto_cleanup = auto_cleanup
        self.cache_file = self.cache_dir / "response_cache.json"
        self.cache: Dict[str, Dict[str, Any]] = {}
        self._load_cache()

        # v2.28.0: 初始化时自动清理过期缓存
        if self.auto_cleanup:
            cleaned = self.cleanup_expired()
            if cleaned > 0:
                logger.info(f"初始化时清理了 {cleaned} 条过期缓存")

        logger.info(
            f"缓存系统初始化完成，TTL: {ttl}秒，最大条目: {max_size}，自动清理: {auto_cleanup}"
        )

    def _load_cache(self) -> None:
        """从文件加载缓存"""
        try:
            if self.cache_file.exists():
                with open(self.cache_file, "r", encoding="utf-8") as f:
                    self.cache = json.load(f)
                logger.info(f"已加载 {len(self.cache)} 条缓存记录")
        except Exception as e:
            logger.warning(f"加载缓存失败: {e}")
            self.cache = {}

    def _save_cache(self) -> None:
        """保存缓存到文件"""
        try:
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(self.cache, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存缓存失败: {e}")

    def _generate_key(self, message: str, context: Optional[str] = None) -> str:
        """
        生成缓存键

        Args:
            message: 用户消息
            context: 上下文信息

        Returns:
            str: 缓存键（MD5 哈希）
        """
        content = message
        if context:
            content += f"|{context}"
        return hashlib.md5(content.encode()).hexdigest()

    def get(
        self,
        message: str,
        context: Optional[str] = None,
    ) -> Optional[str]:
        """
        获取缓存的响应 (v2.28.0: 增强自动清理)

        Args:
            message: 用户消息
            context: 上下文信息

        Returns:
            Optional[str]: 缓存的响应，如果不存在或已过期则返回 None
        """
        # v2.28.0: 定期自动清理过期缓存（每100次查询清理一次）
        if self.auto_cleanup and hasattr(self, "_query_count"):
            self._query_count += 1
            if self._query_count >= 100:
                self.cleanup_expired()
                self._query_count = 0
        elif not hasattr(self, "_query_count"):
            self._query_count = 0

        key = self._generate_key(message, context)

        if key not in self.cache:
            return None

        entry = self.cache[key]
        timestamp = entry.get("timestamp", 0)
        current_time = time.time()

        # 检查是否过期
        if current_time - timestamp > self.ttl:
            logger.debug(f"缓存已过期: {key}")
            del self.cache[key]
            return None

        logger.info(f"缓存命中: {key}")
        entry["hits"] = entry.get("hits", 0) + 1
        entry["last_access"] = current_time
        return entry.get("response")

    def set(
        self,
        message: str,
        response: str,
        context: Optional[str] = None,
    ) -> None:
        """
        设置缓存

        Args:
            message: 用户消息
            response: AI 响应
            context: 上下文信息
        """
        key = self._generate_key(message, context)

        # 如果缓存已满，删除最旧的条目
        if len(self.cache) >= self.max_size:
            self._evict_oldest()

        self.cache[key] = {
            "message": message,
            "response": response,
            "context": context,
            "timestamp": time.time(),
            "hits": 0,
            "last_access": time.time(),
        }

        logger.debug(f"缓存已设置: {key}")
        self._save_cache()

    def _evict_oldest(self) -> None:
        """删除最旧的缓存条目"""
        if not self.cache:
            return

        # 找到最旧的条目
        oldest_key = min(
            self.cache.keys(),
            key=lambda k: self.cache[k].get("last_access", 0),
        )

        del self.cache[oldest_key]
        logger.debug(f"已删除最旧的缓存条目: {oldest_key}")

    def clear(self) -> None:
        """清空所有缓存"""
        self.cache = {}
        self._save_cache()
        logger.info("缓存已清空")

    def get_stats(self) -> Dict[str, Any]:
        """
        获取缓存统计信息

        Returns:
            Dict[str, Any]: 统计信息
        """
        total_hits = sum(entry.get("hits", 0) for entry in self.cache.values())
        total_entries = len(self.cache)

        # 计算过期条目数
        current_time = time.time()
        expired_count = sum(
            1
            for entry in self.cache.values()
            if current_time - entry.get("timestamp", 0) > self.ttl
        )

        return {
            "total_entries": total_entries,
            "total_hits": total_hits,
            "expired_entries": expired_count,
            "max_size": self.max_size,
            "ttl": self.ttl,
            "cache_file": str(self.cache_file),
        }

    def cleanup_expired(self) -> int:
        """
        清理过期的缓存条目

        Returns:
            int: 清理的条目数
        """
        current_time = time.time()
        expired_keys = [
            key
            for key, entry in self.cache.items()
            if current_time - entry.get("timestamp", 0) > self.ttl
        ]

        for key in expired_keys:
            del self.cache[key]

        if expired_keys:
            self._save_cache()
            logger.info(f"已清理 {len(expired_keys)} 条过期缓存")

        return len(expired_keys)


class SemanticCache:
    """语义缓存 - 基于相似度的缓存"""

    def __init__(
        self,
        similarity_threshold: float = 0.9,
        ttl: int = 3600,
    ):
        """
        初始化语义缓存

        Args:
            similarity_threshold: 相似度阈值（0-1）
            ttl: 缓存过期时间（秒）
        """
        self.similarity_threshold = similarity_threshold
        self.ttl = ttl
        self.cache: list = []
        logger.info(f"语义缓存初始化完成，相似度阈值: {similarity_threshold}")

    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """
        计算两个文本的相似度（简单实现）

        Args:
            text1: 文本1
            text2: 文本2

        Returns:
            float: 相似度（0-1）
        """
        # 简单的字符级相似度
        # 实际应用中可以使用更复杂的方法，如词向量、BERT 等
        set1 = set(text1)
        set2 = set(text2)

        if not set1 or not set2:
            return 0.0

        intersection = len(set1 & set2)
        union = len(set1 | set2)

        return intersection / union if union > 0 else 0.0

    def get(self, message: str) -> Optional[str]:
        """
        获取语义相似的缓存响应

        Args:
            message: 用户消息

        Returns:
            Optional[str]: 缓存的响应
        """
        current_time = time.time()

        for entry in self.cache:
            # 检查是否过期
            if current_time - entry["timestamp"] > self.ttl:
                continue

            # 计算相似度
            similarity = self._calculate_similarity(message, entry["message"])

            if similarity >= self.similarity_threshold:
                logger.info(f"语义缓存命中，相似度: {similarity:.2f}")
                entry["hits"] += 1
                return entry["response"]

        return None

    def set(self, message: str, response: str) -> None:
        """
        设置语义缓存

        Args:
            message: 用户消息
            response: AI 响应
        """
        self.cache.append(
            {
                "message": message,
                "response": response,
                "timestamp": time.time(),
                "hits": 0,
            }
        )

        logger.debug(f"语义缓存已设置，当前条目数: {len(self.cache)}")

    def clear(self) -> None:
        """清空语义缓存"""
        self.cache = []
        logger.info("语义缓存已清空")


# 创建全局缓存实例
response_cache = ResponseCache()
semantic_cache = SemanticCache()
