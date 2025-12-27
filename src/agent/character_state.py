"""
角色动态状态系统

实现角色的动态状态（饥饿、疲劳、心情等），让角色更加真实和有生命力。
这是 v2.5 的核心功能之一，用于增强沉浸感。
"""

import os
import json
import secrets
import time
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Dict, Optional

from src.config.settings import settings
from src.utils.logger import get_logger

logger = get_logger(__name__)


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


class CharacterState:
    """
    角色动态状态管理器

    管理角色的各种状态值：
    - 饥饿度 (hunger): 0-100，越高越饿
    - 疲劳度 (fatigue): 0-100，越高越累
    - 活力值 (energy): 0-100，越高越有活力
    - 满足度 (satisfaction): 0-100，越高越满足
    - 孤独感 (loneliness): 0-100，越高越孤独

    状态会随时间自然变化，也会受到互动影响。
    """

    def __init__(
        self,
        persist_file: Optional[str] = None,
        enable_auto_decay: bool = True,
    ):
        """
        初始化角色状态系统

        Args:
            persist_file: 持久化文件路径
            enable_auto_decay: 是否启用自动衰减
        """
        # 状态值 (0-100)
        self.hunger: float = 0.0  # 饥饿度
        self.fatigue: float = 0.0  # 疲劳度
        self.energy: float = 100.0  # 活力值
        self.satisfaction: float = 80.0  # 满足度
        self.loneliness: float = 0.0  # 孤独感

        # 上次更新时间
        self.last_update: datetime = datetime.now()
        self.last_interaction: datetime = datetime.now()

        # 配置
        self.enable_auto_decay = enable_auto_decay
        self._persist_interval_s = max(
            0.0,
            float(getattr(settings.agent, "character_state_persist_interval_s", 2.0) or 0.0),
        )
        self._last_persist_monotonic: float = 0.0
        self._dirty: bool = False
        self._lock = Lock()

        # 持久化文件
        self.persist_file = persist_file or str(
            Path(settings.data_dir) / "memory" /
            "character_state.json"
        )
        Path(self.persist_file).parent.mkdir(parents=True, exist_ok=True)

        # 加载持久化状态
        self._load_state()

        logger.info("角色状态系统初始化完成")

    def _load_state(self) -> None:
        """从文件加载状态"""
        try:
            if Path(self.persist_file).exists():
                with open(self.persist_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.hunger = data.get("hunger", 0.0)
                    self.fatigue = data.get("fatigue", 0.0)
                    self.energy = data.get("energy", 100.0)
                    self.satisfaction = data.get("satisfaction", 80.0)
                    self.loneliness = data.get("loneliness", 0.0)
                    self.last_update = datetime.fromisoformat(
                        data.get("last_update", datetime.now().isoformat())
                    )
                    self.last_interaction = datetime.fromisoformat(
                        data.get("last_interaction", datetime.now().isoformat())
                    )
                logger.info("角色状态已从文件加载")
        except Exception as e:
            logger.warning(f"加载角色状态失败: {e}，使用默认值")

    def _save_state(self, *, force: bool = False) -> None:
        """保存状态到文件（带节流，避免每次交互都落盘）。"""
        with self._lock:
            if not force and not self._dirty:
                return

            interval_s = self._persist_interval_s
            now_mono = time.monotonic()
            if not force and interval_s > 0.0:
                if (now_mono - self._last_persist_monotonic) < interval_s:
                    return

            self._last_persist_monotonic = now_mono
            data = {
                "hunger": self.hunger,
                "fatigue": self.fatigue,
                "energy": self.energy,
                "satisfaction": self.satisfaction,
                "loneliness": self.loneliness,
                "last_update": self.last_update.isoformat(),
                "last_interaction": self.last_interaction.isoformat(),
            }
            try:
                _atomic_write_json(self.persist_file, data)
                self._dirty = False
            except Exception as e:
                logger.error(f"保存角色状态失败: {e}")

    def update_auto_decay(self, persist: bool = True) -> None:
        """
        自动衰减/增长状态值

        基于时间流逝自动更新状态：
        - 饥饿度增加
        - 疲劳度增加
        - 活力值减少
        - 孤独感增加（如果长时间没有互动）
        """
        if not self.enable_auto_decay:
            return

        now = datetime.now()
        time_passed = (now - self.last_update).total_seconds() / 3600  # 小时

        if time_passed < 0.01:  # 少于36秒，不更新
            return

        # 饥饿度增加 (每小时 +5)
        self.hunger = min(100.0, self.hunger + time_passed * 5)

        # 疲劳度增加 (每小时 +3)
        self.fatigue = min(100.0, self.fatigue + time_passed * 3)

        # 活力值减少 (每小时 -4)
        self.energy = max(0.0, self.energy - time_passed * 4)

        # 孤独感增加（如果长时间没有互动）
        time_since_interaction = (now - self.last_interaction).total_seconds() / 3600
        if time_since_interaction > 1:  # 超过1小时
            self.loneliness = min(100.0, self.loneliness + time_since_interaction * 2)

        self.last_update = now
        self._dirty = True
        if persist:
            self._save_state()

    def persist(self, *, force: bool = False) -> None:
        """将当前角色状态持久化到磁盘。"""
        self._save_state(force=force)

    def on_interaction(self, interaction_type: str = "chat", persist: bool = True) -> None:
        """
        处理互动事件

        Args:
            interaction_type: 互动类型 (chat, feed, play, rest)
        """
        self.update_auto_decay(persist=False)  # 先更新自动衰减

        now = datetime.now()
        self.last_interaction = now

        # 根据互动类型更新状态
        if interaction_type == "chat":
            # 普通对话：减少孤独感，轻微增加疲劳
            self.loneliness = max(0.0, self.loneliness - 10)
            self.fatigue = min(100.0, self.fatigue + 1)
            self.satisfaction = min(100.0, self.satisfaction + 2)

        elif interaction_type == "feed":
            # 喂食：减少饥饿度，增加满足度
            self.hunger = max(0.0, self.hunger - 30)
            self.satisfaction = min(100.0, self.satisfaction + 15)

        elif interaction_type == "play":
            # 玩耍：增加活力，减少孤独感，增加疲劳
            self.energy = min(100.0, self.energy + 10)
            self.loneliness = max(0.0, self.loneliness - 20)
            self.fatigue = min(100.0, self.fatigue + 10)
            self.satisfaction = min(100.0, self.satisfaction + 10)

        elif interaction_type == "rest":
            # 休息：减少疲劳，恢复活力
            self.fatigue = max(0.0, self.fatigue - 40)
            self.energy = min(100.0, self.energy + 30)

        self._dirty = True
        if persist:
            self._save_state()

    def flush(self) -> None:
        """强制落盘（用于程序退出或显式保存）。"""
        self._dirty = True
        self._save_state(force=True)

    def _describe_state(self) -> str:
        descriptions = []

        # 饥饿度
        if self.hunger > 80:
            descriptions.append("非常饿，肚子咕咕叫")
        elif self.hunger > 60:
            descriptions.append("有些饿了")
        elif self.hunger > 40:
            descriptions.append("略微有点饿")

        # 疲劳度
        if self.fatigue > 80:
            descriptions.append("非常疲惫，困得睁不开眼")
        elif self.fatigue > 60:
            descriptions.append("有些累了")
        elif self.fatigue > 40:
            descriptions.append("略微有点累")

        # 活力值
        if self.energy < 20:
            descriptions.append("精神不振，无精打采")
        elif self.energy < 40:
            descriptions.append("精力有些不足")
        elif self.energy > 80:
            descriptions.append("精力充沛，活力满满")

        # 孤独感
        if self.loneliness > 70:
            descriptions.append("感到很孤独，渴望主人的陪伴")
        elif self.loneliness > 40:
            descriptions.append("有些想念主人")

        # 满足度
        if self.satisfaction > 90:
            descriptions.append("心满意足")
        elif self.satisfaction < 30:
            descriptions.append("有些不满足")

        if not descriptions:
            return "状态良好"

        return "、".join(descriptions)

    def get_state_description(self) -> str:
        """
        获取状态描述（用于添加到提示词）

        Returns:
            str: 状态描述
        """
        self.update_auto_decay(persist=False)  # 先更新状态
        return self._describe_state()

    def get_state_context(self) -> str:
        """
        获取状态上下文（用于添加到提示词）

        Returns:
            str: 状态上下文
        """
        description = self.get_state_description()

        return f"""
【当前角色状态】
饥饿度: {self.hunger:.1f}/100
疲劳度: {self.fatigue:.1f}/100
活力值: {self.energy:.1f}/100
满足度: {self.satisfaction:.1f}/100
孤独感: {self.loneliness:.1f}/100

状态描述: {description}

请根据当前状态调整你的回复风格和行为。例如：
- 如果很饿，可以提到想吃东西
- 如果很累，语气可能更慵懒
- 如果孤独，会更加渴望主人的陪伴
- 如果活力充沛，会更加活泼
"""

    def get_stats(self) -> Dict:
        """
        获取状态统计信息

        Returns:
            Dict: 状态统计
        """
        self.update_auto_decay(persist=False)

        return {
            "hunger": self.hunger,
            "fatigue": self.fatigue,
            "energy": self.energy,
            "satisfaction": self.satisfaction,
            "loneliness": self.loneliness,
            "description": self._describe_state(),
            "last_update": self.last_update.isoformat(),
            "last_interaction": self.last_interaction.isoformat(),
        }

    def reset_state(self) -> None:
        """重置所有状态到默认值"""
        self.hunger = 0.0
        self.fatigue = 0.0
        self.energy = 100.0
        self.satisfaction = 80.0
        self.loneliness = 0.0
        self.last_update = datetime.now()
        self.last_interaction = datetime.now()
        self._save_state()
        logger.info("角色状态已重置")
