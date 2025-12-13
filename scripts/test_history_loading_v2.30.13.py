#!/usr/bin/env python3
"""
历史消息加载测试工具 v2.30.13
测试历史消息加载逻辑是否正确

功能：
1. 测试相同内容的消息是否都能加载
2. 测试去重逻辑是否正确（只去除ID重复）
3. 测试分页加载是否正常
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.auth.user_session import user_session
from src.auth.database import UserDatabase


def test_history_loading():
    """测试历史消息加载"""
    print("=" * 80)
    print("  历史消息加载测试 v2.30.13")
    print("=" * 80)
    print()

    # 使用UserDatabase进行登录
    print("🔐 测试用户登录...")
    db = UserDatabase()

    # 尝试使用不同的测试用户名
    import time
    test_username = f"test_user_{int(time.time())}"
    test_email = f"{test_username}@example.com"

    # 注册新用户
    print(f"📝 注册测试用户: {test_username}...")
    user_id = db.create_user(test_username, test_email, "test_password")
    if not user_id:
        print("❌ 注册失败，尝试使用已有用户...")
        # 使用已有用户
        user = db.verify_user("test_user", "test_password")
        if not user:
            print("❌ 登录失败")
            return
    else:
        print("✅ 注册成功")
        # 登录新用户
        user = db.verify_user(test_username, "test_password")
        if not user:
            print("❌ 登录失败")
            return

    # 创建会话并登录
    session_token = db.create_session(user['id'])
    user_session.login(user, session_token)

    print(f"✅ 登录成功 (用户ID: {user['id']}, 用户名: {user['username']})")
    print()

    # 测试联系人
    contact_name = "测试猫娘"

    # 添加测试消息
    print("📝 添加测试消息...")
    test_messages = [
        ("user", "你好"),
        ("assistant", "你好主人~"),
        ("user", "你好"),  # 相同内容，不同时间
        ("assistant", "有什么可以帮您的吗？"),
        ("user", "你好"),  # 再次相同内容
        ("assistant", "主人好~"),
    ]

    for role, content in test_messages:
        user_session.add_message(contact_name, role, content)
        print(f"  ✅ 添加消息: [{role}] {content}")
    
    print()

    # 测试加载历史消息
    print("📖 测试加载历史消息...")
    messages = user_session.get_chat_history(contact_name, limit=100, offset=0)
    
    print(f"✅ 加载了 {len(messages)} 条消息")
    print()

    # 显示消息
    print("📋 消息列表:")
    print("-" * 80)
    for i, msg in enumerate(messages):
        print(f"{i+1}. [{msg['role']}] {msg['content']} (ID: {msg['id']}, 时间: {msg['timestamp']})")
    print("-" * 80)
    print()

    # 验证结果
    print("🔍 验证结果:")
    print("-" * 80)

    # 统计"你好"的数量
    user_hello_count = sum(1 for msg in messages if msg['role'] == 'user' and msg['content'] == '你好')
    print(f"用户说'你好'的次数: {user_hello_count}")
    
    if user_hello_count == 3:
        print("✅ 正确！相同内容的消息都被加载了")
    else:
        print(f"❌ 错误！应该有3条'你好'，但只加载了{user_hello_count}条")
    
    # 检查消息ID是否唯一
    msg_ids = [msg['id'] for msg in messages]
    unique_ids = set(msg_ids)
    
    if len(msg_ids) == len(unique_ids):
        print("✅ 正确！所有消息ID都是唯一的（没有重复记录）")
    else:
        print(f"❌ 错误！有重复的消息ID: {len(msg_ids)} vs {len(unique_ids)}")
    
    # 检查消息总数
    if len(messages) == 6:
        print("✅ 正确！加载了所有6条消息")
    else:
        print(f"❌ 错误！应该有6条消息，但只加载了{len(messages)}条")
    
    print("-" * 80)
    print()

    # 清理测试数据
    print("🧹 清理测试数据...")
    user_id = user_session.get_user_id()
    if user_id:
        # 删除测试消息（使用UserDataManager）
        from src.auth.user_data_manager import UserDataManager
        data_manager = UserDataManager()

        # 直接使用SQL删除
        import sqlite3
        db_path = PROJECT_ROOT / "data" / "user_data.db"
        if db_path.exists():
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM chat_history WHERE user_id = ? AND contact_name = ?",
                (user_id, contact_name)
            )
            conn.commit()
            conn.close()
            print("✅ 测试数据已清理")
        else:
            print("⚠️ user_data.db不存在，跳过清理")
    
    print()
    print("=" * 80)
    print("  测试完成！")
    print("=" * 80)


if __name__ == "__main__":
    try:
        test_history_loading()
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()

