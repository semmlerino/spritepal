"""
Qt fixtures for SpritePal tests.

This module provides Qt-related fixtures using pytest-qt directly.
QT_QPA_PLATFORM=offscreen is set by conftest.py before any Qt imports.

Key fixtures:
- qt_app: Session-scoped QApplication
- qtbot: Standard pytest-qt fixture (delegates to pytest-qt)
- main_window: Class-scoped mock main window
- cleanup_workers: Autouse worker thread cleanup
- cleanup_singleton: Dialog cleanup fixture
- signal_timeout, wait_timeout, worker_timeout: Configurable timeouts
"""

from __future__ import annotations

import logging
import os
import sys
import threading
import warnings
from collections.abc import Generator, Iterator
from pathlib import Path
from typing import TYPE_CHECKING, Any
from unittest.mock import Mock

import pytest

if TYPE_CHECKING:
    from pytest import FixtureRequest
    from pytestqt.qtbot import QtBot

# NOTE: pythonpath configured in pyproject.toml - no sys.path manipulation needed

from tests.infrastructure.environment_detection import (
    get_environment_info,
)

# Get environment info - Qt config is set in conftest.py (os.environ.setdefault)
_environment_info = get_environment_info()
IS_HEADLESS = _environment_info.is_headless

# Thread baseline captured IMMEDIATELY at module load time (before any tests run)
# This avoids race conditions where:
# 1. Multiple parallel test collections try to set the baseline simultaneously
# 2. Baseline is captured after prior tests have already spawned threads
_SESSION_THREAD_BASELINE: int = threading.active_count()

# IMPROVED: Capture thread IDENTITIES not just count
# Identity-based detection is more reliable than count-based:
# - Detects specific threads that leaked vs just "count increased"
# - Can report leaked thread names and stack traces
# - Not confused by Qt/pytest helper threads that fluctuate
_SESSION_THREAD_IDENTITIES: dict[int, str] = {t.ident: t.name for t in threading.enumerate() if t.ident is not None}

# Module logger for fixture diagnostics
_logger = logging.getLogger(__name__)


def _get_session_thread_baseline(request: pytest.FixtureRequest | None = None) -> int:
    """Get the session thread baseline.

    Prefers session-captured baseline from pytest_sessionstart hook (more reliable).
    Falls back to module import time baseline with a warning.

    Args:
        request: Optional pytest request fixture for accessing session config

    Returns:
        Thread count baseline for comparison

    Note:
        The fallback to module-load baseline can cause false positive leak detection
        under xdist, since module import happens before pytest_sessionstart. If you
        see this warning frequently, ensure pytest_sessionstart hook is setting
        request.config._thread_baseline.
    """
    if request is not None:
        try:
            baseline = getattr(request.config, "_thread_baseline", None)
            if baseline is not None:
                return baseline
        except AttributeError:
            pass
    # Fallback to module-load baseline (may cause false positives under xdist)
    _logger.warning(
        "Thread baseline fallback to module-load time (%d threads). "
        "Session baseline not available - this may cause false positive leak detection. "
        "Ensure pytest_sessionstart hook is setting config._thread_baseline.",
        _SESSION_THREAD_BASELINE,
    )
    return _SESSION_THREAD_BASELINE


def _get_session_thread_identities(request: pytest.FixtureRequest | None = None) -> dict[int, str]:
    """Get the session thread identities.

    Prefers session-captured identities from pytest_sessionstart hook (more reliable).
    Falls back to module import time identities with a warning.

    Args:
        request: Optional pytest request fixture for accessing session config

    Returns:
        Dict mapping thread ident to thread name

    Note:
        The fallback to module-load identities can cause false positive leak detection
        under xdist. See _get_session_thread_baseline for details.
    """
    if request is not None:
        try:
            identities = getattr(request.config, "_thread_identities", None)
            if identities is not None:
                return identities.copy()
        except AttributeError:
            pass
    # Fallback to module-load identities (may cause false positives under xdist)
    _logger.warning(
        "Thread identities fallback to module-load time (%d threads). "
        "Session identities not available - this may cause false positive leak detection.",
        len(_SESSION_THREAD_IDENTITIES),
    )
    return _SESSION_THREAD_IDENTITIES.copy()


