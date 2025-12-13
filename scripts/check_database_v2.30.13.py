#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据库检查和修复工具 v2.30.13
"""

import sqlite3
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def check_and_fix_database():
    """检查并修复数据库"""
    print("=" * 80)
    print("🔍 数据库检查和修复工具 v2.30.13")
    print("=" * 80)
    print()

    # 查找数据库文件
    db_path = project_root / "data" / "user_data.db"
    print(f"数据库路径: {db_path}")
    print(f"数据库存在: {db_path.exists()}")
    print()

    if not db_path.exists():
        print("⚠️ 数据库文件不存在，尝试创建...")
        db_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        # 检查所有表
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = cursor.fetchall()
        
        print(f"📊 数据库中的表 ({len(tables)} 个):")
        for table in tables:
            print(f"  - {table[0]}")
            
            # 检查表结构
            cursor.execute(f"PRAGMA table_info({table[0]})")
            columns = cursor.fetchall()
            print(f"    列数: {len(columns)}")
            for col in columns:
                print(f"      {col[1]} ({col[2]})")
            
            # 检查记录数
            cursor.execute(f"SELECT COUNT(*) FROM {table[0]}")
            count = cursor.fetchone()[0]
            print(f"    记录数: {count}")
            print()

        # 检查是否缺少chat_history表
        table_names = [t[0] for t in tables]
        if 'chat_history' not in table_names:
            print("❌ 缺少 chat_history 表！")
            print("🔧 正在创建 chat_history 表...")
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS chat_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    contact_name TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (id)
                )
            """)
            
            # 创建索引
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_chat_history_user_contact 
                ON chat_history(user_id, contact_name, timestamp DESC)
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_chat_history_timestamp 
                ON chat_history(timestamp DESC)
            """)
            
            conn.commit()
            print("✅ chat_history 表创建成功！")
        else:
            print("✅ chat_history 表存在")

        # 检查索引
        print("\n📊 数据库索引:")
        cursor.execute("SELECT name, tbl_name FROM sqlite_master WHERE type='index'")
        indexes = cursor.fetchall()
        for idx_name, tbl_name in indexes:
            print(f"  - {idx_name} (表: {tbl_name})")
        print()

        conn.close()

        print("=" * 80)
        print("✅ 数据库检查完成")
        print("=" * 80)

    except Exception as e:
        print(f"❌ 检查失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    check_and_fix_database()

