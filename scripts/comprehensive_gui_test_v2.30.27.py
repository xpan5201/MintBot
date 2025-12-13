"""
综合 GUI 性能测试 v2.30.27

测试所有 GUI 优化的实际效果

测试项目：
1. 优化的消息气泡性能
2. 批量消息渲染性能
3. 滚动性能
4. 内存占用
5. 集成优化效果

作者: MintChat Team
日期: 2025-11-16
"""

import sys
from pathlib import Path
import time
import psutil
import os

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer

from src.utils.logger import logger


def get_memory_usage():
    """获取当前进程内存占用（MB）"""
    process = psutil.Process(os.getpid())
    return process.memory_info().rss / 1024 / 1024


def test_optimized_bubbles(app):
    """测试优化的消息气泡"""
    logger.info("=" * 70)
    logger.info("测试 1: 优化的消息气泡性能")
    logger.info("=" * 70)

    from src.gui.optimized_message_bubble import OptimizedStreamingBubble, OptimizedMessageBubble

    # 测试流式消息气泡
    logger.info("\n测试流式消息气泡...")
    bubble = OptimizedStreamingBubble(is_user=False)
    
    start_time = time.perf_counter()
    
    # 模拟流式输出
    test_text = "喵~ 主人好呀！" * 100
    for i in range(0, len(test_text), 10):
        bubble.append_text(test_text[i:i+10])
    
    bubble.finish_streaming()
    elapsed_ms = (time.perf_counter() - start_time) * 1000
    
    stats = bubble.get_stats()
    logger.info(f"流式消息性能: {elapsed_ms:.2f}ms")
    logger.info(f"性能统计: {stats}")
    
    # 测试普通消息气泡
    logger.info("\n测试普通消息气泡...")
    
    start_time = time.perf_counter()
    
    for i in range(100):
        bubble = OptimizedMessageBubble(f"测试消息 {i+1}", is_user=i % 2 == 0)
    
    elapsed_ms = (time.perf_counter() - start_time) * 1000
    
    logger.info(f"批量创建 100 个消息气泡: {elapsed_ms:.2f}ms")
    logger.info(f"平均每个: {elapsed_ms / 100:.2f}ms")


def test_integrated_optimization(app):
    """测试集成优化效果"""
    logger.info("\n" + "=" * 70)
    logger.info("测试 2: 集成优化效果")
    logger.info("=" * 70)
    
    try:
        from src.gui.light_chat_window import LightChatWindow
        
        logger.info("\n创建聊天窗口...")
        start_mem = get_memory_usage()
        start_time = time.perf_counter()
        
        window = LightChatWindow()
        
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        logger.info(f"窗口创建耗时: {elapsed_ms:.2f}ms")
        
        # 检查优化是否启用
        if hasattr(window, 'performance_optimizer'):
            logger.info("✅ 性能优化已启用")
            
            # 添加测试消息
            logger.info("\n添加 50 条测试消息...")
            start_time = time.perf_counter()
            
            for i in range(50):
                window._add_message(
                    f"测试消息 {i+1}: 喵~ 主人好呀！这是一条测试消息。",
                    is_user=i % 2 == 0,
                    save_to_db=False,
                    with_animation=False,
                )
            
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            logger.info(f"添加 50 条消息耗时: {elapsed_ms:.2f}ms")
            logger.info(f"平均每条: {elapsed_ms / 50:.2f}ms")
            
            # 获取性能统计
            stats = window.performance_optimizer.get_stats()
            logger.info(f"\n性能统计:")
            for key, value in stats.items():
                logger.info(f"  {key}: {value}")
            
            # 内存占用
            current_mem = get_memory_usage()
            logger.info(f"\n内存占用:")
            logger.info(f"  初始: {start_mem:.2f} MB")
            logger.info(f"  当前: {current_mem:.2f} MB")
            logger.info(f"  增加: {current_mem - start_mem:.2f} MB")
            
        else:
            logger.error("❌ 性能优化未启用")
        
        # 显示窗口（可选）
        # window.show()
        # sys.exit(app.exec())
        
    except Exception as e:
        logger.error(f"测试失败: {e}", exc_info=True)


def test_performance_tools():
    """测试性能优化工具"""
    logger.info("\n" + "=" * 70)
    logger.info("测试 3: 性能优化工具")
    logger.info("=" * 70)
    
    from src.gui.performance_optimizer import (
        BatchRenderer,
        MemoryManager,
        PerformanceMonitor,
    )
    
    # 测试批量渲染器
    logger.info("\n测试批量渲染器...")
    renderer = BatchRenderer(interval_ms=16)
    
    call_count = 0
    
    def test_callback():
        nonlocal call_count
        call_count += 1
    
    start_time = time.perf_counter()
    
    # 调度 100 次更新
    for i in range(100):
        renderer.schedule_update(test_callback)
    
    # 等待批量处理完成
    time.sleep(0.1)
    
    elapsed_ms = (time.perf_counter() - start_time) * 1000
    
    logger.info(f"调度 100 次更新耗时: {elapsed_ms:.2f}ms")
    logger.info(f"实际执行次数: {call_count}")
    logger.info(f"批量优化率: {(1 - call_count / 100) * 100:.1f}%")
    
    # 测试性能监控器
    logger.info("\n测试性能监控器...")
    monitor = PerformanceMonitor()
    
    # 记录一些帧时间
    for i in range(60):
        monitor.record_frame(16.67)  # 60fps
    
    stats = monitor.get_stats()
    logger.info(f"性能统计: {stats}")


def main():
    """主函数"""
    logger.info("开始综合 GUI 性能测试...")
    logger.info(f"Python 版本: {sys.version}")
    logger.info(f"项目路径: {project_root}")

    # 创建 QApplication
    app = QApplication(sys.argv)

    # 运行所有测试
    test_optimized_bubbles(app)
    test_performance_tools()
    test_integrated_optimization(app)

    logger.info("\n" + "=" * 70)
    logger.info("所有测试完成！")
    logger.info("=" * 70)


if __name__ == "__main__":
    main()

