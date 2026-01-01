"""
基础对话示例

演示如何使用 MintChat 进行基本对话。
"""

import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.agent.core import MintChatAgent  # noqa: E402
from src.config.settings import settings  # noqa: E402
from src.utils.logger import get_logger  # noqa: E402

logger = get_logger(__name__)


def main():
    """主函数"""
    print("=" * 60)
    print("MintChat - 多模态猫娘女仆智能体")
    print("=" * 60)
    print()

    # 检查 API Key 配置
    try:
        settings.get_llm_api_key()
    except ValueError as e:
        print(f"错误: {e}")
        print("请在 .env 文件中配置相应的 API Key")
        return

    # 创建智能体
    print("正在初始化智能体...")
    try:
        agent = MintChatAgent()
        print("✓ 智能体初始化成功")
        print()
    except Exception as e:
        print(f"✗ 智能体初始化失败: {e}")
        logger.error(f"智能体初始化失败: {e}")
        return

    # 显示问候语
    greeting = agent.get_greeting()
    print(f"{agent.character.name}: {greeting}")
    print()

    # 显示统计信息
    stats = agent.get_stats()
    print("智能体信息:")
    print(f"  - 角色名称: {stats['character_name']}")
    print(f"  - 使用模型: {stats['model_name']}")
    print(f"  - 流式输出: {'启用' if stats['streaming_enabled'] else '禁用'}")
    print(f"  - 可用工具: {', '.join(stats['tool_names'])}")
    print(f"  - 长期记忆: {'启用' if stats['long_term_memory_enabled'] else '禁用'}")
    print()

    # 对话循环
    print(
        "开始对话（输入 'quit' 或 'exit' 退出，'clear' 清空记忆，'stats' 查看统计，'emotion' 查看情感）"
    )
    print("-" * 60)
    print()

    while True:
        try:
            # 获取用户输入
            user_input = input("主人: ").strip()

            if not user_input:
                continue

            # 处理特殊命令
            if user_input.lower() in ["quit", "exit", "退出"]:
                farewell = agent.get_farewell()
                print(f"\n{agent.character.name}: {farewell}")
                break

            if user_input.lower() in ["clear", "清空"]:
                agent.clear_memory()
                print(f"\n{agent.character.name}: 记忆已清空喵~")
                print()
                continue

            if user_input.lower() in ["stats", "统计"]:
                stats = agent.get_stats()
                print("\n对话统计:")
                print(f"  - 最近消息数: {stats['recent_messages_count']}")
                emotion_stats = stats["emotion_stats"]
                print(f"  - 当前情感: {emotion_stats['current_emotion']}")
                print(f"  - 亲密度: {emotion_stats['relationship_level']:.2f}")
                print(f"  - 正面互动: {emotion_stats['positive_interactions']}")
                print()
                continue

            if user_input.lower() in ["emotion", "情感"]:
                emotion_status = agent.get_emotion_status()
                print(f"\n{emotion_status}")
                print()
                continue

            # 生成回复（使用流式输出以获得更好体验）
            if stats.get("streaming_enabled", False):
                print(f"\n{agent.character.name}: ", end="", flush=True)
                for chunk in agent.chat_stream(user_input, save_to_long_term=True):
                    print(chunk, end="", flush=True)
                print()  # 换行
            else:
                response = agent.chat(user_input, save_to_long_term=True)
                print(f"\n{agent.character.name}: {response}")
            print()

        except KeyboardInterrupt:
            print("\n")
            farewell = agent.get_farewell()
            print(f"{agent.character.name}: {farewell}")
            break

        except Exception as e:
            print(f"\n错误: {e}")
            logger.error(f"对话处理错误: {e}")
            print()


if __name__ == "__main__":
    main()
