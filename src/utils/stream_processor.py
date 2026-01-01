"""
流处理器 - v2.32.0

为TTS准备的实时文本流处理器，支持句子分割、文本修正、批量处理。

核心功能:
- 实时句子分割
- 句子边界检测
- 文本修正支持
- 批量处理
- 性能监控

用于: 将LLM流式输出的文本实时分割成句子，发送给TTS引擎
"""

from typing import Iterator, Optional, Callable
from collections import deque
import time

from src.utils.logger import get_logger

logger = get_logger(__name__)


class StreamProcessor:
    """流处理器 - 实时文本流处理"""

    # 强句子结束标点（硬边界），通常用于明显的句末停顿
    STRONG_ENDINGS = {
        "。",
        "！",
        "？",
        ".",
        "!",
        "?",
    }

    # 软句子结束标点（软边界），更偏向语气停顿或子句分隔
    # 只有当前面文本长度足够时才会在这些标点处分句
    SOFT_ENDINGS = {
        ",",
        "，",
        "、",
        ";",
        "；",
        ":",
        "：",
        "…",
        "~",
        "～",
    }

    # 句子结束候选标点（强 + 软），仅用于内部实现
    SENTENCE_ENDINGS = STRONG_ENDINGS | SOFT_ENDINGS

    # 需要作为一个整体保留的标点组合（例如省略号、多重感叹等）
    # 实际实现中会通过连续标点扫描来处理，这里仅用于文档和潜在扩展
    KEEP_TOGETHER = {
        "...",
        "…",
        "……",
        "——",
    }

    def __init__(
        self,
        min_sentence_length: int = 5,
        max_buffer_size: int = 500,
        correction_callback: Optional[Callable[[str], str]] = None,
    ):
        """
        初始化流处理器

        Args:
            min_sentence_length: 最小句子长度（字符数）
            max_buffer_size: 最大缓冲区大小
            correction_callback: 文本修正回调函数
        """
        self.min_sentence_length = min_sentence_length
        self.max_buffer_size = max_buffer_size
        self.correction_callback = correction_callback

        # 缓冲区
        self._buffer = ""
        self._sentence_queue: deque[str] = deque()

        # 统计信息
        self._stats = {
            "total_chunks": 0,
            "total_sentences": 0,
            "total_chars": 0,
            "processing_time": 0.0,
        }

        logger.info(
            f"流处理器初始化: 最小句子长度={min_sentence_length}, 最大缓冲={max_buffer_size}"
        )

    def process_chunk(self, chunk: str) -> Iterator[str]:
        """
        处理文本块，返回完整的句子

        Args:
            chunk: 输入的文本块

        Yields:
            完整的句子
        """
        start_time = time.perf_counter()

        # 添加到缓冲区
        self._buffer += chunk
        self._stats["total_chunks"] += 1
        self._stats["total_chars"] += len(chunk)

        # 检查缓冲区大小
        if len(self._buffer) > self.max_buffer_size:
            # 尝试在缓冲区中寻找最后一个句子边界，避免完全打断
            last_boundary = -1
            for i in range(len(self._buffer) - 1, max(0, len(self._buffer) - 200), -1):
                if self._buffer[i] in self.STRONG_ENDINGS:
                    last_boundary = i
                    break

            if last_boundary > self.min_sentence_length:
                # 找到边界，输出到边界为止
                sentence = self._buffer[: last_boundary + 1].strip()
                self._buffer = self._buffer[last_boundary + 1 :].lstrip()
                logger.debug(
                    "缓冲区接近上限，在边界处切分，输出长度=%d，剩余=%d",
                    len(sentence),
                    len(self._buffer),
                )
            else:
                # 未找到合适边界，强制输出全部内容
                logger.warning(
                    "缓冲区超过最大大小 (%d > %d)，强制输出全部内容，可能打断长句",
                    len(self._buffer),
                    self.max_buffer_size,
                )
                sentence = self._buffer
                self._buffer = ""

            # 应用修正
            if self.correction_callback:
                sentence = self.correction_callback(sentence)

            if sentence:
                self._stats["total_sentences"] += 1
                logger.debug(
                    "输出句子，长度=%d，内容前50字符=%.50s",
                    len(sentence),
                    sentence,
                )
                yield sentence

            # 如果缓冲区仍然过大，继续处理
            # 注意：这里不应该递归调用 process_chunk，因为会导致重复处理
            # 应该直接继续提取句子，直到缓冲区大小合理
            while len(self._buffer) > self.max_buffer_size:
                # 继续提取句子
                more_sentences = self._extract_sentences()
                for sentence in more_sentences:
                    # 应用修正
                    if self.correction_callback:
                        sentence = self.correction_callback(sentence)

                    if sentence:
                        self._stats["total_sentences"] += 1
                        logger.debug(
                            "缓冲区仍过大，继续输出句子，长度=%d，内容前50字符=%.50s",
                            len(sentence),
                            sentence,
                        )
                        yield sentence

                # 如果无法再提取句子（没有合适边界），跳出循环
                if not more_sentences:
                    break
            return

        # 查找句子边界
        sentences = self._extract_sentences()

        # 输出完整的句子
        for sentence in sentences:
            # 应用修正
            if self.correction_callback:
                sentence = self.correction_callback(sentence)

            self._stats["total_sentences"] += 1
            logger.debug(
                "输出句子，长度=%d，内容前50字符=%.50s，缓冲区剩余=%d",
                len(sentence),
                sentence,
                len(self._buffer),
            )
            yield sentence

        # 更新统计
        elapsed = time.perf_counter() - start_time
        self._stats["processing_time"] += elapsed

    def _extract_sentences(self) -> list[str]:
        """从缓冲区提取完整的句子

        设计原则：
        - 永不丢失文本：不满足长度要求时不移除缓冲区内容
        - 先尝试在强边界（句号/问号/感叹号等）处分句
        - 在文本足够长时，允许在软边界（逗号/省略号等）处分句
        - 括号内的标点不作为分句点，避免打断括号说明
        - 连续标点（如"……"、"！！"、"?!"）视为一个整体的句末标记
        """
        sentences: list[str] = []

        # 软边界的最小有效长度（参考 MoeChat 实现），避免在很短文本上过早在逗号/省略号处分句
        soft_min_length = max(self.min_sentence_length, 10)

        while True:
            if not self._buffer:
                break

            end_pos = -1

            # 括号嵌套深度：>0 时认为在括号内部，不在其中切分
            bracket_depth = 0

            i = 0
            buffer_len = len(self._buffer)

            while i < buffer_len:
                ch = self._buffer[i]

                # 更新括号深度
                if ch in {"(", "（", "["}:
                    bracket_depth += 1
                elif ch in {")", "）", "]"}:
                    bracket_depth = max(bracket_depth - 1, 0)

                # 在括号内部不进行分句判断
                if bracket_depth > 0:
                    i += 1
                    continue

                # 非候选标点，继续向后扫描
                if ch not in self.SENTENCE_ENDINGS:
                    i += 1
                    continue

                # 从当前标点开始，向后合并连续的候选标点，视为一个整体边界
                j = i
                while j + 1 < buffer_len and self._buffer[j + 1] in self.SENTENCE_ENDINGS:
                    j += 1

                # 候选句子为从开头到连续标点末尾的部分
                candidate = self._buffer[: j + 1].strip()

                # 如果标点前没有有效内容，则跳过该标点序列
                if not candidate:
                    i = j + 1
                    continue

                # 计算有效长度：忽略括号内内容和空白，仅用于判断是否“过短”
                effective_len = 0
                inner_depth = 0
                for ch2 in candidate:
                    if ch2 in {"(", "（", "["}:
                        inner_depth += 1
                        continue
                    if ch2 in {")", "）", "]"}:
                        inner_depth = max(inner_depth - 1, 0)
                        continue
                    if inner_depth > 0:
                        continue
                    if ch2.isspace():
                        continue
                    effective_len += 1

                # 使用最后一个标点来决定是强边界还是软边界
                boundary_char = self._buffer[j]
                if boundary_char in self.STRONG_ENDINGS:
                    required_len = self.min_sentence_length
                else:
                    required_len = soft_min_length

                if effective_len >= required_len:
                    end_pos = j
                    break

                # 句子太短：继续向后寻找下一个候选边界
                i = j + 1

            # 没有找到合适的分句点，结束循环，等待更多文本或 flush()
            if end_pos == -1:
                break

            # 提取句子（包含结束标记）
            sentence = self._buffer[: end_pos + 1].strip()

            # 将合法句子加入结果，并从缓冲区移除已处理部分
            sentences.append(sentence)
            self._buffer = self._buffer[end_pos + 1 :].lstrip()

        return sentences

    def flush(self) -> Optional[str]:
        """
        刷新缓冲区，返回剩余的文本

        注意：flush 时会输出所有剩余内容，即使不满足最小长度要求，
        确保开头结尾的文本不会被丢失。

        Returns:
            剩余的文本，如果为空返回None
        """
        if not self._buffer:
            return None

        sentence = self._buffer.strip()
        self._buffer = ""

        # 如果文本为空（只有空白字符），返回 None
        if not sentence:
            return None

        # 应用修正
        if self.correction_callback:
            sentence = self.correction_callback(sentence)

        # flush 时输出所有剩余内容，即使很短也要输出，确保不丢失文本
        if sentence:
            self._stats["total_sentences"] += 1
            logger.debug(
                "flush 输出剩余句子，长度=%d，内容前50字符=%.50s",
                len(sentence),
                sentence,
            )
            return sentence

        return None

    def reset(self):
        """重置处理器状态"""
        self._buffer = ""
        self._sentence_queue.clear()
        logger.debug("流处理器已重置")

    def get_stats(self) -> dict:
        """获取统计信息"""
        stats = self._stats.copy()
        if stats["total_chunks"] > 0:
            stats["avg_chunk_size"] = stats["total_chars"] / stats["total_chunks"]
            stats["avg_processing_time"] = stats["processing_time"] / stats["total_chunks"]
        else:
            stats["avg_chunk_size"] = 0.0
            stats["avg_processing_time"] = 0.0

        stats["buffer_size"] = len(self._buffer)
        return stats


