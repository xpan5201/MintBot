"""
完整多模态功能演示

展示 MintChat v2.1 的所有多模态功能：
- 图像理解
- OCR 文字提取
- 语音识别
- 语音合成
- 对话导出
- 智能缓存
"""

import os
import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.multimodal.vision import vision_processor
from src.multimodal.audio import audio_processor
from src.utils.export import exporter
from src.utils.cache import response_cache
from src.utils.logger import get_logger

logger = get_logger(__name__)


def demo_image_analysis():
    """演示图像分析功能"""
    print("\n" + "=" * 60)
    print("📸 图像分析演示")
    print("=" * 60)

    # 注意：需要支持视觉的 LLM（如 GPT-4V）
    try:
        from langchain_openai import ChatOpenAI

        llm = ChatOpenAI(model="gpt-4-vision-preview")

        # 示例：分析图像
        print("\n1. 分析图像内容")
        print("-" * 60)

        # 这里需要替换为实际的图像路径
        image_path = "path/to/your/image.jpg"

        if Path(image_path).exists():
            result = vision_processor.analyze_image(
                image_path, prompt="请详细描述这张图片的内容", llm=llm
            )
            print(f"分析结果: {result}")
        else:
            print(f"⚠️  图像文件不存在: {image_path}")
            print("提示：请替换为实际的图像路径")

    except ImportError:
        print("⚠️  需要安装依赖 langchain-openai，请先执行: uv sync --locked --no-install-project")
    except Exception as e:
        print(f"❌ 图像分析失败: {e}")


def demo_ocr():
    """演示 OCR 功能"""
    print("\n" + "=" * 60)
    print("📝 OCR 文字提取演示")
    print("=" * 60)

    try:
        from langchain_openai import ChatOpenAI

        llm = ChatOpenAI(model="gpt-4-vision-preview")

        print("\n1. 从图片中提取文字")
        print("-" * 60)

        # 这里需要替换为包含文字的图像路径
        image_path = "path/to/document.jpg"

        if Path(image_path).exists():
            text = vision_processor.extract_text_from_image(image_path, llm=llm)
            print(f"提取的文字:\n{text}")
        else:
            print(f"⚠️  图像文件不存在: {image_path}")
            print("提示：请替换为实际的图像路径")

    except ImportError:
        print("⚠️  需要安装依赖 langchain-openai，请先执行: uv sync --locked --no-install-project")
    except Exception as e:
        print(f"❌ OCR 失败: {e}")


def demo_speech_to_text():
    """演示语音识别功能"""
    print("\n" + "=" * 60)
    print("🎤 语音识别演示")
    print("=" * 60)

    print("\n1. 语音转文字")
    print("-" * 60)

    # 这里需要替换为实际的音频文件路径
    audio_path = "path/to/audio.mp3"

    if Path(audio_path).exists():
        try:
            text = audio_processor.speech_to_text(audio_path)
            print(f"识别结果: {text}")
        except Exception as e:
            print(f"❌ 语音识别失败: {e}")
    else:
        print(f"⚠️  音频文件不存在: {audio_path}")
        print("提示：请替换为实际的音频文件路径")


def demo_text_to_speech():
    """演示语音合成功能"""
    print("\n" + "=" * 60)
    print("🔊 语音合成演示")
    print("=" * 60)

    print("\n1. 文字转语音")
    print("-" * 60)

    # 猫娘女仆的台词
    texts = [
        "主人，早上好喵~ 今天也要元气满满哦！",
        "主人想吃什么呢？我来给您准备喵~",
        "主人辛苦了，要不要休息一下呢？",
    ]

    # 不同的音色
    voices = ["nova", "shimmer", "alloy"]

    for i, (text, voice) in enumerate(zip(texts, voices), 1):
        try:
            output_path = audio_processor.text_to_speech(
                text,
                output_path=f"data/audio/tts_demo_{i}.mp3",
                voice=voice,
                model="tts-1",  # 使用标准质量模型
            )
            print(f"✅ [{voice}] {text}")
            print(f"   保存到: {output_path}")
        except Exception as e:
            print(f"❌ 语音合成失败: {e}")


