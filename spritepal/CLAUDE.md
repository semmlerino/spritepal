# SpritePal Development Guidelines

## Critical Rules (Read First)

These rules prevent crashes and test failures. Each has a solution.

| Rule | Solution |
|------|----------|
| **Never `QPixmap` in worker threads** | Use `ThreadSafeTestImage` from `tests/infrastructure/` |
| **Never inherit `QDialog` in mocks** | Use `QObject` with signals (see `tests/infrastructure/mock_dialogs.py`) |
| **Use `isolated_managers` by default** | Only use `session_managers` with `@pytest.mark.shared_state_safe` |
| **Use `tmp_path` for file operations** | Never hardcode paths like `/tmp/test_output` |
| **Use `with qtbot.waitSignal():`** | Context manager catches fast signals; non-context form races |
| **Never `time.sleep()` in Qt tests** | Use `qtbot.wait(ms)` or `qtbot.waitSignal()` |
| **Mock at import location** | `@patch('spritepal.ui.panel.Dialog')`, not `...dialogs.Dialog` |

## Quick Reference

- **Qt Framework**: PySide6 (not PyQt6)
- **Python**: 3.12+
- **Package Manager**: uv
- **Config**: `pyproject.toml` (ruff, basedpyright, pytest)

## Running Tests

All commands run from `spritepal/` directory. Use `~/.local/bin/uv` if `uv` isn't in PATH.

Parallel execution requires pytest-xdist (included in dev dependencies).

### Quick Triage (Start Here)

For large test suites (1900+ tests), get a fast pass/fail summary first:

```bash
# Fast summary - no tracebacks, just pass/fail counts
uv run pytest --tb=no -q 2>&1 | tee /tmp/pytest_triage.log
tail -30 /tmp/pytest_triage.log  # See summary

# Re-run only failures with details
uv run pytest --lf -vv --tb=short
```

**Why tee to a file:** Pytest buffers output; piping directly to `head`/`tail` loses the summary. Always capture to file first for large runs.

### Standard Workflow

```bash
# 1. Quick triage (see above) - identify what's failing
uv run pytest --tb=no -q

# 2. Re-run failures with details
uv run pytest --lf -vv --tb=short

# 3. Drill down on specific test (serial, verbose, full tracebacks)
uv run pytest tests/path/test_file.py::test_name -vv --tb=long -s -n 0

# 4. Full suite when stable (override default maxfail=3)
uv run pytest --maxfail=10
```

**Why these flags:**
- `-vv` - Full test names and assertion details
- `--tb=long` - Full tracebacks for all frames (pyproject.toml sets `--tb=short`)
- `-s` - Show print/log output (**only use with `-n 0`**; parallel output interleaves)
- `-n 0` - Serial execution (pyproject.toml sets `-n auto` for parallel)

**Never use `-q` when debugging** - it hides information you need.

### Useful Shortcuts

```bash
# Re-run only last failures
uv run pytest --lf -vv

# Stop on first failure (fast iteration)
uv run pytest -x -vv

# Filter by name pattern
uv run pytest -k "extraction and not slow" -vv

# Filter by marker
uv run pytest -m "not real_hal" -vv

# Find slow tests
uv run pytest --durations=20
```

### Custom CLI Options

Options defined in conftest.py:

```bash
# Use real HAL binaries instead of mocks
uv run pytest --use-real-hal -v

# Fail if real HAL binaries not found (instead of skip)
uv run pytest --require-real-hal -v

# Control leak detection behavior
uv run pytest --leak-mode=warn  # Warn on leaks (default local)
uv run pytest --leak-mode=fail  # Fail on leaks (default CI)

# Regenerate golden data checksums
uv run pytest tests/test_hal_golden.py --regenerate-golden -v
```

### Parallel Execution

Tests run parallel by default (pyproject.toml sets `-n auto --dist=loadscope`).

