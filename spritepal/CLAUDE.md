# SpritePal Development Guidelines

## Quick Reference

- **Qt Framework**: PySide6 (not PyQt6)
- **Python Version**: 3.11+
- **Package Manager**: uv
- **Config Source of Truth**: `pyproject.toml` (ruff, basedpyright, pytest)

## Documentation Structure

```
spritepal/
├── CLAUDE.md                           # This file - development guidelines
├── README.md                           # Project overview
├── docs/
│   ├── architecture.md                 # Layer structure and import rules
│   ├── REAL_COMPONENT_TESTING_GUIDE.md # Real component testing patterns
│   ├── QT_TESTING_BEST_PRACTICES.md    # pytest-qt patterns
│   ├── dialog_development_guide.md     # Dialog creation patterns
│   └── archive/                        # Historical documentation
├── tests/
│   ├── README.md                       # Test suite overview
│   └── HEADLESS_TESTING.md             # Headless/CI testing
├── TESTING_DEBUG_GUIDE_DO_NOT_DELETE.md    # Critical debug strategies
├── UNIFIED_TESTING_GUIDE_DO_NOT_DELETE.md  # Testing single source of truth
└── SPRITE_LEARNINGS_DO_NOT_DELETE.md       # Sprite extraction knowledge
```

## Development Tools

All tools run via `uv` from the `spritepal/` directory:

```bash
# Sync dependencies (from exhal-master/)
uv sync --extra dev

# Linting
uv run ruff check .
uv run ruff check . --fix

# Type checking
uv run basedpyright core ui utils

# Tests - routine run (stop on first failure, short tracebacks)
QT_QPA_PLATFORM=offscreen uv run pytest tests --maxfail=1 --tb=short

# Tests - full suite (increase maxfail for broader coverage)
QT_QPA_PLATFORM=offscreen uv run pytest tests --maxfail=5 --tb=short -q

# Tests - specific subsets
QT_QPA_PLATFORM=offscreen uv run pytest tests -m "headless and not slow" --maxfail=1  # Fast tests
QT_QPA_PLATFORM=offscreen uv run pytest tests -m "gui" --maxfail=1                    # GUI tests (offscreen)

# Tests - drill down on failure (verbose, full traceback)
QT_QPA_PLATFORM=offscreen uv run pytest tests/path/test_file.py::TestClass::test_name -vv --tb=long
```

## Qt Testing Best Practices

### Real Component Testing (Preferred)

SpritePal uses real components over mocks. **Prefer real components; mock only at true system boundaries** (file I/O, clipboard, network). HAL is mock-by-default because the real `exhal` binary is slow and may not be available.

```python
from tests.infrastructure.real_component_factory import RealComponentFactory

def test_extraction_workflow():
    with RealComponentFactory() as factory:
        manager = factory.create_extraction_manager(with_test_data=True)
        params = {
            "vram_path": "/path/to/vram.bin",
            "cgram_path": "/path/to/cgram.bin",
            "output_base": "test_sprite",
        }
        result = manager.validate_extraction_params(params)
        assert result is True  # Real validation behavior
```

### Critical Crash Prevention

**Never inherit from QDialog in mocks** - causes metaclass conflicts:
```python
from PySide6.QtCore import QObject, Signal

# CORRECT
class MockDialog(QObject):
    accepted = Signal()
    rejected = Signal()

# INCORRECT - Causes fatal crashes
class MockDialog(QDialog):  # Don't do this!
    pass
```

**Mock at import location, not definition**:
```python
@patch('spritepal.ui.rom_extraction_panel.UnifiedManualOffsetDialog')  # Correct
```

### Signal Testing
```python
from tests.fixtures.timeouts import worker_timeout, signal_timeout

# Simple case: signal emits after start() returns
def test_async_operation(qtbot, worker):
    worker.start()
    qtbot.waitSignal(worker.finished, timeout=worker_timeout())

# Use context manager when signal may emit BEFORE start() returns
# (e.g., very fast operations or synchronous signals)
def test_fast_operation(qtbot, worker):
    with qtbot.waitSignal(worker.finished, timeout=signal_timeout()):
        worker.start()

# Multiple signals (finished OR failed) - wait for any one:
def test_async_with_failure_case(qtbot, worker):
    with qtbot.waitSignals([worker.finished, worker.failed], timeout=worker_timeout(), raising=False):
        worker.start()
```

