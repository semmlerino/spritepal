# SpritePal Test Markers Guide

This document explains the test markers used in SpritePal's test suite and when to use each one.

## Quick Reference

| Need | Markers | Command |
|------|---------|---------|
| Fast tests | `headless`, `unit`, `no_qt` | `QT_QPA_PLATFORM=offscreen pytest -m "headless and not slow"` |
| GUI tests | `gui`, `requires_display` | `QT_QPA_PLATFORM=offscreen pytest -m gui` |
| CI tests | `ci_safe`, `headless` | `QT_QPA_PLATFORM=offscreen pytest -m ci_safe` |
| Skip managers | `no_manager_setup` | `QT_QPA_PLATFORM=offscreen pytest -m no_manager_setup` |
| Parallel safe | `parallel_safe` | `QT_QPA_PLATFORM=offscreen pytest -m parallel_safe -n auto` |

## Marker Categories

### Environment Markers

These control WHERE and HOW tests run:

| Marker | Usage Count | Description | Use When |
|--------|-------------|-------------|----------|
| `gui` | ~137 | Requires display/X11 | Test renders actual Qt widgets |
| `headless` | ~134 | No display required | Test logic only, no rendering |
| `requires_display` | ~45 | Explicit display requirement | Test needs pixel-level operations |
| `ci_safe` | ~81 | Safe for CI environments | Test won't flake in CI |

**Examples:**
```python
@pytest.mark.gui  # Uses real Qt widgets (run with QT_QPA_PLATFORM=offscreen)
def test_dialog_renders():
    dialog = MyDialog()
    dialog.show()
    assert dialog.isVisible()

@pytest.mark.headless  # Can run anywhere
def test_dialog_logic():
    dialog = MyDialog()
    assert dialog.validate_input("test") is True
```

### Test Type Markers

These categorize WHAT the test does:

| Marker | Usage Count | Description | Use When |
|--------|-------------|-------------|----------|
| `unit` | ~30 | Fast, isolated tests | Testing single function/class |
| `integration` | ~146 | Component interaction tests | Testing multiple components together |
| `benchmark` | ~29 | Performance benchmarks | Measuring execution time |
| `performance` | ~44 | Performance tests | Checking performance characteristics |
| `slow` | ~58 | Tests >1s execution | Long-running operations |
| `stress` | ~few | Load testing | Concurrent operations, memory limits |

**Examples:**
```python
@pytest.mark.unit
def test_parse_offset():
    assert parse_hex_offset("0x1000") == 4096

@pytest.mark.integration
@pytest.mark.slow
def test_full_extraction_workflow():
    # Multi-step workflow test
    ...
```

### Qt Component Markers

These indicate Qt component requirements:

| Marker | Usage Count | Description | Use When |
|--------|-------------|-------------|----------|
| `qt_real` | ~38 | Uses real Qt components | Testing actual Qt behavior |
| `qt_mock` | ~25 | Uses mocked Qt components | Fast tests, no Qt needed |
| `qt_app` / `qt_application` | ~16 | Needs QApplication | Any Qt widget test |
| `no_qt` | ~47 | Zero Qt dependencies | Pure Python tests |
| `qt_threading` | ~few | Qt threading tests | Tests using QThread |
| `qt_no_exception_capture` | ~few | Disable exception capture | Testing exception behavior |

**Examples:**
```python
@pytest.mark.qt_real
@pytest.mark.qt_app
def test_widget_signals(qtbot):
    widget = MyWidget()
    with qtbot.waitSignal(widget.clicked):
        qtbot.mouseClick(widget, Qt.LeftButton)

@pytest.mark.no_qt
def test_pure_python_logic():
    result = calculate_sprite_offset(0x1000, 16)
    assert result == 0x1010
```

### Manager Markers

These control manager fixture behavior:

| Marker | Usage Count | Description | Use When |
|--------|-------------|-------------|----------|
| `no_manager_setup` | ~39 | Skip manager initialization | Test creates own managers |
| `isolated_managers` | ~few | Fresh manager instances | Test modifies manager state |
| `allows_registry_state` | ~few | Skip pollution detection | Legacy test with shared state |

**Examples:**
```python
@pytest.mark.no_manager_setup  # Don't auto-initialize managers
def test_custom_manager_setup():
    manager = MyManager(custom_config=True)
    ...

# Tests using session_managers fixture should be aware of shared state
# Use isolated_managers if you need clean state
```

### Data and Resource Markers

These indicate external dependencies:

