"""
MintChat 版本管理模块

统一管理项目版本号，确保版本一致性。
"""

__version__ = "2.60.6"
__version_info__ = (2, 60, 6)

# 版本历史（仅保留最近5个版本的详细信息，完整历史见docs/CHANGELOG.md）
VERSION_HISTORY = {
    "2.60.6": {
        "date": "2025-11-21",
        "changes": [
            (
                "🧠 Agent 主系统再升级：引入 `AgentConversationBundle` "
                "统一 chat/chat_stream/chat_stream_async 的上下文构建，"
                "图片描述/来源、角色状态与压缩策略一次成型"
            ),
            (
                "🛡️ LLM failover 与看门狗：`_invoke_with_failover()` 自动触发压缩上下文重试，"
                "`_stream_llm_response()` / `_astream_llm_response()` 共享 `LLMStreamWatchdog`，"
                "首包/总耗时都有日志"
            ),
            (
                "🧰 Context7 工具中间件链：重新挂载 "
                "LLMToolSelector / ContextEditing / ToolLimit / PermissionScoped，"
                "让工具筛选、历史裁剪与权限控制全自动"
            ),
            (
                "📚 记忆检索与日志修复：ConcurrentMemoryRetriever 恢复 per-source 熔断与 EMA 动态超时，"
                "新增 `_LegacyLoggerAdapter` 兼容 `%s`/`%.0f` 日志写法避免占位符泄露"
            ),
        ],
    },
    "2.60.5": {
        "date": "2025-11-21",
        "changes": [
            "🤖 LLM 看门狗回归：恢复 `_invoke_agent_with_timeout()`、线程池与阶段耗时记录，超时即时降级并提醒用户",
            "🌊 流式/异步流式防护：`LLMStreamWatchdog` 统一首包/空闲/总时长控制，queue + wait_for 确保不会无限卡顿",
            "🧠 上下文压缩升级：`_prepare_messages_async()` 重新启用历史摘要窗口，历史要点与状态/记忆上下文一次性拼接",
            (
                "📚 记忆检索与日志修复：ConcurrentMemoryRetriever 恢复 per-source 超时与 `last_latency_ms`，"
                "移除 loguru `isEnabledFor` 调用"
            ),
        ],
    },
    "2.60.4": {
        "date": "2025-11-21",
        "changes": [
            "⚡ TTS性能优化：减少日志噪音，仅在严重超时（超过阈值2倍）时记录警告，成功日志改为debug级别",
            "🎯 TTS预取优化：改进预取策略，仅预取前3个句子以减少资源消耗，优化错误处理减少日志噪音",
            "🚀 记忆检索优化：使用MD5哈希优化缓存键生成，减少内存占用，仅在debug模式下记录详细日志",
            "🧹 代码精简：清理冗余版本号注释，优化上下文构建逻辑，提升代码可读性和执行效率",
        ],
    },
    "2.60.3": {
        "date": "2025-11-21",
        "changes": [
            "🐛 修复TTS错误处理：改进异常信息记录，确保错误类型和详情正确输出，解决空错误日志问题",
            "⚡ Agent核心系统优化：使用frozenset优化关键词匹配，使用字典推导式优化记忆检索计划构建",
            "🎯 核心记忆提取优化：使用类级常量缓存关键词集合，使用any()和生成器表达式提升匹配性能",
            "🧹 代码精简：优化字符串拼接和上下文构建，减少内存分配和提升执行效率",
        ],
    },
    "2.60.2": {
        "date": "2025-11-21",
        "changes": [
            (
                "🐛 修复TTS客户端关闭错误：synthesize方法中检测客户端关闭状态并自动重建，"
                "彻底解决'Cannot send a request, as the client has been closed'报错"
            ),
            "🎯 TTS预取任务错误处理优化：优雅处理客户端关闭和事件循环异常，避免后台任务崩溃",
            "⚡ Agent系统性能优化：精简代码逻辑，提升响应速度和稳定性",
        ],
    },
}


def get_version() -> str:
    """获取当前版本号"""
    return __version__


def get_version_info() -> tuple:
    """获取版本信息元组"""
    return __version_info__


def get_version_string() -> str:
    """获取完整版本字符串"""
    return f"MintChat v{__version__}"


def get_version_history(version: str | None = None) -> dict:
    """
    获取版本历史

    Args:
        version: 指定版本号，如果为None则返回所有历史

    Returns:
        版本历史字典
    """
    if version:
        return VERSION_HISTORY.get(version, {})
    return VERSION_HISTORY


def print_version_info():
    """打印版本信息"""
    from src.utils.logger import logger

    logger.info("=" * 70)
    logger.info(f"  {get_version_string()} - 多模态猫娘女仆智能体")
    logger.info("  Material Design 3 浅色主题 GUI (性能优化版)")
    logger.info("=" * 70)
    logger.info("")

    # 打印最新版本更新内容
    latest_version = __version__
    if latest_version in VERSION_HISTORY:
        info = VERSION_HISTORY[latest_version]
        logger.info(f"📅 版本日期: {info['date']}")
        logger.info("✨ 更新内容:")
        for change in info["changes"]:
            logger.info(f"   - {change}")
        logger.info("")


if __name__ == "__main__":
    # 测试版本信息
    from src.utils.logger import logger

    print_version_info()
    logger.info(f"版本号: {get_version()}")
    logger.info(f"版本元组: {get_version_info()}")
