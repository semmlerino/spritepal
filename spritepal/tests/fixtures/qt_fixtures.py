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


def _get_session_thread_baseline() -> int:
    """Get the session thread baseline (captured at module import time)."""
    return _SESSION_THREAD_BASELINE


def _get_session_thread_identities() -> dict[int, str]:
    """Get the session thread identities (captured at module import time)."""
    return _SESSION_THREAD_IDENTITIES.copy()


# Global timeout configuration - increased for CI/headless environments
# Use PYTEST_TIMEOUT_MULTIPLIER environment variable to scale all timeouts (e.g., 2.0 for slow CI)
def _get_timeout_multiplier() -> float:
    """Get timeout multiplier from environment variable."""
    try:
        return float(os.environ.get("PYTEST_TIMEOUT_MULTIPLIER", "1.0"))
    except ValueError:
        return 1.0


_timeout_multiplier = _get_timeout_multiplier()
_is_ci_or_headless = bool(os.environ.get("CI") or IS_HEADLESS)

DEFAULT_SIGNAL_TIMEOUT = int((10000 if _is_ci_or_headless else 5000) * _timeout_multiplier)
DEFAULT_WAIT_TIMEOUT = int((5000 if _is_ci_or_headless else 2000) * _timeout_multiplier)
DEFAULT_WORKER_TIMEOUT = int((15000 if _is_ci_or_headless else 7500) * _timeout_multiplier)


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
# Qt environment variables (QT_QPA_PLATFORM=offscreen) are set in pyproject.toml.
# Tests that need real Qt must be marked @pytest.mark.gui.


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


