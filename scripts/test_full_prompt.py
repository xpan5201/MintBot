"""
测试完整提示词系统

测试Agent创建时的完整提示词，包括系统提示词和情绪上下文
"""

from src.agent.core import MintChatAgent
from src.agent.emotion import EmotionEngine
from src.agent.mood_system import MoodSystem

def test_full_prompt():
    """测试完整提示词"""
    print("=" * 60)
    print("测试完整提示词系统")
    print("=" * 60)
    
    # 创建Agent（不实际连接LLM）
    print("\n正在初始化Agent...")
    
    # 测试情绪引擎上下文
    print("\n" + "=" * 60)
    print("测试情绪引擎上下文")
    print("=" * 60)
    
    emotion_engine = EmotionEngine()
    emotion_context = emotion_engine.get_emotion_context()
    print(emotion_context)
    
    # 测试情绪系统上下文
    print("\n" + "=" * 60)
    print("测试情绪系统上下文")
    print("=" * 60)
    
    mood_system = MoodSystem()
    mood_context = mood_system.get_mood_context()
    print(mood_context)
    
    # 检查关键信息
    print("\n" + "=" * 60)
    print("关键信息检查")
    print("=" * 60)
    
    checks = {
        "情绪上下文包含角色名": "小雪糕" in emotion_context,
        "情绪上下文包含角色身份": "猫娘女仆" in emotion_context,
        "情绪系统包含情绪状态": "情绪状态" in mood_context or "当前情绪" in mood_context,
        "情绪系统包含角色提醒": "猫娘女仆" in mood_context or "角色" in mood_context,
    }
    
    for check_name, result in checks.items():
        status = "✅" if result else "❌"
        print(f"  {status} {check_name}: {result}")
    
    # 总结
    print("\n" + "=" * 60)
    print("测试总结")
    print("=" * 60)
    
    if all(checks.values()):
        print("✅ 所有检查通过！提示词系统完整且包含角色身份信息。")
    else:
        print("❌ 部分检查失败！提示词系统可能缺少角色身份信息。")
    
    return all(checks.values())

if __name__ == "__main__":
    test_full_prompt()

