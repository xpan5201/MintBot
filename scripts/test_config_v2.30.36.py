"""
测试智能日记系统配置 v2.30.36
"""

import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.config.settings import settings
from src.utils.logger import logger

logger.info("=" * 80)
logger.info("测试智能日记系统配置 v2.30.36")
logger.info("=" * 80)

# 测试配置是否正确加载
logger.info("\n配置测试:")
logger.info(f"✅ smart_diary_enabled: {getattr(settings.agent, 'smart_diary_enabled', True)}")
logger.info(f"✅ diary_importance_threshold: {getattr(settings.agent, 'diary_importance_threshold', 0.6)}")
logger.info(f"✅ daily_summary_enabled: {getattr(settings.agent, 'daily_summary_enabled', True)}")

# 测试 DiaryMemory 是否正确初始化
from src.agent.advanced_memory import DiaryMemory

test_dir = project_root / "data" / "test_config"
diary = DiaryMemory(persist_directory=str(test_dir))

logger.info("\nDiaryMemory 初始化测试:")
logger.info(f"✅ smart_diary_enabled: {diary.smart_diary_enabled}")
logger.info(f"✅ diary_importance_threshold: {diary.diary_importance_threshold}")
logger.info(f"✅ daily_summary_enabled: {diary.daily_summary_enabled}")

logger.info("\n" + "=" * 80)
logger.info("✅ 智能日记系统配置测试完成！")
logger.info("=" * 80)

