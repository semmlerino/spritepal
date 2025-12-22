# SpritePal Test Suite

This directory contains the pytest test suite for SpritePal, featuring **Real Component Testing** infrastructure designed to minimize mock usage and improve test quality and maintainability.

## Quick Start: Real Component Testing

### For New Tests (Recommended)
```python
import pytest
from tests.infrastructure.real_component_factory import RealComponentFactory

@pytest.fixture
def real_factory(isolated_managers):
    """Create RealComponentFactory with proper test isolation."""
    with RealComponentFactory(manager_registry=isolated_managers) as factory:
        yield factory

def test_extraction_workflow(real_factory):
    """Test using real components - no mocks needed!"""
    # Real manager, no casting required
    manager = real_factory.create_extraction_manager(with_test_data=True)

    # Real validation logic
    params = real_factory._data_repo.get_vram_extraction_data("small")
    is_valid = manager.validate_extraction_params(params)
    assert isinstance(is_valid, bool)  # Real behavior
```

### For Qt Widget Tests
```python
def test_real_widget(qtbot, real_factory):
    """Test real Qt widgets with proper lifecycle."""
    widget = real_factory.create_test_widget(qtbot)
    widget.show()
    qtbot.waitExposed(widget)
    # Test real widget behavior
```

### For Integration Tests
```python
from core.di_container import inject
from core.protocols.manager_protocols import ExtractionManagerProtocol, InjectionManagerProtocol

def test_real_integration(isolated_managers):
    """Test real manager integration."""
    extraction = inject(ExtractionManagerProtocol)  # Real ExtractionManager
    injection = inject(InjectionManagerProtocol)    # Real InjectionManager
    # Test real workflow
```

## Testing Philosophy

### Real Components Over Mocks
SpritePal follows the **0.032 mock density threshold** - mocks are used minimally only at system boundaries:

- ✅ **Use Real Components**: Managers, workers, Qt widgets, business logic
- ✅ **Mock System Boundaries**: File I/O, subprocess calls, network requests  
- ✅ **Type Safety**: No unsafe `cast()` operations needed
- ✅ **Authentic Behavior**: Real Qt signals, threading, validation logic

### When to Use Mocks
Mocks are appropriate for:
- External system interfaces (file system, network, subprocess)
- Expensive operations (large file processing)
- Error condition simulation
- Hardware dependencies

Mock at system boundaries only (file I/O, network, subprocess).

## Test Infrastructure

### Core Components
- **RealComponentFactory**: Creates real managers, workers, and UI components with type safety
- **ManagerTestContext**: Manages real manager lifecycles for integration testing
- **DataRepository**: Provides consistent test data (small/medium/comprehensive sizes)
- **Migration Helpers**: Tools for converting mock-based tests to real components

### Directory Structure
```
tests/
├── infrastructure/          # Real component testing framework
│   ├── real_component_factory.py    # Factory for real components
│   ├── manager_test_context.py      # Integration test contexts
│   ├── data_repository.py           # Consistent test data
│   └── qt_mocks.py                  # Qt test doubles
├── fixtures/               # Pytest fixtures
│   ├── core_fixtures.py    # Manager fixtures
│   ├── qt_fixtures.py      # Qt-specific fixtures
│   └── timeouts.py         # Semantic timeout functions
└── test_*.py              # Test files
```

## Test Categories

### Unit Tests with Real Components
- **Core Logic**: `test_extractor.py`, `test_palette_manager.py`
- **Manager Logic**: `test_extraction_manager.py`, `test_injection_manager.py`
- **Utilities**: `test_constants.py`, `test_validation.py`

### Integration Tests
- **Manager Integration**: `test_manager_integration_real_tdd.py`
- **UI Integration**: `test_main_window_state_integration_real.py`
- **Workflow Tests**: `test_unified_dialog_integration_real.py`

### Performance Benchmarks
- Real component performance testing with `pytest-benchmark`
- Memory leak validation with real Qt components
- Threading behavior validation

## Running Tests

