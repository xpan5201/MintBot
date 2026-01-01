"""
用户会话管理模块

维护当前登录用户的会话状态和数据
"""

import threading
from typing import TYPE_CHECKING, Any, Dict, Optional

from pathlib import Path

from src.auth.user_data_manager import UserDataManager
from src.utils.logger import get_logger

logger = get_logger(__name__)

if TYPE_CHECKING:
    from src.auth.database import UserDatabase


class UserSession:
    """用户会话管理器 - 单例模式"""

    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """初始化用户会话"""
        if not self._initialized:
            self._state_lock = threading.RLock()
            self.current_user: Optional[Dict[str, Any]] = None
            self.session_token: Optional[str] = None
            # 对话热路径：默认启用连接池 + WAL，提高频繁读写吞吐并减少锁等待
            self.data_manager = UserDataManager(use_pool=True)
            self._auth_db: Optional["UserDatabase"] = None
            self._initialized = True
            logger.info("用户会话管理器初始化完成")

    def _get_auth_db(self) -> "UserDatabase":
        if self._auth_db is None:
            from src.auth.database import UserDatabase

            self._auth_db = UserDatabase()
        return self._auth_db

    def login(self, user: Dict[str, Any], session_token: Optional[str]) -> None:
        """用户登录

        Args:
            user: 用户信息字典
            session_token: 会话令牌（可为空）
        """
        with self._state_lock:
            self.current_user = user
            self.session_token = session_token
            username = user.get("username")
            user_id = user.get("id")
        logger.info("用户 %s (ID: %s) 已登录", username, user_id)

    def logout(self):
        """用户登出"""
        token: Optional[str]
        username: Optional[str]
        with self._state_lock:
            token = self.session_token
            username = self.current_user.get("username") if self.current_user else None
            self.current_user = None
            self.session_token = None

        if token:
            try:
                self._get_auth_db().invalidate_session(token)
            except Exception as e:
                logger.debug("会话失效失败: %s", e)

        if username:
            logger.info("用户 %s 已登出", username)

    def close(self) -> None:
        """释放会话相关资源（幂等）。

        - 关闭 UserDataManager 的数据库连接池
        - 关闭用户认证数据库的预编译语句连接（若启用）
        """
        with self._state_lock:
            auth_db = getattr(self, "_auth_db", None)
            self._auth_db = None
            data_manager = getattr(self, "data_manager", None)

        if data_manager is not None:
            try:
                close_fn = getattr(data_manager, "close", None)
                if callable(close_fn):
                    close_fn()
            except Exception:
                pass

        if auth_db is not None:
            try:
                close_fn = getattr(auth_db, "close", None)
                if callable(close_fn):
                    close_fn()
            except Exception:
                pass

    def is_logged_in(self) -> bool:
        """检查是否已登录

        Returns:
            是否已登录
        """
        with self._state_lock:
            return self.current_user is not None

    def get_user_id(self) -> Optional[int]:
        """获取当前用户 ID

        Returns:
            用户 ID，未登录返回 None
        """
        with self._state_lock:
            if self.current_user:
                return self.current_user.get("id")
            return None

    def get_username(self) -> Optional[str]:
        """获取当前用户名

        Returns:
            用户名，未登录返回 None
        """
        with self._state_lock:
            if self.current_user:
                return self.current_user.get("username")
            return None

    def get_user_info(self) -> Optional[Dict[str, Any]]:
        """获取当前用户信息

        Returns:
            用户信息字典，未登录返回 None
        """
        with self._state_lock:
            return dict(self.current_user) if isinstance(self.current_user, dict) else None

    # ==================== 数据管理快捷方法 ====================

    def add_contact(self, name: str, avatar: str = "👤", status: str = "在线") -> bool:
        """添加联系人

        Args:
            name: 联系人名称
            avatar: 头像
            status: 状态

        Returns:
            是否添加成功
        """
        user_id = self.get_user_id()
        if user_id is None:
            logger.warning("未登录，无法添加联系人")
            return False
        return self.data_manager.add_contact(user_id, name, avatar, status)

    def get_contacts(self):
        """获取联系人列表

        Returns:
            联系人列表
        """
        user_id = self.get_user_id()
        if user_id is None:
            logger.warning("未登录，无法获取联系人")
            return []
        return self.data_manager.get_contacts(user_id)

    def update_contact(self, old_name: str, new_name: str) -> bool:
        """重命名联系人

        Args:
            old_name: 旧名称
            new_name: 新名称

        Returns:
            是否更新成功
        """
        user_id = self.get_user_id()
        if user_id is None:
            logger.warning("未登录，无法更新联系人")
            return False
        return self.data_manager.update_contact(user_id, old_name, new_name)

    def delete_contact(self, name: str) -> bool:
        """删除联系人

        Args:
            name: 联系人名称

        Returns:
            是否删除成功
        """
        user_id = self.get_user_id()
        if user_id is None:
            logger.warning("未登录，无法删除联系人")
            return False
        return self.data_manager.delete_contact(user_id, name)

    def add_message(self, contact_name: str, role: str, content: str) -> bool:
        """添加聊天消息

        Args:
            contact_name: 联系人名称
            role: 角色 (user/assistant/system)
            content: 消息内容

        Returns:
            是否添加成功
        """
        user_id = self.get_user_id()
        if user_id is None:
            logger.warning("未登录，无法添加消息")
            return False
        return self.data_manager.add_message(user_id, contact_name, role, content)

    def get_chat_history(self, contact_name: str, limit: int = 100, offset: int = 0):
        """获取聊天历史 (v2.30.12: 添加分页支持)

        Args:
            contact_name: 联系人名称
            limit: 最多返回的消息数量
            offset: 偏移量（用于分页加载）

        Returns:
            消息列表
        """
        user_id = self.get_user_id()
        if user_id is None:
            logger.warning("未登录，无法获取聊天历史")
            return []
        return self.data_manager.get_chat_history(user_id, contact_name, limit, offset)

    def get_chat_history_page(
        self, contact_name: str, *, limit: int = 100, before_id: int | None = None
    ):
        """按消息 id 进行 keyset pagination 获取聊天历史（推荐）。"""
        user_id = self.get_user_id()
        if user_id is None:
            logger.warning("未登录，无法获取聊天历史")
            return []
        return self.data_manager.get_chat_history_page(
            user_id, contact_name, limit=limit, before_id=before_id
        )

    def get_chat_history_all(self, contact_name: str):
        """获取某联系人完整聊天历史（从旧到新）。"""
        user_id = self.get_user_id()
        if user_id is None:
            logger.warning("未登录，无法获取聊天历史")
            return []
        return self.data_manager.get_chat_history_all(user_id, contact_name)

    def get_chat_history_count(self, contact_name: str) -> int:
        """获取聊天历史总数 (v2.30.12: 新增)

        Args:
            contact_name: 联系人名称

        Returns:
            消息总数
        """
        user_id = self.get_user_id()
        if user_id is None:
            logger.warning("未登录，无法获取聊天历史总数")
            return 0
        return self.data_manager.get_chat_history_count(user_id, contact_name)

    def clear_chat_history(self, contact_name: str) -> bool:
        """清空聊天历史

        Args:
            contact_name: 联系人名称

        Returns:
            是否清空成功
        """
        user_id = self.get_user_id()
        if user_id is None:
            logger.warning("未登录，无法清空聊天历史")
            return False
        return self.data_manager.clear_chat_history(user_id, contact_name)

    def save_settings(self, settings: Dict[str, Any]) -> bool:
        """保存用户设置

        Args:
            settings: 设置字典

        Returns:
            是否保存成功
        """
        user_id = self.get_user_id()
        if user_id is None:
            logger.warning("未登录，无法保存设置")
            return False
        return self.data_manager.save_user_settings(user_id, settings)

    def get_settings(self) -> Optional[Dict[str, Any]]:
        """获取用户设置

        Returns:
            设置字典，如果不存在返回 None
        """
        user_id = self.get_user_id()
        if user_id is None:
            logger.warning("未登录，无法获取设置")
            return None
        return self.data_manager.get_user_settings(user_id)

    def export_data(self, export_dir: str = "data/exports") -> Optional[str]:
        """导出用户数据

        Args:
            export_dir: 导出目录

        Returns:
            导出文件路径，失败返回 None
        """
        user_id = self.get_user_id()
        if user_id is None:
            logger.warning("未登录，无法导出数据")
            return None
        if export_dir == "data/exports":
            try:
                from src.config.settings import settings

                export_dir = str(Path(settings.data_dir) / "exports")
            except Exception:
                pass
        return self.data_manager.export_user_data(user_id, export_dir)

    def import_data(self, filepath: str) -> bool:
        """导入用户数据

        Args:
            filepath: 导入文件路径

        Returns:
            是否导入成功
        """
        user_id = self.get_user_id()
        if user_id is None:
            logger.warning("未登录，无法导入数据")
            return False
        return self.data_manager.import_user_data(user_id, filepath)

    # ==================== 头像管理 - v2.22.0 新增 ====================

    def update_user_avatar(self, avatar: str) -> bool:
        """更新用户头像

        Args:
            avatar: 头像（emoji 或图片路径）

        Returns:
            是否更新成功
        """
        user_id = self.get_user_id()
        if user_id is None:
            logger.warning("未登录，无法更新用户头像")
            return False

        avatar_norm = (avatar or "").strip() or "👤"
        if len(avatar_norm) > 512:
            avatar_norm = avatar_norm[:512]

        success = self._get_auth_db().update_user_avatar(user_id, avatar_norm)

        if success:
            with self._state_lock:
                if self.current_user is not None:
                    self.current_user["user_avatar"] = avatar_norm
            logger.info("用户 %s 的头像已更新", user_id)

        return success

    def update_ai_avatar(self, avatar: str) -> bool:
        """更新AI助手头像

        Args:
            avatar: 头像（emoji 或图片路径）

        Returns:
            是否更新成功
        """
        user_id = self.get_user_id()
        if user_id is None:
            logger.warning("未登录，无法更新AI助手头像")
            return False

        avatar_norm = (avatar or "").strip() or "🐱"
        if len(avatar_norm) > 512:
            avatar_norm = avatar_norm[:512]

        success = self._get_auth_db().update_ai_avatar(user_id, avatar_norm)

        if success:
            with self._state_lock:
                if self.current_user is not None:
                    self.current_user["ai_avatar"] = avatar_norm
            logger.info("用户 %s 的AI助手头像已更新", user_id)

        return success

    def get_user_avatar(self) -> str:
        """获取用户头像

        Returns:
            用户头像（emoji 或图片路径），未登录返回默认值
        """
        with self._state_lock:
            if self.current_user:
                avatar = self.current_user.get("user_avatar")
                if avatar:
                    return avatar

        user_id = self.get_user_id()
        if user_id is None:
            return "👤"

        avatars = self._get_auth_db().get_user_avatars(user_id)

        if avatars:
            with self._state_lock:
                if self.current_user:
                    self.current_user["user_avatar"] = avatars["user_avatar"]
                    self.current_user["ai_avatar"] = avatars["ai_avatar"]
            return avatars["user_avatar"]

        return "👤"

    def get_ai_avatar(self) -> str:
        """获取AI助手头像

        Returns:
            AI助手头像（emoji 或图片路径），未登录返回默认值
        """
        with self._state_lock:
            if self.current_user:
                avatar = self.current_user.get("ai_avatar")
                if avatar:
                    return avatar

        user_id = self.get_user_id()
        if user_id is None:
            return "🐱"

        avatars = self._get_auth_db().get_user_avatars(user_id)

        if avatars:
            with self._state_lock:
                if self.current_user:
                    self.current_user["user_avatar"] = avatars["user_avatar"]
                    self.current_user["ai_avatar"] = avatars["ai_avatar"]
            return avatars["ai_avatar"]

        return "🐱"


# 创建全局单例实例
user_session = UserSession()
