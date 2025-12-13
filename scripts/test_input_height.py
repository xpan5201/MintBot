"""
测试输入框高度调整逻辑

验证修复后的输入框不会在初始化时扩张到最大
"""

import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer

def test_input_height():
    """测试输入框高度"""
    print("=" * 60)
    print("测试输入框高度调整逻辑")
    print("=" * 60)
    
    # 创建应用
    app = QApplication(sys.argv)
    
    # 导入聊天窗口
    from src.gui.light_chat_window import LightChatWindow
    
    # 创建窗口
    print("\n正在创建聊天窗口...")
    window = LightChatWindow()
    
    # 检查初始高度
    def check_initial_height():
        input_height = window.input_text.height()
        input_area_height = window.input_area.height()

        print(f"\n初始高度检查 (窗口显示后立即检查):")
        print(f"  输入框高度: {input_height}px")
        print(f"  输入区域高度: {input_area_height}px")
        print(f"  预期输入框高度: {window._single_line_height}px")
        print(f"  预期输入区域高度: {window._input_area_min_height}px")

        # 检查是否正确
        initial_check_passed = True
        if input_height == window._single_line_height:
            print("  ✅ 输入框高度正确（单行高度）")
        else:
            print(f"  ❌ 输入框高度错误（应为{window._single_line_height}px）")
            initial_check_passed = False

        if input_area_height == window._input_area_min_height:
            print("  ✅ 输入区域高度正确（最小高度）")
        else:
            print(f"  ❌ 输入区域高度错误（应为{window._input_area_min_height}px）")
            initial_check_passed = False

        if not initial_check_passed:
            print("\n  ⚠️ 初始高度检查失败！这是需要修复的主要问题。")
        
        # 测试输入内容后的高度调整
        print("\n测试输入内容后的高度调整...")
        window.input_text.setPlainText("测试消息")
        
        # 等待高度调整
        QTimer.singleShot(100, check_after_input)
    
    def check_after_input():
        input_height = window.input_text.height()
        input_area_height = window.input_area.height()
        
        print(f"\n输入内容后的高度:")
        print(f"  输入框高度: {input_height}px")
        print(f"  输入区域高度: {input_area_height}px")
        
        # 单行内容应该保持单行高度
        if input_height == window._single_line_height:
            print("  ✅ 输入框高度正确（单行内容保持单行高度）")
        else:
            print(f"  ⚠️ 输入框高度变化（单行内容：{input_height}px）")
        
        # 测试多行内容
        print("\n测试多行内容...")
        window.input_text.setPlainText("第一行\n第二行\n第三行")
        
        QTimer.singleShot(100, check_multiline)
    
    def check_multiline():
        input_height = window.input_text.height()
        input_area_height = window.input_area.height()
        
        print(f"\n多行内容后的高度:")
        print(f"  输入框高度: {input_height}px")
        print(f"  输入区域高度: {input_area_height}px")
        
        # 多行内容应该扩张
        if input_height > window._single_line_height:
            print("  ✅ 输入框高度正确扩张（多行内容）")
        else:
            print("  ❌ 输入框高度未扩张（多行内容应该扩张）")
        
        # 测试清空内容
        print("\n测试清空内容...")
        window.input_text.clear()
        
        QTimer.singleShot(100, check_after_clear)
    
    def check_after_clear():
        input_height = window.input_text.height()
        input_area_height = window.input_area.height()
        
        print(f"\n清空内容后的高度:")
        print(f"  输入框高度: {input_height}px")
        print(f"  输入区域高度: {input_area_height}px")
        
        # 清空后应该恢复单行高度
        if input_height == window._single_line_height:
            print("  ✅ 输入框高度正确恢复（清空后恢复单行高度）")
        else:
            print(f"  ❌ 输入框高度未恢复（应为{window._single_line_height}px）")
        
        print("\n" + "=" * 60)
        print("测试完成！")
        print("=" * 60)
        
        # 关闭应用
        QTimer.singleShot(500, app.quit)
    
    # 显示窗口
    window.show()
    
    # 延迟检查初始高度，确保窗口完全显示
    QTimer.singleShot(200, check_initial_height)
    
    # 运行应用
    sys.exit(app.exec())

if __name__ == "__main__":
    test_input_height()