### Basic Test Execution
```bash
# All tests with real components
uv run pytest tests/ -v

# Specific test file
uv run pytest tests/test_extraction_manager.py -v

# Integration tests only
uv run pytest tests/ -m "integration" -v

# Skip slow tests
uv run pytest tests/ -m "not slow" -v
```

### Coverage Analysis
```bash
# Coverage with real components
pytest tests/ --cov=core --cov=ui --cov-report=html

# Coverage report shows real integration paths tested
# Open htmlcov/index.html in browser:
#   macOS:   open htmlcov/index.html
#   Linux:   xdg-open htmlcov/index.html
#   Windows: start htmlcov/index.html
#   WSL:     wslview htmlcov/index.html  # or: explorer.exe $(wslpath -w htmlcov/index.html)
```

### Performance Testing
```bash
# Benchmark real component performance
uv run pytest tests/ --benchmark-only

# Memory leak detection (requires: uv pip install memray)
uv run pytest tests/ --memray
```

### Migration Tools

**Preferred approach (ripgrep-based):**
```bash
# Find tests using deprecated patterns (replaces migration_helpers.py)
rg "manager_context|real_factory" tests/

# Check for anti-patterns (replaces check_test_patterns.py)
rg "time\.sleep" tests/ --type py
rg "QPixmap" tests/ --type py | grep -v "ThreadSafeTestImage"
```

**Legacy CLI tools** (still available but prefer ripgrep commands above):
```bash
# Analyze mock usage in test files
python -m tests.infrastructure.migration_helpers analyze tests/test_controller.py

# Generate migration report
python -m tests.infrastructure.migration_helpers report

# Generate migration script
python -m tests.infrastructure.migration_helpers generate tests/test_controller.py
```

## Migration Guide

### Converting Existing Tests

1. **Identify Mock Usage**:
   ```bash
   python -m tests.infrastructure.migration_helpers analyze your_test_file.py
   ```

2. **Replace MockFactory Imports**:
   ```python
   # OLD (deprecated)
   from tests.infrastructure.mock_factory import MockFactory
   
   # NEW (preferred)  
   from tests.infrastructure.real_component_factory import RealComponentFactory
   ```

3. **Remove Unsafe Casting**:
   ```python
   # OLD (unsafe)
   mock_manager = MockFactory.create_extraction_manager()
   manager = cast(ExtractionManager, mock_manager)  # TYPE VIOLATION!

   # NEW (type-safe) - use isolated_managers fixture
   def test_extraction(isolated_managers):
       with RealComponentFactory(manager_registry=isolated_managers) as factory:
           manager = factory.create_extraction_manager()  # Properly typed
   ```

4. **Update Test Logic**:
   ```python
   # OLD (testing mocks)
   mock_manager.extract_sprites.assert_called_once()
   
   # NEW (testing behavior)
   result = manager.extract_sprites(params)
   assert result is not None
   assert isinstance(result, dict)
   ```

See existing real component tests in the test suite for migration patterns.

## Performance Benchmarks

Real component testing performance (vs mocks):

| Test Type | Mock Time | Real Component Time | Overhead |
|-----------|-----------|-------------------|----------|
| Unit Test | 1-5ms | 10-50ms | 2-10x (acceptable) |
| Integration | 5-20ms | 50-200ms | 4-10x (valuable) |  
| UI Test | 10-50ms | 100-500ms | 5-10x (authentic) |

**Trade-off**: Slightly slower execution for dramatically improved test value and maintainability.

## Fixture Quick Reference

### Decision Tree

```
What does your test need?

┌─ Managers (ExtractionManager, SessionManager, etc.)
│  └─ Use `isolated_managers` fixture
│     └─ Need shared state for performance?
│        └─ Add @pytest.mark.shared_state_safe + use `session_managers`
│
├─ Qt widgets (buttons, dialogs, windows)
│  └─ Add @pytest.mark.gui
│     └─ Run with: QT_QPA_PLATFORM=offscreen uv run pytest ...
│
├─ HAL compression/decompression
│  └─ Default: `hal_pool` gives MockHAL (fast)
│     └─ Need real compression? Add @pytest.mark.real_hal
│        └─ See "Running Real HAL Tests" section below
│
├─ Wait for signals
│  └─ Use qtbot.waitSignal() with timeout functions
│     └─ NEVER time.sleep()
│
└─ Images in worker threads
   └─ Use ThreadSafeTestImage, NOT QPixmap
```

