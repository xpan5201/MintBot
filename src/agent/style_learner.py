"""
对话风格学习系统

学习和适应用户的对话风格，让回复更加自然和个性化。
这是 v2.5 的核心功能之一，用于让 AI 更接近人类。
"""

import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from src.config.settings import settings
from src.utils.logger import get_logger

logger = get_logger(__name__)

_EMOJI_PATTERN = re.compile(r"[😀-🙏🌀-🗿🚀-🛿]")
_CHINESE_WORD_PATTERN = re.compile(r"[\u4e00-\u9fff]+")
_QUESTION_WORDS = ("吗", "呢", "啊", "什么", "怎么", "为什么", "哪里")
_FORMAL_WORDS = ("您", "请", "谢谢", "不好意思", "麻烦")
_CASUAL_WORDS = ("哈", "嘿", "哇", "呀", "啦", "喔")
_TOPIC_KEYWORDS = {
    "美食": ("吃", "饭", "菜", "食物", "美食", "餐", "饿", "好吃"),
    "娱乐": ("玩", "游戏", "电影", "音乐", "看", "听", "唱"),
    "学习": ("学", "习", "书", "课", "考试", "作业", "知识"),
    "工作": ("工作", "上班", "公司", "项目", "任务", "忙"),
    "情感": ("喜欢", "爱", "想", "开心", "难过", "生气", "感觉"),
    "日常": ("今天", "明天", "昨天", "早上", "晚上", "睡觉", "起床"),
    "天气": ("天气", "下雨", "晴天", "冷", "热", "温度"),
}