| Marker | Usage Count | Description | Use When |
|--------|-------------|-------------|----------|
| `rom_data` | ~113 | ROM data processing | Test uses ROM bytes |
| `file_io` | ~79 | File operations | Test reads/writes files |
| `cache` | ~29 | Cache interactions | Test uses thumbnail/data cache |
| `real_hal` | ~11 | Real HAL compression | Test needs actual HAL subprocess |
| `requires_rom` | ~few | Requires ROM file | Test needs physical ROM file |
| `memory` | ~few | Memory leak tests | Test checks memory usage |

**Examples:**
```python
@pytest.mark.rom_data
@pytest.mark.file_io
def test_extract_sprite_from_rom(tmp_path):
    rom_path = tmp_path / "test.sfc"
    rom_path.write_bytes(mock_rom_data())
    ...

@pytest.mark.real_hal  # Use actual HAL, not mock
def test_hal_compression_accuracy():
    ...
```

### UI Markers

These indicate UI component involvement:

| Marker | Usage Count | Description | Use When |
|--------|-------------|-------------|----------|
| `dialog` | ~39 | Dialog tests | Test involves QDialog |
| `widget` | ~25 | Widget tests | Test involves QWidget |
| `mock_dialogs` | ~20 | Mocked dialog exec() | Test patches dialog execution |
| `signals_slots` | ~56 | Qt signals/slots | Test signal-slot connections |
| `singleton` | ~few | Singleton pattern tests | Test singleton lifecycle |

**Examples:**
```python
@pytest.mark.dialog
@pytest.mark.mock_dialogs
def test_save_dialog_returns_path(monkeypatch):
    monkeypatch.setattr(QFileDialog, 'getSaveFileName', lambda *a: ('/path/file.png', ''))
    ...

@pytest.mark.signals_slots
def test_extraction_signals(qtbot):
    manager = ExtractionManager()
    with qtbot.waitSignal(manager.extraction_complete):
        manager.start_extraction()
```

### Execution Control Markers

These control test execution behavior:

| Marker | Usage Count | Description | Use When |
|--------|-------------|-------------|----------|
| `serial` | ~54 | No parallel execution | Test modifies global state |
| `parallel_safe` | ~42 | Can run in parallel | Test is fully isolated |
| `worker_threads` | ~20 | Uses worker threads | Test creates QThreads |
| `thread_safety` | ~24 | Thread safety tests | Testing concurrent access |
| `process_pool` | ~few | Uses process pools | Test creates subprocesses |
| `segfault_prone` | ~few | May segfault | Handle carefully in CI |

**Examples:**
```python
@pytest.mark.serial  # Run alone, not in parallel
def test_singleton_initialization():
    # Singleton state affects other tests
    ...

@pytest.mark.parallel_safe
def test_isolated_calculation():
    # Pure function, no shared state
    ...
```

## Marker Combinations

### Fast Local Development
```python
pytestmark = [
    pytest.mark.unit,
    pytest.mark.headless,
    pytest.mark.no_qt,
]
```

### CI-Safe Integration Test
```python
pytestmark = [
    pytest.mark.integration,
    pytest.mark.ci_safe,
    pytest.mark.headless,
    pytest.mark.parallel_safe,
]
```

### Full GUI Test
```python
pytestmark = [
    pytest.mark.gui,
    pytest.mark.qt_real,
    pytest.mark.qt_app,
    pytest.mark.requires_display,
    pytest.mark.slow,
]
```

## Common Commands

```bash
# Fast tests only
QT_QPA_PLATFORM=offscreen pytest -m "headless and not slow"

# GUI tests with offscreen backend
QT_QPA_PLATFORM=offscreen pytest -m gui

# CI pipeline
QT_QPA_PLATFORM=offscreen pytest -m ci_safe --tb=short

# Parallel execution
QT_QPA_PLATFORM=offscreen pytest -m parallel_safe -n auto

# Skip slow tests
QT_QPA_PLATFORM=offscreen pytest -m "not slow"

# Unit tests only
pytest -m unit

# Integration tests
pytest -m integration

# Tests without manager setup
pytest -m no_manager_setup

# Performance tests
pytest -m "benchmark or performance"
```

## Adding New Markers

1. Add the marker to `pyproject.toml`:
   ```toml
   markers = [
       "my_marker: Description of what this marker means",
   ]
   ```

2. Document it in this file with usage count and examples.

3. Apply consistently:
   ```python
   @pytest.mark.my_marker
   def test_something():
       ...
   ```

## Fixture Selection Guide

### Manager Fixtures

The test suite provides several manager fixtures with different isolation levels.
**Use `isolated_managers` as the default choice.** Only use `session_managers` for proven-safe read-only tests.

