"""
MintChat 自定义异常类

提供统一的异常处理机制，增强错误信息和调试能力。
"""

from typing import Any, Dict, Optional


class MintChatException(Exception):
    """MintChat 基础异常类"""

    def __init__(
        self,
        message: str,
        error_code: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ):
        """
        初始化异常

        Args:
            message: 错误消息
            error_code: 错误代码
            context: 错误上下文信息
        """
        self.message = message
        self.error_code = error_code or "UNKNOWN_ERROR"
        self.context = context or {}
        super().__init__(self.message)

    def __str__(self) -> str:
        """返回格式化的错误信息"""
        error_str = f"[{self.error_code}] {self.message}"
        if self.context:
            error_str += f" | Context: {self.context}"
        return error_str

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "error_code": self.error_code,
            "message": self.message,
            "context": self.context,
            "type": self.__class__.__name__,
        }


class ConfigurationError(MintChatException):
    """配置错误"""

    def __init__(self, message: str, context: Optional[Dict[str, Any]] = None):
        super().__init__(message, "CONFIG_ERROR", context)


class APIError(MintChatException):
    """API调用错误"""

    def __init__(
        self,
        message: str,
        api_name: Optional[str] = None,
        status_code: Optional[int] = None,
        context: Optional[Dict[str, Any]] = None,
    ):
        ctx = context or {}
        if api_name:
            ctx["api_name"] = api_name
        if status_code:
            ctx["status_code"] = status_code
        super().__init__(message, "API_ERROR", ctx)


class MemoryError(MintChatException):
    """记忆系统错误"""

    def __init__(self, message: str, context: Optional[Dict[str, Any]] = None):
        super().__init__(message, "MEMORY_ERROR", context)


class DatabaseError(MintChatException):
    """数据库错误"""

    def __init__(
        self,
        message: str,
        operation: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ):
        ctx = context or {}
        if operation:
            ctx["operation"] = operation
        super().__init__(message, "DATABASE_ERROR", ctx)


class AuthenticationError(MintChatException):
    """认证错误"""

    def __init__(self, message: str, context: Optional[Dict[str, Any]] = None):
        super().__init__(message, "AUTH_ERROR", context)


class ValidationError(MintChatException):
    """数据验证错误"""

    def __init__(
        self,
        message: str,
        field: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ):
        ctx = context or {}
        if field:
            ctx["field"] = field
        super().__init__(message, "VALIDATION_ERROR", ctx)


class ModelError(MintChatException):
    """模型相关错误"""

    def __init__(
        self,
        message: str,
        model_name: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ):
        ctx = context or {}
        if model_name:
            ctx["model_name"] = model_name
        super().__init__(message, "MODEL_ERROR", ctx)


class ResourceError(MintChatException):
    """资源相关错误（文件、网络等）"""

    def __init__(
        self,
        message: str,
        resource_type: Optional[str] = None,
        resource_path: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ):
        ctx = context or {}
        if resource_type:
            ctx["resource_type"] = resource_type
        if resource_path:
            ctx["resource_path"] = resource_path
        super().__init__(message, "RESOURCE_ERROR", ctx)


class TimeoutError(MintChatException):
    """超时错误"""

    def __init__(
        self,
        message: str,
        timeout_seconds: Optional[float] = None,
        context: Optional[Dict[str, Any]] = None,
    ):
        ctx = context or {}
        if timeout_seconds:
            ctx["timeout_seconds"] = timeout_seconds
        super().__init__(message, "TIMEOUT_ERROR", ctx)


class GUIError(MintChatException):
    """GUI相关错误"""

    def __init__(
        self,
        message: str,
        component: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ):
        ctx = context or {}
        if component:
            ctx["component"] = component
        super().__init__(message, "GUI_ERROR", ctx)


# 错误处理辅助函数


def handle_exception(
    exception: Exception,
    logger: Any,
    user_message: str = "操作失败，请稍后重试",
    log_traceback: bool = True,
) -> str:
    """
    统一的异常处理函数

    Args:
        exception: 异常对象
        logger: 日志记录器
        user_message: 用户友好的错误消息
        log_traceback: 是否记录完整堆栈

    Returns:
        str: 用户友好的错误消息
    """
    if isinstance(exception, MintChatException):
        # 自定义异常，记录详细信息
        logger.error(f"MintChat异常: {exception}")
        if exception.context:
            logger.error(f"错误上下文: {exception.context}")
    else:
        # 其他异常
        logger.error(f"未预期的异常: {type(exception).__name__}: {exception}")

    if log_traceback:
        import traceback

        logger.error(f"完整堆栈:\n{traceback.format_exc()}")

    return user_message


def safe_execute(
    func: callable,
    *args,
    logger: Any = None,
    default_return: Any = None,
    error_message: str = "操作失败",
    **kwargs,
) -> Any:
    """
    安全执行函数，捕获异常并返回默认值

    Args:
        func: 要执行的函数
        *args: 函数参数
        logger: 日志记录器
        default_return: 发生异常时的默认返回值
        error_message: 错误消息
        **kwargs: 函数关键字参数

    Returns:
        函数返回值或默认值
    """
    try:
        return func(*args, **kwargs)
    except Exception as e:
        if logger:
            handle_exception(e, logger, error_message)
        return default_return
