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

- `reset_class_state`: Auto-resets all class-scoped fixtures (autouse, runs automatically)

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
        "golden_hal: Verify HAL output against recorded golden checksums (no real binary needed)"
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
    config.addinivalue_line(
        "markers",
        "parallel_unsafe: Force test to run in serial mode under xdist (use when wrapper fixtures hide shared state)"
    )
    config.addinivalue_line(
        "markers",
        "lenient_reset: Downgrade class fixture reset errors to warnings (for legacy tests during migration)"
    )

    # Make implicit RealComponentFactory warnings visible when we add them
    config.addinivalue_line(
        "filterwarnings",
        "default:RealComponentFactory.*implicit init"
    )

    # Install QPixmap guard via import hook - guarantees guard is installed even for late Qt imports
    _install_qpixmap_guard_unconditional()


def _patch_qpixmap_init() -> None:
    """Patch QPixmap.__init__ to detect worker thread usage."""
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


class _QPixmapGuardImportFinder:
    """Import hook to install QPixmap guard when PySide6.QtGui is imported."""

    _installed: bool = False

    def find_module(self, fullname: str, path: Any = None) -> "_QPixmapGuardImportFinder | None":
        """Return self if this is PySide6.QtGui, else None."""
        if fullname == 'PySide6.QtGui' and not self._installed:
            return self
        return None

    def load_module(self, fullname: str) -> Any:
        """Load the real module, then install QPixmap guard."""
        import importlib

        # Remove ourselves from meta_path to avoid recursion
        if self in sys.meta_path:
            sys.meta_path.remove(self)

        # Mark as installed to prevent re-triggering
        _QPixmapGuardImportFinder._installed = True

        # Import the real module
        module = importlib.import_module(fullname)

        # Install the guard on QPixmap
        _patch_qpixmap_init()

        return module


def _install_qpixmap_guard_unconditional() -> None:
    """Install QPixmap guard unconditionally via import hook.

    This ensures the guard is installed even for tests that import Qt late.
    Uses an import hook that triggers as soon as PySide6.QtGui is imported.
    """
    # If Qt is already imported, patch directly
    if 'PySide6.QtGui' in sys.modules:
        _patch_qpixmap_init()
        return

    # Otherwise, install an import hook to patch when Qt is imported
    # Check if our hook is already installed
    if not any(isinstance(finder, _QPixmapGuardImportFinder) for finder in sys.meta_path):
        sys.meta_path.insert(0, _QPixmapGuardImportFinder())


def pytest_addoption(parser: Any) -> None:
    """Add custom command line options for SpritePal tests."""
    # Determine default leak mode: "fail" in CI, "warn" locally
    # Can be overridden by SPRITEPAL_LEAK_MODE environment variable
    is_ci = os.environ.get("CI") == "true"
    env_leak_mode = os.environ.get("SPRITEPAL_LEAK_MODE", "").lower()

    if env_leak_mode in {"fail", "warn"}:
        default_leak_mode = env_leak_mode
    else:
        # Default: fail in CI, warn locally
        default_leak_mode = "fail" if is_ci else "warn"

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
        help=f"Leak policy: fail or warn for resource/thread leaks. Default: {'fail' if is_ci else 'warn'} ({'CI' if is_ci else 'local'}). Override with SPRITEPAL_LEAK_MODE env var."
    )
    # NOTE: --run-segfault-tests option removed - segfault-prone tests have been deleted


