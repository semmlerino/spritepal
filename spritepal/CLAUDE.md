# SpritePal Development Guidelines

## Critical Rules (Read First)

These rules prevent crashes and test failures. Violating them causes hard-to-debug issues.

| Rule | Why |
|------|-----|
| **Never `QPixmap` in worker threads** | Fatal crash. Use `ThreadSafeTestImage` instead |
| **Never inherit `QDialog` in mocks** | Metaclass conflict = fatal crash. Use `QObject` with signals |
| **Always use `isolated_managers` fixture** | Default choice. `session_managers` causes order-dependent failures |
| **Use `tmp_path` for file operations** | Hardcoded paths break parallel tests |
| **Use `with qtbot.waitSignal():`** | The non-context form races with fast workers |
| **Never `time.sleep()` in Qt tests** | Use `qtbot.wait()` or `waitSignal()` |
| **Mock at import location** | `@patch('spritepal.ui.panel.Dialog')`, not `@patch('spritepal.ui.dialogs.Dialog')` |

## Quick Reference

- **Qt Framework**: PySide6 (not PyQt6)
- **Python Version**: 3.12+
- **Package Manager**: uv
- **Config Source of Truth**: `pyproject.toml` (ruff, basedpyright, pytest)

## Development Commands

All tools run via `uv` from the `spritepal/` directory. If `uv` is not in PATH, use `~/.local/bin/uv run ...`

```bash
# Dependencies
uv sync --extra dev

# Linting
uv run ruff check .
uv run ruff check . --fix

# Type checking
uv run basedpyright core ui utils

# Tests - routine (parallel by default)
uv run pytest

# Tests - debug a failure (serial, verbose)
uv run pytest tests/path/test_file.py::test_name -vv --tb=long -s -n 0

# Tests - full suite
uv run pytest --maxfail=10
```

**Do not use `-q` when debugging failures** - it hides needed information.

## Documentation Pointers

| File | Content |
|------|---------|
| `docs/architecture.md` | Layer structure and import rules |
| `docs/testing_guide.md` | Detailed testing patterns |
| `tests/README.md` | Test suite overview |
| `SPRITE_LEARNINGS_DO_NOT_DELETE.md` | Sprite extraction domain knowledge |
| `DEV_NOTES.md` | Mesen2 integration, historical context |

## Qt Testing

### Minimal Test Template

```python
from tests.fixtures.timeouts import worker_timeout

def test_my_feature(isolated_managers, tmp_path):
    """One-line description."""
    manager = isolated_managers.extraction_manager
    output_file = tmp_path / "output.bin"
    result = manager.some_method()
    assert result is not None
```

### Signal Testing Pattern

```python
from tests.fixtures.timeouts import worker_timeout, LONG

# CORRECT: Context manager catches fast signals
def test_async_op(qtbot, worker):
    with qtbot.waitSignal(worker.finished, timeout=worker_timeout()):
        worker.start()

# For slow operations
def test_slow_op(qtbot, worker):
    with qtbot.waitSignal(worker.finished, timeout=worker_timeout(LONG)):
        worker.start()
```

**Anti-pattern:**
```python
# WRONG: Races with fast-completing workers
worker.start()
qtbot.waitSignal(worker.finished, timeout=worker_timeout())  # May miss signal!
```

### Timeout Functions

Import from `tests/fixtures/timeouts.py` (these are functions, not fixtures):

| Function | Base (ms) | Use For |
|----------|-----------|---------|
| `ui_timeout()` | 1000 | Widget visibility, layout updates |
| `signal_timeout()` | 2000 | Generic signal waits |
| `dialog_timeout()` | 3000 | Dialog accept/reject |
| `worker_timeout()` | 5000 | Background workers, QThread |
| `cleanup_timeout()` | 2000 | Thread termination |

Multipliers: `SHORT=0.5`, `MEDIUM=1.0` (default), `LONG=2.0`

Scale all with `PYTEST_TIMEOUT_MULTIPLIER` env var for slow CI.

### Test Markers

