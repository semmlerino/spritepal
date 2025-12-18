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
- `fixtures/xdist_fixtures.py`: Parallel test execution support

## Parallel Execution (pytest-xdist)

Tests run in parallel by default with `-n auto`. The policy is:
- Tests using `session_managers` are automatically serialized (xdist_group="serial")
- Tests marked `@pytest.mark.parallel_unsafe` or `@pytest.mark.serial` are serialized
- All other tests run in parallel across workers

For serial debugging: `pytest -n 0`

## Fixture Scopes

- **qt_app**: Session scope (shared QApplication across all tests)
- **session_managers**: Session scope (shared managers, requires @shared_state_safe)
- **isolated_managers**: Function scope (fresh managers per test, recommended default)
- **main_window**: Function scope (real Qt signals via RealTestMainWindow)

## State Isolation

Tests using `session_managers` require `@pytest.mark.shared_state_safe` marker
to acknowledge shared state. Mixing `session_managers` and `isolated_managers`
in the same module is prohibited.

For most tests, use `isolated_managers` for complete isolation between tests.
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
        "no_manager_setup: Skip manager initialization for this test"
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


def pytest_sessionstart(session: Any) -> None:
    """Capture thread baseline at session start before any tests run.

    This is more reliable than module import time because:
    1. It runs after pytest infrastructure is fully initialized
    2. It runs before any test fixtures are set up
    3. Under xdist, each worker gets its own session start

    The baseline is stored on session.config and can be accessed by fixtures
    via request.config._thread_baseline and request.config._thread_identities.
    """
    import threading

    session.config._thread_baseline = threading.active_count()
    session.config._thread_identities = {
        t.ident: t.name for t in threading.enumerate() if t.ident is not None
    }


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

    def find_module(self, fullname: str, path: Any = None) -> _QPixmapGuardImportFinder | None:
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
        "--require-real-hal",
        action="store_true",
        default=False,
        help="Fail (don't skip) if real HAL binaries not found for @real_hal tests"
    )
    parser.addoption(
        "--leak-mode",
        action="store",
        choices=["fail", "warn"],
        default=default_leak_mode,
        help=f"Leak policy: fail or warn for resource/thread leaks. Default: {'fail' if is_ci else 'warn'} ({'CI' if is_ci else 'local'}). Override with SPRITEPAL_LEAK_MODE env var."
    )
    # NOTE: --run-segfault-tests option removed - segfault-prone tests have been deleted


def _uses_session_fixtures(item: Any) -> bool:
    """Check if a test item uses session-dependent fixtures.

    Uses static whitelist detection for reliability under parallel collection.

    IMPORTANT: Custom fixtures wrapping session_managers must either:
    1. Be added to SESSION_DEPENDENT_FIXTURES in core_fixtures.py, or
    2. Be marked with @pytest.mark.parallel_unsafe

    The previous dynamic detection using pytest's getfixturedefs() was unreliable
    under xdist parallel collection because:
    - Multiple workers collect tests simultaneously
    - Fixture manager state may be incomplete during collection
    - Silent failures caused non-deterministic serialization

    Args:
        item: pytest test item

    Returns:
        True if the test uses session_managers or known dependent fixtures
    """
    from tests.fixtures.core_fixtures import SESSION_DEPENDENT_FIXTURES

    fixture_names = set(getattr(item, 'fixturenames', []))
    return bool(fixture_names & SESSION_DEPENDENT_FIXTURES)


