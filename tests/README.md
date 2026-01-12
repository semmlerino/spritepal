# SpritePal Test Suite

This directory contains the pytest test suite for SpritePal, featuring **Real Component Testing** infrastructure.

> **For testing patterns, Qt threading, signal testing, and best practices, see [docs/testing_guide.md](../docs/testing_guide.md).**

---

## Quick Start

### Basic Test with Managers
```python
def test_extraction(app_context):
    """Use app_context fixture for isolated test managers."""
    manager = app_context.core_operations_manager
    result = manager.validate_extraction_params({"path": "/test"})
    assert isinstance(result, bool)
```

### Qt Widget Test
```python
@pytest.mark.gui
def test_button_click(qtbot, app_context):
    widget = MyWidget()
    qtbot.addWidget(widget)
    qtbot.mouseClick(widget.button, Qt.LeftButton)
```

### Signal Wait (Always Use Context Manager)
```python
from tests.fixtures.timeouts import worker_timeout

def test_worker(qtbot, app_context):
    worker = MyWorker()
    with qtbot.waitSignal(worker.finished, timeout=worker_timeout()):
        worker.start()
```

---

## Directory Structure

```
tests/
├── unit/                   # Pure logic tests (no Qt, no app_context)
│   ├── controllers/        # Controller unit tests
│   ├── services/           # Service unit tests
│   └── test_*.py           # Core logic, validators, utilities
├── integration/            # Multi-component tests (Qt, app_context)
│   └── test_*.py           # Manager workflows, Qt widgets, workers
├── ui/                     # UI-specific tests
│   └── components/         # Widget tests
├── infrastructure/         # Test framework components
│   ├── real_component_factory.py    # Factory for real components
│   ├── data_repository.py           # Consistent test data
│   ├── thread_safe_test_image.py    # Thread-safe QPixmap alternative
│   └── qt_mocks.py                  # Qt test doubles
└── fixtures/               # Pytest fixtures
    ├── app_context_fixtures.py      # AppContext fixtures (canonical)
    ├── core_fixtures.py    # Singleton reset, autouse safety
    ├── qt_fixtures.py      # Qt-specific fixtures
    └── timeouts.py         # Semantic timeout functions
```

**Additional Test Location:**
- `ui/sprite_editor/tests/` - Subsystem-specific tests for the sprite editor (48 tests)
  - Automatically collected by pytest via `testpaths = ["tests", "ui/sprite_editor/tests"]` in `pyproject.toml`
  - Run with: `uv run pytest ui/sprite_editor/tests/`

### Where Does My Test Go?

| Test Type | Directory | Criteria |
|-----------|-----------|----------|
| **Unit** | `tests/unit/` | No `app_context`, no `qtbot`, no Qt imports, pure logic |
| **Integration** | `tests/integration/` | Uses `app_context`, managers, or Qt widgets |
| **UI** | `tests/ui/` | Widget-specific tests with complex Qt setup |

**Rule of thumb:** If your test imports from `PySide6` or uses the `app_context` fixture, it's an integration test.

---

## Running Tests