def pytest_collection_modifyitems(config: Any, items: list[Any]) -> None:
    """Validate marker usage and enforce serial-by-default xdist policy.

    This hook performs two functions:
    1. Validates that skip_thread_cleanup markers have a reason argument
    2. Enforces SERIAL BY DEFAULT xdist policy - only @pytest.mark.parallel_safe
       tests can distribute across workers

    The xdist policy ensures that:
    - Tests marked @pytest.mark.parallel_safe run on any worker (true parallelism)
    - ALL OTHER tests get grouped to a single 'serial' worker (safe default)

    This conservative approach prevents unmarked tests from racing on hidden
    globals. Tests must explicitly opt-in to parallel execution by being
    marked parallel_safe.

    Args:
        config: pytest config object (required by hook signature)
        items: list of test items being collected
    """
    # === Validate skip_thread_cleanup markers ===
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

    # === Auto-group non-parallel_safe tests for xdist ===
    # Only apply when xdist plugin is active and -n option is used
    if not config.pluginmanager.has_plugin("xdist"):
        return

    # Check if -n option is being used (workers > 0)
    try:
        worker_count = config.getoption("-n", default=None)
    except ValueError:
        # Option not registered (xdist not properly loaded)
        return

    if not worker_count or worker_count == "0":
        return

    # SERIAL BY DEFAULT: Only tests explicitly marked parallel_safe can distribute
    # This prevents unmarked tests from racing on hidden globals
    serial_group = pytest.mark.xdist_group("serial")

    for item in items:
        # Skip tests already marked with xdist_group
        if item.get_closest_marker("xdist_group"):
            continue

        # Tests explicitly marked parallel_safe can distribute to any worker
        if item.get_closest_marker("parallel_safe"):
            continue  # No serial marker = can run in parallel

        # Everything else runs serial (safe default)
        item.add_marker(serial_group)


def pytest_sessionfinish(session: Any, exitstatus: int) -> None:
    """Clean up all singletons at session end to prevent state pollution.

    Uses the centralized reset_all_singletons() helper to ensure consistent
    cleanup across the test suite.
    """
    from tests.fixtures.core_fixtures import reset_all_singletons
    reset_all_singletons()


def pytest_runtest_setup(item: Any) -> None:
    """Record registry state before test runs.

    Performance optimization: Only imports ManagerRegistry for tests that use
    manager-related fixtures, avoiding import overhead for pure unit tests.
    """
    # Fixtures that indicate manager involvement
    manager_related = {
        'session_managers', 'class_managers', 'isolated_managers',
        'managers', 'setup_managers', 'managers_initialized',
        'real_factory', 'manager_context', 'real_extraction_manager',
        'real_injection_manager', 'real_session_manager',
        'test_extraction_manager', 'test_injection_manager', 'test_session_manager',
        'complete_test_context', 'minimal_injection_context',
        'mock_main_window', 'main_window',
    }

    fixture_names = set(getattr(item, 'fixturenames', []))
    if not manager_related.intersection(fixture_names):
        item._registry_was_clean = True  # Assume clean for non-manager tests
        return

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

    Performance optimization: Only imports ManagerRegistry for tests that use
    manager-related fixtures, avoiding import overhead for pure unit tests.

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
    fixture_names = set(getattr(item, 'fixturenames', []))
    cleanup_fixtures = {'isolated_managers', 'setup_managers', 'session_managers'}
    if cleanup_fixtures.intersection(fixture_names):
        return  # Test uses a fixture that manages registry lifecycle

    # Performance optimization: skip import for non-manager tests
    manager_related = {
        'session_managers', 'class_managers', 'isolated_managers',
        'managers', 'setup_managers', 'managers_initialized',
        'real_factory', 'manager_context', 'real_extraction_manager',
        'real_injection_manager', 'real_session_manager',
        'test_extraction_manager', 'test_injection_manager', 'test_session_manager',
        'complete_test_context', 'minimal_injection_context',
        'mock_main_window', 'main_window',
    }
    if not manager_related.intersection(fixture_names):
        return  # Test doesn't use managers - skip check

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
# xdist Registry Cleanliness Check
# ============================================================================