class StyleLearner:
    """对话风格学习器（学习用户习惯、偏好、节奏，个性化回复风格）"""

    def __init__(self, persist_file: Optional[str] = None):
        """初始化风格学习器"""
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

        # 持久化文件
        self.persist_file = persist_file or str(
            Path(settings.data_dir) / "memory" / "style_profile.json"
        )
        Path(self.persist_file).parent.mkdir(parents=True, exist_ok=True)

        # 加载持久化数据
        self._load_profile()

        logger.info("对话风格学习器初始化完成")

    def _load_profile(self) -> None:
        """从文件加载风格配置"""
        try:
            if Path(self.persist_file).exists():
                with open(self.persist_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.user_avg_length = data.get("user_avg_length", 20.0)
                    self.user_common_words = data.get("user_common_words", [])
                    self.user_emoji_usage = data.get("user_emoji_usage", 0.0)
                    self.user_question_ratio = data.get("user_question_ratio", 0.0)
                    self.preferred_topics = data.get("preferred_topics", [])
                    self.preferred_response_length = data.get(
                        "preferred_response_length", "medium"
                    )
                    self.preferred_formality = data.get("preferred_formality", "casual")
                    self.total_interactions = data.get("total_interactions", 0)
                    self.message_lengths = data.get("message_lengths", [])[-100:]  # 只保留最近100条

                    # 重建 Counter
                    self.word_counter = Counter(data.get("word_counter", {}))
                    self.topic_counter = Counter(data.get("topic_counter", {}))

                logger.info("风格配置已从文件加载")
        except Exception as e:
            logger.warning(f"加载风格配置失败: {e}，使用默认值")

    def _save_profile(self) -> None:
        """保存风格配置到文件"""
        try:
            data = {
                "user_avg_length": self.user_avg_length,
                "user_common_words": self.user_common_words,
                "user_emoji_usage": self.user_emoji_usage,
                "user_question_ratio": self.user_question_ratio,
                "preferred_topics": self.preferred_topics,
                "preferred_response_length": self.preferred_response_length,
                "preferred_formality": self.preferred_formality,
                "total_interactions": self.total_interactions,
                "message_lengths": self.message_lengths[-100:],  # 只保存最近100条
                "word_counter": dict(self.word_counter.most_common(100)),  # 只保存前100个
                "topic_counter": dict(self.topic_counter.most_common(50)),  # 只保存前50个
                "last_update": datetime.now().isoformat(),
            }
            with open(self.persist_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存风格配置失败: {e}")

    def learn_from_message(self, user_message: str) -> None:
        """从用户消息中学习（长度、用词、表情、提问、话题、正式程度）"""
        self.total_interactions += 1

        msg_length = len(user_message)
        self.message_lengths.append(msg_length)
        if len(self.message_lengths) > 100:
            self.message_lengths = self.message_lengths[-100:]

        self.user_avg_length = sum(self.message_lengths) / len(self.message_lengths)

        words = self._extract_words(user_message)
        self.word_counter.update(words)
        self.user_common_words = [word for word, _ in self.word_counter.most_common(20)]

        emoji_count = len(_EMOJI_PATTERN.findall(user_message))
        if emoji_count > 0:
            self.user_emoji_usage = self.user_emoji_usage * 0.9 + (emoji_count / msg_length) * 0.1

        is_question = '?' in user_message or '？' in user_message or any(
            word in user_message for word in _QUESTION_WORDS
        )
        self.user_question_ratio = self.user_question_ratio * 0.95 + (0.05 if is_question else 0)

        topics = self._extract_topics(user_message)
        self.topic_counter.update(topics)
        self.preferred_topics = [topic for topic, _ in self.topic_counter.most_common(10)]

        if self.user_avg_length < 15:
            self.preferred_response_length = "short"
        elif self.user_avg_length < 40:
            self.preferred_response_length = "medium"
        else:
            self.preferred_response_length = "long"

        formal_count = sum(1 for word in _FORMAL_WORDS if word in user_message)
        casual_count = sum(1 for word in _CASUAL_WORDS if word in user_message)

        if formal_count > casual_count:
            self.preferred_formality = "formal"
        elif casual_count > 0:
            self.preferred_formality = "casual"
        else:
            self.preferred_formality = "cute"

        if self.total_interactions % 10 == 0:
            self._save_profile()

    @staticmethod
    def _extract_words(text: str) -> List[str]:
        """提取文本中的词语（2字及以上）"""
        words = _CHINESE_WORD_PATTERN.findall(text)
        return [w for w in words if len(w) >= 2]

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
        guidance_parts = []

        length_guide = {
            "short": "请保持回复简短（1-2句话），主人喜欢简洁的回复。",
            "medium": "请保持回复适中（2-3句话），不要太长也不要太短。",
            "long": "可以给出详细的回复（3-5句话），主人喜欢详细的解释。",
        }
        guidance_parts.append(length_guide.get(self.preferred_response_length, ""))

        formality_guide = {
            "formal": "请使用较为正式礼貌的语气，称呼主人时使用'您'。",
            "casual": "请使用轻松随意的语气，可以使用'哈'、'呀'等语气词。",
            "cute": "请使用可爱活泼的语气，多用'喵~'、'呜~'等可爱的表达。",
        }
        guidance_parts.append(formality_guide.get(self.preferred_formality, ""))

        if self.preferred_topics:
            topics_str = "、".join(self.preferred_topics[:3])
            guidance_parts.append(f"主人经常谈论：{topics_str}，可以适当关联这些话题。")

        if self.user_emoji_usage > 0.05:
            guidance_parts.append("主人喜欢使用表情符号，你也可以适当使用。")

        return "\n".join(guidance_parts)

    def get_stats(self) -> Dict:
        """获取学习统计信息"""
        return {
            "total_interactions": self.total_interactions,
            "user_avg_length": f"{self.user_avg_length:.1f}",
            "user_common_words": self.user_common_words[:10],
            "user_emoji_usage": f"{self.user_emoji_usage:.2%}",
            "user_question_ratio": f"{self.user_question_ratio:.2%}",
            "preferred_topics": self.preferred_topics,
            "preferred_response_length": self.preferred_response_length,
            "preferred_formality": self.preferred_formality,
        }
