# SpritePal Development Guidelines

**Last updated: January 12, 2026 — Recent updates: Bug-first TDD workflow (mandatory), Revert to Original button, per-category logging control, UI integration tests (100+)** | See [Table of Contents](#table-of-contents) below

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

**3. Testing** (when running tests):
- Default: parallel via `-n auto` (see `pyproject.toml`)
- **Flaky?** Run serial: `pytest -n 0 -vv` — if passes, it's a race condition
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
- **Why:** Prevents regressions, documents the bug, proves the fix works

**→ For full details, jump to relevant section below**

---

## Table of Contents

1. [Core Principles](#core-principles) — Philosophy behind the codebase
2. [Critical Rules](#critical-rules-read-first) — Will cause crashes/failures if violated
3. [Development Workflow](#development-workflow) — Day-to-day commands and checks
4. [Testing Guide](#testing-guide) — Running, writing, and debugging tests
5. [Code Patterns & Architecture](#code-patterns--architecture) — Design patterns and import rules
6. [Reference](#reference) — Key files, managers, fixtures
7. [Mesen 2 Integration](#mesen-2-integration) — Sprite capture tool (quick start only)
8. [Advanced Topics](#advanced-topics) — Detailed debugging, type checking, UI screenshots

---

## Core Principles

1. **🚨 Bug reports → failing test FIRST** - When the user reports a bug, you MUST write a failing test that reproduces it BEFORE attempting any fix. This is not optional. The workflow is:
   1. Understand and reproduce the bug
   2. Write a test that fails due to the bug
   3. Run the test and verify it fails for the right reason
   4. Fix the bug in the implementation
   5. Run the test and verify it now passes

   **Why mandatory:** Skipping this step has repeatedly led to fixes that don't actually address the bug, or fixes that break later because there's no regression test. A failing test proves you understand the bug and proves your fix works.

2. **Fix bugs, not tests** - Bias toward fixing actual defects in the implementation, not making tests pass by dilution. Do not relax, delete, or rewrite tests unless they are demonstrably incorrect or asserting non-contractual implementation details. Any test change must be explicitly justified by a mismatch with intended external behavior. When uncertain: run the test in isolation, trace actual vs expected values, and verify whether the test's expectation matches documented/intended behavior.

3. **Test logic more than widgets** - Put business logic in plain Python classes so tests stay fast and stable. Keep widget tests focused on wiring, signals, and basic interactions.

4. **Parallel by default** - With 2400+ tests, serial runs take 15+ minutes. Tests run parallel via `-n auto`. Mark tests that need isolation with `@pytest.mark.parallel_unsafe` or use `app_context` fixture (which provides clean state per-test).

5. **Prefer boring determinism** - The fastest dev loop is: small change → run checks → commit.

---

## Critical Rules (Read First)

⚠️ **See the table in [TL;DR](#tldr---essential-rules-read-this-first) above.** These cause crashes (💥) or test failures (🔴).

**Additional context:**
- `QPixmap` crash: Qt GUI objects aren't thread-safe. The error "Fatal Python error: Aborted" with no stack trace is the giveaway.
- `waitSignal()` race: Without context manager, signal may emit before wait starts. Always `with qtbot.waitSignal(...):`.
- Mock location: Python patches at import site, not definition site. Trace where the code `from X import Y` to find patch target.

---

## Development Workflow

### Code Quality Check (Always Do This)

**One canonical sequence before committing:**

```bash
uv run ruff check .              # Lint
uv run ruff format .             # Format
uv run basedpyright core ui utils  # Type check
uv run pytest                    # Run all tests
```

**Note:** If `uv` is not in PATH, use `~/.local/bin/uv run` as fallback (e.g., `~/.local/bin/uv run ruff check .`).

**No silent behavior changes:** If a change affects threading, signals, IO, persistence, or settings → add/adjust tests.

### Definition of Done

A task is complete **only when**:
1. All checks pass: `ruff check . && ruff format . && basedpyright && pytest`
2. Changes are committed: `git add <files> && git commit -m "..."`
3. `git status` shows clean working directory

**Do not consider work "done" until committed.** Uncommitted changes = incomplete task.

**Commit triggers:** After each logical task completion when all checks pass. Use conventional commits (`fix:`, `feat:`, `refactor:`, etc.).

### Committing After Quality Checks

**Always commit after completing changes.** When all checks pass, create a commit immediately—don't leave work uncommitted.

**After all checks pass:**
1. `git status` / `git diff` to review changes
2. `git add <files>` to stage
3. `/commit` (or `git commit -m "fix: description"`) — use conventional commits: `fix:`, `feat:`, `refactor:`, `chore:`, `test:`, `docs:`
4. Example: `fix: resolve race condition in palette sync`

**Never commit if:** checks fail, tests are flaky (verify with `-n 0`), or behavior changed without tests.

### Committing Facade & Law of Demeter Refactoring

When committing changes that add facade methods or remove reach-through access patterns:

1. **Verify facade completeness:**
   - Check that all direct reach-through access in callers is now replaced with facade method calls
   - Confirm new facade methods follow naming convention: `get_*()` for reads, `set_*()` for writes, `clear_*()` for cleanup
   - Ensure docstrings document the purpose of each facade method

2. **Verify reach-through patterns eliminated:**
   ```bash
   # Search for remaining violations (adjust patterns as needed)
   grep -rn "\.tool_manager\." ui/sprite_editor/views/
   grep -rn "\.undo_manager\." ui/sprite_editor/controllers/
   grep -rn "\.asset_browser\.tree" ui/sprite_editor/
   ```
   All results should return nothing if refactoring is complete.

3. **Use conventional commit message:**
   - For new facades: `refactor: add Law of Demeter facade methods in X`
   - For reach-through elimination: `refactor: eliminate reach-through access to X.Y`
   - Example: `refactor: add SpriteAssetBrowser facades to encapsulate tree structure`

4. **Update documentation if needed:**
   - If public API changed significantly, update the subsystem's CLAUDE.md
   - If design patterns changed, consider updating docs/architecture.md

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
| **Drill down on one test** | `pytest tests/path/test_file.py::test_name -vv --tb=long -s -n 0` |
| **Find slow tests** | `pytest --durations=20` |
| **Filter by pattern** | `pytest -k "extraction and not slow" -vv` |
| **Stop on first failure** | `pytest -x -vv` |
| **Serial execution** | `pytest -n 0 -vv` |

**Note:** Pytest buffers output. Always `tee` to file first for large runs.

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

### Parallel Execution (Default)

Tests run parallel via `-n auto` (see `pyproject.toml`).

- **Config:** `--dist=loadscope` groups by module; `xdist_group("serial")` co-locates marked tests
- **Not truly serial:** These only prevent parallel workers from running them, but don't guarantee exclusivity
- **For truly serial:** Use `-n 0`

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
| **Flaky (sometimes passes)** | Run serial: `pytest -n 0 -vv`. If passes → race condition. Check: non-context `waitSignal()`, hardcoded timeouts, `tmp_path` usage |
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
│   └── *.py
├── ui/                    # Qt components
│   ├── sprite_editor/     # Unified editor (Extract → Edit → Inject)
│   ├── components/        # Reusable widgets
│   ├── dialogs/           # Dialog windows
│   ├── workers/           # Background threads
│   └── *.py
├── tests/
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

When you have a CGRAM dump file (e.g., from Mesen2's Debug → Memory Viewer → CGRAM → Export):

1. **CGRAM structure:** 512 bytes total, 256 colors in BGR555 format (2 bytes/color)
2. **Sprite palettes:** Located at $100-$1FF (upper 256 bytes), 8 palettes of 16 colors each
3. **Palette offsets:** Palette N starts at offset `0x100 + (N * 32)`

**Extract to SpritePal JSON format:**
```python
import json

with open("CGRAMdump.dmp", "rb") as f:
    data = f.read()

palette_num = 7  # Sprite palette 0-7
offset = 0x100 + (palette_num * 32)
palette_data = data[offset:offset + 32]

colors = []
for i in range(0, 32, 2):
    bgr = palette_data[i] | (palette_data[i+1] << 8)
    r = (bgr & 0x1F) << 3
    g = ((bgr >> 5) & 0x1F) << 3
    b = ((bgr >> 10) & 0x1F) << 3
    colors.append([r, g, b])

with open("output/my_palette.pal.json", "w") as f:
    json.dump({"name": "My Palette", "colors": colors}, f, indent=2)
```

**OAM palette mapping:** The sprite's OAM attribute byte bits 1-3 specify palette 0-7, which maps to CGRAM $100+N*32.

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

### Documentation Pointers

| Topic | Location |
|-------|----------|
| Qt threading, error path testing | `docs/testing_guide.md` |
| Layer boundaries, architecture | `docs/architecture.md` |
| Sprite format, ROM structure, compression | `docs/mesen2/00_STABLE_SNES_FACTS.md`, `03_GAME_MAPPING_KIRBY_SA1.md` |
