#!/usr/bin/env python3
"""
修复重复消息工具 v2.30.13
清理数据库中的重复聊天消息

功能：
1. 检测重复消息（相同用户、联系人、角色、内容、时间戳）
2. 保留最早的消息，删除重复的
3. 生成详细的清理报告
4. 自动备份数据库

注意：
- 运行前会自动备份数据库
- 只删除完全相同的重复消息
- 保留时间戳最早的消息
"""

import sqlite3
import shutil
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Tuple

PROJECT_ROOT = Path(__file__).parent.parent


class DuplicateMessageFixer:
    """重复消息修复器"""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.backup_path = None
        self.stats = {
            "total_messages": 0,
            "duplicate_groups": 0,
            "duplicates_removed": 0,
        }

    def backup_database(self) -> bool:
        """备份数据库"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            self.backup_path = self.db_path.parent / f"user_data_backup_{timestamp}.db"
            shutil.copy2(self.db_path, self.backup_path)
            print(f"✅ 数据库已备份到: {self.backup_path}")
            return True
        except Exception as e:
            print(f"❌ 备份数据库失败: {e}")
            return False

    def find_duplicates(self) -> List[Tuple[int, List[int]]]:
        """查找重复消息（v2.30.13: 更精确的去重逻辑）

        只删除时间戳非常接近（1秒内）且内容完全相同的消息

        Returns:
            List of (kept_id, [duplicate_ids])
        """
        duplicates = []

        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # 获取总消息数
            cursor.execute("SELECT COUNT(*) FROM chat_history")
            self.stats["total_messages"] = cursor.fetchone()[0]

            # v2.30.13: 更精确的重复检测
            # 重复定义：相同的user_id, contact_name, role, content，且时间戳在1秒内
            cursor.execute("""
                SELECT
                    id,
                    user_id,
                    contact_name,
                    role,
                    content,
                    timestamp
                FROM chat_history
                ORDER BY user_id, contact_name, role, content, timestamp
            """)

            rows = cursor.fetchall()

            # 手动检测时间戳接近的重复消息
            prev_row = None
            for row in rows:
                if prev_row is None:
                    prev_row = row
                    continue

                # 检查是否与前一条消息重复
                # 条件：user_id, contact_name, role, content相同，且时间戳在1秒内
                if (prev_row[1] == row[1] and  # user_id
                    prev_row[2] == row[2] and  # contact_name
                    prev_row[3] == row[3] and  # role
                    prev_row[4] == row[4]):    # content

                    # 解析时间戳（格式：YYYY-MM-DD HH:MM:SS）
                    try:
                        from datetime import datetime
                        prev_time = datetime.strptime(prev_row[5], "%Y-%m-%d %H:%M:%S")
                        curr_time = datetime.strptime(row[5], "%Y-%m-%d %H:%M:%S")
                        time_diff = abs((curr_time - prev_time).total_seconds())

                        # 如果时间差小于1秒，视为重复
                        if time_diff <= 1.0:
                            kept_id = prev_row[0]  # 保留较早的
                            duplicate_id = row[0]  # 删除较晚的

                            # 查找是否已经有这个kept_id的组
                            found = False
                            for i, (kid, dids) in enumerate(duplicates):
                                if kid == kept_id:
                                    duplicates[i] = (kid, dids + [duplicate_id])
                                    found = True
                                    break

                            if not found:
                                duplicates.append((kept_id, [duplicate_id]))

                            self.stats["duplicates_removed"] += 1
                            continue  # 不更新prev_row，继续与同一条比较
                    except Exception as e:
                        print(f"⚠️ 解析时间戳失败: {e}")

                prev_row = row

            self.stats["duplicate_groups"] = len(duplicates)
            conn.close()
            return duplicates

        except Exception as e:
            print(f"❌ 查找重复消息失败: {e}")
            import traceback
            traceback.print_exc()
            return []

    def remove_duplicates(self, duplicates: List[Tuple[int, List[int]]]) -> bool:
        """删除重复消息"""
        if not duplicates:
            print("✅ 没有发现重复消息")
            return True

        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # 收集所有要删除的ID
            all_duplicate_ids = []
            for kept_id, duplicate_ids in duplicates:
                all_duplicate_ids.extend(duplicate_ids)

            # 批量删除
            placeholders = ','.join('?' * len(all_duplicate_ids))
            cursor.execute(
                f"DELETE FROM chat_history WHERE id IN ({placeholders})",
                all_duplicate_ids
            )

            conn.commit()
            conn.close()

            print(f"✅ 已删除 {len(all_duplicate_ids)} 条重复消息")
            return True

        except Exception as e:
            print(f"❌ 删除重复消息失败: {e}")
            return False

    def print_report(self, duplicates: List[Tuple[int, List[int]]]) -> None:
        """打印报告"""
        print("\n" + "=" * 80)
        print("  重复消息清理报告 v2.30.13")
        print("=" * 80)
        print()

        print(f"📊 统计信息")
        print("-" * 80)
        print(f"总消息数: {self.stats['total_messages']}")
        print(f"重复消息组: {self.stats['duplicate_groups']}")
        print(f"删除的重复消息: {self.stats['duplicates_removed']}")
        print(f"清理后消息数: {self.stats['total_messages'] - self.stats['duplicates_removed']}")
        print()

        if duplicates:
            print(f"📝 重复消息详情（显示前10组）")
            print("-" * 80)

            for i, (kept_id, duplicate_ids) in enumerate(duplicates[:10]):
                print(f"\n组 {i+1}:")
                print(f"  保留消息ID: {kept_id}")
                print(f"  删除消息ID: {duplicate_ids}")

            if len(duplicates) > 10:
                print(f"\n... 还有 {len(duplicates) - 10} 组重复消息")

        print()
        print("=" * 80)
        print("💡 提示：")
        print(f"  - 数据库备份: {self.backup_path}")
        print("  - 如需恢复，请将备份文件复制回原位置")
        print("=" * 80)

    def fix(self) -> bool:
        """执行修复"""
        print("🔍 开始检查重复消息...")
        print()

        # 备份数据库
        if not self.backup_database():
            return False

        # 查找重复消息
        duplicates = self.find_duplicates()

        # 打印报告
        self.print_report(duplicates)

        if not duplicates:
            return True

        # 确认删除
        print()
        response = input("是否删除重复消息？(y/n): ")
        if response.lower() != 'y':
            print("❌ 已取消删除")
            return False

        # 删除重复消息
        return self.remove_duplicates(duplicates)


def main():
    """主函数"""
    # 查找数据库文件
    db_path = PROJECT_ROOT / "data" / "user_data.db"
    
    if not db_path.exists():
        print(f"❌ 数据库文件不存在: {db_path}")
        return

    print(f"📁 数据库路径: {db_path}")
    print()

    # 创建修复器
    fixer = DuplicateMessageFixer(db_path)

    # 执行修复
    success = fixer.fix()

    if success:
        print()
        print("✅ 修复完成！")
    else:
        print()
        print("❌ 修复失败")


if __name__ == "__main__":
    main()

