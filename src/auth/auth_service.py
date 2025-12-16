"""
用户认证服务

提供高级认证功能，包括输入验证、错误处理等
"""

import re
from typing import Optional, Dict, Any, Tuple
from .database import UserDatabase


class AuthService:
    """用户认证服务类"""

    def __init__(self, db_path: str = "data/users.db", use_prepared: bool = True):
        """初始化认证服务

        Args:
            db_path: 数据库文件路径
            use_prepared: 是否使用预编译语句（提升30-50%性能）
        """
        self.db = UserDatabase(db_path, use_prepared=use_prepared)
        self.current_user = None
        self.current_session = None

    def validate_username(self, username: str) -> Tuple[bool, str]:
        """验证用户名格式

        Args:
            username: 用户名

        Returns:
            (是否有效, 错误信息)
        """
        if not username:
            return False, "用户名不能为空"

        if len(username) < 3:
            return False, "用户名至少需要 3 个字符"

        if len(username) > 20:
            return False, "用户名最多 20 个字符"

        if not re.match(r'^[a-zA-Z0-9_\u4e00-\u9fa5]+$', username):
            return False, "用户名只能包含字母、数字、下划线和中文"

        return True, ""

    def validate_email(self, email: str) -> Tuple[bool, str]:
        """验证邮箱格式

        Args:
            email: 邮箱

        Returns:
            (是否有效, 错误信息)
        """
        if not email:
            return False, "邮箱不能为空"

        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_pattern, email):
            return False, "邮箱格式不正确"

        return True, ""

    def validate_password(self, password: str) -> Tuple[bool, str]:
        """验证密码强度

        Args:
            password: 密码

        Returns:
            (是否有效, 错误信息)
        """
        if not password:
            return False, "密码不能为空"

        if len(password) < 6:
            return False, "密码至少需要 6 个字符"

        if len(password) > 50:
            return False, "密码最多 50 个字符"

        # 检查密码强度（至少包含字母和数字）
        has_letter = bool(re.search(r'[a-zA-Z]', password))
        has_digit = bool(re.search(r'\d', password))

        if not (has_letter and has_digit):
            return False, "密码必须包含字母和数字"

        return True, ""

    def register(self, username: str, email: str, password: str,
                  confirm_password: str) -> Tuple[bool, str]:
        """注册新用户

        Args:
            username: 用户名
            email: 邮箱
            password: 密码
            confirm_password: 确认密码

        Returns:
            (是否成功, 消息)
        """
        # 验证用户名
        valid, msg = self.validate_username(username)
        if not valid:
            return False, msg

        # 验证邮箱
        valid, msg = self.validate_email(email)
        if not valid:
            return False, msg

        # 验证密码
        valid, msg = self.validate_password(password)
        if not valid:
            return False, msg

        # 检查密码确认
        if password != confirm_password:
            return False, "两次输入的密码不一致"

        # 创建用户
        user_id = self.db.create_user(username, email, password)

        if user_id is None:
            return False, "用户名或邮箱已存在"

        return True, "注册成功！"

    def login(self, username: str, password: str,
               remember_me: bool = False) -> Tuple[bool, str]:
        """用户登录

        Args:
            username: 用户名或邮箱
            password: 密码
            remember_me: 是否记住登录状态

        Returns:
            (是否成功, 消息)
        """
        if not username:
            return False, "请输入用户名或邮箱"

        if not password:
            return False, "请输入密码"

        # 验证用户
        user = self.db.verify_user(username, password)

        if user is None:
            return False, "用户名或密码错误"

        # 创建会话
        expires_in_days = 30 if remember_me else 1
        session_token = self.db.create_session(user['id'], expires_in_days)

        # 保存当前用户和会话
        self.current_user = user
        self.current_session = session_token

        return True, "登录成功！"

    def logout(self):
        """用户登出"""
        if self.current_session:
            self.db.invalidate_session(self.current_session)

        self.current_user = None
        self.current_session = None

    def change_password(self, old_password: str, new_password: str,
                       confirm_password: str) -> Tuple[bool, str]:
        """修改密码

        Args:
            old_password: 旧密码
            new_password: 新密码
            confirm_password: 确认新密码

        Returns:
            (是否成功, 消息)
        """
        if not self.current_user:
            return False, "请先登录"

        if not old_password:
            return False, "请输入旧密码"

        # 验证新密码
        valid, msg = self.validate_password(new_password)
        if not valid:
            return False, msg

        # 检查密码确认
        if new_password != confirm_password:
            return False, "两次输入的新密码不一致"

        # 检查新旧密码是否相同
        if old_password == new_password:
            return False, "新密码不能与旧密码相同"

        # 修改密码
        success = self.db.change_password(
            self.current_user['id'],
            old_password,
            new_password
        )

        if not success:
            return False, "旧密码错误"

        return True, "密码修改成功！"

    def reset_password(
        self, username: str, email: str, new_password: str, confirm_password: str
    ) -> Tuple[bool, str]:
        """重置密码（通过用户名+邮箱匹配，不需要旧密码）

        Args:
            username: 用户名
            email: 邮箱（必须与用户名匹配）
            new_password: 新密码
            confirm_password: 确认新密码

        Returns:
            (是否成功, 消息)
        """
        if not username:
            return False, "请输入用户名"

        # 验证邮箱
        valid, msg = self.validate_email(email)
        if not valid:
            return False, msg

        # 验证新密码
        valid, msg = self.validate_password(new_password)
        if not valid:
            return False, msg

        # 检查密码确认
        if new_password != confirm_password:
            return False, "两次输入的新密码不一致"

        # 重置密码
        success = self.db.reset_password(username, email, new_password)

        if not success:
            return False, "用户名或邮箱不匹配"

        return True, "密码重置成功！"

    def restore_session(self, session_token: str) -> bool:
        """恢复会话

        Args:
            session_token: 会话令牌

        Returns:
            是否成功
        """
        user = self.db.verify_session(session_token)

        if user is None:
            return False

        self.current_user = user
        self.current_session = session_token

        return True

    def is_logged_in(self) -> bool:
        """检查是否已登录

        Returns:
            是否已登录
        """
        return self.current_user is not None

    def get_current_user(self) -> Optional[Dict[str, Any]]:
        """获取当前用户信息

        Returns:
            用户信息字典
        """
        return self.current_user
