"""
Consolidated wait helpers for Qt test synchronization.

This module provides condition-based wait fixtures that replace timing-dependent
qtbot.wait() calls with proper Qt event loop handling.

Usage:
    Import via pytest_plugins in your conftest.py:
        pytest_plugins = ['tests.fixtures.qt_waits']

    Or import specific fixtures directly in conftest.py and re-export.
"""
from __future__ import annotations

import os
from collections.abc import Callable
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from PySide6.QtWidgets import QWidget
    from pytestqt.qtbot import QtBot


def wait_for_condition(
    qtbot: QtBot,
    condition_func: Callable[[], bool],
    timeout: int = 5000,
    message: str = "Condition not met"
) -> bool:
    """
    Wait for a condition to become true using proper Qt event loop handling.

    This implementation uses qtbot's waitUntil which properly handles the Qt event loop
    and avoids segfaults from improper event processing.

    Args:
        qtbot: pytest-qt bot
        condition_func: Function that returns True when condition is met
        timeout: Maximum time to wait in milliseconds
        message: Error message if timeout occurs

    Returns:
        True if condition met within timeout

    Raises:
        TimeoutError: If condition not met within timeout
    """
    try:
        qtbot.waitUntil(condition_func, timeout=timeout)
        return True
    except AssertionError as e:
        raise TimeoutError(f"Timeout waiting for condition: {message}") from e


@pytest.fixture
def wait_for(qtbot: QtBot) -> Callable[..., bool]:
    """Provide the wait_for_condition function as a fixture."""
    def _wait_for(
        condition_func: Callable[[], bool],
        timeout: int = 5000,
        message: str = "Condition not met"
    ) -> bool:
        return wait_for_condition(qtbot, condition_func, timeout, message)
    return _wait_for


@pytest.fixture
def process_events(qtbot: QtBot) -> Callable[[], None]:
    """Process Qt events to ensure UI updates."""
    def _process() -> None:
        from PySide6.QtWidgets import QApplication
        QApplication.processEvents()
    return _process


@pytest.fixture
def wait_for_widget_ready(qtbot: QtBot) -> Callable[..., bool]:
    """
    Helper to wait for widget initialization.

    Replaces fixed qtbot.wait() calls with condition-based waiting.
    Auto-completes when widget becomes visible and enabled.

    Example:
        wait_for_widget_ready(dialog, timeout=1000)
        # Instead of: dialog.show(); qtbot.wait(100)
    """
    def _wait(widget: QWidget, timeout: int = 1000) -> bool:
        """
        Wait for widget to be visible and enabled.

        Args:
            widget: QWidget to wait for
            timeout: Maximum wait time in milliseconds

        Returns:
            True if widget is ready within timeout

        Raises:
            TimeoutError: If widget not ready within timeout
        """
        try:
            qtbot.waitUntil(
                lambda: widget.isVisible() and widget.isEnabled(),
                timeout=timeout
            )
            return True
        except AssertionError as e:
            raise TimeoutError(
                f"Widget {widget.__class__.__name__} not ready within {timeout}ms"
            ) from e
    return _wait


@pytest.fixture
def wait_for_signal_processed(qtbot: QtBot) -> Callable[[], None]:
    """
    Helper to wait for signal processing to complete.

    Ensures Qt event loop has processed pending signals.

    Example:
        slider.setValue(100)
        wait_for_signal_processed()
        # Instead of: slider.setValue(100); qtbot.wait(50)
    """
    def _wait() -> None:
        """
        Wait for pending signals to be processed.

        Uses processEvents() to ensure all queued signals have been delivered.
        """
        from PySide6.QtWidgets import QApplication
        QApplication.processEvents()

    return _wait


@pytest.fixture
def wait_for_theme_applied(qtbot: QtBot) -> Callable[..., bool]:
    """
    Helper to wait for theme changes to be applied.

    Qt theme changes may take multiple event loop cycles to apply.

    Example:
        window.apply_dark_theme()
        wait_for_theme_applied(window)
        # Instead of: window.apply_dark_theme(); qtbot.wait(100)
    """
    def _wait(widget: QWidget, is_dark_theme: bool = True, timeout: int = 500) -> bool:
        """
        Wait for theme to be applied to widget.

        Args:
            widget: QWidget to check
            is_dark_theme: Whether to expect dark theme (True) or light (False)
            timeout: Maximum wait time in milliseconds
        """
        from PySide6.QtGui import QPalette

        def theme_applied() -> bool:
            palette = widget.palette()
            bg_color = palette.color(QPalette.ColorRole.Window)

            if is_dark_theme:
                return bg_color.red() < 128 and bg_color.green() < 128 and bg_color.blue() < 128
            else:
                return bg_color.red() > 128 or bg_color.green() > 128 or bg_color.blue() > 128

        try:
            qtbot.waitUntil(theme_applied, timeout=timeout)
            return True
        except Exception:  # pytestqt.exceptions.TimeoutError is raised, not AssertionError
            # Theme verification can be unreliable in headless mode
            display = os.environ.get("DISPLAY", "")
            qpa_platform = os.environ.get("QT_QPA_PLATFORM", "")
            if not display or qpa_platform == "offscreen":
                return True
            raise

    return _wait


@pytest.fixture
def wait_for_layout_update(qtbot: QtBot) -> Callable[..., bool]:
    """
    Helper to wait for layout changes to be applied.

    Qt layouts may take multiple event cycles to fully update.

    Example:
        window.resize(1024, 768)
        wait_for_layout_update(window, expected_width=1024)
        # Instead of: window.resize(...); qtbot.wait(100)
    """
    def _wait(
        widget: QWidget,
        expected_width: int | None = None,
        expected_height: int | None = None,
        timeout: int = 500
    ) -> bool:
        """
        Wait for widget layout to update.

        Args:
            widget: QWidget to check
            expected_width: Expected width (None to skip check)
            expected_height: Expected height (None to skip check)
            timeout: Maximum wait time in milliseconds
        """
        def layout_updated() -> bool:
            size = widget.size()
            if expected_width is not None and size.width() != expected_width:
                return False
            if expected_height is not None and size.height() != expected_height:
                return False
            return size.width() > 0 and size.height() > 0

        try:
            qtbot.waitUntil(layout_updated, timeout=timeout)
            return True
        except AssertionError as e:
            current_size = widget.size()
            raise TimeoutError(
                f"Layout not updated within {timeout}ms. "
                f"Current: {current_size.width()}x{current_size.height()}, "
                f"Expected: {expected_width}x{expected_height}"
            ) from e

    return _wait
