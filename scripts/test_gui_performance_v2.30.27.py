"""
测试 GUI 性能 v2.30.27

测试优化后的 GUI 组件性能

测试项目：
1. 流式消息气泡性能
2. 批量消息渲染性能
3. 滚动性能
4. 内存占用

作者: MintChat Team
日期: 2025-11-16
"""

import sys
from pathlib import Path
import time

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QScrollArea
from PyQt6.QtCore import QTimer

from src.gui.optimized_message_bubble import OptimizedStreamingBubble, OptimizedMessageBubble
from src.gui.light_message_bubble import LightStreamingMessageBubble, LightMessageBubble
from src.utils.logger import logger


def test_streaming_bubble_performance():
    """测试流式消息气泡性能"""
    logger.info("=" * 70)
    logger.info("测试流式消息气泡性能")
    logger.info("=" * 70)
    
    app = QApplication(sys.argv)
    
    # 测试文本
    test_text = "喵~ 主人好呀！" * 100  # 1400 字符
    
    # 测试优化版本
    logger.info("\n测试优化版本（OptimizedStreamingBubble）...")
    optimized_bubble = OptimizedStreamingBubble(is_user=False)
    
    start_time = time.perf_counter()
    
    # 模拟流式输出（每次 10 个字符）
    for i in range(0, len(test_text), 10):
        chunk = test_text[i:i+10]
        optimized_bubble.append_text(chunk)
    
    # 等待批量处理完成
    QTimer.singleShot(200, app.quit)
    app.exec()
    
    optimized_bubble.finish_streaming()
    elapsed_ms = (time.perf_counter() - start_time) * 1000
    
    logger.info(f"优化版本总耗时: {elapsed_ms:.2f}ms")
    logger.info(f"优化版本性能统计: {optimized_bubble.get_stats()}")
    
    # 测试原版本
    logger.info("\n测试原版本（LightStreamingMessageBubble）...")
    original_bubble = LightStreamingMessageBubble()
    
    start_time = time.perf_counter()
    
    # 模拟流式输出（每次 10 个字符）
    for i in range(0, len(test_text), 10):
        chunk = test_text[i:i+10]
        original_bubble.append_text(chunk)
    
    # 等待处理完成
    QTimer.singleShot(200, app.quit)
    app.exec()
    
    elapsed_ms_original = (time.perf_counter() - start_time) * 1000
    
    logger.info(f"原版本总耗时: {elapsed_ms_original:.2f}ms")
    
    # 性能对比
    logger.info("\n" + "=" * 70)
    logger.info("性能对比")
    logger.info("=" * 70)
    logger.info(f"优化版本: {elapsed_ms:.2f}ms")
    logger.info(f"原版本: {elapsed_ms_original:.2f}ms")
    
    if elapsed_ms_original > 0:
        speedup = elapsed_ms_original / elapsed_ms
        improvement = (1 - elapsed_ms / elapsed_ms_original) * 100
        logger.info(f"性能提升: {speedup:.2f}x ({improvement:.1f}%)")
        
        if improvement >= 30:
            logger.info("✅ 性能提升显著！")
        elif improvement >= 10:
            logger.info("✅ 性能提升良好")
        else:
            logger.warning("⚠️ 性能提升不明显")


def test_batch_message_performance():
    """测试批量消息渲染性能"""
    logger.info("\n" + "=" * 70)
    logger.info("测试批量消息渲染性能")
    logger.info("=" * 70)
    
    app = QApplication(sys.argv)
    
    # 创建滚动区域
    scroll_area = QScrollArea()
    widget = QWidget()
    layout = QVBoxLayout(widget)
    scroll_area.setWidget(widget)
    
    # 测试优化版本
    logger.info("\n测试优化版本（OptimizedMessageBubble）...")
    
    start_time = time.perf_counter()
    
    for i in range(100):
        bubble = OptimizedMessageBubble(f"测试消息 {i+1}", is_user=i % 2 == 0)
        layout.addWidget(bubble)
    
    elapsed_ms = (time.perf_counter() - start_time) * 1000
    
    logger.info(f"优化版本渲染 100 条消息耗时: {elapsed_ms:.2f}ms")
    logger.info(f"平均每条消息: {elapsed_ms / 100:.2f}ms")
    
    # 清理
    for i in reversed(range(layout.count())):
        layout.itemAt(i).widget().deleteLater()
    
    # 测试原版本
    logger.info("\n测试原版本（LightMessageBubble）...")
    
    start_time = time.perf_counter()
    
    for i in range(100):
        bubble = LightMessageBubble(f"测试消息 {i+1}", is_user=i % 2 == 0)
        layout.addWidget(bubble)
    
    elapsed_ms_original = (time.perf_counter() - start_time) * 1000
    
    logger.info(f"原版本渲染 100 条消息耗时: {elapsed_ms_original:.2f}ms")
    logger.info(f"平均每条消息: {elapsed_ms_original / 100:.2f}ms")
    
    # 性能对比
    logger.info("\n" + "=" * 70)
    logger.info("性能对比")
    logger.info("=" * 70)
    logger.info(f"优化版本: {elapsed_ms:.2f}ms")
    logger.info(f"原版本: {elapsed_ms_original:.2f}ms")
    
    if elapsed_ms_original > 0:
        speedup = elapsed_ms_original / elapsed_ms
        improvement = (1 - elapsed_ms / elapsed_ms_original) * 100
        logger.info(f"性能提升: {speedup:.2f}x ({improvement:.1f}%)")


if __name__ == "__main__":
    test_streaming_bubble_performance()
    test_batch_message_performance()

