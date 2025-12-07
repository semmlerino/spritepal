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

    from tests.infrastructure.test_protocols import (
        MockMainWindowProtocol,
        MockQtBotProtocol,
    )

# Add parent directories to path - centralized path setup for tests
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tests.infrastructure.environment_detection import (
    get_environment_info,
    get_environment_report,
)
from tests.infrastructure.safe_fixtures import (
    SafeQApplicationProtocol,
    SafeQtBotProtocol,
    cleanup_all_fixtures,
    create_safe_dialog_factory,
    create_safe_qapp,
    create_safe_qtbot,
    create_safe_widget_factory,
    safe_qt_context,
    validate_fixture_environment,
)

# Get environment info - Qt config is handled by pyproject.toml (qt_qpa_platform = "offscreen")
_environment_info = get_environment_info()
IS_HEADLESS = _environment_info.is_headless

# Thread baseline captured at module load time (before any tests run)
# This avoids race conditions where tests capture baseline after prior tests left threads running
_SESSION_THREAD_BASELINE: int | None = None


def _get_session_thread_baseline() -> int:
    """Get the session thread baseline, capturing it if not yet set."""
    global _SESSION_THREAD_BASELINE
    if _SESSION_THREAD_BASELINE is None:
        _SESSION_THREAD_BASELINE = threading.active_count()
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
    """
    Setup Qt environment automatically based on comprehensive environment detection.

    Uses centralized environment detection to determine the best Qt configuration.
    Qt environment variables (QT_QPA_PLATFORM=offscreen) are set in pytest.ini
    and by configure_qt_for_environment().

    NOTE: We no longer mock Qt modules in headless environments. Tests that need
    real Qt must be marked @pytest.mark.gui and will be skipped in headless.
    Tests that don't need Qt should not import Qt modules.
    This ensures tests fail loudly if they incorrectly require Qt without marking.
    """
    # Qt environment variables are configured by configure_qt_for_environment() at module load
    # and qt_qpa_platform=offscreen is set in pytest.ini for headless mode
    yield


# High-frequency fixture optimizations for 68.6% performance improvement
# These fixtures are optimized based on usage analysis:
# - qt_app: 1,129 uses → session scope (1 instance)
# - main_window: 129 uses → class scope (~30 instances)

