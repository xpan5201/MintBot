"""
智能上下文压缩系统

实现上下文智能压缩，减少 token 消耗，提升响应速度。
这是 v2.5 的核心性能优化功能。
"""

import re
from typing import Dict, List

from src.utils.logger import get_logger

logger = get_logger(__name__)

# v2.29.10: 预编译正则表达式，提升性能
_CHINESE_CHARS_PATTERN = re.compile(r"[\u4e00-\u9fff]")
_WHITESPACE_PATTERN = re.compile(r"\s+")
_PUNCTUATION_PATTERN = re.compile(r"([。！？~…])\1+")
_MEOW_PATTERN = re.compile(r"(喵~?){3,}")
_IMPORTANT_KEYWORDS = (
    "名字",
    "姓名",
    "叫",
    "生日",
    "年龄",
    "住址",
    "地址",
    "明天",
    "后天",
    "下周",
    "下个月",
    "约定",
    "提醒",
    "爱",
    "喜欢",
    "讨厌",
    "生气",
    "开心",
    "难过",
    "想念",
    "重要",
    "记住",
    "别忘",
    "一定要",
    "必须",
)


class ContextCompressor:
    """
    智能上下文压缩器

    功能：
    1. 移除冗余信息
    2. 合并相似内容
    3. 提取关键信息
    4. 智能截断
    """

    def __init__(self, max_tokens: int = 2000):
        """
        初始化上下文压缩器

        Args:
            max_tokens: 最大 token 数量（估算）
        """
        self.max_tokens = max_tokens
        logger.info(f"上下文压缩器初始化完成，最大 token: {max_tokens}")

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """估算文本的 token 数量（中文约1.5字符/token，英文约4字符/token）"""
        chinese_chars = sum(1 for _ in _CHINESE_CHARS_PATTERN.finditer(text))
        other_chars = len(text) - chinese_chars
        return int(chinese_chars / 1.5 + other_chars / 4)

    @staticmethod
    def remove_redundancy(text: str) -> str:
        """移除冗余信息（空白、重复标点、多余的喵）"""
        text = _WHITESPACE_PATTERN.sub(" ", text)
        text = _PUNCTUATION_PATTERN.sub(r"\1", text)
        text = _MEOW_PATTERN.sub("喵~", text)
        return text.strip()

    def extract_key_info(self, messages: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """提取关键信息（保留最近3轮对话+重要历史消息）"""
        if len(messages) <= 6:
            return messages

        recent_messages = messages[-6:]
        important_messages = [
            msg for msg in messages[:-6]
            if self._is_important(msg.get("content", ""))
        ]
        compressed = important_messages + recent_messages
        logger.debug(f"上下文压缩: {len(messages)} -> {len(compressed)} 条消息")
        return compressed

    @staticmethod
    def _is_important(text: str) -> bool:
        """判断文本是否包含重要信息"""
        return any(keyword in text for keyword in _IMPORTANT_KEYWORDS)

    def compress_context(
        self,
        messages: List[Dict[str, str]],
        additional_context: str = "",
    ) -> tuple[List[Dict[str, str]], str]:
        """压缩上下文（提取关键消息+移除冗余）"""
        compressed_messages = self.extract_key_info(messages)

        for msg in compressed_messages:
            if "content" in msg:
                msg["content"] = self.remove_redundancy(msg["content"])

        compressed_context = self.remove_redundancy(additional_context)

        total_tokens = sum(
            self.estimate_tokens(msg.get("content", "")) for msg in compressed_messages
        ) + self.estimate_tokens(compressed_context)

        if total_tokens > self.max_tokens:
            compressed_messages = self._aggressive_compress(compressed_messages, compressed_context)

        logger.debug(f"上下文压缩完成，估算 token: {total_tokens}")
        return compressed_messages, compressed_context

    @staticmethod
    def _aggressive_compress(messages: List[Dict[str, str]], context: str) -> List[Dict[str, str]]:
        """激进压缩（只保留最近2轮对话）"""
        if len(messages) > 4:
            logger.warning("上下文过长，执行激进压缩")
            return messages[-4:]
        return messages

    def summarize_old_messages(
        self,
        messages: List[Dict[str, str]],
        keep_recent: int = 6,
    ) -> str:
        """
        总结旧消息

        将旧消息总结成简短的摘要，而不是完全丢弃

        Args:
            messages: 消息列表
            keep_recent: 保留最近的消息数量

        Returns:
            str: 旧消息摘要
        """
        if len(messages) <= keep_recent:
            return ""

        old_messages = messages[:-keep_recent]

        # 提取关键信息
        key_points = []
        for msg in old_messages:
            content = msg.get("content", "")
            if self._is_important(content):
                # 简化内容
                simplified = content[:50] + "..." if len(content) > 50 else content
                key_points.append(simplified)

        if not key_points:
            return ""

        summary = "【早期对话要点】\n" + "\n".join(f"- {point}" for point in key_points[:5])
        return summary

    def get_compression_stats(
        self,
        original_messages: List[Dict[str, str]],
        compressed_messages: List[Dict[str, str]],
        original_context: str,
        compressed_context: str,
    ) -> Dict:
        """
        获取压缩统计信息

        Args:
            original_messages: 原始消息列表
            compressed_messages: 压缩后的消息列表
            original_context: 原始上下文
            compressed_context: 压缩后的上下文

        Returns:
            Dict: 压缩统计
        """
        original_tokens = sum(
            self.estimate_tokens(msg.get("content", "")) for msg in original_messages
        ) + self.estimate_tokens(original_context)

        compressed_tokens = sum(
            self.estimate_tokens(msg.get("content", "")) for msg in compressed_messages
        ) + self.estimate_tokens(compressed_context)

        compression_ratio = (
            (1 - compressed_tokens / original_tokens) * 100 if original_tokens > 0 else 0
        )

        return {
            "original_messages": len(original_messages),
            "compressed_messages": len(compressed_messages),
            "original_tokens": original_tokens,
            "compressed_tokens": compressed_tokens,
            "compression_ratio": f"{compression_ratio:.1f}%",
            "tokens_saved": original_tokens - compressed_tokens,
        }
