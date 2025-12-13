#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
历史消息问题诊断工具 v2.30.13

诊断项目：
1. 检查数据库中的消息数量
2. 检查是否有重复消息
3. 检查消息的时间戳顺序
4. 检查分页加载逻辑
5. 检查去重逻辑
"""

import sqlite3
import sys
from pathlib import Path
from datetime import datetime

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.utils.logger import logger


def diagnose_history_issues():
    """诊断历史消息问题"""
    print("=" * 80)
    print("🔍 历史消息问题诊断工具 v2.30.13")
    print("=" * 80)
    print()

    # 查找数据库文件
    db_path = project_root / "data" / "user_data.db"
    if not db_path.exists():
        print(f"❌ 数据库文件不存在: {db_path}")
        return

    print(f"✅ 数据库文件: {db_path}")
    print()

    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        # 1. 检查消息总数
        print("📊 1. 消息统计")
        print("-" * 80)
        cursor.execute("SELECT COUNT(*) FROM chat_history")
        total_count = cursor.fetchone()[0]
        print(f"总消息数: {total_count}")

        # 按联系人统计
        cursor.execute("""
            SELECT contact_name, COUNT(*) as count
            FROM chat_history
            GROUP BY contact_name
            ORDER BY count DESC
        """)
        contacts = cursor.fetchall()
        print(f"\n按联系人统计:")
        for contact, count in contacts:
            print(f"  - {contact}: {count} 条消息")
        print()

        # 2. 检查重复消息
        print("📊 2. 重复消息检查")
        print("-" * 80)
        cursor.execute("""
            SELECT role, content, timestamp, COUNT(*) as count
            FROM chat_history
            GROUP BY role, content, timestamp
            HAVING count > 1
            ORDER BY count DESC
            LIMIT 10
        """)
        duplicates = cursor.fetchall()
        if duplicates:
            print(f"⚠️ 发现 {len(duplicates)} 组重复消息:")
            for role, content, timestamp, count in duplicates:
                content_preview = content[:50] + "..." if len(content) > 50 else content
                print(f"  - [{role}] {content_preview} (重复{count}次, 时间:{timestamp})")
        else:
            print("✅ 没有发现重复消息")
        print()

        # 3. 检查时间戳顺序
        print("📊 3. 时间戳顺序检查")
        print("-" * 80)
        for contact, _ in contacts[:3]:  # 只检查前3个联系人
            cursor.execute("""
                SELECT id, role, content, timestamp
                FROM chat_history
                WHERE contact_name = ?
                ORDER BY timestamp DESC
                LIMIT 10
            """, (contact,))
            messages = cursor.fetchall()
            
            print(f"\n联系人: {contact} (最近10条消息)")
            prev_timestamp = None
            order_correct = True
            for msg_id, role, content, timestamp in messages:
                content_preview = content[:30] + "..." if len(content) > 30 else content
                dt = datetime.fromisoformat(timestamp)
                print(f"  ID:{msg_id:4d} [{role:9s}] {dt.strftime('%Y-%m-%d %H:%M:%S')} | {content_preview}")
                
                if prev_timestamp and timestamp > prev_timestamp:
                    print(f"    ⚠️ 时间戳顺序错误！")
                    order_correct = False
                prev_timestamp = timestamp
            
            if order_correct:
                print(f"  ✅ 时间戳顺序正确")
        print()

        # 4. 检查分页加载逻辑
        print("📊 4. 分页加载逻辑检查")
        print("-" * 80)
        if contacts:
            contact_name = contacts[0][0]
            contact_count = contacts[0][1]
            
            print(f"测试联系人: {contact_name} (总消息数: {contact_count})")
            
            # 测试第一页
            cursor.execute("""
                SELECT id, role, content, timestamp
                FROM chat_history
                WHERE contact_name = ?
                ORDER BY timestamp DESC
                LIMIT 5 OFFSET 0
            """, (contact_name,))
            page1 = cursor.fetchall()
            print(f"\n第1页 (LIMIT 5 OFFSET 0): {len(page1)} 条消息")
            for msg_id, role, content, timestamp in page1:
                content_preview = content[:30] + "..." if len(content) > 30 else content
                print(f"  ID:{msg_id:4d} [{role:9s}] {content_preview}")
            
            # 测试第二页
            cursor.execute("""
                SELECT id, role, content, timestamp
                FROM chat_history
                WHERE contact_name = ?
                ORDER BY timestamp DESC
                LIMIT 5 OFFSET 5
            """, (contact_name,))
            page2 = cursor.fetchall()
            print(f"\n第2页 (LIMIT 5 OFFSET 5): {len(page2)} 条消息")
            for msg_id, role, content, timestamp in page2:
                content_preview = content[:30] + "..." if len(content) > 30 else content
                print(f"  ID:{msg_id:4d} [{role:9s}] {content_preview}")
            
            # 检查是否有重叠
            page1_ids = {msg[0] for msg in page1}
            page2_ids = {msg[0] for msg in page2}
            overlap = page1_ids & page2_ids
            if overlap:
                print(f"\n⚠️ 分页重叠！重复的消息ID: {overlap}")
            else:
                print(f"\n✅ 分页正确，无重叠")
        print()

        # 5. 检查去重逻辑
        print("📊 5. 去重逻辑检查")
        print("-" * 80)
        if contacts:
            contact_name = contacts[0][0]
            
            # 模拟当前的去重逻辑
            cursor.execute("""
                SELECT role, content, timestamp, id
                FROM chat_history
                WHERE contact_name = ?
                ORDER BY timestamp DESC
                LIMIT 20
            """, (contact_name,))
            rows = cursor.fetchall()
            
            # 使用消息ID去重
            seen_ids = set()
            messages_by_id = []
            for row in reversed(rows):
                msg_id = row[3]
                if msg_id not in seen_ids:
                    seen_ids.add(msg_id)
                    messages_by_id.append(row)
            
            print(f"原始查询: {len(rows)} 条消息")
            print(f"ID去重后: {len(messages_by_id)} 条消息")
            
            if len(rows) != len(messages_by_id):
                print(f"⚠️ 去重删除了 {len(rows) - len(messages_by_id)} 条消息")
            else:
                print(f"✅ 去重正确，无重复ID")
        print()

        conn.close()

        print("=" * 80)
        print("✅ 诊断完成")
        print("=" * 80)

    except Exception as e:
        print(f"❌ 诊断失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    diagnose_history_issues()