**Note:** The config uses `--dist=loadscope` (groups by module), not `--dist=loadgroup`. The conftest.py applies `xdist_group("serial")` markers to tests using `session_managers` or `@pytest.mark.parallel_unsafe`, but these only co-locate tests on one worker (not truly serial).

**For truly serial execution:** Use `-n 0`.

### When Tests Fail

**Flaky test (passes sometimes, fails other times):**
1. Run serial first: `uv run pytest path/to/test.py -n 0 -vv`
2. If it passes serial, it's a race condition - check for:
   - Non-context `waitSignal()` (signal emits before wait starts)
   - Hardcoded timeouts (use `worker_timeout()` functions)
   - Fixed paths or shared filenames (use `tmp_path` fixture instead)

**Crash with "Fatal Python error: Aborted":**
- Almost always `QPixmap` in a worker thread
- Replace with `ThreadSafeTestImage` from `tests/infrastructure/`

**Test hangs forever:**
- Ctrl-C then re-run with `--full-trace` for useful stack on interrupt
- Dialog waiting for user input - mock `exec()` on the specific dialog class
- Infinite loop in worker - check thread cleanup in fixture teardown

**Passes locally, fails in CI:**
- Usually timeout-related - check if CI uses `PYTEST_TIMEOUT_MULTIPLIER`
- Or display-related - ensure test doesn't require real display (offscreen mode is default)

## Writing Tests

### Minimal Template

```python
from tests.fixtures.timeouts import worker_timeout

def test_my_feature(isolated_managers, tmp_path):
    """One-line description."""
    manager = isolated_managers.extraction_manager
    output_file = tmp_path / "output.bin"
    result = manager.some_method()
    assert result is not None
```

### Signal Testing

```python
from tests.fixtures.timeouts import worker_timeout, LONG

# CORRECT: Context manager catches signals regardless of timing
def test_async_op(qtbot, worker):
    with qtbot.waitSignal(worker.finished, timeout=worker_timeout()):
        worker.start()

# For slow operations (2x default timeout)
def test_slow_op(qtbot, worker):
    with qtbot.waitSignal(worker.finished, timeout=worker_timeout(LONG)):
        worker.start()
```

**Anti-pattern (causes flaky tests):**
```python
worker.start()
qtbot.waitSignal(worker.finished)  # Signal may emit before wait starts!
```

### Fixture Selection

**Default: `isolated_managers`** - slower but always safe.

| Need | Use |
|------|-----|
| Standard test | `isolated_managers` (function-scoped, clean state) |
| Read-only, verified stateless | `session_managers` + `@pytest.mark.shared_state_safe` |
| Clean counters only | `isolated_managers` |
| HAL operations | `hal_pool` (mock by default) |
| Real HAL | `@pytest.mark.real_hal` (skips if binary unavailable) |

**Do not mix `session_managers` and `isolated_managers` in the same module.**

### Advanced Fixtures

For integration tests and real component testing:

| Fixture | Scope | Purpose |
|---------|-------|---------|
| `real_factory` | function | RealComponentFactory wrapper with cleanup |
| `complete_test_context` | function | All managers together (injection, extraction, session) |
| `manager_context_factory` | function | Factory for creating test contexts |
| `test_injection_manager` | function | Context-based injection manager |
| `test_extraction_manager` | function | Context-based extraction manager |
| `real_extraction_manager` | function | Direct real extraction manager |
| `real_injection_manager` | function | Direct real injection manager |
| `real_session_manager` | function | Direct real session manager |
| `isolated_data_repository` | function | Clean DataRepository per test |
| `rom_cache` | function | ROM cache for extraction tests |
| `mock_rom_cache` | function | Mock ROM cache |
| `mock_settings_manager` | function | Mock settings manager |
| `mock_file_dialogs` | function | Patches QFileDialog for testing |

### Test Markers

