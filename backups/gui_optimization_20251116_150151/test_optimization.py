
"""
测试 GUI 优化效果 v2.30.27
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from PyQt6.QtWidgets import QApplication
from src.gui.light_chat_window import LightChatWindow
from src.utils.logger import logger

def test_optimization():
    """测试优化效果"""
    app = QApplication(sys.argv)
    
    # 创建聊天窗口
    window = LightChatWindow()
    
    # 检查优化是否启用
    if hasattr(window, 'performance_optimizer'):
        logger.info("✅ 性能优化已启用")
        
        # 添加测试消息
        for i in range(50):
            window._add_message(f"测试消息 {i+1}", is_user=i % 2 == 0)
        
        # 获取性能统计
        stats = window.performance_optimizer.get_stats()
        logger.info(f"性能统计: {stats}")
    else:
        logger.error("❌ 性能优化未启用")
    
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    test_optimization()
