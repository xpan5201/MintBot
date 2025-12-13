"""
知识库系统测试脚本 - v2.30.38

测试知识库的所有新功能：
1. 添加、更新、删除知识
2. 批量导入、导出
3. 统计信息
4. 智能学习（从对话、文件）
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.agent.advanced_memory import LoreBook
from src.config.settings import settings
import json
from datetime import datetime


def print_section(title: str):
    """打印分隔线"""
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60 + "\n")


def test_basic_operations():
    """测试基本操作"""
    print_section("测试 1: 基本操作（添加、更新、删除）")

    # 创建知识库
    lore_book = LoreBook(persist_directory="data/test_lorebook", user_id=999)

    # 清空测试数据
    lore_book.clear_all()
    print("✅ 清空测试数据")

    # 添加知识
    print("\n📝 添加知识...")
    lore_id_1 = lore_book.add_lore(
        title="猫娘小薄荷",
        content="小薄荷是一只可爱的猫娘女仆，性格温柔体贴，喜欢照顾主人。",
        category="character",
        keywords=["猫娘", "女仆", "温柔"],
        source="manual"
    )
    print(f"✅ 添加知识 1: {lore_id_1}")

    lore_id_2 = lore_book.add_lore(
        title="主人的房间",
        content="主人的房间位于二楼，有一个大窗户，阳光充足。",
        category="location",
        keywords=["房间", "二楼", "窗户"],
        source="manual"
    )
    print(f"✅ 添加知识 2: {lore_id_2}")

    lore_id_3 = lore_book.add_lore(
        title="魔法项链",
        content="一条神秘的魔法项链，据说能够实现愿望。",
        category="item",
        keywords=["魔法", "项链", "愿望"],
        source="manual"
    )
    print(f"✅ 添加知识 3: {lore_id_3}")

    # 获取所有知识
    all_lores = lore_book.get_all_lores()
    print(f"\n📊 当前知识数量: {len(all_lores)}")

    # 更新知识
    print("\n✏️ 更新知识...")
    success = lore_book.update_lore(
        lore_id=lore_id_1,
        content="小薄荷是一只可爱的猫娘女仆，性格温柔体贴，喜欢照顾主人。她最喜欢的食物是小鱼干。",
        keywords=["猫娘", "女仆", "温柔", "小鱼干"]
    )
    print(f"✅ 更新知识: {success}")

    # 查看更新后的知识
    updated_lore = lore_book.get_lore_by_id(lore_id_1)
    print(f"📄 更新后的内容: {updated_lore.get('content')[:50]}...")
    print(f"🔄 更新次数: {updated_lore.get('update_count')}")

    # 删除知识
    print("\n🗑️ 删除知识...")
    success = lore_book.delete_lore(lore_id_3)
    print(f"✅ 删除知识: {success}")

    # 再次获取所有知识
    all_lores = lore_book.get_all_lores()
    print(f"📊 删除后知识数量: {len(all_lores)}")

    return lore_book


def test_batch_operations(lore_book: LoreBook):
    """测试批量操作"""
    print_section("测试 2: 批量操作（导入、导出）")

    # 导出知识库
    export_file = "data/test_lorebook_export.json"
    print(f"\n📤 导出知识库到: {export_file}")
    success = lore_book.export_to_json(export_file)
    print(f"✅ 导出成功: {success}")

    # 查看导出文件
    with open(export_file, "r", encoding="utf-8") as f:
        exported_data = json.load(f)
    print(f"📊 导出的知识数量: {len(exported_data)}")

    # 清空知识库
    lore_book.clear_all()
    print("\n🧹 清空知识库")
    print(f"📊 清空后知识数量: {len(lore_book.get_all_lores())}")

    # 导入知识库
    print(f"\n📥 导入知识库从: {export_file}")
    count = lore_book.import_from_json(export_file, overwrite=False)
    print(f"✅ 导入成功: {count} 条")

    # 再次获取所有知识
    all_lores = lore_book.get_all_lores()
    print(f"📊 导入后知识数量: {len(all_lores)}")


def test_statistics(lore_book: LoreBook):
    """测试统计信息"""
    print_section("测试 3: 统计信息")

    stats = lore_book.get_statistics()

    print(f"📊 总计: {stats['total']} 条")
    print(f"📊 最近7天新增: {stats['recent_count']} 条")
    print(f"\n📂 按类别统计:")
    for category, count in stats['by_category'].items():
        print(f"  - {category}: {count} 条")
    print(f"\n📍 按来源统计:")
    for source, count in stats['by_source'].items():
        print(f"  - {source}: {count} 条")


def test_search(lore_book: LoreBook):
    """测试搜索功能"""
    print_section("测试 4: 搜索功能")

    # 搜索知识
    print("\n🔍 搜索: '猫娘'")
    results = lore_book.search_lore("猫娘", k=5)
    print(f"✅ 找到 {len(results)} 条相关知识")
    for i, result in enumerate(results, 1):
        print(f"\n  {i}. {result['metadata'].get('title')}")
        print(f"     相似度: {result['similarity']:.2f}")
        print(f"     类别: {result['metadata'].get('category')}")


def test_learning_from_conversation(lore_book: LoreBook):
    """测试从对话中学习"""
    print_section("测试 5: 从对话中学习")

    # 模拟对话
    conversations = [
        ("小薄荷的生日是什么时候？", "小薄荷的生日是3月15日，她最喜欢在生日那天吃草莓蛋糕。"),
        ("主人的名字叫什么？", "主人的名字叫李明，是一位温柔的年轻人。"),
        ("今天天气怎么样？", "今天天气很好，阳光明媚。"),  # 不重要的对话
    ]

    print("\n📖 从对话中学习...")
    total_learned = 0
    for user_msg, ai_reply in conversations:
        learned_ids = lore_book.learn_from_conversation(user_msg, ai_reply, auto_extract=True)
        if learned_ids:
            print(f"✅ 学习到 {len(learned_ids)} 条知识: {user_msg[:20]}...")
            total_learned += len(learned_ids)
        else:
            print(f"⏭️ 跳过不重要的对话: {user_msg[:20]}...")

    print(f"\n📊 总共学习到 {total_learned} 条知识")

    # 查看统计
    stats = lore_book.get_statistics()
    print(f"📊 当前总知识数: {stats['total']} 条")


def main():
    """主函数"""
    print("\n" + "🎉" * 30)
    print("  知识库系统测试 - v2.30.38")
    print("🎉" * 30)

    try:
        # 测试基本操作
        lore_book = test_basic_operations()

        # 测试批量操作
        test_batch_operations(lore_book)

        # 测试统计信息
        test_statistics(lore_book)

        # 测试搜索功能
        test_search(lore_book)

        # 测试从对话中学习
        test_learning_from_conversation(lore_book)

        print_section("✅ 所有测试完成！")

    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()

