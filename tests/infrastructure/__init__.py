"""
Testing Infrastructure for SpritePal

This module provides testing infrastructure including:

- RealComponentFactory: Real manager instances with proper Qt parents
- DataRepository: Centralized test data management
- ThreadSafeTestImage: Thread-safe QImage for worker tests
- test_helpers: Simple helper functions for common test needs
"""

from __future__ import annotations

from .data_repository import DataRepository
from .environment_detection import get_environment_info, is_pyside6_available
from .mesen_mocks import (
    MockBoundingBox,
    MockCaptureResult,
    MockOAMEntry,
    MockTileData,
    create_simple_capture,
)
from .qt_pixmap_guard import install_qpixmap_guard
from .test_signal import TestSignal, TestSignalBlocker

# Always available (Qt-independent)
__all__ = [
    "DataRepository",
    "get_environment_info",
    "install_qpixmap_guard",
    "is_pyside6_available",
    "TestSignal",
    "TestSignalBlocker",
    # Mesen capture result mocks
    "MockBoundingBox",
    "MockCaptureResult",
    "MockOAMEntry",
    "MockTileData",
    "create_simple_capture",
]

# Conditional imports based on Qt availability
if is_pyside6_available():
    try:
        from .real_component_factory import RealComponentFactory
        from .test_helpers import (
            create_extraction_worker,
            create_injection_worker,
            create_main_window,
            create_tile_renderer,
        )
        from .thread_safe_test_image import ThreadSafeTestImage
        from .worker_thread_adapter import WorkerThreadAdapter, run_worker_to_completion

        # Add Qt-dependent exports
        __all__.extend(
            [
                "RealComponentFactory",
                "ThreadSafeTestImage",
                "WorkerThreadAdapter",
                "run_worker_to_completion",
                "create_main_window",
                "create_extraction_worker",
                "create_injection_worker",
                "create_tile_renderer",
            ]
        )

    except ImportError as e:
        # PySide6 is available but Qt modules failed to import
        import warnings

        warnings.warn(f"PySide6 is available but Qt modules failed to import: {e}.", RuntimeWarning, stacklevel=2)
