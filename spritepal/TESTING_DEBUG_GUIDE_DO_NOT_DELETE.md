# Testing Debug Guide - DO NOT DELETE

*Essential debugging strategies learned from pytest documentation via context7 MCP*

## Critical Tools for Debugging Hanging Tests

### 1. pytest-pystack - Automatic Stack Trace Capture

**Installation (manual - not in default dev dependencies):**
```bash
# pytest-pystack is NOT included in pyproject.toml dev dependencies
# Install manually when needed for debugging hanging tests:
uv pip install pytest-pystack
# Or with pip:
pip install pytest-pystack
```

> **Note:** This is an optional debugging tool, not required for normal test execution.

**Usage for Hanging Test Detection:**
```bash
# Monitor all tests and generate stack trace if they run longer than threshold
pytest --pystack-threshold=5 --pystack-output-file=hang_traces.log

# Key options:
--pystack-threshold=<seconds>  # Capture stack if test runs longer than this
--pystack-output-file=<path>   # Save stack traces to file
--pystack-args="--native"      # Include native stack traces
```

**Benefits:**
- Automatically captures WHERE tests are hanging
- Doesn't stop the test, just captures the stack trace
- Can run on entire test suite to identify all problematic tests

### 2. pytest-qt Best Practices for Async Operations

**Proper Signal Waiting (Prevents Hangs):**
```python
# CORRECT - With timeout and proper error handling
def test_async_operation(qtbot):
    with qtbot.waitSignal(worker.finished, timeout=5000) as blocker:
        blocker.connect(worker.failed)  # Monitor multiple signals
        worker.start()
    assert blocker.signal_triggered

# INCORRECT - Can hang forever
def test_bad(qtbot):
    worker.start()
    while not worker.is_finished:  # DON'T DO THIS
        qtbot.wait(100)
```

**Key qtbot Methods:**
- `qtbot.waitSignal(signal, timeout=5000)` - Wait for signal with timeout
- `qtbot.waitUntil(callback, timeout=5000)` - Wait for condition
- `qtbot.waitCallback()` - Wait for callback execution
- `qtbot.wait(ms)` - Process events for specified time

**Common Qt Testing Pitfalls:**
1. Not using proper timeouts in waitSignal
2. Infinite loops waiting for conditions
3. Not processing Qt events properly
4. Creating GUI elements in worker threads

### 3. Test Timeout Strategies

**Per-Test Timeout:**
```bash
pytest --timeout=10  # 10 seconds per test
```

**In pyproject.toml:**
```toml
[tool.pytest.ini_options]
timeout = 10
timeout_method = "signal"  # or "thread"
```

**Programmatic:**
```python
@pytest.mark.timeout(5)
def test_quick_operation():
    pass
```

## Debugging Workflow for Hanging Tests

### Step 1: Identify Hanging Tests
```bash
# Run with pystack to capture where tests hang
pytest tests/ --pystack-threshold=3 --pystack-output-file=hangs.log -v

# Analyze the output
cat hangs.log  # Shows exact line where test is stuck
```

### Step 2: Common Fixes for Hanging Tests

**Fix 1: Add Timeouts to Qt Operations**
```python
# Before (hangs if signal never emitted)
with qtbot.waitSignal(signal):
    do_something()

# After (fails cleanly after timeout)
with qtbot.waitSignal(signal, timeout=5000, raising=True):
    do_something()
```

**Fix 2: Use waitUntil for Conditions**
```python
# Before (infinite loop)
while not widget.isVisible():
    qtbot.wait(100)

# After (timeout-aware)
qtbot.waitUntil(lambda: widget.isVisible(), timeout=5000)
```

**Fix 3: Proper Thread Cleanup**
```python
def test_worker(qtbot):
    worker = Worker()
    try:
        worker.start()
        qtbot.waitUntil(lambda: not worker.isRunning(), timeout=5000)
    finally:
        if worker.isRunning():
            worker.quit()
            worker.wait(1000)
```