| Marker | Effect |
|--------|--------|
| `@pytest.mark.requires_display` | Skips in offscreen mode |
| `@pytest.mark.parallel_unsafe` | Forces serial execution |
| `@pytest.mark.shared_state_safe` | **Required** for `session_managers` |
| `@pytest.mark.skip_thread_cleanup(reason='...')` | Skip thread verification (**reason required**) |
| `@pytest.mark.no_manager_setup` | Skip manager initialization |
| `@pytest.mark.no_qt` | Skip Qt-related fixtures |
| `@pytest.mark.allows_registry_state` | Skip pollution detection |
| `@pytest.mark.real_hal` | Use real HAL (requires exhal binary) |

Categorization markers (`@pytest.mark.gui`, `@pytest.mark.headless`) have no behavioral effect.

### Fixture Selection

**Default:** Use `isolated_managers`. It's slower but always safe.

| Fixture | Scope | Use When |
|---------|-------|----------|
| `isolated_managers` | Function | **Default** - tests needing predictable state |
| `session_managers` | Session | Only with `@pytest.mark.shared_state_safe` |
| `reset_manager_state` | Function | Need clean counters without full isolation |

**Do not mix** `session_managers` and `isolated_managers` in the same module.

**`class_managers` is REMOVED** - use `isolated_managers` instead.

### HAL Fixtures

HAL is mock-by-default (100x faster). Use `@pytest.mark.real_hal` only for integration tests.

| Fixture | Behavior |
|---------|----------|
| `hal_pool` | MockHALProcessPool (or real with `--use-real-hal`) |
| `hal_compressor` | MockHALCompressor (or real with `@pytest.mark.real_hal`) |
| `mock_hal` | Always mock (patches imports) |

### Key Imports for Tests

```python
from tests.fixtures.timeouts import worker_timeout, signal_timeout, ui_timeout, LONG
from tests.fixtures.qt_waits import wait_for_condition, wait_for
from tests.infrastructure.qt_mocks import MockDialog
from tests.infrastructure.real_component_factory import RealComponentFactory
from tests.infrastructure.thread_safe_test_image import ThreadSafeTestImage
```

### Parallel Test Execution

Tests run parallel by default (`-n auto`). Use `-n 0` for debugging.

Tests are auto-serialized if they use `session_managers` or are marked `@pytest.mark.parallel_unsafe`.

## Project Architecture

```
spritepal/
├── core/                  # Business logic
│   ├── managers/          # Manager classes
│   ├── protocols/         # Protocol definitions
│   └── *.py               # Core logic
├── ui/                    # Qt UI components
│   ├── components/        # Reusable widgets
│   ├── dialogs/           # Dialog windows
│   ├── workers/           # Background workers
│   └── *.py               # Panel files
├── tests/
│   ├── fixtures/          # Test fixtures
│   └── infrastructure/    # RealComponentFactory, etc.
└── utils/                 # Shared utilities
```

### Import Rules

- **UI** imports from: `core/`, `utils/`
- **Core** imports from: `utils/`
- **Utils** imports from: stdlib only

### Manager Architecture

Use DI, never instantiate managers directly:

```python
from core.di_container import inject
from core.protocols.manager_protocols import ExtractionManagerProtocol

# Production code
extraction_mgr = inject(ExtractionManagerProtocol)

# Tests - use fixtures, not inject()
def test_extraction(isolated_managers):
    extraction_mgr = isolated_managers.extraction_manager
```

Key managers:
- `ApplicationStateManager` - session, state, settings, history
- `CoreOperationsManager` - extraction, injection, palette
- `ExtractionAdapter`/`InjectionAdapter` - legacy interface wrappers

### Key Patterns

**Resource management:**
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

**Thread safety:** Use `QMutex/QMutexLocker` for shared state, prefer signal-based waiting.

**Dialog initialization (DialogBase):**
```python
class MyDialog(DialogBase):
    def __init__(self, parent: QWidget | None = None):
        self.my_widget: QWidget | None = None  # Declare BEFORE super()
        super().__init__(parent)  # Calls _setup_ui()

    def _setup_ui(self):
        self.my_widget = QPushButton("Click me")
```

**Circular imports:** Use local imports in methods when needed.

---

*Last updated: December 19, 2025*
