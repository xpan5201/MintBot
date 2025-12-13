#!/usr/bin/env python3
"""
修复文件编码问题
修复MintChat.py中的emoji显示问题
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def fix_mintchat_encoding():
    """修复MintChat.py的编码问题"""
    file_path = project_root / "MintChat.py"

    print(f"修复文件: {file_path}")

    # 读取文件（使用UTF-8编码）
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    # 替换损坏的emoji字符
    replacements = {
        "- � 向量检索缓存": "- 🚀 向量检索缓存",
    }

    modified = False
    for old, new in replacements.items():
        if old in content:
            content = content.replace(old, new)
            modified = True
            print(f"✅ 替换: {old[:20]}... -> {new[:20]}...")

    if modified:
        # 写回文件（使用UTF-8编码，不带BOM）
        with open(file_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(content)
        print(f"✅ 文件已修复: {file_path}")
        return True
    else:
        print("ℹ️ 未发现需要修复的内容")
        return False


if __name__ == "__main__":
    try:
        success = fix_mintchat_encoding()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"❌ 修复失败: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
