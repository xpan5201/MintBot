#!/usr/bin/env python3
"""
文档整理脚本 v2.29.13
整理docs目录，移除冗余文档，保持项目整洁
"""

import os
import shutil
from pathlib import Path
from typing import List, Dict

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent
DOCS_DIR = PROJECT_ROOT / "docs"
ARCHIVE_DIR = DOCS_DIR / "archive"

# 核心文档（保留在docs根目录）
CORE_DOCS = {
    "README.md",
    "QUICKSTART.md",
    "INSTALL.md",
    "API.md",
    "ARCHITECTURE.md",
    "PROJECT_STRUCTURE.md",
    "CONTRIBUTING.md",
    "CHANGELOG.md",
    "EMOTION_SYSTEM_GUIDE.md",
    "MEMORY_SYSTEM_GUIDE.md",
    "GUI.md",
    "PROMPT_ENGINEERING_GUIDE.md",
}

# 需要归档的文档模式
ARCHIVE_PATTERNS = {
    "v2.24": ["v2.24.0_", "v2.24_", "优化报告_v2.24", "快速开始_v2.24"],
    "v2.25": ["v2.25.0_", "v2.25_"],
    "v2.26": ["v2.26.0_", "v2.26.1_", "v2.26_"],
    "v2.27": ["v2.27.0_", "v2.27.1_", "v2.27.2_", "v2.27.3_", "v2.27_"],
    "v2.28": ["v2.28.0_", "v2.28.1_", "v2.28.2_", "v2.28_"],
    "v2.29": ["v2.29.0_", "v2.29.1_", "v2.29_", "优化清单_v2.29", "表情包界面优化报告_v2.29", "文档整理方案_v2.29"],
}

# 需要删除的冗余文档
REDUNDANT_DOCS = {
    "OPTIMIZATION_SUMMARY_2025-11-13.md",  # 已整合到CHANGELOG
    "OPTIMIZATION_V2.29.12.md",  # 已整合到CHANGELOG
    "CODE_QUALITY_REPORT.md",  # 临时报告
    "PROJECT_CLEANUP_v2.29.1.md",  # 临时文档
    "修复完成_请阅读.md",  # 临时文档
    "QUICK_FIX_REFERENCE.md",  # 已归档
}

# 需要整合的文档
CONSOLIDATE_DOCS = {
    "memory": [
        "MEMORY_PERFORMANCE_OPTIMIZATION.md",
        "MEMORY_PERSISTENCE_FIX.md",
        "MEMORY_SYSTEM_OPTIMIZATION_GUIDE.md",
        "MEMORY_SYSTEM_OPTIMIZATION_SUMMARY.md",
        "MEMORY_V3.2.1_FINAL_SUMMARY.md",
        "MEMORY_V3.3.2_OPTIMIZATION.md",
        "MEMORY_V3.3.3_PERFORMANCE_FIX.md",
        "MEMORY_V3.3_OPTIMIZATION_SUMMARY.md",
    ],
    "emotion": [
        "EMOTION_PERSISTENCE_FIX.md",
        "EMOTION_SYSTEM_OPTIMIZATION_SUMMARY.md",
    ],
    "optimization": [
        "OPTIMIZATION_2025_SUMMARY.md",
    ],
}


def create_archive_structure():
    """创建归档目录结构"""
    print("📁 创建归档目录结构...")
    for version in ARCHIVE_PATTERNS.keys():
        version_dir = ARCHIVE_DIR / version
        version_dir.mkdir(parents=True, exist_ok=True)
        print(f"  ✓ {version_dir.relative_to(PROJECT_ROOT)}")
    print()


def move_version_docs():
    """移动版本文档到归档目录"""
    print("📦 移动版本文档到归档...")
    moved_count = 0
    
    for doc_file in DOCS_DIR.glob("*.md"):
        if doc_file.name in CORE_DOCS:
            continue
            
        # 检查是否匹配归档模式
        for version, patterns in ARCHIVE_PATTERNS.items():
            for pattern in patterns:
                if doc_file.name.startswith(pattern):
                    dest_dir = ARCHIVE_DIR / version
                    dest_file = dest_dir / doc_file.name
                    
                    if not dest_file.exists():
                        shutil.move(str(doc_file), str(dest_file))
                        print(f"  ✓ {doc_file.name} → archive/{version}/")
                        moved_count += 1
                    break
    
    print(f"  移动了 {moved_count} 个文档\n")
    return moved_count


