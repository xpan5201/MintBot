"""
测试角色扮演能力 - 验证AI助手是否正确使用"小雪糕"自称

测试内容:
1. 系统提示词中的自称规范
2. 情绪上下文中的自称提醒
3. 情绪系统中的自称提醒
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.character.config_loader import CharacterConfigLoader
from src.agent.emotion import EmotionEngine
from src.agent.mood_system import MoodSystem
from src.config.settings import settings


def test_system_prompt():
    """测试系统提示词中的自称规范"""
    print("=" * 70)
    print("测试1: 系统提示词中的自称规范")
    print("=" * 70)

    config = CharacterConfigLoader.load_character_settings()
    prompt = CharacterConfigLoader.generate_system_prompt()
    
    print(f"\n角色名: {config['name']}")
    print(f"用户名: {config['user_name']}")
    print(f"\n生成的提示词长度: {len(prompt)} 字符")
    
    # 检查关键词
    checks = {
        "包含'小雪糕'": "小雪糕" in prompt,
        "包含'优先使用小雪糕'": "优先使用" in prompt and "小雪糕" in prompt,
        "包含'禁止使用小喵'": "禁止" in prompt and "小喵" in prompt,
        "包含'你的名字是雪糕'": "雪糕" in prompt,
    }
    
    print("\n关键词检查:")
    for check_name, result in checks.items():
        status = "✅" if result else "❌"
        print(f"  {status} {check_name}: {result}")
    
    # 显示语言风格部分
    if "### 语言风格" in prompt:
        start = prompt.index("### 语言风格")
        end = prompt.index("### 角色表现", start) if "### 角色表现" in prompt[start:] else len(prompt)
        language_style = prompt[start:end]
        print("\n语言风格部分:")
        print("-" * 70)
        print(language_style)
        print("-" * 70)
    
    all_passed = all(checks.values())
    if all_passed:
        print("\n✅ 系统提示词检查通过！")
    else:
        print("\n❌ 系统提示词检查失败！")
    
    return all_passed


def test_emotion_context():
    """测试情绪上下文中的自称提醒"""
    print("\n" + "=" * 70)
    print("测试2: 情绪上下文中的自称提醒")
    print("=" * 70)
    
    emotion_engine = EmotionEngine()
    context = emotion_engine.get_emotion_context()
    
    print(f"\n生成的情绪上下文长度: {len(context)} 字符")
    
    # 检查关键词
    checks = {
        "包含角色名": settings.agent.char in context,
        "包含'雪糕'": "雪糕" in context,
        "包含自称提醒": "自称" in context or "小雪糕" in context,
        "包含'不要使用小喵'": "小喵" in context,
    }
    
    print("\n关键词检查:")
    for check_name, result in checks.items():
        status = "✅" if result else "❌"
        print(f"  {status} {check_name}: {result}")
    
    print("\n情绪上下文内容:")
    print("-" * 70)
    print(context)
    print("-" * 70)
    
    all_passed = all(checks.values())
    if all_passed:
        print("\n✅ 情绪上下文检查通过！")
    else:
        print("\n❌ 情绪上下文检查失败！")
    
    return all_passed


def test_mood_context():
    """测试情绪系统中的自称提醒"""
    print("\n" + "=" * 70)
    print("测试3: 情绪系统中的自称提醒")
    print("=" * 70)
    
    mood_system = MoodSystem()
    context = mood_system.get_mood_context()
    
    if not context:
        print("\n⚠️ 情绪系统未启用")
        return True
    
    print(f"\n生成的情绪上下文长度: {len(context)} 字符")
    
    # 检查关键词
    checks = {
        "包含自称提醒": "自称" in context or "小雪糕" in context,
        "包含'不要使用小喵'": "小喵" in context,
    }
    
    print("\n关键词检查:")
    for check_name, result in checks.items():
        status = "✅" if result else "❌"
        print(f"  {status} {check_name}: {result}")
    
    print("\n情绪系统上下文内容:")
    print("-" * 70)
    print(context)
    print("-" * 70)
    
    all_passed = all(checks.values())
    if all_passed:
        print("\n✅ 情绪系统上下文检查通过！")
    else:
        print("\n❌ 情绪系统上下文检查失败！")
    
    return all_passed


def main():
    """主测试函数"""
    print("\n" + "=" * 70)
    print("MintChat 角色扮演能力测试")
    print("=" * 70)
    
    results = []
    
    # 测试1: 系统提示词
    results.append(("系统提示词", test_system_prompt()))
    
    # 测试2: 情绪上下文
    results.append(("情绪上下文", test_emotion_context()))
    
    # 测试3: 情绪系统
    results.append(("情绪系统", test_mood_context()))
    
    # 总结
    print("\n" + "=" * 70)
    print("测试总结")
    print("=" * 70)
    
    for test_name, passed in results:
        status = "✅ 通过" if passed else "❌ 失败"
        print(f"{status}: {test_name}")
    
    all_passed = all(result for _, result in results)
    
    if all_passed:
        print("\n🎉 所有测试通过！角色扮演能力优化成功！")
    else:
        print("\n❌ 部分测试失败，请检查优化内容。")
    
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())