| Marker | Effect | Enforced |
|--------|--------|----------|
| `@pytest.mark.requires_display` | Skips in offscreen mode | Yes (autouse fixture) |
| `@pytest.mark.shared_state_safe` | **Required** for `session_managers` | Yes (test fails without it) |
| `@pytest.mark.parallel_unsafe` | Co-locates on one xdist worker | Via `xdist_group` marker |
| `@pytest.mark.skip_thread_cleanup(reason='...')` | Skip thread check | Yes (**reason required**) |
| `@pytest.mark.real_hal` | Use real HAL (skips if unavailable) | Yes (fixture check) |

Categorization markers (`@pytest.mark.gui`, `@pytest.mark.headless`) have no behavioral effect.

### Timeout Functions

Import from `tests/fixtures/timeouts.py` (functions, not fixtures):

| Function | Base (ms) | Use For |
|----------|-----------|---------|
| `ui_timeout()` | 1000 | Widget visibility, layout updates |
| `signal_timeout()` | 2000 | Generic signal waits |
| `dialog_timeout()` | 3000 | Dialog accept/reject |
| `worker_timeout()` | 5000 | Background workers, QThread |
| `cleanup_timeout()` | 2000 | Thread termination |

Multipliers: `SHORT=0.5`, `MEDIUM=1.0` (default), `LONG=2.0`

Scale all with `PYTEST_TIMEOUT_MULTIPLIER` env var for slow CI.

### Key Imports

```python
from tests.fixtures.timeouts import worker_timeout, signal_timeout, ui_timeout, LONG
from tests.fixtures.qt_waits import wait_for_condition  # Function (requires qtbot arg)
from tests.infrastructure.mock_dialogs import MockDialog
from tests.infrastructure.real_component_factory import RealComponentFactory
from tests.infrastructure.thread_safe_test_image import ThreadSafeTestImage

# wait_for is a fixture - use as test parameter, not import:
# def test_foo(wait_for): wait_for(lambda: condition, timeout=1000)
```

## Other Development Commands

```bash
# Dependencies
uv sync --extra dev

# Linting
uv run ruff check .
uv run ruff check . --fix

# Type checking
uv run basedpyright core ui utils
```

### Environment Variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `PYTEST_TIMEOUT_MULTIPLIER` | Scale all timeouts for slow CI | `1.0` |
| `SPRITEPAL_EXHAL_PATH` | Path to real exhal binary | System PATH |
| `SPRITEPAL_INHAL_PATH` | Path to real inhal binary | System PATH |
| `SPRITEPAL_LEAK_MODE` | Override leak detection | `fail` (CI), `warn` (local) |
| `QT_QPA_PLATFORM` | Qt display platform | `offscreen` (set by conftest) |

Example for slow CI:
```bash
export PYTEST_TIMEOUT_MULTIPLIER=2.0
uv run pytest
```

### Type Checking Notes

The codebase passes basedpyright with zero errors. To maintain this:

- Use `| None` for optional types, not `Optional`
- Protocols live in `core/protocols/` - check there before creating new ones
- Qt signals need type annotations: `finished = Signal(str, int)`
- For widgets that may not exist yet: `self.widget: QWidget | None = None`

### Taking UI Screenshots

For visual debugging and UI iteration, use this script to capture the app window:

```bash
uv run python -c "
import sys
import os
os.environ['QT_QPA_PLATFORM'] = 'xcb'

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer

from core.managers import initialize_managers
from core.configuration_service import ConfigurationService

config_service = ConfigurationService()
config_service.ensure_directories_exist()
initialize_managers('SpritePal', settings_path=config_service.settings_file, configuration_service=config_service)
from ui import register_ui_factories
register_ui_factories()

from launch_spritepal import SpritePalApp
app = SpritePalApp(sys.argv)

window = app.main_window
window.show()
window.resize(1000, 900)

app.processEvents()
app.processEvents()

def capture():
    pixmap = window.grab()
    pixmap.save('/tmp/spritepal_screenshot.png')
    print(f'Screenshot saved: {pixmap.width()}x{pixmap.height()}')
    app.quit()

QTimer.singleShot(500, capture)
app.exec()
" 2>&1 | tail -5
```

