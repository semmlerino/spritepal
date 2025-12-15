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
- mock_manager_registry: Function scope (fresh per test for isolation)
- real_extraction_manager: Class scope (51 → ~12 instances, 77% reduction)
- rom_cache: Class scope (48 → ~10 instances, 79% reduction)
- mock_settings_manager: Class scope (44 → ~10 instances, 77% reduction)
- real_session_manager: Class scope (26 → ~8 instances, 69% reduction)

## State Isolation

Class-scoped and module-scoped fixtures include automatic state reset
mechanisms to ensure test isolation:

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
import sys

import pytest

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
    "tests.fixtures.xdist_fixtures",  # Parallel test execution support
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
    # New markers for autouse fixture opt-out
    config.addinivalue_line(
        "markers",
        "skip_thread_cleanup: Skip automatic thread cleanup for tests that manage their own threads"
    )
    config.addinivalue_line(
        "markers",
        "shared_state_ok: Allow test to inherit session manager state without triggering pollution detection"
    )
    config.addinivalue_line(
        "markers",
        "shared_state_safe: Mark test as verified safe for use with session_managers (required for session_managers usage)"
    )
    config.addinivalue_line(
        "markers",
        "skip_qpixmap_guard: Skip QPixmap threading guard for tests with special QPixmap needs"
    )
    config.addinivalue_line(
        "markers",
        "skip_hal_reset: Skip HAL singleton reset for tests that manage HAL lifecycle manually"
    )
    config.addinivalue_line(
        "markers",
        "no_qt: Skip all Qt-related fixtures (implies skip_thread_cleanup, skip_qpixmap_guard)"
    )
    config.addinivalue_line(
        "markers",
        "no_hal: Skip all HAL-related fixtures (implies skip_hal_reset)"
    )
    config.addinivalue_line(
        "markers",
        "requires_display: Test requires a real display (skips cleanly in offscreen mode)"
    )
    config.addinivalue_line(
        "markers",
        "requires_real_rom: Test requires real Kirby ROM file (skips if not available)"
    )
    config.addinivalue_line(
        "markers",
        "skip_session_reset: Skip automatic session manager state reset"
    )
    config.addinivalue_line(
        "markers",
        "allows_resource_leaks: Allow test to have resource leaks without failure"
    )

    # Make implicit RealComponentFactory warnings visible when we add them
    config.addinivalue_line(
        "filterwarnings",
        "default:RealComponentFactory.*implicit init"
    )

    # Install QPixmap guard early - catches most cases since qt_app imports Qt early
    _install_qpixmap_guard_early()


def _install_qpixmap_guard_early() -> None:
    """Install QPixmap guard at session start if Qt is available.

    This runs before any test collection/execution, ensuring the guard is in place
    even for tests that import Qt late. The per-test fixture guard_qpixmap_threading
    remains as a fallback.
    """
    try:
        from PySide6.QtCore import QCoreApplication, QThread
        from PySide6.QtGui import QPixmap

        if hasattr(QPixmap, '_test_guard_installed'):
            return  # Already installed

        original_init = QPixmap.__init__

        def guarded_init(self, *args, **kwargs):
            app = QCoreApplication.instance()
            if app and QThread.currentThread() != app.thread():
                raise RuntimeError(
                    "CRITICAL: QPixmap created in worker thread! "
                    "Use QImage or ThreadSafeTestImage."
                )
            original_init(self, *args, **kwargs)

        QPixmap.__init__ = guarded_init
        QPixmap._test_guard_installed = True  # pyright: ignore[reportAttributeAccessIssue]
    except ImportError:
        pass  # Qt not available, skip guard


def pytest_addoption(parser: Any) -> None:
    """Add custom command line options for SpritePal tests."""
    default_leak_mode = os.environ.get("SPRITEPAL_LEAK_MODE", "fail").lower()
    if default_leak_mode not in {"fail", "warn"}:
        default_leak_mode = "fail"

    parser.addoption(
        "--use-real-hal",
        action="store_true",
        default=False,
        help="Use real HAL process pool instead of mocks (slower)"
    )
    parser.addoption(
        "--leak-mode",
        action="store",
        choices=["fail", "warn"],
        default=default_leak_mode,
        help="Leak policy: fail (default) or warn for resource/thread leaks; override with SPRITEPAL_LEAK_MODE."
    )
    # NOTE: --run-segfault-tests option removed - segfault-prone tests have been deleted


