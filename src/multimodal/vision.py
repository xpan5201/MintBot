"""
视觉处理模块 (v2.30.0 优化版)

处理图像输入，支持图像理解和分析。

优化内容:
- 增强OCR预处理（灰度化、二值化、降噪）
- 支持多种图片识别模式（描述、OCR、混合）
- 优化图片压缩和格式转换
- 改进错误处理和日志记录
"""

import base64
from io import BytesIO
from pathlib import Path
from typing import Optional, Union, Literal

from PIL import Image, ImageEnhance, ImageFilter, ImageOps

from src.config.settings import settings
from src.utils.logger import get_logger

logger = get_logger(__name__)


class VisionProcessor:
    """视觉处理器"""

    # 支持的图像格式
    SUPPORTED_FORMATS = ["jpg", "jpeg", "png", "gif", "bmp", "webp"]

    def __init__(self, max_size: Optional[int] = None):
        """
        初始化视觉处理器

        Args:
            max_size: 图像最大尺寸（像素），默认从配置读取
        """
        try:
            self.max_size = max_size or getattr(settings, "max_image_size", 1024)
        except Exception as e:
            logger.warning("无法从配置读取 max_image_size，使用默认值 1024: %s", e)
            self.max_size = 1024

        self.supported_formats = self.SUPPORTED_FORMATS
        logger.info("视觉处理器初始化完成，最大尺寸: %spx", self.max_size)

    def load_image(self, image_path: Union[str, Path]) -> Image.Image:
        """
        加载图像文件

        Args:
            image_path: 图像文件路径

        Returns:
            Image.Image: PIL Image 对象

        Raises:
            FileNotFoundError: 如果文件不存在
            ValueError: 如果文件不是有效的图像
        """
        image_path = Path(image_path)

        if not image_path.exists():
            raise FileNotFoundError(f"图像文件不存在: {image_path}")

        try:
            # Windows 下 Pillow 可能在 Image 对象生命周期内持有文件句柄。
            # 这里使用 copy() + 上下文管理器，确保文件及时关闭，避免后续移动/删除文件失败。
            with Image.open(image_path) as img:
                fmt = getattr(img, "format", None)
                try:
                    img = ImageOps.exif_transpose(img)
                except Exception:
                    pass
                image = img.copy()
                # 保留 format 等元信息，避免 copy() 后 image.format 变为 None
                try:
                    image.format = fmt or getattr(img, "format", None)  # type: ignore[attr-defined]
                except Exception:
                    pass
            logger.info("加载图像: %s, 尺寸: %s", image_path, image.size)
            return image
        except Exception as e:
            logger.error("加载图像失败: %s", e)
            raise ValueError(f"无效的图像文件: {image_path}")

    def resize_image(
        self,
        image: Image.Image,
        max_size: Optional[int] = None,
    ) -> Image.Image:
        """
        调整图像大小

        Args:
            image: PIL Image 对象
            max_size: 最大尺寸

        Returns:
            Image.Image: 调整后的图像
        """
        max_size = max_size or self.max_size

        # 如果图像已经小于最大尺寸，直接返回
        if max(image.size) <= max_size:
            return image

        # 计算缩放比例
        ratio = max_size / max(image.size)
        new_size = tuple(max(1, int(dim * ratio)) for dim in image.size)

        # 调整大小
        resized_image = image.resize(new_size, Image.Resampling.LANCZOS)
        logger.debug("图像已调整: %s -> %s", image.size, new_size)

        return resized_image

    def image_to_base64(self, image: Image.Image, format: str = "PNG") -> str:
        """
        将图像转换为 base64 编码

        Args:
            image: PIL Image 对象
            format: 图像格式

        Returns:
            str: base64 编码的图像数据
        """
        buffered = BytesIO()
        save_kwargs = {}
        fmt = (format or "PNG").upper()
        if fmt == "JPEG":
            # 视觉理解场景对“极致画质”不敏感，使用轻量压缩可显著降低 base64 体积与传输开销。
            save_kwargs.update({"quality": 85, "optimize": True, "progressive": True})
        elif fmt == "PNG":
            save_kwargs.update({"optimize": True})

        image.save(buffered, format=format, **save_kwargs)
        img_bytes = buffered.getvalue()
        img_base64 = base64.b64encode(img_bytes).decode("utf-8")

        logger.debug("图像已转换为 base64，大小: %s 字符", len(img_base64))
        return img_base64

    def _prepare_image_for_llm_from_image(
        self,
        image: Image.Image,
        *,
        format: str = "JPEG",
        max_size: Optional[int] = None,
    ) -> dict:
        """将已加载的 PIL Image 转为 OpenAI-compatible image_url 内容块，避免重复磁盘读取。"""
        # 调整大小
        image = self.resize_image(image, max_size=max_size)

        # 如果是 JPEG 格式且图像有透明通道，转换为 RGB
        if format.upper() == "JPEG" and image.mode in ("RGBA", "LA", "P"):
            # 创建白色背景
            background = Image.new("RGB", image.size, (255, 255, 255))
            if image.mode == "P":
                image = image.convert("RGBA")
            # 使用 alpha 通道作为 mask（如果有）
            mask = image.split()[-1] if image.mode in ("RGBA", "LA") else None
            background.paste(image, mask=mask)
            image = background

        # 转换为 base64
        image_base64 = self.image_to_base64(image, format=format)

        # 确定 MIME 类型
        mime_type = "image/jpeg" if format.upper() == "JPEG" else "image/png"

        # 构建 OpenAI-compatible image_url 内容块
        return {
            "type": "image_url",
            "image_url": {
                "url": f"data:{mime_type};base64,{image_base64}",
            },
        }

    def prepare_image_for_llm(
        self,
        image_path: Union[str, Path],
        format: str = "JPEG",
        max_size: Optional[int] = None,
    ) -> dict:
        """
        准备图像用于 LLM 输入

        Args:
            image_path: 图像文件路径
            format: 输出格式（JPEG 或 PNG），默认 JPEG（更小）

        Returns:
            dict: 包含图像数据的字典，格式适用于 OpenAI-compatible Chat Completions
        """
        try:
            # 加载图像
            image = self.load_image(image_path)
            image_data = self._prepare_image_for_llm_from_image(
                image, format=format, max_size=max_size
            )
            logger.info("图像已准备用于 LLM: %s (%s)", image_path, format)
            return image_data

        except Exception as e:
            logger.error("准备图像失败: %s", e)
            raise

    def analyze_image(
        self,
        image_path: Union[str, Path],
        prompt: str = "请描述这张图片的内容",
        llm=None,
        image_data: Optional[dict] = None,
        max_size: Optional[int] = None,
    ) -> str:
        """
        分析图像内容（需要支持视觉的 LLM）

        Args:
            image_path: 图像文件路径
            prompt: 分析提示
            llm: 支持视觉的 LLM 实例（如 GPT-4V, Claude 3, Gemini Pro Vision）
            image_data: 预先准备好的图像消息片段（用于复用 base64，提升性能）

        Returns:
            str: 图像分析结果
        """
        # 加载图像以验证其存在性：让 FileNotFoundError 等显式抛出，便于上层处理
        image: Optional[Image.Image] = None
        if image_data is None:
            image = self.load_image(image_path)

        try:
            # 如果提供了支持视觉的 LLM，使用它进行分析
            if llm is not None:
                from src.llm_native.backend import ChatRequest
                from src.llm_native.messages import Message, TextPart

                # 准备图像数据（尽量复用，避免重复读取与 base64 编码）
                if image_data is None:
                    image_data = self._prepare_image_for_llm_from_image(
                        image,
                        format="JPEG",
                        max_size=max_size,
                    )

                # 构建消息
                message = Message(role="user", content=[TextPart(prompt), image_data])
                request = ChatRequest(messages=[message], tools=[], temperature=0.0)
                try:
                    response = llm.complete(request)
                except Exception as exc:
                    err_text = str(exc)
                    if ("not a VLM" in err_text) or ("Vision Language Model" in err_text):
                        model_name = ""
                        try:
                            model_name = str(
                                getattr(getattr(llm, "config", None), "model", "") or ""
                            )
                        except Exception:
                            model_name = ""
                        model_hint = f"（当前: {model_name}）" if model_name else ""
                        return (
                            "图像分析失败：当前配置的模型不支持图片（VLM）。"
                            f"{model_hint} 请在 config.user.yaml 配置 VISION_LLM.model 为视觉模型后重试。"
                        )
                    raise
                logger.info("图像分析完成: %s", image_path)
                return str(getattr(response, "output_text", "") or "")

            # 如果没有提供 LLM，返回基本信息
            if image is None:
                info = self.get_image_info(image_path)
            else:
                info = {
                    "path": str(image_path),
                    "size": image.size,
                    "width": image.size[0],
                    "height": image.size[1],
                    "format": image.format,
                    "mode": image.mode,
                }
            return (
                f"这是一张 {info['width']}x{info['height']} 的{info['format']}图像。\n"
                f"提示：要获得详细的图像分析，请使用支持视觉的 LLM（如 GPT-4V、Claude 3 或 Gemini Pro Vision）。"
            )

        except Exception as e:
            logger.error("图像分析失败: %s", e)
            return f"图像分析失败: {str(e)}"

    def preprocess_for_ocr(self, image: Image.Image) -> Image.Image:
        """
        预处理图像以提高OCR准确性 (v2.30.0 新增)

        应用灰度化、对比度增强、锐化等处理

        Args:
            image: PIL Image对象

        Returns:
            Image.Image: 预处理后的图像
        """
        try:
            # 转换为RGB模式（如果是RGBA或其他模式）
            if image.mode != "RGB":
                image = image.convert("RGB")

            # 转换为灰度图
            image = image.convert("L")

            # 增强对比度
            enhancer = ImageEnhance.Contrast(image)
            image = enhancer.enhance(2.0)

            # 锐化
            image = image.filter(ImageFilter.SHARPEN)

            # 降噪（中值滤波）
            image = image.filter(ImageFilter.MedianFilter(size=3))

            logger.debug("图像OCR预处理完成")
            return image

        except Exception as e:
            logger.warning("OCR预处理失败，使用原图: %s", e)
            return image

    def extract_text_from_image(
        self,
        image_path: Union[str, Path],
        llm=None,
        preprocess: bool = True,
        image_data: Optional[dict] = None,
        max_size: Optional[int] = None,
    ) -> str:
        """
        从图像中提取文字（OCR） (v2.30.0 优化版)

        Args:
            image_path: 图像文件路径
            llm: 支持视觉的 LLM 实例（推荐使用 GPT-4V 或 Claude 3）
            preprocess: 是否进行OCR预处理（仅对pytesseract有效）
            image_data: 预先准备好的图像消息片段（用于复用 base64，提升性能）

        Returns:
            str: 提取的文字
        """
        try:
            # 如果提供了支持视觉的 LLM，使用它进行 OCR
            if llm is not None:
                prompt = "请提取这张图片中的所有文字内容，保持原有的格式和排版。如果没有文字，请回复'图片中没有文字'。"
                return self.analyze_image(
                    image_path,
                    prompt,
                    llm,
                    image_data=image_data,
                    max_size=max_size,
                )

            # 否则尝试使用 pytesseract（如果已安装）
            try:
                import pytesseract

                image = self.load_image(image_path)

                # v2.30.0: 应用OCR预处理
                if preprocess:
                    image = self.preprocess_for_ocr(image)

                # 使用中英文混合识别
                text = pytesseract.image_to_string(image, lang="chi_sim+eng")

                if text.strip():
                    logger.info("OCR 提取成功: %s 个字符", len(text))
                    return text.strip()
                else:
                    return "图片中没有检测到文字"

            except ImportError:
                logger.warning("pytesseract 未安装，建议使用支持视觉的 LLM 进行 OCR")
                return "OCR 失败: pytesseract 未安装（请安装 pytesseract 或配置支持视觉的 LLM）"

        except Exception as e:
            logger.error("OCR 失败: %s", e)
            return f"OCR 失败: {str(e)}"

    def get_image_info(self, image_path: Union[str, Path]) -> dict:
        """
        获取图像基本信息

        Args:
            image_path: 图像文件路径

        Returns:
            dict: 图像信息

        Raises:
            FileNotFoundError: 如果文件不存在
            ValueError: 如果文件不是有效的图像
        """
        # load_image 会抛出 FileNotFoundError 或 ValueError
        image = self.load_image(image_path)

        info = {
            "path": str(image_path),
            "size": image.size,
            "width": image.size[0],
            "height": image.size[1],
            "format": image.format,
            "mode": image.mode,
        }

        logger.debug("图像信息: %s", info)
        return info

    def smart_analyze(
        self,
        image_path: Union[str, Path],
        mode: Literal["auto", "describe", "ocr", "both"] = "auto",
        llm=None,
        max_size: Optional[int] = None,
    ) -> dict:
        """
        智能分析图片（v2.30.0 新增）

        根据模式自动选择最佳分析方式：
        - auto: 自动判断（先尝试OCR，如果没有文字则描述图片）
        - describe: 仅描述图片内容
        - ocr: 仅提取文字
        - both: 同时进行描述和OCR

        Args:
            image_path: 图像文件路径
            mode: 分析模式
            llm: 支持视觉的LLM实例

        Returns:
            dict: 分析结果，包含description和text字段
        """
        try:
            result = {
                "description": "",
                "text": "",
                "mode": mode,
                "success": True,
            }

            prepared_image_data: Optional[dict] = None
            if llm is not None:
                # v3.x: 复用一次 base64 编码结果，减少“describe + ocr”场景的重复开销
                try:
                    prepared_image_data = self.prepare_image_for_llm(image_path, max_size=max_size)
                except Exception as exc:
                    # 不中断整体流程：让 analyze_image/extract_text_from_image 自行回退到临时编码
                    logger.warning("prepare_image_for_llm 失败，将回退为按需编码: %s", exc)
                    prepared_image_data = None

            if mode == "describe":
                # 仅描述图片
                result["description"] = self.analyze_image(
                    image_path,
                    prompt="请详细描述这张图片的内容，包括主要对象、场景、颜色、氛围等。",
                    llm=llm,
                    image_data=prepared_image_data,
                    max_size=max_size,
                )

            elif mode == "ocr":
                # 仅OCR
                result["text"] = self.extract_text_from_image(
                    image_path,
                    llm=llm,
                    image_data=prepared_image_data,
                    max_size=max_size,
                )

            elif mode == "both":
                # 同时进行
                result["description"] = self.analyze_image(
                    image_path,
                    prompt="请描述这张图片的内容。",
                    llm=llm,
                    image_data=prepared_image_data,
                    max_size=max_size,
                )
                result["text"] = self.extract_text_from_image(
                    image_path,
                    llm=llm,
                    image_data=prepared_image_data,
                    max_size=max_size,
                )

            else:  # auto
                # 先尝试OCR
                text = self.extract_text_from_image(
                    image_path,
                    llm=llm,
                    image_data=prepared_image_data,
                    max_size=max_size,
                )
                result["text"] = text

                # 如果没有检测到文字，则描述图片
                if "没有" in text or "失败" in text or len(text.strip()) < 5:
                    result["description"] = self.analyze_image(
                        image_path,
                        prompt="请描述这张图片的内容。",
                        llm=llm,
                        image_data=prepared_image_data,
                        max_size=max_size,
                    )
                    result["mode"] = "describe"
                else:
                    result["mode"] = "ocr"

            logger.info("智能分析完成: %s, 模式: %s", image_path, result.get("mode"))
            return result

        except Exception as e:
            logger.error("智能分析失败: %s", e)
            return {
                "description": "",
                "text": f"分析失败: {str(e)}",
                "mode": mode,
                "success": False,
            }


_vision_processor_instance: VisionProcessor | None = None


def get_vision_processor_instance() -> VisionProcessor:
    """获取全局视觉处理器实例（惰性初始化）。

    避免在 import 阶段创建实例，减少 GUI 启动时的阻塞与无意义日志。
    """
    global _vision_processor_instance
    if _vision_processor_instance is None:
        _vision_processor_instance = VisionProcessor()
    return _vision_processor_instance


def __getattr__(name: str):  # pragma: no cover
    # 兼容旧代码：from src.multimodal.vision import vision_processor
    if name == "vision_processor":
        return get_vision_processor_instance()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:  # pragma: no cover
    return sorted(list(globals().keys()) + ["vision_processor"])
