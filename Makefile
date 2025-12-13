.PHONY: help install test lint format clean run

help:
	@echo "MintChat - 多模态猫娘女仆智能体"
	@echo ""
	@echo "可用命令:"
	@echo "  make install    - 安装项目依赖"
	@echo "  make test       - 运行测试"
	@echo "  make lint       - 代码检查"
	@echo "  make format     - 代码格式化"
	@echo "  make clean      - 清理临时文件"
	@echo "  make run        - 运行基础对话示例"
	@echo "  make dev        - 安装开发依赖"

install:
	@echo "安装项目依赖..."
	conda env create -f environment.yml || conda env update -f environment.yml
	@echo "依赖安装完成！"
	@echo "请运行: conda activate mintchat"

dev:
	@echo "安装开发依赖..."
	pip install -e ".[dev]"
	@echo "开发依赖安装完成！"

test:
	@echo "运行测试..."
	pytest tests/ -v

test-cov:
	@echo "运行测试并生成覆盖率报告..."
	pytest --cov=src --cov-report=html --cov-report=term tests/
	@echo "覆盖率报告已生成到 htmlcov/ 目录"

lint:
	@echo "运行代码检查..."
	flake8 src/ tests/ examples/ --max-line-length=100 --ignore=E203,W503
	@echo "代码检查完成！"

format:
	@echo "格式化代码..."
	black src/ tests/ examples/
	@echo "代码格式化完成！"

type-check:
	@echo "运行类型检查..."
	mypy src/ --ignore-missing-imports
	@echo "类型检查完成！"

clean:
	@echo "清理临时文件..."
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	rm -rf htmlcov/ .coverage 2>/dev/null || true
	@echo "清理完成！"

run:
	@echo "运行基础对话示例..."
	python examples/basic_chat.py

run-tools:
	@echo "运行工具使用示例..."
	python examples/tool_usage.py

run-multimodal:
	@echo "运行多模态示例..."
	python examples/multimodal_demo.py

setup-config:
	@echo "设置配置文件..."
	@if [ ! -f config.yaml ]; then \
		cp config.yaml.example config.yaml; \
		echo "config.yaml 文件已创建，请编辑并填入您的 API Key"; \
	else \
		echo "config.yaml 文件已存在"; \
	fi

all: format lint type-check test
	@echo "所有检查完成！"

