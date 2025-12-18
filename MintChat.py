#!/usr/bin/env python3
"""MintChat - 多模态猫娘女仆智能体（Material Design 3、浅色主题、QQ风格、流式输出、性能优化）"""

import sys
import os
import threading
from pathlib import Path
from typing import Dict, Any

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QFont
from PyQt6.QtCore import qInstallMessageHandler, QtMsgType

from src.version import __version__, print_version_info
from src.auth.auth_service import AuthService
from src.auth.user_session import user_session
from src.auth.session_store import (
    delete_session_token_file,
    read_session_token,
    write_session_token_file,
)
from src.utils.logger import logger
from src.utils.dependency_checker import check_optional_dependencies

GUI_ANIMATIONS_ENABLED = os.getenv("MINTCHAT_GUI_ANIMATIONS", "0").lower() not in {
    "0",
    "false",
    "no",
    "off",
}
_tts_init_started = False


def _start_tts_init_async() -> None:
    """后台初始化 TTS（避免阻塞 GUI 启动与首帧渲染）。"""
    global _tts_init_started
    if _tts_init_started:
        return
    _tts_init_started = True

    def _runner() -> None:
        try:
            from src.multimodal import init_tts

            if callable(init_tts):
                init_tts()
        except Exception as e:
            logger.warning(f"TTS 初始化失败: {e}")
            logger.info("应用将继续运行，但 TTS 功能暂不可用")

    threading.Thread(target=_runner, name="MintChatTTSInit", daemon=True).start()


def _qt_message_handler(msg_type, context, message):
    """统一处理 Qt 日志，过滤掉已知的无害噪声信息。

    目前主要用于屏蔽大量重复的：
        QBuffer::seek: Invalid pos: XXXX
    这类信息来自 Qt 内部对内存缓冲区的探测性 seek，不影响实际音频播放，
    但会严重干扰控制台日志查看，因此在这里安全地忽略。
    """
    # 屏蔽 QBuffer::seek 的无效位置提示
    if isinstance(message, str) and "QBuffer::seek: Invalid pos" in message:
        return

    # 其他 Qt 消息仍然通过 Python 日志系统输出，方便排查问题
    if msg_type == QtMsgType.QtWarningMsg:
        logger.warning(message)
    elif msg_type in (QtMsgType.QtCriticalMsg, QtMsgType.QtFatalMsg):
        logger.error(message)
    else:
        # 包含 QtDebugMsg / QtInfoMsg 等
        logger.info(message)


# 安装 Qt 全局消息处理器（必须在 QApplication 创建之前）
qInstallMessageHandler(_qt_message_handler)

from src.utils.exceptions import handle_exception


def _restore_session(session_file: Path) -> bool:
    """尝试恢复用户会话（优化：减少文件I/O和异常处理开销）"""
    session_token = read_session_token(session_file, delete_on_invalid=True)
    if not session_token:
        return False

    try:
        auth_service = AuthService()
        if auth_service.restore_session(session_token):
            user = auth_service.get_current_user()
            logger.info("会话恢复成功，欢迎回来：%s", user.get("username"))
            user_session.login(user, session_token)
            return True

        # 明确无效/过期：清除会话文件，避免下次启动反复尝试
        logger.info("会话无效或已过期，需要重新登录")
        delete_session_token_file(session_file)
        return False
    except Exception as e:
        # 可能是临时性错误（如 DB 锁/IO 问题），不要误删会话文件
        handle_exception(e, logger, "恢复会话失败（将保留会话文件以便下次重试）")
        return False


def main() -> None:
    """主函数"""
    # 启动前检查可选依赖，缺失时给出明确提示
    deps_status = check_optional_dependencies()
    if deps_status["missing"]:
        logger.error(
            "缺失依赖将导致高级功能不可用：%s。请安装后重启。",
            ", ".join(deps_status["missing"]),
        )

    app = QApplication(sys.argv)
    app.setApplicationName("MintChat")
    app.setApplicationVersion(__version__)
    app.setOrganizationName("MintChat")

    font = QFont("Microsoft YaHei UI", 10)
    app.setFont(font)

    # 确保 Material Symbols 字体可用（图标按钮/导航栏依赖）。未安装时仅提示，不影响启动。
    try:
        from src.gui.material_icons import load_material_symbols_font

        load_material_symbols_font()
    except Exception:
        pass

    # 应用全局主题样式（菜单/tooltip/滚动条等全局 QSS）
    try:
        from src.gui.app_theme import apply_app_theme

        apply_app_theme(app)
    except Exception:
        pass

    # v2.48.10: 初始化 TTS 服务（后台线程，避免健康检查阻塞 GUI 启动）
    _start_tts_init_async()

    try:
        from src.config.settings import settings

        data_dir = Path(settings.data_dir)
    except Exception:
        data_dir = Path("data")

    session_file = data_dir / "session.txt"
    if _restore_session(session_file):
        from src.gui.light_chat_window import LightChatWindow

        window = LightChatWindow()
        window.show()
        sys.exit(app.exec())

    from src.gui.auth_manager import AuthManager

    auth_manager = AuthManager(illustration_path=str(data_dir / "images" / "login_illustration.png"))

    def on_login_success(user: Dict[str, Any]) -> None:
        """处理登录成功事件（优化：减少导入开销，合并操作）"""
        logger.info(f"登录成功！欢迎，{user['username']}！")

        try:
            session_token = user.get('session_token')
            remember_me = user.get('remember_me', False)

            if session_token and remember_me:
                if write_session_token_file(session_file, session_token):
                    logger.info(f"会话已保存到: {session_file}")
            else:
                delete_session_token_file(session_file)
                logger.info("已清除保存的会话")

            user_session.login(user, session_token)
        except Exception as e:
            handle_exception(e, logger, "保存会话失败")

        from src.gui.light_chat_window import LightChatWindow

        window = LightChatWindow()

        if not GUI_ANIMATIONS_ENABLED:
            auth_manager.close()
            window.show()
            return

        from PyQt6.QtCore import QPropertyAnimation, QEasingCurve
        from PyQt6.QtWidgets import QGraphicsOpacityEffect

        auth_opacity_effect = QGraphicsOpacityEffect(auth_manager)
        auth_manager.setGraphicsEffect(auth_opacity_effect)

        auth_fade_out = QPropertyAnimation(auth_opacity_effect, b"opacity")
        auth_fade_out.setDuration(300)
        auth_fade_out.setStartValue(1.0)
        auth_fade_out.setEndValue(0.0)
        auth_fade_out.setEasingCurve(QEasingCurve.Type.InCubic)
        auth_fade_out.finished.connect(lambda: (auth_manager.close(), window.show()))
        auth_fade_out.start()

    auth_manager.login_success.connect(on_login_success)
    auth_manager.show()

    try:
        sys.exit(app.exec())
    except KeyboardInterrupt:
        logger.info("程序被用户中断")
        sys.exit(0)


if __name__ == "__main__":
    print()
    print_version_info()
    print("正在启动 GUI...")
    print()

    try:
        main()
    except KeyboardInterrupt:
        logger.info("程序被用户中断")
        sys.exit(0)
    except Exception as e:
        handle_exception(e, logger, "程序运行出错")
        sys.exit(1)
