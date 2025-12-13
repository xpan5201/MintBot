# Repository Guidelines

## Project Structure & Module Organization
MintChat is a Python 3.12+ project built on LangChain/LangGraph. Core code sits in `src/`: `agent/` for orchestration, `multimodal/` for TTS/STT/vision, `gui/` for the PyQt6 UI, `auth/` for login flows, `character/` for persona data, `config/` for settings helpers, `utils/` shared utilities, and `version.py` for release metadata. Demo entrypoints live in `examples/` (`basic_chat.py`, `tool_usage.py`, `multimodal_demo.py`). Tests are in `tests/` with shared fixtures in `conftest.py`. Launch helpers are in `scripts/`; runtime artifacts stay in git-ignored `data/` and `logs/`. Documentation lives in `docs/`, and the main app runner is `MintChat.py`. Keep secrets in the root `config.yaml` (ignored by Git).

## Build, Test, and Development Commands
- `conda env create -f environment.yml` then `conda activate mintchat` (or `make install`) to provision dependencies.
- `make dev` for an editable install with dev extras; `pip install -r requirements.txt` works for minimal setups.
- `python MintChat.py` to start the GUI; `make run`, `make run-tools`, and `make run-multimodal` run the example scripts in `examples/`.
- Quality gates: `make format` (black), `make lint` (flake8), `make type-check` (mypy).
- Tests: `make test` or `pytest tests/ -v`; coverage via `make test-cov` (outputs to `htmlcov/`). Cleanup temp files with `make clean`.

## Coding Style & Naming Conventions
- Use 4-space indents and keep lines near 100 chars (flake8 ignores E203/W503). Run black before committing to avoid churn.
- snake_case for modules/functions/variables, PascalCase for classes, and UPPER_SNAKE_CASE for constants.
- Prefer type hints and concise docstrings for public functions; keep modules focused on one responsibility and place shared helpers in `src/utils`.

## Testing Guidelines
- Pytest auto-discovers `test_*.py` and `Test*` classes under `tests/`; reuse fixtures in `conftest.py`.
- Mark longer checks with `@pytest.mark.slow` or integration paths with `@pytest.mark.integration`; deselect during iteration with `-m "not slow"`.
- Aim for practical coverage using `make test-cov`, and add regression tests when fixing bugs or adding utilities.

## Commit & Pull Request Guidelines
- Write concise commit messages; Conventional Commits-style prefixes (`feat`, `fix`, `docs`, `chore`, `refactor`, `test`) are preferred and can include a scope (e.g., `feat(agent): add routing guard`).
- Keep PRs focused; include a summary, rationale, and any config/API key impacts. Link issues when relevant.
- List verification steps (format/lint/tests) and attach screenshots or clips for GUI-facing changes.
- Never commit secrets or local artifacts (`config.yaml`, `data/`, `logs/`, `.env`); scrub generated files before pushing.

## Configuration & Security
- `config.yaml` is ignored by Git¡ªmaintain your own copy per machine and store provider keys there. Do not hardcode secrets in code.
- `.env` files are also ignored; use environment variables for sensitive overrides when possible.
- If you add new settings, document defaults in `src/config` and mention required keys in PR notes.
