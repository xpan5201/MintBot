"""
知识库系统测试脚本 - v2.30.39

测试新增功能：
1. LLM 辅助知识提取
2. 性能优化（缓存机制）
3. 批量操作
4. 智能去重
5. 文件格式扩展
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.agent.advanced_memory import LoreBook
from src.config.settings import settings
import time


def print_section(title: str):
    """打印分隔线"""
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60 + "\n")


def test_cache_performance(lore_book: LoreBook):
    """测试缓存性能"""
    print_section("测试 1: 缓存性能测试")

    # 添加一些测试数据
    print("📝 添加测试数据...")
    for i in range(10):
        lore_book.add_lore(
            title=f"测试知识 {i+1}",
            content=f"这是第 {i+1} 条测试知识的内容",
            category="general",
            keywords=[f"测试{i+1}", "性能"],
            source="test",
        )

    # 测试无缓存查询
    print("\n⏱️ 测试无缓存查询...")
    start = time.time()
    lores1 = lore_book.get_all_lores(use_cache=False)
    time1 = (time.time() - start) * 1000
    print(f"无缓存查询时间: {time1:.2f}ms")

    # 测试有缓存查询
    print("\n⏱️ 测试有缓存查询...")
    start = time.time()
    lores2 = lore_book.get_all_lores(use_cache=True)
    time2 = (time.time() - start) * 1000
    print(f"有缓存查询时间: {time2:.2f}ms")

    # 计算提升
    speedup = time1 / time2 if time2 > 0 else 0
    print(f"\n🚀 性能提升: {speedup:.1f}x")

    # 测试统计信息缓存
    print("\n⏱️ 测试统计信息缓存...")
    start = time.time()
    stats1 = lore_book.get_statistics(use_cache=False)
    time3 = (time.time() - start) * 1000
    print(f"无缓存统计时间: {time3:.2f}ms")

    start = time.time()
    stats2 = lore_book.get_statistics(use_cache=True)
    time4 = (time.time() - start) * 1000
    print(f"有缓存统计时间: {time4:.2f}ms")

    speedup2 = time3 / time4 if time4 > 0 else 0
    print(f"🚀 性能提升: {speedup2:.1f}x")


def test_batch_operations(lore_book: LoreBook):
    """测试批量操作"""
    print_section("测试 2: 批量操作")

    # 准备批量数据
    lores = [
        {
            "title": f"批量知识 {i+1}",
            "content": f"这是批量添加的第 {i+1} 条知识",
            "category": "general",
            "keywords": [f"批量{i+1}"],
            "source": "batch_test",
        }
        for i in range(20)
    ]

    # 测试批量添加
    print("📦 批量添加 20 条知识...")
    start = time.time()
    added_ids = lore_book.batch_add_lores(lores)
    time_batch = (time.time() - start) * 1000
    print(f"✅ 批量添加成功: {len(added_ids)} 条")
    print(f"⏱️ 批量添加时间: {time_batch:.2f}ms")

    # 测试单个添加（对比）
    print("\n📝 单个添加 20 条知识...")
    start = time.time()
    for lore in lores:
        lore_book.add_lore(
            title=lore["title"] + "_single",
            content=lore["content"],
            category=lore["category"],
            keywords=lore["keywords"],
            source="single_test",
        )
    time_single = (time.time() - start) * 1000
    print(f"✅ 单个添加完成")
    print(f"⏱️ 单个添加时间: {time_single:.2f}ms")

    speedup = time_single / time_batch if time_batch > 0 else 0
    print(f"\n🚀 批量操作提升: {speedup:.1f}x")

    # 测试批量删除
    print("\n🗑️ 批量删除知识...")
    deleted_count = lore_book.batch_delete_lores(added_ids[:10])
    print(f"✅ 批量删除成功: {deleted_count} 条")


def test_deduplication(lore_book: LoreBook):
    """测试智能去重"""
    print_section("测试 3: 智能去重")

    # 添加原始知识
    print("📝 添加原始知识...")
    lore_id1 = lore_book.add_lore(
        title="猫娘小薄荷",
        content="小薄荷是一只可爱的猫娘女仆，性格温柔体贴。",
        category="character",
        keywords=["猫娘", "女仆"],
        source="test",
    )
    print(f"✅ 添加成功: {lore_id1}")

    # 尝试添加相似知识（应该被去重）
    print("\n📝 尝试添加相似知识...")
    learned_ids = lore_book.learn_from_conversation(
        user_message="小薄荷是谁？",
        ai_response="小薄荷是一只温柔可爱的猫娘女仆。",
        use_llm=False,  # 使用规则提取
    )

    if learned_ids:
        print(f"⚠️ 添加了 {len(learned_ids)} 条知识（可能未去重）")
    else:
        print("✅ 成功去重，未添加重复知识")


def test_file_formats(lore_book: LoreBook):
    """测试文件格式支持"""
    print_section("测试 4: 文件格式支持")

    # 创建测试文件
    test_dir = Path("data/test_files")
    test_dir.mkdir(parents=True, exist_ok=True)

    # 测试 JSON 文件
    print("📄 测试 JSON 文件...")
    json_file = test_dir / "test.json"
    json_file.write_text('{"name": "测试", "value": 123}', encoding="utf-8")
    
    learned_ids = lore_book.learn_from_file(str(json_file))
    print(f"✅ JSON 文件学习: {len(learned_ids)} 条知识")

    # 测试 CSV 文件
    print("\n📄 测试 CSV 文件...")
    csv_file = test_dir / "test.csv"
    csv_file.write_text("name,age\n小薄荷,18\n小樱,17", encoding="utf-8")
    
    learned_ids = lore_book.learn_from_file(str(csv_file))
    print(f"✅ CSV 文件学习: {len(learned_ids)} 条知识")

    print("\n✅ 文件格式测试完成")


if __name__ == "__main__":
    print("\n🎉" * 30)
    print("  知识库系统测试 - v2.30.39")
    print("🎉" * 30)

    # 创建测试知识库
    lore_book = LoreBook(persist_directory="data/test_lore_books_v2.30.39")

    try:
        # 运行测试
        test_cache_performance(lore_book)
        test_batch_operations(lore_book)
        test_deduplication(lore_book)
        test_file_formats(lore_book)

        print_section("✅ 所有测试完成！")

    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()

