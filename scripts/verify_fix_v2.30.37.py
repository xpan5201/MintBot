"""
验证修复 v2.30.37

检查 memory_manager.py 中是否还有 surface_variant 错误
"""

import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.utils.logger import logger

logger.info("=" * 80)
logger.info("验证修复 v2.30.37")
logger.info("=" * 80)

# 检查代码中是否还有 surface_variant
logger.info("\n检查 memory_manager.py 中的 surface_variant 使用情况:")
memory_manager_file = project_root / "src" / "gui" / "memory_manager.py"
content = memory_manager_file.read_text(encoding="utf-8")

# 统计 surface_variant 出现次数（作为字典键）
surface_variant_as_key_count = content.count("['surface_variant']")
logger.info(f"['surface_variant'] 出现次数: {surface_variant_as_key_count}")

if surface_variant_as_key_count == 0:
    logger.info(f"✅ 代码中没有使用 ['surface_variant']（已全部修复）")
else:
    logger.error(f"❌ 代码中还有 {surface_variant_as_key_count} 处使用 ['surface_variant']")

# 统计 on_surface_variant 出现次数（这个是正确的）
on_surface_variant_count = content.count("['on_surface_variant']")
logger.info(f"['on_surface_variant'] 出现次数: {on_surface_variant_count}")

if on_surface_variant_count > 0:
    logger.info(f"✅ 代码中正确使用了 ['on_surface_variant'] ({on_surface_variant_count} 处)")

# 统计 surface_container 出现次数
surface_container_count = content.count("['surface_container']")
logger.info(f"['surface_container'] 出现次数: {surface_container_count}")

if surface_container_count > 0:
    logger.info(f"✅ 代码中正确使用了 ['surface_container'] ({surface_container_count} 处)")

# 检查 MD3_LIGHT_COLORS 字典
logger.info("\n检查 MD3_LIGHT_COLORS 字典:")
from src.gui.material_design_light import MD3_LIGHT_COLORS

if 'surface_variant' in MD3_LIGHT_COLORS:
    logger.error(f"❌ surface_variant 存在于字典中（不应该存在）")
else:
    logger.info(f"✅ surface_variant 不存在于字典中（正确）")

if 'surface_container' in MD3_LIGHT_COLORS:
    logger.info(f"✅ surface_container 存在于字典中: {MD3_LIGHT_COLORS['surface_container']}")
else:
    logger.error(f"❌ surface_container 不存在于字典中")

if 'on_surface_variant' in MD3_LIGHT_COLORS:
    logger.info(f"✅ on_surface_variant 存在于字典中: {MD3_LIGHT_COLORS['on_surface_variant']}")
else:
    logger.error(f"❌ on_surface_variant 不存在于字典中")

logger.info("\n" + "=" * 80)
logger.info("✅ 修复验证完成！")
logger.info("=" * 80)
logger.info("\n总结:")
logger.info(f"- ['surface_variant'] 使用次数: {surface_variant_as_key_count} (应该为 0)")
logger.info(f"- ['on_surface_variant'] 使用次数: {on_surface_variant_count} (正确)")
logger.info(f"- ['surface_container'] 使用次数: {surface_container_count} (正确)")
logger.info(f"\n修复状态: {'✅ 成功' if surface_variant_as_key_count == 0 else '❌ 失败'}")

