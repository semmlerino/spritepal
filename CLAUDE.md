# SpritePal Development Guidelines

**Last updated: January 25, 2026** | See [Table of Contents](#table-of-contents) below

**What is SpritePal?** A PySide6 desktop app for editing SNES sprite graphics. Key workflows: Extract sprites from ROM → Edit in pixel editor → Inject back. Also supports AI-assisted frame mapping for sprite animation replacement.

---

## TL;DR - Essential Rules (Read This First)

**1. Environment:**
- **Framework**: PySide6 | **Python**: 3.12+ | **Package Manager**: uv | **Config**: `pyproject.toml`
- **Workflow**: `ruff check . && ruff format . && basedpyright core ui utils && pytest` → then **commit**

**2. Critical Don'ts** (⚠️ Will crash or fail tests):
| ❌ Don't | ✅ Do Instead |
|---------|-------------|
| `QPixmap` in worker threads | Use `ThreadSafeTestImage` |
| Inherit `QDialog` in mocks | Use `QObject` with signals |
| Hardcode paths like `/tmp/test_output` | Use `tmp_path` fixture |
| `time.sleep()` in Qt tests | Use `qtbot.wait(ms)` or `qtbot.waitSignal()` |
| Non-context `waitSignal()` | Always: `with qtbot.waitSignal(signal, timeout=...)` |
| Mock at wrong location | `@patch('spritepal.ui.panel.Dialog')` not `...dialogs.Dialog` |
| Multiple `QApplication` instances | Let pytest-qt manage via `qtbot`/`qapp` fixtures |
| `if pos:` for QPoint checks | Use `if pos is not None:` (QPoint(0,0) is falsy!) |
| `gc.collect()` in Qt cleanup paths | Skip gc.collect(); use deleteLater() + processEvents() |

**3. Testing** (when running tests):
- Default: serial for fast TDD iteration
- **Full suite**: `pytest -n auto --dist=loadscope` for parallel execution
- **Flaky?** If serial passes but parallel fails → race condition
- **Quick triage**: `pytest --tb=no -q 2>&1 | tee /tmp/pytest_triage.log` then `pytest --lf -vv`

**4. Fixtures** (when writing tests):
- Use `app_context` by default (clean state per-test)
- Use `session_app_context` only with `@pytest.mark.shared_state_safe`
- Key imports: `from tests.fixtures.timeouts import worker_timeout`

**5. Code Patterns**:
- **Managers**: Access via `AppContext` (e.g., `context.core_operations_manager`), never instantiate directly
- **Imports**: UI imports core/utils; Core imports utils only
- **Behavior changes**: If affecting threading, signals, IO, persistence, or settings → add/adjust tests
- **DI order**: UI creation happens before manager creation; use deferred injection with setters

**6. Bug Reports → Test First** (⚠️ MANDATORY):
- **When user reports a bug:** Write a failing test BEFORE fixing it
- **Workflow:** Reproduce bug → Write failing test → Verify it fails → Fix code → Test passes

**7. Launch App:**
```bash
uv run python launch_spritepal.py
```

**→ For full details, jump to relevant section below**

---

## Table of Contents

1. [Core Principles](#core-principles) — Philosophy behind the codebase
2. [Development Workflow](#development-workflow) — Day-to-day commands and checks
3. [Testing Guide](#testing-guide) — Running, writing, and debugging tests
4. [Code Patterns & Architecture](#code-patterns--architecture) — Design patterns and import rules
5. [Reference](#reference) — Key files, managers, fixtures
6. [Mesen 2 Integration](#mesen-2-integration) — Sprite capture tool (quick start only)
7. [Known Limitations](#known-limitations) — Documented constraints and workarounds
8. [Advanced Topics](#advanced-topics) — Detailed debugging, type checking, UI screenshots

---

## Core Principles

1. **🚨 Bug reports → failing test FIRST** - When the user reports a bug, write a failing test that reproduces it BEFORE attempting any fix. Workflow: understand bug → write failing test → verify it fails correctly → fix code → test passes. Skipping this has repeatedly led to "fixes" that don't actually address the bug.

2. **Fix bugs, not tests** - Bias toward fixing defects in implementation, not making tests pass by dilution. Don't relax, delete, or rewrite tests unless demonstrably incorrect. When uncertain: run test in isolation, trace actual vs expected, verify expectation matches intended behavior.

3. **Test logic more than widgets** - Put business logic in plain Python classes so tests stay fast and stable. Keep widget tests focused on wiring, signals, and basic interactions.

4. **Tests: serial for TDD, parallel for full suite** - Default (`pytest`) runs serial for fast iteration. Full suite (`pytest -n auto --dist=loadscope`) runs parallel. With 2400+ tests, parallel cuts 15+ minutes to ~3 minutes.

5. **Prefer boring determinism** - The fastest dev loop is: small change → run checks → commit.

**Critical "Don'ts" explained** (from TL;DR table):
- `QPixmap` crash: Qt GUI objects aren't thread-safe. "Fatal Python error: Aborted" with no stack trace = this.
- `waitSignal()` race: Without context manager, signal may emit before wait starts. Always `with qtbot.waitSignal(...):`.
- Mock location: Python patches at import site, not definition site. Trace where `from X import Y` happens.

---

## Development Workflow

### Code Quality Check (Always Do This)

**One canonical sequence before committing:**

```bash
uv run ruff check .              # Lint
uv run ruff format .             # Format
uv run basedpyright core ui utils  # Type check
uv run pytest                    # Run tests (serial, fast for TDD)
# Or for full suite: uv run pytest -n auto --dist=loadscope
```

**Note:** If `uv` is not in PATH, use `~/.local/bin/uv run` as fallback (e.g., `~/.local/bin/uv run ruff check .`).

**No silent behavior changes:** If a change affects threading, signals, IO, persistence, or settings → add/adjust tests.

### Definition of Done & Committing

A task is complete **only when** all checks pass AND changes are committed. Uncommitted changes = incomplete task.

**Commit workflow:**
1. Run all checks: `ruff check . && ruff format . && basedpyright core ui utils && pytest`
2. Review: `git status` / `git diff`
3. Stage: `git add <specific files>` (avoid `git add .`)
4. Commit: `/commit` or `git commit -m "fix: description"`
5. Verify: `git status` shows clean working directory

**Conventional commit prefixes:** `fix:`, `feat:`, `refactor:`, `chore:`, `test:`, `docs:`

**Never commit if:** checks fail, tests are flaky (verify with `pytest -n 0`), or behavior changed without test coverage.

### Environment Setup

```bash
uv sync              # Sync from lockfile
uv sync --extra dev  # Include dev dependencies
uv lock              # Update lockfile after dependency changes
```

---

## Testing Guide

**Comprehensive guide:** [docs/testing_guide.md](docs/testing_guide.md) | **Fixture reference:** [tests/README.md](tests/README.md)

### Quick Commands (Copy-Paste Friendly)

| Goal | Command |
|------|---------|
| **Quick pass/fail summary** | `pytest --tb=no -q 2>&1 \| tee /tmp/pytest_triage.log` |
| **Re-run failures with details** | `pytest --lf -vv --tb=short` |
| **Drill down on one test** | `pytest tests/path/test_file.py::test_name -vv --tb=long -s` |
| **Find slow tests** | `pytest --durations=20` |
| **Filter by pattern** | `pytest -k "extraction and not slow" -vv` |
| **Stop on first failure** | `pytest -x -vv` |
| **Full suite (parallel)** | `pytest -n auto --dist=loadscope` |

**Note:** Pytest buffers output. Always `tee` to file first for large runs.

### Fast Test Runs (Performance Optimization)

Use these selectors to skip heavy Qt/integration fixtures for faster TDD cycles:

```bash
# Pure unit tests (fastest TDD loop - skips Qt and manager overhead)
pytest tests/unit/ -q

# Non-GUI tests only
pytest -m "not gui" -q

# Quick smoke test (stop on first failure)
pytest tests/unit/ -m "not slow" --maxfail=1 -q

# Specific subsystem unit tests
pytest tests/unit/core/ -q       # Core logic only
pytest tests/unit/utils/ -q      # Utils only
```

**Why these are faster:**
- Unit tests in `tests/unit/` don't trigger Qt fixtures or manager initialization
- The `-q` flag reduces output overhead
- Skipping `gui` marker avoids QApplication setup/teardown

### Writing Tests

**Quick template:**
```python
from tests.fixtures.timeouts import worker_timeout

def test_my_feature(app_context, tmp_path):
    """One-line description."""
    manager = app_context.core_operations_manager
    output_file = tmp_path / "output.bin"
    result = manager.some_method()
    assert result is not None

# Signal wait - ALWAYS use context manager
def test_async_op(qtbot, app_context):
    worker = MyWorker()
    with qtbot.waitSignal(worker.finished, timeout=worker_timeout()):
        worker.start()
```

**Key imports:**
```python
from tests.fixtures.timeouts import worker_timeout, signal_timeout, ui_timeout, LONG
from tests.infrastructure.thread_safe_test_image import ThreadSafeTestImage
from tests.infrastructure.real_component_factory import RealComponentFactory
```

**Fixture decision tree:**
- **`app_context`** - Default for unit tests. Provides clean Qt state + managers per-test. Use this 95% of the time.
- **`session_app_context`** - Only with `@pytest.mark.shared_state_safe`. For tests that need to share state across runs.
- **`tmp_path`** - Always for file operations. Never hardcode paths.
- **`qtbot`** - For Qt signal/widget testing.

### Parallel Execution

Default `pytest` runs serial (fast TDD iteration). Full suite uses parallel:

```bash
pytest -n auto --dist=loadscope   # Parallel execution (~3 min vs 15+ serial)
```

- `--dist=loadscope` groups tests by module
- `@pytest.mark.parallel_unsafe` or `xdist_group("serial")` for tests needing isolation (note: only prevents concurrent execution, doesn't guarantee true isolation)

### Custom CLI Options (in conftest.py)

```bash
pytest --use-real-hal -v              # Use real HAL binaries instead of mocks
pytest --require-real-hal -v          # Fail if HAL binaries not found
pytest --leak-mode=warn               # Warn on leaks (default local)
pytest --leak-mode=fail               # Fail on leaks (default CI)
pytest tests/test_hal_golden.py --regenerate-golden -v  # Update golden checksums
```

### UI Integration Tests

Signal-driven workflow tests in `tests/ui/integration/` verify observable Qt behavior through public APIs (100+ tests):
- Mouse/canvas interactions (PixelCanvas, hover, zoom)
- Tool selection and icon toolbar signals
- Color/palette selection
- Sprite asset browser selection
- Extract/Inject workflow signals
- ROM workflow integration
- Multi-component signal ordering

Use `helpers/signal_spy_utils.py:MultiSignalRecorder` to track and validate multiple signal emissions with order verification.

### Debugging Failed Tests

| Symptom | Solution |
|---------|----------|
| **Flaky (sometimes passes)** | Run serial (default) first; if passes but fails with `-n auto` → race condition. Check: non-context `waitSignal()`, hardcoded timeouts, `tmp_path` usage |
| **"Fatal Python error: Aborted"** | `QPixmap` in worker thread. Replace with `ThreadSafeTestImage` |
| **Hangs forever** | Ctrl-C → `--full-trace`. Check: dialog mocking `exec()`, worker cleanup in fixture teardown |
| **Passes locally, fails in CI** | Usually timeout. Check `PYTEST_TIMEOUT_MULTIPLIER` or display requirements (offscreen is default) |

---

## Code Patterns & Architecture

### Import Rules (Enforce These)

```
UI ──→ Core ──→ Utils ──→ Stdlib only
        ↓
      (Core can only import Utils)
```

- **UI** imports: core, utils, PySide6
- **Core** imports: utils, stdlib (no UI)
- **Utils** imports: stdlib only

### Dependency Injection Order

`MainWindow.__init__()` creates UI BEFORE services. Use deferred injection:

```python
# In _create_workspaces() - service doesn't exist yet
workspace = SpriteEditorWorkspace(message_service=None)

# In _setup_managers() - now inject
workspace.set_message_service(status_bar_manager)

# Setter cascades through children
def set_message_service(self, service):
    self._message_service = service
    for child in self.children:
        child.set_message_service(service)
```

**Before refactoring DI:** Trace `__init__` → `_setup_ui()` → `_setup_managers()` order.

### Manager Access (Production Code)

Never instantiate managers directly. Access via `AppContext`:

```python
from core.app_context import get_app_context

context = get_app_context()
state_mgr = context.application_state_manager
operations_mgr = context.core_operations_manager
```

**In tests:**
```python
def test_something(app_context):  # Fixture provides this
    operations_mgr = app_context.core_operations_manager
```

### Key Patterns

| Pattern | Location | Notes |
|---------|----------|-------|
| **Resource cleanup** | `ui/workers/batch_thumbnail_worker.py:_rom_context` | Use `@contextmanager` with try/finally |
| **Thread safety** | General | Use `QMutex/QMutexLocker`; prefer signals over polling |
| **Dialog init** | `ui/components/base/dialog_base.py` | Declare instance vars BEFORE `super().__init__()` |
| **Circular imports** | General | Use local imports in methods when needed |
| **Workflow state changes** | `rom_workflow_controller.py` | Keep asset browser enabled in edit mode; prompt to save on sprite selection if unsaved changes |
| **Revert to Original** | `rom_workflow_controller.py:revert_to_original()` | Shows confirmation if unsaved changes exist; reloads original sprite via `open_in_editor()` |

---

## Reference

### Environment Variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `PYTEST_TIMEOUT_MULTIPLIER` | Scale all timeouts for slow CI | `1.0` |
| `SPRITEPAL_EXHAL_PATH` | Path to real exhal binary | System PATH |
| `SPRITEPAL_INHAL_PATH` | Path to real inhal binary | System PATH |
| `SPRITEPAL_LEAK_MODE` | Override leak detection | `fail` (CI), `warn` (local) |
| `SPRITEPAL_INJECT_DEBUG` | Enable injection debug mode (saves images to temp) | `false` |
| `QT_QPA_PLATFORM` | Qt display platform | `offscreen` (pytest default) |

### Test Resources

| Resource | Path |
|----------|------|
| Test ROM | `roms/Kirby Super Star (USA).sfc` |

### Logging Control

Per-category logging control accessible via **Settings → Logging tab**. Supported categories: ROM Extraction, Tile Rendering, Thumbnail Worker, Tile Hash Database, ROM Tile Matcher, HAL Compression, All UI Workers. Persists via `ApplicationStateManager`.

### Type Checking (basedpyright, zero errors)

- Use `| None` instead of `Optional`
- Qt signals need explicit annotations: `finished = Signal(str, int)`
- **Protocols removed** (commits 0c37f478, ace57d16 - over-engineering). Use concrete types instead.
- **Dict invariance:** Use `Mapping[str, object]` for read-only params; never replace `dict[str, Any]` with `dict[str, object]`

### Key Files & Locations

| Looking for... | Location |
|----------------|----------|
| **Managers** | `core/managers/core_operations_manager.py`, `core/managers/application_state_manager.py` |
| **Sprite Editor** | `ui/sprite_editor/` (Extract/Edit/Inject workflow) |
| **Frame Mapping** | `ui/frame_mapping/` — AI-to-game frame mapping workspace |
| **Frame Mapping Controller** | `ui/frame_mapping/controllers/frame_mapping_controller.py` — frame pairing, injection |
| **Workbench Canvas** | `ui/frame_mapping/views/workbench_canvas.py` — zoom/pan, in-game preview, alignment |
| **Frame Mapping Project** | `core/frame_mapping_project.py` — AIFrame, GameFrame, FrameMapping data classes |
| **AppContext** | `core/app_context.py` — use `get_app_context()` to access managers; provides lazy-initialized shared services (HALCompressor, SpriteConfigLoader, DefaultPaletteLoader) |
| **Settings UI** | `ui/dialogs/settings_dialog.py` — includes logging control tab for per-category logging |
| **Logging config** | `utils/logging_config.py` — logging setup and category control API |
| **Base patterns** | `ui/components/base/dialog_base.py` — declare vars BEFORE `super().__init__()` |
| **Mesen integration** | `core/mesen_integration/` — ROM offset discovery; see address_space_bridge.py, rom_tile_matcher.py |
| **ROM Workflow** | `ui/sprite_editor/controllers/rom_workflow_controller.py` — Revert to Original, edit mode management, capture sync |
| **Test fixtures** | `tests/fixtures/core_fixtures.py`, `tests/fixtures/qt_fixtures.py` |
| **Qt mocks** | `tests/infrastructure/qt_mocks.py` |
| **Safe signals** | `ui/common/signal_utils.py` — `safe_disconnect()`, etc. |
| **ThreadSafeTestImage** | `tests/infrastructure/thread_safe_test_image.py` — for worker thread testing |
| **RealComponentFactory** | `tests/infrastructure/real_component_factory.py` — for testing with real components |
| **UI Integration Tests** | `tests/ui/integration/` — 100+ signal-driven workflow tests; see `helpers/signal_spy_utils.py` for MultiSignalRecorder |

### Project Structure

```
spritepal/
├── core/                  # Business logic (no UI)
│   ├── managers/          # AppContext, state, operations
│   ├── mesen_integration/ # ROM offset discovery
│   ├── frame_mapping_project.py  # Frame mapping data model
│   └── *.py
├── ui/                    # Qt components
│   ├── sprite_editor/     # Unified editor (Extract → Edit → Inject)
│   ├── frame_mapping/     # AI-to-game frame mapping (4-zone workspace)
│   │   ├── controllers/   # FrameMappingController
│   │   ├── views/         # AIFramesPane, CapturesLibraryPane, WorkbenchCanvas
│   │   └── dialogs/       # SpriteSelectionDialog
│   ├── workspaces/        # FrameMappingWorkspace
│   ├── components/        # Reusable widgets
│   ├── dialogs/           # Dialog windows
│   ├── workers/           # Background threads
│   └── *.py
├── tests/                 # All tests (consolidated January 2026)
│   ├── unit/              # Pure logic tests (no Qt)
│   ├── integration/       # Multi-component tests
│   ├── ui/                # UI-specific tests
│   │   ├── integration/   # UI integration tests
│   │   └── sprite_editor/ # Sprite editor subsystem tests (125+)
│   ├── fixtures/          # Test fixtures (app_context, qtbot, etc.)
│   └── infrastructure/    # Mocks, factories, test utilities
├── utils/                 # Stdlib-only utilities
└── mesen2_integration/    # Lua scripts for emulator (external tool)
```

---

## Mesen 2 Integration (Quick Start)

**What:** SNES emulator tool to capture sprite data at runtime. Runs from Windows (WSL interop).

**Location:** `tools/mesen2/` | **Detailed docs:** `mesen2_integration/README.md`

**Quick start:**
- **To find sprite ROM offset:** Run `run_sprite_rom_finder.bat` → click sprite → read `FILE: 0xNNNNNN`
- **To capture to JSON:** Run `run_sprite_capture.bat` → captures to `mesen2_exchange/sprite_capture_*.json`
- **To process captures:** `uv run python scripts/extract_sprite_from_capture.py mesen2_exchange/sprite_capture_*.json`

**Key points:**
- Testrunner mode (`--testrunner`) runs headless; for gameplay, use movie file (see README for details)
- Frame analysis: ignore 0-500 (boot), focus on 1500+ (gameplay where SA-1 is active)
- SA-1 address mapping: `file = (bank - 0xC0) * 0x10000 + addr`

**Available Lua scripts:** `sprite_rom_finder.lua` (recommended), `sprite_identifier.lua`, `vram_tile_dump.lua`, `asset_selector_tracer_v3.lua`, and more in `mesen2_integration/lua_scripts/`

### Extracting Palettes from CGRAM Dumps

CGRAM structure: 512 bytes, sprite palettes at $100-$1FF (8 palettes × 16 colors × 2 bytes in BGR555).

For extraction details and code, see `docs/mesen2/02_DATA_CONTRACTS.md`.

---

## Known Limitations

### Palette Index Painting Limitation

The injection pipeline converts images to RGBA for compositing (`core/services/injection_orchestrator.py:293`).
Palette indices are lost and re-quantized using RGB color matching. If your palette has duplicate
colors, pixels of those colors will all map to the same index. Index painting only works when
all palette colors are unique. The Palette Editor shows a warning banner when duplicates are detected
(see `ui/frame_mapping/windows/ai_frame_palette_editor.py:137-147`).

**Workaround:** Ensure all colors in your palette are unique (even slightly different shades work).

**Future consideration:** If needed, investigate index-preserving pipeline that skips RGBA conversion
when no transforms are needed (scale=1.0, no flip) or passes a parallel "index map" through compositor.

---

## Advanced Topics

### Taking UI Screenshots (for debugging)

```bash
# Capture app window (requires X11/xcb display)
QT_QPA_PLATFORM=xcb uv run python -c "
from PySide6.QtCore import QTimer; from launch_spritepal import SpritePalApp; import sys
app = SpritePalApp(sys.argv); w = app.main_window; w.show(); w.resize(1000, 900)
QTimer.singleShot(500, lambda: (w.grab().save('/tmp/spritepal_screenshot.png'), app.quit()))
app.exec()
"
```

**Debug widget boundaries:** `widget.setStyleSheet('QWidget { border: 1px solid red; }')`

### Qt Thread Cleanup (gc.collect() Hazard)

**NEVER call gc.collect() during Qt worker cleanup.** Causes segfaults.

**Why:** gc.collect() triggers finalization of PySide6/Qt objects while background threads
are still running, causing "Fatal Python error: Aborted".

**Safe cleanup sequence:**
```python
worker.requestInterruption()
worker.quit()
worker.wait(5000)
worker.deleteLater()
QApplication.processEvents()
```

**Existing implementations:** See `tests/infrastructure/real_component_factory.py:411-415`.

### Documentation Pointers

| Topic | Location |
|-------|----------|
| Qt threading, error path testing | `docs/testing_guide.md` |
| Layer boundaries, architecture | `docs/architecture.md` |
| Sprite format, ROM structure, compression | `docs/mesen2/00_STABLE_SNES_FACTS.md`, `03_GAME_MAPPING_KIRBY_SA1.md` |