@pytest.fixture(autouse=True)
def assert_registry_clean_under_xdist(
    request: pytest.FixtureRequest,
) -> Generator[None, None, None]:
    """Ensure registry is clean before/after each test under xdist.

    This fixture catches direct ManagerRegistry usage outside fixtures.
    Only active when running under pytest-xdist (PYTEST_XDIST_WORKER set).

    Tests using manager fixtures are exempt - those fixtures manage lifecycle.
    """
    import os

    # Only active under xdist workers
    if not os.environ.get("PYTEST_XDIST_WORKER"):
        yield
        return

    # Skip if test uses a manager fixture (they manage lifecycle)
    manager_fixtures = {
        "isolated_managers",
        "session_managers",
        "setup_managers",
        "manager_context",
        "real_extraction_manager",
        "real_session_manager",
        "real_factory",
        "mock_main_window",
        "main_window",
    }
    fixture_names = set(getattr(request, "fixturenames", []))
    if manager_fixtures & fixture_names:
        yield
        return

    # Skip if test has escape hatch marker
    if request.node.get_closest_marker("allows_registry_state"):
        yield
        return

    try:
        from core.managers.registry import ManagerRegistry

        registry = ManagerRegistry()

        # Before test: registry should be clean
        if registry.is_initialized():
            pytest.fail(
                f"Registry dirty before {request.node.name} - "
                "previous test leaked state or direct instantiation detected. "
                "Use isolated_managers fixture or reset after test."
            )

        yield

        # After test: if registry got initialized, that's a problem
        if registry.is_initialized():
            registry.reset_for_tests()
            pytest.fail(
                f"Test {request.node.name} initialized ManagerRegistry "
                "without using a manager fixture. "
                "Fix: Use isolated_managers fixture."
            )
    except ImportError:
        yield  # ManagerRegistry not available, skip check


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
def guard_qpixmap_threading(request: FixtureRequest):
    """Verify QPixmap threading guard is active (autouse).

    The actual guard is installed via import hook in pytest_configure
    (_install_qpixmap_guard_unconditional). This fixture just ensures
    the guard remains active for Qt tests.

    The import hook approach guarantees the guard is installed even for
    tests that import Qt late, closing the timing hole in the previous
    implementation.

    Overhead: Minimal. Early-exits for non-Qt tests (no_qt marker or
    PySide6.QtGui not imported). The marker check and sys.modules check
    are O(1) operations.

    Opt-out markers:
        @pytest.mark.skip_qpixmap_guard - Skip verification
        @pytest.mark.no_qt - Skip for non-Qt tests
    """
    markers = [m.name for m in request.node.iter_markers()]

    # Opt-OUT: Skip if explicitly marked
    if 'skip_qpixmap_guard' in markers or 'no_qt' in markers:
        yield
        return

    # If Qt is imported, verify the guard is installed
    # The import hook should have installed it when PySide6.QtGui was imported
    if 'PySide6.QtGui' in sys.modules:
        try:
            from PySide6.QtGui import QPixmap

            if not hasattr(QPixmap, '_test_guard_installed'):
                # Guard not installed - try to install it now
                # (shouldn't happen with import hook, but provides fallback)
                _patch_qpixmap_init()
        except ImportError:
            pass  # Qt not available

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

@pytest.fixture(scope="function", autouse=True)
def reset_class_state(
    request: pytest.FixtureRequest,
) -> Generator[None, None, None]:
    """SAFETY NET: Auto-reset state for class-scoped fixtures between tests.

    This is a SECONDARY cleanup mechanism. Class-scoped fixtures should have
    their own explicit finalizers via request.addfinalizer(). This autouse
    fixture provides an additional safety net to catch missed state.

    Architecture:
    - Per-fixture finalizers (primary): Run at END of fixture scope (end of class)
    - This fixture (safety net): Runs after EACH test to reset state between tests

    NOTE: This is function-scoped so it runs AFTER each test to reset
    class-scoped fixture state before the next test runs.

    IMPORTANT: reset_mock() only clears call history. We must also clear:
    - return_value (if manually configured)
    - side_effect (if manually configured)
    - Any internal state

    Reset errors fail the test by default. Use @pytest.mark.lenient_reset
    to downgrade to warnings for legacy tests during migration.

    MAINTENANCE: When adding new class-scoped fixtures that hold mutable state,
    either (preferred) add a request.addfinalizer() in the fixture definition,
    or add the fixture name to fixtures_to_reset below. The fixtures_to_reset
    set should match the class-scoped fixtures in tests/fixtures/core_fixtures.py.
    """
    # Run test first
    yield

    # Reset fixtures AFTER each test for the next one
    fixture_names = set(getattr(request, 'fixturenames', []))

    # Class-scoped fixtures that need reset between tests
    fixtures_to_reset = {
        'real_extraction_manager',  # Real component - uses reset_state() or clear()
        'real_session_manager',     # Real component - uses reset_state() or clear()
        'rom_cache',
        'mock_settings_manager',
        'main_window',
        'fast_mock_main_window',
        'mock_controller',
    }

    # Only run reset logic if test uses class-scoped fixtures
    used_class_fixtures = fixtures_to_reset & fixture_names
    if not used_class_fixtures:
        return

    # Check for lenient mode marker
    lenient = request.node.get_closest_marker("lenient_reset") is not None
    reset_errors: list[str] = []

    for fixture_name in used_class_fixtures:
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
            else:
                # No known reset method - warn about potential state leak
                reset_errors.append(
                    f"Fixture '{fixture_name}' has no reset method "
                    f"(tried: reset_state, clear_cache, clear)"
                )
        except pytest.FixtureLookupError:
            pass  # Fixture not available in this context
        except Exception as e:
            # Handle fixtures that have been torn down (common with Qt fixtures)
            # "The fixture value for X is not available" means it's already cleaned up
            error_str = str(e)
            if "not available" in error_str and "torn down" in error_str:
                pass  # Fixture already cleaned up - no reset needed
            else:
                reset_errors.append(f"Reset failed for '{fixture_name}': {e}")

    # Handle reset errors
    if reset_errors:
        error_msg = "Class fixture reset errors:\n" + "\n".join(f"  - {e}" for e in reset_errors)
        if lenient:
            import logging
            logging.getLogger(__name__).warning(error_msg)
        else:
            pytest.fail(error_msg)


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
    1. Must use isolated_managers (not session_managers, class_managers, managers)
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
        'managers',          # Depends on session_managers
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


