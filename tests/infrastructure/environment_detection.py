"""
Minimal environment detection for SpritePal test suite.

Qt offscreen mode is set in tests/conftest.py via:
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
"""

from __future__ import annotations

import os
import sys
from collections.abc import Callable
from typing import TypeVar

import pytest

F = TypeVar("F", bound=Callable[..., object])


class EnvironmentInfo:
    """Simple environment info container."""

    def __init__(self) -> None:
        self.platform = sys.platform
        self.is_wsl = self._detect_wsl()
        self.is_offscreen = self._detect_offscreen()
        self.pyside6_available = self._detect_pyside6()
        self.is_headless = self._detect_headless()

    def _detect_wsl(self) -> bool:
        """Fast WSL detection via filesystem."""
        if sys.platform != "linux":
            return False
        try:
            uname = os.uname().release.lower()
            return "microsoft" in uname or "wsl" in uname
        except (OSError, AttributeError):
            return False

    def _detect_offscreen(self) -> bool:
        """True if using Qt offscreen mode (no display but Qt works).

        Offscreen mode is NOT headless - Qt works fully, just without
        a physical display. Event loops run, signals fire, deleteLater() works.
        """
        return os.environ.get("QT_QPA_PLATFORM") == "offscreen"

    def _detect_headless(self) -> bool:
        """True if Qt is completely unavailable (no GUI possible at all).

        Note: Offscreen mode is NOT headless - Qt works fine in offscreen mode.
        Use is_offscreen for the distinction between display vs no display.
        """
        # PySide6 not available = truly headless
        if not self.pyside6_available:
            return True
        # WSL without display AND not using offscreen = headless
        if self.is_wsl and not self.is_offscreen and not os.environ.get("DISPLAY"):
            return True
        # Linux without display AND not using offscreen = headless
        if sys.platform.startswith("linux") and not self.is_offscreen and not os.environ.get("DISPLAY"):
            return True
        return False

    def _detect_pyside6(self) -> bool:
        """Check if PySide6 is available."""
        try:
            import PySide6.QtCore  # noqa: F401

            return True
        except ImportError:
            return False


# Global singleton
_environment_info: EnvironmentInfo | None = None


def get_environment_info() -> EnvironmentInfo:
    """Get cached environment info."""
    global _environment_info
    if _environment_info is None:
        _environment_info = EnvironmentInfo()
    return _environment_info


def is_wsl_environment() -> bool:
    """Check if running in WSL."""
    return get_environment_info().is_wsl


def is_pyside6_available() -> bool:
    """Check if PySide6 is available."""
    return get_environment_info().pyside6_available


def skip_if_wsl(func_or_reason: F | str | None = None) -> F | Callable[[F], F]:
    """Skip test if running in WSL.

    Can be used as:
        @skip_if_wsl
        def test_foo(): ...

        @skip_if_wsl("Custom reason")
        def test_bar(): ...
    """
    default_reason = "Test skipped in WSL environment"

    if func_or_reason is None:
        # Called as @skip_if_wsl()
        def decorator(func: F) -> F:
            return pytest.mark.skipif(is_wsl_environment(), reason=default_reason)(func)  # type: ignore[return-value]

        return decorator  # type: ignore[return-value]
    elif callable(func_or_reason):
        # Called as @skip_if_wsl (no parentheses)
        return pytest.mark.skipif(is_wsl_environment(), reason=default_reason)(func_or_reason)  # type: ignore[return-value]
    else:
        # Called as @skip_if_wsl("reason")
        reason = func_or_reason

        def decorator(func: F) -> F:
            return pytest.mark.skipif(is_wsl_environment(), reason=reason)(func)  # type: ignore[return-value]

        return decorator  # type: ignore[return-value]


def requires_real_qt(func: F) -> F:
    """Skip test if real Qt threading isn't available."""
    info = get_environment_info()
    should_skip = not info.pyside6_available
    return pytest.mark.skipif(should_skip, reason="Test requires real Qt (PySide6)")(func)  # type: ignore[return-value]