def pytest_collection_modifyitems(config: Any, items: list[Any]) -> None:
    """Validate marker usage and enforce PARALLEL BY DEFAULT xdist policy.

    This hook performs three functions:
    1. Tracks real_hal marked tests for reporting
    2. Validates that skip_thread_cleanup markers have a reason argument
    3. Enforces PARALLEL BY DEFAULT xdist policy - tests using session_managers
       are auto-serialized, all others run in parallel

    The xdist policy ensures that:
    - Tests using session_managers are auto-grouped to 'serial' worker
    - Tests marked @pytest.mark.parallel_unsafe are forced to 'serial' worker
    - ALL OTHER tests can distribute across workers (true parallelism)

    This is the inverse of the previous "serial by default" policy.
    Tests no longer need @pytest.mark.parallel_safe to run in parallel.

    Args:
        config: pytest config object (required by hook signature)
        items: list of test items being collected
    """
    import warnings

    # === Track real_hal tests for CI visibility ===
    real_hal_tests = [item for item in items if item.get_closest_marker('real_hal')]
    config._real_hal_test_count = len(real_hal_tests)
    config._real_hal_test_nodeids = [item.nodeid for item in real_hal_tests]

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

    # === Auto-serialize session-dependent tests for xdist ===
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

    # PARALLEL BY DEFAULT: Only tests using session_managers are serialized
    serial_group = pytest.mark.xdist_group("serial")

    for item in items:
        # Skip tests already marked with xdist_group
        if item.get_closest_marker("xdist_group"):
            continue

        # Force serial if marked parallel_unsafe or serial
        if item.get_closest_marker("parallel_unsafe") or item.get_closest_marker("serial"):
            item.add_marker(serial_group)
            continue

        # Auto-detect session fixture usage (direct and transitive)
        if _uses_session_fixtures(item):
            item.add_marker(serial_group)
            continue

        # Deprecation warning for parallel_safe marker (no longer needed)
        if item.get_closest_marker("parallel_safe"):
            warnings.warn(
                f"{item.nodeid}: @pytest.mark.parallel_safe is deprecated. "
                "Tests are now parallel by default. Remove this marker.",
                DeprecationWarning,
                stacklevel=1
            )

        # DEFAULT: No marker = runs in parallel (the key inversion)

    # Validate no module uses both session_managers and isolated_managers
    _validate_no_same_module_mixing(items)


def _validate_no_same_module_mixing(items: list[Any]) -> None:
    """Fail fast if a module uses both session_managers and isolated_managers.

    This validation runs at collection time (not fixture setup time) for reliability
    under xdist parallel collection. The previous runtime detection in isolated_managers
    caused false positives because _session_state.is_initialized persists per-worker,
    not per-module.

    Args:
        items: list of pytest test items

    Raises:
        pytest.fail: If any module uses both fixture types
    """
    from collections import defaultdict

    from tests.fixtures.core_fixtures import SESSION_DEPENDENT_FIXTURES

    # Group fixtures by module
    module_fixtures: dict[str, set[str]] = defaultdict(set)
    for item in items:
        module = getattr(item.module, '__name__', None) if hasattr(item, 'module') else None
        if module:
            fixture_names = set(getattr(item, 'fixturenames', []))
            module_fixtures[module].update(fixture_names)

    # Check for mixing
    for module, fixtures in module_fixtures.items():
        uses_session = bool(fixtures & SESSION_DEPENDENT_FIXTURES)
        uses_isolated = 'isolated_managers' in fixtures
        if uses_session and uses_isolated:
            pytest.fail(
                f"Module '{module}' uses both session_managers and isolated_managers. "
                "This causes order-dependent failures under parallel execution.\n"
                "Fix: Use ONE fixture type per module:\n"
                "  - Use isolated_managers for tests that need clean state (default)\n"
                "  - Use session_managers + @pytest.mark.shared_state_safe for read-only tests\n"
                "See CLAUDE.md 'Test Fixture Selection Guide' for guidance.",
                pytrace=False,
            )


def pytest_sessionfinish(session: Any, exitstatus: int) -> None:
    """Clean up all singletons at session end to prevent state pollution.

    Uses the centralized reset_all_singletons() helper to ensure consistent
    cleanup across the test suite.
    """
    from tests.fixtures.core_fixtures import reset_all_singletons
    reset_all_singletons()


def pytest_terminal_summary(terminalreporter: Any, exitstatus: int, config: Any) -> None:
    """Report real_hal test execution summary for CI visibility.

    Warns if real_hal tests were skipped due to missing HAL binaries,
    making silent failures visible in CI output.
    """
    if not hasattr(config, '_real_hal_test_count'):
        return

    total_count = config._real_hal_test_count
    if total_count == 0:
        return

    # Count skipped real_hal tests by checking skip reasons
    skipped_real_hal = 0
    skipped_stats = terminalreporter.stats.get('skipped', [])
    real_hal_nodeids = set(getattr(config, '_real_hal_test_nodeids', []))

    for report in skipped_stats:
        # Check if this skipped test is a real_hal test
        if report.nodeid in real_hal_nodeids:
            skipped_real_hal += 1

    if skipped_real_hal > 0:
        terminalreporter.write_line("")
        terminalreporter.write_line(
            f"WARNING: {skipped_real_hal}/{total_count} @real_hal tests were SKIPPED "
            "(HAL binaries not found)",
            yellow=True,
        )
        terminalreporter.write_line(
            "  Set SPRITEPAL_EXHAL_PATH and SPRITEPAL_INHAL_PATH, or use --require-real-hal to fail instead",
            yellow=True,
        )


