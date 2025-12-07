# SpritePal Development Guidelines

## Quick Reference

- **Qt Framework**: PySide6 (not PyQt6)
- **Python Version**: 3.11+
- **Package Manager**: uv
- **Config Source of Truth**: `pyproject.toml` (ruff, basedpyright, pytest)

## Documentation Structure

```
spritepal/
├── CLAUDE.md                           # This file - development guidelines
├── README.md                           # Project overview
├── docs/
│   ├── architecture.md                 # Layer structure and import rules
│   ├── REAL_COMPONENT_TESTING_GUIDE.md # Real component testing patterns
│   ├── QT_TESTING_BEST_PRACTICES.md    # pytest-qt patterns
│   ├── dialog_development_guide.md     # Dialog creation patterns
│   └── archive/                        # Historical documentation
├── tests/
│   ├── README.md                       # Test suite overview
│   └── HEADLESS_TESTING.md             # Headless/CI testing
├── TESTING_DEBUG_GUIDE_DO_NOT_DELETE.md    # Critical debug strategies
├── UNIFIED_TESTING_GUIDE_DO_NOT_DELETE.md  # Testing single source of truth
└── SPRITE_LEARNINGS_DO_NOT_DELETE.md       # Sprite extraction knowledge
```

## Development Tools

All tools use the parent venv from the `spritepal/` directory:

```bash
# Sync dependencies (from exhal-master/)
uv sync --extra dev

# Linting (from spritepal/)
../.venv/bin/ruff check .
../.venv/bin/ruff check . --fix

# Type checking (from spritepal/)
../.venv/bin/basedpyright core ui utils

# Tests (from spritepal/)
../.venv/bin/pytest tests -v
../.venv/bin/pytest tests -m "headless and not slow"  # Fast tests
../.venv/bin/pytest tests -m "gui" --xvfb             # GUI tests
```

## Qt Testing Best Practices

### Real Component Testing (Preferred)

SpritePal uses real components over mocks. **Prefer real components; mock only at true system boundaries** (HAL subprocess, file I/O, clipboard, network).

```python
from spritepal.tests.infrastructure.real_component_factory import RealComponentFactory
from spritepal.core.extraction_params import ExtractionParams

def test_extraction_workflow():
    with RealComponentFactory() as factory:
        manager = factory.create_extraction_manager(with_test_data=True)
        params = ExtractionParams(offset=0x1000, width=16, height=16)
        result = manager.validate_extraction_params(params)
        assert isinstance(result, bool)  # Real behavior
```

### Critical Crash Prevention

**Never inherit from QDialog in mocks** - causes metaclass conflicts:
```python
from PySide6.QtCore import QObject, Signal

# CORRECT
class MockDialog(QObject):
    accepted = Signal()
    rejected = Signal()

# INCORRECT - Causes fatal crashes
class MockDialog(QDialog):  # Don't do this!
    pass
```

**Mock at import location, not definition**:
```python
@patch('ui.rom_extraction_panel.UnifiedManualOffsetDialog')  # Correct
```

### Signal Testing
```python
def test_async_operation(qtbot, worker):
    worker.start()
    qtbot.waitSignal(worker.finished, timeout=5000)

# For multiple signals (finished OR failed):
def test_async_with_failure_case(qtbot, worker):
    with qtbot.waitSignals([worker.finished, worker.failed], timeout=5000):
        worker.start()
```

### Test Markers
- `@pytest.mark.gui` - Requires display or xvfb (real Qt widgets rendered)
- `@pytest.mark.headless` - No display required (can use real components if no rendering)
- `@pytest.mark.serial` - No parallel execution

### Test Fixture Selection Guide

| Need | Use | NOT |
|------|-----|-----|
| Fast tests, shared state OK | `session_managers` | `setup_managers` |
| Isolated manager state | `isolated_managers` | `session_managers` |
| Real component testing | `RealComponentFactory` | `Mock()` + `cast()` |
| Qt images in worker thread | `ThreadSafeTestImage` | `QPixmap` |
| Singleton dialog cleanup | `cleanup_singleton` | Own cleanup fixture |
| Signal waiting | `qtbot.waitSignal()` | `time.sleep()` |

**Manager Fixture Isolation Levels:**

