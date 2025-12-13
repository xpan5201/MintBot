"""
检查 MintChat 安装状态

运行此脚本以验证所有依赖是否正确安装。
"""

import sys


def check_python_version():
    """检查 Python 版本"""
    print("检查 Python 版本...")
    version = sys.version_info
    if version.major == 3 and version.minor >= 12:
        print(f"  ✓ Python {version.major}.{version.minor}.{version.micro}")
        return True
    else:
        print(f"  ✗ Python {version.major}.{version.minor}.{version.micro} (需要 3.12+)")
        return False


def check_module(module_name, package_name=None, optional=False):
    """检查模块是否安装"""
    package_name = package_name or module_name
    try:
        __import__(module_name)
        print(f"  ✓ {package_name}")
        return True
    except ImportError:
        if optional:
            print(f"  ⚠ {package_name} (可选)")
        else:
            print(f"  ✗ {package_name} (缺失)")
        return False


def main():
    """主函数"""
    print("=" * 60)
    print("MintChat 安装检查")
    print("=" * 60)
    print()

    all_ok = True

    # 检查 Python 版本
    if not check_python_version():
        all_ok = False
    print()

    # 检查核心依赖
    print("检查核心依赖...")
    core_deps = [
        ("langchain", "langchain"),
        ("langchain_core", "langchain-core"),
        ("langchain_community", "langchain-community"),
        ("langgraph", "langgraph"),
    ]
    for module, package in core_deps:
        if not check_module(module, package):
            all_ok = False
    print()

    # 检查 LLM 提供商
    print("检查 LLM 提供商...")
    llm_providers = [
        ("langchain_openai", "langchain-openai", False),
        ("langchain_anthropic", "langchain-anthropic", True),
        ("langchain_google_genai", "langchain-google-genai", True),
        ("openai", "openai", False),
    ]
    for module, package, optional in llm_providers:
        if not check_module(module, package, optional):
            if not optional:
                all_ok = False
    print()

    # 检查多模态支持
    print("检查多模态支持...")
    multimodal_deps = [
        ("PIL", "pillow", False),
        ("cv2", "opencv-python", False),
        ("soundfile", "soundfile", True),
        ("pydub", "pydub", True),
        ("librosa", "librosa", True),
    ]
    for module, package, optional in multimodal_deps:
        if not check_module(module, package, optional):
            if not optional:
                all_ok = False
    print()

    # 检查向量数据库
    print("检查向量数据库...")
    vector_deps = [
        ("chromadb", "chromadb", False),
        ("faiss", "faiss-cpu", True),
        ("sentence_transformers", "sentence-transformers", False),
    ]
    for module, package, optional in vector_deps:
        if not check_module(module, package, optional):
            if not optional:
                all_ok = False
    print()

    # 检查工具和实用程序
    print("检查工具和实用程序...")
    util_deps = [
        ("pydantic", "pydantic"),
        ("dotenv", "python-dotenv"),
        ("yaml", "pyyaml"),
        ("requests", "requests"),
        ("aiohttp", "aiohttp"),
        ("loguru", "loguru"),
    ]
    for module, package in util_deps:
        if not check_module(module, package):
            all_ok = False
    print()

    # 检查配置文件
    print("检查配置文件...")
    import os

    if os.path.exists("config.yaml"):
        print("  ✓ config.yaml")
    else:
        print("  ✗ config.yaml (缺失)")
        if os.path.exists("config.yaml.example"):
            print("    提示: 请复制 config.yaml.example 为 config.yaml")
        all_ok = False
    print()

    # 检查项目结构
    print("检查项目结构...")
    required_dirs = ["src", "examples", "docs", "data"]
    for dir_name in required_dirs:
        if os.path.exists(dir_name):
            print(f"  ✓ {dir_name}/")
        else:
            print(f"  ✗ {dir_name}/ (缺失)")
            all_ok = False
    print()

    # 总结
    print("=" * 60)
    if all_ok:
        print("✓ 所有必需依赖已安装！")
        print()
        print("下一步:")
        print("1. 编辑 config.yaml 文件，填入您的 API Key")
        print("2. 运行 run.bat (Windows) 或 ./run.sh (Linux/Mac) 启动 MintChat")
    else:
        print("✗ 部分依赖缺失")
        print()
        print("解决方案:")
        print("1. 运行 install_deps.bat (Windows) 或 ./install_deps.sh (Linux/Mac)")
        print("2. 或手动安装缺失的依赖: pip install <package-name>")
    print("=" * 60)

    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())

