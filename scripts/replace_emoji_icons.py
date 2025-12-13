"""
批量替换GUI中的emoji图标为MD3图标
v2.31.0
"""

import re
from pathlib import Path

# emoji到MD3图标的映射
EMOJI_TO_MD3 = {
    "👤": "person",
    "🤖": "smart_toy",
    "🐱": "pets",
    "🧠": "psychology",
    "📋": "assignment",
    "⚙️": "settings",
    "📚": "library_books",
    "📁": "folder_open",
    "📝": "note",
    "🎭": "masks",
    "🔌": "tune",
    "💡": "lightbulb",
    "🔄": "refresh",
    "💾": "save",
    "🗑️": "delete",
    "📷": "photo_camera",
    "📄": "description",
    "🖼️": "image",
    "🔍": "manage_search",
    "💬": "chat",
}

def replace_emoji_in_file(file_path: Path):
    """替换文件中的emoji图标"""
    print(f"处理文件: {file_path}")
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    original_content = content
    replacements = 0
    
    # 替换分组标题中的emoji
    for emoji, md3_icon in EMOJI_TO_MD3.items():
        # 匹配 _create_group("emoji 文本")
        pattern = rf'_create_group\("{re.escape(emoji)}\s+'
        replacement = f'_create_group(f"{{MATERIAL_ICONS[\'{md3_icon}\']}}  '
        if re.search(pattern, content):
            content = re.sub(pattern, replacement, content)
            replacements += 1
            print(f"  替换分组标题: {emoji} -> {md3_icon}")
    
    # 替换按钮中的emoji (QPushButton("emoji 文本"))
    for emoji, md3_icon in EMOJI_TO_MD3.items():
        # 匹配 QPushButton("emoji 文本")
        pattern = rf'QPushButton\("{re.escape(emoji)}\s+([^"]+)"\)'
        matches = re.findall(pattern, content)
        for match in matches:
            old_str = f'QPushButton("{emoji} {match}")'
            new_str = f'self._create_icon_button("{md3_icon}", "{match}", 15)'
            if old_str in content:
                content = content.replace(old_str, new_str)
                replacements += 1
                print(f"  替换按钮: {emoji} {match} -> {md3_icon}")
    
    # 替换标签中的emoji (QLabel("emoji 文本"))
    for emoji, md3_icon in EMOJI_TO_MD3.items():
        # 匹配 QLabel("emoji 文本")
        pattern = rf'QLabel\("{re.escape(emoji)}\s+([^"]+)"\)'
        matches = re.findall(pattern, content)
        for match in matches:
            old_str = f'QLabel("{emoji} {match}")'
            new_str = f'self._create_icon_label("{md3_icon}", "{match}", 16)'
            if old_str in content:
                content = content.replace(old_str, new_str)
                replacements += 1
                print(f"  替换标签: {emoji} {match} -> {md3_icon}")
    
    # 替换头像预览中的emoji
    for emoji, md3_icon in EMOJI_TO_MD3.items():
        # 匹配 QLabel("emoji")
        pattern = rf'QLabel\("{re.escape(emoji)}"\)'
        if re.search(pattern, content):
            # 这些是头像预览,保持emoji或使用图标
            print(f"  发现头像预览emoji: {emoji}")
    
    if content != original_content:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"✓ 完成替换 {replacements} 处")
        return True
    else:
        print("  无需替换")
        return False

def main():
    """主函数"""
    print("=" * 60)
    print("批量替换GUI中的emoji图标为MD3图标")
    print("=" * 60)
    
    # 要处理的文件列表
    files_to_process = [
        Path("src/gui/settings_panel.py"),
        Path("src/gui/light_chat_window.py"),
    ]
    
    total_files = 0
    for file_path in files_to_process:
        if file_path.exists():
            if replace_emoji_in_file(file_path):
                total_files += 1
        else:
            print(f"文件不存在: {file_path}")
    
    print("=" * 60)
    print(f"完成! 共处理 {total_files} 个文件")
    print("=" * 60)

if __name__ == "__main__":
    main()

