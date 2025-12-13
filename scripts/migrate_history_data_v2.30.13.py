#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
迁移历史消息数据 v2.30.13

从 data/users.db 迁移到 data/user_data.db
"""

import sqlite3
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def migrate_history_data():
    """迁移历史消息数据"""
    print("=" * 80)
    print("🔄 迁移历史消息数据 v2.30.13")
    print("=" * 80)
    print()

    old_db_path = project_root / "data" / "users.db"
    new_db_path = project_root / "data" / "user_data.db"

    print(f"源数据库: {old_db_path}")
    print(f"目标数据库: {new_db_path}")
    print()

    if not old_db_path.exists():
        print("⚠️ 源数据库不存在，无需迁移")
        return

    if not new_db_path.exists():
        print("❌ 目标数据库不存在，请先初始化")
        return

    try:
        # 连接到两个数据库
        old_conn = sqlite3.connect(str(old_db_path))
        new_conn = sqlite3.connect(str(new_db_path))

        old_cursor = old_conn.cursor()
        new_cursor = new_conn.cursor()

        # 检查源数据库是否有chat_history表
        old_cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='chat_history'")
        if not old_cursor.fetchone():
            print("⚠️ 源数据库中没有 chat_history 表，无需迁移")
            old_conn.close()
            new_conn.close()
            return

        # 检查源数据库中的消息数量
        old_cursor.execute("SELECT COUNT(*) FROM chat_history")
        old_count = old_cursor.fetchone()[0]
        print(f"源数据库中的消息数: {old_count}")

        if old_count == 0:
            print("⚠️ 源数据库中没有消息，无需迁移")
            old_conn.close()
            new_conn.close()
            return

        # 检查目标数据库中的消息数量
        new_cursor.execute("SELECT COUNT(*) FROM chat_history")
        new_count = new_cursor.fetchone()[0]
        print(f"目标数据库中的消息数: {new_count}")
        print()

        # 自动迁移（不询问）
        print("⚠️ 警告：此操作将把源数据库中的所有消息复制到目标数据库")
        print("✅ 自动开始迁移...")
        print()

        # 读取所有消息
        old_cursor.execute("""
            SELECT user_id, contact_name, role, content, timestamp
            FROM chat_history
            ORDER BY timestamp ASC
        """)
        messages = old_cursor.fetchall()

        # 插入到新数据库
        migrated_count = 0
        for msg in messages:
            try:
                new_cursor.execute("""
                    INSERT INTO chat_history (user_id, contact_name, role, content, timestamp)
                    VALUES (?, ?, ?, ?, ?)
                """, msg)
                migrated_count += 1
            except sqlite3.IntegrityError as e:
                print(f"⚠️ 跳过重复消息: {e}")

        new_conn.commit()

        print(f"✅ 成功迁移 {migrated_count}/{old_count} 条消息")
        print()

        # 验证迁移结果
        new_cursor.execute("SELECT COUNT(*) FROM chat_history")
        final_count = new_cursor.fetchone()[0]
        print(f"迁移后目标数据库中的消息数: {final_count}")

        old_conn.close()
        new_conn.close()

        print()
        print("=" * 80)
        print("✅ 迁移完成")
        print("=" * 80)

    except Exception as e:
        print(f"❌ 迁移失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    migrate_history_data()

