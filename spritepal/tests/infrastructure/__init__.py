"""
Testing Infrastructure for SpritePal

This module provides testing infrastructure including:

- ApplicationFactory: Standardized Qt application setup
- RealComponentFactory: Real manager instances with proper Qt parents
- DataRepository: Centralized test data management
- ThreadSafeTestImage: Thread-safe QImage for worker tests
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
        from .real_component_factory import RealComponentFactory
        from .thread_safe_test_image import ThreadSafeTestImage

        # Add Qt-dependent exports
        __all__.extend([
            "RealComponentFactory",
            "ApplicationFactory",
            "QtTestContext",
            "qt_test_context",
            "ThreadSafeTestImage",
        ])

    except ImportError as e:
        # PySide6 is available but Qt modules failed to import
        import warnings
        warnings.warn(
            f"PySide6 is available but Qt modules failed to import: {e}.",
            RuntimeWarning, stacklevel=2
        )
