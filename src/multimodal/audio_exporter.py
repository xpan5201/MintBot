"""
音频导出器 - v2.41.0

支持导出TTS合成的音频文件，功能包括：
- 单个音频导出
- 批量音频导出
- 多种格式支持（WAV, MP3, OGG）
- 自动文件命名
- 自定义文件名模板 (v2.41.0)
- 导出元数据（JSON）(v2.41.0)
"""

from pathlib import Path
from typing import List, Dict, Any, Optional
import tempfile
import os
import json
from datetime import datetime

from src.multimodal.audio import AudioProcessor
from src.utils.logger import get_logger

logger = get_logger(__name__)


class AudioExporter:
    """音频导出器 (v2.41.0)"""

    # v2.41.0: 默认文件名模板
    DEFAULT_FILENAME_TEMPLATE = "tts_{timestamp}_{text_preview}"

    def __init__(self, output_dir: str = "data/tts_exports"):
        """
        初始化音频导出器

        Args:
            output_dir: 输出目录
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.audio_processor = AudioProcessor()

        # v2.41.0: 文件名模板
        self.filename_template = self.DEFAULT_FILENAME_TEMPLATE

        logger.info(f"音频导出器已初始化: {output_dir}")

    def export_single(
        self,
        audio_data: bytes,
        filename: Optional[str] = None,
        format: str = "wav",
        text: Optional[str] = None,
        ref_audio: Optional[str] = None,
        emotion: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        export_metadata: bool = False,
    ) -> str:
        """
        导出单个音频 (v2.41.0: 增加元数据支持)

        Args:
            audio_data: 音频数据（WAV格式）
            filename: 文件名（可选，自动生成）
            format: 输出格式（wav, mp3, ogg）
            text: 文本内容（用于生成文件名）
            ref_audio: 参考音频名称 (v2.41.0)
            emotion: 情感标签 (v2.41.0)
            metadata: 元数据字典 (v2.41.0)
            export_metadata: 是否导出元数据到JSON (v2.41.0)

        Returns:
            str: 导出的文件路径
        """
        try:
            # v2.41.0: 使用模板生成文件名
            if filename is None:
                filename = self.generate_filename(
                    format=format, text=text, ref_audio=ref_audio, emotion=emotion
                )

            # 确保文件名有正确的扩展名
            if not filename.endswith(f".{format}"):
                filename = f"{filename}.{format}"

            output_path = self.output_dir / filename

            # 如果格式是WAV，直接保存
            if format.lower() == "wav":
                with open(output_path, "wb") as f:
                    f.write(audio_data)
                logger.info(f"导出WAV音频: {output_path}")
            else:
                # 其他格式需要转换
                # 先保存为临时WAV文件
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_wav:
                    temp_wav.write(audio_data)
                    temp_wav_path = temp_wav.name

                try:
                    # 转换格式
                    self.audio_processor.convert_audio_format(
                        input_path=temp_wav_path, output_path=str(output_path), output_format=format
                    )
                    logger.info(f"导出{format.upper()}音频: {output_path}")

                finally:
                    # 删除临时文件
                    if os.path.exists(temp_wav_path):
                        os.remove(temp_wav_path)

            # v2.41.0: 导出元数据
            if export_metadata and metadata:
                metadata_filename = output_path.stem + "_metadata.json"
                self.export_metadata(metadata, metadata_filename)

            return str(output_path)

        except Exception as e:
            logger.error(f"导出音频失败: {e}")
            raise

    def export_batch(
        self,
        items: List[Dict[str, Any]],
        format: str = "wav",
        progress_callback: Optional[callable] = None,
    ) -> List[str]:
        """
        批量导出音频

        Args:
            items: 音频项目列表，每项包含 audio_data 和 text
            format: 输出格式（wav, mp3, ogg）
            progress_callback: 进度回调函数 (current, total)

        Returns:
            List[str]: 导出的文件路径列表
        """
        exported_paths = []
        total = len(items)

        for i, item in enumerate(items):
            try:
                audio_data = item.get("audio_data")
                text = item.get("text", "")

                if not audio_data:
                    logger.warning(f"跳过无音频数据的项目: {text[:30]}...")
                    continue

                # 导出单个音频
                output_path = self.export_single(audio_data=audio_data, format=format, text=text)
                exported_paths.append(output_path)

                # 调用进度回调
                if progress_callback:
                    progress_callback(i + 1, total)

            except Exception as e:
                logger.error(f"导出第{i+1}个音频失败: {e}")
                continue

        logger.info(f"批量导出完成: {len(exported_paths)}/{total}")
        return exported_paths

    def get_export_directory(self) -> str:
        """
        获取导出目录

        Returns:
            str: 导出目录路径
        """
        return str(self.output_dir)

    def set_export_directory(self, directory: str):
        """
        设置导出目录

        Args:
            directory: 新的导出目录
        """
        self.output_dir = Path(directory)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"导出目录已更新: {directory}")

    def set_filename_template(self, template: str):
        """
        设置文件名模板 (v2.41.0)

        Args:
            template: 文件名模板，支持以下占位符：
                - {timestamp}: 时间戳
                - {text_preview}: 文本预览
                - {ref_audio}: 参考音频名称
                - {emotion}: 情感标签
                - {index}: 序号
        """
        self.filename_template = template
        logger.info(f"文件名模板已更新: {template}")

    def generate_filename(
        self,
        format: str = "wav",
        text: Optional[str] = None,
        ref_audio: Optional[str] = None,
        emotion: Optional[str] = None,
        index: Optional[int] = None,
    ) -> str:
        """
        根据模板生成文件名 (v2.41.0)

        Args:
            format: 文件格式
            text: 文本内容
            ref_audio: 参考音频名称
            emotion: 情感标签
            index: 序号

        Returns:
            str: 生成的文件名
        """
        # 生成时间戳
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # 生成文本预览
        text_preview = ""
        if text:
            text_preview = text[:10].replace(" ", "_").replace("\n", "_")
            text_preview = "".join(c for c in text_preview if c.isalnum() or c in ("_", "-"))

        # 替换占位符
        filename = self.filename_template
        filename = filename.replace("{timestamp}", timestamp)
        filename = filename.replace("{text_preview}", text_preview)
        filename = filename.replace("{ref_audio}", ref_audio or "")
        filename = filename.replace("{emotion}", emotion or "")
        filename = filename.replace("{index}", str(index) if index is not None else "")

        # 添加扩展名
        filename = f"{filename}.{format}"

        return filename

    def export_metadata(self, metadata: Dict[str, Any], filename: Optional[str] = None) -> str:
        """
        导出元数据到JSON文件 (v2.41.0)

        Args:
            metadata: 元数据字典
            filename: 文件名（可选，自动生成）

        Returns:
            str: 导出的文件路径
        """
        try:
            # 生成文件名
            if filename is None:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"tts_metadata_{timestamp}.json"

            # 确保文件名有.json扩展名
            if not filename.endswith(".json"):
                filename = f"{filename}.json"

            output_path = self.output_dir / filename

            # 写入JSON文件
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(metadata, f, ensure_ascii=False, indent=2)

            logger.info(f"导出元数据: {output_path}")
            return str(output_path)

        except Exception as e:
            logger.error(f"导出元数据失败: {e}")
            raise


# 创建全局音频导出器实例
_audio_exporter_instance = None


def get_audio_exporter(output_dir: str = "data/tts_exports") -> AudioExporter:
    """
    获取音频导出器实例（单例模式）

    Args:
        output_dir: 输出目录

    Returns:
        AudioExporter: 音频导出器实例
    """
    global _audio_exporter_instance

    if _audio_exporter_instance is None:
        _audio_exporter_instance = AudioExporter(output_dir)

    return _audio_exporter_instance
