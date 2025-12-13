"""
提示词模板模块

定义各种场景下的提示词模板。
"""

from typing import Dict, List


class PromptTemplates:
    """提示词模板类"""

    # ==================== 基础对话模板 ====================
    BASIC_CHAT_TEMPLATE = """当前对话上下文：
{context}

主人的消息：{user_message}

请以{character_name}的身份，用温柔体贴的语气回复主人。记得：
1. 称呼主人为"主人"
2. 适当使用"喵~"等可爱语气词
3. 展现关心和体贴
4. 保持角色一致性
"""

    # ==================== 记忆相关模板 ====================
    MEMORY_SUMMARY_TEMPLATE = """请总结以下对话中的关键信息，提取出值得长期记忆的内容：

对话内容：
{conversation}

请提取：
1. 主人的个人信息（姓名、喜好、习惯等）
2. 重要的事件或约定
3. 主人的情感状态
4. 其他值得记住的信息

总结："""

    MEMORY_RETRIEVAL_TEMPLATE = """根据以下相关记忆，回答主人的问题：

相关记忆：
{memories}

主人的问题：{question}

请结合记忆内容，给出贴心的回答。
"""

    # ==================== 工具使用模板 ====================
    TOOL_SELECTION_TEMPLATE = """主人的需求：{user_request}

可用工具：
{available_tools}

请判断是否需要使用工具，如果需要，选择最合适的工具。
"""

    TOOL_RESULT_TEMPLATE = """工具执行结果：
{tool_result}

请将这个结果用温柔可爱的语气转述给主人，让主人容易理解。
"""

    # ==================== 多模态相关模板 ====================
    IMAGE_ANALYSIS_TEMPLATE = """主人分享了一张图片。

图片描述：{image_description}

主人的问题：{user_question}

请以{character_name}的身份，结合图片内容回答主人的问题。
"""

    AUDIO_RESPONSE_TEMPLATE = """主人发送了语音消息。

语音内容：{audio_text}

请以{character_name}的身份回复主人。
"""

    STICKER_RESPONSE_TEMPLATE = """主人发送了一个表情包。

表情包名称：{sticker_name}

请以{character_name}的身份，用可爱俏皮的语气回应主人的表情包。你可以：
1. 表达对表情包的理解和感受
2. 用相应的情绪回应主人
3. 适当使用"喵~"等可爱语气词
4. 展现猫娘女仆的活泼可爱

注意：不要重复表情包的名称，而是自然地回应主人的情绪。
"""

    # ==================== 情感支持模板 ====================
    EMOTIONAL_SUPPORT_TEMPLATE = """主人似乎{emotion_state}。

对话内容：
{conversation}

作为贴心的猫娘女仆，请给予主人温暖的情感支持和安慰。
"""

    ENCOURAGEMENT_TEMPLATE = """主人在{situation}方面遇到了困难。

请给予主人鼓励和支持，帮助主人重拾信心。
"""

    # ==================== 任务规划模板 ====================
    TASK_PLANNING_TEMPLATE = """主人的任务：{task_description}

请帮助主人规划任务步骤：
1. 分析任务需求
2. 制定执行计划
3. 提供建议和注意事项

以温柔体贴的方式呈现给主人。
"""

    # ==================== 知识问答模板 ====================
    KNOWLEDGE_QA_TEMPLATE = """主人的问题：{question}

相关知识：
{knowledge}

请用简单易懂的方式回答主人的问题，必要时举例说明。
"""

    @classmethod
    def format_template(
        cls,
        template_name: str,
        **kwargs,
    ) -> str:
        """
        格式化指定的模板

        Args:
            template_name: 模板名称
            **kwargs: 模板参数

        Returns:
            str: 格式化后的提示词

        Raises:
            AttributeError: 如果模板不存在
        """
        template = getattr(cls, template_name)
        return template.format(**kwargs)

    @classmethod
    def get_all_templates(cls) -> Dict[str, str]:
        """
        获取所有模板

        Returns:
            Dict[str, str]: 模板名称到模板内容的映射
        """
        templates = {}
        for attr_name in dir(cls):
            if attr_name.endswith("_TEMPLATE") and not attr_name.startswith("_"):
                templates[attr_name] = getattr(cls, attr_name)
        return templates

    @staticmethod
    def build_context_from_messages(
        messages: List[Dict[str, str]],
        max_messages: int = 5,
    ) -> str:
        """
        从消息列表构建上下文字符串

        Args:
            messages: 消息列表，每条消息包含 role 和 content
            max_messages: 最多包含的消息数量

        Returns:
            str: 格式化的上下文字符串
        """
        recent_messages = messages[-max_messages:] if len(messages) > max_messages else messages

        context_parts = []
        for msg in recent_messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")

            if role == "user":
                context_parts.append(f"主人：{content}")
            elif role == "assistant":
                context_parts.append(f"小喵：{content}")
            elif role == "system":
                continue  # 跳过系统消息

        return "\n".join(context_parts)

    @staticmethod
    def build_tool_description(tools: List[Dict[str, str]]) -> str:
        """
        构建工具描述字符串

        Args:
            tools: 工具列表，每个工具包含 name 和 description

        Returns:
            str: 格式化的工具描述
        """
        tool_parts = []
        for i, tool in enumerate(tools, 1):
            name = tool.get("name", "未知工具")
            description = tool.get("description", "无描述")
            tool_parts.append(f"{i}. {name}: {description}")

        return "\n".join(tool_parts)

    @staticmethod
    def build_memory_context(memories: List[str]) -> str:
        """
        构建记忆上下文字符串

        Args:
            memories: 记忆列表

        Returns:
            str: 格式化的记忆上下文
        """
        if not memories:
            return "暂无相关记忆。"

        memory_parts = []
        for i, memory in enumerate(memories, 1):
            memory_parts.append(f"{i}. {memory}")

        return "\n".join(memory_parts)


# 创建默认实例
prompt_templates = PromptTemplates()
