"""
对话历史导出工具

支持将对话历史导出为多种格式。
"""

import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Union

from src.utils.logger import get_logger

logger = get_logger(__name__)


class ConversationExporter:
    """对话历史导出器"""

    def __init__(self, output_dir: Optional[Union[str, Path]] = None):
        """
        初始化导出器

        Args:
            output_dir: 输出目录，默认为 data/exports
        """
        self.output_dir = Path(output_dir or "data/exports")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"对话导出器初始化完成，输出目录: {self.output_dir}")

    def export_to_json(
        self,
        conversations: List[Dict],
        filename: Optional[str] = None,
    ) -> str:
        """
        导出为 JSON 格式

        Args:
            conversations: 对话列表
            filename: 文件名，默认使用时间戳

        Returns:
            str: 导出文件路径
        """
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"conversation_{timestamp}.json"

        output_path = self.output_dir / filename

        try:
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "export_time": datetime.now().isoformat(),
                        "total_messages": len(conversations),
                        "conversations": conversations,
                    },
                    f,
                    ensure_ascii=False,
                    indent=2,
                )

            logger.info(f"对话已导出为 JSON: {output_path}")
            return str(output_path)

        except Exception as e:
            logger.error(f"导出 JSON 失败: {e}")
            raise

    def export_to_markdown(
        self,
        conversations: List[Dict],
        filename: Optional[str] = None,
        title: str = "对话记录",
    ) -> str:
        """
        导出为 Markdown 格式

        Args:
            conversations: 对话列表
            filename: 文件名，默认使用时间戳
            title: 文档标题

        Returns:
            str: 导出文件路径
        """
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"conversation_{timestamp}.md"

        output_path = self.output_dir / filename

        try:
            with open(output_path, "w", encoding="utf-8") as f:
                # 写入标题
                f.write(f"# {title}\n\n")
                f.write(f"**导出时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                f.write(f"**对话数量**: {len(conversations)}\n\n")
                f.write("---\n\n")

                # 写入对话
                for i, conv in enumerate(conversations, 1):
                    role = conv.get("role", "unknown")
                    content = conv.get("content", "")
                    timestamp = conv.get("timestamp", "")

                    if role == "user":
                        f.write(f"## 👤 主人 ({timestamp})\n\n")
                    elif role == "assistant":
                        f.write(f"## 🐱 猫娘女仆 ({timestamp})\n\n")
                    else:
                        f.write(f"## {role} ({timestamp})\n\n")

                    f.write(f"{content}\n\n")
                    f.write("---\n\n")

            logger.info(f"对话已导出为 Markdown: {output_path}")
            return str(output_path)

        except Exception as e:
            logger.error(f"导出 Markdown 失败: {e}")
            raise

    def export_to_txt(
        self,
        conversations: List[Dict],
        filename: Optional[str] = None,
    ) -> str:
        """
        导出为纯文本格式

        Args:
            conversations: 对话列表
            filename: 文件名，默认使用时间戳

        Returns:
            str: 导出文件路径
        """
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"conversation_{timestamp}.txt"

        output_path = self.output_dir / filename

        try:
            with open(output_path, "w", encoding="utf-8") as f:
                # 写入头部
                f.write("=" * 60 + "\n")
                f.write("对话记录\n")
                f.write(f"导出时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"对话数量: {len(conversations)}\n")
                f.write("=" * 60 + "\n\n")

                # 写入对话
                for conv in conversations:
                    role = conv.get("role", "unknown")
                    content = conv.get("content", "")
                    timestamp = conv.get("timestamp", "")

                    if role == "user":
                        f.write(f"[{timestamp}] 主人:\n")
                    elif role == "assistant":
                        f.write(f"[{timestamp}] 猫娘女仆:\n")
                    else:
                        f.write(f"[{timestamp}] {role}:\n")

                    f.write(f"{content}\n\n")
                    f.write("-" * 60 + "\n\n")

            logger.info(f"对话已导出为 TXT: {output_path}")
            return str(output_path)

        except Exception as e:
            logger.error(f"导出 TXT 失败: {e}")
            raise

    def export_to_html(
        self,
        conversations: List[Dict],
        filename: Optional[str] = None,
        title: str = "对话记录",
    ) -> str:
        """
        导出为 HTML 格式

        Args:
            conversations: 对话列表
            filename: 文件名，默认使用时间戳
            title: 文档标题

        Returns:
            str: 导出文件路径
        """
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"conversation_{timestamp}.html"

        output_path = self.output_dir / filename

        try:
            with open(output_path, "w", encoding="utf-8") as f:
                # HTML 头部
                f.write("<!DOCTYPE html>\n")
                f.write("<html lang='zh-CN'>\n")
                f.write("<head>\n")
                f.write("    <meta charset='UTF-8'>\n")
                f.write(f"    <title>{title}</title>\n")
                f.write("    <style>\n")
                f.write(
                    "        body { font-family: Arial, sans-serif; "
                    "max-width: 800px; margin: 0 auto; padding: 20px; }\n"
                )
                f.write(
                    "        .header { text-align: center; "
                    "border-bottom: 2px solid #333; padding-bottom: 20px; }\n"
                )
                f.write(
                    "        .message { margin: 20px 0; padding: 15px; "
                    "border-radius: 10px; }\n"
                )
                f.write("        .user { background-color: #e3f2fd; }\n")
                f.write("        .assistant { background-color: #f3e5f5; }\n")
                f.write("        .role { font-weight: bold; margin-bottom: 5px; }\n")
                f.write("        .timestamp { color: #666; font-size: 0.9em; }\n")
                f.write("        .content { margin-top: 10px; line-height: 1.6; }\n")
                f.write("    </style>\n")
                f.write("</head>\n")
                f.write("<body>\n")

                # 头部信息
                f.write("    <div class='header'>\n")
                f.write(f"        <h1>{title}</h1>\n")
                f.write(f"        <p>导出时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>\n")
                f.write(f"        <p>对话数量: {len(conversations)}</p>\n")
                f.write("    </div>\n\n")

                # 对话内容
                for conv in conversations:
                    role = conv.get("role", "unknown")
                    content = conv.get("content", "")
                    timestamp = conv.get("timestamp", "")

                    css_class = "user" if role == "user" else "assistant"
                    role_name = "👤 主人" if role == "user" else "🐱 猫娘女仆"

                    f.write(f"    <div class='message {css_class}'>\n")
                    f.write(f"        <div class='role'>{role_name}</div>\n")
                    f.write(f"        <div class='timestamp'>{timestamp}</div>\n")
                    f.write(f"        <div class='content'>{content}</div>\n")
                    f.write("    </div>\n\n")

                # HTML 尾部
                f.write("</body>\n")
                f.write("</html>\n")

            logger.info(f"对话已导出为 HTML: {output_path}")
            return str(output_path)

        except Exception as e:
            logger.error(f"导出 HTML 失败: {e}")
            raise


# 创建全局导出器实例
exporter = ConversationExporter()
