"""
测试提示词系统

检查配置文件是否正确加载，提示词是否包含角色信息
"""

from src.character.config_loader import CharacterConfigLoader
from src.config.settings import settings

def test_config_loading():
    """测试配置加载"""
    print("=" * 60)
    print("测试配置加载")
    print("=" * 60)
    
    config = CharacterConfigLoader.load_character_settings()
    
    print(f"\n角色名: {config['name']}")
    print(f"用户名: {config['user_name']}")
    print(f"\n基本设定:\n{config['settings']}")
    print(f"\n性格设定:\n{config['personalities']}")
    print(f"\n自定义提示词:\n{config['custom_prompt']}")
    print(f"\n对话示例:\n{config['message_example']}")
    
    return config

def test_prompt_generation():
    """测试提示词生成"""
    print("\n" + "=" * 60)
    print("测试提示词生成")
    print("=" * 60)
    
    prompt = CharacterConfigLoader.generate_system_prompt()
    
    print(f"\n生成的提示词长度: {len(prompt)} 字符")
    print(f"\n完整提示词:\n{'-' * 60}")
    print(prompt)
    print("-" * 60)
    
    # 检查关键信息是否包含
    checks = {
        "角色名 '小雪糕'": "小雪糕" in prompt,
        "用户名 '主人'": "主人" in prompt,
        "猫娘女仆": "猫娘女仆" in prompt or "猫耳" in prompt,
        "性格描述": "温柔" in prompt or "可爱" in prompt or "聪明" in prompt,
        "语气词": "喵" in prompt,
    }
    
    print(f"\n关键信息检查:")
    for check_name, result in checks.items():
        status = "✅" if result else "❌"
        print(f"  {status} {check_name}: {result}")
    
    return prompt, all(checks.values())

def test_settings():
    """测试settings配置"""
    print("\n" + "=" * 60)
    print("测试settings配置")
    print("=" * 60)
    
    print(f"\nis_up (是否使用模板): {settings.agent.is_up}")
    print(f"char (角色名): {settings.agent.char}")
    print(f"user (用户名): {settings.agent.user}")
    print(f"char_settings长度: {len(settings.agent.char_settings)} 字符")
    print(f"char_personalities长度: {len(settings.agent.char_personalities)} 字符")
    print(f"prompt长度: {len(settings.agent.prompt)} 字符")

if __name__ == "__main__":
    # 测试配置加载
    config = test_config_loading()
    
    # 测试settings
    test_settings()
    
    # 测试提示词生成
    prompt, all_passed = test_prompt_generation()
    
    # 总结
    print("\n" + "=" * 60)
    print("测试总结")
    print("=" * 60)
    if all_passed:
        print("✅ 所有检查通过！提示词系统工作正常。")
    else:
        print("❌ 部分检查失败！提示词系统可能存在问题。")