**Key points:**
- Uses `xcb` platform for WSL X11 forwarding (not `offscreen`)
- `window.grab()` captures widget directly (more reliable than `screen.grabWindow()`)
- 500ms delay allows layout to stabilize before capture
- View screenshot with: `Read /tmp/spritepal_screenshot.png`

**For debug borders** (visualize widget boundaries):
```python
panel = window.rom_extraction_panel
panel.setStyleSheet('QWidget { border: 1px solid red; }')
```

## Documentation Pointers

| When you need... | Read |
|------------------|------|
| Qt threading rules, error path testing patterns | `docs/testing_guide.md` |
| Layer boundaries, what imports what | `docs/architecture.md` |
| Fixture decision tree, RealComponentFactory usage | `tests/README.md` |
| Sprite format details, ROM structure, compression | `SPRITE_LEARNINGS_DO_NOT_DELETE.md` |

## Project Architecture

```
spritepal/
├── core/                  # Business logic
│   ├── managers/          # Manager classes
│   ├── protocols/         # Protocol definitions
│   └── *.py               # Core logic
├── ui/                    # Qt UI components
│   ├── components/        # Reusable widgets
│   ├── dialogs/           # Dialog windows
│   ├── workers/           # Background workers
│   └── *.py               # Panel files
├── tests/
│   ├── fixtures/          # Test fixtures
│   └── infrastructure/    # RealComponentFactory, ThreadSafeTestImage
└── utils/                 # Shared utilities
```

### Key Files

| Looking for... | Location |
|----------------|----------|
| Manager protocols | `core/protocols/manager_protocols.py` |
| Dialog protocols | `core/protocols/dialog_protocols.py` |
| Preview protocols | `core/protocols/preview_protocols.py` |
| Worker protocols | `core/protocols/worker_protocols.py` |
| All protocols (exports) | `core/protocols/__init__.py` |
| ExtractionManager, InjectionManager | `core/managers/` |
| DialogBase (init pattern) | `ui/components/base/dialog_base.py` |
| DI container, `inject()` | `core/di_container.py` |
| Test fixtures | `tests/fixtures/core_fixtures.py`, `tests/fixtures/qt_fixtures.py` |
| MockDialog, Qt mocks | `tests/infrastructure/mock_dialogs.py`, `tests/infrastructure/qt_mocks.py` |
| ThreadSafeTestImage | `tests/infrastructure/thread_safe_test_image.py` |
| RealComponentFactory | `tests/infrastructure/real_component_factory.py` |
| Test data repository | `tests/infrastructure/data_repository.py` |

### Import Rules

- **UI** imports from: `core/`, `utils/`
- **Core** imports from: `utils/`
- **Utils** imports from: stdlib only

### Manager Architecture

Use DI, never instantiate managers directly:

```python
from core.di_container import inject
from core.protocols.manager_protocols import ExtractionManagerProtocol

# Production code
extraction_mgr = inject(ExtractionManagerProtocol)

# Tests - use fixtures, not inject()
def test_extraction(isolated_managers):
    extraction_mgr = isolated_managers.extraction_manager
```

Key managers: `ApplicationStateManager`, `CoreOperationsManager` (registered as both `ExtractionManagerProtocol` and `InjectionManagerProtocol`)

### Key Patterns

**Resource management:** Use `@contextmanager` with try/finally for file/mmap cleanup. See `ui/workers/batch_thumbnail_worker.py:_rom_context` for the canonical pattern.

**Thread safety:** Use `QMutex/QMutexLocker` for shared state; prefer signal-based waiting over polling.

**Dialog initialization (DialogBase):** Declare instance variables BEFORE `super().__init__()`:
```python
class MyDialog(DialogBase):
    def __init__(self, parent: QWidget | None = None):
        self.my_widget: QWidget | None = None  # BEFORE super()
        super().__init__(parent)  # Calls _setup_ui()
```

**Circular imports:** Use local imports in methods when needed.

---

*Last updated: December 21, 2025*
