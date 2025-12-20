"""
ApplicationFactory: Standardized Qt application setup for testing.

This factory provides consistent Qt application lifecycle management for tests,
ensuring proper parent/child relationships and avoiding Qt lifecycle bugs.
"""
from __future__ import annotations

import atexit
import os
import sys
from contextlib import contextmanager
from typing import Any

from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication


class ApplicationFactory:
    """
    Factory for creating and managing Qt applications in tests.

    Provides standardized Qt application setup that:
    - Ensures single QApplication instance per test session
    - Manages proper application lifecycle
    - Handles offscreen rendering for headless testing
    - Provides cleanup mechanisms to prevent Qt lifecycle issues
    """

    _application_instance: QApplication | None = None
    _cleanup_registered: bool = False

    @classmethod
    def get_application(cls, force_offscreen: bool = True) -> QApplication:
        """
        Get or create a QApplication instance for testing.

        Args:
            force_offscreen: Force offscreen rendering for headless testing

        Returns:
            QApplication instance suitable for testing
        """
        if cls._application_instance is None:
            cls._create_application(force_offscreen)

        return cls._application_instance

    @classmethod
    def _create_application(cls, force_offscreen: bool) -> None:
        """Create a new QApplication with proper test configuration."""
        # Check if QApplication already exists
        existing_app = QApplication.instance()
        if existing_app is not None:
            cls._application_instance = existing_app
            # Configure the existing application to have the correct test settings
            cls._configure_test_application()
            return

        # Set up offscreen rendering for headless testing
        if force_offscreen:
            os.environ["QT_QPA_PLATFORM"] = "offscreen"

        # Create application with test-friendly arguments
        test_args = [sys.argv[0], "-platform", "offscreen"] if force_offscreen else [sys.argv[0]]
        cls._application_instance = QApplication(test_args)

        # Configure application for testing
        cls._configure_test_application()

        # Register cleanup
        if not cls._cleanup_registered:
            atexit.register(cls._cleanup_application)
            cls._cleanup_registered = True

    @classmethod
    def _configure_test_application(cls) -> None:
        """Configure the application for optimal testing."""
        if cls._application_instance is None:
            return

        app = cls._application_instance

        # Prevent application from quitting when last window closes
        app.setQuitOnLastWindowClosed(False)

        # Set test-friendly application attributes
        app.setApplicationName("SpritePal-Test")
        app.setApplicationVersion("test")
        app.setOrganizationName("SpritePal-Test")

        # Process any pending events to ensure clean state
        app.processEvents()

    @classmethod
    def _cleanup_application(cls) -> None:
        """Clean up the application instance."""
        if cls._application_instance is not None:
            try:
                cls._application_instance.quit()
                cls._application_instance = None
            except Exception:
                # Ignore cleanup errors during test shutdown
                pass

    @classmethod
    def reset_application(cls) -> None:
        """
        Reset the application for a new test context.

        WARNING: Only use this in specific test scenarios that require
        a fresh application instance. Most tests should reuse the same
        application for performance.
        """
        cls._cleanup_application()
        cls._application_instance = None

    @classmethod
    def process_events(cls, timeout_ms: int = 100) -> None:
        """
        Process Qt events and wait for the specified duration.

        Args:
            timeout_ms: Time to wait while processing events (default 100ms)
        """
        if cls._application_instance:
            cls._application_instance.processEvents()
            # Use QTest.qWait to respect the timeout while processing events
            from PySide6.QtTest import QTest
            QTest.qWait(timeout_ms)  # wait-ok: explicit API for timed event processing

class QtTestContext:
    """
    Context manager for Qt testing that ensures proper setup and cleanup.

    Usage:
        with TestQtContext() as qt_context:
            app = qt_context.application
            # Test Qt components with guaranteed proper lifecycle
    """

    def __init__(self, force_offscreen: bool = True, process_events_on_exit: bool = True):
        """
        Initialize Qt test context.

        Args:
            force_offscreen: Force offscreen rendering for headless testing
            process_events_on_exit: Process events when exiting context
        """
        self.force_offscreen = force_offscreen
        self.process_events_on_exit = process_events_on_exit
        self.application: QApplication | None = None

    def __enter__(self) -> QtTestContext:
        """Enter the Qt test context."""
        self.application = ApplicationFactory.get_application(self.force_offscreen)
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Exit the Qt test context with proper cleanup."""
        if self.process_events_on_exit and self.application:
            # Process any remaining events to ensure clean state
            ApplicationFactory.process_events()

    def process_events(self, timeout_ms: int = 100) -> None:
        """Process Qt events within the context."""
        ApplicationFactory.process_events(timeout_ms)

# Convenience functions for common testing patterns
def get_test_application(force_offscreen: bool = True) -> QApplication:
    """Get a QApplication instance configured for testing."""
    return ApplicationFactory.get_application(force_offscreen)

@contextmanager
def qt_test_context(force_offscreen: bool = True):
    """Context manager for Qt testing."""
    with QtTestContext(force_offscreen) as context:
        yield context.application

def ensure_qt_application() -> QApplication:
    """
    Ensure a Qt application exists, creating one if necessary.

    This is a convenience function for tests that need to ensure
    Qt is available but don't need specific configuration.
    """
    return ApplicationFactory.get_application()

def process_qt_events(timeout_ms: int = 100) -> None:
    """Process Qt events for the current application."""
    ApplicationFactory.process_events(timeout_ms)

# Test validation functions
def validate_qt_application_state() -> dict[str, Any]:
    """
    Validate Qt application state for debugging test issues.

    Returns:
        Dictionary with Qt application state information
    """
    app = QApplication.instance()
    if app is None:
        return {"status": "no_application", "error": "No QApplication instance found"}

    return {
        "status": "ok",
        "application_name": app.applicationName(),
        "quit_on_last_window_closed": app.quitOnLastWindowClosed(),
        "platform_name": app.platformName() if hasattr(app, "platformName") else "unknown",
        "pixmap_creation_test": _test_pixmap_creation(),
    }

def _test_pixmap_creation() -> dict[str, Any]:
    """Test that Qt pixmap creation works (validates rendering setup)."""
    try:
        pixmap = QPixmap(100, 100)  # pixmap-ok: validating main thread rendering
        return {
            "success": True,
            "width": pixmap.width(),
            "height": pixmap.height(),
            "is_null": pixmap.isNull()
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }
