# Repository Guidelines (MintChat)

## Project Structure & Module Organization

MintChat is a Python 3.13+ project built on LangChain/LangGraph.

- Core code lives in `src/`:
  - `agent/`: orchestration (chat/chat_stream, memory, tools)
  - `multimodal/`: TTS/ASR/vision
  - `gui/`: PyQt6 UI (GUI entry is `MintChat.py`)
  - `auth/`: login/session flows
  - `character/`: persona data
  - `config/`: settings helpers (`src/config/settings.py`)
  - `utils/`: shared utilities
  - `version.py`: release metadata
- Demo entrypoints: `examples/`
- Scripts/helpers: `scripts/`
- Tests: `tests/` (fixtures in `tests/conftest.py`)
- Runtime artifacts: `data/`, `logs/` (git-ignored)
- Docs: `docs/`

## Environment & Package Management (uv + .venv)

This repo uses **uv** to manage dependencies and a project-local virtual environment at **`.venv/`**.

- Dependency source of truth: `pyproject.toml`
- Lockfile (commit to git): `uv.lock`
- Create/sync env:
  - `uv sync --locked --no-install-project` (runtime deps)
  - `uv sync --locked --group dev --no-install-project` (includes dev tools)
- Run commands without activating:
  - Windows: `.\.venv\Scripts\python.exe MintChat.py`
  - macOS/Linux: `./.venv/bin/python MintChat.py`

### PyTorch (CUDA / cu130)

- Windows/Linux 锁定使用 `torch==2.9.1+cu130`（PyTorch 官方索引，见 `pyproject.toml` 的 `[tool.uv.sources]` / `[[tool.uv.index]]`）。
- 验证：`.\.venv\Scripts\python.exe -c "import torch; print(torch.__version__, torch.version.cuda, torch.cuda.is_available())"`

### Optional extras

- ASR（语音识别 / FunASR）: `uv sync --locked --no-install-project --extra asr`

### Updating dependencies

1. Edit `pyproject.toml`
2. Run `uv lock`
3. Run `uv sync --locked --no-install-project` (and add `--group dev` if needed)
4. Update docs if commands/entrypoints changed

## Build, Test, and Development Commands

Preferred (no Make required):

- Install: `uv sync --locked --no-install-project`
- Dev deps: `uv sync --locked --group dev --no-install-project`
- Tests: `.\.venv\Scripts\python.exe -m pytest tests/ -v` (Windows) / `./.venv/bin/python -m pytest tests/ -v`
- Coverage: `.\.venv\Scripts\python.exe -m pytest --cov=src --cov-report=html --cov-report=term tests/` (Windows) / `./.venv/bin/python -m pytest --cov=src --cov-report=html --cov-report=term tests/`
- Format: `.\.venv\Scripts\python.exe -m black src/ tests/ examples/` (Windows) / `./.venv/bin/python -m black src/ tests/ examples/`
- Lint: `.\.venv\Scripts\python.exe -m flake8 src/ tests/ examples/ --max-line-length=100 --ignore=E203,W503` (Windows) / `./.venv/bin/python -m flake8 src/ tests/ examples/ --max-line-length=100 --ignore=E203,W503`
- Type-check: `.\.venv\Scripts\python.exe -m mypy src/ --ignore-missing-imports` (Windows) / `./.venv/bin/python -m mypy src/ --ignore-missing-imports`

Makefile shortcuts (optional): `make install`, `make dev`, `make test`, `make lint`, `make format`, `make type-check`, `make clean`.

## Coding Style & Naming Conventions

- 4-space indents; keep lines near 100 chars
- `snake_case` for modules/functions/variables, `PascalCase` for classes, `UPPER_SNAKE_CASE` for constants
- Prefer type hints and concise docstrings for public functions

## Testing Guidelines

- Pytest auto-discovers `test_*.py` and `Test*` classes under `tests/`
- Use `@pytest.mark.slow` / `@pytest.mark.integration` for long-running checks

## Configuration & Security

- `config.yaml` is **local-only** and ignored by Git. Do not commit secrets.
- Use `config.yaml.example` as the committed template.
- `.env` files are ignored; prefer env vars for sensitive overrides.

## PR / Change Hygiene

- Keep changes focused; avoid unrelated refactors.
- If you add/modify settings, update `config.yaml.example` and relevant docs.