def _safe_serialize(obj: Any) -> Any:
    """Convert objects to JSON-serializable form for hashing.

    Handles common Python types and converts them to a stable representation.
    """
    if obj is None:
        return None
    if isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, (list, tuple)):
        return [_safe_serialize(item) for item in obj]
    if isinstance(obj, dict):
        return {str(k): _safe_serialize(v) for k, v in sorted(obj.items())}
    if isinstance(obj, set):
        return sorted(str(x) for x in obj)
    if isinstance(obj, frozenset):
        return sorted(str(x) for x in obj)
    if hasattr(obj, 'name') and hasattr(obj, 'value'):  # Enum
        return obj.name
    if hasattr(obj, '__dict__'):
        # For simple objects, serialize public attributes
        return {k: _safe_serialize(v) for k, v in sorted(vars(obj).items())
                if not k.startswith('_')}
    return str(obj)


def _hash_manager_state() -> str:
    """Hash key manager state for drift detection using content-aware hashing.

    Returns a hash of manager state that would indicate test pollution.
    Unlike the previous length-based approach, this hashes actual VALUES
    so mutations that don't change collection sizes are still detected.
    """
    import hashlib
    import json

    state_data: dict[str, Any] = {}
    try:
        from core.managers.registry import ManagerRegistry

        registry = ManagerRegistry()
        if not registry.is_initialized():
            return "uninitialized"

        # Check ApplicationStateManager (the real consolidated manager)
        app_state = registry.get_application_state_manager()
        if app_state:
            # Hash actual content, not just lengths
            state_data["settings"] = _safe_serialize(getattr(app_state, '_settings', {}))
            state_data["runtime"] = _safe_serialize(getattr(app_state, '_runtime_state', {}))

            # State snapshots - hash count only (keys are timestamps, too variable)
            state_data["snapshots_count"] = len(getattr(app_state, '_state_snapshots', {}))

            # Sprite history - hash full content
            state_data["history"] = _safe_serialize(getattr(app_state, '_sprite_history', []))

            # Workflow state (enum value)
            workflow = getattr(app_state, '_workflow_state', None)
            state_data["workflow"] = workflow.name if workflow else "none"

            # Cache session stats (accumulating counters) - full values
            state_data["cache_stats"] = _safe_serialize(getattr(app_state, '_cache_session_stats', {}))

            # Preloaded offsets - hash full content
            state_data["preloaded"] = _safe_serialize(getattr(app_state, '_preloaded_offsets', set()))

        # Check CoreOperationsManager
        core_ops = registry.get_core_operations_manager()
        if core_ops:
            # Check if there's an active worker
            state_data["active_worker"] = getattr(core_ops, '_current_worker', None) is not None

    except Exception as e:
        return f"error:{type(e).__name__}"

    # Create stable hash from serialized content
    try:
        state_json = json.dumps(state_data, sort_keys=True, default=str)
        return hashlib.md5(state_json.encode()).hexdigest()[:12]
    except Exception:
        # Fallback to string representation
        state_str = str(sorted(state_data.items()))
        return hashlib.md5(state_str.encode()).hexdigest()[:12]


