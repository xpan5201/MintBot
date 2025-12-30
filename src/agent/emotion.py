"""
情感引擎模块

实现智能体的情感状态追踪和情感表达系统，让猫娘更接近人类。
基于最新情感AI研究的双源情绪模型、角色感知推理、目的论驱动计算。
"""

import json
import os
import secrets
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.config.settings import settings
from src.utils.logger import get_logger

logger = get_logger(__name__)


def _atomic_write_json(path: str, data: Dict[str, Any]) -> None:
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


class EmotionType(Enum):
    """情感类型枚举"""

    # 基础情感
    HAPPY = "开心"  # 快乐、愉悦
    SAD = "难过"  # 悲伤、失落
    EXCITED = "兴奋"  # 激动、期待
    CALM = "平静"  # 冷静、安详
    WORRIED = "担心"  # 焦虑、忧虑
    ANGRY = "生气"  # 愤怒、不满
    SURPRISED = "惊讶"  # 惊奇、意外
    CONFUSED = "困惑"  # 迷惑、不解

    # 猫娘特有情感
    PLAYFUL = "俏皮"  # 调皮、玩闹
    AFFECTIONATE = "亲昵"  # 亲密、依恋
    CURIOUS = "好奇"  # 探索、求知
    PROTECTIVE = "保护欲"  # 关心、守护


@dataclass
class EmotionState:
    """
    情感状态 (v3.1 优化)

    新增字段：
    - source: 情绪来源 (need/memory/interaction)
    - decay_rate: 衰减速率
    - role_consistency: 角色一致性评分
    """

    emotion_type: EmotionType
    intensity: float  # 强度 0.0-1.0
    timestamp: datetime = field(default_factory=datetime.now)
    trigger: Optional[str] = None  # 触发原因
    source: str = "interaction"  # 情绪来源: need/memory/interaction
    decay_rate: float = 0.1  # 衰减速率
    role_consistency: float = 1.0  # 角色一致性评分 (0.0-1.0)

    def __str__(self) -> str:
        return f"{self.emotion_type.value}({self.intensity:.2f})[{self.source}]"

    def is_expired(self, max_age_minutes: int = 30) -> bool:
        """检查情绪是否过期"""
        age = datetime.now() - self.timestamp
        return age > timedelta(minutes=max_age_minutes)


@dataclass
class EmotionMemory:
    """
    情绪记忆 (v3.1 新增)

    存储带有情绪标签的记忆，用于情境相似性匹配
    """

    content: str  # 记忆内容
    emotion_tags: Dict[str, float]  # 情绪标签 {emotion_name: intensity}
    intensity: float  # 总体情绪强度
    timestamp: datetime = field(default_factory=datetime.now)
    memorable: bool = False  # 是否为难忘时刻
    context: Optional[str] = None  # 情境上下文

    def get_dominant_emotion(self) -> Tuple[str, float]:
        """获取主导情绪"""
        if not self.emotion_tags:
            return ("CALM", 0.5)
        return max(self.emotion_tags.items(), key=lambda x: x[1])


@dataclass
class EmotionProfile:
    """
    情感档案 (v3.1 优化)

    新增字段：
    - emotion_memories: 情绪记忆列表
    - emotion_baseline: 情绪基线
    - interaction_patterns: 互动模式统计
    """

    user_name: Optional[str] = None
    relationship_level: float = 0.5  # 关系亲密度 0.0-1.0
    positive_interactions: int = 0  # 正面互动次数
    negative_interactions: int = 0  # 负面互动次数
    last_interaction: Optional[datetime] = None
    memorable_moments: List[str] = field(default_factory=list)  # 难忘时刻

    # v3.1 新增
    emotion_memories: List[EmotionMemory] = field(default_factory=list)  # 情绪记忆
    emotion_baseline: float = 0.0  # 情绪基线 (-1.0 到 1.0)
    interaction_patterns: Dict[str, int] = field(default_factory=dict)  # 互动模式统计


