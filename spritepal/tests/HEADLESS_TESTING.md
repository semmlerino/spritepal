# Headless Testing Guide for SpritePal

This guide explains how to run SpritePal tests in headless environments (CI/CD, servers without display).

## Setup

Tests are configured to run in headless mode using Qt's offscreen platform:
- `tests/conftest.py` sets `QT_QPA_PLATFORM=offscreen` via `os.environ.setdefault`
- GUI tests marked `@pytest.mark.gui` run with offscreen backend (not skipped)
- Tests marked `@pytest.mark.requires_display` are skipped when offscreen
- Tests that need Qt but have issues will **fail loudly** with clear error messages

## Test Behavior

### Real Qt with Offscreen Mode
SpritePal tests use **real Qt components** with the offscreen platform plugin.
This means:
- QApplication works in headless environments
- Qt widgets can be created and tested
- Signal/slot connections work correctly
- No mock Qt modules are used

### Test Categories
1. **Tests without Qt dependencies**: Run normally, no special setup needed
2. **Tests with Qt dependencies**: Work via offscreen mode
3. **GUI tests (@pytest.mark.gui)**: Run with offscreen backend, no display required

## Running Tests

### Using uv (recommended)
```bash
# All tests
uv run pytest tests/ -v

# Non-GUI tests only
uv run pytest tests/ -v -k "not gui"

# With verbose environment info
PYTEST_VERBOSE_ENVIRONMENT=1 uv run pytest tests/ -v
```

### Direct pytest
```bash
# All tests (offscreen mode is set in pytest.ini)
python -m pytest tests/ -v

# Override platform if needed
QT_QPA_PLATFORM=offscreen python -m pytest tests/ -v
```

## Test Markers

| Marker | Behavior in Headless (offscreen) |
|--------|---------------------|
| `@pytest.mark.gui` | Runs (with offscreen backend) |
| `@pytest.mark.headless` | Runs |
| `@pytest.mark.requires_display` | Skipped |
| (no marker) | Runs with offscreen |

## CI/CD Integration

For GitHub Actions or similar:
```yaml
- name: Run tests
  run: |
    uv run pytest tests/ -v --tb=short
```

No additional environment variables needed - `tests/conftest.py` configures offscreen mode.

## Troubleshooting

### Test fails with "Qt not available"
- Ensure PySide6 is installed: `uv sync --extra dev`
- The test may incorrectly require display - mark it @pytest.mark.gui

### Test fails with "Failed to create QApplication"
- QT_QPA_PLATFORM=offscreen should be set (done automatically in tests/conftest.py)
- Check that no conflicting Qt environment variables are set

### Test passes locally but fails in CI
- Local environment may have display access
- Add @pytest.mark.gui to tests that truly require a display
- Or fix the test to work with offscreen mode

## Implementation Details

### No Mock Fallbacks
Previous versions would silently mock Qt in headless environments.
Now tests **fail loudly** if they:
- Need Qt but aren't marked appropriately
- Have Qt import errors
- Can't create QApplication

This ensures tests are honest about their requirements.

### Fixture Behavior
- `qt_app`: Creates real QApplication (with offscreen)
- `safe_qtbot`: Returns real pytest-qt qtbot
- `qtbot`: Standard pytest-qt fixture (works with offscreen)

All fixtures fail with clear error messages if Qt is unavailable.