### Common Fixture Patterns

**Basic test with managers:**
```python
from core.di_container import inject
from core.protocols.manager_protocols import ExtractionManagerProtocol

def test_extraction_validates_params(isolated_managers):
    # Use inject() to get managers (isolated_managers sets up DI container)
    manager = inject(ExtractionManagerProtocol)
    result = manager.validate_extraction_params({"path": "/test"})
    assert isinstance(result, bool)
```

**Qt widget test:**
```python
@pytest.mark.gui
def test_button_click(qtbot, isolated_managers):
    widget = MyWidget()
    qtbot.addWidget(widget)
    qtbot.mouseClick(widget.button, Qt.LeftButton)
    assert widget.clicked_count == 1
```

**Signal wait test:**
```python
from tests.fixtures.timeouts import worker_timeout

@pytest.mark.gui
def test_worker_completes(qtbot, isolated_managers):
    worker = MyWorker()
    with qtbot.waitSignal(worker.finished, timeout=worker_timeout()):
        worker.start()
```

**Thread-safe image test:**
```python
from tests.infrastructure.thread_safe_test_image import ThreadSafeTestImage

def test_worker_with_image():
    # QPixmap in worker thread = CRASH
    image = ThreadSafeTestImage.create(100, 100)
    worker = ImageWorker(image)
    worker.process()
```

### Fixture Reference

| Fixture | Scope | When to Use |
|---------|-------|-------------|
| `isolated_managers` | function | **Default choice** - clean state each test |
| `session_managers` | session | Performance-critical + `@pytest.mark.shared_state_safe` |
| `hal_pool` | function | HAL operations (mock by default) |
| `qtbot` | function | Qt widget testing |
| `cleanup_singleton` | function | Reset singleton dialogs |

### Timeout Functions

Always use semantic timeouts from `tests/fixtures/timeouts.py`:
```python
from tests.fixtures.timeouts import signal_timeout, worker_timeout, ui_timeout

timeout=ui_timeout()      # ~1000ms - widget visibility, layout updates
timeout=signal_timeout()  # ~2000ms - generic signal waits, event propagation
timeout=worker_timeout()  # ~5000ms - background workers, QThread operations
```

All timeouts scale with `PYTEST_TIMEOUT_MULTIPLIER` environment variable.

### Test Markers

| Marker | Meaning |
|--------|---------|
| `@pytest.mark.gui` | Uses Qt widgets (requires `QT_QPA_PLATFORM=offscreen`) |
| `@pytest.mark.headless` | No display needed |
| `@pytest.mark.real_hal` | Use real HAL (requires `exhal` binary) |
| `@pytest.mark.shared_state_safe` | Test won't pollute state (required with `session_managers`) |

### Anti-Patterns

| Wrong | Right |
|-------|-------|
| `time.sleep(1)` | `qtbot.wait(1000)` |
| `timeout=5000` | `timeout=worker_timeout()` |
| `QPixmap` in worker | `ThreadSafeTestImage` |
| `session_managers` alone | + `@pytest.mark.shared_state_safe` |

---

## Test Guidelines

### Real Component Testing Principles
- **Real First**: Use real components unless there's a specific need for mocking
- **Mock at Boundaries**: Mock external systems (file I/O, network), not business logic
- **Type Safety**: Avoid `cast()` operations - use typed factories instead
- **Authentic Behavior**: Test real Qt signals, threading, and validation logic
- **Proper Cleanup**: Use context managers for resource management

### Code Quality Standards
- **Mock Density**: Target ≤ 0.032 (mocks per line of test code)
- **Type Coverage**: 100% type safety for new test code
- **Signal Testing**: Use `QSignalSpy` and `qtbot.waitSignal()` for Qt testing
- **Worker Testing**: Test real threading behavior with timeouts
- **Memory Management**: Verify cleanup with real component lifecycle testing

