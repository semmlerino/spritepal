# Test Fixture Cheatsheet

## Quick Decision Table

| What you need | Fixture | Notes |
|--------------|---------|-------|
| Managers (extraction, injection, state) | `app_context` | Default choice, always safe |
| Managers (shared, performance) | `session_app_context` | Requires `@pytest.mark.shared_state_safe` |
| Qt widgets | `qtbot` | Add `@pytest.mark.gui` |
| Wait for signals | `qtbot.waitSignal()` | Use `with` context manager |
| HAL compression (fast) | `hal_pool` | Mock by default |
| HAL compression (real) | `@pytest.mark.real_hal` | Skips if binary unavailable |
| Temporary files | `tmp_path` | Built-in pytest fixture |
| Real component factory | `real_factory` | For integration tests |

## Common Patterns

### Basic Manager Test
```python
def test_extraction_validates(app_context):
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
    assert widget.clicked
```

### Signal Wait (CORRECT)
```python
from tests.fixtures.timeouts import worker_timeout

def test_worker_completes(qtbot, app_context):
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
    image = ThreadSafeTestImage(100, 100)  # Constructor, not .create()
    worker = ImageWorker(image)
```

## Manager Access Pattern

**Use the `app_context` fixture to access managers:**
```python
def test_something(app_context):
    manager = app_context.core_operations_manager
    state = app_context.application_state_manager
    rom_cache = app_context.rom_cache
```

Benefits: Automatic cleanup, test isolation, better IDE support.

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
| `session_app_context` without marker | Add `@pytest.mark.shared_state_safe` |
| Hardcoded `/tmp/test.bin` | `tmp_path / "test.bin"` |

## When to Use session_app_context

Almost never. Use `app_context` unless:
1. Test is read-only AND verified stateless
2. You add `@pytest.mark.shared_state_safe`
3. You understand parallel test implications

## Where to Add New Tests

| Testing... | Location |
|------------|----------|
| Core logic (pure, no Qt) | `tests/unit/core/` |
| UI controllers/services | `tests/unit/ui/` |
| Manager + multi-component | `tests/integration/` |
| Widget / Qt interaction | `tests/ui/` |

---

*Last updated: February 6, 2026*
