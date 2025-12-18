"""
Qt fixtures for SpritePal tests.

This module provides Qt-related fixtures using pytest-qt directly.
QT_QPA_PLATFORM=offscreen is configured in pyproject.toml for headless mode.

Key fixtures:
- qt_app: Session-scoped QApplication
- qtbot: Standard pytest-qt fixture (delegates to pytest-qt)
- main_window: Class-scoped mock main window
- cleanup_workers: Autouse worker thread cleanup
- cleanup_singleton: ManualOffsetDialog singleton cleanup
- signal_timeout, wait_timeout, worker_timeout: Configurable timeouts
"""
from __future__ import annotations

import os
import sys
import threading
import warnings
from collections.abc import Generator, Iterator
from pathlib import Path
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock, Mock

import pytest

if TYPE_CHECKING:
    from pytest import FixtureRequest
    from pytestqt.qtbot import QtBot

    from tests.infrastructure.test_protocols import (
        MockMainWindowProtocol,
    )

# NOTE: pythonpath configured in pyproject.toml - no sys.path manipulation needed

from tests.infrastructure.environment_detection import (
    get_environment_info,
)

# Get environment info - Qt config is handled by pyproject.toml (qt_qpa_platform = "offscreen")
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
_SESSION_THREAD_IDENTITIES: dict[int, str] = {
    t.ident: t.name for t in threading.enumerate() if t.ident is not None
}


def _get_session_thread_baseline(request: pytest.FixtureRequest | None = None) -> int:
    """Get the session thread baseline.

    Prefers session-captured baseline from pytest_sessionstart hook (more reliable).
    Falls back to module import time baseline for backward compatibility.

    Args:
        request: Optional pytest request fixture for accessing session config

    Returns:
        Thread count baseline for comparison
    """
    if request is not None:
        try:
            baseline = getattr(request.config, '_thread_baseline', None)
            if baseline is not None:
                return baseline
        except AttributeError:
            pass
    return _SESSION_THREAD_BASELINE


def _get_session_thread_identities(request: pytest.FixtureRequest | None = None) -> dict[int, str]:
    """Get the session thread identities.

    Prefers session-captured identities from pytest_sessionstart hook (more reliable).
    Falls back to module import time identities for backward compatibility.

    Args:
        request: Optional pytest request fixture for accessing session config

    Returns:
        Dict mapping thread ident to thread name
    """
    if request is not None:
        try:
            identities = getattr(request.config, '_thread_identities', None)
            if identities is not None:
                return identities.copy()
        except AttributeError:
            pass
    return _SESSION_THREAD_IDENTITIES.copy()


# Import consolidated timeout functions from timeouts.py (single source of truth)
# See tests/fixtures/timeouts.py for base values and PYTEST_TIMEOUT_MULTIPLIER scaling
from tests.fixtures.timeouts import (
    LONG,
    get_timeout_multiplier,
    signal_timeout as _signal_timeout_func,
    ui_timeout as _ui_timeout_func,
    worker_timeout as _worker_timeout_func,
)

# Legacy constants for backward compatibility - delegate to timeouts.py
# NOTE: Prefer using the functions from timeouts.py directly in new code
_timeout_multiplier = get_timeout_multiplier()
_is_ci_or_headless = bool(os.environ.get("CI") or IS_HEADLESS)

# Apply CI/headless scaling on top of the standard timeouts
_ci_multiplier = LONG if _is_ci_or_headless else 1.0
DEFAULT_SIGNAL_TIMEOUT = _signal_timeout_func(_ci_multiplier)
DEFAULT_WAIT_TIMEOUT = _ui_timeout_func(_ci_multiplier)
DEFAULT_WORKER_TIMEOUT = _worker_timeout_func(_ci_multiplier)


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
    import os
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
            f"Failed to create QApplication: {e}. "
            "Ensure QT_QPA_PLATFORM=offscreen is set for headless environments."
        )


