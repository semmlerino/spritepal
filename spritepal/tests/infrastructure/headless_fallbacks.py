"""
Fallback implementations for Qt-dependent functionality in headless environments.

These classes provide stub implementations that raise helpful error messages
when Qt functionality is accessed in headless mode.
"""
from __future__ import annotations

from typing import Any

from .environment_detection import HeadlessModeError


class HeadlessApplicationFactory:
    """Fallback for ApplicationFactory in headless environments."""

    @classmethod
    def get_application(cls, force_offscreen: bool = True) -> None:
        raise HeadlessModeError("ApplicationFactory")

    @classmethod
    def reset_application(cls) -> None:
        raise HeadlessModeError("ApplicationFactory.reset_application")

    @classmethod
    def process_events(cls, timeout_ms: int = 100) -> None:
        raise HeadlessModeError("ApplicationFactory.process_events")

class HeadlessQtTestContext:
    """Fallback for QtTestContext in headless environments."""

    def __init__(self, force_offscreen: bool = True, process_events_on_exit: bool = True):
        pass

    def __enter__(self) -> HeadlessQtTestContext:
        raise HeadlessModeError("QtTestContext")

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        pass

class HeadlessQtTestingFramework:
    """Fallback for QtTestingFramework in headless environments."""

    def __init__(self, qt_app: Any | None = None):
        raise HeadlessModeError("QtTestingFramework")

class HeadlessRealManagerFixtureFactory:
    """Fallback for RealManagerFixtureFactory in headless environments."""

    def __init__(self, qt_parent: Any = None, manager_factory: Any = None):
        raise HeadlessModeError("RealManagerFixtureFactory")

# Fallback functions
def headless_qt_test_context(force_offscreen: bool = True):
    """Fallback for qt_test_context function."""
    raise HeadlessModeError("qt_test_context")

def headless_qt_dialog_test(dialog_class: type, *args, **kwargs):
    """Fallback for qt_dialog_test function."""
    raise HeadlessModeError("qt_dialog_test")

def headless_qt_widget_test(widget_class: type, *args, **kwargs):
    """Fallback for qt_widget_test function."""
    raise HeadlessModeError("qt_widget_test")

def headless_qt_worker_test(worker_class: type, *args, **kwargs):
    """Fallback for qt_worker_test function."""
    raise HeadlessModeError("qt_worker_test")

def headless_validate_qt_object_lifecycle(obj: Any) -> dict[str, Any]:
    """Fallback for validate_qt_object_lifecycle function."""
    raise HeadlessModeError("validate_qt_object_lifecycle")
