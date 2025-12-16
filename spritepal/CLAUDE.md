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

All tools run via `uv` from the `spritepal/` directory.

**Defaults configured in `pyproject.toml`.** Qt offscreen mode set automatically in `conftest.py`.

**Note:** If `uv` is not in PATH (common in some CI environments), use the full path: `~/.local/bin/uv run ...`

```bash
# Sync dependencies (uv finds workspace root automatically)
uv sync --extra dev

# Linting
uv run ruff check .
uv run ruff check . --fix

# Type checking
uv run basedpyright core ui utils

# Tests - routine run (uses pyproject.toml defaults: -v --tb=short -ra --maxfail=3)
uv run pytest

# Tests - on failure, drill down with full context
uv run pytest tests/path/test_file.py::TestClass::test_name -vv --tb=long -s

# Tests - full suite (override maxfail)
uv run pytest --maxfail=10

# Tests - parallel (marked tests only)
uv run pytest -m parallel_safe -n auto
```

**Do not use `-q` when debugging failures** - it hides information you need.

## Qt Testing Best Practices

### Real Component Testing (Preferred)

SpritePal uses real components over mocks. **Prefer real components; mock only at true system boundaries** (file I/O, clipboard, network). HAL is mock-by-default because the real `exhal` binary is slow and may not be available.

```python
from tests.infrastructure.real_component_factory import RealComponentFactory

def test_extraction_workflow(tmp_path):  # Always use tmp_path for file operations
    with RealComponentFactory() as factory:
        manager = factory.create_extraction_manager(with_test_data=True)
        # Create test files in tmp_path (parallel-safe, auto-cleaned)
        vram_file = tmp_path / "vram.bin"
        cgram_file = tmp_path / "cgram.bin"
        vram_file.write_bytes(b"\x00" * 0x8000)  # Test data
        cgram_file.write_bytes(b"\x00" * 0x200)
        params = {
            "vram_path": str(vram_file),
            "cgram_path": str(cgram_file),
            "output_base": str(tmp_path / "test_sprite"),
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

**Always use the context manager form** — it handles both fast and slow signals without race conditions:

```python
from tests.fixtures.timeouts import worker_timeout, signal_timeout, LONG

# PREFERRED: Context manager catches signals that emit before/during/after start()
def test_async_operation(qtbot, worker):
    with qtbot.waitSignal(worker.finished, timeout=worker_timeout()):
        worker.start()

# Multiple possible outcomes - test ONE path per test (pytest-qt has no "wait for any"):
def test_worker_success(qtbot, worker):
    with qtbot.waitSignal(worker.finished, timeout=worker_timeout()):
        worker.start()  # Configure worker for success path

def test_worker_failure(qtbot, worker):
    with qtbot.waitSignal(worker.failed, timeout=worker_timeout()):
        worker.start()  # Configure worker for failure path

# For slow operations, use the LONG multiplier:
def test_slow_extraction(qtbot, worker):
    with qtbot.waitSignal(worker.finished, timeout=worker_timeout(LONG)):
        worker.start()