@pytest.fixture(scope="session")
def qt_app() -> Any:
    """Session-scoped QApplication fixture for maximum performance.

    Used 1,129 times across tests. Session scope reduces instantiations
    from 1,129 to 1 (99.9% reduction).

    Handles QApplication singleton properly to avoid conflicts.

    NOTE: This fixture always creates a real QApplication. In headless
    environments, pytest.ini sets QT_QPA_PLATFORM=offscreen which allows
    Qt to work without a display. Tests that fail with this fixture in
    headless mode should either:
    1. Be marked @pytest.mark.gui (skipped in headless)
    2. Not require QApplication at all
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


# Enhanced Safe Fixture Implementations
@pytest.fixture
def enhanced_safe_qtbot(request: FixtureRequest) -> SafeQtBotProtocol:
    """
    Enhanced safe qtbot fixture that requires real Qt (with offscreen in headless).

    This fixture provides real Qt functionality and fails loudly if Qt is unavailable.
    Use mock_qtbot fixture instead for tests that explicitly don't need real Qt.

    Per HEADLESS_TESTING.md: "No Mock Fallbacks - tests fail loudly"
    """
    # No try/except - let HeadlessModeError propagate for clear failure
    qtbot = create_safe_qtbot(request, allow_mock=False)
    yield qtbot
    # Cleanup handled by fixture manager


@pytest.fixture
def safe_qtbot(request: FixtureRequest) -> SafeQtBotProtocol:
    """
    Alias for enhanced_safe_qtbot for backwards compatibility.

    Some test files use `safe_qtbot` as the fixture name. This provides
    the same functionality as `enhanced_safe_qtbot`.
    """
    qtbot = create_safe_qtbot(request, allow_mock=False)
    yield qtbot


@pytest.fixture
def mock_qtbot(request: FixtureRequest) -> SafeQtBotProtocol:
    """
    Explicit mock qtbot fixture for tests that don't need real Qt.

    Use this fixture with @pytest.mark.mock_qt to document that a test
    intentionally uses mock Qt behavior.

    Only use when:
    - Testing logic that doesn't depend on real Qt signal/slot behavior
    - Testing code paths that should work without Qt installed
    - Unit tests that mock Qt components anyway
    """
    from tests.infrastructure.safe_fixtures import SafeQtBot

    qtbot = SafeQtBot(headless=True)
    yield qtbot
    qtbot.cleanup()


@pytest.fixture(scope="session")
def enhanced_safe_qapp() -> SafeQApplicationProtocol:
    """
    Enhanced safe QApplication fixture that requires real Qt (with offscreen in headless).

    This fixture provides real Qt functionality and fails loudly if Qt is unavailable.

    Per HEADLESS_TESTING.md: "No Mock Fallbacks - tests fail loudly"
    """
    # No try/except - let HeadlessModeError propagate for clear failure
    qapp = create_safe_qapp(allow_mock=False)
    yield qapp
    # Cleanup handled by fixture manager


@pytest.fixture
def safe_widget_factory_fixture(request: FixtureRequest):
    """
    Safe widget factory for creating Qt widgets (with offscreen in headless).

    Provides real Qt widget creation and fails loudly if Qt is unavailable.

    Per HEADLESS_TESTING.md: "No Mock Fallbacks - tests fail loudly"
    """
    # No try/except - let errors propagate for clear failure
    factory = create_safe_widget_factory()
    yield factory
    factory.cleanup()


@pytest.fixture
def safe_dialog_factory_fixture(request: FixtureRequest):
    """
    Safe dialog factory for creating Qt dialogs (with offscreen in headless).

    Provides real Qt dialog creation and fails loudly if Qt is unavailable.

    Per HEADLESS_TESTING.md: "No Mock Fallbacks - tests fail loudly"
    """
    # No try/except - let errors propagate for clear failure
    factory = create_safe_dialog_factory()
    yield factory
    factory.cleanup()


@pytest.fixture
def safe_qt_environment(request: FixtureRequest):
    """
    Complete safe Qt environment with all components (offscreen in headless).

    Provides a complete Qt testing environment and fails loudly if Qt unavailable.

    Per HEADLESS_TESTING.md: "No Mock Fallbacks - tests fail loudly"
    """
    # No try/except - let errors propagate for clear failure
    with safe_qt_context(request) as qt_env:
        yield qt_env


# Override pytest-qt fixtures to use safe versions
@pytest.fixture
def enhanced_qtbot(request: FixtureRequest) -> SafeQtBotProtocol:
    """Override pytest-qt qtbot with enhanced safe version."""
    return request.getfixturevalue('enhanced_safe_qtbot')


@pytest.fixture
def qtbot(enhanced_safe_qtbot: SafeQtBotProtocol) -> SafeQtBotProtocol:
    """Override standard qtbot with safe version.
    
    This ensures that tests requesting 'qtbot' automatically get the safe wrapper
    that correctly handles mock widgets in headless environments.
    """
    return enhanced_safe_qtbot


@pytest.fixture(scope="session")
def enhanced_qapp() -> SafeQApplicationProtocol:
    """Override pytest-qt qapp with enhanced safe version."""
    # Delegate to our enhanced safe fixture
    return create_safe_qapp()


# Session-level cleanup fixture
@pytest.fixture(scope="session", autouse=True)
def cleanup_safe_fixtures_session():
    """Auto-cleanup all safe fixtures at session end."""
    yield

    # Cleanup all fixtures at session end
    try:
        cleanup_all_fixtures()
        import logging
        logging.getLogger(__name__).info("Safe fixtures cleanup completed")
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Error during safe fixtures cleanup: {e}")


# Validation fixture for debugging
@pytest.fixture
def fixture_validation_report():
    """
    Provide fixture validation report for debugging.

    Usage:
        def test_something(fixture_validation_report):
            if fixture_validation_report['errors']:
                pytest.skip(f"Fixture validation failed: {fixture_validation_report['errors']}")
    """
    return validate_fixture_environment()


# Helper fixtures for gradual migration
@pytest.fixture
def real_qtbot(request: FixtureRequest):
    """
    Real qtbot fixture for tests that specifically need real Qt.

    Use this only for integration tests that require real Qt behavior.
    Will skip in headless environments without xvfb.
    """
    env_info = get_environment_info()

    if env_info.is_headless and not env_info.xvfb_available:
        pytest.skip("Real qtbot requires display or xvfb")

    try:
        # Import and use pytest-qt directly
        pytest.importorskip("pytestqt")
        return request.getfixturevalue('qtbot')  # Get real qtbot from pytest-qt
    except Exception as e:
        pytest.skip(f"Real qtbot not available: {e}")


@pytest.fixture
def adaptive_qtbot(request: FixtureRequest):
    """
    Adaptive qtbot that chooses implementation based on test markers.

    Uses real qtbot for tests marked with @pytest.mark.qt_real
    Uses mock qtbot for tests marked with @pytest.mark.qt_mock
    Uses safe qtbot (auto-detect) for unmarked tests
    """
    if request.node.get_closest_marker("qt_real"):
        return request.getfixturevalue('real_qtbot')
    if request.node.get_closest_marker("qt_mock"):
        return request.getfixturevalue('mock_qtbot')
    return request.getfixturevalue('enhanced_safe_qtbot')


# Configuration and debugging helpers
@pytest.fixture
def debug_fixture_logging(request: FixtureRequest):
    """Opt-in fixture for debugging safe fixtures.

    Enable by requesting this fixture in your test AND setting
    PYTEST_DEBUG_FIXTURES=1 environment variable.
    """
    if os.environ.get('PYTEST_DEBUG_FIXTURES'):
        import logging
        logging.getLogger('tests.infrastructure.safe_fixtures').setLevel(logging.DEBUG)

    yield


@pytest.fixture
def safe_qapp(qt_app: Any) -> Any:  # QApplication | Mock but avoid circular import
    """Provide a QApplication that works in both headless and GUI environments.

    This fixture now uses the optimized qt_app fixture instead of pytest-qt's qapp.
    """
    return qt_app


@pytest.fixture(autouse=True)
def cleanup_workers(request: pytest.FixtureRequest) -> Generator[None, None, None]:
    """
    Clean up worker threads after tests that spawn them.

    This fixture only runs cleanup for tests marked with @pytest.mark.worker_threads.
    This avoids the 50-500ms overhead for tests that don't spawn workers.

    Uses session-level thread baseline to avoid race conditions where per-test
    baseline captures lingering threads from prior tests.

    Usage:
        @pytest.mark.worker_threads
        def test_extraction_worker():
            # Worker cleanup will run after this test
            pass

    For tests that explicitly don't need worker cleanup, use:
        @pytest.mark.no_qt or @pytest.mark.no_manager_setup
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
    # This avoids race conditions with lingering threads from prior tests
    baseline_thread_count = _get_session_thread_baseline()

    yield

    # Import here to avoid circular imports
    from PySide6.QtCore import QCoreApplication, QThread
    from PySide6.QtWidgets import QApplication

    from ui.common.worker_manager import WorkerManager

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


# Timeout fixtures for consistent signal waiting across tests
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
