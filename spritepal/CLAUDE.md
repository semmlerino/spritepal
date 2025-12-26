# SpritePal Development Guidelines

## Core Principles

1. **Test logic more than widgets** - Put business logic in plain Python classes so tests stay fast and stable. Keep widget tests focused on wiring, signals, and basic interactions.

2. **Parallel by default** - With 1900+ tests, serial runs take 15+ minutes. Tests run parallel via `-n auto`. Mark tests that need isolation with `@pytest.mark.parallel_unsafe` or use `app_context` fixture (which provides clean state per-test).

3. **Prefer boring determinism** - The fastest dev loop is: small change → run checks → commit.

## Critical Rules (Read First)

These rules prevent crashes and test failures. Each has a solution.

| Rule | Solution |
|------|----------|
| **Never `QPixmap` in worker threads** | Use `ThreadSafeTestImage` from `tests/infrastructure/` |
| **Never inherit `QDialog` in mocks** | Use `QObject` with signals (see `tests/infrastructure/qt_mocks.py`) |
| **Use `app_context` fixture by default** | Use `session_app_context` only with `@pytest.mark.shared_state_safe` |
| **Use `tmp_path` for file operations** | Never hardcode paths like `/tmp/test_output` |
| **Use `with qtbot.waitSignal():`** | Context manager catches fast signals; non-context form races |
| **Never `time.sleep()` in Qt tests** | Use `qtbot.wait(ms)` or `qtbot.waitSignal()` |
| **Mock at import location** | `@patch('spritepal.ui.panel.Dialog')`, not `...dialogs.Dialog` |
| **One QApplication only** | Let pytest-qt manage it via `qtbot`/`qapp` fixtures |

## Quick Reference

- **Qt Framework**: PySide6 (not PyQt6)
- **Python**: 3.12+
- **Package Manager**: uv
- **Config**: `pyproject.toml` (ruff, basedpyright, pytest)

## Claude Code Workflow

When editing this repo, follow these rules:

1. **One canonical check sequence**
   ```bash
   uv run ruff check .
   uv run ruff format .
   uv run basedpyright core ui utils
   uv run pytest
   ```

2. **No silent behavior changes** - If a change affects threading, signals, IO, persistence, or settings: add/adjust tests.

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

**Note:** The config uses `--dist=loadscope` (groups by module), not `--dist=loadgroup`. The conftest.py applies `xdist_group("serial")` markers to tests using `session_app_context` or `@pytest.mark.parallel_unsafe`, but these only co-locate tests on one worker (not truly serial).

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

> **Comprehensive testing guide:** [docs/testing_guide.md](docs/testing_guide.md)
> **Fixture reference:** [tests/README.md](tests/README.md)

### Quick Template

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

### Key Imports

```python
from tests.fixtures.timeouts import worker_timeout, signal_timeout, ui_timeout, LONG
from tests.infrastructure.thread_safe_test_image import ThreadSafeTestImage
from tests.infrastructure.real_component_factory import RealComponentFactory
```

## Other Development Commands

### Environment Setup

```bash
uv sync              # Sync from lockfile
uv sync --extra dev  # Include dev dependencies
uv lock              # Update lockfile after dependency changes
```

### Code Quality

```bash
uv run ruff check .              # Lint
uv run ruff check . --fix        # Auto-fix
uv run ruff format .             # Format
uv run basedpyright core ui utils  # Type check
```

### Environment Variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `PYTEST_TIMEOUT_MULTIPLIER` | Scale all timeouts for slow CI | `1.0` |
| `SPRITEPAL_EXHAL_PATH` | Path to real exhal binary | System PATH |
| `SPRITEPAL_INHAL_PATH` | Path to real inhal binary | System PATH |
| `SPRITEPAL_LEAK_MODE` | Override leak detection | `fail` (CI), `warn` (local) |
| `QT_QPA_PLATFORM` | Qt display platform | `offscreen` (set by conftest) |

### Type Checking Notes

The codebase passes basedpyright with zero errors. Key rules:

- Use `| None` not `Optional`; Qt signals need annotations: `finished = Signal(str, int)`
- Protocols live in `core/protocols/` - check before creating new ones
- **Dict invariance:** Use `Mapping[str, object]` for read-only params; never replace `dict[str, Any]` with `dict[str, object]`

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
| CoreOperationsManager | `core/managers/core_operations_manager.py` (handles extraction and injection) |
| ApplicationStateManager | `core/managers/application_state_manager.py` (session, settings, state) |
| DialogBase (init pattern) | `ui/components/base/dialog_base.py` |
| AppContext, `get_app_context()` | `core/app_context.py` |
| DI container (deprecated) | `core/di_container.py` |
| Test fixtures | `tests/fixtures/core_fixtures.py`, `tests/fixtures/qt_fixtures.py` |
| Qt mocks | `tests/infrastructure/qt_mocks.py` |
| Signal utilities (`safe_disconnect`, etc.) | `ui/common/signal_utils.py` |
| ThreadSafeTestImage | `tests/infrastructure/thread_safe_test_image.py` |
| RealComponentFactory | `tests/infrastructure/real_component_factory.py` |
| Test data repository | `tests/infrastructure/data_repository.py` |

### Import Rules

- **UI** imports from: `core/`, `utils/`
- **Core** imports from: `utils/`
- **Utils** imports from: stdlib only

### Manager Architecture

Use AppContext to access managers, never instantiate directly:

```python
from core.app_context import get_app_context

# Production code
context = get_app_context()
state_mgr = context.application_state_manager
operations_mgr = context.core_operations_manager

# Tests - use app_context fixture
def test_extraction(app_context):
    operations_mgr = app_context.core_operations_manager
```

Key managers: `ApplicationStateManager`, `CoreOperationsManager` (handles extraction and injection operations)

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

*Last updated: December 26, 2025*
