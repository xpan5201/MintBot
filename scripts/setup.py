"""
MintChat 安装配置
"""

from pathlib import Path

from setuptools import find_packages, setup

# 读取 README
readme_file = Path(__file__).parent / "README.md"
long_description = readme_file.read_text(encoding="utf-8") if readme_file.exists() else ""

# 读取版本号
version = "2.5.1"

setup(
    name="mintchat",
    version=version,
    author="MintChat Team",
    author_email="",
    description="多模态猫娘女仆智能体",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/yourusername/MintChat",
    packages=find_packages(exclude=["tests", "examples"]),
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.12",
    ],
    python_requires=">=3.12,<3.13",  # 测试阶段仅支持 Python 3.12
    install_requires=[
        "langchain>=1.0.0",
        "langchain-core>=1.0.0",
        "langchain-community>=1.0.0",
        "langgraph>=1.0.0",
        "langchain-openai>=1.0.0",
        "langchain-anthropic>=1.0.0",
        "langchain-google-genai>=1.0.0",
        "openai>=1.0.0",
        "pillow>=10.0.0",
        "opencv-python>=4.8.0",
        "soundfile>=0.12.0",
        "pydub>=0.25.0",
        "librosa>=0.10.0",
        "pytesseract>=0.3.10",
        "chromadb>=0.4.0",
        "faiss-cpu>=1.7.4",
        "sentence-transformers>=2.2.0",
        "pydantic>=2.0.0",
        "pydantic-settings>=2.0.0",
        "python-dotenv>=1.0.0",
        "pyyaml>=6.0",
        "requests>=2.31.0",
        "aiohttp>=3.9.0",
        "loguru>=0.7.0",
        "langsmith>=0.1.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.4.0",
            "black>=23.0.0",
            "flake8>=6.0.0",
            "mypy>=1.5.0",
            "ipython>=8.12.0",
            "jupyter>=1.0.0",
        ],
    },
)