| Fixture | Scope | Reset Between Tests | Use When |
|---------|-------|---------------------|----------|
| `session_managers` | Session | NO | Fast tests OK with shared state; state persists across ALL tests |
| `isolated_managers` | Function | YES (full cleanup) | Tests that modify manager state or need clean slate |
| `setup_managers` | Function | YES | Default fixture with conditional setup |
| `fast_managers` | Function (backed by session) | NO | Performance-focused tests (alias for session_managers) |

**IMPORTANT**: `session_managers` is NOT reset between tests - manager state (caches, settings, active operations) persists across the entire test session. Use `isolated_managers` when:
- Your test modifies ManagerRegistry state
- Your test needs predictable initial state
- Your test could pollute state for other tests

The `isolated_managers` fixture has an explicit guard that fails if ManagerRegistry is already initialized (detects test pollution).

**Common Mistakes to Avoid:**
- `QPixmap` in worker threads causes fatal crashes - use `ThreadSafeTestImage`
- Hardcoded thread counts - capture baseline at test start
- `time.sleep()` in Qt tests - use `qtbot.wait()` or `waitSignal()`
- Inheriting `QDialog` in mocks - causes metaclass crashes
- Missing singleton cleanup - use `cleanup_singleton` fixture

**Environment Variables** (implemented in `spritepal/tests/conftest.py`):
- `PYTEST_TIMEOUT_MULTIPLIER=2.0` - Scale all timeouts (useful for slow CI)
- `PYTEST_DEBUG_FIXTURES=1` - Enable fixture performance monitoring

## Project Architecture

```
spritepal/
├── core/              # Business logic (managers, extractors)
├── ui/                # Qt UI components
│   ├── components/    # Reusable widgets
│   ├── dialogs/       # Dialog windows
│   ├── panels/        # Panel widgets
│   └── windows/       # Main/detached windows
├── tests/
│   ├── infrastructure/  # RealComponentFactory, test contexts
│   └── examples/        # Pattern examples
└── utils/             # Shared utilities
```

### Import Rules (see docs/architecture.md)
- **UI** imports from: core/, managers/, utils/
- **Managers** import from: core/, utils/
- **Core** imports from: utils/
- **Utils** imports from: Python stdlib only

### Circular Import Resolution
```python
def open_detached_gallery(self):
    # Local import to avoid circular dependency
    from spritepal.ui.windows.detached_gallery_window import DetachedGalleryWindow
    self.detached_window = DetachedGalleryWindow(self)
```

## Key Patterns

### Resource Management
Always use context managers for file/mmap resources:
```python
@contextmanager
def _rom_context(self):
    rom_file = None
    rom_mmap = None
    try:
        rom_file = Path(self.rom_path).open('rb')
        rom_mmap = mmap.mmap(rom_file.fileno(), 0, access=mmap.ACCESS_READ)
        yield rom_mmap
    finally:
        with suppress(Exception):
            if rom_mmap: rom_mmap.close()
        with suppress(Exception):
            if rom_file: rom_file.close()
```

### Thread Safety
- Use `QMutex/QMutexLocker` for shared state
- Prefer signal-based waiting; avoid sleeps except for narrowly scoped throttling
- Test with `qtbot.waitSignal()` for async operations

### Dialog Initialization (DialogBase pattern)
```python
class MyDialog(DialogBase):
    def __init__(self, parent: QWidget | None = None):
        # Step 1: Declare ALL instance variables BEFORE super().__init__
        self.my_widget: QWidget | None = None

        # Step 2: Call super().__init__() - this calls _setup_ui()
        super().__init__(parent)

    def _setup_ui(self):
        # Step 3: Create widgets
        self.my_widget = QPushButton("Click me")
```

## Mesen2/Sprite Finding (Active Work)

Current focus: Finding and extracting SNES sprites using Mesen2 emulator.

Key documentation:
- `NEXT_STEPS_PLAN.md` - Current sprite finding strategy
- `MESEN2_LUA_API_LEARNINGS_DO_NOT_DELETE.md` - Lua scripting knowledge
- `SPRITE_LEARNINGS_DO_NOT_DELETE.md` - ROM extraction patterns

## Historical Documentation

Completed phase reports and one-time fix summaries are archived in:
`docs/archive/` (phase_reports/, migration_reports/, fix_summaries/, analysis_docs/)

---

*Last updated: December 2025*
