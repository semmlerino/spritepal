"""
Enhanced test isolation utilities for SpritePal tests.

This module provides comprehensive test isolation to prevent state leakage
between tests.
"""
from __future__ import annotations

import gc
import threading
import time
from collections.abc import Generator

import pytest
from PySide6.QtWidgets import QApplication

# Serial execution required: QApplication management, Manager registry manipulation, HAL process pool, Thread safety concerns
pytestmark = [

    pytest.mark.serial,
    pytest.mark.qt_application,
    pytest.mark.singleton,
    pytest.mark.process_pool,
    pytest.mark.thread_safety,
    pytest.mark.gui,
    pytest.mark.integration,
    pytest.mark.memory,
    pytest.mark.requires_display,
]

@pytest.fixture(autouse=True)
def ensure_complete_test_isolation() -> Generator[None, None, None]:
    """
    Ensure complete isolation between tests.
    
    This fixture:
    1. Captures initial state before test
    2. Runs the test
    3. Cleans up all resources after test
    """
    # Capture initial state
    initial_threads = set(threading.enumerate())

    # Run test
    yield

    # Clean up after test
    _cleanup_managers()
    _cleanup_hal_pool()
    _cleanup_threads(initial_threads)
    _cleanup_qt_application()
    _force_garbage_collection()

def _cleanup_managers() -> None:
    """Force cleanup all manager singletons."""
    try:
        from spritepal.core.managers.registry import ManagerRegistry

        # Use official API for test isolation
        ManagerRegistry.reset_for_tests()

        # Clear any module-level registry
        import spritepal.core.managers.registry as registry_module
        if hasattr(registry_module, '_registry'):
            registry_module._registry = None
    except ImportError:
        pass

def _cleanup_hal_pool() -> None:
    """Force reset HAL process pool singleton."""
    try:
        from spritepal.core.hal_compression import HALProcessPool

        # Force reset singleton
        if hasattr(HALProcessPool, '_instance'):
            if HALProcessPool._instance is not None:
                try:
                    HALProcessPool._instance.force_reset()
                except Exception:
                    pass
                HALProcessPool._instance = None
    except ImportError:
        pass

def _cleanup_threads(initial_threads: set) -> None:
    """Wait for test threads to finish."""
    timeout = time.time() + 5  # 5 second timeout
    current_threads = set(threading.enumerate()) - initial_threads

    for thread in current_threads:
        if thread.is_alive() and time.time() < timeout:
            try:
                thread.join(timeout=0.1)
            except Exception:
                pass

def _cleanup_qt_application() -> None:
    """Clean up Qt application instance."""
    app = QApplication.instance()
    if app:
        try:
            # Process any pending events
            app.processEvents()

            # Don't actually quit the app as it might be needed for other tests
            # Just process events to clean up
        except Exception:
            pass

def _force_garbage_collection() -> None:
    """Force garbage collection to clean up resources."""
    gc.collect()
    # Run multiple times to handle circular references
    gc.collect()
    gc.collect()
