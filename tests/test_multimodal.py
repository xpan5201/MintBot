"""
多模态功能测试

测试 VisionProcessor 和 AudioProcessor 的基本功能
"""

import pytest
from pathlib import Path
from src.multimodal.vision import VisionProcessor
from src.multimodal.audio import AudioProcessor


class TestVisionProcessor:
    """VisionProcessor 测试"""

    def test_init(self):
        """测试初始化"""
        processor = VisionProcessor()
        assert processor is not None

    def test_supported_formats(self):
        """测试支持的图片格式"""
        processor = VisionProcessor()

        expected_formats = ["jpg", "jpeg", "png", "gif", "bmp", "webp"]
        assert processor.SUPPORTED_FORMATS == expected_formats

    def test_smart_analyze_auto_falls_back_when_pytesseract_missing(self, sample_image_path, monkeypatch):
        """auto 模式下无 pytesseract 时应回退到 describe（避免只返回 OCR 缺依赖提示）。"""
        import builtins

        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "pytesseract":
                raise ImportError("pytesseract not installed")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)

        processor = VisionProcessor()
        result = processor.smart_analyze(str(sample_image_path), mode="auto", llm=None)
        assert result.get("mode") == "describe"
        assert "这是一张" in (result.get("description") or "")

    def test_validate_image_format_valid(self, sample_image_path):
        """测试有效图片格式验证"""
        processor = VisionProcessor()

        # JPG 格式应该有效
        assert sample_image_path.suffix.lower() in [f".{fmt}" for fmt in processor.SUPPORTED_FORMATS]

    def test_validate_image_format_invalid(self, temp_dir):
        """测试无效图片格式验证"""
        processor = VisionProcessor()

        # 创建一个不支持的格式文件
        invalid_file = temp_dir / "test.txt"
        invalid_file.touch()

        # 验证格式不在支持列表中
        assert invalid_file.suffix.lower() not in [f".{fmt}" for fmt in processor.SUPPORTED_FORMATS]

    def test_image_file_not_found(self):
        """测试图片文件不存在的情况"""
        processor = VisionProcessor()

        # 尝试分析不存在的文件应该抛出错误
        with pytest.raises(Exception):
            processor.analyze_image("nonexistent_image.jpg")


class TestAudioProcessor:
    """AudioProcessor 测试"""

    def test_init(self):
        """测试初始化"""
        processor = AudioProcessor()
        assert processor is not None

    def test_supported_formats(self):
        """测试支持的音频格式"""
        processor = AudioProcessor()

        expected_formats = ["mp3", "wav", "ogg", "flac", "m4a", "aac"]
        assert processor.SUPPORTED_FORMATS == expected_formats

    def test_validate_audio_format_valid(self, sample_audio_path):
        """测试有效音频格式验证"""
        processor = AudioProcessor()

        # MP3 格式应该有效
        assert sample_audio_path.suffix.lower() in [f".{fmt}" for fmt in processor.SUPPORTED_FORMATS]

    def test_validate_audio_format_invalid(self, temp_dir):
        """测试无效音频格式验证"""
        processor = AudioProcessor()

        # 创建一个不支持的格式文件
        invalid_file = temp_dir / "test.txt"
        invalid_file.touch()

        # 验证格式不在支持列表中
        assert invalid_file.suffix.lower() not in [f".{fmt}" for fmt in processor.SUPPORTED_FORMATS]

    def test_audio_file_not_found(self):
        """测试音频文件不存在的情况"""
        processor = AudioProcessor()

        # 尝试转录不存在的文件应该抛出错误
        with pytest.raises(Exception):
            processor.transcribe_audio("nonexistent_audio.mp3")


@pytest.mark.integration
class TestMultimodalIntegration:
    """多模态集成测试"""

    def test_vision_and_audio_processors_coexist(self):
        """测试视觉和音频处理器可以同时存在"""
        vision = VisionProcessor()
        audio = AudioProcessor()

        assert vision is not None
        assert audio is not None
        assert vision != audio

    def test_processors_have_different_formats(self):
        """测试处理器支持不同的格式"""
        vision = VisionProcessor()
        audio = AudioProcessor()

        # 确保格式列表不同
        assert vision.SUPPORTED_FORMATS != audio.SUPPORTED_FORMATS

        # 确保没有重叠（图片和音频格式应该不同）
        vision_set = set(vision.SUPPORTED_FORMATS)
        audio_set = set(audio.SUPPORTED_FORMATS)
        assert len(vision_set & audio_set) == 0  # 没有交集
