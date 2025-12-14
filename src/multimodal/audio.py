"""
音频处理模块

处理音频输入输出，支持语音识别和语音合成。
"""

from pathlib import Path
from typing import Optional, Union

from src.utils.logger import get_logger

logger = get_logger(__name__)


class AudioProcessor:
    """音频处理器"""

    # 支持的音频格式
    SUPPORTED_FORMATS = ["mp3", "wav", "ogg", "flac", "m4a", "aac"]

    def __init__(self):
        """初始化音频处理器"""
        self.supported_formats = self.SUPPORTED_FORMATS
        logger.info("音频处理器初始化完成")

    def load_audio(self, audio_path: Union[str, Path]) -> dict:
        """
        加载音频文件

        Args:
            audio_path: 音频文件路径

        Returns:
            dict: 音频信息（包含采样率、时长、通道数等）

        Raises:
            FileNotFoundError: 如果文件不存在
        """
        audio_path = Path(audio_path)

        if not audio_path.exists():
            raise FileNotFoundError(f"音频文件不存在: {audio_path}")

        try:
            # 尝试使用 soundfile（更轻量）
            try:
                import soundfile as sf

                data, samplerate = sf.read(str(audio_path))
                duration = len(data) / samplerate
                channels = 1 if len(data.shape) == 1 else data.shape[1]

                logger.info(f"加载音频: {audio_path} (时长: {duration:.2f}s)")

                return {
                    "path": str(audio_path),
                    "status": "loaded",
                    "samplerate": samplerate,
                    "duration": duration,
                    "channels": channels,
                    "samples": len(data),
                    "format": audio_path.suffix,
                }
            except ImportError:
                # 降级到基本信息
                logger.warning("soundfile 未安装，返回基本信息")
                return {
                    "path": str(audio_path),
                    "status": "loaded",
                    "size": audio_path.stat().st_size,
                    "format": audio_path.suffix,
                }

        except Exception as e:
            logger.error(f"加载音频失败: {e}")
            raise

    def speech_to_text(
        self,
        audio_path: Union[str, Path],
        api_key: Optional[str] = None,
        model: str = "whisper-1",
    ) -> str:
        """
        语音转文字（ASR）- 使用 OpenAI Whisper API

        Args:
            audio_path: 音频文件路径
            api_key: OpenAI API Key（如果未提供，从环境变量读取）
            model: 模型名称，默认 whisper-1

        Returns:
            str: 识别的文字
        """
        try:
            audio_path = Path(audio_path)

            if not audio_path.exists():
                raise FileNotFoundError(f"音频文件不存在: {audio_path}")

            # 尝试使用 OpenAI Whisper API
            try:
                from openai import OpenAI
                import os

                # 获取 API Key
                key = api_key or os.getenv("OPENAI_API_KEY")
                if not key:
                    raise ValueError("未提供 OpenAI API Key")

                client = OpenAI(api_key=key)

                # 调用 Whisper API
                with open(audio_path, "rb") as audio_file:
                    transcript = client.audio.transcriptions.create(
                        model=model,
                        file=audio_file,
                        language="zh",  # 指定中文
                    )

                logger.info(f"语音识别成功: {len(transcript.text)} 个字符")
                return transcript.text

            except ImportError:
                logger.warning("openai 库未安装，请运行: pip install openai")
                return "语音识别需要安装 openai 库"

        except Exception as e:
            logger.error(f"语音识别失败: {e}")
            return f"语音识别失败: {str(e)}"

    def text_to_speech(
        self,
        text: str,
        output_path: Optional[Union[str, Path]] = None,
        voice: str = "alloy",
        model: str = "tts-1",
        api_key: Optional[str] = None,
    ) -> str:
        """
        文字转语音（TTS）- 使用 OpenAI TTS API

        Args:
            text: 要转换的文字
            output_path: 输出音频文件路径
            voice: 语音类型（alloy, echo, fable, onyx, nova, shimmer）
            model: 模型名称（tts-1 或 tts-1-hd）
            api_key: OpenAI API Key（如果未提供，从环境变量读取）

        Returns:
            str: 输出文件路径
        """
        try:
            # 设置输出路径
            if output_path is None:
                output_path = Path("data/audio/tts_output.mp3")

            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)

            # 尝试使用 OpenAI TTS API
            try:
                from openai import OpenAI
                import os

                # 获取 API Key
                key = api_key or os.getenv("OPENAI_API_KEY")
                if not key:
                    raise ValueError("未提供 OpenAI API Key")

                client = OpenAI(api_key=key)

                # 调用 TTS API
                response = client.audio.speech.create(
                    model=model,
                    voice=voice,
                    input=text,
                )

                # 保存音频文件
                response.stream_to_file(output_path)

                logger.info(f"语音合成成功: {text[:50]}... -> {output_path}")
                return str(output_path)

            except ImportError:
                logger.warning("openai 库未安装，请运行: pip install openai")
                return "语音合成需要安装 openai 库"

        except Exception as e:
            logger.error(f"语音合成失败: {e}")
            return f"语音合成失败: {str(e)}"

    def get_audio_info(self, audio_path: Union[str, Path]) -> dict:
        """
        获取音频基本信息

        Args:
            audio_path: 音频文件路径

        Returns:
            dict: 音频信息（采样率、时长、通道数、格式等）

        Raises:
            FileNotFoundError: 如果文件不存在
        """
        audio_path = Path(audio_path)

        if not audio_path.exists():
            raise FileNotFoundError(f"音频文件不存在: {audio_path}")

        # 使用 load_audio 获取详细信息（会抛出异常）
        info = self.load_audio(audio_path)

        logger.debug(f"音频信息: {info}")
        return info

    def convert_audio_format(
        self,
        input_path: Union[str, Path],
        output_path: Union[str, Path],
        output_format: str = "mp3",
    ) -> str:
        """
        转换音频格式

        Args:
            input_path: 输入音频文件路径
            output_path: 输出音频文件路径
            output_format: 输出格式（mp3, wav, ogg, flac 等）

        Returns:
            str: 输出文件路径
        """
        input_path = Path(input_path)
        output_path = Path(output_path)

        if not input_path.exists():
            raise FileNotFoundError(f"输入文件不存在: {input_path}")

        try:
            # 尝试使用 pydub
            try:
                from pydub import AudioSegment

                # 加载音频
                audio = AudioSegment.from_file(str(input_path))

                # 导出为目标格式
                audio.export(str(output_path), format=output_format)

                logger.info(f"音频格式转换成功: {input_path} -> {output_path}")
                return str(output_path)

            except ImportError:
                # 降级策略：使用 soundfile（仅支持 wav）
                if output_format.lower() == "wav":
                    import soundfile as sf
                    data, samplerate = sf.read(str(input_path))
                    sf.write(str(output_path), data, samplerate)
                    logger.info(f"音频转换为 WAV: {input_path} -> {output_path}")
                    return str(output_path)
                else:
                    logger.warning("pydub 未安装，仅支持转换为 WAV 格式")
                    raise ImportError("需要安装 pydub 以支持多种音频格式转换")

        except Exception as e:
            logger.error(f"音频格式转换失败: {e}")
            raise


_audio_processor_instance: AudioProcessor | None = None


def get_audio_processor_instance() -> AudioProcessor:
    """获取全局音频处理器实例（惰性初始化）。

    避免在 import 阶段创建实例，减少 GUI 启动时的阻塞与无意义日志。
    """
    global _audio_processor_instance
    if _audio_processor_instance is None:
        _audio_processor_instance = AudioProcessor()
    return _audio_processor_instance


def __getattr__(name: str):  # pragma: no cover
    # 兼容旧代码：from src.multimodal.audio import audio_processor
    if name == "audio_processor":
        return get_audio_processor_instance()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:  # pragma: no cover
    return sorted(list(globals().keys()) + ["audio_processor"])