**Never use hardcoded timeout values** like `timeout=5000`. Use semantic timeouts from `tests/fixtures/timeouts.py` which scale with `PYTEST_TIMEOUT_MULTIPLIER`.

### Test Markers
- `@pytest.mark.gui` - Uses real Qt widgets (run with `QT_QPA_PLATFORM=offscreen`)
- `@pytest.mark.headless` - No display required (can use real components if no rendering)
- `@pytest.mark.serial` - No parallel execution
- `@pytest.mark.parallel_safe` - Can run in parallel with pytest-xdist

**IMPORTANT**: Always run tests with `QT_QPA_PLATFORM=offscreen` to avoid display dependencies.
Do NOT use pytest-xvfb - it causes hangs in WSL2 and some CI environments.

### Parallel Test Execution (pytest-xdist)

SpritePal supports parallel test execution using pytest-xdist with a conservative opt-in approach.

**Running Tests:**
```bash
# Serial execution (default, safe for all tests)
QT_QPA_PLATFORM=offscreen uv run pytest tests --maxfail=3

# Parallel execution for marked tests only
QT_QPA_PLATFORM=offscreen uv run pytest tests -m "parallel_safe" -n auto --maxfail=3

# Run both: serial first, then parallel
./scripts/run_tests_parallel.sh
```

**Marking Tests as Parallel-Safe:**

Tests must meet ALL these criteria to be marked `@pytest.mark.parallel_safe`:

1. Uses `isolated_managers` fixture (NOT `session_managers`)
2. Uses `tmp_path` for any file operations (NOT hardcoded paths)
3. Does not modify module-level globals
4. Does not depend on test execution order

```python
@pytest.mark.parallel_safe
def test_extraction_logic(isolated_managers, tmp_path):
    """This test is safe for parallel execution."""
    settings_path = tmp_path / "settings.json"
    # ... test code using isolated managers ...
```

**Validation:** The `check_parallel_isolation` fixture automatically validates that
`parallel_safe` tests don't use incompatible fixtures like `session_managers`.

**Common Mistakes:**
- Using `session_managers` with `parallel_safe` - causes fixture conflicts
- Hardcoded `/tmp/test_output` paths - use `tmp_path` fixture instead
- Relying on singleton state from previous tests

### Modular Fixture Architecture

Test fixtures are organized into modular files for maintainability:

```
tests/
├── conftest.py                  # Coordinator - imports from modular files
├── fixtures/
│   ├── qt_fixtures.py           # Qt app, main window, qtbot, cleanup_singleton
│   ├── qt_waits.py              # wait_for_condition, wait_for helpers
│   ├── qt_mocks.py              # MockDialog, MockQWidget, etc.
│   ├── timeouts.py              # Semantic timeouts (worker_timeout, signal_timeout, etc.)
│   ├── core_fixtures.py         # Manager fixtures, DI fixtures, state management
│   ├── hal_fixtures.py          # HAL compression mock/real fixtures
│   ├── xdist_fixtures.py        # Parallel testing support (pytest-xdist)
│   └── test_*_helper.py         # Component-specific test helpers
└── infrastructure/
    ├── real_component_factory.py    # RealComponentFactory
    └── thread_safe_test_image.py    # ThreadSafeTestImage for worker threads
```

**Common imports for tests:**
```python
from tests.fixtures.qt_waits import wait_for_condition, wait_for
from tests.fixtures.qt_mocks import MockDialog
from tests.fixtures.timeouts import worker_timeout, signal_timeout, ui_timeout
from tests.infrastructure.real_component_factory import RealComponentFactory
from tests.infrastructure.thread_safe_test_image import ThreadSafeTestImage
```

### Test Fixture Selection Guide

| Need | Use | NOT |
|------|-----|-----|
| **Default for all tests** | `isolated_managers` | `session_managers` |
| Proven-safe shared state | `session_managers` + `@pytest.mark.shared_state_safe` | bare `session_managers` |
| Real component testing | `RealComponentFactory` | `Mock()` + `cast()` |
| Qt images in worker thread | `ThreadSafeTestImage` | `QPixmap` |
| Singleton dialog cleanup | `cleanup_singleton` | Own cleanup fixture |
| Signal waiting | `qtbot.waitSignal()` | `time.sleep()` |
| HAL with mocks (fast) | `hal_pool` (default) | Real HAL |
| HAL with real impl | `@pytest.mark.real_hal` | Mock HAL |