```

**⚠️ Anti-pattern (causes flaky tests):**
```python
# DON'T: Races with fast-completing workers
worker.start()
qtbot.waitSignal(worker.finished, timeout=worker_timeout())  # May miss signal!
```

**Timeout Reference** (base values, scaled by `PYTEST_TIMEOUT_MULTIPLIER`):

| Function | Base (ms) | Use For |
|----------|-----------|---------|
| `ui_timeout()` | 1000 | Widget visibility, layout updates |
| `signal_timeout()` | 2000 | Generic signal waits, event propagation |
| `dialog_timeout()` | 3000 | Dialog accept/reject |
| `worker_timeout()` | 5000 | Background workers, QThread operations |
| `cleanup_timeout()` | 2000 | Thread termination, resource cleanup |

Multipliers: `SHORT=0.5`, `MEDIUM=1.0` (default), `LONG=2.0`

**Important:** These are **functions** from `tests/fixtures/timeouts.py`, not fixtures. Import them explicitly:
```python
from tests.fixtures.timeouts import worker_timeout, signal_timeout, ui_timeout, LONG
```

**Note:** The global `timeout = 30` in pyproject.toml (pytest-timeout) is for *test execution time*, not signal waits. These semantic timeout functions are for Qt signal/event waiting within tests.

**Timeout Escalation Policy:**
- If a test times out in CI but passes locally: **fix the async logic**, don't increase `PYTEST_TIMEOUT_MULTIPLIER`
- Only increase multiplier for known-slow environments (e.g., ARM CI runners, resource-constrained VMs)
- Never use multiplier >3.0 without investigating root cause first
- If you find yourself repeatedly increasing timeouts for a test, the test is flaky—fix the race condition

### Test Markers

| Marker | Requires Display | Can Combine With | Notes |
|--------|-----------------|------------------|-------|
| `@pytest.mark.gui` | Yes (offscreen OK) | `parallel_safe`, `slow` | Uses real Qt widgets |
| `@pytest.mark.headless` | No | `parallel_safe`, `slow` | No rendering needed |
| `@pytest.mark.serial` | — | Any | Forces sequential execution |
| `@pytest.mark.parallel_safe` | — | `gui`, `headless` | Safe for pytest-xdist |

**Mutual exclusivity:** `gui` and `headless` are mutually exclusive — a test is either one or the other.

**Note**: Qt offscreen mode is set automatically in `conftest.py`. Do NOT use pytest-xvfb - it causes hangs in WSL2 and some CI environments.

### Parallel Test Execution (pytest-xdist)

SpritePal supports parallel test execution using pytest-xdist with a conservative opt-in approach.

**Running Tests:**
```bash
# Serial execution (default)
uv run pytest

# Parallel execution for marked tests only
uv run pytest -m parallel_safe -n auto

# Run both: serial tests first, then parallel-safe tests
uv run pytest -m "not parallel_safe" && uv run pytest -m parallel_safe -n auto
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

**Validation:** The `check_parallel_isolation` fixture (`autouse=True`) validates at test
execution time that `parallel_safe` tests don't use incompatible fixtures. Tests using
`session_managers` with `@pytest.mark.parallel_safe` will fail with an explicit error message.
Note: `class_managers` has been removed entirely and fails immediately if used.

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

**Quick Decision Flowchart:**
```
┌─ Writing a NEW test? ─────────────────────────────────────────────────┐
│                                                                        │
│  Q1: Does the test modify manager state (caches, counters, config)?   │
│      YES → Use `isolated_managers` (DEFAULT)                          │
│      NO  → Continue to Q2                                             │
│                                                                        │
│  Q2: Is the test a read-only operation verified stateless?            │
│      YES → Use `session_managers` + `@pytest.mark.shared_state_safe`  │
│      NO  → Use `isolated_managers` (DEFAULT)                          │
│                                                                        │
│  Q3: Need parallel execution with pytest-xdist?                       │
│      YES → Use `isolated_managers` + `tmp_path` + `@pytest.mark.parallel_safe` │
│      NO  → Default choice still applies                               │
│                                                                        │
│  When in doubt: Use `isolated_managers` — it's slower but always safe │
└────────────────────────────────────────────────────────────────────────┘
```

| Need | Use | NOT |
|------|-----|-----|
| **Default for all tests** | `isolated_managers` | `session_managers` |
| Proven-safe shared state | `session_managers` + `@pytest.mark.shared_state_safe` (enforced) | bare `session_managers` (fails) |
| Real component testing | `RealComponentFactory` | `Mock()` + `cast()` |
| Qt images in worker thread | `ThreadSafeTestImage` | `QPixmap` |
| Singleton dialog cleanup | `cleanup_singleton` fixture (auto-cleans DialogRegistry) | Own cleanup fixture |
| Signal waiting | `qtbot.waitSignal()` | `time.sleep()` |
| HAL with mocks (fast) | `hal_pool` (default) | Real HAL |
| HAL with real impl | `@pytest.mark.real_hal` | Mock HAL |

