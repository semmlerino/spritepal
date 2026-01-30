# Unified Testing Guide - DO NOT DELETE
*The single source of truth for testing SpritePal with Qt and pytest*

## Table of Contents
1. [Supported Stack](#supported-stack)
2. [Signal Reference](#signal-reference) (manager and worker signals)
3. [Core Principles](#core-principles) (includes System Boundaries, Deterministic Time)
4. [When to Mock](#when-to-mock)
5. [Signal Testing](#signal-testing) (includes TestSignal vs QSignalSpy guidance)
6. [Essential Test Doubles](#essential-test-doubles)
7. [Parametrized Tests](#parametrized-tests)
8. [Error Path Testing Strategy](#error-path-testing-strategy)
9. [Qt-Specific Patterns](#qt-specific-patterns)
10. [Qt Threading Safety](#qt-threading-safety)
11. [Critical Pitfalls](#critical-pitfalls)
12. [Quick Reference](#quick-reference)

---

## Supported Stack

| Component | Version/Library |
|-----------|-----------------|
| **Qt Binding** | PySide6 (not PyQt6) |
| **Qt Version** | 6.x |
| **Python** | 3.12+ |
| **Testing** | pytest, pytest-qt, pytest-mock, pytest-timeout |
| **Package Manager** | uv |

**Important**: All examples use PySide6 imports (`Signal` not `pyqtSignal`). If you're copy-pasting examples, ensure your imports match:
```python
from PySide6.QtCore import Signal, QObject
from PySide6.QtWidgets import QWidget, QDialog
```

---

## Signal Reference

This section documents the signals emitted by SpritePal managers and workers.

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

All managers inherit these signals:

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

## Core Principles

### 1. Test Behavior, Not Implementation
```python
# ❌ BAD - Testing implementation
with patch.object(model, '_parse_output') as mock_parse:
    model.refresh()
    mock_parse.assert_called_once()  # Who cares?

# ✅ GOOD - Testing behavior
model.refresh()
assert len(model.get_shots()) == 3  # Actual outcome
```

### 2. Real Components Over Mocks
```python
# ❌ BAD - Mocking everything
controller = Mock(spec=Controller)
controller.process.return_value = "result"

# ✅ GOOD - Real component with test dependencies
controller = Controller(
    process_pool=TestProcessPool(),  # Test double
    cache=CacheManager(tmp_path)     # Real with temp storage
)
```

### 3. Mock Only at System Boundaries

**SpritePal system boundaries** (mock these, test everything else real):

| Boundary | Example | Why Mock |
|----------|---------|----------|
| **HAL compressor subprocess** | `subprocess.run(["inhal", ...])` | External binary, slow, non-deterministic timing |
| **File-backed ROM cache** | `ROMCache.load()` with disk I/O | Use `tmp_path` for real I/O, mock only for error simulation |
| **OS-level clipboard** | `QClipboard.text()` | Platform-dependent, pollutes system state |
| **System time** | `time.time()`, `datetime.now()` | Non-deterministic, timing-sensitive tests |
| **Network** | HTTP calls (if any) | External service availability |

**Deterministic time guidance:**
```python
# ✅ monkeypatch time functions directly
def test_time_dependent_cache(monkeypatch):
    fake_time = 1000.0
    monkeypatch.setattr("time.time", lambda: fake_time)

    cache.store("key", data)
    assert cache.get_timestamp("key") == 1000.0

    # Advance time
    fake_time = 2000.0
    monkeypatch.setattr("time.time", lambda: fake_time)
    assert cache.is_expired("key", max_age=500)  # Expired

# ✅ For datetime, monkeypatch the module import location
def test_datetime_dependent(monkeypatch):
    from datetime import datetime
    fake_now = datetime(2025, 1, 15, 12, 0, 0)
    monkeypatch.setattr("mymodule.datetime",
                        Mock(now=Mock(return_value=fake_now)))
```

**File I/O Guidance:**
- **Prefer real I/O with `tmp_path`** - gives confidence tests work with real filesystem
- **Mock filesystem only for:**
  - Rare error branches (permission denied, disk full, network drive failures)
  - Non-portable system paths that can't be reproduced
  - Performance isolation when file I/O dominates test runtime
- **Don't mock** routine file reads/writes - use `tmp_path` fixture instead

---

## When to Mock: Layer-Based Strategy

| Test Layer | Mock | Use Real | Example |
|------------|------|----------|---------|
| **Unit** | Everything except class under test | Class logic, pure functions | Test `TileRenderer` with mock image data |
| **Integration** | System boundaries (HAL, disk I/O errors) | Managers, cache, workers, signals | Test `ExtractionManager` → `TileRenderer` → `HALCompressor` (mocked) |
| **UI** | Dialogs, file pickers, clipboard | Widgets, layouts, signals | Test button click → signal → manager call (mock manager) |

> **Note**: "Mock nothing in E2E" is an ideal, not a rule. In real pipelines, stub external services, licensing APIs, or nondeterministic dependencies when CI reliability matters more than perfect realism.

### Unit Testing - Mock External Dependencies
```python
def test_tile_renderer_unit():
    """Test TileRenderer logic without real image library."""
    renderer = TileRenderer()

    # Mock the image creation (boundary)
    with patch('PIL.Image.new') as mock_image:
        mock_image.return_value = Mock(width=8, height=8)

        # Test real logic
        result = renderer.render_tile(tile_data)
        assert result is not None
```

### Integration Testing - Mock System Boundaries
```python
def test_extraction_workflow_integration(app_context, tmp_path):
    """Test real manager → worker → renderer, mock HAL subprocess."""
    manager = app_context.core_operations_manager

    # Real components
    rom_path = tmp_path / "test.sfc"
    create_test_rom(rom_path)

    # Mock system boundary (HAL compressor subprocess)
    with patch('core.hal_compressor.HALCompressor.decompress') as mock_hal:
        mock_hal.return_value = create_test_tile_data()

        # Test real integration
        result = manager.extract_from_rom(rom_path, offset=0x200000)
        assert result.success
        assert len(result.files) > 0  # Real file creation via tmp_path
```

### UI Testing - Mock Managers, Test Widget Behavior
```python
def test_extract_button_ui(qtbot):
    """Test UI wiring without running full extraction."""
    mock_manager = Mock(spec=CoreOperationsManager)
    mock_manager.extract_from_vram.return_value = ExtractResult(success=True)

    widget = ExtractionTab(manager=mock_manager)
    qtbot.addWidget(widget)

    # Test real UI behavior
    qtbot.mouseClick(widget.extract_button, Qt.LeftButton)

    # Verify UI called manager correctly
    mock_manager.extract_from_vram.assert_called_once()
    assert widget.status_label.text() == "Extraction complete"
```

### Deciding What to Mock

**Mock when:**
- Dependency is slow (subprocess, network, large file I/O)
- Dependency is nondeterministic (system time, random data)
- Testing error paths (simulate disk full, permission denied)
- Isolating layer under test (UI tests shouldn't run real extraction)

**Keep real when:**
- Fast and deterministic (memory cache, data structures)
- Integration point being tested (manager → worker communication)
- Behavior depends on real implementation (signal emission order)
- `tmp_path` makes real I/O feasible

---

## Signal Testing

### Strategy: Choose the Right Tool

| Scenario | Tool | When to Use |
|----------|------|-------------|
| Real Qt widget signals | `QSignalSpy` | Testing actual Qt components |
| Test double signals | `TestSignal` | Non-Qt or mocked components |
| Async Qt operations | `qtbot.waitSignal()` | Waiting for real Qt signals |
| Mock object callbacks | `.assert_called()` | Pure Python mocks |

**Rule of thumb:**
- If the **code under test expects a Qt Signal**, use real `QObject`-based test doubles with actual signals.
- If the **code is pure Python** (no Qt dependency), prefer `TestSignal` or simple callbacks.

### QSignalSpy for Real Qt Signals
```python
def test_real_qt_signal(qtbot):
    widget = RealQtWidget()  # Real Qt object
    qtbot.addWidget(widget)
    
    # QSignalSpy ONLY works with real Qt signals
    spy = QSignalSpy(widget.data_changed)
    
    widget.update_data("test")
    
    assert len(spy) == 1
    assert spy[0][0] == "test"
```

### TestSignal for Test Doubles
```python
class TestSignal:
    """Lightweight signal test double"""
    def __init__(self):
        self.emissions = []
        self.callbacks = []
    
    def emit(self, *args):
        self.emissions.append(args)
        for callback in self.callbacks:
            callback(*args)
    
    def connect(self, callback):
        self.callbacks.append(callback)
    
    @property
    def was_emitted(self):
        return len(self.emissions) > 0

# Usage
def test_with_test_double():
    manager = TestProcessPoolManager()  # Has TestSignal
    manager.command_completed.connect(on_complete)
    
    manager.execute("test")
    
    assert manager.command_completed.was_emitted
```

### Waiting for Async Signals
```python
def test_async_operation(qtbot):
    processor = DataProcessor()  # Real Qt object
    
    with qtbot.waitSignal(processor.finished, timeout=1000) as blocker:
        processor.start()
    
    assert blocker.signal_triggered
    assert blocker.args[0] == "success"
```

### MultiSignalRecorder (Complex Workflows)

For verifying complex multi-signal workflows with ordering:
```python
from tests.ui.integration.helpers.signal_spy_utils import MultiSignalRecorder

def test_extract_workflow_signals(qtbot, app_context):
    """Verify complete extraction signal workflow."""
    manager = app_context.core_operations_manager

    recorder = MultiSignalRecorder()
    recorder.add_signal(manager.extraction_progress, "progress")
    recorder.add_signal(manager.palettes_extracted, "palettes")
    recorder.add_signal(manager.files_created, "files")

    manager.extract_from_vram(params)

    # Verify all signals fired
    assert recorder.was_emitted("progress")
    assert recorder.was_emitted("palettes")
    assert recorder.was_emitted("files")

    # Verify order
    recorder.verify_order(["progress", "palettes", "files"])

    # Verify count
    assert recorder.emission_count("progress") >= 3
```

**When to use which approach:**
| Goal | Use |
|------|-----|
| Wait for single async operation | `qtbot.waitSignal()` |
| Verify signal emitted N times | `QSignalSpy` |
| Inspect signal payloads | `QSignalSpy` |
| Verify multi-signal order | `MultiSignalRecorder` |
| Test pure Python callbacks | `TestSignal` or mock |

---

## Private Method Testing

### When It's Acceptable

Some private methods are **worth testing directly** despite implementation coupling:

1. **Pure algorithms:** Color conversion, compression, parsing
2. **Complex calculations:** Offset calculations, coordinate transforms
3. **Data structure manipulation:** Tree balancing, graph algorithms

**Example - Testing color conversion algorithm:**
```python
def test_bgr555_to_rgb888_conversion(palette_manager):
    """Direct algorithm test avoids I/O overhead."""
    palette_manager.cgram_data = create_test_cgram([0x7FFF, 0x0000, 0x001F])
    palette_manager._extract_palettes()  # Private method with pure algorithm

    assert palette_manager.palettes[0][0] == [255, 255, 255]  # White
    assert palette_manager.palettes[0][1] == [0, 0, 0]        # Black
    assert palette_manager.palettes[0][2] == [255, 0, 0]      # Red
```

**Justification:** Testing `_extract_palettes()` directly avoids:
- File I/O for CGRAM dumps
- Full manager initialization
- External dependencies (HAL, ROM cache)

This keeps tests **fast, focused, and deterministic**.

### When to Avoid Private Method Testing

Avoid testing private methods when:
- A **public API** exists that exercises the same logic
- The method is **implementation detail** that may change
- Tests can achieve the same coverage through **signal-based testing**

**Instead of:**
```python
# Couples test to implementation
widget._browse_file()  # Private UI action
```

**Prefer:**
```python
# Test via public API/signals
with qtbot.waitSignal(widget.file_selected, timeout=1000):
    qtbot.mouseClick(widget.browse_button, Qt.LeftButton)
```

### Test-Support Methods for Concurrency

For testing concurrency control without running actual operations, use the public
test-support methods on `BaseManager`:

```python
def test_concurrent_operations(app_context):
    manager = app_context.core_operations_manager

    # Start simulated operations
    assert manager.simulate_operation_start("vram_extraction")
    assert manager.simulate_operation_start("rom_extraction")

    # Verify conflict detection
    assert not manager.simulate_operation_start("vram_extraction")  # Already running

    # Cleanup
    manager.simulate_operation_finish("vram_extraction")
    manager.simulate_operation_finish("rom_extraction")
```

---

## Essential Test Doubles

### MockHALCompressor
```python
class MockHALCompressor:
    """Replace HAL compression calls with predictable behavior"""
    def __init__(self):
        self.compressions = []
        self.decompressions = []
        self.compression_complete = TestSignal()
        self.decompression_complete = TestSignal()
    
    def compress(self, data: bytes, format: str = "3bpp") -> bytes:
        self.compressions.append((data, format))
        # Return predictable compressed data
        compressed = b"\x00" * (len(data) // 2)
        self.compression_complete.emit(len(compressed))
        return compressed
    
    def decompress(self, data: bytes, format: str = "3bpp") -> bytes:
        self.decompressions.append((data, format))
        # Return predictable decompressed data
        decompressed = b"\xFF" * (len(data) * 2)
        self.decompression_complete.emit(len(decompressed))
        return decompressed
```

### MockMainWindow (Real Qt Signals, Mock Behavior)
```python
from PySide6.QtCore import QObject, Signal
from unittest.mock import Mock

class MockMainWindow(QObject):
    """Real Qt object with signals, mocked behavior"""

    # Real Qt signals (PySide6 uses Signal, not pyqtSignal)
    extraction_started = Signal()
    rom_loaded = Signal(str)
    sprite_found = Signal(int, object)

    def __init__(self):
        super().__init__()
        # Mock attributes
        self.status_bar = Mock()
        self.rom_path = None
        self.rom_size = 0x400000

    def get_extraction_params(self):
        return {
            "rom_path": "/test/rom.sfc",
            "start_offset": 0x200000,
            "format": "3bpp"
        }  # Test data
```

### Factory Fixtures
```python
@pytest.fixture
def make_sprite_data():
    """Factory for sprite test data"""
    def _make_sprite(offset=0x200000, size=0x800, format="3bpp"):
        return {
            "offset": offset,
            "size": size,
            "format": format,
            "data": b"\xFF" * size
        }
    return _make_sprite

@pytest.fixture
def real_rom_cache(tmp_path):
    """Real ROM cache with temp storage"""
    return ROMCache(cache_dir=tmp_path / "rom_cache")
```

### Parametrized Tests

Use `@pytest.mark.parametrize` to reduce duplicate test code and make coverage explicit:

```python
import pytest

# ✅ ROM offsets - test multiple extraction points
@pytest.mark.parametrize("offset,expected_size", [
    (0x200000, 0x800),   # Standard sprite bank
    (0x280000, 0x1000),  # Large sprite bank
    (0x000000, 0),       # Header area (no sprites)
    (0x3FFFFF, 0),       # Past end of ROM
])
def test_extract_sprite_at_offset(extraction_manager, offset, expected_size):
    result = extraction_manager.extract_at(offset)
    assert len(result.data) == expected_size


# ✅ Format variations
@pytest.mark.parametrize("format_id,bpp", [
    ("3bpp", 3),
    ("4bpp", 4),
    ("2bpp", 2),
])
def test_sprite_format_detection(sprite_validator, format_id, bpp):
    sprite = make_test_sprite(format=format_id)
    assert sprite_validator.detect_bpp(sprite) == bpp


# ✅ Error cases - explicit coverage of failure modes
@pytest.mark.parametrize("invalid_input,expected_error", [
    (None, TypeError),
    (b"", ValueError),
    (b"\x00" * 3, ValueError),  # Too short
    ("not bytes", TypeError),
])
def test_validation_rejects_invalid(sprite_validator, invalid_input, expected_error):
    with pytest.raises(expected_error):
        sprite_validator.validate(invalid_input)


# ✅ Combine with fixtures for complex scenarios
@pytest.mark.parametrize("width", [8, 16, 32])
@pytest.mark.parametrize("height", [8, 16, 32])
def test_sprite_dimensions(make_sprite_data, width, height):
    sprite = make_sprite_data(width=width, height=height)
    assert sprite.width == width
    assert sprite.height == height
```

**When to parametrize:**
- Multiple offsets, formats, or sizes that should behave similarly
- Known edge cases and boundary values
- Error conditions with expected exception types
- Combinations of independent parameters (use multiple decorators)

### Error Path Testing Strategy

Structure tests to cover success, invalid input, and external failure scenarios:

```python
class TestSpriteExtraction:
    """Example: structured coverage of success and error paths."""

    # ── Success Cases ──────────────────────────────────────────────
    def test_extract_valid_sprite(self, extraction_manager, valid_rom):
        """Happy path: valid ROM, valid offset."""
        result = extraction_manager.extract(valid_rom, offset=0x200000)
        assert result.success
        assert result.data is not None

    def test_extract_multiple_sprites(self, extraction_manager, valid_rom):
        """Happy path: batch extraction."""
        results = extraction_manager.extract_range(valid_rom, 0x200000, 0x210000)
        assert len(results) > 0
        assert all(r.success for r in results)

    # ── Invalid Input Cases ────────────────────────────────────────
    def test_extract_none_rom_raises(self, extraction_manager):
        """Invalid input: None ROM."""
        with pytest.raises(TypeError, match="ROM cannot be None"):
            extraction_manager.extract(None, offset=0x200000)

    def test_extract_negative_offset_raises(self, extraction_manager, valid_rom):
        """Invalid input: negative offset."""
        with pytest.raises(ValueError, match="offset must be non-negative"):
            extraction_manager.extract(valid_rom, offset=-1)

    def test_extract_offset_past_eof_returns_empty(self, extraction_manager, valid_rom):
        """Edge case: offset beyond ROM size."""
        result = extraction_manager.extract(valid_rom, offset=0xFFFFFFFF)
        assert not result.success
        assert result.error_code == "OFFSET_OUT_OF_RANGE"

    # ── External Failure Simulation ────────────────────────────────
    def test_extract_hal_subprocess_failure(self, extraction_manager, valid_rom, monkeypatch):
        """External failure: HAL decompressor crashes."""
        def mock_hal_crash(*args, **kwargs):
            raise subprocess.CalledProcessError(1, "inhal", stderr=b"Segfault")

        monkeypatch.setattr(extraction_manager._hal, "decompress", mock_hal_crash)

        result = extraction_manager.extract(valid_rom, offset=0x200000)
        assert not result.success
        assert "decompression failed" in result.error_message.lower()

    def test_extract_disk_full_on_cache_write(self, extraction_manager, valid_rom, monkeypatch):
        """External failure: disk full when caching result."""
        def mock_disk_full(*args, **kwargs):
            raise OSError(28, "No space left on device")

        monkeypatch.setattr(extraction_manager._cache, "store", mock_disk_full)

        # Extraction succeeds but cache fails gracefully
        result = extraction_manager.extract(valid_rom, offset=0x200000)
        assert result.success  # Core operation worked
        assert result.cached is False  # But caching failed
```

**Error path checklist:**
- [ ] Success with valid input (happy path)
- [ ] `TypeError` for wrong types (`None`, wrong class)
- [ ] `ValueError` for invalid values (negative, out of range)
- [ ] Edge cases (empty, boundary values, max size)
- [ ] External failures (subprocess crash, I/O error, network timeout)
- [ ] Graceful degradation (partial success, fallback behavior)

---

## Qt-Specific Patterns

### qtbot Essential Methods
```python
# Widget management
qtbot.addWidget(widget)           # Register for cleanup
qtbot.waitExposed(widget)         # Wait for show
qtbot.waitActive(widget)          # Wait for focus

# Signal testing
qtbot.waitSignal(signal, timeout=1000)
qtbot.assertNotEmitted(signal)
with qtbot.waitSignal(signal):
    do_something()

# Event simulation
qtbot.mouseClick(widget, Qt.LeftButton)
qtbot.keyClick(widget, Qt.Key_Return)
qtbot.keyClicks(widget, "text")

# Timing
qtbot.wait(100)                   # Process events
qtbot.waitUntil(lambda: condition, timeout=1000)
```

### Testing Modal Dialogs

**Important**: Mock at the specific dialog level, not the base `QDialog` class.
Qt uses C++ bindings, so base-class monkeypatching doesn't work reliably.

```python
def test_dialog(qtbot, monkeypatch):
    # Mock exec() on the SPECIFIC dialog class, not QDialog base
    monkeypatch.setattr(MyDialog, "exec",
                       lambda self: QDialog.DialogCode.Accepted)

    dialog = MyDialog()
    qtbot.addWidget(dialog)

    dialog.input_field.setText("test")
    result = dialog.exec()

    assert result == QDialog.DialogCode.Accepted
    assert dialog.get_value() == "test"
```

### Worker Thread Testing

**Prefer `waitSignal` over `waitUntil`** - signals are clearer and less flaky for QThread-like objects:

```python
def test_worker_preferred(qtbot):
    """Preferred pattern: wait on signals directly."""
    worker = DataWorker()
    qtbot.addWidget(worker)  # If worker is a QObject

    # ✅ PREFERRED - Wait on the finished signal directly
    with qtbot.waitSignal(worker.finished, timeout=5000) as blocker:
        worker.start()

    assert blocker.signal_triggered
    assert worker.result is not None

    # Cleanup
    if worker.isRunning():
        worker.quit()
        worker.wait(1000)


def test_worker_alternative(qtbot):
    """Alternative when signals aren't available or suitable."""
    worker = DataWorker()

    worker.start()

    # ⚠️ FALLBACK - Use waitUntil only when signal-based waiting isn't possible
    qtbot.waitUntil(lambda: not worker.isRunning(), timeout=5000)

    assert worker.result is not None

    # Cleanup
    if worker.isRunning():
        worker.quit()
        worker.wait(1000)
```

---

## Qt Threading Safety

### The Fundamental Rule: QPixmap vs QImage

Qt has **strict threading rules** that cause crashes if violated in tests:

| Class | Thread Safety | Usage |
|-------|---------------|--------|
| **QPixmap** | ❌ **Main GUI thread ONLY** | Display, UI rendering |
| **QImage** | ✅ **Any thread** | Image processing, workers |

### ⚠️ Threading Violation Crash Symptoms
```python
# ❌ FATAL ERROR - Creates QPixmap in worker thread
def test_worker_processing():
    def worker():
        pixmap = QPixmap(100, 100)  # CRASH: "Fatal Python error: Aborted"
    
    thread = threading.Thread(target=worker)
    thread.start()  # Will crash Python
```

### The Canonical Qt Threading Pattern

Qt's official threading pattern for image operations:

```
Worker Thread (Background):     Main Thread (GUI):
┌─────────────────────┐        ┌──────────────────┐
│ 1. Process with     │─signal→│ 4. Convert to    │
│    QImage           │        │    QPixmap       │
│                     │        │                  │
│ 2. Emit signal      │        │ 5. Display in UI │
│    with QImage      │        │                  │
│                     │        │                  │
│ 3. Worker finishes  │        │ 6. UI updates    │
└─────────────────────┘        └──────────────────┘
```

### Thread-Safe Test Doubles

> **SpritePal-specific pattern**: This is a recommended project-specific pattern, not an industry standard. The concept applies broadly to Qt threading, but the implementation is tailored to SpritePal's needs. Qt API details may vary across binding versions (PySide6 vs PyQt6) and Qt versions.

Create thread-safe alternatives for Qt objects in tests:

```python
from PySide6.QtCore import QSize
from PySide6.QtGui import QColor, QImage


class ThreadSafeTestImage:
    """Thread-safe test double for QPixmap using QImage internally.

    QPixmap is not thread-safe and can only be used in the main GUI thread.
    QImage is thread-safe and can be used in any thread. This class provides
    a QPixmap-like interface while using QImage internally for thread safety.

    Based on Qt's canonical threading pattern for image operations.
    """

    def __init__(self, width: int = 100, height: int = 100):
        """Create a thread-safe test image."""
        # Use QImage which is thread-safe, unlike QPixmap
        self._image = QImage(width, height, QImage.Format.Format_RGB32)
        self._width = width
        self._height = height
        self._image.fill(QColor(255, 255, 255))  # Fill with white by default

    def fill(self, color: QColor | None = None) -> None:
        """Fill the image with a color."""
        if color is None:
            color = QColor(255, 255, 255)
        self._image.fill(color)

    def isNull(self) -> bool:
        """Check if the image is null."""
        return self._image.isNull()

    def sizeInBytes(self) -> int:
        """Return the size of the image in bytes."""
        return self._image.sizeInBytes()

    def size(self) -> QSize:
        """Return the size of the image."""
        return QSize(self._width, self._height)
```

### Usage in Threading Tests

Replace QPixmap with ThreadSafeTestImage in tests that involve worker threads:

```python
def test_concurrent_image_processing():
    """Test concurrent image operations without Qt threading violations."""
    results = []
    errors = []
    
    def process_image(thread_id: int):
        """Process image in worker thread."""
        try:
            # ✅ SAFE - Use ThreadSafeTestImage instead of QPixmap
            image = ThreadSafeTestImage(100, 100)
            image.fill(QColor(255, 0, 0))  # Thread-safe operation
            
            # Mock the cache manager's QImage usage
            with patch('cache_manager.QImage') as mock_image_class:
                mock_image = MagicMock()
                mock_image.isNull.return_value = False
                mock_image.sizeInBytes.return_value = image.sizeInBytes()
                mock_image_class.return_value = mock_image
                
                # Test the actual threading behavior
                result = cache_manager.process_in_thread(image)
                results.append((thread_id, result is not None))
                
        except Exception as e:
            errors.append((thread_id, str(e)))
    
    # Start multiple worker threads
    threads = []
    for i in range(5):
        t = threading.Thread(target=process_image, args=(i,))
        threads.append(t)
        t.start()
        
    # Wait for completion
    for t in threads:
        t.join(timeout=5.0)
        
    # Verify no threading violations occurred
    assert len(errors) == 0, f"Threading errors: {errors}"
    assert len(results) == 5
```

### Real-World Example: Cache Manager Threading

Before (Crashes):
```python
# ❌ CAUSES CRASHES - QPixmap in worker thread
def test_cache_threading():
    def cache_worker():
        pixmap = QPixmap(100, 100)  # FATAL ERROR
        cache.store("key", pixmap)
    
    threading.Thread(target=cache_worker).start()
```

After (Thread-Safe):
```python
# ✅ THREAD-SAFE - QImage-based test double
def test_cache_threading():
    def cache_worker():
        image = ThreadSafeTestImage(100, 100)  # Safe in any thread
        
        # Mock the internal QImage usage
        with patch('cache_manager.QImage') as mock_qimage:
            mock_qimage.return_value = mock_image
            result = cache.store("key", image)
            
    threading.Thread(target=cache_worker).start()
```

### Key Implementation Insights

1. **Internal Implementation Matters**: Even if your API accepts "image-like" objects, the internal implementation must use QImage in worker threads.

2. **Patch the Right Level**: When mocking Qt image operations, patch `cache_manager.QImage`, not `QPixmap`.

3. **Test Double Strategy**: Create test doubles that mimic the interface but use thread-safe internals.

4. **Resource Management**: QImage cleanup is automatic, but track memory usage for performance tests.

### Threading Test Checklist

- [ ] ✅ Use `ThreadSafeTestImage` instead of `QPixmap` in worker threads
- [ ] ✅ Patch `QImage` operations, not `QPixmap` operations  
- [ ] ✅ Test both single-threaded and multi-threaded scenarios
- [ ] ✅ Verify no "Fatal Python error: Aborted" crashes
- [ ] ✅ Check that worker threads can create/manipulate images safely
- [ ] ✅ Ensure main thread can display results from worker threads

### Performance Considerations

```python
# QImage is slightly more expensive than QPixmap for creation
# but essential for thread safety

# ✅ GOOD - Efficient thread-safe testing
class TestImagePool:
    """Reuse ThreadSafeTestImage instances for performance."""
    
    def __init__(self):
        self._pool = []
        
    def get_test_image(self, width=100, height=100):
        if self._pool:
            image = self._pool.pop()
            image.fill()  # Reset to white
            return image
        return ThreadSafeTestImage(width, height)
        
    def return_image(self, image):
        self._pool.append(image)
```

---

## Critical Pitfalls

### ⚠️ Qt Threading Violations (FATAL)
```python
# ❌ CRASHES PYTHON - QPixmap in worker thread
def test_worker():
    def worker_func():
        pixmap = QPixmap(100, 100)  # FATAL: "Fatal Python error: Aborted"
    threading.Thread(target=worker_func).start()

# ✅ SAFE - QImage-based test double
def test_worker():
    def worker_func():
        image = ThreadSafeTestImage(100, 100)  # Thread-safe
    threading.Thread(target=worker_func).start()
```

### ⚠️ Qt Container Truthiness
```python
# ❌ DANGEROUS - Some Qt containers may evaluate falsy when empty!
if self.layout:  # May be False for empty QVBoxLayout in some bindings!
    self.layout.addWidget(widget)

# ✅ SAFE - Explicit None check
if self.layout is not None:
    self.layout.addWidget(widget)
```

> **Binding-dependent behavior**: Layout truthiness behavior varies between PySide6 and PyQt6, and across Qt versions. We've observed issues with `QVBoxLayout` and `QHBoxLayout` in PySide6. Prefer explicit `is not None` checks for all Qt objects to be safe.

### ⚠️ QSignalSpy Only Works with Real Signals
```python
# ❌ CRASHES
mock_widget = Mock()
spy = QSignalSpy(mock_widget.signal)  # TypeError!

# ✅ WORKS
real_widget = QWidget()
spy = QSignalSpy(real_widget.destroyed)  # Real signal
```

### ⚠️ Widget Initialization Order
```python
# ❌ WRONG - AttributeError risk
class MyWidget(QWidget):
    def __init__(self):
        super().__init__()  # Might trigger signals!
        self.data = []      # Too late!

# ✅ CORRECT
class MyWidget(QWidget):
    def __init__(self):
        self.data = []      # Initialize first
        super().__init__()
```

### ⚠️ Never Create GUI in Worker Threads
```python
# ❌ CRASH
class Worker(QThread):
    def run(self):
        dialog = QDialog()  # GUI in wrong thread!

# ✅ CORRECT
class Worker(QThread):
    show_dialog = Signal(str)  # PySide6 Signal

    def run(self):
        self.show_dialog.emit("message")  # Main thread shows
```

### ⚠️ Don't Mock Class Under Test
```python
# ❌ POINTLESS
def test_controller():
    controller = Mock(spec=Controller)
    controller.process.return_value = "result"
    # Testing the mock, not the controller!

# ✅ MEANINGFUL
def test_controller():
    controller = Controller(dependencies=Mock())
    result = controller.process()
    assert result == expected
```

### ⚠️ ROMCache Collision in Parallel Tests
```python
# ❌ FLAKY - Identical mock ROM content = same SHA-256 hash = cache collision
@pytest.fixture
def mock_rom_file(tmp_path):
    rom_data = bytearray(128 * 1024)
    # Static content means all parallel tests get the same cache key!
    rom_path = tmp_path / "test.sfc"
    rom_path.write_bytes(rom_data)
    return rom_path

# ✅ STABLE - UUID ensures unique content hash per test
@pytest.fixture
def mock_rom_file(tmp_path):
    import uuid
    rom_data = bytearray(128 * 1024)
    # Unique ID at start ensures each test gets unique cache key
    rom_data[0:16] = uuid.uuid4().bytes
    rom_path = tmp_path / "test.sfc"
    rom_path.write_bytes(rom_data)
    return rom_path
```

> **Root cause**: ROMCache uses SHA-256 hash of file content as cache key. When multiple parallel tests create mock ROMs with identical content, they share the same cache entry. This causes intermittent failures where one test's cached results affect another test's assertions.

---

## Quick Reference

### Testing Checklist
- [ ] Use real components where possible
- [ ] Mock only external dependencies
- [ ] Use `qtbot.addWidget()` for all widgets
- [ ] Check `is not None` for Qt containers
- [ ] Initialize attributes before `super().__init__()`
- [ ] Use QSignalSpy only with real signals
- [ ] Add UUID to mock ROM content (prevents cache collisions)
- [ ] Clean up workers in fixtures
- [ ] Mock dialog `exec()` methods
- [ ] Test both success and error paths
- [ ] **Use ThreadSafeTestImage instead of QPixmap in worker threads**
- [ ] **Patch QImage operations, not QPixmap operations in threading tests**
- [ ] **Verify no "Fatal Python error: Aborted" crashes in threading tests**

### Command Patterns
```python
# Run tests
pytest tests/  # Run all tests

# With coverage
pytest --cov=spritepal tests/

# Specific test
pytest tests/test_extraction_manager.py::TestExtractionManager::test_extract_sprites
```

### Common Fixtures
```python
@pytest.fixture
def qtbot(): ...           # Qt test interface
@pytest.fixture
def tmp_path(): ...         # Temp directory
@pytest.fixture
def isolated_data_repository(): ... # Isolated ROM/sprite data repository
@pytest.fixture
def monkeypatch(): ...      # Mock attributes
@pytest.fixture
def caplog(): ...           # Capture logs
```

### Before vs After Example
```python
# ❌ BEFORE - Excessive mocking
def test_bad(self):
    with patch.object(manager._hal_compressor, 'decompress') as mock:
        mock.return_value = b"\xFF" * 100
        manager.extract_sprite(offset)
        mock.assert_called()  # Testing mock

# ✅ AFTER - Test double with real behavior
def test_good(self):
    manager._hal_compressor = MockHALCompressor()
    test_rom_data = b"\x42" * 0x800
    
    result = manager.extract_sprite(0x200000, test_rom_data)
    
    assert result.success  # Testing behavior
    assert len(manager.get_extracted_sprites()) == 1
```

### Anti-Patterns Summary
```python
# ❌ QPixmap in worker threads (CRASHES)
threading.Thread(target=lambda: QPixmap(100, 100)).start()

# ❌ QSignalSpy with mocks
spy = QSignalSpy(mock.signal)

# ❌ Qt container truthiness
if self.layout:

# ❌ GUI in threads
worker.run(): QDialog()

# ❌ Mock everything
controller = Mock(spec=Controller)

# ❌ Parent chain access
self.parent().parent().method()

# ❌ Testing implementation
mock.assert_called_once()
```

---

## GUI Window Prevention in Tests

### The Challenge
Qt widgets that call `show()`, `showFullScreen()`, or dialog `exec()` can cause tests to:
- Hang waiting for user interaction
- Display flickering windows during test runs  
- Steal focus from other applications
- Fail in CI/CD environments

### Solutions (in order of preference)

#### 1. Mock Dialog exec() Methods (Recommended by pytest-qt)
```python
def test_dialog(qtbot, monkeypatch):
    # Mock the exec() method to return immediately
    monkeypatch.setattr(MyDialog, "exec", lambda self: QDialog.DialogCode.Accepted)
    
    dialog = MyDialog()
    result = dialog.exec()  # Returns immediately
    assert result == QDialog.DialogCode.Accepted
```

#### 2. Use pytest-timeout to Prevent Hanging Tests
```toml
# In pyproject.toml [tool.pytest.ini_options]:
timeout = 30
timeout_method = "thread"
```

#### 3. Set QT_QPA_PLATFORM=offscreen (RECOMMENDED)
```bash
# This is the recommended approach for all headless/CI testing
QT_QPA_PLATFORM=offscreen pytest tests/
```

**NOTE**: Do NOT use pytest-xvfb or xvfb-run - they cause hangs in WSL2 and some CI environments.

### Important Notes
- **Monkeypatching Qt base classes doesn't work** - Qt uses C++ bindings
- **Mock at the specific dialog/widget level** - Not at QWidget/QDialog base
- **Always set a timeout** - Prevents infinite hangs from GUI blocking

## Summary

**Philosophy**: Test behavior, not implementation.

**Strategy**: Real components with test doubles for I/O.

**Qt-Specific**: Respect the event loop, signals are first-class, threading rules are FATAL.

**GUI Prevention**: Mock dialog exec() methods, use timeouts, avoid actual window display.

**Observed Improvements** (SpritePal-specific, anecdotal):
- Test speed: Noticeably faster without HAL subprocess overhead
- Bug discovery: More issues caught with real integration vs excessive mocking
- Maintenance: Fewer mock updates needed when internal implementations change
- Memory safety: ThreadSafeTestImage eliminated Qt threading crashes

**SpritePal Testing Focus Areas**:
- ROM extraction/injection workflows
- Sprite detection and validation
- Palette management
- Manual offset dialog singleton behavior
- Grid arrangement and preview generation
- Worker thread lifecycle management
- Cache consistency

---

## Debugging Recipes

### Taking UI Screenshots

```bash
# Capture app window (requires X11/xcb display)
QT_QPA_PLATFORM=xcb uv run python -c "
from PySide6.QtCore import QTimer; from launch_spritepal import SpritePalApp; import sys
app = SpritePalApp(sys.argv); w = app.main_window; w.show(); w.resize(1000, 900)
QTimer.singleShot(500, lambda: (w.grab().save('/tmp/spritepal_screenshot.png'), app.quit()))
app.exec()
"
```

**Debug widget boundaries:** `widget.setStyleSheet('QWidget { border: 1px solid red; }')`

### Headless Rendering & Visual Comparisons

Test visual changes without launching the full app:

```bash
# Render workbench alignment (list mappings with --list-mappings)
uv run python scripts/render_workbench.py -p mapping.spritepal-mapping.json -m 0 -o /tmp/workbench.png

# Render quantized preview (side-by-side original vs quantized)
uv run python scripts/render_quantized_preview.py -p mapping.spritepal-mapping.json -m 0 \
    --side-by-side --display-scale 8 -o /tmp/quantized.png
```

**Before/after comparison workflow:**
1. Render with current code → `/tmp/after.png`
2. Temporarily revert the change in source
3. Render with old code → `/tmp/before.png`
4. Restore the fix
5. Create comparison (see `scripts/render_quantized_preview.py` for pattern)

**Quick symmetry test** (verifies quantization preserves symmetric pixels):
```bash
uv run pytest tests/unit/test_palette_utils.py::TestQuantizationSymmetry -v
```

---

*Last Updated: January 30, 2026 | SpritePal Testing Reference - DO NOT DELETE*

**Critical**: ThreadSafeTestImage implementation required to prevent Qt threading violations that cause "Fatal Python error: Aborted" crashes in worker tests.