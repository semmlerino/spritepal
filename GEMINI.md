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

The project follows a modular structure with explicit dependency wiring via `AppContext`.

- **`core/`**: Business logic and domain services.
    - `app_context.py`: Centralized dependency injection and lifecycle management.
    - `managers/`: Higher-level orchestration (e.g., `ApplicationStateManager`, `CoreOperationsManager`).
    - `services/`: Specialized logic (e.g., `PreviewGenerator`, `ROMCache`).
    - `rom_extractor.py` & `rom_injector.py`: Core SNES/HAL logic.
- **`ui/`**: User interface components.
    - `main_window.py`: Root UI container and mode switcher.
    - `workspaces/`: Major functional areas (e.g., `SpriteEditorWorkspace`).
    - `controllers/`: Logic for UI interactions (e.g., `EditingController`, `ROMWorkflowController`).
    - `widgets/`, `dialogs/`, `components/`: Reusable UI elements.
- **`utils/`**: Low-level helpers and constants.
- **`mesen2_integration/`**: Lua scripts and bridge logic for the Mesen 2 emulator.

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
  - Use `-n auto` for parallel execution (default in `pyproject.toml`).
  - Use `-n 0` for serial debugging.
  - Tests run in `offscreen` mode by default.
- **Linting:**
  ```bash
  uv run ruff check .
  uv run ruff check . --fix
  ```
- **Type Checking (Strict):**
  ```bash
  uv run basedpyright core ui utils
  ```

## Development Conventions

- **Type Safety:** Use strict type hints everywhere. `basedpyright` is configured in strict mode.
- **Coding Style:**
    - 4-space indentation, 120-character line limit.
    - `snake_case` for functions/variables, `PascalCase` for classes.
    - Qt conventions: UI widgets and signals often use `camelCase` to match Qt's API; Ruff is configured to allow this in UI code.
- **UI/Threading:**
    - **NEVER** create or manipulate `QPixmap` or `QImage` in background threads (leads to crashes). Use `PIL.Image` in workers and convert to `QPixmap` in the main thread using `pil_to_qpixmap`.
    - Use `AppContext` to access shared services rather than global singletons where possible.
- **Testing:**
    - Use `pytest-qt` for GUI testing.
    - Prefer `isolated_managers` fixture to avoid state leakage between tests.
    - Use `@pytest.mark.shared_state_safe` only when `session_managers` is absolutely necessary.
    - Avoid `time.sleep()`; use `qtbot.wait_signal()` or `qtbot.wait_until()`.
- **Error Handling:** Use the centralized `ErrorHandler` in `ui/common/error_handler.py` for consistent user feedback.

## Operational Guidelines

- **Search and Grep:** When searching the codebase (using `grep`, `ripgrep`, or `search_file_content`), always exclude hidden directories that contain metadata, caches, or environments.
    - Specifically exclude: `.serena/`, `.pytest_cache/`, `.ruff_cache/`, `.uv_cache/`, `.venv/`, `.git/`.
    - Example: `grep -r "pattern" . --exclude-dir={.serena,.pytest_cache,.ruff_cache,.uv_cache,.venv,.git}`

## Key Files & Entry Points

- `launch_spritepal.py`: Main application entry point.
- `pyproject.toml`: Tool configuration (Ruff, Basedpyright, Pytest) and dependencies.
- `AGENTS.md`: High-level guidelines for AI agents working on this repo.
- `AUDIT_REPORT.md`: Architectural audit identifying public contracts and boundaries.
- `REDESIGN_PLAN.md`: Roadmap and history of UI/UX improvements.
- `SPRITE_LEARNINGS_DO_NOT_DELETE.md`: Domain-specific knowledge about SNES formats and compression.
