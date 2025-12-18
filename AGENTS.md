# Repository Guidelines

## Project Structure & Module Organization

- `main.py`: entrypoint for the multi-round MCQ generation workflow.
- `utils/config.py`: runtime configuration (models, rounds, log path).
- `utils/api_client.py`: OpenAI-compatible client helpers (vision/text calls).
- `prompts/`: prompt builders for each stage.
- `pipeline/`: episode orchestration, solvers, logging.
- `steps/`: per-round step loop (prompt-driven / graph mode).
- `graph/`: local KG + path sampling (graph mode).
- `utils/parsing.py`: response parsing (`<question>`, `<answer>`, option letter).
- `utils/schema.py`: shared data types (`StageResult` etc).
- Assets: `test.png` (input image), `context.txt` (reference text), output log defaults to `question_log.jsonl`.
- Local environment: `env/` may contain a local virtual environment; don’t commit `__pycache__/` changes.

## Build, Test, and Development Commands

- Run the workflow: `python main.py`
  - Reads `test.png`, generates questions for up to `MAX_ROUNDS`, and appends results to `QUESTION_LOG_PATH`.
- Quick syntax check: `python -m py_compile $(ls *.py pipeline/*.py steps/*.py graph/*.py prompts/*.py utils/*.py | tr '\n' ' ')`
- (Optional) create/use a venv:
  - Create: `python -m venv .venv`
  - Activate: `source .venv/bin/activate`
  - Install deps (example): `pip install openai`

## Coding Style & Naming Conventions

- Python 3.10+ (uses `X | None` union types).
- Indentation: 4 spaces; keep functions small and single-purpose.
- Naming: modules `snake_case.py`, functions `snake_case`, constants `UPPER_SNAKE_CASE`.
- Prefer type hints on public functions and data structures.

## Testing Guidelines

- No formal test suite is included yet.
- For changes, at minimum run `python -m py_compile ...` and do a manual smoke run (`python main.py`) when network access/credentials are available.
- If tests are added later, place them under `tests/` and prefer `pytest` with names like `tests/test_pipeline.py`.

## Commit & Pull Request Guidelines

- Current history uses short, descriptive messages (e.g., `Initial commit`, `文件拆分`). Keep commits concise and task-focused.
- PRs should include: summary, how to run/verify (`python main.py`), and any config/env changes.
- Avoid committing secrets. Prefer providing API keys via environment variables, not source code.
