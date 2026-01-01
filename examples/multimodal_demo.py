"""
多模态交互示例

演示如何使用 MintChat 进行多模态交互（图像、音频等）。
"""

import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.multimodal.audio import audio_processor  # noqa: E402
from src.multimodal.vision import vision_processor  # noqa: E402
from src.utils.logger import get_logger  # noqa: E402

logger = get_logger(__name__)


def demo_vision():
    """演示视觉处理功能"""
    print("\n" + "=" * 60)
    print("视觉处理演示")
    print("=" * 60)

    # 创建测试图像（如果不存在）
    test_image_path = Path("examples/test_image.jpg")

    if not test_image_path.exists():
        print(f"\n提示: 请将测试图像放置在 {test_image_path}")
        print("跳过视觉处理演示...")
        return

    try:
        # 获取图像信息
        print("\n1. 获取图像信息:")
        info = vision_processor.get_image_info(test_image_path)
        print(f"   - 路径: {info['path']}")
        print(f"   - 尺寸: {info['width']}x{info['height']}")
        print(f"   - 格式: {info['format']}")

        # 分析图像
        print("\n2. 分析图像内容:")
        analysis = vision_processor.analyze_image(test_image_path)
        print(f"   {analysis}")

    except Exception as e:
        print(f"\n错误: {e}")
        logger.error(f"视觉处理演示失败: {e}")


def demo_audio():
    """演示音频处理功能"""
    print("\n" + "=" * 60)
    print("音频处理演示")
    print("=" * 60)

    # 创建测试音频（如果不存在）
    test_audio_path = Path("examples/test_audio.mp3")

    if not test_audio_path.exists():
        print(f"\n提示: 请将测试音频放置在 {test_audio_path}")
        print("跳过音频处理演示...")
        return

    try:
        # 获取音频信息
        print("\n1. 获取音频信息:")
        info = audio_processor.get_audio_info(test_audio_path)
        print(f"   - 路径: {info['path']}")
        print(f"   - 大小: {info['size']} 字节")
        print(f"   - 格式: {info['format']}")

        # 语音识别
        print("\n2. 语音识别:")
        text = audio_processor.speech_to_text(test_audio_path)
        print(f"   {text}")

    except Exception as e:
        print(f"\n错误: {e}")
        logger.error(f"音频处理演示失败: {e}")


def demo_tts():
    """演示文字转语音功能"""
    print("\n" + "=" * 60)
    print("文字转语音演示")
    print("=" * 60)

    text = "主人，欢迎回来~我是小喵，您的专属猫娘女仆喵~"

    try:
        print(f"\n要转换的文字: {text}")
        output_path = audio_processor.text_to_speech(text)
        print(f"输出路径: {output_path}")
        print("（注意: TTS 功能尚未完全实现）")

    except Exception as e:
        print(f"\n错误: {e}")
        logger.error(f"TTS 演示失败: {e}")


def demo_multimodal_chat():
    """演示多模态对话"""
    print("\n" + "=" * 60)
    print("多模态对话演示")
    print("=" * 60)

    print("\n提示: 多模态对话功能需要支持视觉的 LLM（如 GPT-4V）")
    print("当前版本的基础实现尚不支持完整的多模态对话")
    print("该功能将在后续版本中完善")


def main():
    """主函数"""
    print("=" * 60)
    print("MintChat - 多模态功能演示")
    print("=" * 60)

    # 演示各项功能
    demo_vision()
    demo_audio()
    demo_tts()
    demo_multimodal_chat()

    print("\n" + "=" * 60)
    print("演示完成")
    print("=" * 60)


if __name__ == "__main__":
    main()