def demo_conversation_export():
    """演示对话导出功能"""
    print("\n" + "=" * 60)
    print("📤 对话导出演示")
    print("=" * 60)

    # 模拟对话历史
    conversations = [
        {
            "role": "user",
            "content": "你好，猫娘女仆",
            "timestamp": "2025-11-05 10:00:00",
        },
        {
            "role": "assistant",
            "content": "主人好喵~ 很高兴见到您！有什么需要帮忙的吗？",
            "timestamp": "2025-11-05 10:00:01",
        },
        {
            "role": "user",
            "content": "今天天气怎么样？",
            "timestamp": "2025-11-05 10:01:00",
        },
        {
            "role": "assistant",
            "content": "让我帮您查一下喵~ 今天天气晴朗，温度适宜，很适合出门哦！",
            "timestamp": "2025-11-05 10:01:05",
        },
        {
            "role": "user",
            "content": "谢谢你",
            "timestamp": "2025-11-05 10:02:00",
        },
        {
            "role": "assistant",
            "content": "不客气喵~ 能帮到主人我很开心！",
            "timestamp": "2025-11-05 10:02:01",
        },
    ]

    print("\n1. 导出为不同格式")
    print("-" * 60)

    try:
        # 导出为 JSON
        json_path = exporter.export_to_json(conversations, "demo_chat.json")
        print(f"✅ JSON 格式: {json_path}")

        # 导出为 Markdown
        md_path = exporter.export_to_markdown(
            conversations, "demo_chat.md", title="猫娘女仆对话记录"
        )
        print(f"✅ Markdown 格式: {md_path}")

        # 导出为 TXT
        txt_path = exporter.export_to_txt(conversations, "demo_chat.txt")
        print(f"✅ TXT 格式: {txt_path}")

        # 导出为 HTML
        html_path = exporter.export_to_html(
            conversations, "demo_chat.html", title="猫娘女仆对话记录"
        )
        print(f"✅ HTML 格式: {html_path}")

    except Exception as e:
        print(f"❌ 导出失败: {e}")


def demo_cache_system():
    """演示缓存系统"""
    print("\n" + "=" * 60)
    print("💾 智能缓存演示")
    print("=" * 60)

    print("\n1. 响应缓存")
    print("-" * 60)

    # 模拟对话
    message = "今天天气怎么样？"
    response = "今天天气晴朗，温度 20°C，适合出门喵~"

    # 设置缓存
    response_cache.set(message, response)
    print(f"✅ 已缓存: {message}")

    # 获取缓存
    cached_response = response_cache.get(message)
    if cached_response:
        print(f"✅ 缓存命中: {cached_response}")
    else:
        print("❌ 缓存未命中")

    # 获取统计信息
    print("\n2. 缓存统计")
    print("-" * 60)
    stats = response_cache.get_stats()
    print(f"总条目数: {stats['total_entries']}")
    print(f"总命中数: {stats['total_hits']}")
    print(f"过期条目: {stats['expired_entries']}")
    print(f"最大容量: {stats['max_size']}")
    print(f"TTL: {stats['ttl']} 秒")


def main():
    """主函数"""
    print("\n" + "=" * 60)
    print("🎨 MintChat v2.1 完整多模态功能演示")
    print("=" * 60)
    print("\n本演示展示以下功能：")
    print("1. 图像理解（需要 GPT-4V 或 Claude 3）")
    print("2. OCR 文字提取")
    print("3. 语音识别（需要 OpenAI API Key）")
    print("4. 语音合成（需要 OpenAI API Key）")
    print("5. 对话导出（JSON、Markdown、TXT、HTML）")
    print("6. 智能缓存系统")

    # 检查环境变量
    if not os.getenv("OPENAI_API_KEY"):
        print("\n⚠️  警告: 未设置 OPENAI_API_KEY 环境变量")
        print("部分功能（语音识别、语音合成、图像理解）需要 API Key")

    # 运行各个演示
    try:
        # demo_image_analysis()  # 需要图像文件
        # demo_ocr()  # 需要图像文件
        # demo_speech_to_text()  # 需要音频文件
        demo_text_to_speech()  # 可以直接运行
        demo_conversation_export()  # 可以直接运行
        demo_cache_system()  # 可以直接运行

    except KeyboardInterrupt:
        print("\n\n👋 演示已中断")
    except Exception as e:
        logger.error(f"演示出错: {e}")
        raise

    print("\n" + "=" * 60)
    print("✅ 演示完成！")
    print("=" * 60)
    print("\n提示：")
    print("- 要使用图像和语音功能，请设置 OPENAI_API_KEY")
    print("- 要使用图像理解，需要 GPT-4V 或 Claude 3 模型")
    print("- 导出的文件保存在 data/exports/ 目录")
    print("- 语音文件保存在 data/audio/ 目录")


if __name__ == "__main__":
    main()
