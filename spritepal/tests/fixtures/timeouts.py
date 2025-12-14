"""
Semantic timeout helpers for Qt testing.

This module provides named timeouts that scale with environment settings,
replacing magic numbers like `timeout=5000` throughout the test suite.

Usage:
    from tests.fixtures.timeouts import worker_timeout, ui_timeout, signal_timeout

    qtbot.waitSignal(worker.finished, timeout=worker_timeout())
    qtbot.wait(ui_timeout())
    with qtbot.waitSignal(dialog.accepted, timeout=signal_timeout()):
        dialog.accept()

Environment Variables:
    PYTEST_TIMEOUT_MULTIPLIER: Scale all timeouts (default: 1.0)
        Set to 2.0+ for slow CI environments or WSL2.
"""

from __future__ import annotations

import os

__all__ = [
    "get_timeout_multiplier",
    "worker_timeout",
    "ui_timeout",
    "signal_timeout",
    "dialog_timeout",
    "cleanup_timeout",
    "SHORT",
    "MEDIUM",
    "LONG",
]

# Base timeout values in milliseconds
_BASE_UI_TIMEOUT = 1000  # UI responsiveness checks
_BASE_SIGNAL_TIMEOUT = 2000  # Signal emission waits
_BASE_WORKER_TIMEOUT = 5000  # Background worker completion
_BASE_DIALOG_TIMEOUT = 3000  # Dialog interactions
_BASE_CLEANUP_TIMEOUT = 2000  # Resource cleanup waits

# Semantic multipliers for readability
SHORT = 0.5
MEDIUM = 1.0
LONG = 2.0


def get_timeout_multiplier() -> float:
    """
    Get the environment timeout multiplier.

    Returns:
        Multiplier from PYTEST_TIMEOUT_MULTIPLIER env var, default 1.0
    """
    try:
        return float(os.environ.get("PYTEST_TIMEOUT_MULTIPLIER", "1.0"))
    except ValueError:
        return 1.0


def _scaled_timeout(base_ms: int, multiplier: float = 1.0) -> int:
    """Apply both local multiplier and environment multiplier."""
    env_mult = get_timeout_multiplier()
    return int(base_ms * multiplier * env_mult)


def worker_timeout(multiplier: float = MEDIUM) -> int:
    """
    Timeout for background worker completion.

    Use for:
        - Extraction workers
        - Injection workers
        - Any QThread-based operations

    Args:
        multiplier: Scale factor (use SHORT, MEDIUM, LONG constants)

    Returns:
        Timeout in milliseconds

    Example:
        qtbot.waitSignal(worker.finished, timeout=worker_timeout())
        qtbot.waitSignal(slow_worker.finished, timeout=worker_timeout(LONG))
    """
    return _scaled_timeout(_BASE_WORKER_TIMEOUT, multiplier)


def ui_timeout(multiplier: float = MEDIUM) -> int:
    """
    Timeout for UI responsiveness checks.

    Use for:
        - Widget visibility waits
        - Layout updates
        - Repaint operations

    Args:
        multiplier: Scale factor (use SHORT, MEDIUM, LONG constants)

    Returns:
        Timeout in milliseconds

    Example:
        qtbot.wait(ui_timeout(SHORT))
    """
    return _scaled_timeout(_BASE_UI_TIMEOUT, multiplier)


def signal_timeout(multiplier: float = MEDIUM) -> int:
    """
    Timeout for signal emission waits.

    Use for:
        - Generic signal waits
        - Cross-component communication
        - Event propagation

    Args:
        multiplier: Scale factor (use SHORT, MEDIUM, LONG constants)

    Returns:
        Timeout in milliseconds

    Example:
        with qtbot.waitSignal(obj.changed, timeout=signal_timeout()):
            obj.trigger_change()
    """
    return _scaled_timeout(_BASE_SIGNAL_TIMEOUT, multiplier)


def dialog_timeout(multiplier: float = MEDIUM) -> int:
    """
    Timeout for dialog interactions.

    Use for:
        - Dialog acceptance/rejection
        - Modal dialog waits
        - File dialog simulations

    Args:
        multiplier: Scale factor (use SHORT, MEDIUM, LONG constants)

    Returns:
        Timeout in milliseconds

    Example:
        with qtbot.waitSignal(dialog.accepted, timeout=dialog_timeout()):
            dialog.accept()
    """
    return _scaled_timeout(_BASE_DIALOG_TIMEOUT, multiplier)


def cleanup_timeout(multiplier: float = MEDIUM) -> int:
    """
    Timeout for cleanup operations.

    Use for:
        - Thread termination waits
        - Resource deallocation
        - Singleton cleanup

    Args:
        multiplier: Scale factor (use SHORT, MEDIUM, LONG constants)

    Returns:
        Timeout in milliseconds

    Example:
        thread.wait(cleanup_timeout())
    """
    return _scaled_timeout(_BASE_CLEANUP_TIMEOUT, multiplier)
