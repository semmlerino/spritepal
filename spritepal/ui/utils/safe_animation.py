"""
Safe animation utilities for Qt widgets.

Provides fallback behavior for animations in headless environments where
Qt graphics resources may not be available.
"""
from __future__ import annotations

import contextlib
import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from PySide6.QtCore import QEasingCurve, QObject, QPropertyAnimation
    from PySide6.QtWidgets import QWidget

def is_headless_environment() -> bool:
    """
    Detect if we're running in a headless environment.

    Checks for:
    - CI environment variables
    - Missing DISPLAY on Linux
    - QT_QPA_PLATFORM=offscreen
    - WSL environment without display

    Returns:
        True if headless environment detected
    """
    # Check for CI environments
    if os.environ.get("CI"):
        return True

    # Check for GitHub Actions
    if os.environ.get("GITHUB_ACTIONS"):
        return True

    # Check for explicit offscreen platform
    if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
        return True

    # Check for no display on Linux/WSL
    if sys.platform.startswith("linux") and not os.environ.get("DISPLAY"):
        # Additional check for WSL
        if Path("/proc/sys/fs/binfmt_misc/WSLInterop").exists():
            return True
        return True

    # Try to detect Qt screen availability
    try:
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        if app:
            # Check if we can get screen info
            qapp = cast(QApplication, app)
            if not qapp.primaryScreen():
                return True
            # Check if screen geometry is valid
            screen = qapp.primaryScreen()
            if screen and (screen.geometry().width() == 0 or screen.geometry().height() == 0):
                return True
    except Exception:
        # If we can't even check, assume headless
        return True

    return False

class SafeAnimation:
    """
    Safe wrapper for QPropertyAnimation that falls back to instant changes in headless mode.

    This class provides the same interface as QPropertyAnimation but automatically
    detects headless environments and applies property changes instantly without
    animation when graphics resources are unavailable.
    """

    def __init__(self, target: QObject | None = None, property_name: bytes | None = None):
        """
        Initialize safe animation wrapper.

        Args:
            target: The QObject to animate
            property_name: The property to animate (as bytes)
        """
        self._target = target
        self._property_name = property_name
        self._start_value = None
        self._end_value = None
        self._duration = 250
        self._is_headless = is_headless_environment()
        self._animation: QPropertyAnimation | None = None
        self._finished_callbacks: list[Callable[..., Any]] = []
        self._value_changed_callbacks: list[Callable[..., Any]] = []

        # Only create real animation if not headless
        if not self._is_headless and target and property_name:
            try:
                from PySide6.QtCore import QPropertyAnimation
                self._animation = QPropertyAnimation(target, property_name)
            except Exception:
                # Fall back to headless mode if animation creation fails
                self._is_headless = True
                self._animation = None

    def setDuration(self, duration: int) -> None:
        """Set animation duration (ignored in headless mode)."""
        self._duration = duration
        if self._animation:
            self._animation.setDuration(duration)

    def setStartValue(self, value: Any) -> None:
        """Set start value for animation."""
        self._start_value = value
        if self._animation:
            self._animation.setStartValue(value)

    def setEndValue(self, value: Any) -> None:
        """Set end value for animation."""
        self._end_value = value
        if self._animation:
            self._animation.setEndValue(value)

    def setEasingCurve(self, curve: QEasingCurve.Type) -> None:
        """Set easing curve (ignored in headless mode)."""
        if self._animation:
            self._animation.setEasingCurve(curve)

    def start(self) -> None:
        """
        Start the animation or apply changes instantly in headless mode.
        """
        if self._animation:
            # Use real animation
            self._animation.start()
        elif self._target and self._property_name and self._end_value is not None:
            # Instant property change in headless mode
            # _property_name is always bytes when not None
            property_name = self._property_name.decode()

            # Apply the end value directly
            if hasattr(self._target, property_name):
                setter_name = f"set{property_name[0].upper()}{property_name[1:]}"
                if hasattr(self._target, setter_name):
                    setter = getattr(self._target, setter_name)
                    setter(self._end_value)
                else:
                    # Try direct property assignment
                    setattr(self._target, property_name, self._end_value)

            # Trigger value changed callbacks with end value
            for callback in self._value_changed_callbacks:
                with contextlib.suppress(Exception):
                    callback(self._end_value)

            # Trigger finished callbacks
            for callback in self._finished_callbacks:
                with contextlib.suppress(Exception):
                    callback()

    def stop(self) -> None:
        """Stop the animation."""
        if self._animation:
            self._animation.stop()

    @property
    def valueChanged(self):
        """Get value changed signal or mock."""
        if self._animation:
            return self._animation.valueChanged
        # Return a mock signal interface
        return self._MockSignal(self._value_changed_callbacks)

    @property
    def finished(self):
        """Get finished signal or mock."""
        if self._animation:
            return self._animation.finished
        # Return a mock signal interface
        return self._MockSignal(self._finished_callbacks)

    class _MockSignal:
        """Mock signal for headless mode."""

        def __init__(self, callbacks: list[Callable[..., Any]]):
            self._callbacks = callbacks

        def connect(self, callback: Callable[..., Any]) -> None:
            """Connect a callback."""
            if callback not in self._callbacks:
                self._callbacks.append(callback)

        def disconnect(self, callback: Callable[..., Any]) -> None:
            """Disconnect a callback."""
            if callback in self._callbacks:
                self._callbacks.remove(callback)

def create_safe_animation(target: QWidget | None = None,
                         property_name: bytes | None = None) -> SafeAnimation:
    """
    Factory function to create a safe animation.

    Args:
        target: The widget to animate
        property_name: The property to animate

    Returns:
        SafeAnimation instance that works in both normal and headless modes
    """
    return SafeAnimation(target, property_name)