## Performance Optimization Patterns

### 1. Fixture Scope Optimization
```python
# Identified with pytest --durations=20

# Problem: Heavy setup for every test
@pytest.fixture(autouse=True)
def setup_managers():
    initialize_managers()  # 350ms per test!

# Solution: Add marker to skip when not needed
@pytest.fixture(autouse=True)
def setup_managers(request):
    if request.node.get_closest_marker("no_manager_setup"):
        yield
        return
    initialize_managers()
```

### 2. Test Categorization
```python
# Fast unit tests
@pytest.mark.no_manager_setup
@pytest.mark.unit
def test_pure_function():
    assert add(2, 2) == 4

# Slower integration tests
@pytest.mark.integration
@pytest.mark.gui
def test_full_workflow(qtbot):
    # Complex GUI test
```

### 3. Running Tests by Category
```bash
# Fast tests only
QT_QPA_PLATFORM=offscreen pytest -m "unit and no_manager_setup"

# GUI tests with offscreen backend
QT_QPA_PLATFORM=offscreen pytest -m "gui"

# Skip slow tests during development
QT_QPA_PLATFORM=offscreen pytest -m "not slow"
```

## Environment-Specific Issues

### WSL/Headless Environment Handling
```python
import os
import sys

def is_headless_environment():
    """Detect if running in headless environment"""
    if os.environ.get("CI"):
        return True
    if not os.environ.get("DISPLAY"):
        return True
    if "microsoft" in os.uname().release.lower():  # WSL detection
        return True
    return False

# Skip GUI tests in incompatible environments
@pytest.mark.skipif(
    is_headless_environment(),
    reason="GUI tests require display"
)
def test_gui_operation(qtbot):
    pass
```

### Offscreen Backend for CI/Headless Testing
```bash
# Use Qt's offscreen platform (recommended - no dependencies)
QT_QPA_PLATFORM=offscreen pytest tests/

# Alternative: Set in conftest.py (already configured)
# os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

# NOTE: Do NOT use pytest-xvfb - it causes hangs in WSL2/CI environments
```

## Key Metrics and Benchmarks

### Performance Targets
- Unit tests: < 0.1s per test
- Integration tests: < 1s per test  
- GUI tests: < 2s per test
- Full suite: < 5 minutes

### Monitoring Commands
```bash
# Profile slow tests
pytest --durations=20

# Memory profiling
pytest --memray

# Coverage with performance
pytest --cov --cov-report=term --durations=10
```

## Emergency Fixes

### When Everything is Timing Out
1. **Add --timeout flag**: `pytest --timeout=5`
2. **Run minimal subset**: `pytest tests/test_constants.py -v`
3. **Check for autouse fixtures**: Look in conftest.py
4. **Use pystack**: `pytest --pystack-threshold=2`
5. **Disable problematic fixtures temporarily**

### Quick Test Health Check
```bash
# Count tests
pytest --collect-only -q | tail -1

# Run fastest tests first
pytest tests/test_constants.py tests/test_exceptions.py

# Check for import errors
python -c "import tests.test_module"
```

## Lessons Learned

1. **Timeouts are critical** - Never use infinite waits in tests
2. **Monitor autouse fixtures** - They run for EVERY test
3. **Use markers liberally** - Categorize tests for selective running
4. **pystack is invaluable** - Shows exactly where tests hang
5. **Real components > mocks** - But need proper cleanup
6. **Environment matters** - WSL/Docker/CI need special handling

## References

- pytest-pystack: https://github.com/bloomberg/pytest-pystack
- pytest-qt: https://github.com/pytest-dev/pytest-qt
- pytest-timeout: https://github.com/pytest-dev/pytest-timeout
- UNIFIED_TESTING_GUIDE_DO_NOT_DELETE.md - Project-specific patterns

---
*Last Updated: 2025-08-16 | Critical debugging reference - DO NOT DELETE*