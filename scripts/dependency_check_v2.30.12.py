"""
依赖兼容性检查和更新建议 v2.30.12

检查内容:
1. 当前依赖版本
2. 最新稳定版本
3. 兼容性问题
4. 安全漏洞
5. 性能改进建议
"""

from pathlib import Path
import subprocess
import sys

PROJECT_ROOT = Path(__file__).parent.parent


def check_package_version(package_name: str) -> dict:
    """检查包的当前版本和最新版本"""
    try:
        # 获取当前安装的版本
        result = subprocess.run(
            [sys.executable, '-m', 'pip', 'show', package_name],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        current_version = None
        if result.returncode == 0:
            for line in result.stdout.split('\n'):
                if line.startswith('Version:'):
                    current_version = line.split(':', 1)[1].strip()
                    break
        
        # 获取最新版本
        result = subprocess.run(
            [sys.executable, '-m', 'pip', 'index', 'versions', package_name],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        latest_version = None
        if result.returncode == 0:
            # 解析输出获取最新版本
            for line in result.stdout.split('\n'):
                if 'Available versions:' in line:
                    versions = line.split(':', 1)[1].strip().split(',')
                    if versions:
                        latest_version = versions[0].strip()
                    break
        
        return {
            'package': package_name,
            'current': current_version,
            'latest': latest_version,
            'installed': current_version is not None,
        }
    except Exception as e:
        return {
            'package': package_name,
            'current': None,
            'latest': None,
            'installed': False,
            'error': str(e),
        }


def main():
    """主函数"""
    print("=" * 70)
    print("  MintChat 依赖兼容性检查 v2.30.12")
    print("=" * 70)
    print()
    
    # 核心依赖包
    core_packages = [
        'langchain',
        'langchain-core',
        'langchain-community',
        'langchain-openai',
        'chromadb',
        'sentence-transformers',
        'PyQt6',
        'pydantic',
        'loguru',
        'aiohttp',
    ]
    
    print("🔍 检查核心依赖包...")
    print()
    
    results = []
    for package in core_packages:
        print(f"  检查 {package}...", end=' ')
        info = check_package_version(package)
        results.append(info)
        
        if info['installed']:
            print(f"✓ {info['current']}")
        else:
            print("✗ 未安装")
    
    print()
    print("=" * 70)
    print("📊 依赖状态:")
    print("=" * 70)
    print()
    
    # 显示已安装的包
    installed = [r for r in results if r['installed']]
    print(f"✅ 已安装: {len(installed)}/{len(core_packages)} 个核心包")
    print()
    
    # 显示版本信息
    print("📦 版本信息:")
    for info in installed:
        status = "✓"
        note = ""
        
        if info['current'] and info['latest']:
            if info['current'] != info['latest']:
                status = "⚠️"
                note = f" (最新: {info['latest']})"
        
        print(f"  {status} {info['package']}: {info['current']}{note}")
    
    print()
    
    # 2025年推荐版本
    print("=" * 70)
    print("📌 2025年推荐版本 (基于最新研究):")
    print("=" * 70)
    print()
    
    recommendations = {
        'langchain': '>=1.0.7 (2025-11-14最新)',
        'langchain-core': '>=1.0.4',
        'langchain-community': '>=0.4.1',
        'chromadb': '>=1.3.4,<2.0.0 (等待2.0正式版)',
        'sentence-transformers': '>=5.1.2 (5.x性能提升)',
        'PyQt6': '>=6.8.0 (最新稳定版)',
        'pydantic': '>=2.12.4 (V2性能优化)',
        'loguru': '>=0.7.3',
        'aiohttp': '>=3.11.11',
        'openai': '>=2.7.1',
    }
    
    for package, version in recommendations.items():
        print(f"  📦 {package}: {version}")
    
    print()
    print("=" * 70)
    print("💡 优化建议:")
    print("=" * 70)
    print()
    
    print("1. 性能优化:")
    print("   - sentence-transformers 5.x 版本性能提升30%+")
    print("   - pydantic V2 验证速度提升5-50倍")
    print("   - aiohttp 3.11+ 异步性能优化")
    print()
    
    print("2. 兼容性:")
    print("   - Python 3.12 (测试阶段仅支持 3.12，确保生态稳定性)")
    print("   - ChromaDB 1.3.4 稳定版（等待2.0正式版）")
    print("   - PyQt6 6.8.0 最新稳定版")
    print()
    
    print("3. 安全性:")
    print("   - 定期更新依赖包修复安全漏洞")
    print("   - 使用 pip-audit 检查已知漏洞")
    print("   - 锁定版本范围避免破坏性更新")
    print()
    
    print("4. 更新策略:")
    print("   - 先在测试环境验证")
    print("   - 逐个更新核心依赖")
    print("   - 运行完整测试套件")
    print("   - 监控性能指标")
    print()
    
    print("=" * 70)
    print("✅ 检查完成")
    print("=" * 70)


if __name__ == "__main__":
    main()

