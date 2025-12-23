"""
修复 pkg_resources 弃用警告 - v2.53.2

pkg_resources 是 setuptools 的旧 API，已被弃用。
本脚本升级 setuptools 到最新版本以消除警告。

参考: https://setuptools.pypa.io/en/latest/pkg_resources.html
"""

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent


def upgrade_setuptools():
    """升级 setuptools 到最新版本"""
    print("=" * 70)
    print("  修复 pkg_resources 弃用警告")
    print("=" * 70)
    print()
    
    print("📦 升级 setuptools 到最新版本...")
    try:
        result = subprocess.run(
            [sys.executable, '-m', 'pip', 'install', '--upgrade', 'setuptools'],
            capture_output=True,
            text=True,
            timeout=60
        )
        
        if result.returncode == 0:
            print("✅ setuptools 升级成功")
            print()
            print("输出:")
            print(result.stdout)
        else:
            print("❌ setuptools 升级失败")
            print()
            print("错误:")
            print(result.stderr)
            return False
            
    except Exception as e:
        print(f"❌ 升级失败: {e}")
        return False
    
    print()
    print("=" * 70)
    print("  验证修复")
    print("=" * 70)
    print()
    
    # 验证 setuptools 版本
    try:
        result = subprocess.run(
            [sys.executable, '-m', 'pip', 'show', 'setuptools'],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0:
            for line in result.stdout.split('\n'):
                if line.startswith('Version:'):
                    version = line.split(':', 1)[1].strip()
                    print(f"✅ setuptools 当前版本: {version}")
                    break
        
    except Exception as e:
        print(f"⚠️ 无法验证版本: {e}")
    
    print()
    print("=" * 70)
    print("  修复完成")
    print("=" * 70)
    print()
    print("说明:")
    print("- pkg_resources 是 setuptools 的旧 API，已被弃用")
    print("- 升级到最新版本的 setuptools 可以消除此警告")
    print("- 如果警告仍然存在，可能来自其他依赖包")
    print("- 这个警告不会影响 MintChat 的功能")
    print()
    
    return True


def main():
    """主函数"""
    success = upgrade_setuptools()
    
    if success:
        print("🎉 修复成功！")
        print()
        print("下一步:")
        print("1. 重启 MintChat")
        print("2. 如果警告仍然存在，请忽略它（不影响功能）")
        print()
    else:
        print("❌ 修复失败")
        print()
        print("手动修复:")
        print("  uv sync --locked --no-install-project")
        print("  uv pip install --upgrade setuptools")
        print()
     
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())

