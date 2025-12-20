"""
Testing Infrastructure for SpritePal

This module provides comprehensive testing infrastructure to support
real Qt testing and reduce over-mocking patterns. It includes:

- ApplicationFactory: Standardized Qt application setup (Qt-dependent)
- RealComponentFactory: Real manager instances with proper Qt parents (Qt-dependent)
- DataRepository: Centralized test data management (Qt-independent)
- QtTestingFramework: Standardized patterns for Qt component testing (Qt-dependent)

The infrastructure is designed to:
1. Enable real Qt testing instead of extensive mocking
2. Catch architectural bugs (especially Qt lifecycle issues)
3. Provide maintainable and understandable test patterns
4. Support both fast unit tests and comprehensive integration tests
5. Work in both Qt and headless environments

In headless environments (without PySide6), Qt-dependent features will raise
HeadlessModeError with helpful messages, while Qt-independent features remain available.
"""
from __future__ import annotations

from .data_repository import DataRepository
from .environment_detection import get_environment_info, is_pyside6_available
from .test_signal import TestSignal, TestSignalBlocker

# Always available (Qt-independent)
__all__ = [
    "DataRepository",
    "get_environment_info",
    "is_pyside6_available",
    "TestSignal",
    "TestSignalBlocker",
]

# Conditional imports based on Qt availability
if is_pyside6_available():
    try:
        from .qt_application_factory import (
            ApplicationFactory,
            QtTestContext,
            qt_test_context,
        )
        from .qt_testing_framework import (
            QtTestingFramework,
            qt_dialog_test,
            qt_widget_test,
            qt_worker_test,
            validate_qt_object_lifecycle,
        )
        from .real_component_factory import RealComponentFactory

        # Add Qt-dependent exports
        __all__.extend([
            "QtTestingFramework",
            "RealComponentFactory",
            "ApplicationFactory",
            "QtTestContext",
            "qt_dialog_test",
            "qt_test_context",
            "qt_widget_test",
            "qt_worker_test",
            "validate_qt_object_lifecycle",
        ])

    except ImportError as e:
        # PySide6 is available but Qt modules failed to import
        # This can happen in some CI environments
        import warnings
        warnings.warn(
            f"PySide6 is available but Qt modules failed to import: {e}. "
            f"Falling back to headless mode.",
            RuntimeWarning, stacklevel=2
        )
        # Override detection function locally
        def _override_detection():
            return False
        is_pyside6_available = _override_detection

# Provide fallback implementations for headless environments
if not is_pyside6_available():
    from .headless_fallbacks import (
        HeadlessApplicationFactory as ApplicationFactory,
        HeadlessQtTestContext as QtTestContext,
        HeadlessQtTestingFramework as QtTestingFramework,
        HeadlessRealComponentFactory as RealComponentFactory,
        headless_qt_dialog_test as qt_dialog_test,
        headless_qt_test_context as qt_test_context,
        headless_qt_widget_test as qt_widget_test,
        headless_qt_worker_test as qt_worker_test,
        headless_validate_qt_object_lifecycle as validate_qt_object_lifecycle,
    )

    # Add fallback exports (these will raise HeadlessModeError when used)
    __all__.extend([
        "QtTestingFramework",
        "RealComponentFactory",
        "ApplicationFactory",
        "QtTestContext",
        "qt_dialog_test",
        "qt_test_context",
        "qt_widget_test",
        "qt_worker_test",
        "validate_qt_object_lifecycle",
    ])

    # Emit warning that headless stubs are active
    # This helps catch environments where tests might silently skip Qt components
    import warnings
    warnings.warn(
        "Headless stubs are active - PySide6 is not available. "
        "Any test using Qt components will fail at runtime with HeadlessModeError. "
        "Install PySide6 for proper test execution: uv sync --extra dev",
        RuntimeWarning,
        stacklevel=2,
    )
