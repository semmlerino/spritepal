# Test Infrastructure Headless Compatibility

> **IMPORTANT: PySide6 is Required for Running Tests**
>
> The test infrastructure uses conditional imports for headless compatibility:
>
> - Qt-independent APIs (DataRepository, signals, environment detection) always available
> - Qt-dependent APIs (RealComponentFactory, ThreadSafeTestImage) require PySide6
> - This is **intentional** - tests fail loudly without dependencies, not silently pass
>
> **For running tests:** PySide6 is **required**: `uv sync --extra dev`
>
> **For static analysis only** (no tests):
> - basedpyright and ruff can analyze code without PySide6
> - Module loading succeeds due to conditional imports
>
> If you see `ImportError` on Qt infrastructure imports, install PySide6 with `uv sync --extra dev`

The test infrastructure has conditional imports to support headless static analysis environments.

## Implementation

### Environment Detection
- `environment_detection.py`: Detects PySide6 availability and headless environments
- Supports CI environments, GitHub Actions, and systems without display
- Provides comprehensive environment information for debugging

### Conditional Import Strategy
- `__init__.py`: Uses conditional imports based on `is_pyside6_available()` check
- Qt-dependent modules only imported when PySide6 is available
- **When PySide6 is unavailable**: Attempting to import Qt-dependent APIs raises `ImportError` or `RuntimeWarning`
- Real test infrastructure is only available when PySide6 is installed
- No fallback stubs exist - this is intentional to fail loudly, not silently

## Features

### Always Available (Qt-Independent)
- `DataRepository`: Centralized test data management
- `get_environment_info()`: Environment detection information
- `is_pyside6_available()`: PySide6 availability check
- `TestSignal` and `TestSignalBlocker`: Safe signal utilities for testing

### Conditionally Available (Qt-Dependent)
When PySide6 is available:
- `RealComponentFactory`: Real manager instances and Qt component factories
- `ThreadSafeTestImage`: Thread-safe QImage for worker thread tests
- `WorkerThreadAdapter` and `run_worker_to_completion()`: Background worker utilities
- Helper functions: `create_main_window()`, `create_extraction_worker()`, `create_injection_worker()`, `create_tile_renderer()`

When PySide6 is not available:
- Qt-dependent exports are not added to `__all__`
- Attempting to import them raises `ImportError` or `RuntimeWarning`
- Use only Qt-independent APIs in headless environments

## Usage

### Headless Environment (PySide6 not available)
```python
from tests.infrastructure import DataRepository, get_environment_info, TestSignal

# These work - Qt-independent
repo = DataRepository()
env_info = get_environment_info()
signal = TestSignal()

# These raise ImportError or RuntimeWarning
# (PySide6 not installed)
# from tests.infrastructure import RealComponentFactory  # ❌ ImportError
# from tests.infrastructure import ThreadSafeTestImage  # ❌ ImportError
```

### Qt Environment (PySide6 available)
```python
from tests.infrastructure import DataRepository, RealComponentFactory, ThreadSafeTestImage
from core.app_context import get_app_context

# All work when PySide6 is available
repo = DataRepository()
factory = RealComponentFactory()
test_image = ThreadSafeTestImage(32, 32)

# Create components for testing
with factory:
    extraction_worker = factory.create_extraction_worker()
    main_window = factory.create_main_window()

# Access managers via app_context (preferred)
app_context = get_app_context()
state_manager = app_context.application_state_manager
operations_manager = app_context.core_operations_manager
```

## Error Handling

### ImportError (Missing PySide6)
When attempting to import Qt-dependent infrastructure without PySide6:
- `ImportError` is raised when trying to import conditional modules
- Clear indication that PySide6 is required for those features
- Solution: Install PySide6 with `uv sync --extra dev`

### RuntimeWarning (PySide6 Available but Qt Import Failed)
When PySide6 is installed but Qt modules fail to import:
- `RuntimeWarning` is issued with details about the import failure
- Qt-dependent exports are not added to `__all__`
- Suggests checking display availability or Qt library issues
- Use only Qt-independent APIs as fallback

## Benefits

1. **CI/CD Compatibility**: Tests can run in headless CI environments
2. **Optional Dependencies**: PySide6 not required for basic testing
3. **Clear Error Messages**: Helpful guidance when Qt features are needed
4. **Backward Compatibility**: Existing code continues to work unchanged
5. **Development Flexibility**: Mix of Qt and non-Qt test approaches

## Testing

The implementation has been verified to:
- Import successfully without PySide6 installed
- Provide Qt-independent functionality in headless mode
- Raise appropriate errors for Qt-dependent features
- Maintain full functionality when Qt is available
- Support environment detection and debugging

## Migration

No code changes required for existing tests. The infrastructure automatically detects the environment and provides appropriate functionality or error messages.