# For timeout functions, import directly from tests.fixtures.timeouts:
#     from tests.fixtures.timeouts import worker_timeout, signal_timeout, ui_timeout
# See tests/fixtures/timeouts.py for base values and PYTEST_TIMEOUT_MULTIPLIER scaling
from tests.fixtures.timeouts import cleanup_timeout, get_timeout_multiplier


@pytest.fixture(scope="session", autouse=True)
def capture_thread_baseline() -> Iterator[None]:
    """Capture thread baseline at session start before any tests run.

    This fixture runs first (autouse, session scope) to capture the baseline
    thread count before any test spawns threads. Individual tests use this
    baseline to detect thread leaks more reliably.
    """
    # Capture baseline early in session
    _ = _get_session_thread_baseline()
    yield


# NOTE: qt_environment_setup was removed - it did nothing.
# Qt environment variables (QT_QPA_PLATFORM=offscreen) are set at the TOP of conftest.py
# (before any Qt imports) to ensure reliable headless operation.
# Tests that need real Qt must be marked @pytest.mark.gui.


def ensure_headless_qt() -> Any:
    """Ensure Qt is running in headless mode and return QApplication.

    This is the single source of truth for headless Qt initialization.
    Can be called both as a regular function (from helper classes) and
    at module import time.

    Note: QT_QPA_PLATFORM=offscreen should already be set via conftest.py,
    but this function ensures it's set for safety and creates a QApplication
    if one doesn't exist.

    Returns:
        QApplication instance
    """
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ.setdefault("QT_QUICK_BACKEND", "software")

    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


# =============================================================================
# Core Qt Fixtures
# =============================================================================


@pytest.fixture(scope="session")
def qt_app() -> Any:
    """Session-scoped QApplication fixture for maximum performance.

    Used 1,129 times across tests. Session scope reduces instantiations
    from 1,129 to 1 (99.9% reduction).

    Handles QApplication singleton properly to avoid conflicts.

    NOTE: This fixture always creates a real QApplication. In headless
    environments, pyproject.toml sets QT_QPA_PLATFORM=offscreen which allows
    Qt to work without a display.
    """
    try:
        from PySide6.QtWidgets import QApplication

        # Get existing instance or create new one
        app = QApplication.instance()
        if app is None:
            app = QApplication([])

        return app
    except ImportError as e:
        pytest.fail(
            f"Qt not available: {e}. "
            "Tests requiring Qt should be marked @pytest.mark.gui "
            "or the test environment should have PySide6 installed."
        )
    except Exception as e:
        pytest.fail(
            f"Failed to create QApplication: {e}. Ensure QT_QPA_PLATFORM=offscreen is set for headless environments."
        )


@pytest.fixture(scope="function")
def main_window(qtbot: Any) -> Any:
    """Main window with REAL Qt signals - the DEFAULT for all tests.

    This is the default main_window fixture. It provides:
    - Real Qt signals for proper qtbot.waitSignal() testing
    - Mock methods/attributes for UI components
    - Suitable for integration tests and signal-slot testing

    Use this fixture for:
    - Tests using qtbot.waitSignal() on main window signals
    - Testing signal-slot connections
    - Integration tests
    """
    from tests.infrastructure.qt_mocks import RealTestMainWindow

    window = RealTestMainWindow()
    qtbot.addWidget(window)  # Ensure proper cleanup
    return window


# =============================================================================
# Simplified Fixture Aliases (backwards compatibility)
# =============================================================================

# NOTE: We no longer override pytest-qt's qtbot fixture.
# Tests should use the standard 'qtbot' fixture from pytest-qt.
# QT_QPA_PLATFORM=offscreen handles headless mode automatically.


# =============================================================================
# Worker Thread Management
# =============================================================================