**Why `isolated_managers` is the default:** `session_managers` persists state across ALL tests in a session. This causes order-dependent failures when tests assume clean state. Only use `session_managers` for tests explicitly verified to be stateless.

**Manager Fixture Isolation Levels:**

| Fixture | Scope | Reset Between Tests | Use When |
|---------|-------|---------------------|----------|
| `isolated_managers` | Function | YES (full cleanup) | **Default choice** - tests that need predictable state |
| `setup_managers` | Function | YES | Alternative default with conditional setup |
| `session_managers` | Session | NO | Only with `@pytest.mark.shared_state_safe` |
| `reset_manager_state` | Function | YES (caches only) | Need clean counters without full isolation |

**Deprecated fixtures (do not use in new code):**

| Fixture | Replacement | Reason |
|---------|-------------|--------|
| `setup_managers` | `isolated_managers` | Deprecated, use `isolated_managers` for per-test isolation |
| `class_managers` | `isolated_managers` | **REMOVED** - fails immediately with error. Use `isolated_managers` |

**⚠️ Do not mix `session_managers` and `isolated_managers` in the same module.** Same-module mixing causes test failures—this is intentional. It indicates a test design problem where some tests expect clean state while others expect shared state. Keep each test module consistent: either all `isolated_managers` or all `session_managers` (with proper markers). Cross-module usage (different files using different fixtures) is handled automatically.

**HAL Fixtures:**

HAL (compression/decompression) is **mock-by-default** because:
- Real HAL requires the external `exhal` binary which may not be available
- Mock HAL is ~100x faster (~1ms vs ~100ms per operation)
- Use `@pytest.mark.real_hal` only for integration tests validating actual compression
- Tests marked `@pytest.mark.real_hal` will **skip** if `exhal` is not in PATH

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
| `@pytest.mark.shared_state_safe` | **Enforced** when using `session_managers` - test fails without it |
| `@pytest.mark.no_manager_setup` | Skip setup_managers fixture |
| `@pytest.mark.real_hal` | Use real HAL implementation |
| `@pytest.mark.skip_thread_cleanup(reason='...')` | Skip thread leak detection (**reason required!**) |
| `@pytest.mark.no_qt` | Skip all Qt-related fixtures (implies skip_thread_cleanup) |
| `@pytest.mark.parallel_unsafe` | Force serial execution under xdist (for wrapper fixtures) |

**Important:** `skip_thread_cleanup` **requires** a `reason` argument explaining why thread cleanup is skipped. Tests without a reason will fail with `pytest.UsageError`. Example:
```python
@pytest.mark.skip_thread_cleanup(reason='Uses session_managers which owns threads')
def test_with_owned_threads():
    ...
```

**Common Mistakes to Avoid:**
- `QPixmap` in worker threads causes fatal crashes - use `ThreadSafeTestImage`
- Hardcoded thread counts - capture baseline at test start
- `time.sleep()` in Qt tests - use `qtbot.wait()` or `waitSignal()`
- Inheriting `QDialog` in mocks - causes metaclass crashes
- Missing singleton cleanup - use `cleanup_singleton` fixture
- Using `session_managers` without `@pytest.mark.shared_state_safe`
- Custom fixtures wrapping `session_managers` without `@pytest.mark.parallel_unsafe` - auto-grouping won't detect the dependency

### Wait Helper Usage

| Need | Use | NOT |
|------|-----|-----|
| Wait for condition | `wait_for_condition(qtbot, cond, timeout)` from `qt_waits.py` | `time.sleep()` |
| Wait fixed time | `qtbot.wait(ms)` or `wait_for(qtbot, ms)` | `time.sleep()` |
| Wait for signal | `qtbot.waitSignal(signal, timeout)` | Custom wait loops |
| Wait for thread exit | `thread.wait(timeout)` for QThread | `time.sleep()` + `isRunning()` |

