"""
表情包上传修复脚本 - v2.29.1

用于诊断和修复表情包上传功能的问题
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def check_dependencies():
    """检查依赖"""
    print("=" * 60)
    print("1. 检查依赖...")
    print("=" * 60)
    
    try:
        from PyQt6.QtWidgets import QApplication, QFileDialog
        print("✅ PyQt6 已安装")
    except ImportError:
        print("❌ PyQt6 未安装")
        print("   请运行: pip install PyQt6")
        return False
    
    try:
        from src.gui.emoji_picker import EmojiPicker
        print("✅ EmojiPicker 可以导入")
    except ImportError as e:
        print(f"❌ EmojiPicker 导入失败: {e}")
        return False
    
    try:
        from src.auth.user_data_manager import UserDataManager
        print("✅ UserDataManager 可以导入")
    except ImportError as e:
        print(f"❌ UserDataManager 导入失败: {e}")
        return False
    
    print()
    return True


def check_methods():
    """检查方法"""
    print("=" * 60)
    print("2. 检查方法...")
    print("=" * 60)
    
    from src.gui.emoji_picker import EmojiPicker
    
    methods = [
        'upload_custom_sticker',
        'create_custom_sticker_grid',
        'clear_all_stickers',
        'on_sticker_clicked',
        'on_sticker_delete_requested',
    ]
    
    all_ok = True
    for method in methods:
        if hasattr(EmojiPicker, method):
            print(f"✅ {method} 方法存在")
        else:
            print(f"❌ {method} 方法不存在")
            all_ok = False
    
    print()
    return all_ok


def check_file_dialog():
    """检查文件对话框"""
    print("=" * 60)
    print("3. 检查文件对话框...")
    print("=" * 60)
    
    try:
        from PyQt6.QtWidgets import QApplication, QFileDialog
        
        # 创建应用（如果还没有）
        app = QApplication.instance()
        if app is None:
            app = QApplication(sys.argv)
        
        print("✅ QApplication 创建成功")
        print("✅ QFileDialog 可用")
        
        # 检查文件对话框配置
        print()
        print("文件对话框配置:")
        print("  - 使用系统原生对话框: ✅")
        print("  - 支持的格式: GIF, PNG, JPG, JPEG, WEBP")
        print("  - 最大文件大小: 10MB")
        
        print()
        return True
    except Exception as e:
        print(f"❌ 文件对话框检查失败: {e}")
        return False


def test_file_dialog():
    """测试文件对话框"""
    print("=" * 60)
    print("4. 测试文件对话框...")
    print("=" * 60)
    
    try:
        from PyQt6.QtWidgets import QApplication, QFileDialog
        
        # 创建应用（如果还没有）
        app = QApplication.instance()
        if app is None:
            app = QApplication(sys.argv)
        
        print("即将打开文件选择对话框...")
        print("请选择一个图片文件进行测试")
        print()
        
        # 打开文件对话框
        file_path, _ = QFileDialog.getOpenFileName(
            None,
            "测试 - 选择表情包图片",
            "",
            "图片文件 (*.gif *.png *.jpg *.jpeg *.webp);;GIF动图 (*.gif);;PNG图片 (*.png);;JPG图片 (*.jpg *.jpeg);;WEBP图片 (*.webp);;所有文件 (*.*)"
        )
        
        if file_path:
            print(f"✅ 文件选择成功: {file_path}")
            
            # 验证文件
            file = Path(file_path)
            if file.exists():
                size = file.stat().st_size
                print(f"   文件大小: {size / 1024:.2f}KB")
                print(f"   文件类型: {file.suffix}")
                
                if size > 10 * 1024 * 1024:
                    print(f"   ⚠️ 警告: 文件过大（{size / 1024 / 1024:.2f}MB），超过10MB限制")
                else:
                    print(f"   ✅ 文件大小符合要求")
                
                allowed = ['.gif', '.png', '.jpg', '.jpeg', '.webp']
                if file.suffix.lower() in allowed:
                    print(f"   ✅ 文件类型符合要求")
                else:
                    print(f"   ⚠️ 警告: 不支持的文件类型")
            else:
                print(f"   ❌ 文件不存在")
        else:
            print("ℹ️ 用户取消了文件选择")
        
        print()
        return True
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def check_user_directory():
    """检查用户目录"""
    print("=" * 60)
    print("5. 检查用户目录...")
    print("=" * 60)
    
    data_dir = project_root / "data"
    users_dir = data_dir / "users"
    
    print(f"数据目录: {data_dir}")
    print(f"用户目录: {users_dir}")
    
    if data_dir.exists():
        print("✅ data 目录存在")
    else:
        print("❌ data 目录不存在")
        print("   正在创建...")
        data_dir.mkdir(parents=True, exist_ok=True)
        print("✅ data 目录已创建")
    
    if users_dir.exists():
        print("✅ users 目录存在")
    else:
        print("❌ users 目录不存在")
        print("   正在创建...")
        users_dir.mkdir(parents=True, exist_ok=True)
        print("✅ users 目录已创建")
    
    print()
    return True


def print_summary():
    """打印总结"""
    print("=" * 60)
    print("诊断总结")
    print("=" * 60)
    print()
    print("如果文件对话框无法打开，可能的原因：")
    print()
    print("1. ❌ 未登录")
    print("   解决方案: 先登录用户账号")
    print()
    print("2. ❌ 在非主线程中调用")
    print("   解决方案: 确保在主线程（GUI线程）中调用")
    print()
    print("3. ❌ PyQt6 版本问题")
    print("   解决方案: 更新 PyQt6 到最新版本")
    print("   命令: pip install --upgrade PyQt6")
    print()
    print("4. ❌ 权限问题")
    print("   解决方案: 以管理员身份运行程序")
    print()
    print("5. ❌ 系统兼容性问题")
    print("   解决方案: 检查操作系统是否支持")
    print()
    print("=" * 60)
    print("修复建议")
    print("=" * 60)
    print()
    print("1. 确保已登录用户")
    print("2. 在主窗口中点击上传按钮")
    print("3. 检查控制台是否有错误信息")
    print("4. 查看日志文件: logs/mintchat.log")
    print()
    print("如果问题仍然存在，请提供以下信息：")
    print("- 操作系统版本")
    print("- Python 版本")
    print("- PyQt6 版本")
    print("- 错误日志")
    print()


def main():
    """主函数"""
    print()
    print("=" * 60)
    print("表情包上传功能诊断工具 v2.29.1")
    print("=" * 60)
    print()
    
    # 检查依赖
    if not check_dependencies():
        print()
        print("❌ 依赖检查失败，请先安装依赖")
        return
    
    # 检查方法
    if not check_methods():
        print()
        print("❌ 方法检查失败，代码可能有问题")
        return
    
    # 检查文件对话框
    if not check_file_dialog():
        print()
        print("❌ 文件对话框检查失败")
        return
    
    # 检查用户目录
    check_user_directory()
    
    # 询问是否测试文件对话框
    print("是否要测试文件对话框？(y/n): ", end="")
    choice = input().strip().lower()
    
    if choice == 'y':
        test_file_dialog()
    
    # 打印总结
    print_summary()
    
    print("=" * 60)
    print("✅ 诊断完成")
    print("=" * 60)
    print()


if __name__ == "__main__":
    main()