**Why `isolated_managers` is the default:** `session_managers` persists state across ALL tests in a session. This causes order-dependent failures when tests assume clean state. Only use `session_managers` for tests explicitly verified to be stateless.

**Manager Fixture Isolation Levels:**

| Fixture | Scope | Reset Between Tests | Use When |
|---------|-------|---------------------|----------|
| `isolated_managers` | Function | YES (full cleanup) | **Default choice** - tests that need predictable state |
| `setup_managers` | Function | YES | Alternative default with conditional setup |
| `session_managers` | Session | NO | **Unsafe** - only with `@pytest.mark.shared_state_safe` |
| `fast_managers` | Function (backed by session) | NO | **Unsafe** - alias for session_managers |
| `reset_manager_state` | Function | YES (caches only) | Need clean counters without full isolation |

**Mixing session + isolated fixtures:** If a module already activated `session_managers`, `isolated_managers` will temporarily pause the session managers and restore them (with the original settings path) after the test. Prefer keeping suites consistent (all isolated or all session-backed), but this safety net prevents cross-test pollution when you must mix.

**HAL Fixtures:**

HAL (compression/decompression) is **mock-by-default** because:
- Real HAL requires the external `exhal` binary which may not be available
- Mock HAL is ~100x faster (~1ms vs ~100ms per operation)
- Use `@pytest.mark.real_hal` only for integration tests validating actual compression

| Fixture | Default Behavior | With `--use-real-hal` or `@pytest.mark.real_hal` |
|---------|------------------|--------------------------------------------------|
| `hal_pool` | MockHALProcessPool (fast) | Real HALProcessPool |
| `hal_compressor` | MockHALCompressor (fast) | Real HALCompressor |
| `mock_hal` | Explicit mock (patches imports) | N/A (always mock) |
| `hal_test_data` | Standard test data patterns | N/A |

**Escape Hatch Markers:**

| Marker | Effect |
|--------|--------|
| `@pytest.mark.allows_registry_state` | Skip pollution detection for this test |
| `@pytest.mark.shared_state_safe` | Required when using `session_managers` (certifies test is stateless) |
| `@pytest.mark.no_manager_setup` | Skip setup_managers fixture |
| `@pytest.mark.real_hal` | Use real HAL implementation |

The `isolated_managers` fixture now pauses active `session_managers` during the test and restores them afterward; it still fails if it cannot restore or if it detects unmanaged registry pollution.

**Common Mistakes to Avoid:**
- `QPixmap` in worker threads causes fatal crashes - use `ThreadSafeTestImage`
- Hardcoded timeout values like `timeout=5000` - use `worker_timeout()` from `timeouts.py`
- Hardcoded thread counts - capture baseline at test start
- `time.sleep()` in Qt tests - use `qtbot.wait()` or `waitSignal()`
- Inheriting `QDialog` in mocks - causes metaclass crashes
- Missing singleton cleanup - use `cleanup_singleton` fixture
- Using `session_managers` without `@pytest.mark.shared_state_safe`

### Wait Helper Usage

| Need | Use | NOT |
|------|-----|-----|
| Wait for condition | `wait_for_condition(qtbot, cond, timeout)` from `qt_waits.py` | `time.sleep()` |
| Wait fixed time | `qtbot.wait(ms)` or `wait_for(qtbot, ms)` | `time.sleep()` |
| Wait for signal | `qtbot.waitSignal(signal, timeout)` | Custom wait loops |
| Wait for thread exit | `thread.wait(timeout)` for QThread | `time.sleep()` + `isRunning()` |

**Intentional sleeps:** If `time.sleep()` is truly needed (thread interleaving tests, OS cleanup), annotate with `# sleep-ok: <reason>`.

**Environment Variables** (set externally, read by `tests/conftest.py`):
- `PYTEST_TIMEOUT_MULTIPLIER=2.0` - Scale all timeouts (useful for slow CI)
- `QT_QPA_PLATFORM=offscreen` - Required for headless Qt testing

## Project Architecture

