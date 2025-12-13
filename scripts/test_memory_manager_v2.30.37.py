"""
测试记忆管理器修复 v2.30.37

测试内容：
1. 导入记忆管理器
2. 检查 MD3_LIGHT_COLORS 字典
3. 验证修复是否成功
"""

import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.utils.logger import logger

logger.info("=" * 80)
logger.info("测试记忆管理器修复 v2.30.37")
logger.info("=" * 80)

# 测试 1: 检查 MD3_LIGHT_COLORS 字典
logger.info("\n测试 1: 检查 MD3_LIGHT_COLORS 字典")
from src.gui.material_design_light import MD3_LIGHT_COLORS

logger.info(f"✅ MD3_LIGHT_COLORS 导入成功")
logger.info(f"字典包含 {len(MD3_LIGHT_COLORS)} 个键")

# 检查是否有 surface_variant
if 'surface_variant' in MD3_LIGHT_COLORS:
    logger.info(f"✅ surface_variant 存在: {MD3_LIGHT_COLORS['surface_variant']}")
else:
    logger.info(f"⚠️ surface_variant 不存在（这是预期的）")

# 检查是否有 surface_container
if 'surface_container' in MD3_LIGHT_COLORS:
    logger.info(f"✅ surface_container 存在: {MD3_LIGHT_COLORS['surface_container']}")
else:
    logger.error(f"❌ surface_container 不存在")

# 检查是否有 on_surface_variant
if 'on_surface_variant' in MD3_LIGHT_COLORS:
    logger.info(f"✅ on_surface_variant 存在: {MD3_LIGHT_COLORS['on_surface_variant']}")
else:
    logger.error(f"❌ on_surface_variant 不存在")

# 测试 2: 导入记忆管理器
logger.info("\n测试 2: 导入记忆管理器")
try:
    from src.gui.memory_manager import MemoryManagerWidget
    logger.info(f"✅ MemoryManagerWidget 导入成功")
except Exception as e:
    logger.error(f"❌ MemoryManagerWidget 导入失败: {e}")
    sys.exit(1)

# 测试 3: 检查代码中是否还有 surface_variant
logger.info("\n测试 3: 检查代码中是否还有 surface_variant")
memory_manager_file = project_root / "src" / "gui" / "memory_manager.py"
content = memory_manager_file.read_text(encoding="utf-8")

# 统计 surface_variant 出现次数
surface_variant_count = content.count("'surface_variant']")
logger.info(f"'surface_variant'] 出现次数: {surface_variant_count}")

if surface_variant_count == 0:
    logger.info(f"✅ 代码中没有使用 'surface_variant']（已全部修复）")
else:
    logger.warning(f"⚠️ 代码中还有 {surface_variant_count} 处使用 'surface_variant']")

# 统计 on_surface_variant 出现次数（这个是正确的）
on_surface_variant_count = content.count("'on_surface_variant']")
logger.info(f"'on_surface_variant'] 出现次数: {on_surface_variant_count}")

if on_surface_variant_count > 0:
    logger.info(f"✅ 代码中正确使用了 'on_surface_variant']")

logger.info("\n" + "=" * 80)
logger.info("✅ 记忆管理器修复测试完成！")
logger.info("=" * 80)

