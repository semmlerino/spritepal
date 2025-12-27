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

### Test Data Patterns

| Need | Use |
|------|-----|
| Single ROM file | `test_rom_file` fixture |
| Single VRAM file | `test_vram_file` fixture |
| Complete test setup (all files) | `TestDataFactory.create_test_files(tmp_path)` |
| Injection test files | `TestDataFactory.create_injection_test_files(tmp_path)` |

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
from tests.infrastructure.data_repository import get_test_data_repository

def test_workflow(app_context):
    # Access managers directly from app_context
    manager = app_context.core_operations_manager

    # Use DataRepository for test data
    data_repo = get_test_data_repository()
    params = data_repo.get_vram_extraction_data("small")
    result = manager.validate_extraction_params(params)

# For Qt component creation, use RealComponentFactory
def test_with_workers(app_context):
    with RealComponentFactory() as factory:
        worker = factory.create_extraction_worker(params)
        # ... test code ...
```

---

## More Information

- **Testing patterns & best practices**: [docs/testing_guide.md](../docs/testing_guide.md)
- **Fixture cheatsheet**: [tests/FIXTURE_CHEATSHEET.md](FIXTURE_CHEATSHEET.md)
- **Infrastructure docs**: `tests/infrastructure/` subdirectories

---

*Last updated: December 27, 2025*
