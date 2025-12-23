"""
Minimal environment detection for SpritePal test suite.

This module provides basic environment detection. Qt offscreen mode is set
in tests/conftest.py via os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen').
"""

from __future__ import annotations

import functools
import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, ParamSpec, TypeVar

import pytest

F = TypeVar('F', bound=Callable[..., Any])
P = ParamSpec('P')
R = TypeVar('R')


class EnvironmentInfo:
    """Simple environment info container."""

    def __init__(self) -> None:
        self.platform = sys.platform
        self.is_wsl = self._detect_wsl()
        self.is_headless = self._detect_headless()
        self.pyside6_available = self._detect_pyside6()

    def _detect_wsl(self) -> bool:
        """Fast WSL detection via filesystem."""
        if sys.platform != 'linux':
            return False
        try:
            uname = os.uname().release.lower()
            return 'microsoft' in uname or 'wsl' in uname
        except (OSError, AttributeError):
            return False

    def _detect_headless(self) -> bool:
        """Simple headless detection."""
        if os.environ.get('QT_QPA_PLATFORM') == 'offscreen':
            return True
        if self.is_wsl:
            return True
        if sys.platform.startswith('linux') and not os.environ.get('DISPLAY'):
            return True
        return False

    def _detect_pyside6(self) -> bool:
        """Check if PySide6 is available."""
        try:
            import PySide6.QtCore  # noqa: F401
            return True
        except ImportError:
            return False

    # Properties for backward compatibility
    @property
    def is_ci(self) -> bool:
        return bool(os.environ.get('CI'))

    @property
    def is_docker(self) -> bool:
        return Path('/.dockerenv').exists()

    @property
    def has_display(self) -> bool:
        return not self.is_headless

    @property
    def xvfb_available(self) -> bool:
        import shutil
        return shutil.which('Xvfb') is not None

    @property
    def qt_info(self) -> dict[str, Any]:
        return {'available': self.pyside6_available}

    @property
    def ci_system(self) -> str | None:
        if os.environ.get('GITHUB_ACTIONS'):
            return 'GitHub Actions'
        return 'CI' if self.is_ci else None

    @property
    def recommended_qt_platform(self) -> str | None:
        return 'offscreen' if self.is_headless else None

    @property
    def should_use_xvfb(self) -> bool:
        return False  # Just use offscreen

    @property
    def python_version(self) -> str:
        return f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"


# Global singleton
_environment_info: EnvironmentInfo | None = None


def get_environment_info() -> EnvironmentInfo:
    """Get cached environment info."""
    global _environment_info
    if _environment_info is None:
        _environment_info = EnvironmentInfo()
    return _environment_info


# Simple convenience functions
def is_headless_environment() -> bool:
    return get_environment_info().is_headless


def is_ci_environment() -> bool:
    return get_environment_info().is_ci


def is_wsl_environment() -> bool:
    return get_environment_info().is_wsl


def is_docker_environment() -> bool:
    return get_environment_info().is_docker


def has_display_available() -> bool:
    return get_environment_info().has_display


def is_xvfb_available() -> bool:
    return get_environment_info().xvfb_available


def get_recommended_qt_platform() -> str | None:
    return get_environment_info().recommended_qt_platform


def is_pyside6_available() -> bool:
    return get_environment_info().pyside6_available


def configure_qt_for_environment() -> None:
    """No-op. Qt offscreen mode is set in tests/conftest.py."""
    pass


def get_environment_report() -> str:
    """Simple environment report."""
    info = get_environment_info()
    return f"""
=== Environment ===
Platform: {info.platform}
WSL: {info.is_wsl}
Headless: {info.is_headless}
PySide6: {info.pyside6_available}
==================
"""


def print_environment_report() -> None:
    print(get_environment_report())


class HeadlessModeError(RuntimeError):
    """Raised when Qt functionality is accessed in headless mode."""

    def __init__(self, feature: str) -> None:
        super().__init__(f"Qt feature '{feature}' not available in headless mode.")


def require_qt(feature: str) -> None:
    """Raise error if Qt is not available."""
    info = get_environment_info()
    if not info.pyside6_available:
        raise HeadlessModeError(feature)


# =============================================================================
# Test Decorators
# =============================================================================

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
            return pytest.mark.skipif(
                is_wsl_environment(),
                reason=default_reason
            )(func)  # type: ignore[return-value] - pytest.mark stubs don't preserve TypeVar
        return decorator  # type: ignore[return-value] - pytest.mark stubs don't preserve TypeVar
    elif callable(func_or_reason):
        # Called as @skip_if_wsl (no parentheses)
        return pytest.mark.skipif(
            is_wsl_environment(),
            reason=default_reason
        )(func_or_reason)  # type: ignore[return-value] - pytest.mark stubs don't preserve TypeVar
    else:
        # Called as @skip_if_wsl("reason")
        reason = func_or_reason
        def decorator(func: F) -> F:
            return pytest.mark.skipif(
                is_wsl_environment(),
                reason=reason
            )(func)  # type: ignore[return-value] - pytest.mark stubs don't preserve TypeVar
        return decorator  # type: ignore[return-value] - pytest.mark stubs don't preserve TypeVar


def skip_if_no_display(func: F) -> F:
    """Skip test if no display is available."""
    return pytest.mark.skipif(
        not has_display_available(),
        reason="Test requires display"
    )(func)  # type: ignore[return-value] - pytest.mark stubs don't preserve TypeVar


def skip_in_ci(func: F) -> F:
    """Skip test in CI environments."""
    return pytest.mark.skipif(
        is_ci_environment(),
        reason="Test skipped in CI"
    )(func)  # type: ignore[return-value] - pytest.mark stubs don't preserve TypeVar


def requires_display(func: F) -> F:
    """Decorator to mark test as requiring a display."""
    return skip_if_no_display(func)


def requires_real_qt(func: F) -> F:
    """Skip test if real Qt threading isn't available."""
    info = get_environment_info()
    should_skip = not info.pyside6_available
    return pytest.mark.skipif(
        should_skip,
        reason="Test requires real Qt (PySide6)"
    )(func)  # type: ignore[return-value] - pytest.mark stubs don't preserve TypeVar


def headless_safe(func: Callable[P, R]) -> Callable[P, R]:
    """Mark test as safe to run in headless environments (no-op decorator)."""
    @functools.wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        return func(*args, **kwargs)
    return wrapper


def ci_safe(func: Callable[P, R]) -> Callable[P, R]:
    """Mark test as safe to run in CI environments (no-op decorator)."""
    @functools.wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        return func(*args, **kwargs)
    return wrapper
