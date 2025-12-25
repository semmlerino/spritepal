# SpritePal Test Suite

This directory contains the pytest test suite for SpritePal, featuring **Real Component Testing** infrastructure.

> **For testing patterns, Qt threading, signal testing, and best practices, see [docs/testing_guide.md](../docs/testing_guide.md).**

---

## Quick Start

### Basic Test with Managers
```python
from core.di_container import inject
from core.managers.core_operations_manager import CoreOperationsManager

def test_extraction(isolated_managers):
    manager = inject(CoreOperationsManager)
    result = manager.validate_extraction_params({"path": "/test"})
    assert isinstance(result, bool)
```

### Qt Widget Test
```python
@pytest.mark.gui
def test_button_click(qtbot, isolated_managers):
    widget = MyWidget()
    qtbot.addWidget(widget)
    qtbot.mouseClick(widget.button, Qt.LeftButton)
```

### Signal Wait (Always Use Context Manager)
```python
from tests.fixtures.timeouts import worker_timeout

def test_worker(qtbot, isolated_managers):
    worker = MyWorker()
    with qtbot.waitSignal(worker.finished, timeout=worker_timeout()):
        worker.start()
```

---

## Directory Structure

```
tests/
├── infrastructure/          # Test framework components
│   ├── real_component_factory.py    # Factory for real components
│   ├── manager_test_context.py      # Integration test contexts
│   ├── data_repository.py           # Consistent test data
│   ├── thread_safe_test_image.py    # Thread-safe QPixmap alternative
│   └── qt_mocks.py                  # Qt test doubles
├── fixtures/               # Pytest fixtures
│   ├── core_fixtures.py    # Manager fixtures (isolated_managers, etc.)
│   ├── qt_fixtures.py      # Qt-specific fixtures
│   └── timeouts.py         # Semantic timeout functions
├── integration/            # Integration tests
├── controllers/            # Controller tests
└── test_*.py              # Unit tests
```

---

## Running Tests

```bash
# All tests (parallel by default)
uv run pytest

# Quick triage - pass/fail summary only
uv run pytest --tb=no -q

# Re-run only failures with details
uv run pytest --lf -vv --tb=short

# Single test with full output (serial)
uv run pytest tests/path/test_file.py::test_name -vv --tb=long -s -n 0

# Coverage report
uv run pytest --cov=core --cov=ui --cov-report=html
```

---

## Fixture Quick Reference

| Fixture | When to Use |
|---------|-------------|
| `isolated_managers` | **Default** - clean state each test |
| `session_managers` | Only with `@pytest.mark.shared_state_safe` |
| `hal_pool` | HAL operations (mock by default) |
| `qtbot` | Qt widget testing |
| `tmp_path` | Temporary files |

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
| `@pytest.mark.shared_state_safe` | Required with `session_managers` |
| `@pytest.mark.requires_display` | Skipped in offscreen mode |

---

## Anti-Patterns

| Wrong | Right |
|-------|-------|
| `time.sleep(1)` | `qtbot.wait(1000)` |
| `timeout=5000` | `timeout=worker_timeout()` |
| `QPixmap` in worker thread | `ThreadSafeTestImage` |
| `session_managers` alone | + `@pytest.mark.shared_state_safe` |
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

@pytest.fixture
def real_factory(isolated_managers):
    with RealComponentFactory() as factory:
        yield factory

def test_workflow(real_factory):
    manager = real_factory.create_extraction_manager(with_test_data=True)
    params = real_factory._data_repo.get_vram_extraction_data("small")
    result = manager.validate_extraction_params(params)
```

---

## More Information

- **Testing patterns & best practices**: [docs/testing_guide.md](../docs/testing_guide.md)
- **Fixture cheatsheet**: [tests/FIXTURE_CHEATSHEET.md](FIXTURE_CHEATSHEET.md)
- **Infrastructure docs**: `tests/infrastructure/` subdirectories

---

*Last updated: December 25, 2025*