@pytest.fixture(scope="class")
def fast_mock_main_window() -> MockMainWindowProtocol:
    """Class-scoped MOCK main window for fast unit tests.

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

    return window  # pyright: ignore[reportReturnType]  # Mock conforms to protocol at runtime


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

@pytest.fixture(autouse=True)
def cleanup_workers(request: pytest.FixtureRequest) -> Generator[None, None, None]:
    """Clean up worker threads after ALL tests (autouse).

    This fixture runs cleanup by default and FAILS if threads are leaked.
    Previously this was opt-in with @pytest.mark.worker_threads; now it's
    opt-out with @pytest.mark.skip_thread_cleanup.

    IMPROVED: Uses identity-based detection instead of count-based.
    - ALWAYS captures thread identities BEFORE test runs
    - ALWAYS compares identities AFTER test to find new threads
    - Reports leaked thread names and stack traces for debugging
    - Only does Qt-specific cleanup when Qt is available

    Accounts for pytest-timeout's monitoring thread (when timeout_method="thread")
    which is created per test but cleaned up AFTER this fixture runs.

    Opt-out markers:
        @pytest.mark.skip_thread_cleanup - Skip cleanup (rare, use only if truly needed)
        @pytest.mark.no_manager_setup - Skip for non-Qt tests
        @pytest.mark.no_qt - Skip for non-Qt tests
    """
    import time

    markers = [m.name for m in request.node.iter_markers()]

    # Opt-OUT: Skip if explicitly marked
    if 'skip_thread_cleanup' in markers or 'no_manager_setup' in markers or 'no_qt' in markers:
        yield
        return

    # PHASE 4: ALWAYS capture thread IDENTITIES before test (not just count)
    # This allows us to identify WHICH threads leaked, not just "count increased"
    # DO THIS BEFORE ANY EARLY RETURNS - we need baseline for leak detection
    before_threads: dict[int, str] = {
        t.ident: t.name for t in threading.enumerate() if t.ident is not None
    }

    yield

    # PHASE 4: Determine if Qt is active for conditional Qt-specific cleanup
    # But we ALWAYS check for leaked threads at the end regardless
    qt_available = False
    qt_app = None
    try:
        from PySide6.QtCore import QCoreApplication
        qt_app = QCoreApplication.instance()
        qt_available = qt_app is not None
    except ImportError:
        # PySide6 not importable - definitely not a Qt test
        qt_available = False

    # PHASE 4: Qt-specific cleanup (CONDITIONAL on Qt being available)
    if qt_available:
        from PySide6.QtCore import QThread
        from PySide6.QtWidgets import QApplication

        from ui.common import WorkerManager

        # Clean up any remaining workers
        try:
            WorkerManager.cleanup_all()
        except Exception as e:
            import logging
            logging.debug(f"Error during worker cleanup: {e}")

    # Detect if pytest-timeout is active with thread method
    timeout_method = request.config.getini("timeout_method")
    timeout_value = request.config.getini("timeout")

    pytest_timeout_active = False
    if timeout_method == "thread":
        try:
            if timeout_value is not None:
                timeout_num = float(timeout_value) if isinstance(timeout_value, str) else timeout_value
                pytest_timeout_active = timeout_num > 0
        except (ValueError, TypeError):
            pass

    # PHASE 4: Wait for worker threads to finish with proper timeout
    # Scale with PYTEST_TIMEOUT_MULTIPLIER for slow CI environments
    max_wait_ms = int(1000 * _timeout_multiplier)
    poll_interval_ms = 20
    elapsed = 0
    leaked_threads: dict[int, str] = {}

    while elapsed < max_wait_ms:
        # IMPROVED: Compare thread identities, not counts
        current_threads = {
            t.ident: t.name for t in threading.enumerate() if t.ident is not None
        }
        leaked_threads = {
            ident: name for ident, name in current_threads.items()
            if ident not in before_threads
        }

        # Filter out pytest-timeout's monitoring thread if active
        if pytest_timeout_active:
            leaked_threads = {
                ident: name for ident, name in leaked_threads.items()
                if "pytest_timeout" not in name.lower() and "timeout" not in name.lower()
            }

        if not leaked_threads:
            break

        # PHASE 4: Qt event processing (CONDITIONAL on Qt being available)
        if qt_available:
            from PySide6.QtCore import QThread
            app = QCoreApplication.instance()
            if app:
                app.processEvents()

            current_thread = QThread.currentThread()
            if current_thread:
                current_thread.msleep(poll_interval_ms)
            else:
                time.sleep(poll_interval_ms / 1000.0)
        else:
            # Non-Qt test: just sleep
            time.sleep(poll_interval_ms / 1000.0)

        elapsed += poll_interval_ms

    # PHASE 4: ALWAYS report leaked threads (not conditional on Qt)
    if leaked_threads:
        test_name = request.node.name if hasattr(request, 'node') else "<unknown>"

        # Build detailed error message with thread info
        msg_lines = [
            f"Test '{test_name}' leaked {len(leaked_threads)} thread(s):",
        ]

        for ident, name in leaked_threads.items():
            msg_lines.append(f"  - {name} (ident={ident})")

            # Try to get stack trace for the leaked thread
            try:
                import sys
                frame = sys._current_frames().get(ident)
                if frame:
                    import traceback
                    msg_lines.append("    Stack trace:")
                    for line in traceback.format_stack(frame):
                        for subline in line.strip().split("\n"):
                            msg_lines.append(f"      {subline}")
            except Exception:
                msg_lines.append("    (stack trace unavailable)")

        msg_lines.append("")
        msg_lines.append("Fix: Ensure all workers are properly stopped and joined.")
        msg_lines.append("Use @pytest.mark.skip_thread_cleanup(reason='...') to opt out if truly needed.")

        pytest.fail("\n".join(msg_lines))

    # PHASE 4: Garbage collection (ALWAYS run for all tests)
    if IS_HEADLESS:
        import gc
        gc.collect()

    # PHASE 4: Additional Qt-specific checks (CONDITIONAL on Qt being available)
    if qt_available and not IS_HEADLESS:
        from PySide6.QtCore import QThread
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        if app:
            for _ in range(5):
                app.processEvents()
                # Re-check with identity comparison
                current_threads = {
                    t.ident: t.name for t in threading.enumerate() if t.ident is not None
                }
                leaked = {
                    ident: name for ident, name in current_threads.items()
                    if ident not in before_threads
                }
                if not leaked:
                    break
                current = QThread.currentThread()
                if current:
                    current.msleep(10)


# =============================================================================
# Timeout Fixtures
# =============================================================================

@pytest.fixture
def signal_timeout() -> int:
    """Provide configurable timeout for Qt signal waiting."""
    return DEFAULT_SIGNAL_TIMEOUT


@pytest.fixture
def wait_timeout() -> int:
    """Provide configurable timeout for general Qt operations."""
    return DEFAULT_WAIT_TIMEOUT


@pytest.fixture
def worker_timeout() -> int:
    """Provide configurable timeout for worker thread operations."""
    return DEFAULT_WORKER_TIMEOUT


@pytest.fixture
def timeout_config() -> dict[str, int]:
    """Provide complete timeout configuration for complex tests."""
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
