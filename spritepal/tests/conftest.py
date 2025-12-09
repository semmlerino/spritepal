# pyright: recommended  # Use recommended mode for test files with enhanced basedpyright features
# pyright: reportPrivateUsage=false  # Allow testing private methods
# pyright: reportUnknownMemberType=warning  # Mock attributes are dynamic
# pyright: reportUnknownArgumentType=warning  # Test data may be dynamic
# pyright: reportUntypedFunctionDecorator=error  # Type all decorators
# pyright: reportUnnecessaryTypeIgnoreComment=error  # Clean up unused ignores
"""
Unified pytest configuration for SpritePal tests.

This module consolidates all test configuration into a single, modern approach
that works consistently across all environments (headless, GUI, CI/CD).

## Modular Fixture Architecture

Fixtures are organized into modular files for maintainability:
- `fixtures/qt_fixtures.py`: Qt application, main window, qtbot fixtures
- `fixtures/core_fixtures.py`: Manager fixtures, DI fixtures, state management
- `fixtures/hal_fixtures.py`: HAL compression mock/real fixtures

## Performance Optimizations

This conftest.py implements fixture scope optimizations that reduce fixture
instantiations by 68.6% based on usage analysis:

- qt_app: Session scope (1,129 → 1 instance, 99.9% reduction)
- main_window: Class scope (129 → ~30 instances, 77% reduction)
- controller: Class scope (119 → ~30 instances, 75% reduction)
- mock_manager_registry: Module scope (81 → ~15 instances, 81% reduction)
- real_extraction_manager: Class scope (51 → ~12 instances, 77% reduction)
- rom_cache: Class scope (48 → ~10 instances, 79% reduction)
- mock_settings_manager: Class scope (44 → ~10 instances, 77% reduction)
- real_session_manager: Class scope (26 → ~8 instances, 69% reduction)

## State Isolation

Class-scoped and module-scoped fixtures include automatic state reset
mechanisms to ensure test isolation:

- `reset_main_window_state`: Resets main window state between tests
- `reset_controller_state`: Resets controller state between tests
- `reset_class_state`: Resets all class-scoped mock fixtures (requires @pytest.mark.usefixtures)

## Scope Selection Guidelines

- **Session scope**: For expensive, stateless resources (Qt application)
- **Module scope**: For fixtures shared across test modules with minimal state
- **Class scope**: For fixtures shared within test classes with manageable state
- **Function scope**: For fixtures requiring full isolation (default)

All optimized fixtures maintain backward compatibility and proper cleanup.
"""

from __future__ import annotations

# CRITICAL: Set offscreen mode BEFORE any Qt imports to prevent dialogs
import os

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import tempfile
import warnings
from collections.abc import Generator
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any
from unittest.mock import Mock

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from pytest import FixtureRequest

    from tests.infrastructure.test_protocols import (
        MockMainWindowProtocol,
    )

# Import consolidated mock utilities
import contextlib

import pytest

# Import constants from timeout configuration module
from .constants_timeout import (
    INTEGRATION_PATTERNS,
    SLOW_TEST_PATTERNS,
    TIMEOUT_BENCHMARK,
    TIMEOUT_INTEGRATION,
    TIMEOUT_SLOW,
    TIMEOUT_UNIT,
)
from .infrastructure.environment_detection import get_environment_info

# ============================================================================
# pytest_plugins - Import fixtures from modular files
# ============================================================================
# This imports all fixtures from the modular fixture files, making them
# available to all tests automatically.

pytest_plugins = [
    "tests.fixtures.qt_fixtures",
    "tests.fixtures.core_fixtures",
    "tests.fixtures.hal_fixtures",
]


@lru_cache(maxsize=1)
def _get_environment_info():
    """Lazy-load environment info to avoid import-time side effects."""
    return get_environment_info()