# Known helper threads that are not worker leaks (specific framework/tooling threads)
# These threads may appear transiently and should not cause leak failures
# IMPORTANT: Keep this list TIGHT - generic patterns like "QThread" or "Thread-"
# hide real worker leaks. Tests with expected leaks must use skip_thread_cleanup.
_KNOWN_HELPER_THREADS: frozenset[str] = frozenset(
    {
        # Testing infrastructure
        "pytest-timeout",
        "pytest_timeout",
        "coverage",
        # Development tools
        "pydevd",
        "watchdog",
        # Python runtime
        "_GCMonitor",
        # Qt framework internals (specific, not generic)
        "QDBusConnectionManager",
        # NOTE: ThreadPoolExecutor- and Dummy- patterns were intentionally removed
        # to avoid masking real thread leaks. Tests with expected pool threads
        # should use @pytest.mark.skip_thread_cleanup(reason="...").
    }
)


def _is_known_helper_thread(name: str) -> bool:
    """Check if a thread name matches a known helper thread pattern."""
    name_lower = name.lower()
    return any(helper.lower() in name_lower for helper in _KNOWN_HELPER_THREADS)


def _get_current_threads() -> dict[int, str]:
    """Get current thread identities as {ident: name} dict."""
    return {t.ident: t.name for t in threading.enumerate() if t.ident is not None}


def _find_leaked_threads(
    before: dict[int, str],
    current: dict[int, str],
    filter_pytest_timeout: bool = False,
    filter_helper_threads: bool = True,
) -> dict[int, str]:
    """Find threads that exist now but didn't exist before.

    Args:
        before: Threads present before the test
        current: Threads present after the test
        filter_pytest_timeout: Legacy flag to filter pytest-timeout threads
        filter_helper_threads: If True, filter out known helper threads
    """
    leaked = {ident: name for ident, name in current.items() if ident not in before}

    # Legacy pytest-timeout filter (now covered by helper thread filter)
    if filter_pytest_timeout:
        leaked = {
            ident: name
            for ident, name in leaked.items()
            if "pytest_timeout" not in name.lower() and "timeout" not in name.lower()
        }

    # Filter known helper threads
    if filter_helper_threads:
        leaked = {ident: name for ident, name in leaked.items() if not _is_known_helper_thread(name)}

    return leaked


def _format_leak_message(test_name: str, leaked: dict[int, str]) -> str:
    """Format a detailed leak report with stack traces."""
    import traceback

    lines = [f"Test '{test_name}' leaked {len(leaked)} thread(s):"]
    for ident, name in leaked.items():
        lines.append(f"  - {name} (ident={ident})")
        try:
            frame = sys._current_frames().get(ident)
            if frame:
                lines.append("    Stack trace:")
                for line in traceback.format_stack(frame):
                    for subline in line.strip().split("\n"):
                        lines.append(f"      {subline}")
        except Exception:
            lines.append("    (stack trace unavailable)")
    lines.extend(
        [
            "",
            "Fix: Ensure all workers are properly stopped and joined.",
            "Use @pytest.mark.skip_thread_cleanup(reason='...') to opt out if truly needed.",
        ]
    )
    return "\n".join(lines)


def _wait_for_threads(
    before_threads: dict[int, str],
    max_wait_ms: int,
    poll_interval_ms: int,
    filter_pytest_timeout: bool,
    qt_available: bool,
) -> dict[int, str]:
    """Wait for leaked threads to finish, return any remaining leaks."""
    import time

    # Fast path: check immediately before entering wait loop
    # Most tests have no leaked threads - exit without any waiting
    leaked = _find_leaked_threads(before_threads, _get_current_threads(), filter_pytest_timeout)
    if not leaked:
        return {}

    elapsed = 0
    while elapsed < max_wait_ms:
        # Re-check in case threads finished during our initial check
        leaked = _find_leaked_threads(before_threads, _get_current_threads(), filter_pytest_timeout)
        if not leaked:
            break

        if qt_available:
            from PySide6.QtCore import QCoreApplication, QThread

            app = QCoreApplication.instance()
            if app:
                app.processEvents()
            current = QThread.currentThread()
            if current:
                current.msleep(poll_interval_ms)
            else:
                time.sleep(poll_interval_ms / 1000.0)  # sleep-ok: non-Qt fallback
        else:
            time.sleep(poll_interval_ms / 1000.0)  # sleep-ok: non-Qt fallback

        elapsed += poll_interval_ms

    return leaked