def pytest_collection_modifyitems(config: Any, items: list[Any]) -> None:
    """Validate marker usage during test collection.

    Enforces that skip_thread_cleanup markers have a reason argument to prevent
    mass opt-out from thread leak detection without documentation.

    Args:
        config: pytest config object (required by hook signature)
        items: list of test items being collected
    """
    for item in items:
        marker = item.get_closest_marker("skip_thread_cleanup")
        if marker is not None:
            # Check if reason kwarg is provided
            reason = marker.kwargs.get("reason")
            if not reason:
                raise pytest.UsageError(
                    f"Test {item.nodeid} uses @pytest.mark.skip_thread_cleanup "
                    "without a reason. Add reason='...' explaining why thread "
                    "cleanup should be skipped for this test.\n"
                    "Example: @pytest.mark.skip_thread_cleanup(reason='Uses session_managers which owns threads')"
                )


def pytest_sessionfinish(session: Any, exitstatus: int) -> None:
    """Clean up all singletons at session end to prevent state pollution.

    This hook ensures:
    1. ManagerRegistry singleton is fully reset
    2. DataRepository temp files are cleaned up
    3. HAL process pool singleton is reset

    Without this, state can leak between test runs or cause errors
    in subsequent test sessions.
    """
    # 1. Reset ManagerRegistry singleton completely using official API
    with contextlib.suppress(Exception):
        from core.managers.registry import ManagerRegistry
        ManagerRegistry.reset_for_tests()

    # 2. Clean up DataRepository (temp files and singleton)
    with contextlib.suppress(Exception):
        from tests.infrastructure.test_data_repository import cleanup_test_data_repository
        cleanup_test_data_repository()

    # 3. Reset HAL singleton using official API
    with contextlib.suppress(Exception):
        from core.hal_compression import HALProcessPool
        HALProcessPool.reset_for_tests()


def pytest_runtest_setup(item: Any) -> None:
    """Record registry state before test runs."""
    try:
        from core.managers.registry import ManagerRegistry
        # Store whether registry was clean BEFORE the test
        item._registry_was_clean = ManagerRegistry.is_clean()
    except ImportError:
        item._registry_was_clean = True  # Assume clean if can't check


def pytest_runtest_teardown(item: Any, nextitem: Any) -> None:
    """Enforce ManagerRegistry cleanup after each test.

    This hook converts documentation ("use isolated_managers") into runtime
    enforcement. Tests that DIRTY the registry (change it from clean to dirty)
    without using a manager fixture will fail.

    This catches:
    - Tests that initialize managers without cleanup fixtures
    - Accidental state pollution between tests

    This does NOT catch:
    - Tests that inherit dirty state from previous tests (use isolated_managers to fix)
    - Tests explicitly marked to allow registry state
    """
    # Skip enforcement for tests that opt out
    if item.get_closest_marker("allows_registry_state"):
        return
    if item.get_closest_marker("shared_state_ok"):
        return

    # Only check tests that didn't use manager fixtures
    fixture_names = getattr(item, 'fixturenames', [])
    cleanup_fixtures = {'isolated_managers', 'setup_managers', 'session_managers'}
    if cleanup_fixtures.intersection(fixture_names):
        return  # Test uses a fixture that manages registry lifecycle

    # Check if THIS test dirtied the registry
    try:
        from core.managers.registry import ManagerRegistry

        was_clean = getattr(item, '_registry_was_clean', True)
        is_clean_now = ManagerRegistry.is_clean()

        # Only fail if the test changed state from clean to dirty
        if was_clean and not is_clean_now:
            pytest.fail(
                f"Test '{item.name}' initialized ManagerRegistry without a manager fixture.\n"
                "Fix: Use isolated_managers fixture, or add "
                "@pytest.mark.allows_registry_state if intentional."
            )
    except ImportError:
        pass  # ManagerRegistry not available, skip check


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
# Function-scoped fixtures for proper test isolation
# ============================================================================