```
spritepal/
├── core/                  # Business logic
│   ├── managers/          # Manager classes (extraction, injection, session, etc.)
│   ├── protocols/         # Protocol definitions for type safety
│   └── *.py               # Core logic (extractor, validator, etc.)
├── ui/                    # Qt UI components
│   ├── components/        # Reusable widgets
│   ├── dialogs/           # Dialog windows
│   ├── widgets/           # Widget classes
│   ├── windows/           # Main/detached windows
│   ├── workers/           # Background workers
│   └── *.py               # Panel files (rom_extraction_panel.py, etc.)
├── tests/
│   ├── fixtures/          # Test fixtures (qt_fixtures, core_fixtures, etc.)
│   ├── infrastructure/    # RealComponentFactory, test contexts
│   └── *.py               # Test files
└── utils/                 # Shared utilities
```

### Import Rules (see docs/architecture.md)
- **UI** imports from: `core/` (including `core/managers/`), `utils/`
- **Core** imports from: `utils/`
- **Utils** imports from: Python stdlib only

Note: Managers live at `core/managers/`, not a top-level `managers/` directory.

### Manager Architecture (Consolidated)

SpritePal uses a **consolidated manager architecture** with backward-compatible adapters:

```
┌─────────────────────────────────────────────────────────────┐
│                    DI Container (inject())                   │
│  - Protocol-based dependency resolution                      │
│  - Thread-safe singleton/factory management                  │
└─────────────────────┬───────────────────────────────────────┘
                      │
        ┌─────────────┴─────────────┐
        │                           │
        ▼                           ▼
┌──────────────────────┐   ┌────────────────────────┐
│ ApplicationStateManager │ │ CoreOperationsManager  │
│ - Session state         │   │ - Extraction operations │
│ - Settings persistence  │   │ - Injection operations  │
│ - History management    │   │ - Palette management    │
│ - Workflow state        │   │                        │
│                        │   │                        │
│ Adapters:              │   │ Adapters:              │
│ └─ SessionManager      │   │ ├─ ExtractionManager   │
│                        │   │ └─ InjectionManager    │
└──────────────────────┘   └────────────────────────┘
```

**Key Points:**
- Use `inject(ExtractionManagerProtocol)` to get managers - never instantiate directly
- Adapters (SessionManager, ExtractionManager, InjectionManager) provide backward-compatible interfaces
- All managers registered via `initialize_managers()` at app startup
- Cleanup via `cleanup_managers()` at app exit

**Example Usage:**
```python
from core.di_container import inject
from core.protocols.manager_protocols import ExtractionManagerProtocol

# Get manager instance via DI
extraction_manager = inject(ExtractionManagerProtocol)
result = extraction_manager.extract_from_rom(params)
```

### Circular Import Resolution
```python
def open_detached_gallery(self):
    # Local import to avoid circular dependency
    from spritepal.ui.windows.detached_gallery_window import DetachedGalleryWindow
    self.detached_window = DetachedGalleryWindow(self)
```

## Key Patterns

### Resource Management
Always use context managers for file/mmap resources:
```python
@contextmanager
def _rom_context(self):
    rom_file = None
    rom_mmap = None
    try:
        rom_file = Path(self.rom_path).open('rb')
        rom_mmap = mmap.mmap(rom_file.fileno(), 0, access=mmap.ACCESS_READ)
        yield rom_mmap
    finally:
        with suppress(Exception):
            if rom_mmap: rom_mmap.close()
        with suppress(Exception):
            if rom_file: rom_file.close()
```

### Thread Safety
- Use `QMutex/QMutexLocker` for shared state
- Prefer signal-based waiting; avoid sleeps except for narrowly scoped throttling
- Test with `qtbot.waitSignal()` for async operations

### Dialog Initialization (DialogBase pattern)
```python
class MyDialog(DialogBase):
    def __init__(self, parent: QWidget | None = None):
        # Step 1: Declare ALL instance variables BEFORE super().__init__
        self.my_widget: QWidget | None = None

        # Step 2: Call super().__init__() - this calls _setup_ui()
        super().__init__(parent)

    def _setup_ui(self):
        # Step 3: Create widgets
        self.my_widget = QPushButton("Click me")
```

## Background Context

For Mesen2 integration, sprite finding research, and historical documentation,
see `DEV_NOTES.md`. This file contains only operational development guidelines.

---

*Last updated: January 6, 2026*
