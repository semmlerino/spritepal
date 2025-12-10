# SpritePal Context for Gemini

## Project Overview
**SpritePal** is a Python-based tool for extracting, editing, and injecting sprites for SNES ROM hacks, specifically targeting HAL compression formats (e.g., Kirby Super Star). It utilizes **PySide6** for the GUI and **uv** for dependency management.

## Environment & Setup
- **OS**: Linux (current context)
- **Python**: 3.11+
- **Package Manager**: `uv` (Universal Package Manager)
- **GUI Framework**: PySide6
- **Configuration**: `pyproject.toml` is the single source of truth for build, linting, and testing config.

## Key Commands

All commands should be run from the project root (`spritepal/` or `exhal-master/`).

### Running the Application
```bash
# Using uv to run the inline script provided in README or the launcher
uv run python launch_spritepal.py
```

### Testing
**Crucial:** Always use `QT_QPA_PLATFORM=offscreen` to avoid display dependency issues in headless environments.

```bash
# Run all tests (fast fail)
QT_QPA_PLATFORM=offscreen uv run pytest tests --maxfail=1 --tb=short

# Run specific subsets
QT_QPA_PLATFORM=offscreen uv run pytest tests -m "headless and not slow"  # Fast tests
QT_QPA_PLATFORM=offscreen uv run pytest tests -m "gui"                    # GUI tests

# Debug a specific test with full traceback
QT_QPA_PLATFORM=offscreen uv run pytest tests/path/to/test.py -vv --tb=long
```

### Code Quality
```bash
# Linting (Ruff)
uv run ruff check .
uv run ruff check . --fix  # Auto-fix

# Type Checking (Basedpyright - Strict)
uv run basedpyright core ui utils
```

## Architecture & Conventions

### Directory Structure
- `core/`: Business logic, managers, extractors, HAL compression.
- `ui/`: PySide6 widgets, windows, dialogs.
- `utils/`: Shared utilities (logging, geometry, etc.).
- `tests/`: Pytest suite (see Testing Strategy).

### Coding Standards
- **Typing**: strict compliance required (checked by `basedpyright`).
- **Imports**:
    - UI -> Core/Managers/Utils
    - Managers -> Core/Utils
    - Core -> Utils
    - Utils -> Stdlib only
    - *Avoid circular imports by using local imports inside methods if necessary.*
- **Resource Management**: Use context managers (`with` statements) for file I/O and mmap operations.

### Testing Strategy
- **Preference**: Use **Real Components** (`RealComponentFactory`) over mocks whenever possible. Mock only system boundaries (IO, Network).
- **Qt Testing**:
    - Use `qtbot` fixture.
    - **Never** inherit from `QDialog` in mocks (causes crashes).
    - Use `ThreadSafeTestImage` instead of `QPixmap` in worker threads.
    - Avoid `time.sleep()`; use `qtbot.waitSignal()` or `qtbot.wait()`.
- **Fixtures**:
    - `session_managers`: Shared state (faster, risk of pollution).
    - `isolated_managers`: Clean state per test (safer).

## Current Focus
The project is currently working on **Mesen2 Emulator Integration** for improved sprite finding.
- Refer to `NEXT_STEPS_PLAN.md` for the immediate roadmap.
- Refer to `SPRITE_LEARNINGS_DO_NOT_DELETE.md` for extraction logic details.

## Important Documentation
- `CLAUDE.md`: Detailed developer guidelines and testing patterns.
- `docs/architecture.md`: Architectural details.
- `TESTING_DEBUG_GUIDE_DO_NOT_DELETE.md`: Debugging strategies.
