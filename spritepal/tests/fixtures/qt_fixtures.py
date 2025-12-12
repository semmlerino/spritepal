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

# Add parent directories to path - centralized path setup for tests
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

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


def _get_session_thread_baseline() -> int:
    """Get the session thread baseline (captured at module import time)."""
    return _SESSION_THREAD_BASELINE


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


@pytest.fixture(scope="session", autouse=True)
def qt_environment_setup() -> Iterator[None]:
    """Setup Qt environment automatically.

    Qt environment variables (QT_QPA_PLATFORM=offscreen) are set in pyproject.toml.
    Tests that need real Qt must be marked @pytest.mark.gui.
    """
    yield


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
def main_window() -> MockMainWindowProtocol:
    """Class-scoped main window fixture for performance optimization.

    Used 129 times across tests. Class scope reduces instantiations
    from 129 to ~30 (77% reduction).

    Creates a fully configured mock main window with all required
    attributes and signals.
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
    """Clean up worker threads after tests that spawn them.

    This fixture only runs cleanup for tests marked with @pytest.mark.worker_threads.
    This avoids the 50-500ms overhead for tests that don't spawn workers.

    Uses session-level thread baseline to avoid race conditions where per-test
    baseline captures lingering threads from prior tests.

    Usage:
        @pytest.mark.worker_threads
        def test_extraction_worker():
            # Worker cleanup will run after this test
            pass
    """
    # Only run cleanup for tests that explicitly need it
    markers = [m.name for m in request.node.iter_markers()]
    needs_worker_cleanup = 'worker_threads' in markers

    # Also skip if explicitly marked to not use Qt/managers
    if 'no_manager_setup' in markers or 'no_qt' in markers:
        yield
        return

    if not needs_worker_cleanup:
        yield
        return

    # Use session-level baseline (captured before any tests ran)
    baseline_thread_count = _get_session_thread_baseline()

    yield

    # Import here to avoid circular imports
    from PySide6.QtCore import QCoreApplication, QThread
    from PySide6.QtWidgets import QApplication

    from ui.common import WorkerManager

    # Clean up any remaining workers
    try:
        WorkerManager.cleanup_all()
    except Exception as e:
        import logging
        logging.debug(f"Error during worker cleanup: {e}")

    # Wait for worker threads to finish with proper timeout
    max_wait_ms = 500
    poll_interval_ms = 20
    elapsed = 0

    while elapsed < max_wait_ms:
        active_threads = threading.active_count()
        if active_threads <= baseline_thread_count:
            break

        app = QCoreApplication.instance()
        if app:
            app.processEvents()

        current_thread = QThread.currentThread()
        if current_thread:
            current_thread.msleep(poll_interval_ms)
        else:
            import time
            time.sleep(poll_interval_ms / 1000.0)

        elapsed += poll_interval_ms

    active_threads = threading.active_count()
    if active_threads > baseline_thread_count:
        import logging
        logging.debug(f"Active thread count after cleanup wait: {active_threads}")

    if IS_HEADLESS:
        import gc
        gc.collect()

    # Also check for any QThread instances that might be running
    if not IS_HEADLESS:
        app = QApplication.instance()
        if app:
            for _ in range(5):
                app.processEvents()
                if threading.active_count() <= baseline_thread_count:
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
