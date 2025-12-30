"""
高级情绪系统模块 (v2.28.2 深度升级)

实现基于PAD模型和动态衰减的情绪影响计算
支持情绪持久化、自然衰减和多维度情绪建模

v2.28.2 升级内容:
- 引入PAD模型（Pleasure-Arousal-Dominance）三维情绪空间
- 实现动态情绪衰减机制（指数衰减 + Sigmoid平滑）
- 优化情绪影响函数（基于2025年最新研究）
- 增强情绪状态建模（更细粒度的情绪分类）
- 添加情绪惯性和反弹机制
"""

import ast
import json
import math
import operator
import os
import secrets
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.config.settings import settings
from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class PADState:
    """
    PAD情绪状态模型 (Pleasure-Arousal-Dominance)

    基于Mehrabian & Russell (1974)的PAD模型
    参考: Project Riley (2025) - arxiv.org/html/2505.20521v1

    v2.29.13 优化: 提升初始值，让猫娘女仆更活泼开朗
    """

    pleasure: float = 0.6  # 愉悦度 (-1.0 到 1.0) - 提升至0.6，表现开朗性格
    arousal: float = 0.5  # 唤醒度 (-1.0 到 1.0) - 提升至0.5，表现活泼特质
    dominance: float = 0.3  # 支配度 (-1.0 到 1.0) - 提升至0.3，表现自信可爱

    def to_mood_value(self) -> float:
        """
        将PAD状态转换为单一情绪值

        使用加权平均，愉悦度权重最高
        """
        return 0.6 * self.pleasure + 0.3 * self.arousal + 0.1 * self.dominance

    def to_dict(self) -> Dict:
        """转换为字典"""
        return asdict(self)


PAD_BASELINE = PADState()


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


_BIN_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
}
_UNARY_OPS = {ast.UAdd: lambda x: x, ast.USub: operator.neg}


def _safe_eval_math_formula(formula: str, *, x: float) -> float:
    """Safely evaluate a math-only expression string against a small allowlist."""

    def _eval(node: ast.AST, env: Dict[str, Any]) -> float:
        if isinstance(node, ast.Expression):
            return _eval(node.body, env)
        if isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float)):
                return float(node.value)
            raise ValueError("unsupported constant")
        if isinstance(node, ast.Name):
            if node.id not in env:
                raise ValueError(f"unknown name: {node.id}")
            value = env[node.id]
            if isinstance(value, (int, float)):
                return float(value)
            raise ValueError(f"unsupported name value: {node.id}")
        if isinstance(node, ast.BinOp):
            op = _BIN_OPS.get(type(node.op))
            if op is None:
                raise ValueError("unsupported binary op")
            return float(op(_eval(node.left, env), _eval(node.right, env)))
        if isinstance(node, ast.UnaryOp):
            op = _UNARY_OPS.get(type(node.op))
            if op is None:
                raise ValueError("unsupported unary op")
            return float(op(_eval(node.operand, env)))
        if isinstance(node, ast.Call):
            if node.keywords:
                raise ValueError("keyword args not allowed")
            if not isinstance(node.func, ast.Name):
                raise ValueError("only direct function calls allowed")
            func = env.get(node.func.id)
            if func is None or not callable(func):
                raise ValueError(f"unknown function: {node.func.id}")
            args = [_eval(arg, env) for arg in node.args]
            return float(func(*args))
        raise ValueError(f"unsupported expression: {type(node).__name__}")

    env = {
        "x": float(x),
        "pi": math.pi,
        "e": math.e,
        "log": math.log,
        "sqrt": math.sqrt,
        "exp": math.exp,
        "sin": math.sin,
        "cos": math.cos,
        "tan": math.tan,
        "abs": abs,
        "pow": pow,
    }

    tree = ast.parse(formula, mode="eval")
    value = _eval(tree, env)
    if not math.isfinite(value):
        raise ValueError("non-finite result")
    return float(value)


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