def _get_manager_state_details() -> dict[str, Any]:
    """Get detailed manager state for debugging.

    Returns a dict of state values that can be compared before/after a test.
    Unlike the hash function, this provides full content for debugging diffs.
    """
    state: dict[str, Any] = {}
    try:
        from core.managers.registry import ManagerRegistry

        registry = ManagerRegistry()
        if not registry.is_initialized():
            return {"status": "uninitialized"}

        app_state = registry.get_application_state_manager()
        if app_state:
            # Include actual content for detailed comparison
            settings = getattr(app_state, '_settings', {})
            state["settings_count"] = len(settings)
            state["settings_keys"] = sorted(settings.keys()) if settings else []

            runtime = getattr(app_state, '_runtime_state', {})
            state["runtime_count"] = len(runtime)
            state["runtime_keys"] = sorted(runtime.keys()) if runtime else []

            state["snapshots_count"] = len(getattr(app_state, '_state_snapshots', {}))

            history = getattr(app_state, '_sprite_history', [])
            state["history_count"] = len(history)
            # Include first few items for debugging
            state["history_preview"] = history[:3] if history else []

            workflow = getattr(app_state, '_workflow_state', None)
            state["workflow"] = workflow.name if workflow else "none"

            cache_stats = getattr(app_state, '_cache_session_stats', {})
            state["cache_stats"] = _safe_serialize(cache_stats)

            preloaded = getattr(app_state, '_preloaded_offsets', set())
            state["preloaded_count"] = len(preloaded)
            # Include first few offsets for debugging
            state["preloaded_preview"] = sorted(list(preloaded)[:5]) if preloaded else []

        core_ops = registry.get_core_operations_manager()
        if core_ops:
            state["active_worker"] = getattr(core_ops, '_current_worker', None) is not None

    except Exception as e:
        state["error"] = str(e)

    return state


@pytest.fixture(autouse=True)
def enforce_shared_state_safe(request: FixtureRequest) -> Generator[None, None, None]:
    """Enforce that session_managers usage requires @pytest.mark.shared_state_safe.

    This fixture validates at test execution time that any test using session_managers
    has the shared_state_safe marker, ensuring developers consciously acknowledge
    they're using shared state.

    Additionally, it validates that manager state doesn't drift during the test,
    catching tests that claim to be stateless but actually modify shared state.

    The marker requirement ensures:
    1. Developers understand session_managers shares state across tests
    2. Tests are reviewed for statelessness before using session_managers
    3. Order-dependent test failures are easier to diagnose
    """
    # Only check tests that use session_managers
    fixture_names = set(getattr(request, 'fixturenames', []))
    if 'session_managers' not in fixture_names:
        yield
        return

    # Require the marker
    if not request.node.get_closest_marker('shared_state_safe'):
        pytest.fail(
            f"Test '{request.node.name}' uses session_managers but lacks "
            "@pytest.mark.shared_state_safe marker. Either:\n"
            "  1. Add @pytest.mark.shared_state_safe (if test is verified stateless), or\n"
            "  2. Use isolated_managers instead (recommended for most tests)"
        )

    # Capture state before test (both hash and details for debugging)
    before_hash = _hash_manager_state()
    before_state = _get_manager_state_details()

    yield

    # Validate state unchanged after test
    after_hash = _hash_manager_state()
    if before_hash != after_hash:
        after_state = _get_manager_state_details()

        # Build detailed change report
        changed_fields: list[str] = []
        all_keys = set(before_state.keys()) | set(after_state.keys())
        for key in sorted(all_keys):
            before_val = before_state.get(key, "<missing>")
            after_val = after_state.get(key, "<missing>")
            if before_val != after_val:
                changed_fields.append(f"    {key}: {before_val} -> {after_val}")

        changes_str = "\n".join(changed_fields) if changed_fields else "    (no details available)"
        fixtures_str = ", ".join(sorted(fixture_names))

        pytest.fail(
            f"Test '{request.node.name}' modified session manager state despite "
            "@pytest.mark.shared_state_safe marker.\n"
            f"  State hash: {before_hash} -> {after_hash}\n"
            f"  Changed fields:\n{changes_str}\n"
            f"  Fixtures used: {fixtures_str}\n"
            "  Either:\n"
            "    1. Fix the test to not modify shared state, or\n"
            "    2. Use isolated_managers instead"
        )


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
