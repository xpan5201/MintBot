"""
简单的表情包上传测试 - v2.29.1

直接测试 QFileDialog 是否能正常工作
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def test_qfiledialog():
    """测试 QFileDialog"""
    print("=" * 60)
    print("测试 QFileDialog")
    print("=" * 60)
    print()
    
    try:
        from PyQt6.QtWidgets import QApplication, QFileDialog
        
        # 创建应用
        app = QApplication(sys.argv)
        
        print("✅ QApplication 创建成功")
        print()
        print("即将打开文件选择对话框...")
        print("这应该是系统原生的文件选择器（Windows资源管理器）")
        print()
        
        # 测试1: 基本的文件对话框
        print("测试1: 基本文件对话框")
        file_path, _ = QFileDialog.getOpenFileName(
            None,
            "测试 - 选择任意文件",
            "",
            "所有文件 (*.*)"
        )
        
        if file_path:
            print(f"✅ 选择了文件: {file_path}")
        else:
            print("ℹ️ 用户取消了选择")
        
        print()
        
        # 测试2: 图片文件对话框（与表情包上传相同的配置）
        print("测试2: 图片文件对话框（表情包上传配置）")
        file_path, _ = QFileDialog.getOpenFileName(
            None,
            "选择表情包图片",
            "",
            "图片文件 (*.gif *.png *.jpg *.jpeg *.webp);;GIF动图 (*.gif);;PNG图片 (*.png);;JPG图片 (*.jpg *.jpeg);;WEBP图片 (*.webp);;所有文件 (*.*)"
        )
        
        if file_path:
            print(f"✅ 选择了文件: {file_path}")
            
            # 验证文件
            file = Path(file_path)
            if file.exists():
                size = file.stat().st_size
                print(f"   文件大小: {size / 1024:.2f}KB")
                print(f"   文件类型: {file.suffix}")
                
                # 检查是否符合要求
                if size <= 10 * 1024 * 1024:
                    print(f"   ✅ 文件大小符合要求（≤10MB）")
                else:
                    print(f"   ❌ 文件过大（{size / 1024 / 1024:.2f}MB）")
                
                allowed = ['.gif', '.png', '.jpg', '.jpeg', '.webp']
                if file.suffix.lower() in allowed:
                    print(f"   ✅ 文件类型符合要求")
                else:
                    print(f"   ❌ 不支持的文件类型")
        else:
            print("ℹ️ 用户取消了选择")
        
        print()
        print("=" * 60)
        print("测试完成")
        print("=" * 60)
        print()
        print("如果文件对话框正常打开，说明 QFileDialog 工作正常")
        print("如果在 MintChat 中无法打开，可能的原因：")
        print("1. 未登录用户")
        print("2. 在非主线程中调用")
        print("3. 窗口焦点问题")
        print()
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    test_qfiledialog()

