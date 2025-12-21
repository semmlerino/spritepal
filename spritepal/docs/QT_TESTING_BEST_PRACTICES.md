# Qt Testing Best Practices

A comprehensive guide for testing PyQt6/PySide6 applications with pytest-qt, based on real-world experience refactoring a 2000+ test suite.

## Table of Contents

1. [Introduction](#introduction)
2. [Core Principles](#core-principles)
3. [Essential Patterns](#essential-patterns)
4. [Signal Testing](#signal-testing)
5. [Dependency Injection](#dependency-injection)
6. [Common Pitfalls](#common-pitfalls)
7. [Worker Thread Testing](#worker-thread-testing)
8. [Dialog Testing](#dialog-testing)
9. [Performance Testing](#performance-testing)
10. [Quick Reference](#quick-reference)

## Introduction

Qt testing is fundamentally different from regular Python testing due to:
- **Event Loop**: Qt requires an event loop for signals, timers, and async operations
- **Object Lifecycle**: Qt objects have parent-child relationships affecting memory management
- **Threading Model**: Qt enforces thread affinity for GUI objects
- **Signal/Slot System**: Asynchronous communication requires special handling

## Core Principles

### 1. Prefer Real Components Over Mocks

**Why**: Real Qt components provide actual signal behavior, proper event handling, and realistic interactions.

```python
# ❌ BAD - Fully mocked component
def test_controller_bad(self):
    controller = Mock(spec=ExtractionController)
    controller.start_extraction.return_value = True
    # This doesn't test real behavior!

# ✅ GOOD - Real component with mocked dependencies
@pytest.fixture
def controller(self):
    # Real controller with mocked dependencies
    return ExtractionController(
        main_window=Mock(),  # Mock only external dependencies
        extraction_manager=Mock(spec=ExtractionManager),
        injection_manager=Mock(spec=InjectionManager),
    )

def test_controller_good(self, controller):
    # Tests real controller logic
    controller.start_extraction()
    # Assertions on real behavior
```

### 2. Understand Qt's Event Loop

The `qtbot` fixture manages the event loop automatically:

```python
def test_async_operation(qtbot):
    widget = MyWidget()
    qtbot.addWidget(widget)  # Ensures cleanup
    
    # Wait for async signal with timeout
    with qtbot.waitSignal(widget.finished, timeout=1000):
        widget.start_operation()
    
    # Event loop processes during wait
    assert widget.result is not None
```

### 3. Signals Are First-Class Citizens

Treat signals as the primary interface for testing Qt components:

```python
def test_signal_emission(qtbot):
    widget = RealWidget()
    qtbot.addWidget(widget)
    
    # Use QSignalSpy for real signals
    spy = QSignalSpy(widget.data_changed)
    
    widget.update_data("new value")
    
    assert len(spy) == 1
    assert spy[0][0] == "new value"
```

## Essential Patterns

### Pattern 1: Real Components with Mocked Dependencies

This pattern provides the best balance between test isolation and realistic behavior:

```python
class MockMainWindow(QObject):
    """Real Qt object with signals, mocked behavior"""
    
    # Real Qt signals
    extract_requested = Signal()
    file_opened = Signal(str)
    
    def __init__(self):
        super().__init__()
        # Mock attributes for behavior
        self.status_bar = Mock()
        self.toolbar = Mock()
        
    def get_extraction_params(self):
        # Return test data
        return {"vram_path": "/test/path"}

def test_controller_with_real_signals(qtbot):
    window = MockMainWindow()  # Real signals, mock behavior
    controller = ExtractionController(window)
    
    # Test real signal connections
    spy = QSignalSpy(window.extract_requested)
    window.extract_requested.emit()
    
    assert len(spy) == 1
```

### Pattern 2: Fixture Hierarchy for Component Creation

Organize fixtures to build components systematically:

```python
@pytest.fixture
def temp_files(tmp_path):
    """Create test files"""
    vram = tmp_path / "test.vram"
    vram.write_bytes(b"\x00" * 0x10000)
    return {"vram": str(vram)}

@pytest.fixture
def managers():
    """Create real managers"""
    return {
        "extraction": ExtractionManager(),
        "injection": InjectionManager(),
    }

@pytest.fixture
def main_window(qtbot):
    """Create test main window"""
    window = MockMainWindow()
    qtbot.addWidget(window)
    return window

@pytest.fixture
def controller(main_window, managers):
    """Compose controller from fixtures"""
    return ExtractionController(
        main_window=main_window,
        **managers
    )
```

### Pattern 3: Context Management for Dependency Injection

Use context managers for thread-local dependency injection:

```python
from tests.infrastructure.manager_test_context import manager_context

def test_worker_with_context():
    # Worker needs manager in context
    with manager_context("extraction") as ctx:
        extraction_manager = ctx.get_extraction_manager()
        worker = VRAMExtractionWorker(params)
        # Worker can now find manager via context
        assert extraction_manager is not None
```

## Signal Testing

### QSignalSpy vs Mock Assertions

**Critical**: QSignalSpy only works with real Qt signals!

```python
# ❌ WRONG - QSignalSpy with Mock
def test_signal_mock_wrong():
    mock_widget = Mock()
    spy = QSignalSpy(mock_widget.some_signal)  # TypeError!

# ✅ CORRECT - QSignalSpy with real signal
def test_signal_real(qtbot):
    real_widget = QWidget()
    qtbot.addWidget(real_widget)
    # Only works with real Qt signals
    spy = QSignalSpy(real_widget.destroyed)

# ✅ CORRECT - Mock assertions for mock objects
def test_mock_behavior():
    mock_widget = Mock()
    mock_widget.update_data("test")
    mock_widget.update_data.assert_called_with("test")
```

### Waiting for Signals

Use `qtbot.waitSignal` for async operations:

```python
def test_async_operation(qtbot):
    processor = DataProcessor()
    
    # Wait for signal with timeout
    with qtbot.waitSignal(processor.finished, timeout=5000) as blocker:
        processor.start()
        # Blocks here until signal emitted or timeout
    
    # Check if signal was emitted
    assert blocker.signal_triggered
    
    # Access signal arguments
    assert blocker.args[0] == "success"
```

### Testing Signal Chains

```python
def test_signal_chain(qtbot):
    source = SignalSource()
    processor = SignalProcessor()
    
    # Connect chain
    source.data_ready.connect(processor.process_data)
    
    # Watch final signal
    with qtbot.waitSignal(processor.processing_complete):
        source.emit_data("test")
    
    assert processor.result == "processed: test"
```

### Assert Signal Not Emitted

```python
def test_no_error_signal(qtbot):
    widget = MyWidget()
    
    with qtbot.assertNotEmitted(widget.error):
        widget.safe_operation()
    # Test passes if error signal not emitted
```

## Dependency Injection

### Design for Testability

Structure your Qt classes to accept dependencies:

```python
class MainWindow(QMainWindow):
    def __init__(
        self,
        extraction_manager=None,
        injection_manager=None,
        parent=None
    ):
        super().__init__(parent)
        # Use provided or create default
        self.extraction_manager = extraction_manager or ExtractionManager()
        self.injection_manager = injection_manager or InjectionManager()

# Easy to test with mocks
def test_main_window():
    window = MainWindow(
        extraction_manager=Mock(spec=ExtractionManager),
        injection_manager=Mock(spec=InjectionManager)
    )
```

### Factory Pattern for Complex Components

```python
class ComponentFactory:
    """Factory for creating test components"""
    
    def create_main_window(self, with_mocks=False):
        if with_mocks:
            return MockMainWindow()
        return MainWindow()
    
    def create_controller(self, window, managers=None):
        if managers is None:
            managers = self.create_managers()
        return Controller(window, **managers)
    
    def create_managers(self, mock=False):
        if mock:
            return {
                "extraction": Mock(spec=ExtractionManager),
                "injection": Mock(spec=InjectionManager),
            }
        return {
            "extraction": ExtractionManager(),
            "injection": InjectionManager(),
        }
```

## Common Pitfalls

### Pitfall 1: Qt Container Truthiness

Many Qt containers evaluate to `False` when empty:

```python
# ❌ DANGEROUS - Fails for empty containers
def process_layout(self):
    if self.layout:  # False for empty QVBoxLayout!
        self.layout.addWidget(widget)

# ✅ SAFE - Explicit None check
def process_layout(self):
    if self.layout is not None:
        self.layout.addWidget(widget)

# Affected classes:
# QVBoxLayout, QHBoxLayout, QGridLayout, QStackedWidget,
# QListWidget, QTreeWidget, QTabWidget, QSplitter
```

### Pitfall 2: Widget Initialization Order

Always initialize attributes before calling `super().__init__()`:

```python
# ❌ WRONG - AttributeError risk
class MyWidget(QWidget):
    def __init__(self):
        super().__init__()  # Might trigger signals
        self.data = []  # Too late if signal accesses self.data!

# ✅ CORRECT - Safe initialization
class MyWidget(QWidget):
    def __init__(self):
        self.data = []  # Initialize first
        super().__init__()  # Now safe
```

### Pitfall 3: Cross-Thread GUI Creation

Never create GUI objects in worker threads:

```python
# ❌ WRONG - Creates GUI in worker thread
class Worker(QThread):
    def run(self):
        dialog = QMessageBox()  # Crash or undefined behavior!

# ✅ CORRECT - Emit signal to main thread
class Worker(QThread):
    show_message = Signal(str)
    
    def run(self):
        self.show_message.emit("Message")  # Main thread shows dialog
```

### Pitfall 4: Direct Parent Access

Avoid accessing parent widgets directly:

```python
# ❌ FRAGILE - Breaks if hierarchy changes
def get_main_window(self):
    return self.parent().parent().parent()

# ✅ ROBUST - Explicit reference
def __init__(self, main_window, parent=None):
    super().__init__(parent)
    self.main_window = main_window  # Direct reference
```

## Worker Thread Testing

### Basic Worker Test Pattern

```python
class TestWorker:
    @pytest.fixture
    def worker(self):
        worker = DataProcessingWorker(test_params)
        yield worker
        # Cleanup
        if worker.isRunning():
            worker.quit()
            worker.wait(1000)
    
    def test_successful_processing(self, qtbot, worker):
        # Monitor signals
        finished_spy = QSignalSpy(worker.finished)
        error_spy = QSignalSpy(worker.error)
        
        # Start worker
        worker.start()
        
        # Wait for completion
        qtbot.waitUntil(lambda: not worker.isRunning(), timeout=5000)
        
        # Verify results
        assert len(finished_spy) == 1
        assert len(error_spy) == 0
```

### Testing Worker Interruption

```python
def test_worker_interruption(qtbot, worker):
    worker.start()
    
    # Request interruption
    worker.requestInterruption()
    
    # Wait for worker to stop
    qtbot.waitUntil(lambda: not worker.isRunning(), timeout=1000)
    
    # Verify clean shutdown
    assert worker.isInterruptionRequested()
    assert not worker.isRunning()
```

### Worker with Manager Context

```python
from tests.infrastructure.manager_test_context import manager_context

def test_worker_with_manager():
    with manager_context("extraction") as ctx:
        extraction_mgr = ctx.get_extraction_manager()
        worker = ExtractionWorker(params)
        # Worker finds manager through context
        worker.start()
        worker.wait(1000)
        assert worker.result is not None
```

## Dialog Testing

### Modal Dialog Testing

```python
def test_modal_dialog(qtbot, monkeypatch):
    # Mock exec() to prevent blocking
    monkeypatch.setattr(QDialog, "exec", lambda self: QDialog.DialogCode.Accepted)
    
    dialog = MyDialog()
    qtbot.addWidget(dialog)
    
    # Set test values
    dialog.input_field.setText("test value")
    
    # Simulate accept
    result = dialog.exec()
    
    assert result == QDialog.DialogCode.Accepted
    assert dialog.get_value() == "test value"
```

### Testing Dialog Static Methods

```python
def test_message_box(monkeypatch):
    # Mock static method
    monkeypatch.setattr(
        QMessageBox, 
        "question",
        lambda *args: QMessageBox.StandardButton.Yes
    )
    
    result = QMessageBox.question(None, "Title", "Continue?")
    assert result == QMessageBox.StandardButton.Yes
```

## Performance Testing

### Benchmark Qt Operations

```python
@pytest.mark.benchmark
def test_widget_creation_performance(benchmark, qtbot):
    def create_complex_widget():
        widget = ComplexWidget()
        qtbot.addWidget(widget)
        return widget
    
    widget = benchmark(create_complex_widget)
    assert widget is not None
```

### Memory Leak Detection

```python
def test_no_memory_leak(qtbot):
    import gc
    import weakref
    
    # Create widget
    widget = MyWidget()
    qtbot.addWidget(widget)
    
    # Create weak reference
    ref = weakref.ref(widget)
    
    # Delete widget
    widget.deleteLater()
    qtbot.wait(100)  # Process events
    del widget
    gc.collect()
    
    # Verify deleted
    assert ref() is None
```

## Quick Reference

### Essential pytest-qt Fixtures

| Fixture | Purpose | Example |
|---------|---------|---------|
| `qtbot` | Main testing interface | `qtbot.addWidget(widget)` |
| `qapp` | QApplication instance | `qapp.processEvents()` |
| `qtmodeltester` | Test QAbstractItemModel | `qtmodeltester.check(model)` |
| `qtlog` | Capture Qt messages | `assert "warning" in qtlog.records` |

### qtbot Key Methods

```python
# Widget management
qtbot.addWidget(widget)           # Register for cleanup
qtbot.waitExposed(widget)         # Wait for widget to show
qtbot.waitActive(widget)          # Wait for widget activation

# Signal testing
qtbot.waitSignal(signal, timeout) # Wait for signal emission
qtbot.assertNotEmitted(signal)    # Assert signal not emitted
QSignalSpy(signal)                 # Record signal emissions

# Event simulation
qtbot.mouseClick(widget, Qt.MouseButton.LeftButton)
qtbot.keyClick(widget, Qt.Key.Key_Return)
qtbot.keyClicks(widget, "text")

# Timing
qtbot.wait(ms)                    # Process events for duration
qtbot.waitUntil(callable, timeout) # Wait for condition
```

### Testing Checklist

- [ ] Use real components where possible
- [ ] Mock only external dependencies
- [ ] Use `qtbot.addWidget()` for all widgets
- [ ] Check `is not None` for Qt containers
- [ ] Initialize attributes before `super().__init__()`
- [ ] Use QSignalSpy only with real signals
- [ ] Handle worker cleanup in fixtures
- [ ] Mock dialog `exec()` methods
- [ ] Use context managers for dependency injection
- [ ] Test both success and error paths

### Anti-Patterns to Avoid

```python
# ❌ Don't use QSignalSpy with mocks
spy = QSignalSpy(mock_object.signal)

# ❌ Don't check Qt container truthiness
if self.layout:  # Dangerous!

# ❌ Don't create GUI in threads
worker.run(): dialog = QDialog()

# ❌ Don't forget widget cleanup
widget = QWidget()  # No qtbot.addWidget()

# ❌ Don't mock everything
controller = Mock(spec=Controller)

# ❌ Don't access parent chain directly  
self.parent().parent().method()
```

### Recommended Test Structure

```python
import pytest
from PySide6.QtCore import QObject, Signal
from PySide6.QtTest import QSignalSpy
from unittest.mock import Mock

class TestMyComponent:
    """Test suite for MyComponent"""
    
    @pytest.fixture
    def component(self, qtbot):
        """Create component with test dependencies"""
        component = MyComponent(
            dependency=Mock(spec=RealDependency)
        )
        qtbot.addWidget(component)
        return component
    
    def test_initialization(self, component):
        """Test component initializes correctly"""
        assert component.isEnabled()
        assert component.dependency is not None
    
    def test_signal_emission(self, qtbot, component):
        """Test component emits signals correctly"""
        spy = QSignalSpy(component.data_changed)
        
        component.update_data("test")
        
        assert len(spy) == 1
        assert spy[0][0] == "test"
    
    def test_error_handling(self, qtbot, component):
        """Test component handles errors gracefully"""
        component.dependency.process.side_effect = Exception("Test error")
        
        with qtbot.assertNotEmitted(component.critical_error):
            component.safe_process()
        
        assert component.last_error == "Test error"
```

## Conclusion

Effective Qt testing requires understanding the framework's unique characteristics. By following these patterns and avoiding common pitfalls, you can create a robust, maintainable test suite that actually validates your application's behavior rather than just achieving coverage metrics.

Remember: **Real components with mocked dependencies** provide the optimal balance between test isolation and realistic behavior validation.

---

*Last updated: December 21, 2025*