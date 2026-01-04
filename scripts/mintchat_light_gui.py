"""
MintChat 浅色主题 GUI 启动器

基于 Material Design 3 浅色主题
参考 QQ 现代化界面设计
使用可爱的渐变色
"""

import sys
from pathlib import Path
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QFont

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from src.gui.light_chat_window import LightChatWindow


def main():
    """主函数"""
    # 创建应用
    app = QApplication(sys.argv)

    # 设置应用信息
    app.setApplicationName("MintChat")
    app.setOrganizationName("MintChat")
    app.setApplicationDisplayName("MintChat - 猫娘女仆智能体")

    # 设置默认字体
    font = QFont("Microsoft YaHei UI", 10)
    app.setFont(font)

    # 创建主窗口
    window = LightChatWindow()
    window.show()

    # 运行应用
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
