# SpritePal Project Context

SpritePal is a PySide6-based sprite extraction and editing tool for SNES ROM hacking, specifically designed for games using HAL compression (like Kirby Super Star). It provides a full "Extract → Edit → Inject" workflow with integrated palette management and Mesen 2 emulator integration.

## Project Overview

- **Main Goal:** Simplify the process of finding, extracting, modifying, and re-injecting sprites into SNES ROMs.
- **Core Workflow:**
    1. **Extract:** Pull sprites from ROM (via hex offset or Mesen 2 capture) or VRAM dumps.
    2. **Edit:** Modify pixels and palettes in a built-in sprite editor.
    3. **Inject:** Compress and write modified sprites back into the ROM or VRAM.
- **Key Technologies:**
    - **Language:** Python 3.12+
    - **UI Framework:** PySide6 (Qt for Python)
    - **Image Processing:** Pillow (PIL), NumPy
    - **Dependency Management:** `uv`
    - **Quality Tools:** `ruff` (linting), `basedpyright` (strict type checking), `pytest` (testing)

## Architecture

The project follows a modular, layered structure with explicit dependency wiring via `AppContext`. Recent refactorings (Jan 2026) have prioritized the **Law of Demeter** by introducing facade methods and reducing tight coupling.

- **`core/`**: Business logic and domain services.
    - `app_context.py`: Centralized dependency injection and lifecycle management.
    - `managers/`: Higher-level orchestration (`ApplicationStateManager`, `CoreOperationsManager`).
    - `services/`: Specialized logic (`PreviewGenerator`, `ROMCache`).
    - **New Core Utilities**: Logic extracted for testability into `hal_parser.py`, `tile_utils.py`, and `analysis_utils.py`.
    - `rom_extractor.py` & `rom_injector.py`: Core SNES/HAL logic.
- **`ui/`**: User interface components.
    - `main_window.py`: Root UI container with a modern **Dock-based layout** (QDockWidget).
    - `workspaces/`: Major functional areas (e.g., `SpriteEditorWorkspace`).
    - `controllers/`: Logic for UI interactions (e.g., `EditingController`, `ROMWorkflowController`).
    - `widgets/`: Reusable elements like `SegmentedToggle` (mode switcher) and `ElidedPathLabel`.
- **`utils/`**: Low-level helpers and constants.
- **`mesen2_integration/`**: Lua scripts and bridge logic for the Mesen 2 emulator.

## Recent Milestones (January 2026)

- **UI Redesign**: Implemented a modern IDE-like experience with Dock-based layouts, vertical output controls, and standardized margins. Replaced many QComboBoxes with `SegmentedToggle`.
- **Architectural Cleanup**: Completed project-wide Law of Demeter (LoD) refactoring, eliminating reach-through access to internal managers and services.
- **Test Infrastructure**: Migrated to `isolated_data_repository` fixture for better state isolation. Expanded UI testing to 100+ signal-driven integration tests using `MultiSignalRecorder`.
- **Enhanced ROM Workflow**: Added "Revert to Original" functionality, palette-correct sprite previews, and robust synchronization with Mesen 2 capture logs.
- **Stability**: Fixed critical bugs including `RecursionError` in `OffsetLineEdit` and thread-safety issues in error handling singletons.

## Building and Running

Commands should be executed from the `spritepal/` root directory.

- **Setup Environment:**
  ```bash
  uv sync --extra dev
  ```
- **Run Application:**
  ```bash
  uv run python launch_spritepal.py
  ```
- **Run Tests:**
  ```bash
  uv run pytest
  ```
  - Use `-n auto` for parallel execution.
  - Use `-n 0` for serial debugging.
- **Linting & Type Checking:**
  ```bash
  uv run ruff check . --fix
  uv run basedpyright core ui utils
  ```

## Development Conventions

- **Bug-First TDD**: (Mandatory) Always write a failing reproduction test before fixing a bug.
- **Type Safety**: Strict type hints required; `basedpyright` is configured in strict mode.
- **UI/Threading**: Never create `QPixmap`/`QImage` in background threads; use `ThreadSafeTestImage` in workers.
- **Law of Demeter**: Use facade methods (`get_*`, `set_*`) on parent components instead of accessing internal children directly.
- **Cleanup**: Disconnect signals in `closeEvent` using `safe_disconnect` to prevent memory leaks.

## Key Files & Entry Points

- `launch_spritepal.py`: Main application entry point.
- `pyproject.toml`: Consolidated tool configuration (Ruff, Basedpyright, Pytest).
- `CLAUDE.md`: Highly detailed development guidelines and troubleshooting.
- `AGENTS.md`: High-level guidelines for AI agents.
- `donso/AUDIT_REPORT.md`: Architectural audit identifying public contracts.
- `SPRITE_LEARNINGS_DO_NOT_DELETE.md`: Domain-specific knowledge about SNES formats.

## Search & Tooling Guidelines
- **Prefer Internal Tools:** Always use `search_file_content` or `search_for_pattern` instead of `run_shell_command("grep ...")`. These tools are optimized and automatically respect `.gitignore` and `.geminiignore`.
- **Exclude Noisy Folders:** When forced to use shell commands (`grep`, `find`, `ls`), always exclude metadata and environment folders: `.git`, `.serena`, `.venv`, `.ruff_cache`, `.pytest_cache`, and `__pycache__`.
- **Shell Example:** Use `rg` (ripgrep) which respects ignores by default, or `grep -r --exclude-dir={.git,.serena,.venv,__pycache__} "pattern" .`.
- **ripgrep:** `rg` is available in this environment.