def remove_redundant_docs():
    """删除冗余文档"""
    print("🗑️  删除冗余文档...")
    removed_count = 0
    
    for doc_name in REDUNDANT_DOCS:
        doc_file = DOCS_DIR / doc_name
        if doc_file.exists():
            doc_file.unlink()
            print(f"  ✓ 删除 {doc_name}")
            removed_count += 1
    
    print(f"  删除了 {removed_count} 个文档\n")
    return removed_count


def archive_consolidate_docs():
    """归档需要整合的文档"""
    print("📚 归档待整合文档...")
    archived_count = 0
    
    consolidate_dir = ARCHIVE_DIR / "to_consolidate"
    consolidate_dir.mkdir(parents=True, exist_ok=True)
    
    for category, docs in CONSOLIDATE_DOCS.items():
        category_dir = consolidate_dir / category
        category_dir.mkdir(parents=True, exist_ok=True)
        
        for doc_name in docs:
            doc_file = DOCS_DIR / doc_name
            if doc_file.exists():
                dest_file = category_dir / doc_name
                shutil.move(str(doc_file), str(dest_file))
                print(f"  ✓ {doc_name} → archive/to_consolidate/{category}/")
                archived_count += 1
    
    print(f"  归档了 {archived_count} 个文档\n")
    return archived_count


def generate_docs_index():
    """生成文档索引"""
    print("📝 生成文档索引...")
    
    index_content = """# MintChat 文档索引

欢迎查阅MintChat项目文档！

## 📚 核心文档

### 快速开始
- [快速开始指南](QUICKSTART.md) - 5分钟快速上手
- [安装指南](INSTALL.md) - 详细安装步骤
- [启动指南](LAUNCH_GUIDE.md) - 启动和配置

### 开发文档
- [API文档](API.md) - 完整API参考
- [架构文档](ARCHITECTURE.md) - 系统架构设计
- [项目结构](PROJECT_STRUCTURE.md) - 目录结构说明
- [贡献指南](CONTRIBUTING.md) - 如何贡献代码

### 系统指南
- [情绪系统指南](EMOTION_SYSTEM_GUIDE.md) - PAD情绪模型使用
- [记忆系统指南](MEMORY_SYSTEM_GUIDE.md) - 长短期记忆系统
- [GUI使用指南](GUI.md) - 图形界面使用
- [提示词工程](PROMPT_ENGINEERING_GUIDE.md) - 提示词优化技巧

### 更新日志
- [CHANGELOG](CHANGELOG.md) - 完整版本历史

## 📦 归档文档

历史版本文档已归档至 [archive](archive/) 目录：
- [v2.24](archive/v2.24/) - 统一异常处理系统
- [v2.25](archive/v2.25/) - 动画属性修复
- [v2.26](archive/v2.26/) - ChromaDB持久化
- [v2.27](archive/v2.27/) - 数据库连接池
- [v2.28](archive/v2.28/) - 情绪系统升级
- [v2.29](archive/v2.29/) - 全面性能优化

## 🔍 查找文档

- **新手**: 从 [快速开始指南](QUICKSTART.md) 开始
- **开发者**: 查看 [API文档](API.md) 和 [架构文档](ARCHITECTURE.md)
- **贡献者**: 阅读 [贡献指南](CONTRIBUTING.md)
- **历史版本**: 查看 [archive](archive/) 目录

---

**版本**: v2.29.13  
**更新日期**: 2025-11-13
"""
    
    readme_file = DOCS_DIR / "README.md"
    with open(readme_file, "w", encoding="utf-8") as f:
        f.write(index_content)
    
    print(f"  ✓ 生成 {readme_file.relative_to(PROJECT_ROOT)}\n")


def main():
    """主函数"""
    print("=" * 60)
    print("  MintChat 文档整理工具 v2.29.13")
    print("=" * 60)
    print()
    
    # 1. 创建归档目录结构
    create_archive_structure()
    
    # 2. 移动版本文档
    moved = move_version_docs()
    
    # 3. 删除冗余文档
    removed = remove_redundant_docs()
    
    # 4. 归档待整合文档
    archived = archive_consolidate_docs()
    
    # 5. 生成文档索引
    generate_docs_index()
    
    # 统计
    print("=" * 60)
    print("  整理完成！")
    print("=" * 60)
    print(f"  移动文档: {moved} 个")
    print(f"  删除文档: {removed} 个")
    print(f"  归档文档: {archived} 个")
    print()
    print("  核心文档保留在 docs/ 目录")
    print("  历史文档归档至 docs/archive/ 目录")
    print("=" * 60)


if __name__ == "__main__":
    main()

