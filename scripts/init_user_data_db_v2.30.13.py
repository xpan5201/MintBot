#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
初始化用户数据库 v2.30.13

确保所有表都正确创建
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.auth.user_data_manager import UserDataManager
from src.utils.logger import logger


def init_database():
    """初始化数据库"""
    print("=" * 80)
    print("🔧 初始化用户数据库 v2.30.13")
    print("=" * 80)
    print()

    try:
        # 创建UserDataManager实例，这会自动初始化数据库
        print("正在初始化数据库...")
        manager = UserDataManager(db_path="data/user_data.db")
        
        print("✅ 数据库初始化完成！")
        print()
        
        # 验证表是否创建成功
        import sqlite3
        db_path = project_root / "data" / "user_data.db"
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = cursor.fetchall()
        
        print(f"📊 数据库中的表 ({len(tables)} 个):")
        for table in tables:
            print(f"  ✅ {table[0]}")
        
        conn.close()
        
        print()
        print("=" * 80)
        print("✅ 初始化完成")
        print("=" * 80)
        
    except Exception as e:
        print(f"❌ 初始化失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    init_database()

