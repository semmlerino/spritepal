# Repository Guidelines

## Project Structure & Module Organization
- `core/`: business logic, managers, protocols. Core should only import from `utils/`.
- `ui/`: PySide6 widgets, dialogs, and workers; UI may import from `core/` and `utils/`.
- `utils/`: shared helpers (stdlib-only imports).
- `tests/`: pytest suite, fixtures, and infrastructure (e.g., thread-safe test images).
- `docs/`, `examples/`, `benchmarks/`, `scripts/`, `tools/`: guidance and tooling.
- `roms/`, `extracted_sprites/`: local test assets; do not add new copyrighted ROMs.

## Build, Test, and Development Commands
Run from `spritepal/`:
- `uv sync --extra dev` installs dev dependencies.
- `uv run python launch_spritepal.py` starts the app.
- `uv run pytest` runs the suite (parallel by default).
- `uv run pytest -n 0 tests/path/test_file.py::test_name` runs a single test serially.
- `uv run ruff check .` lints; add `--fix` for auto-fixes.
- `uv run basedpyright core ui utils` runs strict type checks.

## Coding Style & Naming Conventions
- Python 3.12+, 4-space indents, 120-char lines (Ruff config in `pyproject.toml`).
- Prefer type hints everywhere; use `| None` for optionals and annotate Qt signals.
- Naming: modules/functions in `snake_case`, classes in `PascalCase`, tests as `test_*.py`, `Test*` classes, `test_*` functions.

## Testing Guidelines
- Frameworks: `pytest`, `pytest-qt`, `pytest-xdist` (default `-n auto`).
- Use `isolated_managers` unless `session_managers` is required with `@pytest.mark.shared_state_safe`.
- Avoid `time.sleep()`; use `qtbot.wait()`/`waitSignal()` context managers.
- Never create `QPixmap` in worker threads; use `ThreadSafeTestImage` instead.

## Commit & Pull Request Guidelines
- Commit messages follow Conventional Commits: `fix: ...`, `refactor: ...`, `docs: ...`, with optional scopes (e.g., `refactor(dialogs): ...`).
- PRs should include a short summary, tests run (or why skipped), and screenshots for UI changes.
- Call out any ROM/test data dependencies and avoid adding copyrighted ROMs.

## Configuration & Environment
- Tooling config lives in `pyproject.toml` (ruff, basedpyright, pytest).
- Useful vars: `PYTEST_TIMEOUT_MULTIPLIER`, `SPRITEPAL_EXHAL_PATH`, `SPRITEPAL_INHAL_PATH`, `SPRITEPAL_LEAK_MODE`. Tests set `QT_QPA_PLATFORM=offscreen`.