| Fixture | Scope | Isolation | Use When |
|---------|-------|-----------|----------|
| `isolated_managers` | Function | Full (per-test) | **Default choice** - any test that needs managers |
| `session_managers` | Session | None (state persists) | Read-only tests + `@pytest.mark.shared_state_safe` |
| `reset_manager_state` | Function | Caches only | Clean counters, keep managers |

**Deprecated fixtures (do not use in new code):**

| Fixture | Status | Replacement |
|---------|--------|-------------|
| `class_managers` | **Removed** - fails immediately | Use `isolated_managers` |
| `setup_managers` | Deprecated | Use `isolated_managers` |
| `fast_managers` | Deprecated | Use `session_managers` + marker |

**Examples:**
```python
# Default: Full isolation for each test (recommended)
def test_modifies_state(isolated_managers):
    # Fresh managers, won't affect other tests
    manager = isolated_managers.extraction_manager
    ...

# Session-scoped ONLY with marker (enforced)
@pytest.mark.shared_state_safe
def test_read_only_operation(session_managers):
    # Uses shared session managers - must be proven stateless
    pass

# For parallel execution, combine with parallel_safe
@pytest.mark.parallel_safe
def test_isolated_extraction(isolated_managers, tmp_path):
    # Safe for pytest-xdist
    output_file = tmp_path / "output.png"
    ...
```

### Real Component Fixtures

Prefer real components over mocks. Mock only at true system boundaries.

| Fixture | Scope | Returns |
|---------|-------|---------|
| `real_factory` | Function | RealComponentFactory instance |
| `real_extraction_manager` | Function | Real ExtractionManager (from `isolated_managers`) |
| `real_injection_manager` | Function | Real InjectionManager |
| `real_session_manager` | Function | Real SessionManager (from `isolated_managers`) |
| `rom_cache` | Function | Real ROMCache (isolated via `tmp_path`) |

**Note:** All real component fixtures are function-scoped for full test isolation.
This enables parallel execution with `@pytest.mark.parallel_safe`.

### HAL Fixtures

| Fixture | Default | With `@pytest.mark.real_hal` |
|---------|---------|------------------------------|
| `hal_pool` | MockHALProcessPool (fast) | Real HALProcessPool |
| `hal_compressor` | MockHALCompressor (fast) | Real HALCompressor |

### Fixture-Marker Compatibility

| Fixture | Compatible Markers | Notes |
|---------|-------------------|-------|
| `isolated_managers` | `parallel_safe`, `serial` | **Default choice** - works with all markers |
| `session_managers` | `shared_state_safe` (required) | Cannot combine with `parallel_safe` |
| `hal_pool` | Any | Use `real_hal` marker for real HAL |
| `qtbot` | `gui`, `qt_real` | Cannot combine with `no_qt` |

**Important:** Tests marked `@pytest.mark.parallel_safe` **must** use `isolated_managers` (not `session_managers`).
The `check_parallel_isolation` fixture enforces this at runtime.

### Migrating to Parallel-Safe Tests

To enable parallel execution with pytest-xdist, tests must meet these criteria:

1. Use `isolated_managers` fixture (NOT `session_managers`)
2. Use `tmp_path` for all file operations (NOT hardcoded paths)
3. Do not modify module-level globals
4. Do not depend on test execution order

**Migration example:**

```python
# BEFORE: Not parallel-safe
class TestExtraction:
    def test_extract(self, session_managers):
        output = "/tmp/test_output.png"  # Hardcoded path - race condition!
        ...

# AFTER: Parallel-safe
@pytest.mark.parallel_safe
class TestExtraction:
    def test_extract(self, isolated_managers, tmp_path):
        output = tmp_path / "test_output.png"  # Isolated path
        ...
```

**Migrating from local fixtures:**

```python
# OLD - Don't do this
@pytest.fixture(autouse=True)
def setup_managers():
    initialize_managers("TestApp")
    yield
    cleanup_managers()

# NEW - Use shared fixture
def test_something(isolated_managers):
    manager = isolated_managers.extraction_manager
    ...
```

## Troubleshooting

### Test skipped unexpectedly
Check for conflicting markers:
```bash
pytest --collect-only -m "gui and headless"  # Shows 0 tests - conflicting!
```

### Test runs too slow
Add `@pytest.mark.slow` and filter:
```bash
pytest -m "not slow"
```

### Test flakes in CI
1. Add `@pytest.mark.ci_safe` only after verifying stability
2. Consider `@pytest.mark.serial` if state-dependent
3. Check for `time.sleep()` calls - use `qtbot.wait()` instead
