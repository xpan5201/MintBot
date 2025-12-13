"""
应用 GUI 优化到现有聊天窗口 v2.30.27

自动集成所有性能优化

作者: MintChat Team
日期: 2025-11-16
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.utils.logger import logger


def apply_optimizations():
    """应用 GUI 优化"""
    logger.info("=" * 70)
    logger.info("应用 GUI 优化到现有聊天窗口")
    logger.info("=" * 70)
    
    # 1. 检查现有文件
    logger.info("\n1. 检查现有文件...")
    
    files_to_check = [
        "src/gui/light_chat_window.py",
        "src/gui/performance_optimizer.py",
        "src/gui/optimized_message_bubble.py",
        "src/gui/chat_window_optimizer.py",
    ]
    
    for file_path in files_to_check:
        full_path = project_root / file_path
        if full_path.exists():
            logger.info(f"✅ {file_path}")
        else:
            logger.error(f"❌ {file_path} 不存在")
            return False
    
    # 2. 备份现有文件
    logger.info("\n2. 备份现有文件...")
    
    import shutil
    from datetime import datetime
    
    backup_dir = project_root / "backups" / f"gui_optimization_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    backup_dir.mkdir(parents=True, exist_ok=True)
    
    for file_path in files_to_check[:1]:  # 只备份主窗口文件
        full_path = project_root / file_path
        if full_path.exists():
            backup_path = backup_dir / Path(file_path).name
            shutil.copy2(full_path, backup_path)
            logger.info(f"✅ 已备份: {file_path} -> {backup_path}")
    
    # 3. 生成集成代码
    logger.info("\n3. 生成集成代码...")
    
    integration_code = '''
# ==================== GUI 性能优化集成 v2.30.27 ====================
# 在 LightChatWindow.__init__() 方法末尾添加以下代码：

from src.gui.chat_window_optimizer import ChatWindowOptimizer

# 初始化性能优化器
self.performance_optimizer = ChatWindowOptimizer(
    scroll_area=self.scroll_area,
    enable_gpu=True,
    enable_memory_management=True,
    max_messages=200,
)

# 应用优化到现有窗口
self.performance_optimizer.optimize_existing_window(self)

logger.info("✅ GUI 性能优化已启用")

# ==================== 集成完成 ====================
'''
    
    integration_file = backup_dir / "integration_code.txt"
    integration_file.write_text(integration_code, encoding='utf-8')
    logger.info(f"✅ 集成代码已生成: {integration_file}")
    
    # 4. 显示集成说明
    logger.info("\n4. 集成说明...")
    logger.info("""
请按照以下步骤手动集成优化：

步骤 1: 打开 src/gui/light_chat_window.py

步骤 2: 在 LightChatWindow.__init__() 方法末尾添加以下代码：

    from src.gui.chat_window_optimizer import ChatWindowOptimizer
    
    # 初始化性能优化器
    self.performance_optimizer = ChatWindowOptimizer(
        scroll_area=self.scroll_area,
        enable_gpu=True,
        enable_memory_management=True,
        max_messages=200,
    )
    
    # 应用优化到现有窗口
    self.performance_optimizer.optimize_existing_window(self)
    
    logger.info("✅ GUI 性能优化已启用")

步骤 3: 保存文件并重启应用

步骤 4: 查看性能统计：
    在聊天窗口中，可以通过以下代码查看性能统计：
    
    stats = self.performance_optimizer.get_stats()
    print(stats)

注意事项：
- 优化会自动启用 GPU 加速
- 优化会自动管理内存（最多保留 200 条消息）
- 优化会批量处理滚动（减少重绘）
- 优化会监控性能（FPS、帧时间等）
""")
    
    # 5. 生成测试脚本
    logger.info("\n5. 生成测试脚本...")
    
    test_code = '''
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
'''
    
    test_file = backup_dir / "test_optimization.py"
    test_file.write_text(test_code, encoding='utf-8')
    logger.info(f"✅ 测试脚本已生成: {test_file}")
    
    # 6. 完成
    logger.info("\n" + "=" * 70)
    logger.info("GUI 优化准备完成！")
    logger.info("=" * 70)
    logger.info(f"\n备份目录: {backup_dir}")
    logger.info(f"集成代码: {integration_file}")
    logger.info(f"测试脚本: {test_file}")
    logger.info("\n请按照上述说明手动集成优化代码。")
    
    return True


if __name__ == "__main__":
    apply_optimizations()

