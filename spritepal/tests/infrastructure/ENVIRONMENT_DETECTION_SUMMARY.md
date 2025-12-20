# Environment Detection Module

## Overview

Minimal environment detection for the SpritePal test suite. Qt offscreen mode is set in `tests/conftest.py` via `os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')`.

## Module: `tests/infrastructure/environment_detection.py`

### Detection Functions

| Function | Description |
|----------|-------------|
| `get_environment_info()` | Returns cached `EnvironmentInfo` singleton |
| `is_headless_environment()` | True if offscreen, WSL, or no DISPLAY |
| `is_ci_environment()` | True if `CI` env var is set |
| `is_wsl_environment()` | True if running in WSL/WSL2 |
| `is_docker_environment()` | True if `/.dockerenv` exists |
| `has_display_available()` | Inverse of `is_headless_environment()` |
| `is_pyside6_available()` | True if PySide6 can be imported |

### Test Decorators

| Decorator | Effect |
|-----------|--------|
| `@skip_if_wsl` | Skip in WSL environments |
| `@skip_if_no_display` | Skip if no display available |
| `@skip_in_ci` | Skip in CI environments |
| `@requires_display` | Alias for `@skip_if_no_display` |
| `@requires_real_qt` | Skip if PySide6 unavailable |
| `@headless_safe` | No-op marker (documentation only) |
| `@ci_safe` | No-op marker (documentation only) |

### EnvironmentInfo Properties

```python
info = get_environment_info()
info.platform          # sys.platform
info.is_wsl            # WSL detection
info.is_headless       # Headless environment
info.pyside6_available # PySide6 available
info.is_ci             # CI environment
info.is_docker         # Docker container
info.has_display       # Not headless
```

## Usage

```python
from tests.infrastructure.environment_detection import (
    is_headless_environment,
    skip_if_wsl,
    requires_display,
)

# Check environment
if is_headless_environment():
    print("Running in headless mode")

# Skip test in WSL
@skip_if_wsl
def test_requires_native_display():
    pass

# Skip if no display
@requires_display
def test_gui_rendering():
    pass
```

## Notes

- Qt offscreen mode is configured in `tests/conftest.py`, not this module
- The `configure_qt_for_environment()` function is a no-op
- For display-dependent tests, prefer `@pytest.mark.requires_display` marker