@pytest.fixture(scope="function")
def mock_manager_registry() -> Generator[Mock, None, None]:
    """Function-scoped mock registry for proper test isolation.

    Changed from module-scope to function-scope to ensure:
    - Each test gets a fresh mock instance
    - No call history leaks between tests
    - No return value pollution between tests

    The ~80ms overhead (81 tests × ~1ms per Mock) is negligible compared
    to the determinism benefit of fresh state per test.
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
    # No cleanup needed - fixture is discarded after each test


# ============================================================================
# Qt Threading Safety Fixtures
# ============================================================================

@pytest.fixture(autouse=True)
def guard_qpixmap_threading(request: FixtureRequest, monkeypatch: pytest.MonkeyPatch):
    """Prevent QPixmap creation in worker threads during tests (autouse).

    This fixture monkeypatches QPixmap.__init__ to raise a RuntimeError
    if it's called from a non-GUI thread, helping to identify critical
    Qt threading violations that cause segfaults.

    This is now autouse (was previously opt-in). The overhead is minimal
    and the protection against silent Qt crashes is worth it.

    Opt-out markers:
        @pytest.mark.skip_qpixmap_guard - Skip for tests that can't use the guard
        @pytest.mark.no_qt - Skip for non-Qt tests
    """
    markers = [m.name for m in request.node.iter_markers()]

    # Opt-OUT: Skip if explicitly marked
    if 'skip_qpixmap_guard' in markers or 'no_qt' in markers:
        yield
        return

    # Don't import PySide6 if it hasn't been imported yet - avoids pulling
    # Qt into non-Qt tests that don't have the no_qt marker
    if 'PySide6.QtGui' not in sys.modules:
        yield
        return

    try:
        from PySide6.QtCore import QCoreApplication, QThread
        from PySide6.QtGui import QPixmap
    except ImportError:
        # Qt not available, skip the guard
        yield
        return

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


@pytest.fixture(autouse=True)
def skip_requires_display(request: FixtureRequest):
    """Skip tests marked with @pytest.mark.requires_display when running headless.

    This fixture provides a clean skip mechanism for tests that require a real
    display (not offscreen mode). Use this instead of xfail for environment
    capabilities.

    Example:
        @pytest.mark.requires_display
        def test_real_dialog():
            '''This test needs a real display.'''
            ...  # Skips cleanly in CI/offscreen, runs with real display
    """
    marker = request.node.get_closest_marker("requires_display")
    if marker is not None:
        # Check if running in offscreen mode
        qpa_platform = os.environ.get("QT_QPA_PLATFORM", "")
        if qpa_platform == "offscreen":
            pytest.skip("Test requires real display (not offscreen mode)")


# ============================================================================
# Class-scoped State Reset Fixtures
# ============================================================================

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


@pytest.fixture(autouse=True)
def check_parallel_isolation(request: FixtureRequest) -> Generator[None, None, None]:
    """Enforce that parallel-safe tests don't use shared mutable state.

    This fixture automatically checks that tests marked with @pytest.mark.parallel_safe
    don't use session-scoped or class-scoped fixtures that could cause race conditions
    when running tests in parallel with pytest-xdist.

    The check runs automatically for all parallel_safe tests.

    Requirements for parallel_safe tests:
    1. Must use isolated_managers (not session_managers, class_managers, fast_managers)
    2. Should use tmp_path for any file operations
    3. Must not depend on test execution order

    Usage:
        @pytest.mark.parallel_safe
        def test_can_run_in_parallel(isolated_managers, tmp_path):
            # This test is validated automatically
            ...
    """
    # Only validate tests marked as parallel_safe
    if not request.node.get_closest_marker('parallel_safe'):
        yield
        return

    # Fixtures that have mutable shared state and are unsafe for parallel execution
    # These are session-scoped or class-scoped fixtures that persist across tests
    shared_mutable_fixtures = {
        'session_managers',  # Session-scoped, shares state across all tests in session
        'class_managers',    # Class-scoped, shares state within test class
        'fast_managers',     # Alias for session_managers
        'rom_cache',         # Class-scoped cache that could be shared
    }

    # Check if test uses any shared mutable fixtures
    fixture_names = set(getattr(request, 'fixturenames', []))
    conflicting = fixture_names & shared_mutable_fixtures

    if conflicting:
        pytest.fail(
            f"Test '{request.node.name}' is marked @pytest.mark.parallel_safe but uses "
            f"shared mutable fixtures: {conflicting}. "
            "Use isolated_managers and tmp_path for parallel-safe tests."
        )

    # Validate that isolated_managers is used (recommended for parallel tests)
    if 'isolated_managers' not in fixture_names:
        # Check if it might be using managers at all
        manager_related = {'setup_managers', 'managers_initialized'}
        if manager_related & fixture_names:
            pytest.fail(
                f"Test '{request.node.name}' is marked @pytest.mark.parallel_safe but uses "
                f"manager fixtures other than isolated_managers. "
                "Use isolated_managers for parallel-safe tests."
            )

    yield


# ===========================================================================================
# Wait Helper Fixtures for Eliminating Flaky qtbot.wait() Calls
# ===========================================================================================
# These fixtures are consolidated in tests/fixtures/qt_waits.py and re-exported here.
# See that module for implementation details.
#
# Usage: Add fixture parameter to test method, then use instead of qtbot.wait()
# Example:
#   def test_something(self, qtbot, wait_for_signal_processed):
#       button.click()
#       wait_for_signal_processed()  # Instead of qtbot.wait(100)
# ===========================================================================================

# Re-export wait helpers from shared module
from tests.fixtures.qt_waits import (
    process_events,
    wait_for,
    wait_for_layout_update,
    wait_for_signal_processed,
    wait_for_theme_applied,
    wait_for_widget_ready,
)
