# Testing Guide

*Single source of truth for testing SpritePal with Qt and pytest*

## Stack

| Component | Version |
|-----------|---------|
| Qt Binding | PySide6 |
| Python | 3.12+ |
| Testing | pytest, pytest-qt, pytest-mock, pytest-timeout |
| Package Manager | uv |

---

## Core Principles

1. **Test behavior, not implementation** - Assert outcomes, not internal method calls
2. **Real components over mocks** - Mock only at system boundaries
3. **Use `tmp_path` for file I/O** - Real filesystem, isolated per-test

### System Boundaries (Mock These)

| Boundary | Why Mock |
|----------|----------|
| HAL compressor subprocess | External binary, slow |
| System time | Non-deterministic |
| Clipboard | Platform-dependent |
| Network | External service |

### What to Keep Real

- Memory cache, data structures
- Manager → worker communication
- Signal emission order
- File I/O via `tmp_path`

---

## When to Mock

| Test Layer | Mock | Keep Real |
|------------|------|-----------|
| **Unit** | External deps | Class under test |
| **Integration** | System boundaries | Managers, workers, signals |
| **UI** | Dialogs, managers | Widgets, layouts, signals |

```python
# Unit: mock external dependency
with patch('PIL.Image.new') as mock:
    result = renderer.render_tile(data)

# Integration: mock system boundary only
with patch('core.hal_compressor.HALCompressor.decompress') as mock:
    result = manager.extract_from_rom(rom_path)

# UI: mock manager, test widget behavior
mock_manager = Mock(spec=CoreOperationsManager)
widget = ExtractionTab(manager=mock_manager)
qtbot.mouseClick(widget.extract_button, Qt.LeftButton)
mock_manager.extract_from_vram.assert_called_once()
```

---

## Signal Testing

| Scenario | Tool |
|----------|------|
| Real Qt signals | `QSignalSpy` |
| Async wait | `qtbot.waitSignal()` |
| Multi-signal order | `MultiSignalRecorder` (see `tests/ui/integration/helpers/`) |
| Mock callbacks | `.assert_called()` |

```python
# Wait for async signal
with qtbot.waitSignal(worker.finished, timeout=5000):
    worker.start()

# Spy on signal emissions
spy = QSignalSpy(widget.data_changed)
widget.update_data("test")
assert len(spy) == 1
```

**Rule:** `QSignalSpy` only works with real Qt signals, not mocks.

---

## Qt Pitfalls (Will Crash or Fail)

| Pitfall | Symptom | Fix |
|---------|---------|-----|
| `QPixmap` in worker thread | "Fatal Python error: Aborted" | Use `ThreadSafeTestImage` |
| `if pos:` for QPoint | False for (0,0) | `if pos is not None:` |
| `waitSignal()` no context | Race condition | `with qtbot.waitSignal(...):` |
| `time.sleep()` in tests | Blocks event loop | `qtbot.wait(ms)` |
| `gc.collect()` in Qt cleanup | Segfault | `deleteLater()` + `processEvents()` |
| Mock inherits `QDialog` | Real dialog created | Inherit `QObject` |
| Mock at definition site | Patch fails | `@patch('module.that.imports.Class')` |
| Multiple `QApplication` | Qt error | Let pytest-qt manage |
| `QSignalSpy(mock.signal)` | TypeError | Only use with real signals |
| Init after `super().__init__()` | AttributeError | Init attributes first |
| GUI created in worker | Crash | Emit signal, create in main thread |

### Safe Worker Cleanup

```python
worker.requestInterruption()
worker.quit()
worker.wait(5000)
worker.deleteLater()
QApplication.processEvents()
```

### Threading Rule

- **QPixmap** - Main thread only
- **QImage** - Any thread (use `ThreadSafeTestImage` in tests)

---

## Testing Patterns

### Modal Dialogs

Mock `exec()` on the specific dialog class, not `QDialog` base:

```python
monkeypatch.setattr(MyDialog, "exec", lambda self: QDialog.DialogCode.Accepted)
```

### Worker Threads

Prefer `waitSignal` over `waitUntil`:

```python
with qtbot.waitSignal(worker.finished, timeout=5000):
    worker.start()
```