def create_tts_processor(
    min_sentence_length: int = 5,
    correction_callback: Optional[Callable[[str], str]] = None,
) -> StreamProcessor:
    """
    创建用于TTS的流处理器

    Args:
        min_sentence_length: 最小句子长度
        correction_callback: 文本修正回调

    Returns:
        StreamProcessor: 流处理器实例
    """
    return StreamProcessor(
        min_sentence_length=min_sentence_length,
        max_buffer_size=500,
        correction_callback=correction_callback,
    )


# 示例用法
if __name__ == "__main__":
    # 创建处理器
    processor = create_tts_processor(min_sentence_length=5)

    # 模拟流式输入
    chunks = [
        "你好",
        "主人",
        "！",
        "今天",
        "天气",
        "真好",
        "啊",
        "。",
        "我们",
        "一起",
        "出去",
        "玩",
        "吧",
        "？",
    ]

    print("=== 流式处理示例 ===")
    for chunk in chunks:
        print(f"输入: {chunk}")
        for sentence in processor.process_chunk(chunk):
            print(f"  -> 输出句子: {sentence}")

    # 刷新剩余内容
    remaining = processor.flush()
    if remaining:
        print(f"  -> 剩余内容: {remaining}")

    # 获取统计
    stats = processor.get_stats()
    print(f"\n统计信息: {stats}")