See [CLAUDE.md](../CLAUDE.md#running-tests) for test commands, flags, and debugging workflows.

---

## Manager Access Pattern

**Use `get_app_context()` to access managers:**
```python
from core.app_context import get_app_context

context = get_app_context()
manager = context.core_operations_manager
```

Benefits:
- Explicit manager access via attributes (better IDE support)
- Clearer dependency relationships
- No need to import manager classes for type lookup

**Note:** The `inject()` pattern has been removed. Use `get_app_context()` exclusively.

---

## Fixture Quick Reference

| Fixture | When to Use |
|---------|-------------|
| `app_context` | **Preferred** - clean state each test (from `app_context_fixtures.py`) |
| `session_app_context` | Shared state with `@pytest.mark.shared_state_safe` |
| `test_rom_file` | Create ROM files with various sizes/options |
| `test_vram_file` | Create VRAM dump files |
| `hal_pool` | HAL operations (mock by default) |
| `qtbot` | Qt widget testing |
| `tmp_path` | Temporary files |

## Fixture Lifecycle Map

Reference for fixture scopes, state management, and cleanup. Critical for onboarding and debugging test isolation issues.

⚠️ **Risky Pattern:** Session-scoped fixtures create shared state that can surprise new maintainers. Always use `app_context` (function-scoped, clean per-test) unless you have a specific reason for `session_app_context` AND use `@pytest.mark.shared_state_safe`.

### Session-Scoped Fixtures (⚠️ Shared State)

| Fixture | Location | State | Cleanup | Risk |
|---------|----------|-------|---------|------|
| `qt_app` | `qt_fixtures.py:96` | Single `QApplication` instance | Session end | Qt app singleton; reused across all tests |
| `session_app_context` | `app_context_fixtures.py:29` | Shared `AppContext` + managers | Session end via `reset_app_context()` | State leaks between tests without `@pytest.mark.shared_state_safe` |
| `session_data_repository` | `core_fixtures.py:148` | Shared test data files | Session end (files in system temp) | Real ROM data may not be found in CI |
| `capture_thread_baseline` | `qt_fixtures.py:96` | Thread count snapshot | Session end | Detects worker cleanup failures |
| `worker_temp_root` | `xdist_fixtures.py:46` | Temp directory per xdist worker | Session end | Parallel safety: each worker gets isolated temp |
| `configure_worker_environment` | `xdist_fixtures.py:46` | Environment variables (PYTEST_TIMEOUT_MULTIPLIER, etc.) | Session end (cleared) | Affects all tests in worker |

**When to use session fixtures:**
- Test is read-only (no state mutations)
- You explicitly add `@pytest.mark.shared_state_safe`
- You understand parallel execution implications (workers are isolated; tests within a worker share state)

### Function-Scoped Fixtures (✅ Clean Per-Test)

| Fixture | Location | State | Cleanup | Notes |
|---------|----------|-------|---------|-------|
| `app_context` | `app_context_fixtures.py:29` | Fresh `AppContext` + managers | Auto-reset + event processing | **Preferred**. Creates new context if none exists; suspends session context if present |
| `clean_registry_state` | `core_fixtures.py:148` | Manager singletons (HAL, config, palette) | Suspend/reset + processes events (if not headless) | Ensures managers start clean |
| `isolated_data_repository` | `core_fixtures.py:148` | Test files in `tmp_path` | Auto-cleanup via `tmp_path` | Parallel-safe; files deleted after test |
| `main_window` | `qt_fixtures.py:96` | `QMainWindow` instance | Destroyed at test end | Requires `qtbot` fixture |
| `cleanup_workers` | `qt_fixtures.py:96` | `WorkerManager` shutdown | Checks for leaks + stops active workers | Autouse; detects threading bugs |
| `cleanup_singleton` | `qt_fixtures.py:96` | Qt singleton state | Clears singleton on teardown | Prevents cross-test contamination |
| `real_extraction_manager` | `core_fixtures.py:148` | Real `ExtractionManager` instance | Auto-cleanup | Accessor; uses `app_context` internally |
| `real_injection_manager` | `core_fixtures.py:148` | Real `InjectionManager` instance | Auto-cleanup | Accessor; uses `app_context` internally |
| `real_session_manager` | `core_fixtures.py:148` | Real `SessionManager` instance | Auto-cleanup | Accessor; uses `app_context` internally |
| `hal_pool` | `hal_fixtures.py:63` | HAL compression pool (mock or real) | Shutdown pool on teardown | Real mode with `@pytest.mark.real_hal` |
| `hal_compressor` | `hal_fixtures.py:63` | `HALCompressor` singleton | Reset + shutdown on teardown | Real/mock per config |
| `test_rom_file` | `test_data_fixtures.py:87` | ROM file in `tmp_path` | Auto-cleanup | Factory; pass `size="default"` etc. |
| `test_vram_file` | `test_data_fixtures.py:87` | VRAM file in `tmp_path` | Auto-cleanup | Factory; pass `size=...` in bytes |
| `rom_cache` | `core_fixtures.py:148` | ROM cache in `tmp_path` | Auto-cleanup | Isolated per-test cache |
| `multi_signal_recorder` | `ui/integration/conftest.py:19` | Signal recorder factory | Clears recorders on teardown | Returns callable to create `MultiSignalRecorder` instances |

### Autouse Fixtures (Always Active)

| Fixture | Location | Purpose | Applies To | Notes |
|---------|----------|---------|------------|-------|
| `skip_requires_display` | `conftest.py:451` | Skip tests marked `@pytest.mark.requires_display` in headless mode | All tests | Checks `QT_QPA_PLATFORM=offscreen` |
| `verify_cleanup` | `conftest.py:451` | Assert no active operations at test end | All tests | Catches resource leaks |
| `enforce_shared_state_safe` | `conftest.py:451` | Enforce `@pytest.mark.shared_state_safe` with `session_app_context` | All tests using `session_app_context` | Prevents accidental state sharing |
| `reset_hal_singletons` | `hal_fixtures.py:63` | Clear HAL singleton state between tests | All tests (if HAL fixture used) | Prevents cross-test contamination |
| `capture_thread_baseline` | `qt_fixtures.py:96` | Detect worker/thread leaks | All Qt tests | Session autouse; checks final thread count |

### Utility Functions (No Scope)

| Function | Location | Returns | Cleanup |
|----------|----------|---------|---------|
| `test_data_factory` | `conftest.py:451` | Bytearray factory | No persistent state |
| `temp_files` | `conftest.py:451` | `NamedTemporaryFile` wrapper | Deletes on teardown |
| `standard_test_params` | `conftest.py:451` | Test parameters (uses `temp_files` + `tmp_path`) | Via `temp_files` |
| `mock_manager_registry` | `conftest.py:451` | Mock registry | No cleanup needed (Mock) |
| `wait_for`, `process_events`, etc. | `qt_waits.py:52` | Signal wait utilities | Semantic timeout helpers |

### Dependency Graph

```
qt_app (session)
  ↓
  ├─ session_app_context (session, depends on qt_app)
  │   └─ app_context (function, auto-suspends session if present)
  │       └─ clean_registry_state (function, resets singletons)
  │
  ├─ capture_thread_baseline (session autouse, detects leaks)
  │   └─ cleanup_workers (function autouse, stops leaks)
  │
  ├─ reset_hal_singletons (autouse)
  │   └─ hal_pool (function)
  │
  └─ worker_temp_root (session)
      └─ configure_worker_environment (session autouse, sets env vars)

test_rom_file, test_vram_file (function)
  └─ tmp_path (pytest built-in)
```

### Key Patterns

**Rule 1: Use `app_context` by default**
```python
def test_extraction(app_context):  # Clean state, auto-reset
    manager = app_context.core_operations_manager
    result = manager.extract(...)
    assert result is not None
```

**Rule 2: Use `session_app_context` only with marker**
```python
@pytest.mark.shared_state_safe  # REQUIRED
def test_shared_data(session_app_context):
    # Shared managers reused across test
    result = session_app_context.core_operations_manager.extract(...)
```

**Rule 3: Autouse fixtures are transparent**
```python
def test_anything(app_context):
    # skip_requires_display, verify_cleanup, reset_hal_singletons
    # all run automatically—no explicit dependency needed
    pass
```

**Rule 4: tmp_path is always available**
```python
def test_files(tmp_path):  # pytest built-in, always clean
    output = tmp_path / "result.bin"
    # Files auto-deleted after test
```

### Debugging Fixture Issues

| Symptom | Likely Cause | Fix |
|---------|--------------|-----|
| Test passes in isolation, fails parallel | Shared session state | Add `@pytest.mark.shared_state_safe` or use `app_context` |
| "Fatal Python error: Aborted" | `QPixmap` in worker thread | Use `ThreadSafeTestImage` instead |
| Hangs or timeout | Worker not cleaned up | Check `cleanup_workers` fixture; verify no threads spawned without cleanup |
| State leaks to next test | Session fixture reused | Use function-scoped fixture (default: `app_context`) |
| Real ROM data not found | `session_data_repository` in CI | Use `DataRepository.find_real_kirby_rom()` with fallback |

---

## Test Data Sources

SpritePal has three test data generation systems. Use the right one for your needs:

| System | Location | When to Use |
|--------|----------|------------|
| **`test_data_fixtures.py`** | `tests/fixtures/` | **Single file needed (PREFERRED)** - use `test_rom_file` or `test_vram_file` fixtures |
| **`TestDataFactory`** | `tests/fixtures/test_data_factory.py` | Complete test setup (ROM + VRAM + CGRAM + OAM + sprite + palette) for integration tests |
| **`DataRepository`** | `tests/infrastructure/data_repository.py` | Session-scoped shared test data, real test data lookup, centralized management |

### Recommendation

**Use `test_data_fixtures.py` for 90% of tests.** It's the simplest, most reliable, and has zero overhead:

```python
# Most tests look like this
def test_extraction(test_rom_file, tmp_path):
    rom_path = test_rom_file(size="default")
    result = validate_extraction(rom_path)
    assert result is not None
```

### When to Use Each System

#### 1. Single File Tests (PREFERRED) - `test_data_fixtures.py`

Use the pytest fixtures `test_rom_file` and `test_vram_file` when you need just one or two files:

```python
def test_rom_validation(test_rom_file):
    """Simple test with default 1MB ROM."""
    rom_path = test_rom_file()  # Creates in tmp_path automatically
    assert Path(rom_path).exists()

def test_various_sizes(test_rom_file, test_vram_file):
    """Test with different sizes."""
    small_rom = test_rom_file(size="small")  # 32KB
    large_rom = test_rom_file(size="large")  # 2MB
    vram = test_vram_file(size=32 * 1024)    # Custom 32KB
```

**Presets:** `"tiny"` (13KB), `"small"` (32KB), `"medium"` (512KB), `"default"` (1MB), `"large"` (2MB)

#### 2. Complete Test Setups - `TestDataFactory`

Use `TestDataFactory` for integration tests needing the full pipeline (ROM + VRAM + CGRAM + OAM + sprite + palette):

```python
from tests.fixtures.test_data_factory import TestDataFactory

def test_full_extraction_workflow(tmp_path):
    """Complete extraction test with all file types."""
    paths = TestDataFactory.create_test_files(tmp_path)

    # Now you have:
    # paths.rom_path, paths.vram_path, paths.cgram_path, paths.oam_path
    # paths.sprite_path, paths.palette_path, paths.metadata_path
    # paths.output_dir

    result = manager.extract_sprite(paths.rom_path, output_dir=paths.output_dir)
    assert result.success
```

**For injection tests:**
```python
def test_injection_workflow(tmp_path):
    """Injection-specific setup (zeroed ROM/VRAM)."""
    paths = TestDataFactory.create_injection_test_files(tmp_path)
    result = manager.inject_sprite(paths.sprite_path, paths.rom_path)
    assert result.success
```

#### 3. Centralized Data - `DataRepository`

Use the `isolated_data_repository` fixture for **per-test isolated data** with automatic cleanup:

```python
def test_with_repository(app_context, isolated_data_repository):
    """Access test data repository with per-test isolation."""
    # Get pre-configured extraction params
    params = isolated_data_repository.get_vram_extraction_data("medium")
    # Returns dict with: vram_path, cgram_path, oam_path, output_base, etc.

    result = app_context.core_operations_manager.extract(**params)
```

**When to use:**
- Tests need **generated test files** (VRAM, ROM, CGRAM)
- Tests access **real Kirby ROM data** (DataRepository finds it)
- You need **consistent parameters** across tests (e.g., offset, size)

**DEPRECATED:** The `get_test_data_repository()` singleton is deprecated. It accumulates
temp directories across the session and doesn't provide parallel test isolation.
Use `isolated_data_repository` fixture instead.

```python
# DEPRECATED - do not use in new tests
from tests.infrastructure.data_repository import get_test_data_repository
repo = get_test_data_repository()  # Emits DeprecationWarning

# RECOMMENDED - use fixture
def test_isolated_repo(isolated_data_repository):
    """Isolated DataRepository (no conflicts in parallel tests)."""
    params = isolated_data_repository.get_vram_extraction_data("small")
    # Files live in tmp_path, auto-cleaned after test
```

### Test Data Patterns

| Need | Use |
|------|-----|
| Single ROM file | `test_rom_file(size="...")` fixture |
| Single VRAM file | `test_vram_file(size=...)` fixture |
| Complete test setup | `TestDataFactory.create_test_files(tmp_path)` |
| Injection test files | `TestDataFactory.create_injection_test_files(tmp_path)` |
| **Per-test data (recommended)** | `isolated_data_repository` fixture |
| ~~Shared data (session-scoped)~~ | ~~`get_test_data_repository()`~~ (deprecated) |

**Note:** `app_context` and `session_app_context` can safely coexist in the same test run. When `app_context` detects an existing session context, it uses `suspend_app_context()` to temporarily hide it, creates an isolated context for the test, then restores the session context afterward. This prevents function-scoped tests from destroying session-scoped contexts.

### Timeout Functions

```python
from tests.fixtures.timeouts import ui_timeout, signal_timeout, worker_timeout

timeout=ui_timeout()      # ~1000ms - widget visibility
timeout=signal_timeout()  # ~2000ms - generic signals
timeout=worker_timeout()  # ~5000ms - background workers
```

### Test Markers

| Marker | Effect |
|--------|--------|
| `@pytest.mark.gui` | Qt widget test (runs in offscreen mode) |
| `@pytest.mark.real_hal` | Use real HAL binaries (skips if unavailable) |
| `@pytest.mark.shared_state_safe` | Required with `session_app_context` |
| `@pytest.mark.requires_display` | Skipped in offscreen mode |

---

## Anti-Patterns

| Wrong | Right |
|-------|-------|
| `time.sleep(1)` | `qtbot.wait(1000)` |
| `timeout=5000` | `timeout=worker_timeout()` |
| `QPixmap` in worker thread | `ThreadSafeTestImage` |
| `session_app_context` alone | + `@pytest.mark.shared_state_safe` |
| Hardcoded `/tmp/test.bin` | `tmp_path / "test.bin"` |

---

## Real HAL Tests

Tests marked `@pytest.mark.real_hal` require the `exhal`/`inhal` binaries:

```bash
# Set paths
export SPRITEPAL_EXHAL_PATH=/path/to/exhal
export SPRITEPAL_INHAL_PATH=/path/to/inhal

# Run real HAL tests
uv run pytest -m real_hal -v

# Force failure if binaries missing
uv run pytest -m real_hal --require-real-hal -v
```

**Note:** CI skips real HAL tests by design.

---

## RealComponentFactory

For integration tests with real components:

```python
from tests.infrastructure.real_component_factory import RealComponentFactory

def test_workflow(app_context, isolated_data_repository):
    # Access managers directly from app_context
    manager = app_context.core_operations_manager

    # Use isolated_data_repository fixture for test data
    params = isolated_data_repository.get_vram_extraction_data("small")
    result = manager.validate_extraction_params(params)

# For Qt component creation, use RealComponentFactory with explicit data_repository
def test_with_workers(app_context, isolated_data_repository):
    with RealComponentFactory(data_repository=isolated_data_repository) as factory:
        params = isolated_data_repository.get_vram_extraction_data("small")
        worker = factory.create_extraction_worker(params)
        # ... test code ...
```

---

## More Information

- **Testing patterns & best practices**: [docs/testing_guide.md](../docs/testing_guide.md)
- **Fixture cheatsheet**: [tests/FIXTURE_CHEATSHEET.md](FIXTURE_CHEATSHEET.md)
- **Infrastructure docs**: `tests/infrastructure/` subdirectories

---

*Last updated: January 5, 2026 (Added Test Data Sources section with consolidation guidance)*