@pytest.fixture
def fast_mock_main_window() -> MockMainWindowProtocol:
    """Function-scoped MOCK main window for fast unit tests.

    WARNING: Signals are MagicMock objects, NOT real Qt signals.
    - DO NOT use qtbot.waitSignal() with these signals - it will timeout
    - For real signal behavior, use `main_window` fixture instead
    - For testing signal emission: check `window.extract_requested.emit.called`

    Use this for unit tests that:
    - Don't need real Qt signal behavior
    - Use `.emit.called` or `.emit.assert_called_*()` patterns
    - Need fast execution without Qt overhead

    For integration tests, use `main_window` (real signals) instead.
    """
    # Create a simple mock window without spec to avoid issues
    window = Mock()

    # Add all required signals as MagicMocks to allow emission simulation
    window.extract_requested = MagicMock()
    window.open_in_editor_requested = MagicMock()
    window.arrange_rows_requested = MagicMock()
    window.arrange_grid_requested = MagicMock()
    window.inject_requested = MagicMock()
    window.extraction_completed = MagicMock()
    window.extraction_error_occurred = MagicMock()

    # Add all required attributes with proper mocks
    window.extraction_panel = Mock()
    window.rom_extraction_panel = Mock()
    window.output_settings_manager = Mock()
    window.toolbar_manager = Mock()
    window.preview_coordinator = Mock()
    window.status_bar_manager = Mock()
    window.status_bar = Mock()
    window.sprite_preview = Mock()
    window.palette_preview = Mock()
    window.extraction_tabs = Mock()

    # Add state attributes
    window._output_path = ""
    window._extracted_files = []

    return window  # pyright: ignore[reportReturnType]  # Mock conforms to protocol at runtime  # pyright: ignore[reportReturnType]  # Mock conforms to protocol at runtime


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

    For unit tests needing fast MagicMock signals, use `fast_mock_main_window`.
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


@pytest.fixture
def safe_qapp(qt_app: Any) -> Any:
    """Alias for qt_app for backwards compatibility."""
    return qt_app


# =============================================================================
# Worker Thread Management
# =============================================================================

# Known helper threads that are not worker leaks (common framework/tooling threads)
# These threads may appear transiently and should not cause leak failures
_KNOWN_HELPER_THREADS: frozenset[str] = frozenset({
    "pytest-timeout",
    "pytest_timeout",
    "coverage",
    "watchdog",
    "_GCMonitor",
    "pydevd",  # Python debugger
    "QDBusConnectionManager",  # Qt D-Bus
    "QThread",  # Generic QThread name
    "Thread-",  # Default Python thread naming
})


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
            ident: name for ident, name in leaked.items()
            if "pytest_timeout" not in name.lower() and "timeout" not in name.lower()
        }

    # Filter known helper threads
    if filter_helper_threads:
        leaked = {
            ident: name for ident, name in leaked.items()
            if not _is_known_helper_thread(name)
        }

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
    lines.extend([
        "",
        "Fix: Ensure all workers are properly stopped and joined.",
        "Use @pytest.mark.skip_thread_cleanup(reason='...') to opt out if truly needed.",
    ])
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

    elapsed = 0
    leaked: dict[int, str] = {}

    while elapsed < max_wait_ms:
        leaked = _find_leaked_threads(
            before_threads, _get_current_threads(), filter_pytest_timeout
        )
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
    if any(m in markers for m in ('skip_thread_cleanup', 'no_manager_setup', 'no_qt')):
        yield
        return

    # Only run for Qt/worker tests
    qt_fixtures = {'qtbot', 'qt_app', 'qapp', 'hal_pool', 'hal_compressor',
                   'cleanup_singleton', 'real_factory', 'real_extraction_manager'}
    if not (qt_fixtures & set(getattr(request, 'fixturenames', []))):
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
    leaked = _wait_for_threads(
        before_threads,
        max_wait_ms=int(1000 * _timeout_multiplier),
        poll_interval_ms=20,
        filter_pytest_timeout=filter_pytest_timeout,
        qt_available=qt_available,
    )

    # Report leaks
    if leaked:
        leak_mode = request.config.getoption("--leak-mode")
        allow_leaks = leak_mode == "warn" or "allows_resource_leaks" in markers
        test_name = getattr(request.node, 'name', '<unknown>')
        message = _format_leak_message(test_name, leaked)

        if allow_leaks:
            warnings.warn(message, ResourceWarning, stacklevel=2)
        else:
            pytest.fail(message)

    # Cleanup
    if IS_HEADLESS:
        import gc
        gc.collect()


