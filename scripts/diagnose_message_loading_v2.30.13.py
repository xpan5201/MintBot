#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
历史消息加载诊断工具 v2.30.13
检查消息保存和加载逻辑
"""

import sqlite3
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def diagnose_message_loading():
    """诊断消息加载问题"""
    db_path = project_root / "data" / "user_data.db"
    
    if not db_path.exists():
        print(f"❌ 数据库不存在: {db_path}")
        return
    
    print(f"📊 诊断数据库: {db_path}")
    print("=" * 80)
    
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    # 1. 检查消息总数
    cursor.execute("SELECT COUNT(*) FROM chat_history")
    total_count = cursor.fetchone()[0]
    print(f"\n1️⃣ 消息总数: {total_count}")
    
    # 2. 按联系人统计
    cursor.execute("""
        SELECT contact_name, COUNT(*) as count
        FROM chat_history
        GROUP BY contact_name
        ORDER BY count DESC
    """)
    print(f"\n2️⃣ 按联系人统计:")
    for row in cursor.fetchall():
        print(f"   - {row[0]}: {row[1]}条消息")
    
    # 3. 检查最近的消息（按时间戳降序）
    cursor.execute("""
        SELECT id, contact_name, role, content, timestamp
        FROM chat_history
        ORDER BY timestamp DESC
        LIMIT 10
    """)
    print(f"\n3️⃣ 最近10条消息（按时间戳降序）:")
    for i, row in enumerate(cursor.fetchall(), 1):
        msg_id, contact, role, content, timestamp = row
        content_preview = content[:50] + "..." if len(content) > 50 else content
        print(f"   {i}. [ID:{msg_id}] {contact} - {role} - {timestamp}")
        print(f"      内容: {content_preview}")
    
    # 4. 模拟get_chat_history的查询逻辑
    print(f"\n4️⃣ 模拟get_chat_history查询（limit=20）:")
    
    # 获取第一个联系人
    cursor.execute("SELECT DISTINCT contact_name FROM chat_history LIMIT 1")
    contact_name = cursor.fetchone()
    if not contact_name:
        print("   ❌ 没有联系人")
        conn.close()
        return
    
    contact_name = contact_name[0]
    print(f"   联系人: {contact_name}")
    
    # 模拟查询（按timestamp DESC）
    limit = 20
    fetch_limit = limit * 2
    cursor.execute("""
        SELECT role, content, timestamp, id
        FROM chat_history
        WHERE contact_name = ?
        ORDER BY timestamp DESC
        LIMIT ?
    """, (contact_name, fetch_limit))
    
    rows = cursor.fetchall()
    print(f"   查询结果: {len(rows)}条（fetch_limit={fetch_limit}）")
    
    # 模拟去重逻辑（v2.30.13修复后）
    seen_ids = set()
    messages = []

    print(f"\n   处理顺序（从最新的开始，不reversed）:")
    for i, row in enumerate(rows, 1):
        msg_id = row[3]
        timestamp = row[2]
        content_preview = row[1][:30] + "..." if len(row[1]) > 30 else row[1]

        if msg_id not in seen_ids:
            seen_ids.add(msg_id)
            messages.append({
                "role": row[0],
                "content": row[1],
                "timestamp": row[2],
                "id": msg_id
            })
            status = "✅ 添加"
        else:
            status = "⚠️ 跳过（重复ID）"

        print(f"   {i}. [ID:{msg_id}] {timestamp} - {status}")
        print(f"      {content_preview}")

        if len(messages) >= limit:
            print(f"   ⚠️ 达到limit={limit}，停止处理")
            break

    # v2.30.13: 反转消息列表，让消息按时间从旧到新排列
    messages.reverse()
    
    print(f"\n   最终返回: {len(messages)}条消息")
    print(f"   消息顺序（从旧到新）:")
    for i, msg in enumerate(messages, 1):
        content_preview = msg['content'][:30] + "..." if len(msg['content']) > 30 else msg['content']
        print(f"   {i}. [ID:{msg['id']}] {msg['timestamp']} - {msg['role']}")
        print(f"      {content_preview}")
    
    # 5. 检查是否有重复ID
    cursor.execute("""
        SELECT id, COUNT(*) as count
        FROM chat_history
        GROUP BY id
        HAVING count > 1
    """)
    duplicates = cursor.fetchall()
    print(f"\n5️⃣ 重复ID检查:")
    if duplicates:
        print(f"   ⚠️ 发现{len(duplicates)}个重复ID:")
        for row in duplicates:
            print(f"   - ID {row[0]}: {row[1]}次")
    else:
        print(f"   ✅ 没有重复ID")
    
    conn.close()
    print("\n" + "=" * 80)
    print("✅ 诊断完成")

if __name__ == "__main__":
    diagnose_message_loading()

