# Worker Patterns

SpritePal uses a standardized worker pattern based on `BaseWorker` for all background operations.

## Standard Pattern (Required for new workers)

All workers must extend `BaseWorker` and use the `@handle_worker_errors` decorator:

```python
from core.workers.base import BaseWorker, handle_worker_errors
from PySide6.QtCore import Signal

class MyWorker(BaseWorker):
    """Background worker for X operation."""

    # Custom signals for this worker's results
    result_ready = Signal(object)

    def __init__(self, param: str) -> None:
        super().__init__()
        self._param = param
        self._operation_name = "MyWorker"  # Used in error messages

    @handle_worker_errors("my operation", handle_interruption=True)
    def run(self) -> None:
        """Execute in background thread."""
        # Check for cancellation at key points
        self.check_cancellation()

        # Emit progress updates
        self.emit_progress(25, "Processing step 1...")

        # Do actual work
        result = self._do_work()

        self.check_cancellation()
        self.emit_progress(75, "Finalizing...")

        # Emit results and completion
        self.result_ready.emit(result)
        self.operation_finished.emit(True, "Completed successfully")

    def _do_work(self) -> object:
        """Actual work implementation."""
        # Your business logic here
        return {"status": "done"}
```

## Inherited Signals

All workers inherit these signals from `BaseWorker`:

| Signal | Parameters | Description |
|--------|------------|-------------|
| `progress` | `(int, str)` | Percent complete (0-100) and message |
| `error` | `(str,)` | Error message for display |
| `warning` | `(str,)` | Warning message for display |
| `operation_finished` | `(bool, str)` | Success flag and final message |

## Specialized Base Classes

For common patterns, extend from specialized base classes instead of `BaseWorker` directly:

### ScanWorkerBase

For ROM/memory scanning operations:

```python
from core.workers.specialized import ScanWorkerBase

class MyScanWorker(ScanWorkerBase):
    """Scanner for finding items in data."""

    def run(self) -> None:
        for item in self._scan_items():
            self.check_cancellation()
            self.item_found.emit(item)  # Inherited signal
        self.scan_finished.emit(True)
```

Adds signals:
- `item_found(dict)` - Emitted for each found item
- `scan_progress(int, int)` - Current position and total
- `scan_finished(bool)` - Scan completion status

## Worker Lifecycle with WorkerManager

Always use `WorkerManager` for proper worker lifecycle management:

```python
from PySide6.QtCore import QThread
from core.services.worker_lifecycle import WorkerManager

# Create worker and thread
worker = MyWorker(param)
thread = QThread()
worker.moveToThread(thread)

# Start worker
WorkerManager.start_worker(worker, thread)

# When done (or on cleanup):
WorkerManager.cleanup_worker(worker, timeout=5000)
```

### Cleanup in UI Components

For UI components managing workers:

```python
class MyPanel(QWidget):
    def __init__(self):
        super().__init__()
        self._worker: MyWorker | None = None
        self._thread: QThread | None = None

    def start_operation(self):
        self._worker = MyWorker(param)
        self._thread = QThread()
        self._worker.moveToThread(self._thread)

        # Connect signals BEFORE starting
        self._worker.result_ready.connect(self._on_result)
        self._worker.operation_finished.connect(self._on_finished)

        WorkerManager.start_worker(self._worker, self._thread)

    def _on_finished(self, success: bool, message: str):
        """Handle completion - cleanup happens automatically."""
        self._worker = None
        self._thread = None

    def closeEvent(self, event):
        """Ensure cleanup on window close."""
        if self._worker:
            WorkerManager.cleanup_worker(self._worker)
        super().closeEvent(event)
```

## Error Handling

The `@handle_worker_errors` decorator handles common exception patterns:

```python
@handle_worker_errors(
    "my operation",           # Context for error messages
    handle_interruption=True,  # Handle InterruptedError (cancellation)
    include_runtime_error=False  # Whether to catch RuntimeError
)
def run(self) -> None:
    ...
```

### Exception Handling Order

1. `InterruptedError` - Cancellation (re-raised unless `handle_interruption=True`)
2. `OSError`, `PermissionError` - File I/O errors
3. `ValueError`, `TypeError` - Data format errors
4. `RuntimeError` - Only if `include_runtime_error=True`
5. `Exception` - General fallback

All handled exceptions:
- Log the error with full context
- Emit `error` signal
- Emit `operation_finished(False, error_message)`

## Anti-Patterns to Avoid

### Don't Inherit from QThread Directly

```python
# BAD - Old pattern, don't use
class OldWorker(QThread):
    def run(self):
        ...

# GOOD - Use composition
class NewWorker(BaseWorker):
    def run(self):
        ...

worker = NewWorker()
thread = QThread()
worker.moveToThread(thread)
```

### Don't Skip Cancellation Checks

```python
# BAD - Can't be cancelled
def run(self):
    for item in huge_list:
        process(item)  # No cancellation check!

# GOOD - Cancellable
def run(self):
    for item in huge_list:
        self.check_cancellation()  # Check at each iteration
        process(item)
```

### Don't Forget Thread Safety

```python
# BAD - QPixmap in worker thread causes crash
def run(self):
    pixmap = QPixmap(100, 100)  # FATAL ERROR

# GOOD - Use QImage instead (thread-safe)
def run(self):
    image = QImage(100, 100, QImage.Format.Format_ARGB32)
    # Or use ThreadSafeTestImage in tests
```

## Migration Guide

If you have workers using the old `QThread` inheritance pattern:

1. Change base class from `QThread` to `BaseWorker`
2. Add `@handle_worker_errors` decorator to `run()`
3. Set `self._operation_name` in `__init__`
4. Add `self.check_cancellation()` at iteration points
5. Update callers to use `moveToThread()` pattern
6. Use `WorkerManager` for lifecycle management

---

## Worker Audit (December 2025)

The following production workers still use the deprecated `QThread` inheritance pattern and should be migrated:

| File | Class | Priority | Notes |
|------|-------|----------|-------|
| `ui/rom_extraction/workers/search_worker.py` | `SpriteSearchWorker` | Low | Used by ROMExtractionPanel |
| `ui/dialogs/advanced_search_dialog.py` | `SearchWorker` | Low | Dialog-local worker |
| `ui/common/simple_preview_coordinator.py` | `SimplePreviewWorker` | Low | Preview generation |

**Note**: Test files using `QThread` directly are acceptable (test doubles don't need the full pattern).

---

*Last updated: December 21, 2025*