@pytest.fixture(autouse=True)
def cleanup_workers(request: pytest.FixtureRequest) -> Generator[None, None, None]:
    """Clean up worker threads after Qt tests (autouse, opt-in by fixture usage).

    Only runs full thread tracking for tests using Qt/worker fixtures.
    Reports leaked thread names and stack traces for debugging.

    Opt-out markers: skip_thread_cleanup, no_manager_setup, no_qt
    """
    markers = [m.name for m in request.node.iter_markers()]

    # Skip if explicitly marked
    if any(m in markers for m in ("skip_thread_cleanup", "no_manager_setup", "no_qt")):
        logger = logging.getLogger(__name__)
        logger.debug(
            "Thread cleanup skipped for %s (markers: %s)",
            request.node.nodeid,
            [m for m in markers if m in ("skip_thread_cleanup", "no_manager_setup", "no_qt")],
        )
        yield
        return

    # Only run for Qt/worker tests
    qt_fixtures = {
        "qtbot",
        "qt_app",
        "qapp",
        "hal_pool",
        "hal_compressor",
        "cleanup_singleton",
        "real_factory",
        "real_extraction_manager",
        "app_context",
        "session_app_context",
    }
    if not (qt_fixtures & set(getattr(request, "fixturenames", []))):
        yield
        return

    before_threads = _get_current_threads()
    yield

    # Check if Qt is available
    qt_available = False
    try:
        from PySide6.QtCore import QCoreApplication

        qt_available = QCoreApplication.instance() is not None
    except ImportError:
        pass

    # Qt-specific cleanup
    if qt_available:
        from ui.common import WorkerManager

        try:
            WorkerManager.cleanup_all()
        except Exception:
            pass

        # Early exit if no workers were registered
        # Skips expensive thread leak detection for worker-free tests
        if not hasattr(WorkerManager, "_worker_registry") or not WorkerManager._worker_registry:
            return  # No workers to wait for

    # Check for pytest-timeout thread method
    filter_pytest_timeout = False
    if request.config.getini("timeout_method") == "thread":
        try:
            timeout_val = request.config.getini("timeout")
            if timeout_val:
                filter_pytest_timeout = float(timeout_val) > 0
        except (ValueError, TypeError):
            pass

    # Wait for threads to finish
    # Uses cleanup_timeout() (2000ms base, scaled by PYTEST_TIMEOUT_MULTIPLIER)
    # Tests with slow cleanup should use @pytest.mark.skip_thread_cleanup
    leaked = _wait_for_threads(
        before_threads,
        max_wait_ms=cleanup_timeout(),
        poll_interval_ms=20,
        filter_pytest_timeout=filter_pytest_timeout,
        qt_available=qt_available,
    )

    # Report leaks
    if leaked:
        leak_mode = request.config.getoption("--leak-mode")
        allow_leaks = leak_mode == "warn"
        test_name = getattr(request.node, "name", "<unknown>")
        message = _format_leak_message(test_name, leaked)

        if allow_leaks:
            warnings.warn(message, ResourceWarning, stacklevel=2)
        else:
            pytest.fail(message)

    # Note: We intentionally skip gc.collect() here to avoid Qt finalization race.
    # WorkerManager.cleanup_all() already handles safe cleanup of Qt objects.


# =============================================================================
# Singleton Cleanup
# =============================================================================


@pytest.fixture
def cleanup_singleton(qt_app: Any) -> Generator[None, None, None]:
    """Dialog cleanup fixture for tests using Qt dialogs.

    With per-instance dialog management, cleanup is handled automatically
    by Qt's parent-child hierarchy. This fixture processes pending events
    to ensure clean state between tests.

    Usage:
        def test_something(cleanup_singleton):
            # Events processed before test
            dialog = UnifiedManualOffsetDialog(parent=widget, ...)
            # ... test code ...
            # Events processed after test
    """
    from PySide6.QtWidgets import QApplication

    def _process_events():
        """Process Qt events to ensure clean state."""
        app = QApplication.instance()
        if app:
            app.processEvents()

    # Process events before test
    _process_events()

    yield

    # Process events after test
    _process_events()
