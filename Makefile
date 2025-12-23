.PHONY: help lock install test test-cov lint format type-check clean run run-tools run-multimodal run-gui setup-config

UV ?= uv

ifeq ($(OS),Windows_NT)
PY := .venv/Scripts/python.exe
else
PY := .venv/bin/python
endif

help:
	@echo "MintChat - 多模态猫娘女仆智能体"
	@echo ""
	@echo "可用命令:"
	@echo "  make install    - 安装运行依赖 (uv sync --no-install-project)"
	@echo "  make dev        - 安装开发依赖 (uv sync --group dev --no-install-project)"
	@echo "  make lock       - 更新 uv.lock"
	@echo "  make test       - 运行测试 (pytest)"
	@echo "  make lint       - 代码检查 (flake8)"
	@echo "  make format     - 代码格式化 (black)"
	@echo "  make type-check - 类型检查 (mypy)"
	@echo "  make clean      - 清理缓存/报告"
	@echo "  make run        - 运行基础对话示例"
	@echo "  make run-gui    - 启动 GUI (MintChat.py)"

lock:
	@$(UV) lock

sync:
	@$(UV) sync --locked --no-install-project

install: setup-config sync
	@echo "依赖安装完成！"

dev:
	@$(UV) sync --locked --group dev --no-install-project
	@echo "开发依赖安装完成！"

test: dev
	@echo "运行测试..."
	@$(PY) -m pytest tests/ -v

test-cov: dev
	@echo "运行测试并生成覆盖率报告..."
	@$(PY) -m pytest --cov=src --cov-report=html --cov-report=term tests/
	@echo "覆盖率报告已生成到 htmlcov/ 目录"

lint: dev
	@echo "运行代码检查..."
	@$(PY) -m flake8 src/ tests/ examples/ --max-line-length=100 --ignore=E203,W503
	@echo "代码检查完成！"

format: dev
	@echo "格式化代码..."
	@$(PY) -m black src/ tests/ examples/
	@echo "代码格式化完成！"

type-check: dev
	@echo "运行类型检查..."
	@$(PY) -m mypy src/ --ignore-missing-imports
	@echo "类型检查完成！"

clean:
	@echo "清理临时文件..."
	@$(UV) run --no-project --script scripts/clean.py
	@echo "清理完成！"

run: sync
	@echo "运行基础对话示例..."
	@$(PY) examples/basic_chat.py

run-tools: sync
	@echo "运行工具使用示例..."
	@$(PY) examples/tool_usage.py

run-multimodal: sync
	@echo "运行多模态示例..."
	@$(PY) examples/multimodal_demo.py

run-gui: sync
	@echo "启动 GUI..."
	@$(PY) MintChat.py

setup-config:
	@echo "设置配置文件..."
	@$(UV) run --no-project --script scripts/setup_config.py

all: format lint type-check test
	@echo "所有检查完成！"