### Parallel Test Isolation

Add UUID to mock ROM content to prevent cache collisions:

```python
@pytest.fixture
def mock_rom_file(tmp_path):
    rom_data = bytearray(128 * 1024)
    rom_data[0:16] = uuid.uuid4().bytes  # Unique hash per test
    rom_path = tmp_path / "test.sfc"
    rom_path.write_bytes(rom_data)
    return rom_path
```

### Error Path Testing

```python
class TestExtraction:
    def test_success(self, manager, valid_rom):
        result = manager.extract(valid_rom, offset=0x200000)
        assert result.success

    def test_none_raises(self, manager):
        with pytest.raises(TypeError):
            manager.extract(None, offset=0x200000)

    def test_hal_failure(self, manager, valid_rom, monkeypatch):
        monkeypatch.setattr(manager._hal, "decompress",
            lambda *a: (_ for _ in ()).throw(subprocess.CalledProcessError(1, "inhal")))
        result = manager.extract(valid_rom, offset=0x200000)
        assert not result.success
```

### Parametrized Tests

```python
@pytest.mark.parametrize("offset,expected", [
    (0x200000, 0x800),
    (0x000000, 0),      # Header
    (0x3FFFFF, 0),      # Past EOF
])
def test_extract_at_offset(manager, offset, expected):
    assert len(manager.extract_at(offset).data) == expected
```

---

## Quick Reference

### Commands

```bash
pytest tests/                    # All tests
pytest tests/unit/ -q            # Unit only (fastest)
pytest -x -vv                    # Stop on first failure
pytest --lf -vv                  # Re-run failures
pytest -n auto --dist=loadscope # Parallel
pytest --durations=20            # Find slow tests
```

### Fixtures

| Fixture | Purpose |
|---------|---------|
| `qtbot` | Qt test interface |
| `tmp_path` | Temp directory |
| `app_context` | Clean managers per-test |
| `monkeypatch` | Mock attributes |

### Checklist

- [ ] `qtbot.addWidget()` for all widgets
- [ ] `is not None` for Qt containers
- [ ] Init attributes before `super().__init__()`
- [ ] UUID in mock ROM content
- [ ] Mock dialog `exec()` not base class
- [ ] `ThreadSafeTestImage` in worker threads

---

## GUI Prevention

```bash
QT_QPA_PLATFORM=offscreen pytest tests/  # Headless
```

Mock dialog execution:
```python
monkeypatch.setattr(MyDialog, "exec", lambda self: QDialog.DialogCode.Accepted)
```

Set timeout in `pyproject.toml`:
```toml
[tool.pytest.ini_options]
timeout = 30
```

---

## Debugging Recipes

### UI Screenshots

```bash
QT_QPA_PLATFORM=xcb uv run python -c "
from PySide6.QtCore import QTimer; from launch_spritepal import SpritePalApp; import sys
app = SpritePalApp(sys.argv); w = app.main_window; w.show(); w.resize(1000, 900)
QTimer.singleShot(500, lambda: (w.grab().save('/tmp/screenshot.png'), app.quit()))
app.exec()
"
```

### Visual Comparisons

```bash
uv run python scripts/render_workbench.py -p mapping.spritepal-mapping.json -m 0 -o /tmp/workbench.png
uv run python scripts/render_quantized_preview.py -p mapping.spritepal-mapping.json -m 0 --side-by-side -o /tmp/quantized.png
```

### Debug Widget Boundaries

```python
widget.setStyleSheet('QWidget { border: 1px solid red; }')
```

---

## Key Test Infrastructure

| Class | Location | Purpose |
|-------|----------|---------|
| `ThreadSafeTestImage` | `tests/infrastructure/thread_safe_test_image.py` | QPixmap replacement for workers |
| `MockHALCompressor` | `tests/infrastructure/` | HAL subprocess mock |
| `MultiSignalRecorder` | `tests/ui/integration/helpers/signal_spy_utils.py` | Multi-signal order verification |
| `RealComponentFactory` | `tests/infrastructure/real_component_factory.py` | Real component creation |

---

*Last Updated: January 30, 2026*
