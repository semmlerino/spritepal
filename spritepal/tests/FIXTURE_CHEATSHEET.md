# Test Fixture Cheatsheet

## Quick Decision Table

| What you need | Fixture | Notes |
|--------------|---------|-------|
| Managers (extraction, injection, state) | `isolated_managers` | Default choice, always safe |
| Qt widgets | `qtbot` | Add `@pytest.mark.gui` |
| Wait for signals | `qtbot.waitSignal()` | Use `with` context manager |
| HAL compression (fast) | `hal_pool` | Mock by default |
| HAL compression (real) | `@pytest.mark.real_hal` | Skips if binary unavailable |
| Temporary files | `tmp_path` | Built-in pytest fixture |
| Real component factory | `real_factory` | For integration tests |

## Common Patterns

### Basic Manager Test
```python
from core.app_context import get_app_context

def test_extraction_validates(isolated_managers):
    context = get_app_context()
    manager = context.core_operations_manager
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
    assert widget.clicked
```

### Signal Wait (CORRECT)
```python
from tests.fixtures.timeouts import worker_timeout

def test_worker_completes(qtbot, isolated_managers):
    worker = MyWorker()
    with qtbot.waitSignal(worker.finished, timeout=worker_timeout()):
        worker.start()  # Signal may emit fast - context manager catches it
```

### Signal Wait (WRONG - causes flaky tests)
```python
# DON'T DO THIS - signal may emit before waitSignal starts
worker.start()
qtbot.waitSignal(worker.finished)  # Race condition!
```

### Thread-Safe Image (for workers)
```python
from tests.infrastructure.thread_safe_test_image import ThreadSafeTestImage

def test_worker_with_image():
    # QPixmap in worker = CRASH. Use this instead:
    image = ThreadSafeTestImage.create(100, 100)
    worker = ImageWorker(image)
```

## Manager Access Pattern

**Use `get_app_context()` to access managers:**
```python
from core.app_context import get_app_context

context = get_app_context()
manager = context.core_operations_manager
state = context.application_state_manager
```

Benefits: Explicit access, better IDE support, no class imports needed.

**Note:** The `inject()` pattern has been removed. Use `get_app_context()` exclusively.

## Timeout Functions

Import from `tests/fixtures/timeouts.py`:

| Function | Base (ms) | Use for |
|----------|-----------|---------|
| `ui_timeout()` | 1000 | Widget visibility, layouts |
| `signal_timeout()` | 2000 | Generic signal waits |
| `dialog_timeout()` | 3000 | Dialog accept/reject |
| `worker_timeout()` | 5000 | Background workers, QThread |

Multipliers: `LONG=2.0`, `SHORT=0.5`
```python
timeout=worker_timeout(LONG)  # 10000ms for slow operations
```

## Anti-Patterns

| Wrong | Right |
|-------|-------|
| `time.sleep(1)` | `qtbot.wait(1000)` |
| `timeout=5000` | `timeout=worker_timeout()` |
| `QPixmap` in worker thread | `ThreadSafeTestImage` |
| `session_managers` without marker | Add `@pytest.mark.shared_state_safe` |
| Hardcoded `/tmp/test.bin` | `tmp_path / "test.bin"` |

## When to Use session_managers

Almost never. Use `isolated_managers` unless:
1. Test is read-only AND verified stateless
2. You add `@pytest.mark.shared_state_safe`
3. You understand parallel test implications

## Where to Add New Tests

| Testing... | Location |
|------------|----------|
| Core logic (extractor, palette, etc.) | `tests/test_<module>.py` |
| Manager behavior | `tests/test_<manager>_manager.py` |
| UI components | `tests/ui/test_<component>.py` |
| End-to-end workflows | `tests/integration/` |
| Controller logic | `tests/controllers/` |

---

*Last updated: December 25, 2025*