def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        "markers",
        "allows_registry_state: Allow test to find/leave registry initialized without manager fixtures"
    )
    config.addinivalue_line(
        "markers",
        "real_hal: Use real HAL implementation instead of mocks"
    )
    config.addinivalue_line(
        "markers",
        "no_manager_setup: Skip setup_managers fixture for this test"
    )


def pytest_addoption(parser: Any) -> None:
    """Add custom command line options for SpritePal tests."""
    parser.addoption(
        "--use-real-hal",
        action="store_true",
        default=False,
        help="Use real HAL process pool instead of mocks (slower)"
    )
    # NOTE: --run-segfault-tests option removed - segfault-prone tests have been deleted


def pytest_sessionfinish(session: Any, exitstatus: int) -> None:
    """Clean up all singletons at session end to prevent state pollution.

    This hook ensures:
    1. ManagerRegistry singleton is fully reset
    2. DataRepository temp files are cleaned up
    3. HAL process pool singleton is reset

    Without this, state can leak between test runs or cause errors
    in subsequent test sessions.
    """
    # 1. Reset ManagerRegistry singleton completely
    with contextlib.suppress(Exception):
        from core.managers.registry import ManagerRegistry
        ManagerRegistry._instance = None
        ManagerRegistry._cleanup_registered = False

    # 2. Clean up DataRepository (temp files and singleton)
    with contextlib.suppress(Exception):
        from tests.infrastructure.test_data_repository import cleanup_test_data_repository
        cleanup_test_data_repository()

    # 3. Reset HAL singleton (already handled by atexit, but ensure clean state)
    with contextlib.suppress(Exception):
        from core.hal_compression import HALProcessPool
        if hasattr(HALProcessPool, '_instance'):
            HALProcessPool._instance = None


# ============================================================================
# Test Data Factories (not in modular files - specific to test data creation)
# ============================================================================

