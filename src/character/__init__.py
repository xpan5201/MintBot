"""
角色系统模块

定义猫娘女仆的性格、提示词等角色特性。
"""

from .personality import CharacterPersonality
from .prompts import PromptTemplates

__all__ = ["CharacterPersonality", "PromptTemplates"]
