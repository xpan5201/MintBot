"""
对话风格学习系统

学习和适应用户的对话风格，让回复更加自然和个性化。
这是 v2.5 的核心功能之一，用于让 AI 更接近人类。
"""

import json
import os
import re
import secrets
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from src.config.settings import settings
from src.utils.logger import get_logger

logger = get_logger(__name__)

# 覆盖历史版本中可能含有“字面 emoji 字符”的正则，确保在不同终端编码/字体下稳定工作。
_EMOJI_PATTERN = re.compile(r"[\U0001F300-\U0001FAFF\u2600-\u27BF]")
_CHINESE_WORD_PATTERN = re.compile(r"[\u4e00-\u9fff]+")
_LAUGHTER_PATTERN = re.compile(r"(哈{2,}|呵{2,}|hh+|233+)", re.IGNORECASE)
_LOG_TIMESTAMP_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}", re.MULTILINE)
_CUTE_MARKERS = ("喵", "呜", "嘤", "qwq", "owo", "~", "\u0E05", "咩")  # "\u0E05" 是 U+0E05，部分字体会呈现“猫爪”样式
_QUESTION_WORDS = ("吗", "呢", "什么", "怎么", "为什么", "哪里", "多少", "几点", "几号", "啥")
_FORMAL_WORDS = ("您", "请", "谢谢", "不好意思", "麻烦")
_CASUAL_WORDS = ("哈", "嘿", "哇", "呀", "啦", "喔")
_TOPIC_KEYWORDS = {
    "美食": ("美食", "吃饭", "好吃", "餐厅", "外卖", "饿", "菜谱", "甜品"),
    "娱乐": ("游戏", "电影", "音乐", "追剧", "综艺", "听歌", "唱歌", "直播"),
    "学习": ("学习", "课程", "考试", "作业", "知识", "刷题", "复习", "背书"),
    "工作": ("工作", "上班", "公司", "项目", "任务", "加班", "开会", "绩效"),
    "情感": ("喜欢", "爱", "想", "开心", "难过", "生气", "感觉"),
    "日常": ("今天", "明天", "昨天", "早上", "晚上", "睡觉", "起床"),
    "天气": ("天气", "下雨", "晴天", "冷", "热", "温度"),
}


def _atomic_write_json(path: str, data: Dict) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(f"{target.name}.tmp.{secrets.token_hex(6)}")
    try:
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, target)
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass


class StyleLearner:
    """对话风格学习器（学习用户习惯、偏好、节奏，个性化回复风格）"""

    def __init__(self, persist_file: Optional[str] = None, *, user_id: Optional[int] = None):
        """初始化风格学习器"""
        import threading

        # 用户对话特征
        self.user_avg_length: float = 20.0  # 平均消息长度
        self.user_common_words: List[str] = []  # 常用词
        self.user_emoji_usage: float = 0.0  # 表情使用频率
        self.user_question_ratio: float = 0.0  # 提问比例

        # 用户偏好
        self.preferred_topics: List[str] = []  # 偏好话题
        self.preferred_response_length: str = "medium"  # short/medium/long
        self.preferred_formality: str = "casual"  # formal/casual/cute

        # 统计数据
        self.total_interactions: int = 0
        self.message_lengths: List[int] = []
        self.word_counter: Counter = Counter()
        self.topic_counter: Counter = Counter()
        self.formality_counter: Counter = Counter()
        self._message_length_sum: int = 0

        self._history_max_len: int = max(10, int(getattr(settings.agent, "style_history_max_len", 100)))
        self._word_counter_max: int = max(0, int(getattr(settings.agent, "style_word_counter_max", 100)))
        self._topic_counter_max: int = max(0, int(getattr(settings.agent, "style_topic_counter_max", 50)))
        self._max_message_chars: int = max(
            50, int(getattr(settings.agent, "style_learning_max_message_chars", 800))
        )
        self._max_message_lines: int = max(
            1, int(getattr(settings.agent, "style_learning_max_message_lines", 12))
        )
        self._guidance_min_interactions: int = max(
            0, int(getattr(settings.agent, "style_guidance_min_interactions", 6))
        )
        self._guidance_max_chars: int = max(
            0, int(getattr(settings.agent, "style_guidance_max_chars", 600))
        )
        self._topic_decay: float = min(
            1.0, max(0.0, float(getattr(settings.agent, "style_topic_decay", 0.985)))
        )
        self._formality_decay: float = min(
            1.0, max(0.0, float(getattr(settings.agent, "style_formality_decay", 0.99)))
        )

        self._persist_interval_s: float = max(
            0.0, float(getattr(settings.agent, "style_persist_interval_s", 15.0))
        )
        self._persist_every_n_interactions: int = max(
            1, int(getattr(settings.agent, "style_persist_every_n_interactions", 10))
        )
        self._last_persist_monotonic: float = 0.0
        self._dirty: bool = False
        # 可能在 learn_from_message() -> _save_profile() 等路径出现重入，使用 RLock 更安全
        self._lock = threading.RLock()

        # 持久化文件
        if persist_file is not None:
            self.persist_file = persist_file
        else:
            base = Path(settings.data_dir)
            if user_id is not None:
                self.persist_file = str(
                    base / "users" / str(user_id) / "memory" / "style_profile.json"
                )
            else:
                self.persist_file = str(base / "memory" / "style_profile.json")
        Path(self.persist_file).parent.mkdir(parents=True, exist_ok=True)

        # 加载持久化数据
        self._load_profile()

        logger.info("对话风格学习器初始化完成")

    def _load_profile(self) -> None:
        """从文件加载风格配置"""
        with self._lock:
            try:
                path = Path(self.persist_file)
                if not path.exists():
                    return

                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                except json.JSONDecodeError as e:
                    logger.warning("风格配置文件已损坏，将忽略并重建: %s (%s)", path, e)
                    try:
                        backup = path.with_name(
                            f"{path.name}.corrupt.{datetime.now().strftime('%Y%m%d-%H%M%S')}"
                        )
                        os.replace(path, backup)
                    except Exception:
                        pass
                    return

                self.user_avg_length = data.get("user_avg_length", 20.0)
                self.user_common_words = data.get("user_common_words", [])
                self.user_emoji_usage = data.get("user_emoji_usage", 0.0)
                self.user_question_ratio = data.get("user_question_ratio", 0.0)
                self.preferred_topics = data.get("preferred_topics", [])
                self.preferred_response_length = data.get("preferred_response_length", "medium")
                self.preferred_formality = data.get("preferred_formality", "casual")
                self.total_interactions = data.get("total_interactions", 0)
                self.message_lengths = data.get("message_lengths", [])[-self._history_max_len :]  # 只保留最近N条
                self._message_length_sum = sum(self.message_lengths)
                if self.message_lengths:
                    self.user_avg_length = self._message_length_sum / len(self.message_lengths)

                # 重建 Counter
                self.word_counter = Counter(data.get("word_counter", {}))
                self.topic_counter = Counter(data.get("topic_counter", {}))
                self.formality_counter = Counter(data.get("formality_counter", {}))
                if self.formality_counter:
                    try:
                        self.preferred_formality = self.formality_counter.most_common(1)[0][0]
                    except Exception:
                        pass

                self._dirty = False
                self._last_persist_monotonic = time.monotonic()
                logger.info("风格配置已从文件加载")
            except Exception as e:
                logger.warning(f"加载风格配置失败: {e}，使用默认值")

    def _save_profile(self, *, force: bool = False) -> None:
        """保存风格配置到文件"""
        with self._lock:
            try:
                if not force:
                    if not self._dirty:
                        return

                    now = time.monotonic()
                    due_by_time = self._persist_interval_s > 0 and (
                        (now - self._last_persist_monotonic) >= self._persist_interval_s
                    )
                    due_by_count = (self.total_interactions % self._persist_every_n_interactions) == 0
                    if not (due_by_time or due_by_count):
                        return

                data = {
                    "user_avg_length": self.user_avg_length,
                    "user_common_words": self.user_common_words,
                    "user_emoji_usage": self.user_emoji_usage,
                    "user_question_ratio": self.user_question_ratio,
                    "preferred_topics": self.preferred_topics,
                    "preferred_response_length": self.preferred_response_length,
                    "preferred_formality": self.preferred_formality,
                    "total_interactions": self.total_interactions,
                    "message_lengths": self.message_lengths[-self._history_max_len :],  # 只保存最近N条
                    "word_counter": (
                        dict(self.word_counter.most_common(self._word_counter_max))
                        if self._word_counter_max > 0
                        else {}
                    ),
                "topic_counter": (
                    {
                        k: round(float(v), 4)
                        for k, v in self.topic_counter.most_common(self._topic_counter_max)
                    }
                    if self._topic_counter_max > 0
                    else {}
                ),
                "formality_counter": {k: round(float(v), 4) for k, v in dict(self.formality_counter).items()},
                "last_update": datetime.now().isoformat(),
            }
                _atomic_write_json(self.persist_file, data)
                self._dirty = False
                self._last_persist_monotonic = time.monotonic()
            except Exception as e:
                logger.error(f"保存风格配置失败: {e}")

    def persist(self, *, force: bool = False) -> None:
        """将风格画像持久化到磁盘。"""
        self._save_profile(force=force)

    def learn_from_message(self, user_message: str, persist: bool = True) -> None:
        """从用户消息中学习（长度、用词、表情、提问、话题、正式程度）"""
        with self._lock:
            if not bool(getattr(settings.agent, "style_learning_enabled", True)):
                return

            text = (user_message or "").strip()
            if not text:
                return

            if not self._should_learn_message(text):
                return

            msg_length = len(text)
            self.total_interactions += 1

            self.message_lengths.append(msg_length)
            self._message_length_sum += msg_length
            if len(self.message_lengths) > self._history_max_len:
                removed = self.message_lengths.pop(0)
                self._message_length_sum -= removed

            self.user_avg_length = (
                (self._message_length_sum / len(self.message_lengths))
                if self.message_lengths
                else 20.0
            )

            if words := self._extract_words(text):
                if self._word_counter_max > 0:
                    self.word_counter.update(words)
                    # 防止长时间运行导致 Counter 无界增长（只保留更常见的词）
                    if len(self.word_counter) > max(self._word_counter_max * 20, 2000):
                        keep_top = max(self._word_counter_max * 5, 500)
                        self.word_counter = Counter(dict(self.word_counter.most_common(keep_top)))
                    self.user_common_words = [word for word, _ in self.word_counter.most_common(20)]

            emoji_count = len(_EMOJI_PATTERN.findall(text))
            emoji_ratio = emoji_count / max(1, msg_length)
            self.user_emoji_usage = self.user_emoji_usage * 0.9 + emoji_ratio * 0.1

            is_question = ("?" in text) or ("？" in text) or any(
                word in text for word in _QUESTION_WORDS
            )
            self.user_question_ratio = self.user_question_ratio * 0.95 + (
                0.05 if is_question else 0.0
            )

            if self._topic_decay < 1.0:
                for key in list(self.topic_counter.keys()):
                    self.topic_counter[key] = float(self.topic_counter[key]) * self._topic_decay
                    if self.topic_counter[key] <= 0.01:
                        try:
                            del self.topic_counter[key]
                        except KeyError:
                            pass

            if topics := self._extract_topics(text):
                for topic in topics:
                    self.topic_counter[topic] = float(self.topic_counter.get(topic, 0.0)) + 1.0
                self.preferred_topics = [topic for topic, _ in self.topic_counter.most_common(10)]

            if self.user_avg_length < 15:
                self.preferred_response_length = "short"
            elif self.user_avg_length < 40:
                self.preferred_response_length = "medium"
            else:
                self.preferred_response_length = "long"

            formality = self._classify_formality(text, emoji_count=emoji_count)
            if self._formality_decay < 1.0:
                for key in list(self.formality_counter.keys()):
                    self.formality_counter[key] = float(self.formality_counter[key]) * self._formality_decay
                    if self.formality_counter[key] <= 0.01:
                        try:
                            del self.formality_counter[key]
                        except KeyError:
                            pass
            self.formality_counter[formality] = float(self.formality_counter.get(formality, 0.0)) + 1.0
            if self.formality_counter:
                self.preferred_formality = self.formality_counter.most_common(1)[0][0]

            self._dirty = True
            if persist:
                self._save_profile()

    def _should_learn_message(self, text: str) -> bool:
        stripped = (text or "").strip()
        if not stripped:
            return False

        if len(stripped) > self._max_message_chars:
            return False
        if stripped.count("\n") + 1 > self._max_message_lines:
            return False
        if "```" in stripped:
            return False

        lower = stripped.lower()
        if "traceback (most recent call last)" in lower:
            return False

        if _LOG_TIMESTAMP_PATTERN.search(stripped) and stripped.count("\n") >= 2:
            return False

        if stripped.startswith("{") and stripped.endswith("}") and stripped.count(":") >= 2:
            return False

        if len(stripped) >= 80:
            meaningful = sum(
                1
                for ch in stripped
                if ch.isalnum() or ("\u4e00" <= ch <= "\u9fff")
            )
            if meaningful / len(stripped) < 0.35:
                return False

        if len(stripped) >= 40 and len(set(stripped)) <= 2:
            return False

        return True

    @staticmethod
    def _classify_formality(text: str, *, emoji_count: int) -> str:
        value = text or ""
        lower = value.strip().lower()

        formal_score = 0
        stripped = value.strip()
        if "您" in value:
            formal_score += 2
        if "请问" in value:
            formal_score += 2
        if "不好意思" in value:
            formal_score += 2
        if "麻烦" in value:
            formal_score += 2
        if "谢谢" in value:
            formal_score += 2
        if "请" in value:
            formal_score += 1
        if stripped.startswith("请"):
            formal_score += 1

        casual_score = sum(1 for w in _CASUAL_WORDS if w in value)
        if _LAUGHTER_PATTERN.search(value):
            casual_score += 1

        cute_score = 0
        if any(marker in lower for marker in _CUTE_MARKERS if marker != "~"):
            cute_score += 2
        if "~" in value:
            cute_score += 1
        if emoji_count > 0:
            cute_score += 1

        if formal_score >= 2 and formal_score >= casual_score + cute_score:
            return "formal"
        if cute_score >= 2 and cute_score >= casual_score + formal_score:
            return "cute"
        return "casual"

    def flush(self) -> None:
        """强制落盘（用于程序退出或显式保存）。"""
        with self._lock:
            self._dirty = True
            self._save_profile(force=True)

    @staticmethod
    def _extract_words(text: str) -> List[str]:
        """提取文本中的“伪词”。

        - 对于较短的连续中文片段（2-6字）直接作为词。
        - 对于更长的片段，提取 2-4 字 n-gram（带上限）以避免整句污染统计。
        """
        segments = _CHINESE_WORD_PATTERN.findall(text or "")
        if not segments:
            return []

        words: list[str] = []
        max_words = 80
        for seg in segments:
            seg = seg.strip()
            seg_len = len(seg)
            if seg_len < 2:
                continue

            if 2 <= seg_len <= 6:
                words.append(seg)
                if len(words) >= max_words:
                    break
                continue

            for n in (2, 3, 4):
                if seg_len < n:
                    continue
                for i in range(seg_len - n + 1):
                    words.append(seg[i : i + n])
                    if len(words) >= max_words:
                        break
                if len(words) >= max_words:
                    break

            if len(words) >= max_words:
                break

        return words

    @staticmethod
    def _extract_topics(text: str) -> List[str]:
        """提取话题关键词"""
        topics = []
        for topic, keywords in _TOPIC_KEYWORDS.items():
            if any(keyword in text for keyword in keywords):
                topics.append(topic)

        return topics

    def get_style_guidance(self) -> str:
        """获取风格指导（用于添加到提示词）"""
        if not bool(getattr(settings.agent, "style_learning_enabled", True)):
            return ""

        with self._lock:
            if self.total_interactions < self._guidance_min_interactions:
                return ""
            preferred_response_length = self.preferred_response_length
            preferred_formality = self.preferred_formality
            user_question_ratio = float(self.user_question_ratio)
            preferred_topics = list(self.preferred_topics or [])[:3]
            user_emoji_usage = float(self.user_emoji_usage)
            guidance_max_chars = int(self._guidance_max_chars)

        user_name = getattr(settings.agent, "user", "主人")
        guidance_parts: list[str] = []

        if preferred_response_length == "short":
            guidance_parts.append(f"对{user_name}：回复偏简短（1-2句），先给结论再补充。")
        elif preferred_response_length == "long":
            guidance_parts.append(f"对{user_name}：回复可以稍详细（3-5句），把思路讲清楚。")
        else:
            guidance_parts.append(f"对{user_name}：回复适中（2-3句），简洁但信息完整。")

        if preferred_formality == "formal":
            guidance_parts.append("语气偏正式礼貌，必要时用“您”指代对方。")
        elif preferred_formality == "cute":
            guidance_parts.append("语气偏可爱/撒娇，偶尔用软萌口癖（注意不要过度）。")
        else:
            guidance_parts.append("语气自然口语化，轻松但不过分。")

        if user_question_ratio > 0.4:
            guidance_parts.append("用户常以提问为主：先直接回答，再用一句轻问推进对话。")

        if preferred_topics:
            topics_str = "、".join(preferred_topics)
            guidance_parts.append(f"可自然联想到话题：{topics_str}。")

        if user_emoji_usage > 0.05:
            guidance_parts.append("可适当加入表情/颜文字。")

        guidance = "\n".join(part for part in guidance_parts if part).strip()
        if not guidance:
            return ""

        if guidance_max_chars > 0 and len(guidance) > guidance_max_chars:
            guidance = guidance[: guidance_max_chars - 1].rstrip() + "…"
        return guidance

    def get_stats(self) -> Dict:
        """获取学习统计信息"""
        with self._lock:
            total_interactions = int(self.total_interactions)
            user_avg_length = float(self.user_avg_length)
            user_common_words = list(self.user_common_words or [])[:10]
            user_emoji_usage = float(self.user_emoji_usage)
            user_question_ratio = float(self.user_question_ratio)
            preferred_topics = list(self.preferred_topics or [])
            preferred_response_length = str(self.preferred_response_length)
            preferred_formality = str(self.preferred_formality)
            formality_counter = dict(self.formality_counter)

        return {
            "total_interactions": total_interactions,
            "user_avg_length": f"{user_avg_length:.1f}",
            "user_common_words": user_common_words,
            "user_emoji_usage": f"{user_emoji_usage:.2%}",
            "user_question_ratio": f"{user_question_ratio:.2%}",
            "preferred_topics": preferred_topics,
            "preferred_response_length": preferred_response_length,
            "preferred_formality": preferred_formality,
            "formality_counter": formality_counter,
        }