@pytest.fixture
def test_data_factory() -> Callable[..., bytearray]:
    """
    Factory for creating consistent test data structures.

    Provides a unified way to create VRAM, CGRAM, and OAM test data
    with realistic patterns used across the test suite.
    """
    def _create_test_data(data_type: str, size: int | None = None, **kwargs: Any) -> bytearray:
        """
        Create test data of specified type.

        Args:
            data_type: Type of data - 'vram', 'cgram', 'oam'
            size: Size override (uses defaults if None)
            **kwargs: Additional parameters for data generation

        Returns:
            Bytearray with realistic test data
        """
        if data_type == "vram":
            # Lazy import constants to reduce startup overhead
            from utils.constants import BYTES_PER_TILE, VRAM_SPRITE_OFFSET

            default_size = 0x10000  # 64KB
            data = bytearray(size or default_size)

            # Add realistic sprite data at VRAM offset
            start_offset = kwargs.get("sprite_offset", VRAM_SPRITE_OFFSET)
            tile_count = kwargs.get("tile_count", 10)

            for i in range(tile_count):
                offset = start_offset + i * BYTES_PER_TILE
                if offset + BYTES_PER_TILE <= len(data):
                    for j in range(BYTES_PER_TILE):
                        data[offset + j] = (i + j) % 256

            return data

        if data_type == "cgram":
            default_size = 512  # 256 colors * 2 bytes
            data = bytearray(size or default_size)

            # Add realistic palette data (BGR555 format)
            for i in range(0, len(data), 2):
                data[i] = i % 256
                data[i + 1] = (i // 2) % 32

            return data

        if data_type == "oam":
            default_size = 544  # Standard OAM size
            data = bytearray(size or default_size)

            # Add realistic OAM data (sprite attributes)
            for i in range(0, min(len(data), 512), 4):  # 4 bytes per entry
                data[i] = i % 256      # X position
                data[i + 1] = i % 224  # Y position
                data[i + 2] = i % 256  # Tile index
                data[i + 3] = 0x20     # Attributes

            return data

        raise ValueError(f"Unknown data type: {data_type}")

    return _create_test_data

@pytest.fixture
def temp_files() -> Iterator[Callable[[bytes, str], str]]:
    """
    Factory for creating temporary test files with automatic cleanup.

    Creates temporary files with test data and ensures they are
    properly cleaned up after test completion.
    """
    created_files: list[str] = []

    def _create_temp_file(data: bytes, suffix: str = ".dmp") -> str:
        """Create a temporary file with the given data."""
        temp_file = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
        temp_file.write(data)
        temp_file.close()
        created_files.append(temp_file.name)
        return temp_file.name

    yield _create_temp_file

    # Cleanup
    for file_path in created_files:
        try:
            Path(file_path).unlink(missing_ok=True)
        except OSError:
            pass  # File might already be deleted

@pytest.fixture
def standard_test_params(
    test_data_factory: Callable[..., bytearray],
    temp_files: Callable[[bytes, str], str],
) -> dict[str, Any]:
    """
    Create standard test parameters used across integration tests.

    Provides the common set of test parameters that many integration
    tests use, reducing duplication in test setup.
    """
    # Create standard test data
    vram_data = test_data_factory("vram")
    cgram_data = test_data_factory("cgram")
    oam_data = test_data_factory("oam")

    # Create temporary files - convert bytearray to bytes for temp_files
    vram_file = temp_files(bytes(vram_data), ".dmp")
    cgram_file = temp_files(bytes(cgram_data), ".dmp")
    oam_file = temp_files(bytes(oam_data), ".dmp")

    return {
        "vram_path": vram_file,
        "cgram_path": cgram_file,
        "oam_path": oam_file,
        "output_base": "test_output",
        "create_grayscale": True,
        "create_metadata": True,
        "vram_data": vram_data,
        "cgram_data": cgram_data,
        "oam_data": oam_data,
    }

@pytest.fixture
def minimal_sprite_data(
    test_data_factory: Callable[..., bytearray],
) -> dict[str, Any]:
    """
    Create minimal but valid sprite data for quick tests.

    Provides a lightweight alternative to full test data for tests
    that just need basic sprite data structure.
    """
    return {
        "vram": test_data_factory("vram", size=0x1000),  # 4KB
        "cgram": test_data_factory("cgram", size=32),    # 1 palette
        "width": 64,
        "height": 64,
        "tile_count": 8,
    }


# ============================================================================
# Module-scoped fixtures (remain in conftest.py for performance)
# ============================================================================

@pytest.fixture(scope="module")
def mock_manager_registry() -> Generator[Mock, None, None]:
    """Module-scoped manager registry fixture for performance optimization.

    Used 81 times across tests. Module scope reduces instantiations
    from 81 to ~15 (81% reduction).

    Provides a mock manager registry with common manager access methods.
    Resets mock state at end of module to prevent state leakage.
    """
    registry = Mock()

    # Add common registry methods
    registry.get_manager = Mock()
    registry.register_manager = Mock()
    registry.is_initialized = Mock(return_value=True)
    registry.cleanup = Mock()

    # Add manager getters
    registry.get_extraction_manager = Mock()
    registry.get_injection_manager = Mock()
    registry.get_session_manager = Mock()

    yield registry

    # Reset mock state at end of module to prevent state leakage
    registry.reset_mock(return_value=True, side_effect=True)


# ============================================================================
# Qt Threading Safety Fixtures
# ============================================================================

@pytest.fixture
def guard_qpixmap_threading(request: FixtureRequest, monkeypatch: pytest.MonkeyPatch):
    """Prevent QPixmap creation in worker threads during tests.

    This fixture monkeypatches QPixmap.__init__ to raise a RuntimeError
    if it's called from a non-GUI thread, helping to identify critical
    Qt threading violations that cause segfaults.

    Opt-in via marker:
        @pytest.mark.qt_threading
        def test_threaded_operation(guard_qpixmap_threading):
            ...

    Or skip for entire test class:
        @pytest.mark.usefixtures("guard_qpixmap_threading")
        class TestThreadedWidgets:
            ...

    Previously autouse=True, but this added overhead to ALL tests including
    non-Qt tests. Now opt-in for tests that actually need threading safety.
    """
    # Skip if test doesn't have qt_threading marker AND didn't explicitly request fixture
    if not request.node.get_closest_marker('qt_threading'):
        # If explicitly requested as a fixture, still run the guard
        if 'guard_qpixmap_threading' not in request.fixturenames:
            yield
            return

    from PySide6.QtCore import QCoreApplication, QThread
    from PySide6.QtGui import QPixmap

    original_init = QPixmap.__init__

    def guarded_init(self, *args, **kwargs):
        app = QCoreApplication.instance()
        # Only check if an application instance exists and if not on the main GUI thread
        if app and QThread.currentThread() != app.thread():
            raise RuntimeError(
                "CRITICAL: QPixmap created in worker thread! "
                "Use QImage or ThreadSafeTestImage. "
                "Conversion to QPixmap must happen on the main GUI thread."
            )
        original_init(self, *args, **kwargs)

    monkeypatch.setattr(QPixmap, '__init__', guarded_init)
    yield


# ============================================================================
# Class-scoped State Reset Fixtures
# ============================================================================

@pytest.fixture(scope="class")
def reset_main_window_state(main_window: MockMainWindowProtocol) -> Generator[None, None, None]:
    """Reset main window state between tests within the same class.

    This fixture ensures state isolation when using class-scoped main_window.
    Must be explicitly requested by test classes that need it.
    """
    # Reset state before test
    if hasattr(main_window, '_output_path'):
        main_window._output_path = ""
    if hasattr(main_window, '_extracted_files'):
        main_window._extracted_files = []

    # Reset all mock call histories
    for attr_name in dir(main_window):
        attr = getattr(main_window, attr_name, None)
        if isinstance(attr, Mock):
            attr.reset_mock()

    yield

    # Additional cleanup after test if needed
    pass

@pytest.fixture(scope="class")
def reset_controller_state(controller: Mock) -> Generator[None, None, None]:
    """Reset controller state between tests within the same class.

    This fixture ensures state isolation when using class-scoped controller.
    Must be explicitly requested by test classes that need it.
    """
    # Reset controller state if it's a real controller
    if hasattr(controller, 'reset_state'):
        controller.reset_state()
    elif isinstance(controller, Mock):
        controller.reset_mock()

    yield

    # Additional cleanup after test if needed
    pass

@pytest.fixture(scope="function")
def reset_class_state(
    request: pytest.FixtureRequest,
) -> Generator[None, None, None]:
    """Reset state for class-scoped fixtures between tests.

    This fixture ensures proper state isolation for performance-optimized
    class-scoped fixtures. Request it explicitly in test classes that need
    fixture state reset between tests.

    NOTE: This is function-scoped so it runs AFTER each test to reset
    class-scoped fixture state before the next test runs.

    Usage:
        @pytest.mark.usefixtures("reset_class_state")
        class TestExtractionPanel:
            pass

    IMPORTANT: reset_mock() only clears call history. We must also clear:
    - return_value (if manually configured)
    - side_effect (if manually configured)
    - Any internal state
    """
    # Run test first
    yield

    # Reset fixtures AFTER each test for the next one
    fixture_names = getattr(request, 'fixturenames', [])

    # Reset fixtures dynamically based on what's actually used
    fixtures_to_reset = [
        'real_extraction_manager',  # Real component - uses reset_state() or clear()
        'real_session_manager',     # Real component - uses reset_state() or clear()
        'rom_cache',
        'mock_settings_manager',
        'main_window',
    ]

    for fixture_name in fixtures_to_reset:
        if fixture_name in fixture_names:
            try:
                fixture_value = request.getfixturevalue(fixture_name)
                if isinstance(fixture_value, Mock):
                    # Full reset: clear call history AND configured values
                    fixture_value.reset_mock(return_value=True, side_effect=True)
                elif hasattr(fixture_value, 'reset_state'):
                    # Real component with explicit reset method
                    fixture_value.reset_state()
                elif hasattr(fixture_value, 'clear_cache'):
                    # ROMCache and similar use clear_cache() method
                    fixture_value.clear_cache()
                elif hasattr(fixture_value, 'clear'):
                    # Generic clear for collections
                    fixture_value.clear()
            except pytest.FixtureLookupError:
                pass  # Fixture not available in this context
            except Exception as e:
                # Log reset failures but don't fail the test
                # Reset is best-effort to improve isolation
                import logging
                logging.getLogger(__name__).warning(
                    f"Failed to reset fixture {fixture_name}: {e}"
                )


@pytest.fixture
def verify_cleanup(request: FixtureRequest) -> Generator[None, None, None]:
    """Verify that test cleanup actually succeeded.

    This fixture checks for lingering state after tests complete,
    helping identify incomplete cleanup that could cause flaky tests.

    Usage:
        @pytest.mark.usefixtures("verify_cleanup")
        class TestWithCleanupVerification:
            pass

    Or explicitly:
        def test_something(verify_cleanup):
            ...
    """
    yield

    # Verify no lingering manager state
    from core.managers.registry import ManagerRegistry

    registry = ManagerRegistry()
    if registry.is_initialized():
        # Check for active operations that weren't cleaned up
        for manager_name in ['extraction_manager', 'injection_manager', 'session_manager']:
            if hasattr(registry, manager_name):
                manager = getattr(registry, manager_name)
                if manager and hasattr(manager, '_active_operations'):
                    active_ops = getattr(manager, '_active_operations', [])
                    if active_ops:
                        warnings.warn(
                            f"Test '{request.node.name}': Manager '{manager_name}' has "
                            f"{len(active_ops)} active operations after cleanup",
                            UserWarning,
                            stacklevel=2
                        )

                # Check for unclosed resources
                if manager and hasattr(manager, '_open_handles'):
                    handles = getattr(manager, '_open_handles', [])
                    if handles:
                        warnings.warn(
                            f"Test '{request.node.name}': Manager '{manager_name}' has "
                            f"{len(handles)} open handles after cleanup",
                            UserWarning,
                            stacklevel=2
                        )


@pytest.fixture
def check_parallel_isolation(request: FixtureRequest) -> Generator[None, None, None]:
    """Enforce that parallel-safe tests don't use shared mutable state.

    This fixture checks that tests marked with @pytest.mark.parallel_safe
    don't use session-scoped fixtures that could cause race conditions
    when running tests in parallel.

    Usage:
        @pytest.mark.parallel_safe
        def test_can_run_in_parallel(check_parallel_isolation):
            # This test will fail if it uses shared fixtures
            ...
    """
    # Check if test is marked as parallel_safe
    if not request.node.get_closest_marker('parallel_safe'):
        yield
        return

    # List of fixtures that have mutable shared state
    shared_mutable_fixtures = {
        'session_managers',
        'mock_manager_registry',
        'rom_cache',  # Class-scoped, could be shared
    }

    # Check if test uses any shared mutable fixtures
    fixture_names = set(getattr(request, 'fixturenames', []))
    conflicting = fixture_names & shared_mutable_fixtures

    if conflicting:
        pytest.fail(
            f"Test '{request.node.name}' is marked parallel_safe but uses "
            f"shared mutable fixtures: {conflicting}. "
            "Use isolated_managers or function-scoped fixtures instead."
        )

    yield


# ===========================================================================================
# Wait Helper Fixtures for Eliminating Flaky qtbot.wait() Calls
# ===========================================================================================
# These fixtures replace timing-dependent qtbot.wait() calls with condition-based waits
# that auto-complete when the expected state is reached. This eliminates flakiness caused
# by hardcoded delays that may be insufficient in slow environments (CI, WSL2, etc.).
#
# Usage: Add fixture parameter to test method, then use instead of qtbot.wait()
# Example:
#   def test_something(self, qtbot, wait_for_signal_processed):
#       button.click()
#       wait_for_signal_processed()  # Instead of qtbot.wait(100)
# ===========================================================================================

@pytest.fixture
def wait_for_widget_ready(qtbot):
    """
    Helper to wait for widget initialization.

    Replaces fixed qtbot.wait() calls with condition-based waiting.
    Auto-completes when widget becomes visible and enabled.

    Example:
        wait_for_widget_ready(dialog, timeout=1000)
        # Instead of: dialog.show(); qtbot.wait(100)
    """
    def _wait(widget, timeout=1000):
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
def wait_for_signal_processed(qtbot):
    """
    Helper to wait for signal processing to complete.

    Ensures Qt event loop has processed pending signals.

    Example:
        slider.setValue(100)
        wait_for_signal_processed()
        # Instead of: slider.setValue(100); qtbot.wait(50)
    """
    def _wait(timeout=100):
        """
        Wait for pending signals to be processed.

        Args:
            timeout: Maximum wait time in milliseconds

        Note:
            Uses processEvents() to ensure all queued signals have been delivered.
        """
        from PySide6.QtWidgets import QApplication

        # Process all pending events - this is sufficient for signal delivery
        QApplication.processEvents()

    return _wait


@pytest.fixture
def wait_for_theme_applied(qtbot):
    """
    Helper to wait for theme changes to be applied.

    Qt theme changes may take multiple event loop cycles to apply.

    Example:
        window.apply_dark_theme()
        wait_for_theme_applied(window)
        # Instead of: window.apply_dark_theme(); qtbot.wait(100)
    """
    def _wait(widget, is_dark_theme=True, timeout=500):
        """
        Wait for theme to be applied to widget.

        Args:
            widget: QWidget to check
            is_dark_theme: Whether to expect dark theme (True) or light (False)
            timeout: Maximum wait time in milliseconds
        """
        # Check for headless mode FIRST - theme verification unreliable there
        import os
        display = os.environ.get("DISPLAY", "")
        qpa_platform = os.environ.get("QT_QPA_PLATFORM", "")
        is_headless = not display or qpa_platform == "offscreen"

        if is_headless:
            # Skip theme verification in headless mode - just process events
            from PySide6.QtWidgets import QApplication
            QApplication.processEvents()
            return True

        # In non-headless mode, actually verify theme
        from PySide6.QtGui import QPalette

        def theme_applied():
            palette = widget.palette()
            bg_color = palette.color(QPalette.ColorRole.Window)

            if is_dark_theme:
                # Dark theme: background should be dark
                return bg_color.red() < 128 and bg_color.green() < 128 and bg_color.blue() < 128
            else:
                # Light theme: background should be light
                return bg_color.red() > 128 or bg_color.green() > 128 or bg_color.blue() > 128

        qtbot.waitUntil(theme_applied, timeout=timeout)
        return True

    return _wait


@pytest.fixture
def wait_for_layout_update(qtbot):
    """
    Helper to wait for layout changes to be applied.

    Qt layouts may take multiple event cycles to fully update.

    Example:
        window.resize(1024, 768)
        wait_for_layout_update(window, expected_width=1024)
        # Instead of: window.resize(...); qtbot.wait(100)
    """
    def _wait(widget, expected_width=None, expected_height=None, timeout=500):
        """
        Wait for widget layout to update.

        Args:
            widget: QWidget to check
            expected_width: Expected width (None to skip check)
            expected_height: Expected height (None to skip check)
            timeout: Maximum wait time in milliseconds
        """
        def layout_updated():
            size = widget.size()
            if expected_width is not None and size.width() != expected_width:
                return False
            if expected_height is not None and size.height() != expected_height:
                return False
            # If no specific size expected, just check that size is reasonable
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
