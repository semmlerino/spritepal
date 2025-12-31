"""Memory management helpers for Qt tests.

Provides utilities for detecting memory leaks in Qt applications.
"""

from __future__ import annotations

import gc
from collections.abc import Generator
from contextlib import contextmanager
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PySide6.QtWidgets import QApplication


class MemoryHelper:
    """Helper class for memory management in Qt tests."""

    @staticmethod
    def get_widget_count() -> int:
        """Get count of all QWidget instances."""
        from PySide6.QtWidgets import QWidget

        return len([obj for obj in gc.get_objects() if isinstance(obj, QWidget)])

    @staticmethod
    def get_object_count(obj_type: type) -> int:
        """Get count of objects of specific type."""
        return len([obj for obj in gc.get_objects() if isinstance(obj, obj_type)])

    @staticmethod
    @contextmanager
    def assert_no_leak(obj_type: type, max_increase: int = 0) -> Generator[None, None, None]:
        """Context manager to assert no memory leak of specific object type.

        Args:
            obj_type: Object type to monitor
            max_increase: Maximum allowed increase in object count

        Example:
            with MemoryHelper.assert_no_leak(QWidget):
                widget = QWidget()
                widget.deleteLater()
        """
        from PySide6.QtWidgets import QApplication

        gc.collect()
        initial_count = MemoryHelper.get_object_count(obj_type)

        try:
            yield
        finally:
            # Process events to allow deleteLater to take effect
            app = QApplication.instance()
            if app:
                app.processEvents()
            gc.collect()

            final_count = MemoryHelper.get_object_count(obj_type)
            increase = final_count - initial_count

            assert increase <= max_increase, (
                f"Memory leak detected: {increase} {obj_type.__name__} objects leaked (max allowed: {max_increase})"
            )
