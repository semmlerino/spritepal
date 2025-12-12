# Test Infrastructure Headless Compatibility

The test infrastructure has been made Qt-optional to support headless testing environments without PySide6.

## Implementation

### Environment Detection
- `environment_detection.py`: Detects PySide6 availability and headless environments
- Supports CI environments, GitHub Actions, and systems without display
- Provides comprehensive environment information for debugging

### Conditional Imports
- `__init__.py`: Uses conditional imports based on Qt availability
- Qt-dependent modules only imported when PySide6 is available
- Graceful fallback to headless implementations when Qt is not available

### Fallback Implementations
- `headless_fallbacks.py`: Provides stub implementations for Qt features
- Raises `HeadlessModeError` with helpful messages when Qt features are accessed
- Maintains the same public API for backward compatibility

## Features

### Always Available (Qt-Independent)
- `DataRepository`: Centralized test data management
- `get_environment_info()`: Environment detection information
- `is_pyside6_available()`: PySide6 availability check

### Conditionally Available (Qt-Dependent)
When PySide6 is available:
- `ApplicationFactory`: Qt application management
- `QtTestingFramework`: Qt component testing utilities  
- `RealComponentFactory`: Real Qt component instances
- All Qt testing context managers and helpers

When PySide6 is not available:
- Same imports work but raise `HeadlessModeError` with helpful messages
- Clear indication of what's needed to enable Qt features

## Usage

### Headless Environment
```python
from tests.infrastructure import DataRepository, get_environment_info

# This works - Qt-independent
repo = DataRepository()
env_info = get_environment_info()

# This raises HeadlessModeError with helpful message
from tests.infrastructure import ApplicationFactory
ApplicationFactory.get_application()  # Error with guidance
```

### Qt Environment  
```python
from tests.infrastructure import DataRepository, ApplicationFactory

# Both work when PySide6 is available
repo = DataRepository()
app = ApplicationFactory.get_application()
```

## Error Handling

### HeadlessModeError
Custom exception that provides clear guidance:
- Explains what Qt feature was accessed
- Suggests installing PySide6 and ensuring display availability
- Recommends using non-Qt testing alternatives

### Import Warnings
When PySide6 is detected but Qt modules fail to import:
- Issues RuntimeWarning with details
- Falls back to headless mode automatically
- Provides debugging information in logs

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