def pytest_runtest_setup(item: Any) -> None:
    """Record registry state before test runs.

    Performance optimization: Only imports ManagerRegistry for tests that use
    manager-related fixtures, avoiding import overhead for pure unit tests.
    """
    import os

    # Fixtures that indicate manager involvement
    manager_related = {
        'session_managers', 'class_managers', 'isolated_managers',
        'managers', 'managers_initialized',
        'real_factory', 'manager_context', 'real_extraction_manager',
        'real_injection_manager', 'real_session_manager',
        'test_extraction_manager', 'test_injection_manager', 'test_session_manager',
        'complete_test_context', 'minimal_injection_context',
        'mock_main_window', 'main_window',
    }

    # Fixtures that manage registry lifecycle (don't fail pre-test for these)
    # This matches the original assert_registry_clean_under_xdist exemptions
    cleanup_fixtures = {
        'isolated_managers', 'session_managers', 'manager_context',
        'managers', 'managers_initialized',  # Legacy manager fixtures
        'real_factory', 'real_extraction_manager', 'real_session_manager',
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
        is_clean = ManagerRegistry.is_clean()
        item._registry_was_clean = is_clean

        # Under xdist: fail if registry is dirty BEFORE test (pollution from previous)
        # But only for tests NOT using cleanup fixtures (those manage lifecycle themselves)
        is_xdist = os.environ.get("PYTEST_XDIST_WORKER") is not None
        has_escape_marker = item.get_closest_marker("allows_registry_state")
        uses_cleanup_fixture = bool(cleanup_fixtures.intersection(fixture_names))

        if is_xdist and not is_clean and not has_escape_marker and not uses_cleanup_fixture:
            pytest.fail(
                f"Registry dirty before {item.name} - "
                "previous test leaked state or direct instantiation detected. "
                "Use isolated_managers fixture or reset after test."
            )
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
    cleanup_fixtures = {'isolated_managers', 'session_managers'}
    if cleanup_fixtures.intersection(fixture_names):
        return  # Test uses a fixture that manages registry lifecycle

    # Performance optimization: skip import for non-manager tests
    manager_related = {
        'session_managers', 'class_managers', 'isolated_managers',
        'managers', 'managers_initialized',
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
# Test Data Factories (not in modular files - specific to test data creation)
# ============================================================================
# NOTE: xdist registry cleanliness check has been consolidated into
# pytest_runtest_setup hook above for better performance (single import)

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
# Test Cleanup Verification
# ============================================================================

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
    """Soft validation for parallel test best practices.

    NOTE: The @pytest.mark.parallel_safe marker is DEPRECATED. Tests run in
    parallel by default. This fixture now only emits a deprecation warning
    if the marker is present, and provides soft recommendations for best practices.

    Best practices for parallel-safe tests:
    1. Use isolated_managers (not session_managers)
    2. Use tmp_path for any file operations
    3. Don't depend on test execution order

    To force serial execution, use @pytest.mark.parallel_unsafe instead.
    """
    import warnings

    # Emit deprecation warning if parallel_safe marker is present
    if request.node.get_closest_marker('parallel_safe'):
        warnings.warn(
            f"Test '{request.node.name}' uses deprecated @pytest.mark.parallel_safe marker. "
            "Tests are parallel by default; this marker is ignored. "
            "Use @pytest.mark.parallel_unsafe to force serial execution.",
            DeprecationWarning,
            stacklevel=2,
        )

    yield


@pytest.fixture(autouse=True)
def enforce_shared_state_safe(request: FixtureRequest) -> Generator[None, None, None]:
    """Enforce that session_managers usage requires @pytest.mark.shared_state_safe.

    This fixture validates at test execution time that any test using session_managers
    has the shared_state_safe marker, ensuring developers consciously acknowledge
    they're using shared state.

    The marker requirement ensures:
    1. Developers understand session_managers shares state across tests
    2. Tests are reviewed for statelessness before using session_managers
    3. Order-dependent test failures are easier to diagnose

    NOTE: State drift detection via hashing was removed because:
    - It accessed private manager attributes (_settings, _runtime_state, etc.)
    - Per-test JSON hashing added overhead
    - Schema drift caused false positives
    - Isolation is now guaranteed by fixture scoping (use isolated_managers)
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

    yield
    # No post-test state validation - isolation is guaranteed by fixture scoping


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