# =============================================================================
# Timeout Fixtures (Legacy - prefer functions from tests.fixtures.timeouts)
# =============================================================================
# NOTE: These fixture-based timeouts exist for backward compatibility.
# For NEW code, prefer importing functions directly from tests.fixtures.timeouts:
#
#     from tests.fixtures.timeouts import worker_timeout, signal_timeout, ui_timeout
#     qtbot.waitSignal(worker.finished, timeout=worker_timeout())
#
# The function-based approach is documented in CLAUDE.md and provides better
# composability with multipliers (SHORT, MEDIUM, LONG).

@pytest.fixture
def signal_timeout() -> int:
    """Provide configurable timeout for Qt signal waiting.

    .. note::
        Prefer using ``from tests.fixtures.timeouts import signal_timeout``
        in new code for better composability with multipliers.
    """
    return DEFAULT_SIGNAL_TIMEOUT


@pytest.fixture
def wait_timeout() -> int:
    """Provide configurable timeout for general Qt operations.

    .. note::
        Prefer using ``from tests.fixtures.timeouts import ui_timeout``
        in new code for better composability with multipliers.
    """
    return DEFAULT_WAIT_TIMEOUT


@pytest.fixture
def worker_timeout() -> int:
    """Provide configurable timeout for worker thread operations.

    .. note::
        Prefer using ``from tests.fixtures.timeouts import worker_timeout``
        in new code for better composability with multipliers.
    """
    return DEFAULT_WORKER_TIMEOUT


@pytest.fixture
def timeout_config() -> dict[str, int]:
    """Provide complete timeout configuration for complex tests.

    .. note::
        Prefer using functions from ``tests.fixtures.timeouts`` directly
        in new code for better composability.
    """
    return {
        'signal': DEFAULT_SIGNAL_TIMEOUT,
        'wait': DEFAULT_WAIT_TIMEOUT,
        'worker': DEFAULT_WORKER_TIMEOUT,
        'short': 500,
        'medium': DEFAULT_WAIT_TIMEOUT,
        'long': DEFAULT_WORKER_TIMEOUT,
    }


# =============================================================================
# Singleton Cleanup
# =============================================================================

@pytest.fixture
def cleanup_singleton(qt_app: Any) -> Generator[None, None, None]:
    """Centralized ManualOffsetDialog singleton cleanup fixture.

    This fixture ensures the ManualOffsetDialogSingleton is properly cleaned up
    before and after each test with explicit ordering to prevent segfaults:
    1. Process pending events (ensure Qt is in stable state)
    2. Request dialog close (triggers Qt cleanup chain)
    3. Wait for dialog to be hidden (confirm close completed)
    4. Schedule deferred deletion (let Qt handle memory)
    5. Process events again (flush deferred deletions)
    6. Reset singleton reference

    Usage:
        def test_something(cleanup_singleton):
            # Singleton is already reset before test
            dialog = ManualOffsetDialogSingleton.get_dialog(panel)
            # ... test code ...
            # Singleton will be reset after test with proper ordering
    """
    from PySide6.QtWidgets import QApplication

    from ui.rom_extraction_panel import ManualOffsetDialogSingleton

    def _safe_cleanup_singleton():
        """Cleanup with explicit ordering to prevent segfaults."""
        app = QApplication.instance()

        # Step 1: Process pending events first
        if app:
            app.processEvents()

        instance = ManualOffsetDialogSingleton._instance
        if instance is not None:
            try:
                # Step 2: Request close
                instance.close()

                # Step 3: Process events to complete close
                if app:
                    app.processEvents()

                # Step 4: Check if hidden (close completed)
                if hasattr(instance, 'isHidden') and not instance.isHidden():
                    # Force hide if close didn't work
                    instance.hide()
                    if app:
                        app.processEvents()

                # Step 5: Schedule deferred deletion
                instance.deleteLater()

                # Step 6: Process deferred deletions
                if app:
                    app.processEvents()
            except (RuntimeError, AttributeError):
                # Widget may already be deleted, ignore
                pass

        # Step 7: Reset singleton reference
        ManualOffsetDialogSingleton.reset()

        # Final event processing
        if app:
            app.processEvents()

    # Clean before test
    _safe_cleanup_singleton()

    yield

    # Clean after test with same careful ordering
    _safe_cleanup_singleton()
