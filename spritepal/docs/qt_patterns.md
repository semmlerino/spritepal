# Qt Patterns Reference

This document covers Qt signals, worker patterns, and testing best practices for SpritePal.

---

## 1. Signal Reference

### Core Manager Signals

#### CoreOperationsManager (`core/managers/core_operations_manager.py`)

| Signal | Payload | When emitted |
|--------|---------|--------------|
| `extraction_progress` | `str` | Progress message during extraction |
| `extraction_warning` | `str` | Partial success warning |
| `preview_generated` | `(object, int)` | QPixmap and offset after preview |
| `palettes_extracted` | `dict` | Palette data extracted |
| `files_created` | `list[str]` | Paths of extracted files |
| `injection_progress` | `str` | Progress message during injection |
| `injection_finished` | `(bool, str)` | Success flag and message |
| `compression_info` | `dict` | Compression statistics |

#### ApplicationStateManager (`core/managers/application_state_manager.py`)

| Signal | Payload | When emitted |
|--------|---------|--------------|
| `state_changed` | `(str, dict)` | Category and data when state changes |
| `workflow_state_changed` | `(object, object)` | Old and new workflow states |
| `session_changed` | `()` | Session data modified |
| `current_offset_changed` | `int` | ROM offset selection changed |
| `preview_ready` | `(int, QImage)` | Offset and preview image |

#### BaseManager (`core/managers/base_manager.py`)

All managers inherit:

| Signal | Payload | When emitted |
|--------|---------|--------------|
| `error_occurred` | `str` | Any error during operation |
| `warning_occurred` | `str` | Non-fatal warning |
| `operation_started` | `str` | Operation name when starting |
| `operation_finished` | `str` | Operation name when complete |
| `progress_updated` | `(str, int, int)` | Operation, current, total |

### Worker Signals

#### BaseWorker (`core/workers/base.py`)

| Signal | Payload | When emitted |
|--------|---------|--------------|
| `progress` | `(int, str)` | Percent complete and message |
| `error` | `(str,)` | Error message for display |
| `warning` | `(str,)` | Warning message |
| `operation_finished` | `(bool, str)` | Success flag and message |

### Signal Naming Conventions

| Pattern | Meaning |
|---------|---------|
| `*_ready` | Data is available for use |
| `*_changed` | State has been modified |
| `*_requested` | User action needs handling |
| `*_completed` / `*_finished` | Operation done |
| `*_error` / `*_failed` | Operation failed |
| `*_progress` | Intermediate status update |

---

## 2. Worker Patterns

### Standard Worker Pattern

All workers must extend `BaseWorker` and use `@handle_worker_errors`:

```python
from core.workers.base import BaseWorker, handle_worker_errors
from PySide6.QtCore import Signal

class MyWorker(BaseWorker):
    result_ready = Signal(object)

    def __init__(self, param: str) -> None:
        super().__init__()
        self._param = param
        self._operation_name = "MyWorker"

    @handle_worker_errors("my operation", handle_interruption=True)
    def run(self) -> None:
        self.check_cancellation()
        self.emit_progress(25, "Processing...")
        result = self._do_work()
        self.check_cancellation()
        self.result_ready.emit(result)
        self.operation_finished.emit(True, "Completed")
```

### Worker Lifecycle with WorkerManager

```python
from core.services.worker_lifecycle import WorkerManager

# Create and start
worker = MyWorker(param)
thread = QThread()
worker.moveToThread(thread)
WorkerManager.start_worker(worker, thread)

# Cleanup
WorkerManager.cleanup_worker(worker, timeout=5000)
```

### Anti-Patterns

```python
# BAD - Inheriting QThread directly
class OldWorker(QThread):
    def run(self): ...

# GOOD - Use composition
class NewWorker(BaseWorker):
    def run(self): ...

# BAD - QPixmap in worker (causes crash)
def run(self):
    pixmap = QPixmap(100, 100)  # FATAL ERROR

# GOOD - Use QImage (thread-safe)
def run(self):
    image = QImage(100, 100, QImage.Format.Format_ARGB32)

# BAD - No cancellation checks
def run(self):
    for item in huge_list:
        process(item)

# GOOD - Cancellable
def run(self):
    for item in huge_list:
        self.check_cancellation()
        process(item)
```

---

## 3. Testing Best Practices

### Core Principles

1. **Prefer real components over mocks** - Real Qt components provide actual signal behavior
2. **Signals are first-class citizens** - Test via signals, not internal state
3. **Use `qtbot.addWidget()`** - Ensures proper cleanup

### Essential Patterns

#### Real Components with Mocked Dependencies

```python
class MockMainWindow(QObject):
    extract_requested = Signal()  # Real signal

    def __init__(self):
        super().__init__()
        self.status_bar = Mock()  # Mock behavior

def test_controller(qtbot):
    window = MockMainWindow()
    controller = ExtractionController(window)
    spy = QSignalSpy(window.extract_requested)
    window.extract_requested.emit()
    assert len(spy) == 1
```

#### Signal Testing

```python
def test_async_operation(qtbot):
    processor = DataProcessor()

    with qtbot.waitSignal(processor.finished, timeout=5000) as blocker:
        processor.start()

    assert blocker.signal_triggered
    assert blocker.args[0] == "success"
```

#### Worker Testing

```python
def test_worker(qtbot):
    worker = DataWorker(params)
    finished_spy = QSignalSpy(worker.finished)

    worker.start()
    qtbot.waitUntil(lambda: not worker.isRunning(), timeout=5000)

    assert len(finished_spy) == 1
```

### Common Pitfalls

#### Qt Container Truthiness

```python
# BAD - Fails for empty containers
if self.layout:  # False for empty QVBoxLayout!
    self.layout.addWidget(widget)

# GOOD - Explicit None check
if self.layout is not None:
    self.layout.addWidget(widget)
```

#### Widget Initialization Order

```python
# BAD - AttributeError risk
class MyWidget(QWidget):
    def __init__(self):
        super().__init__()  # Might trigger signals
        self.data = []  # Too late!

# GOOD - Safe initialization
class MyWidget(QWidget):
    def __init__(self):
        self.data = []  # Initialize first
        super().__init__()
```

#### Cross-Thread GUI Creation

```python
# BAD - GUI in worker thread
class Worker(QThread):
    def run(self):
        dialog = QMessageBox()  # Crash!

# GOOD - Signal to main thread
class Worker(QThread):
    show_message = Signal(str)
    def run(self):
        self.show_message.emit("Message")
```

### Quick Reference

| Method | Purpose |
|--------|---------|
| `qtbot.addWidget(w)` | Register for cleanup |
| `qtbot.waitSignal(sig, timeout)` | Wait for signal |
| `qtbot.assertNotEmitted(sig)` | Assert no emission |
| `QSignalSpy(sig)` | Record emissions |
| `qtbot.mouseClick(w, btn)` | Simulate click |
| `qtbot.wait(ms)` | Process events |
| `qtbot.waitUntil(fn, timeout)` | Wait for condition |

### Anti-Patterns Checklist

- [ ] Don't use QSignalSpy with mocks (only real signals)
- [ ] Don't check Qt container truthiness (`if layout:`)
- [ ] Don't create GUI in worker threads
- [ ] Don't forget `qtbot.addWidget()` cleanup
- [ ] Don't mock everything - use real components
- [ ] Don't access parent chain directly (`parent().parent()`)

---

*Last updated: December 23, 2025*
