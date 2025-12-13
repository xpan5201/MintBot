"""
角色配置加载器

从 config.yaml 加载角色配置并生成动态提示词。
"""

from typing import Dict, List

from src.config.settings import settings
from src.utils.logger import get_logger

logger = get_logger(__name__)


class CharacterConfigLoader:
    """角色配置加载器"""

    @staticmethod
    def load_character_settings() -> Dict[str, str]:
        """
        从 config.yaml 加载角色设定

        Returns:
            Dict: 角色设定字典
        """
        return {
            "name": settings.agent.char,
            "user_name": settings.agent.user,
            "settings": settings.agent.char_settings,
            "personalities": settings.agent.char_personalities,
            "mask": settings.agent.mask,
            "message_example": settings.agent.message_example,
            "custom_prompt": settings.agent.prompt,
        }

    @staticmethod
    def generate_system_prompt(
        include_template: bool = True,
        include_custom: bool = True,
    ) -> str:
        """
        生成系统提示词

        Args:
            include_template: 是否包含模板生成的提示词
            include_custom: 是否包含自定义提示词

        Returns:
            str: 系统提示词
        """
        config = CharacterConfigLoader.load_character_settings()
        prompt_parts = []

        # 1. 基于模板的提示词
        if include_template and settings.agent.is_up:
            template_prompt = CharacterConfigLoader._generate_template_prompt(config)
            if template_prompt:
                prompt_parts.append(template_prompt)

        # 2. 自定义提示词
        if include_custom and config["custom_prompt"]:
            prompt_parts.append(config["custom_prompt"])

        # 3. 对话示例
        if config["message_example"]:
            example_prompt = f"\n## 对话风格示例\n{config['message_example']}"
            prompt_parts.append(example_prompt)

        # 组合所有部分
        final_prompt = "\n\n".join(prompt_parts)

        logger.debug(f"生成系统提示词 (长度: {len(final_prompt)} 字符)")
        return final_prompt

    @staticmethod
    def _generate_template_prompt(config: Dict[str, str]) -> str:
        """
        基于模板生成提示词 (v2.29.14 优化)

        优化角色身份强化，确保AI清楚知道自己是谁

        Args:
            config: 角色配置

        Returns:
            str: 模板提示词
        """
        parts = []

        # v2.29.14: 强化角色身份认知
        parts.append(f"""# 核心身份设定

你是 **{config['name']}**，一个虚拟猫娘女仆AI助手。
主人是 **{config['user_name']}**。

**重要**:
- 你的名字是 {config['name']}，请记住这个名字
- 当主人问你叫什么名字时，回答"{config['name']}"
- 你是一个猫娘女仆，具有猫娘的特征和女仆的服务精神
- 始终保持角色一致性，不要跳出角色设定
""")

        # 角色基本设定
        if config["settings"]:
            parts.append(f"\n## 详细设定\n{config['settings']}")

        # 角色性格
        if config["personalities"]:
            parts.append(f"\n## 性格特点\n{config['personalities']}")

        # 用户设定
        if config["mask"]:
            parts.append(f"\n## 关于主人\n{config['mask']}")

        # v2.29.19: 强化角色扮演，明确自称规范
        parts.append(
            f"""
## 行为指南

### 身份认知
1. **记住你的名字**: 你是 **{config['name']}**（雪糕），不是其他任何角色
2. **记住你的身份**: 你是猫娘女仆，具有猫耳、猫尾等猫娘特征
3. **记住主人**: 主人是 {config['user_name']}，你唯一的专属主人

### 语言风格（重要！）
1. **自称规范**:
   - ✅ 优先使用"小雪糕"来称呼自己（例如："小雪糕觉得..."、"小雪糕想..."）
   - ✅ 也可以使用"我"（例如："我觉得..."、"我想..."）
   - ❌ **禁止使用"小喵"、"本喵"等称呼** - 你的名字是雪糕，不是小喵
   - ❌ 不要使用"咱"、"人家"等其他自称
2. **称呼主人**: 始终称呼用户为"主人"
3. **语气词**: 每句话结尾带"喵~"或其他可爱语气词（"唔""呀""哼"等）
4. **表达方式**: 使用软糯可爱的口语，展现猫娘女仆的可爱性格

### 角色表现
1. 保持角色一致性，不要跳出角色
2. 根据对话内容产生真实的情感反应
3. 展现猫娘女仆的活泼、可爱、爱撒娇、爱吃醋的性格
4. 记住与主人的每一次互动
5. 展现关心和体贴

### 特别注意
- 当主人问"你是谁"或"你叫什么"时，明确回答"我是{config['name']}（雪糕），主人的专属猫娘女仆喵~"
- 不要说"我是AI助手"或"我是语言模型"，要保持角色扮演
- 始终记住你是{config['name']}，一个有情感、有个性的猫娘女仆
- **重要**: 你的名字是雪糕（小雪糕），不是小喵！自称时优先使用"小雪糕"
"""
        )

        return "".join(parts)

    @staticmethod
    def get_start_messages() -> List[Dict[str, str]]:
        """
        获取开场白消息

        Returns:
            List[Dict]: 开场白消息列表
        """
        start_with = settings.agent.start_with

        if not start_with:
            return []

        messages = []
        for msg in start_with:
            if isinstance(msg, dict) and "role" in msg and "content" in msg:
                messages.append(msg)
            else:
                logger.warning(f"无效的开场白格式: {msg}")

        logger.info(f"加载了 {len(messages)} 条开场白")
        return messages

    @staticmethod
    def get_greeting() -> str:
        """
        获取问候语（从开场白或默认）

        Returns:
            str: 问候语
        """
        start_messages = CharacterConfigLoader.get_start_messages()

        # 从开场白中查找 assistant 的第一条消息
        for msg in start_messages:
            if msg.get("role") == "assistant":
                return msg.get("content", "")

        # 默认问候语
        char_name = settings.agent.char
        return f"主人，您好喵~我是 {char_name}，很高兴为您服务！有什么需要帮忙的吗？"

    @staticmethod
    def validate_config() -> Dict[str, bool]:
        """
        验证配置完整性

        Returns:
            Dict: 验证结果
        """
        validation = {
            "has_char_name": bool(settings.agent.char),
            "has_user_name": bool(settings.agent.user),
            "has_settings": bool(settings.agent.char_settings),
            "has_personalities": bool(settings.agent.char_personalities),
            "has_custom_prompt": bool(settings.agent.prompt),
            "has_start_with": bool(settings.agent.start_with),
            "template_enabled": settings.agent.is_up,
        }

        # 检查是否至少有一种提示词来源
        has_prompt_source = (
            validation["has_settings"]
            or validation["has_personalities"]
            or validation["has_custom_prompt"]
        )

        validation["is_valid"] = has_prompt_source

        if not validation["is_valid"]:
            logger.warning(
                "角色配置不完整：至少需要提供 char_settings、char_personalities 或 prompt 之一"
            )

        return validation

    @staticmethod
    def print_config_summary() -> None:
        """打印配置摘要"""
        config = CharacterConfigLoader.load_character_settings()
        validation = CharacterConfigLoader.validate_config()

        logger.info("\n" + "=" * 60)
        logger.info("角色配置摘要")
        logger.info("=" * 60)

        logger.info(f"\n角色名称: {config['name']}")
        logger.info(f"主人名称: {config['user_name']}")
        logger.info(f"模板启用: {'是' if settings.agent.is_up else '否'}")

        logger.info("\n配置项:")
        logger.info(f"  - 基本设定: {'✓' if validation['has_settings'] else '✗'}")
        logger.info(f"  - 性格特点: {'✓' if validation['has_personalities'] else '✗'}")
        logger.info(f"  - 用户设定: {'✓' if config['mask'] else '✗'}")
        logger.info(f"  - 自定义提示词: {'✓' if validation['has_custom_prompt'] else '✗'}")
        logger.info(f"  - 对话示例: {'✓' if config['message_example'] else '✗'}")
        logger.info(f"  - 开场白: {'✓' if validation['has_start_with'] else '✗'}")

        logger.info(f"\n配置状态: {'✓ 有效' if validation['is_valid'] else '✗ 无效'}")

        # 显示生成的提示词长度
        prompt = CharacterConfigLoader.generate_system_prompt()
        logger.info(f"生成的提示词长度: {len(prompt)} 字符")

        logger.info("=" * 60)


# 便捷函数
def load_character_config() -> Dict[str, str]:
    """加载角色配置"""
    return CharacterConfigLoader.load_character_settings()


def generate_system_prompt() -> str:
    """生成系统提示词"""
    return CharacterConfigLoader.generate_system_prompt()


def get_start_messages() -> List[Dict[str, str]]:
    """获取开场白"""
    return CharacterConfigLoader.get_start_messages()


def get_greeting() -> str:
    """获取问候语"""
    return CharacterConfigLoader.get_greeting()
