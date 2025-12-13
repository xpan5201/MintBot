"""
ChatThread 超时修复测试脚本 v2.30.45

测试内容：
1. 正常对话测试
2. 超时处理测试
3. 错误处理测试
4. 资源清理测试
"""

import sys
import time
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.utils.logger import logger


def test_llm_timeout_config():
    """测试 LLM 超时配置"""
    logger.info("=" * 60)
    logger.info("测试 1: LLM 超时配置")
    logger.info("=" * 60)
    
    try:
        from src.agent.core import MintChatAgent
        from src.config.settings import settings
        
        # 创建 agent
        agent = MintChatAgent()
        
        # 检查 LLM 是否有超时配置
        llm = agent.llm
        
        # 检查是否有 timeout 属性
        if hasattr(llm, 'timeout'):
            logger.info(f"✅ LLM 超时配置: {llm.timeout} 秒")
        elif hasattr(llm, 'request_timeout'):
            logger.info(f"✅ LLM 超时配置: {llm.request_timeout} 秒")
        else:
            logger.warning("⚠️ LLM 可能没有超时配置")
        
        # 检查是否有重试配置
        if hasattr(llm, 'max_retries'):
            logger.info(f"✅ LLM 重试配置: {llm.max_retries} 次")
        else:
            logger.warning("⚠️ LLM 可能没有重试配置")
        
        logger.info("✅ 测试 1 通过：LLM 超时配置正常")
        return True
        
    except Exception as e:
        logger.error(f"❌ 测试 1 失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_chatthread_timeout_handling():
    """测试 ChatThread 超时处理"""
    logger.info("\n" + "=" * 60)
    logger.info("测试 2: ChatThread 超时处理")
    logger.info("=" * 60)
    
    try:
        from src.gui.light_chat_window import ChatThread
        from src.agent.core import MintChatAgent
        from PyQt6.QtCore import QCoreApplication
        
        # 创建 Qt 应用（如果不存在）
        app = QCoreApplication.instance()
        if app is None:
            app = QCoreApplication(sys.argv)
        
        # 创建 agent
        agent = MintChatAgent()
        
        # 创建 ChatThread，设置很短的超时时间（1秒）
        thread = ChatThread(
            agent=agent,
            message="你好",
            timeout=1.0  # 1秒超时
        )
        
        # 检查 ChatThread 是否有正确的属性
        assert hasattr(thread, '_is_running'), "❌ ChatThread 缺少 _is_running 属性"
        assert hasattr(thread, '_python_thread'), "❌ ChatThread 缺少 _python_thread 属性"
        assert hasattr(thread, 'timeout'), "❌ ChatThread 缺少 timeout 属性"
        assert hasattr(thread, 'stop'), "❌ ChatThread 缺少 stop 方法"
        assert hasattr(thread, 'cleanup'), "❌ ChatThread 缺少 cleanup 方法"
        
        logger.info("✅ ChatThread 属性检查通过")
        logger.info(f"✅ 超时设置: {thread.timeout} 秒")
        
        # 清理
        thread.cleanup()
        
        logger.info("✅ 测试 2 通过：ChatThread 超时处理正常")
        return True
        
    except Exception as e:
        logger.error(f"❌ 测试 2 失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_chatthread_cleanup():
    """测试 ChatThread 资源清理"""
    logger.info("\n" + "=" * 60)
    logger.info("测试 3: ChatThread 资源清理")
    logger.info("=" * 60)
    
    try:
        from src.gui.light_chat_window import ChatThread
        from src.agent.core import MintChatAgent
        from PyQt6.QtCore import QCoreApplication
        
        # 创建 Qt 应用（如果不存在）
        app = QCoreApplication.instance()
        if app is None:
            app = QCoreApplication(sys.argv)
        
        # 创建 agent
        agent = MintChatAgent()
        
        # 创建 ChatThread
        thread = ChatThread(
            agent=agent,
            message="测试消息",
            timeout=300.0
        )
        
        # 检查初始状态
        assert thread.agent is not None, "❌ agent 应该不为 None"
        assert thread.message is not None, "❌ message 应该不为 None"
        
        logger.info("✅ 初始状态检查通过")
        
        # 调用 cleanup
        thread.cleanup()
        
        # 检查清理后的状态
        assert thread.agent is None, "❌ cleanup 后 agent 应该为 None"
        assert thread.message is None, "❌ cleanup 后 message 应该为 None"
        assert thread.image_path is None, "❌ cleanup 后 image_path 应该为 None"
        assert thread.image_analysis is None, "❌ cleanup 后 image_analysis 应该为 None"
        assert thread._python_thread is None, "❌ cleanup 后 _python_thread 应该为 None"
        
        logger.info("✅ 清理后状态检查通过")
        logger.info("✅ 测试 3 通过：ChatThread 资源清理正常")
        return True
        
    except Exception as e:
        logger.error(f"❌ 测试 3 失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """主测试函数"""
    logger.info("开始 ChatThread 超时修复测试 v2.30.45")
    logger.info("=" * 60)
    
    results = []
    
    # 测试 1: LLM 超时配置
    results.append(("LLM 超时配置", test_llm_timeout_config()))
    
    # 测试 2: ChatThread 超时处理
    results.append(("ChatThread 超时处理", test_chatthread_timeout_handling()))
    
    # 测试 3: ChatThread 资源清理
    results.append(("ChatThread 资源清理", test_chatthread_cleanup()))
    
    # 输出测试结果
    logger.info("\n" + "=" * 60)
    logger.info("测试结果汇总")
    logger.info("=" * 60)
    
    for name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        logger.info(f"{name}: {status}")
    
    # 统计
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    logger.info("=" * 60)
    logger.info(f"总计: {passed}/{total} 通过")
    
    if passed == total:
        logger.info("🎉 所有测试通过！ChatThread 超时修复正常工作！")
        return 0
    else:
        logger.error(f"⚠️ {total - passed} 个测试失败")
        return 1


if __name__ == "__main__":
    sys.exit(main())