**Intentional sleeps:** If `time.sleep()` is truly needed (thread interleaving tests, OS cleanup), annotate with `# sleep-ok: <reason>`.

**Environment Variables** (optional, read by `tests/conftest.py`):
- `PYTEST_TIMEOUT_MULTIPLIER=2.0` - Scale all timeouts (useful for slow CI)

Note: `QT_QPA_PLATFORM=offscreen` is set at the **top** of conftest.py (before any Qt imports) to ensure reliable headless operation. Do not add Qt imports above line 56 in conftest.py.

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

### Manager Architecture (Consolidated with Adapters)

SpritePal uses a **consolidated manager architecture** with inheritance-based adapters:

```
┌─────────────────────────────────────────────────────────────┐
│            DI Container (inject() via protocols)            │
│  - inject(SessionManagerProtocol)    → SessionAdapter       │
│  - inject(ExtractionManagerProtocol) → ExtractionAdapter    │
│  - inject(InjectionManagerProtocol)  → InjectionAdapter     │
└───────────────────────────┬─────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        ▼                   ▼                   ▼
┌──────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│ ApplicationState │ │ CoreOperations  │ │   Monitoring    │
│     Manager      │ │     Manager     │ │     Manager     │
│ (session, state, │ │ (extraction,    │ │ (performance)   │
│  settings, hist) │ │  injection,     │ │                 │
│                  │ │  palette)       │ │                 │
└────────┬─────────┘ └────────┬────────┘ └─────────────────┘
         │                    │
         │ provides           │ provides
         ▼                    ▼
┌──────────────────┐ ┌──────────────────────────────────────┐
│  SessionAdapter  │ │ ExtractionAdapter │ InjectionAdapter │
│ (extends         │ │ (extends          │ (extends         │
│  SessionManager) │ │  ExtractionMgr)   │  InjectionMgr)   │
└────────┬─────────┘ └────────┬─────────┴──────┬───────────┘
         │                    │                │
    inherits from        inherits from    inherits from
         ▼                    ▼                ▼
┌──────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│ SessionManager   │ │ExtractionManager│ │InjectionManager │
│ (DEPRECATED      │ │ (DEPRECATED     │ │ (DEPRECATED     │
│  base class)     │ │  base class)    │ │  base class)    │
└──────────────────┘ └─────────────────┘ └─────────────────┘
```

**Key Points:**
- **Always use DI**: `inject(XxxManagerProtocol)` - never instantiate managers directly
- **Consolidated managers** hold all business logic (ApplicationStateManager, CoreOperationsManager)
- **Adapters** (SessionAdapter, ExtractionAdapter, InjectionAdapter) inherit from legacy base classes
  for interface compatibility but delegate all work to consolidated managers
- **Legacy managers** (SessionManager, ExtractionManager, InjectionManager) exist only as base classes
  for adapters - direct instantiation is deprecated and emits a warning

**Example Usage (Production Code):**
```python
from core.di_container import inject
from core.protocols.manager_protocols import (
    SessionManagerProtocol,
    ExtractionManagerProtocol,
    InjectionManagerProtocol,
)

# Correct: Use DI to get adapter instances
session_mgr = inject(SessionManagerProtocol)
extraction_mgr = inject(ExtractionManagerProtocol)
injection_mgr = inject(InjectionManagerProtocol)

# DEPRECATED: Direct instantiation emits DeprecationWarning
# from core.managers import SessionManager
# session_mgr = SessionManager()  # Don't do this!
```

**In Tests:** Use fixtures, not `inject()` directly:
```python
# CORRECT: Fixtures provide isolated or session-scoped managers
def test_extraction(isolated_managers):  # or session_managers + marker
    from core.managers.registry import ManagerRegistry
    registry = ManagerRegistry()
    extraction_mgr = registry.extraction_manager
    # ... test code ...

# WRONG: inject() returns shared singletons, breaks test isolation
def test_extraction_wrong():
    extraction_mgr = inject(ExtractionManagerProtocol)  # Don't do this in tests!
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

*Last updated: December 15, 2025*