### Test Data Management
- **Small Data**: Quick unit tests (< 1KB test files)
- **Medium Data**: Integration tests (1-10KB test files)
- **Comprehensive Data**: Full workflow tests (10KB+ test files)
- **Consistent Paths**: Use `DataRepository` for reliable test data

## Documentation

- **[Real Component Testing Guide](infrastructure/REAL_COMPONENT_TESTING_GUIDE.md)**: Comprehensive patterns and migration guide
- **[Environment Detection](infrastructure/ENVIRONMENT_DETECTION_SUMMARY.md)**: Test environment detection and skip decorators

## Recent Test Suite Improvements

### Isolation & Parallelism (December 2025)

The test suite has been significantly improved for better isolation and parallel execution:

**Isolation Fixes:**
- `ManagerRegistry.reset_for_tests()` now properly resets singleton state
- Added missing singleton resets (PreviewGenerator, SignalRegistry, WorkerManager)
- Session manager state validated before/after tests with `shared_state_safe` marker
- All manager fixtures are function-scoped with automatic cleanup via pytest teardown

**Parallelism:**
- Tests run in parallel by default with `-n auto` (configured in pyproject.toml)
- Tests with `session_managers` are auto-grouped to serial (xdist_group="serial")
- Tests marked `@pytest.mark.parallel_unsafe` are forced to serial
- For serial debugging: `pytest -n 0`

**Race Condition Fixes:**
- Signal-before-waitSignal patterns fixed (use context manager form)
- Hardcoded timeouts replaced with semantic helpers (`worker_timeout()`, etc.)
- `time.sleep()` loops replaced with condition-based polling

**Performance:**
- Thread-leak checker now opt-in (only activates for Qt/worker tests)
- Headless fallback fixed: offscreen Qt is NOT treated as headless
- Real HAL binaries used when `@pytest.mark.real_hal` is set

### Running Real HAL Tests

Tests marked with `@pytest.mark.real_hal` require the `exhal` and `inhal` binaries to be available. By default, these tests gracefully skip when binaries are unavailable.

**Setup:**
1. Build the HAL tools from source (https://github.com/Asmodegun/exhal) or obtain pre-built binaries
2. Set environment variables pointing to the binaries:
   ```bash
   export SPRITEPAL_EXHAL_PATH=/path/to/exhal
   export SPRITEPAL_INHAL_PATH=/path/to/inhal
   ```
3. Alternatively, place binaries in your PATH or in `~/.local/bin/`

**Running:**
```bash
# Run only real HAL tests (skips if binaries not found)
uv run pytest -m real_hal -v

# Force failure instead of skip when binaries missing
uv run pytest -m real_hal --require-real-hal -v

# Regenerate golden data checksums
uv run pytest tests/test_hal_golden.py --regenerate-golden -v
```

**Note:** CI does not have HAL binaries installed; `@pytest.mark.real_hal` tests are skipped in CI. This is by design to keep CI simple while allowing local verification with real compression.

**Removed Fixtures:**
- `setup_managers` - use `isolated_managers` instead
- `class_managers` - use `isolated_managers` instead

## Success Metrics

The real component testing migration is **ongoing** (128 test files, ~2000+ tests):
- ✅ **Infrastructure complete** - RealComponentFactory, DataRepository, migration tools available
- ✅ **New tests use real components** - established patterns throughout test suite
- ✅ **Type safety for new tests** - eliminated unsafe `cast()` operations in migrated tests
- ✅ **Parallel execution** - tests run with `-n auto` by default
- ⚠️ **Target mock density: 0.032** - continuously improving
- 📋 **Next steps** - incrementally migrate heavily-mocked files to RealComponentFactory

## Getting Help

- **Infrastructure**: See `tests/infrastructure/` for framework documentation
- **Patterns**: Review existing real component tests for established patterns
- **CLAUDE.md**: Project-level testing guidelines and quick reference

---

*Last updated: December 21, 2025*