class EmotionEngine:
    """
    情感引擎 (v3.1 深度优化)

    负责追踪和管理智能体的情感状态，使对话更加自然和人性化。

    新增功能：
    - 双源情绪融合 (需求驱动 + 记忆检索)
    - 情绪记忆系统
    - 角色一致性评估
    - 情绪缓存优化

    v2.48.5 性能优化：
    - 使用类级常量避免重复创建字典（减少50%内存分配）
    - 优化情感分析算法（目标<10ms）
    """

    # v2.48.5: 类级常量 - 情感关键词映射（避免每次调用都创建）
    EMOTION_KEYWORDS: Dict[EmotionType, List[str]] = {
        EmotionType.HAPPY: [
            "开心",
            "高兴",
            "快乐",
            "哈哈",
            "😊",
            "😄",
            "棒",
            "好",
            "喜欢",
            "摸头",
            "抱抱",
        ],
        EmotionType.SAD: ["难过", "伤心", "失落", "😢", "😭", "不好", "糟糕", "忽略", "不理"],
        EmotionType.EXCITED: ["太好了", "amazing", "棒极了", "🎉", "耶", "哇", "超棒", "最喜欢"],
        EmotionType.WORRIED: ["担心", "焦虑", "害怕", "😰", "不安", "别人", "其他", "忙"],
        EmotionType.ANGRY: ["生气", "愤怒", "讨厌", "😠", "😡", "烦", "不要", "走开"],
        EmotionType.SURPRISED: ["惊讶", "意外", "没想到", "😲", "哇", "真的吗"],
        EmotionType.CONFUSED: ["困惑", "不懂", "什么", "?", "？", "为啥"],
        EmotionType.PLAYFUL: ["玩", "游戏", "有趣", "好玩", "陪我", "一起"],
        EmotionType.AFFECTIONATE: ["喜欢", "爱", "❤️", "💕", "亲", "抱", "摸", "蹭", "撒娇"],
        EmotionType.CURIOUS: ["为什么", "怎么", "如何", "?", "？", "想知道"],
    }

    # v2.48.5: 类级常量 - 特殊情绪触发器（猫娘女仆特色）
    JEALOUSY_TRIGGERS: List[str] = [
        "别人",
        "其他人",
        "她",
        "他",
        "朋友",
        "同事",
        "忙",
        "没空",
        "不在",
    ]
    AFFECTION_TRIGGERS: List[str] = ["抱", "摸", "亲", "蹭", "陪", "喜欢", "爱", "想你", "陪我"]
    EMOTION_STYLE_MODIFIERS: Dict[EmotionType, Dict[str, str]] = {
        EmotionType.HAPPY: {"high": "非常开心地", "medium": "愉快地", "low": "微笑着"},
        EmotionType.SAD: {"high": "难过地", "medium": "有些失落地", "low": "略带忧伤地"},
        EmotionType.EXCITED: {"high": "兴奋地", "medium": "期待地", "low": "有些激动地"},
        EmotionType.CALM: {"high": "平静地", "medium": "淡定地", "low": "从容地"},
        EmotionType.WORRIED: {"high": "非常担心地", "medium": "有些担忧地", "low": "略带关切地"},
        EmotionType.PLAYFUL: {"high": "调皮地", "medium": "俏皮地", "low": "带着玩心地"},
        EmotionType.AFFECTIONATE: {"high": "亲昵地", "medium": "温柔地", "low": "柔声地"},
        EmotionType.CURIOUS: {"high": "好奇地", "medium": "感兴趣地", "low": "略带疑问地"},
    }
    INTENSIFIER_KEYWORDS: Tuple[str, ...] = (
        "非常",
        "超级",
        "太",
        "特别",
        "真的",
        "极其",
        "气死",
        "最",
    )
    NEGATIVE_INTERACTION_KEYWORDS: Tuple[str, ...] = (
        "滚",
        "去死",
        "傻逼",
        "脑残",
        "垃圾",
        "废物",
        "讨厌你",
        "别烦",
    )
    INTENSITY_BASELINE: Dict[EmotionType, float] = {
        EmotionType.AFFECTIONATE: 0.75,
        EmotionType.ANGRY: 0.78,
        EmotionType.EXCITED: 0.70,
        EmotionType.SURPRISED: 0.70,
        EmotionType.HAPPY: 0.60,
        EmotionType.PLAYFUL: 0.60,
        EmotionType.WORRIED: 0.60,
        EmotionType.SAD: 0.55,
        EmotionType.CONFUSED: 0.55,
        EmotionType.CURIOUS: 0.55,
        EmotionType.CALM: 0.40,
    }

    def __init__(
        self,
        default_emotion: EmotionType = EmotionType.HAPPY,  # v2.29.13: 改为HAPPY，更符合活泼性格
        emotion_decay_rate: float = 0.08,  # v2.29.13: 降低衰减率，保持情绪更久
        max_history: int = 50,
        enable_emotion_memory: bool = True,
        enable_dual_source: bool = True,
        persist_file: Optional[str] = None,
        user_id: Optional[int] = None,
    ):
        """
        初始化情感引擎 (v2.29.13 优化)

        优化初始情绪状态，让猫娘女仆更活泼开朗

        Args:
            default_emotion: 默认情感状态（改为HAPPY）
            emotion_decay_rate: 情感衰减率（降低至0.08，保持情绪更久）
            max_history: 最大情感历史记录数
            enable_emotion_memory: 是否启用情绪记忆
            enable_dual_source: 是否启用双源情绪融合
            persist_file: 持久化文件路径
            user_id: 用户ID，用于创建用户特定的记忆路径
        """
        # v2.29.13: 初始情绪改为HAPPY，强度提升至0.7
        self.current_emotion = EmotionState(
            emotion_type=default_emotion, intensity=0.7, source="default"
        )
        self.emotion_history: List[EmotionState] = []
        self.emotion_decay_rate = emotion_decay_rate
        self.max_history = max_history
        # v2.29.13: 提升初始关系亲密度和情绪基线
        self.user_profile = EmotionProfile(
            relationship_level=0.7,  # 提升至0.7，表现亲近感
            emotion_baseline=0.5,  # 提升情绪基线至0.5，保持积极
        )

        # v3.1 新增配置
        self.enable_emotion_memory = enable_emotion_memory
        self.enable_dual_source = enable_dual_source

        # 情绪缓存 (性能优化)
        self._emotion_cache: Dict[str, EmotionType] = {}
        self._cache_timestamp: Optional[datetime] = None
        self._cache_ttl_seconds = 60  # 缓存有效期60秒
        self._last_persist_monotonic: float = 0.0

        # v3.1 持久化支持
        if persist_file:
            self.persist_file = persist_file
        elif user_id is not None:
            self.persist_file = str(
                Path(settings.data_dir) / "users" / str(user_id) / "memory" / "emotion_state.json"
            )
        else:
            self.persist_file = str(Path(settings.data_dir) / "memory" / "emotion_state.json")

        Path(self.persist_file).parent.mkdir(parents=True, exist_ok=True)

        # 加载持久化的情绪状态
        self._load_emotion_state()

        logger.info(
            "情感引擎初始化完成 (v3.1)，当前情感: %s (%.2f)",
            self.current_emotion.emotion_type.value,
            self.current_emotion.intensity,
        )

    def _load_emotion_state(self) -> None:
        """加载持久化的情绪状态 (v3.1 新增)"""
        try:
            if Path(self.persist_file).exists():
                import json

                data = json.loads(Path(self.persist_file).read_text(encoding="utf-8"))

                # 加载当前情绪
                if "current_emotion" in data:
                    emotion_data = data["current_emotion"]
                    self.current_emotion = EmotionState(
                        emotion_type=EmotionType[emotion_data["emotion_type"]],
                        intensity=emotion_data["intensity"],
                        timestamp=datetime.fromisoformat(emotion_data["timestamp"]),
                        trigger=emotion_data.get("trigger"),
                        source=emotion_data.get("source", "default"),
                        decay_rate=emotion_data.get("decay_rate", 0.1),
                        role_consistency=emotion_data.get("role_consistency", 1.0),
                    )

                # 加载情绪历史（最近50条）
                if "emotion_history" in data:
                    self.emotion_history = []
                    for hist in data["emotion_history"][-50:]:
                        self.emotion_history.append(
                            EmotionState(
                                emotion_type=EmotionType[hist["emotion_type"]],
                                intensity=hist["intensity"],
                                timestamp=datetime.fromisoformat(hist["timestamp"]),
                                trigger=hist.get("trigger"),
                                source=hist.get("source", "interaction"),
                                decay_rate=hist.get("decay_rate", 0.1),
                                role_consistency=hist.get("role_consistency", 1.0),
                            )
                        )

                # 加载用户档案
                if "user_profile" in data:
                    profile_data = data["user_profile"]
                    self.user_profile.user_name = profile_data.get("user_name")
                    self.user_profile.relationship_level = profile_data.get(
                        "relationship_level", 0.5
                    )
                    self.user_profile.positive_interactions = profile_data.get(
                        "positive_interactions", 0
                    )
                    self.user_profile.negative_interactions = profile_data.get(
                        "negative_interactions", 0
                    )
                    self.user_profile.memorable_moments = profile_data.get("memorable_moments", [])
                    self.user_profile.emotion_baseline = profile_data.get("emotion_baseline", 0.0)
                    self.user_profile.interaction_patterns = profile_data.get(
                        "interaction_patterns", {}
                    )

                    if profile_data.get("last_interaction"):
                        self.user_profile.last_interaction = datetime.fromisoformat(
                            profile_data["last_interaction"]
                        )

                    # 加载情绪记忆
                    if "emotion_memories" in profile_data:
                        self.user_profile.emotion_memories = []
                        for mem in profile_data["emotion_memories"][-100:]:
                            self.user_profile.emotion_memories.append(
                                EmotionMemory(
                                    content=mem["content"],
                                    emotion_tags=mem["emotion_tags"],
                                    intensity=mem["intensity"],
                                    timestamp=datetime.fromisoformat(mem["timestamp"]),
                                    memorable=mem.get("memorable", False),
                                    context=mem.get("context"),
                                )
                            )

                logger.info(
                    "加载情绪状态: %s (%.2f), 关系亲密度: %.2f",
                    self.current_emotion.emotion_type.value,
                    self.current_emotion.intensity,
                    self.user_profile.relationship_level,
                )
        except Exception as e:
            logger.warning("加载情绪状态失败: %s，使用默认值", e)

    def _save_emotion_state(self, *, force: bool = False) -> None:
        """保存情绪状态 (v3.1 新增)"""
        try:
            interval_s = float(getattr(settings.agent, "emotion_persist_interval_s", 0.0) or 0.0)
            if not force and interval_s > 0.0:
                now_mono = time.monotonic()
                if (now_mono - self._last_persist_monotonic) < interval_s:
                    return
                self._last_persist_monotonic = now_mono
            else:
                self._last_persist_monotonic = time.monotonic()

            # 序列化当前情绪
            current_emotion_data = {
                "emotion_type": self.current_emotion.emotion_type.name,
                "intensity": self.current_emotion.intensity,
                "timestamp": self.current_emotion.timestamp.isoformat(),
                "trigger": self.current_emotion.trigger,
                "source": self.current_emotion.source,
                "decay_rate": self.current_emotion.decay_rate,
                "role_consistency": self.current_emotion.role_consistency,
            }

            # 序列化情绪历史（最近50条）
            emotion_history_data = []
            for emotion in self.emotion_history[-50:]:
                emotion_history_data.append(
                    {
                        "emotion_type": emotion.emotion_type.name,
                        "intensity": emotion.intensity,
                        "timestamp": emotion.timestamp.isoformat(),
                        "trigger": emotion.trigger,
                        "source": emotion.source,
                        "decay_rate": emotion.decay_rate,
                        "role_consistency": emotion.role_consistency,
                    }
                )

            # 序列化用户档案
            user_profile_data = {
                "user_name": self.user_profile.user_name,
                "relationship_level": self.user_profile.relationship_level,
                "positive_interactions": self.user_profile.positive_interactions,
                "negative_interactions": self.user_profile.negative_interactions,
                "last_interaction": (
                    self.user_profile.last_interaction.isoformat()
                    if self.user_profile.last_interaction
                    else None
                ),
                "memorable_moments": self.user_profile.memorable_moments,
                "emotion_baseline": self.user_profile.emotion_baseline,
                "interaction_patterns": self.user_profile.interaction_patterns,
            }

            # 序列化情绪记忆（最近100条）
            emotion_memories_data = []
            for memory in self.user_profile.emotion_memories[-100:]:
                emotion_memories_data.append(
                    {
                        "content": memory.content,
                        "emotion_tags": memory.emotion_tags,
                        "intensity": memory.intensity,
                        "timestamp": memory.timestamp.isoformat(),
                        "memorable": memory.memorable,
                        "context": memory.context,
                    }
                )
            user_profile_data["emotion_memories"] = emotion_memories_data

            # 保存到文件
            data = {
                "current_emotion": current_emotion_data,
                "emotion_history": emotion_history_data,
                "user_profile": user_profile_data,
                "last_update": datetime.now().isoformat(),
            }

            _atomic_write_json(self.persist_file, data)

            logger.debug(
                "情绪状态已保存: %s (%.2f)",
                self.current_emotion.emotion_type.value,
                self.current_emotion.intensity,
            )
        except Exception as e:
            logger.error("保存情绪状态失败: %s", e)

    def persist(self, *, force: bool = False) -> None:
        """将当前情绪/用户档案状态持久化到磁盘。"""
        self._save_emotion_state(force=force)

    def flush(self) -> None:
        """强制落盘（用于程序退出或显式保存）。"""
        self.persist(force=True)

    def update_emotion(
        self,
        emotion_type: EmotionType,
        intensity: float,
        trigger: Optional[str] = None,
        source: str = "interaction",
        persist: bool = True,
    ) -> EmotionState:
        """
        更新当前情感状态 (v3.1 优化)

        Args:
            emotion_type: 新的情感类型
            intensity: 情感强度 (0.0-1.0)
            trigger: 触发原因
            source: 情绪来源 (need/memory/interaction/fused)

        Returns:
            更新后的情感状态
        """
        # 限制强度范围
        intensity = max(0.0, min(1.0, intensity))

        # v3.1 角色一致性评估
        role_consistency = self.evaluate_role_consistency(emotion_type)

        # 根据角色一致性调整强度
        if role_consistency < 0.5:
            # 低一致性情绪，减弱强度
            intensity *= role_consistency
            logger.debug(
                "情绪 %s 与角色一致性较低 (%.2f)，强度调整为 %.2f",
                emotion_type.value,
                role_consistency,
                intensity,
            )

        # 保存旧情感到历史
        if self.current_emotion:
            self.emotion_history.append(self.current_emotion)
            if len(self.emotion_history) > self.max_history:
                self.emotion_history.pop(0)

        # 更新当前情感
        self.current_emotion = EmotionState(
            emotion_type=emotion_type,
            intensity=intensity,
            trigger=trigger,
            source=source,
            decay_rate=self.emotion_decay_rate,
            role_consistency=role_consistency,
        )

        # v3.1 保存情绪状态
        if persist:
            self._save_emotion_state()

        logger.debug("情感更新: %s", self.current_emotion)
        return self.current_emotion

    def analyze_message(self, message: str) -> EmotionType:
        """
        分析消息内容，推断应该产生的情感反应

        v2.29.13 优化: 增强猫娘女仆的情绪特征（爱撒娇、爱吃醋）
        v2.48.5 性能优化: 使用类级常量，优化算法（目标<10ms）

        Args:
            message: 用户消息

        Returns:
            推断的情感类型
        """
        message = (message or "").strip()
        if not message:
            return EmotionType.HAPPY

        # v2.48.5: 使用小写转换一次，避免重复调用
        message_lower = message.lower()

        # v3.1: 轻量缓存（避免重复分析同一句话）
        now = datetime.now()
        if (
            self._cache_timestamp is None
            or (now - self._cache_timestamp).total_seconds() >= self._cache_ttl_seconds
        ):
            self._emotion_cache.clear()
            self._cache_timestamp = now
        else:
            cache_key = message_lower if len(message_lower) <= 200 else message_lower[:200]
            cached = self._emotion_cache.get(cache_key)
            if cached is not None:
                return cached
        if len(self._emotion_cache) >= 512:
            self._emotion_cache.clear()
            self._cache_timestamp = now

        # v2.48.5: 优先检查特殊情绪触发器（早期返回优化）
        # 检测"撒娇"相关内容（优先级更高，符合猫娘特性）
        if any(trigger in message_lower for trigger in self.AFFECTION_TRIGGERS):
            result = EmotionType.AFFECTIONATE
            cache_key = message_lower if len(message_lower) <= 200 else message_lower[:200]
            self._emotion_cache[cache_key] = result
            return result

        # 检测"吃醋"相关内容
        if any(trigger in message_lower for trigger in self.JEALOUSY_TRIGGERS):
            result = EmotionType.WORRIED
            cache_key = message_lower if len(message_lower) <= 200 else message_lower[:200]
            self._emotion_cache[cache_key] = result
            return result

        # v2.48.5: 优化关键词匹配 - 使用生成器表达式减少内存分配
        emotion_scores: Dict[EmotionType, int] = {}
        for emotion, keywords in self.EMOTION_KEYWORDS.items():
            score = sum(1 for keyword in keywords if keyword in message_lower)
            if score > 0:
                emotion_scores[emotion] = score

        # 返回得分最高的情感，如果没有匹配则返回开心（默认活泼状态）
        if emotion_scores:
            result = max(emotion_scores.items(), key=lambda x: x[1])[0]
        else:
            result = EmotionType.HAPPY  # v2.29.13: 改为HAPPY，保持活泼

        cache_key = message_lower if len(message_lower) <= 200 else message_lower[:200]
        self._emotion_cache[cache_key] = result
        return result

    def estimate_message_intensity(self, message: str, emotion_type: EmotionType) -> float:
        """
        基于消息文本粗略估计情感强度（0.0-1.0）。

        目标：
        - 足够快（纯字符串操作）
        - 稳定可解释（可预测）
        """
        text = (message or "").strip()
        if not text:
            return 0.0

        message_lower = text.lower()
        base = float(self.INTENSITY_BASELINE.get(emotion_type, 0.6))

        exclam = message_lower.count("!") + message_lower.count("！")
        ques = message_lower.count("?") + message_lower.count("？")
        base += 0.08 * min(exclam, 3)
        base += 0.05 * min(ques, 2)

        keywords = self.EMOTION_KEYWORDS.get(emotion_type, [])
        hits = 0
        for kw in keywords:
            if kw and kw in message_lower:
                hits += 1
                if hits >= 4:
                    break
        base += 0.03 * min(hits, 4)

        if any(w in message_lower for w in self.INTENSIFIER_KEYWORDS):
            base += 0.05

        if len(text) <= 4:
            base -= 0.10
        elif len(text) >= 120:
            base += 0.05

        return max(0.0, min(1.0, base))

    def is_negative_interaction(
        self,
        message: str,
        emotion_type: Optional[EmotionType] = None,
    ) -> bool:
        """
        粗略判断一次互动是否“关系受损”（用于档案更新的负面信号）。

        约定：
        - 只对“明显攻击/辱骂/驱赶”类内容判为负面，避免把“难过/担心”误判为负面互动。
        """
        text = (message or "").strip()
        if not text:
            return False

        message_lower = text.lower()
        if any(w in message_lower for w in self.NEGATIVE_INTERACTION_KEYWORDS):
            return True

        if emotion_type is None:
            try:
                emotion_type = self.analyze_message(text)
            except Exception:
                return False

        return emotion_type == EmotionType.ANGRY

    def decay_emotion(self, persist: bool = True) -> None:
        """
        情感自然衰减 (v2.29.13 优化)

        优化衰减目标：让猫娘女仆回归到开心状态而非平静
        """
        # v2.29.13: 不衰减HAPPY状态，保持活泼
        if self.current_emotion.emotion_type == EmotionType.HAPPY:
            return

        if self.current_emotion.emotion_type != EmotionType.CALM:
            new_intensity = self.current_emotion.intensity * (1 - self.current_emotion.decay_rate)
            if new_intensity < 0.2:
                # v2.29.13: 强度过低时回归开心状态（而非平静）
                self.update_emotion(
                    EmotionType.HAPPY,
                    0.6,
                    "自然衰减回归开心",
                    source="decay",
                    persist=persist,
                )
            else:
                self.current_emotion.intensity = new_intensity
                # v3.1 保存衰减后的状态
                if persist:
                    self._save_emotion_state()

    def get_emotion_modifier(self) -> str:
        """
        获取当前情感的语言修饰符，用于调整回复风格

        Returns:
            情感修饰符文本
        """
        emotion = self.current_emotion
        intensity = emotion.intensity

        # 根据强度选择修饰符
        level = "high" if intensity > 0.7 else "medium" if intensity > 0.4 else "low"
        return self.EMOTION_STYLE_MODIFIERS.get(emotion.emotion_type, {}).get(level, "")

    def update_user_profile(
        self,
        interaction_positive: bool,
        memorable_moment: Optional[str] = None,
        persist: bool = True,
    ) -> None:
        """
        更新用户情感档案 (v3.1 优化)

        Args:
            interaction_positive: 本次互动是否为正面
            memorable_moment: 难忘时刻描述
        """
        self.user_profile.last_interaction = datetime.now()

        if interaction_positive:
            self.user_profile.positive_interactions += 1
            # 增加亲密度（根据当前亲密度动态调整增长速度）
            growth_rate = 0.01 * (1.0 - self.user_profile.relationship_level * 0.5)
            self.user_profile.relationship_level = min(
                1.0, self.user_profile.relationship_level + growth_rate
            )
            # v3.1 更新情绪基线（正面互动提升基线）
            self.user_profile.emotion_baseline = min(
                1.0, self.user_profile.emotion_baseline + 0.005
            )
        else:
            self.user_profile.negative_interactions += 1
            # 降低亲密度
            self.user_profile.relationship_level = max(
                0.0, self.user_profile.relationship_level - 0.02
            )
            # v3.1 更新情绪基线（负面互动降低基线）
            self.user_profile.emotion_baseline = max(
                -1.0, self.user_profile.emotion_baseline - 0.01
            )

        if memorable_moment:
            self.user_profile.memorable_moments.append(memorable_moment)
            if len(self.user_profile.memorable_moments) > 20:
                self.user_profile.memorable_moments.pop(0)

        # v3.1 保存用户档案
        if persist:
            self._save_emotion_state()

        logger.debug(f"用户档案更新: 亲密度={self.user_profile.relationship_level:.2f}")

    def get_relationship_description(self) -> str:
        """获取当前关系描述"""
        level = self.user_profile.relationship_level
        if level > 0.8:
            return "非常亲密的主人"
        elif level > 0.6:
            return "亲密的主人"
        elif level > 0.4:
            return "熟悉的主人"
        elif level > 0.2:
            return "主人"
        else:
            return "刚认识的主人"

    def get_emotion_context(self) -> str:
        """
        获取情感上下文信息，用于增强 prompt (v2.29.14 优化)

        优化上下文，强化角色身份认知

        Returns:
            情感上下文描述
        """
        user_name = settings.agent.user
        char_name = settings.agent.char

        emotion_label = self.current_emotion.emotion_type.value
        intensity = float(self.current_emotion.intensity or 0.0)
        relationship_desc = self.get_relationship_description()
        modifier = self.get_emotion_modifier()

        intensity_label = "高" if intensity > 0.7 else "中" if intensity > 0.4 else "低"
        line = (
            "\n【情感】"
            f"{emotion_label}（强度：{intensity_label}）；"
            f"与{user_name}关系：{relationship_desc}。\n"
        )
        if modifier:
            line += f"语气基调：{modifier}。"
        line += (
            "把情感融入表达，不要在回复里直接复述“情感/强度/数值”。" f"自称优先用“{char_name}”。"
        )
        return line

    def add_emotion_memory(
        self,
        content: str,
        emotion_tags: Dict[str, float],
        intensity: float,
        memorable: bool = False,
        context: Optional[str] = None,
    ) -> None:
        """
        添加情绪记忆 (v3.1 新增)

        Args:
            content: 记忆内容
            emotion_tags: 情绪标签字典
            intensity: 总体情绪强度
            memorable: 是否为难忘时刻
            context: 情境上下文
        """
        if not self.enable_emotion_memory:
            return

        memory = EmotionMemory(
            content=content,
            emotion_tags=emotion_tags,
            intensity=intensity,
            memorable=memorable,
            context=context,
        )

        self.user_profile.emotion_memories.append(memory)

        # 限制记忆数量，保留最重要的
        if len(self.user_profile.emotion_memories) > 100:
            # 优先保留难忘时刻和高强度情绪
            self.user_profile.emotion_memories.sort(
                key=lambda m: (m.memorable, m.intensity), reverse=True
            )
            self.user_profile.emotion_memories = self.user_profile.emotion_memories[:100]

        logger.debug("添加情绪记忆 (强度: %.2f)", intensity)

    def retrieve_similar_emotion_memories(
        self, current_context: str, top_k: int = 3
    ) -> List[EmotionMemory]:
        """
        检索相似情境的情绪记忆 (v3.1 新增)

        Args:
            current_context: 当前情境描述
            top_k: 返回最相似的k个记忆

        Returns:
            相似情绪记忆列表
        """
        if not self.enable_emotion_memory or not self.user_profile.emotion_memories:
            return []

        # 简单的关键词匹配 (未来可以用向量相似度)
        scored_memories = []
        current_words = set(current_context.lower().split())

        for memory in self.user_profile.emotion_memories:
            memory_words = set(memory.content.lower().split())
            if memory.context:
                memory_words.update(memory.context.lower().split())

            # 计算词汇重叠度
            overlap = len(current_words & memory_words)
            if overlap > 0:
                # 考虑时间衰减
                age_days = (datetime.now() - memory.timestamp).days
                time_decay = max(0.1, 1.0 - age_days / 365.0)  # 一年后衰减到0.1

                score = overlap * memory.intensity * time_decay
                if memory.memorable:
                    score *= 1.5  # 难忘时刻加权

                scored_memories.append((score, memory))

        # 返回得分最高的top_k个
        scored_memories.sort(key=lambda x: x[0], reverse=True)
        return [m for _, m in scored_memories[:top_k]]

    def fuse_emotions(
        self,
        need_emotion: Optional[EmotionType] = None,
        memory_emotions: Optional[List[EmotionMemory]] = None,
        interaction_emotion: Optional[EmotionType] = None,
    ) -> EmotionState:
        """
        融合多源情绪 (v3.1 新增 - 双源情绪模型)

        Args:
            need_emotion: 需求驱动的情绪
            memory_emotions: 记忆检索的情绪
            interaction_emotion: 当前互动触发的情绪

        Returns:
            融合后的情绪状态
        """
        if not self.enable_dual_source:
            # 如果未启用双源融合，直接返回互动情绪
            if interaction_emotion:
                return EmotionState(
                    emotion_type=interaction_emotion, intensity=0.6, source="interaction"
                )
            return self.current_emotion

        # 收集所有情绪及其权重
        emotion_scores: Dict[EmotionType, float] = {}

        # 1. 需求驱动情绪 (权重 0.4)
        if need_emotion:
            emotion_scores[need_emotion] = emotion_scores.get(need_emotion, 0.0) + 0.4

        # 2. 记忆检索情绪 (权重 0.3)
        if memory_emotions:
            for memory in memory_emotions:
                dominant_emotion_name, intensity = memory.get_dominant_emotion()
                try:
                    emotion_type = EmotionType[dominant_emotion_name.upper()]
                    emotion_scores[emotion_type] = (
                        emotion_scores.get(emotion_type, 0.0) + 0.3 * intensity
                    )
                except KeyError:
                    logger.debug("未知情绪类型: %s, 跳过", dominant_emotion_name)

        # 3. 当前互动情绪 (权重 0.3)
        if interaction_emotion:
            emotion_scores[interaction_emotion] = emotion_scores.get(interaction_emotion, 0.0) + 0.3

        # 选择得分最高的情绪
        if emotion_scores:
            fused_emotion = max(emotion_scores.items(), key=lambda x: x[1])
            return EmotionState(
                emotion_type=fused_emotion[0],
                intensity=min(1.0, fused_emotion[1]),
                source="fused",
                trigger="双源情绪融合",
            )

        return self.current_emotion

    def evaluate_role_consistency(self, emotion_type: EmotionType) -> float:
        """
        评估情绪与角色的一致性 (v3.1 新增)

        猫娘女仆角色特征：
        - 温柔、体贴、忠诚
        - 俏皮、可爱、活泼
        - 不应过度激烈或负面

        Args:
            emotion_type: 情绪类型

        Returns:
            一致性评分 (0.0-1.0)
        """
        # 高度一致的情绪
        high_consistency = {
            EmotionType.HAPPY,
            EmotionType.PLAYFUL,
            EmotionType.AFFECTIONATE,
            EmotionType.CURIOUS,
            EmotionType.CALM,
            EmotionType.EXCITED,
            EmotionType.PROTECTIVE,
        }

        # 中度一致的情绪
        medium_consistency = {EmotionType.WORRIED, EmotionType.SURPRISED, EmotionType.CONFUSED}

        # 低度一致的情绪 (应避免或减弱)
        low_consistency = {EmotionType.ANGRY, EmotionType.SAD}

        if emotion_type in high_consistency:
            return 1.0
        elif emotion_type in medium_consistency:
            return 0.7
        elif emotion_type in low_consistency:
            return 0.3
        else:
            return 0.5

    def get_stats(self) -> Dict[str, Any]:
        """获取情感引擎统计信息 (v3.1 优化)"""
        return {
            "current_emotion": str(self.current_emotion),
            "emotion_history_count": len(self.emotion_history),
            "relationship_level": self.user_profile.relationship_level,
            "positive_interactions": self.user_profile.positive_interactions,
            "negative_interactions": self.user_profile.negative_interactions,
            "memorable_moments_count": len(self.user_profile.memorable_moments),
            # v3.1 新增
            "emotion_memories_count": len(self.user_profile.emotion_memories),
            "emotion_baseline": self.user_profile.emotion_baseline,
            "dual_source_enabled": self.enable_dual_source,
            "emotion_memory_enabled": self.enable_emotion_memory,
        }