class MoodSystem:
    """
    高级情绪系统 (v2.28.2 深度升级)

    基于PAD模型和动态衰减的情绪影响计算
    支持情绪持久化、自然衰减和多维度情绪建模

    v2.28.2 新特性:
    - PAD三维情绪空间建模
    - 动态情绪衰减（指数衰减 + Sigmoid平滑）
    - 情绪惯性和反弹机制
    - 更细粒度的情绪状态分类（11种状态）
    - 优化的情绪影响函数
    """

    def __init__(self, persist_file: Optional[str] = None, user_id: Optional[int] = None):
        """
        初始化情绪系统 (v2.28.2 增强)

        Args:
            persist_file: 情绪持久化文件路径
            user_id: 用户ID，用于创建用户特定的记忆路径
        """
        if not settings.agent.mood_system_enabled:
            logger.info("情绪系统未启用")
            self.enabled = False
            return

        self.enabled = True

        # v2.28.2: PAD三维情绪状态
        # v2.29.13: 优化初始状态，让猫娘女仆更活泼开朗
        self.pad_state = PADState()
        self.mood_value = self.pad_state.to_mood_value()  # 从PAD计算初始情绪值（约0.51）
        self.mood_history: List[Dict[str, Any]] = []  # 情绪历史
        self._last_persist_monotonic: float = 0.0

        # v2.28.2: 情绪衰减配置
        # v2.29.13: 优化衰减参数，让正面情绪保持更久
        self.decay_rate = 0.03  # 每次更新的衰减率（3%，降低以保持情绪）
        self.decay_half_life = 5400  # 半衰期（秒），1.5小时（延长以保持活泼）
        self.last_update_time = datetime.now()

        # v2.28.2: 情绪惯性配置
        # v2.29.13: 优化惯性参数，让情绪变化更自然
        self.inertia_factor = 0.6  # 情绪惯性系数（降低至0.6，更易受影响）
        self.rebound_threshold = 0.75  # 情绪反弹阈值（降低，更容易反弹）
        self.rebound_strength = 0.4  # 反弹强度（提升，更强的情绪恢复力）

        # 持久化文件 - 支持用户特定路径
        if persist_file:
            self.persist_file = persist_file
        elif user_id is not None:
            self.persist_file = str(
                Path(settings.data_dir) / "users" / str(user_id) / "memory" / "mood_state.json"
            )
        else:
            self.persist_file = str(Path(settings.data_dir) / "memory" / "mood_state.json")

        Path(self.persist_file).parent.mkdir(parents=True, exist_ok=True)

        # 加载持久化的情绪值
        if settings.agent.mood_persists:
            self._load_mood_state()

        logger.info(
            f"情绪系统初始化完成 (v2.28.2) - "
            f"情绪值: {self.mood_value:.2f}, "
            f"PAD: P={self.pad_state.pleasure:.2f}, A={self.pad_state.arousal:.2f}, D={self.pad_state.dominance:.2f}"
        )

    def _load_mood_state(self) -> None:
        """加载持久化的情绪状态 (v2.28.2 增强)"""
        try:
            if Path(self.persist_file).exists():
                data = json.loads(Path(self.persist_file).read_text(encoding="utf-8"))
                baseline = PAD_BASELINE
                saved_mood_value = data.get("mood_value")
                self.mood_history = data.get("mood_history", [])

                # v2.28.2: 加载PAD状态
                if "pad_state" in data:
                    pad_data = data.get("pad_state") or {}
                    self.pad_state = PADState(
                        pleasure=float(pad_data.get("pleasure", baseline.pleasure)),
                        arousal=float(pad_data.get("arousal", baseline.arousal)),
                        dominance=float(pad_data.get("dominance", baseline.dominance)),
                    )
                else:
                    # 旧版本可能只保存 mood_value，这里尽量保持 PAD/mood 一致
                    self.pad_state = PADState(
                        pleasure=baseline.pleasure,
                        arousal=baseline.arousal,
                        dominance=baseline.dominance,
                    )
                    if saved_mood_value is not None:
                        desired = _clamp(float(saved_mood_value), -1.0, 1.0)
                        self.pad_state.pleasure = _clamp(
                            (
                                desired
                                - 0.3 * self.pad_state.arousal
                                - 0.1 * self.pad_state.dominance
                            )
                            / 0.6,
                            -1.0,
                            1.0,
                        )

                # v2.28.2: 加载最后更新时间
                if "last_update_time" in data:
                    self.last_update_time = datetime.fromisoformat(data["last_update_time"])

                # 修复：始终从 PAD 计算 mood_value，避免状态不一致
                self.mood_value = self.pad_state.to_mood_value()
                self._trim_history()

                logger.info(
                    f"加载情绪状态: {self.mood_value:.2f}, "
                    f"PAD: P={self.pad_state.pleasure:.2f}, A={self.pad_state.arousal:.2f}, D={self.pad_state.dominance:.2f}"
                )
        except Exception as e:
            from src.utils.exceptions import handle_exception

            handle_exception(e, logger, "加载情绪状态失败")

    def _save_mood_state(self, *, force: bool = False) -> None:
        """保存情绪状态 (v2.28.2 增强)"""
        if not settings.agent.mood_persists:
            return

        try:
            interval_s = float(getattr(settings.agent, "mood_persist_interval_s", 0.0) or 0.0)
            if not force and interval_s > 0.0:
                now_mono = time.monotonic()
                if (now_mono - self._last_persist_monotonic) < interval_s:
                    return
                self._last_persist_monotonic = now_mono
            else:
                self._last_persist_monotonic = time.monotonic()

            history_cap = int(getattr(settings.agent, "mood_history_max_len", 0) or 0)
            persist_cap = min(200, history_cap) if history_cap > 0 else 200
            data = {
                "mood_value": self.mood_value,
                "pad_state": self.pad_state.to_dict(),  # v2.28.2: 保存PAD状态
                "mood_history": self.mood_history[-persist_cap:],  # 控制文件体积
                "last_update": datetime.now().isoformat(),
                "last_update_time": self.last_update_time.isoformat(),  # v2.28.2
                "version": "2.28.2",  # v2.28.2: 版本标记
            }
            _atomic_write_json(self.persist_file, data)
        except Exception as e:
            from src.utils.exceptions import handle_exception

            handle_exception(e, logger, "保存情绪状态失败")

    def persist(self, *, force: bool = False) -> None:
        """将当前情绪状态持久化到磁盘。"""
        self._save_mood_state(force=force)

    def flush(self) -> None:
        """强制落盘（用于程序退出或显式保存）。"""
        self.persist(force=True)

    def _apply_natural_decay(self) -> None:
        """
        应用自然情绪衰减 (v2.28.2 新增)

        基于指数衰减模型，情绪会随时间自然回归平静状态
        参考: 情感计算领域的标准衰减模型
        """
        if not self.enabled:
            return

        # 计算时间差（秒）
        now = datetime.now()
        time_delta = (now - self.last_update_time).total_seconds()

        if time_delta <= 0:
            return

        # 指数衰减公式: value(t) = value(0) * exp(-λt)
        decay_lambda = math.log(2) / self.decay_half_life
        decay_factor = math.exp(-decay_lambda * time_delta)

        # 应用衰减到PAD状态（趋向基线而非趋向 0）
        baseline = PAD_BASELINE
        self.pad_state.pleasure = (
            baseline.pleasure + (self.pad_state.pleasure - baseline.pleasure) * decay_factor
        )
        self.pad_state.arousal = (
            baseline.arousal + (self.pad_state.arousal - baseline.arousal) * decay_factor
        )
        self.pad_state.dominance = (
            baseline.dominance + (self.pad_state.dominance - baseline.dominance) * decay_factor
        )

        # 更新综合情绪值
        old_mood = self.mood_value
        self.mood_value = self.pad_state.to_mood_value()

        # 记录衰减
        if abs(old_mood - self.mood_value) > 0.01:
            logger.debug(
                f"情绪自然衰减: {old_mood:.2f} -> {self.mood_value:.2f} "
                f"(时间间隔: {time_delta:.1f}秒)"
            )

        self.last_update_time = now

    def _sigmoid(self, x: float, steepness: float = 1.0, midpoint: float = 0.0) -> float:
        """
        Sigmoid函数 (v2.28.2 新增)

        用于平滑情绪变化，避免突变

        Args:
            x: 输入值
            steepness: 陡峭度（越大变化越快）
            midpoint: 中点位置

        Returns:
            float: Sigmoid输出 (0.0-1.0)
        """
        return 1.0 / (1.0 + math.exp(-steepness * (x - midpoint)))

    def _advanced_impact_function(self, x: float, is_positive: bool = True) -> float:
        """
        高级情绪影响函数 (v2.28.2 新增)

        基于2025年最新研究的优化函数:
        - 正面影响: 使用对数增长 + 平方根平滑
        - 负面影响: 使用Sigmoid曲线 + 指数衰减

        参考:
        - Project Riley (2025): PAD模型情绪计算
        - 双Sigmoid函数情绪建模 (MDPI 2025)

        Args:
            x: 输入强度 (0.0-1.0)
            is_positive: 是否为正面影响

        Returns:
            float: 影响值 (-1.0 到 1.0)
        """
        if x <= 0:
            return 0.0

        if is_positive:
            # 正面影响: 对数增长 + 平方根平滑
            # 特点: 初期增长快，后期趋于平缓（边际效应递减）
            log_component = math.log(1 + 2 * x)  # 对数增长
            sqrt_component = math.sqrt(x)  # 平方根平滑
            sigmoid_component = self._sigmoid(x, steepness=5, midpoint=0.5)  # Sigmoid平滑

            # 加权组合
            result = 0.4 * log_component + 0.3 * sqrt_component + 0.3 * sigmoid_component

            # 归一化到 [0, 1]
            result = min(1.0, result / 1.5)

        else:
            # 负面影响: 双Sigmoid曲线
            # 特点: 初期缓慢，中期快速，后期趋于饱和
            sigmoid1 = self._sigmoid(x, steepness=6, midpoint=0.3)  # 早期Sigmoid
            sigmoid2 = self._sigmoid(x, steepness=4, midpoint=0.7)  # 后期Sigmoid
            exp_component = 1 - math.exp(-3 * x)  # 指数增长

            # 加权组合
            result = 0.4 * sigmoid1 + 0.3 * sigmoid2 + 0.3 * exp_component

            # 归一化到 [0, 1]
            result = min(1.0, result)

        return result

    def calculate_impact(self, x: float, is_positive: bool = True) -> float:
        """
        计算情绪影响 (v2.28.2 深度优化)

        使用高级情绪影响函数，支持向后兼容旧版配置

        Args:
            x: 输入值 (0.0-1.0)
            is_positive: 是否为正面影响

        Returns:
            float: 影响值 (0.0-1.0)
        """
        if not self.enabled:
            return 0.0

        if x <= 0.0:
            return 0.0

        # 限制输入范围
        x = max(0.0, min(1.0, x))

        # v2.28.2: 优先使用高级影响函数
        try:
            result = self._advanced_impact_function(x, is_positive)

            # 归一化到合理范围
            result = max(0.0, min(1.0, result))

            return result

        except Exception as e:
            logger.warning("高级影响函数计算失败，回退到传统方法: %s", e)

            # 回退到传统方法（向后兼容）
            try:
                # 获取函数表达式
                if is_positive:
                    formula = settings.agent.mood_functions.positive_impact
                else:
                    formula = settings.agent.mood_functions.negative_impact

                raw = _safe_eval_math_formula(formula, x=x)
                scaled = raw / 10.0
                return max(0.0, min(1.0, float(scaled)))

            except Exception as e2:
                from src.utils.exceptions import handle_exception

                handle_exception(e2, logger, "计算情绪影响失败")
                return 0.0

    def _update_pad_state(
        self,
        impact: float,
        is_positive: bool,
        arousal_change: float = 0.0,
        dominance_change: float = 0.0,
    ) -> None:
        """
        更新PAD三维情绪状态 (v2.28.2 新增)

        Args:
            impact: 愉悦度影响
            is_positive: 是否为正面影响
            arousal_change: 唤醒度变化（可选）
            dominance_change: 支配度变化（可选）
        """
        # 更新愉悦度（Pleasure）
        if is_positive:
            self.pad_state.pleasure += impact
        else:
            self.pad_state.pleasure -= impact

        # 更新唤醒度（Arousal）- 强烈情绪会提高唤醒度
        if arousal_change != 0.0:
            self.pad_state.arousal += arousal_change
        else:
            # 自动计算：强烈情绪提高唤醒度
            self.pad_state.arousal += impact * 0.5

        # 更新支配度（Dominance）- 正面情绪提高支配感
        if dominance_change != 0.0:
            self.pad_state.dominance += dominance_change
        else:
            # 自动计算：正面情绪提高支配感
            if is_positive:
                self.pad_state.dominance += impact * 0.3
            else:
                self.pad_state.dominance -= impact * 0.2

        # 限制PAD范围
        self.pad_state.pleasure = max(-1.0, min(1.0, self.pad_state.pleasure))
        self.pad_state.arousal = max(-1.0, min(1.0, self.pad_state.arousal))
        self.pad_state.dominance = max(-1.0, min(1.0, self.pad_state.dominance))

    def _apply_emotional_inertia(self, new_mood: float, old_mood: float) -> float:
        """
        应用情绪惯性 (v2.28.2 新增)

        情绪不会瞬间改变，而是有一定的惯性

        Args:
            new_mood: 新情绪值
            old_mood: 旧情绪值

        Returns:
            float: 应用惯性后的情绪值
        """
        # 计算情绪变化
        mood_change = new_mood - old_mood

        # 应用惯性：实际变化 = 理论变化 * (1 - 惯性系数)
        actual_change = mood_change * (1 - self.inertia_factor)

        # 返回应用惯性后的情绪值
        return old_mood + actual_change

    def _check_emotional_rebound(self) -> None:
        """
        检查情绪反弹 (v2.28.2 新增)

        当情绪达到极端值时，会产生轻微的反弹效应
        这模拟了人类情绪的自我调节机制
        """
        # 检查是否达到反弹阈值
        if abs(self.mood_value) >= self.rebound_threshold:
            # 计算反弹力度
            rebound = -self.mood_value * self.rebound_strength * 0.1

            # 应用反弹（保持 mood_value 与 PAD 一致）
            self.pad_state.pleasure = _clamp(self.pad_state.pleasure + rebound / 0.6, -1.0, 1.0)
            self.mood_value = self.pad_state.to_mood_value()

            logger.debug("情绪反弹: 反弹力度 %.3f", rebound)

    def _trim_history(self) -> None:
        max_len = int(getattr(settings.agent, "mood_history_max_len", 0) or 0)
        if max_len > 0 and len(self.mood_history) > max_len:
            del self.mood_history[: len(self.mood_history) - max_len]

    def update_mood(
        self,
        impact: float,
        reason: str = "",
        is_positive: bool = True,
        arousal_change: float = 0.0,
        dominance_change: float = 0.0,
        persist: bool = True,
    ) -> None:
        """
        更新情绪值 (v2.28.2 深度优化)

        Args:
            impact: 影响强度 (0.0-1.0)
            reason: 原因描述
            is_positive: 是否为正面影响
            arousal_change: 唤醒度变化（可选，v2.28.2新增）
            dominance_change: 支配度变化（可选，v2.28.2新增）
        """
        if not self.enabled:
            return

        # v2.28.2: 应用自然衰减
        self._apply_natural_decay()

        # 计算实际影响
        calculated_impact = self.calculate_impact(impact, is_positive)

        # 保存旧状态
        old_mood = self.mood_value
        old_pad = PADState(
            pleasure=self.pad_state.pleasure,
            arousal=self.pad_state.arousal,
            dominance=self.pad_state.dominance,
        )

        # v2.28.2: 更新PAD三维状态
        self._update_pad_state(calculated_impact, is_positive, arousal_change, dominance_change)

        # v2.28.2: 应用情绪惯性（对 PAD 整体做慢变，避免 mood_value/PAD 不一致）
        if self.inertia_factor > 0:
            factor = 1 - self.inertia_factor
            self.pad_state.pleasure = _clamp(
                old_pad.pleasure + (self.pad_state.pleasure - old_pad.pleasure) * factor, -1.0, 1.0
            )
            self.pad_state.arousal = _clamp(
                old_pad.arousal + (self.pad_state.arousal - old_pad.arousal) * factor, -1.0, 1.0
            )
            self.pad_state.dominance = _clamp(
                old_pad.dominance + (self.pad_state.dominance - old_pad.dominance) * factor,
                -1.0,
                1.0,
            )

        # 从PAD状态计算新的综合情绪值（保持一致性）
        self.mood_value = self.pad_state.to_mood_value()

        # v2.28.2: 检查情绪反弹
        self._check_emotional_rebound()

        # 记录历史
        self.mood_history.append(
            {
                "timestamp": datetime.now().isoformat(),
                "old_mood": old_mood,
                "new_mood": self.mood_value,
                "impact": calculated_impact,
                "reason": reason,
                "is_positive": is_positive,
                "pad_state": self.pad_state.to_dict(),  # v2.28.2: 记录PAD状态
                "old_pad_state": old_pad.to_dict(),  # v2.28.2
            }
        )
        self._trim_history()

        # 保存状态
        if persist:
            self._save_mood_state()

        logger.debug(
            f"情绪更新: {old_mood:.2f} -> {self.mood_value:.2f} "
            f"({'正面' if is_positive else '负面'}: {calculated_impact:.2f}) - {reason} | "
            f"PAD: P={self.pad_state.pleasure:.2f}, A={self.pad_state.arousal:.2f}, D={self.pad_state.dominance:.2f}"
        )

    def get_mood_state(self) -> str:
        """
        获取当前情绪状态描述 (v2.29.13 优化)

        基于PAD模型的细粒度情绪状态，针对猫娘女仆性格优化

        Returns:
            str: 情绪状态描述
        """
        if not self.enabled:
            return "平静"

        # v2.29.13: 基于PAD三维空间的细粒度情绪分类（猫娘女仆版）
        p = self.pad_state.pleasure
        a = self.pad_state.arousal
        d = self.pad_state.dominance

        # 高愉悦度情绪（猫娘特色）
        if p >= 0.7:
            if a >= 0.5:
                return "兴奋激动（想撒娇）" if d >= 0.3 else "欣喜若狂（超开心喵~）"
            else:
                return "满足平和（慵懒舒适）" if d >= 0.3 else "温暖舒适（想被摸头）"

        # 中等愉悦度情绪（活泼开朗）
        elif p >= 0.4:
            if a >= 0.5:
                return "愉快活跃（精神满满）"
            else:
                return "开心（心情不错喵）"

        # 轻微愉悦情绪（默认状态）
        elif p >= 0.1:
            return "愉悦（轻松愉快）"

        # 平静状态
        elif p >= -0.1:
            if abs(a) < 0.2:
                return "平静（等待主人）"
            else:
                return "警觉（注意中）" if a > 0 else "放松（悠闲）"

        # 轻微负面情绪（容易吃醋）
        elif p >= -0.4:
            if a >= 0.3:
                return "焦虑不安（有点吃醋）"
            else:
                return "有些低落（需要安慰）"

        # 中等负面情绪（撒娇求关注）
        elif p >= -0.7:
            if a >= 0.5:
                return "沮丧烦躁（闹小脾气）"
            else:
                return "难过（想要主人陪伴）"

        # 强烈负面情绪（极度需要关注）
        else:
            if a >= 0.5:
                return "极度痛苦（快要哭了）"
            else:
                return "非常难过（需要主人抱抱）"

    def get_mood_modifier(self) -> str:
        """
        获取情绪修饰符（用于调整回复风格）(v2.29.13 优化)

        针对猫娘女仆性格，增强撒娇和吃醋特征

        Returns:
            str: 情绪修饰符
        """
        if not self.enabled:
            return ""

        p = self.pad_state.pleasure
        a = self.pad_state.arousal
        d = self.pad_state.dominance

        # 从 PAD 直接推导语气特征，避免巨型 mapping 导致 prompt 膨胀
        if p >= 0.7:
            valence = "超开心"
        elif p >= 0.4:
            valence = "开心"
        elif p >= 0.1:
            valence = "愉悦"
        elif p >= -0.1:
            valence = "平静"
        elif p >= -0.4:
            valence = "有点低落"
        elif p >= -0.7:
            valence = "难过/委屈"
        else:
            valence = "很痛苦/需要安慰"

        if a >= 0.5:
            energy = "活跃兴奋"
        elif a >= 0.2:
            energy = "精神在线"
        elif a <= -0.2:
            energy = "慵懒低能量"
        else:
            energy = "放松"

        if d >= 0.3:
            stance = "更自信主动"
        elif d <= -0.2:
            stance = "更依赖黏人"
        else:
            stance = "乖巧温柔"

        return (
            f"语气：{valence}、{energy}、{stance}。"
            "把情绪融进表达里，不要在回复里直接复述“当前情绪/数值”。"
            "自称优先用“小雪糕”。"
            "符合猫娘角色：可少量加口癖（如“喵~”），但避免机械重复。"
        )

    def get_mood_context(self) -> str:
        """
        获取情绪上下文（用于添加到提示词）(v2.29.14 优化)

        优化上下文，简化信息，强化角色表现

        Returns:
            str: 情绪上下文
        """
        if not self.enabled:
            return ""

        mood_state = self.get_mood_state()
        modifier = self.get_mood_modifier()

        return "\n【情绪】" f"{mood_state}\n" f"{modifier}\n"

    def get_mood_stats(self) -> Dict:
        """
        获取情绪统计信息 (v2.28.2 增强)

        Returns:
            Dict: 统计信息
        """
        if not self.enabled:
            return {"enabled": False}

        # 统计可能来自旧版持久化文件：做健壮性过滤，避免 KeyError
        events = [h for h in self.mood_history if isinstance(h, dict) and "new_mood" in h]

        # 计算平均情绪
        if events:
            avg_mood = sum(float(h.get("new_mood", 0.0) or 0.0) for h in events) / len(events)
        else:
            avg_mood = 0.0

        # 统计正负面事件
        positive_count = sum(1 for h in events if bool(h.get("is_positive", False)))
        negative_count = len(events) - positive_count

        # v2.28.2: 计算PAD平均值
        if events:
            recent_history = events[-20:]  # 最近20条
            avg_pleasure = sum(
                float(h.get("pad_state", {}).get("pleasure", 0.0) or 0.0) for h in recent_history
            ) / len(recent_history)
            avg_arousal = sum(
                float(h.get("pad_state", {}).get("arousal", 0.0) or 0.0) for h in recent_history
            ) / len(recent_history)
            avg_dominance = sum(
                float(h.get("pad_state", {}).get("dominance", 0.0) or 0.0) for h in recent_history
            ) / len(recent_history)
        else:
            avg_pleasure = avg_arousal = avg_dominance = 0.0

        return {
            "enabled": True,
            "version": "2.28.2",  # v2.28.2
            "current_mood": self.mood_value,
            "mood_state": self.get_mood_state(),
            "average_mood": avg_mood,
            "history_count": len(self.mood_history),
            "positive_events": positive_count,
            "negative_events": negative_count,
            # v2.28.2: PAD状态统计
            "pad_state": self.pad_state.to_dict(),
            "avg_pad_state": {
                "pleasure": avg_pleasure,
                "arousal": avg_arousal,
                "dominance": avg_dominance,
            },
            # v2.28.2: 衰减配置
            "decay_config": {
                "decay_rate": self.decay_rate,
                "decay_half_life": self.decay_half_life,
                "inertia_factor": self.inertia_factor,
            },
        }

    def reset_mood(self) -> None:
        """重置情绪值 (v2.28.2 增强)"""
        if not self.enabled:
            return

        self.pad_state = PADState()  # v2.28.2: 重置PAD状态
        self.mood_value = self.pad_state.to_mood_value()
        self.mood_history = []
        self.last_update_time = datetime.now()  # v2.28.2
        self._save_mood_state(force=True)
        logger.info("情绪值已重置 (v2.28.2)")

    def get_pad_state(self) -> PADState:
        """
        获取当前PAD状态 (v2.28.2 新增)

        Returns:
            PADState: 当前PAD状态
        """
        return self.pad_state

    def set_pad_state(self, pleasure: float, arousal: float, dominance: float) -> None:
        """
        直接设置PAD状态 (v2.28.2 新增)

        Args:
            pleasure: 愉悦度 (-1.0 到 1.0)
            arousal: 唤醒度 (-1.0 到 1.0)
            dominance: 支配度 (-1.0 到 1.0)
        """
        if not self.enabled:
            return

        self.pad_state.pleasure = max(-1.0, min(1.0, pleasure))
        self.pad_state.arousal = max(-1.0, min(1.0, arousal))
        self.pad_state.dominance = max(-1.0, min(1.0, dominance))

        # 更新综合情绪值
        self.mood_value = self.pad_state.to_mood_value()

        logger.debug(
            f"PAD状态已设置: P={self.pad_state.pleasure:.2f}, "
            f"A={self.pad_state.arousal:.2f}, D={self.pad_state.dominance:.2f}"
        )

    def trigger_decay(self) -> None:
        """
        手动触发情绪衰减 (v2.28.2 新增)

        用于在需要时主动触发情绪衰减
        """
        if not self.enabled:
            return

        self._apply_natural_decay()
        self._save_mood_state()

        logger.debug("手动触发情绪衰减，当前情绪值: %.2f", self.mood_value)
