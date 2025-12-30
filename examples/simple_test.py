"""
简单测试 - 验证核心功能

此脚本仅测试核心功能，不依赖可选的依赖包。
"""

import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

print("=" * 60)
print("MintChat 简单测试")
print("=" * 60)
print()

# 测试 1: 导入核心模块
print("1. 测试导入核心模块...")
try:
    from src.config.settings import settings

    print("   ✓ 配置系统")
except Exception as e:
    print(f"   ✗ 配置系统: {e}")
    sys.exit(1)

try:
    from src.character import personality  # noqa: F401

    print("   ✓ 角色系统")
except Exception as e:
    print(f"   ✗ 角色系统: {e}")
    sys.exit(1)

try:
    from src.character.config_loader import CharacterConfigLoader

    print("   ✓ 角色配置加载器")
except Exception as e:
    print(f"   ✗ 角色配置加载器: {e}")
    sys.exit(1)

try:
    from src.utils.performance import PerformanceMonitor

    print("   ✓ 性能监控")
except Exception as e:
    print(f"   ✗ 性能监控: {e}")
    sys.exit(1)

print()

# 测试 2: 配置加载
print("2. 测试配置加载...")
try:
    print(f"   ✓ 角色名称: {settings.agent.char}")
    print(f"   ✓ 主人名称: {settings.agent.user}")
    print(f"   ✓ LLM 模型: {settings.llm.model}")
except Exception as e:
    print(f"   ✗ 配置加载失败: {e}")
    sys.exit(1)

print()

# 测试 3: 角色配置
print("3. 测试角色配置...")
try:
    config = CharacterConfigLoader.load_character_settings()
    print("   ✓ 角色配置加载成功")
    print(f"   ✓ 角色名称: {config['name']}")

    prompt = CharacterConfigLoader.generate_system_prompt()
    print(f"   ✓ 生成提示词 ({len(prompt)} 字符)")

    greeting = CharacterConfigLoader.get_greeting()
    print(f"   ✓ 问候语: {greeting[:50]}...")
except Exception as e:
    print(f"   ✗ 角色配置失败: {e}")
    sys.exit(1)

print()

# 测试 4: 性能监控
print("4. 测试性能监控...")
try:
    monitor = PerformanceMonitor()

    # 记录一些测试数据
    monitor.record_metric("test", 1.0)
    monitor.record_metric("test", 2.0)
    monitor.record_metric("test", 1.5)

    stats = monitor.get_stats("test")
    print(f"   ✓ 记录指标: {stats['count']} 次")
    print(f"   ✓ 平均值: {stats['avg']:.2f}")
except Exception as e:
    print(f"   ✗ 性能监控失败: {e}")
    sys.exit(1)

print()

# 测试 5: Agent 导入（不创建实例）
print("5. 测试 Agent 导入...")
try:
    from src.agent import core  # noqa: F401

    print("   ✓ Agent 模块导入成功")
    print("   ⚠ 注意: 需要安装所有依赖才能创建 Agent 实例")
except Exception as e:
    print(f"   ✗ Agent 导入失败: {e}")
    print(f"   错误详情: {e}")
    sys.exit(1)

print()

# 总结
print("=" * 60)
print("✓ 核心功能测试通过！")
print()
print("下一步:")
print("1. 运行 install_deps.bat (Windows) 或 ./install_deps.sh (Linux/Mac)")
print("   安装所有依赖")
print("2. 编辑 config.user.yaml 文件，填入您的 API Key")
print("3. 运行 run.bat (Windows) 或 ./run.sh (Linux/Mac) 启动 MintChat")
print("=" * 60)
